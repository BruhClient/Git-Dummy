"""Lane-assignment algorithm for the commit graph (streaming topological order)."""
from __future__ import annotations

import collections as _collections
import re as _re
from typing import Optional

from core.git_tracker import CommitInfo


def _branch_base(name: str) -> str:
    """Strip remote-tracking prefixes to get the logical branch name.

    e.g. "origin/Zen" → "Zen", "refs/remotes/origin/Zen" → "Zen"
    """
    for pfx in ("refs/remotes/origin/", "origin/", "refs/heads/"):
        name = name.removeprefix(pfx)
    return name


def _compute_lanes(
    commits: list[CommitInfo],
    branch_tip_map: dict[str, list[str]],
    local_tip_shas: set[str] | None = None,
) -> tuple[dict[str, int], dict[int, str]]:
    """
    Classic streaming lane algorithm — the same approach used by git log --graph.

    Requires commits to be in TOPOLOGICAL ORDER (children before parents),
    which graph_commits() guarantees via --topo-order.

    How it works
    ------------
    • We maintain a list of "open lanes".  Each slot holds the SHA that lane
      is currently waiting to see (its next expected commit).
    • For each commit we find which lane is expecting it, assign it there,
      then update that lane to expect the commit's first parent.
    • Merge commits open extra lanes for their additional parents.
    • When multiple lanes converge on the same SHA (a branch was merged),
      we free the stale duplicates so their slots can be reused.
    • Lane 0 is pre-seeded with the primary (main/master) tip so it
      always gets the green accent colour.
    """
    if not commits:
        return {}, {}

    # ── Lookup tables used throughout ───────────────────────────────────────
    commit_index   = {c.sha: i for i, c in enumerate(commits)}
    commit_sha_set = {c.sha for c in commits}
    commit_by_sha  = {c.sha: c for c in commits}

    # ── Identify primary branch ───────────────────────────────────────────
    primary = next(
        (n for names in branch_tip_map.values() for n in names if n in ("main", "master")),
        None,
    )

    # When multiple tips share the same branch name (e.g. local "main" and
    # "origin/main" point to different commits), decide which one anchors
    # lane 0 by walking the topologically-newest candidate's first-parent
    # chain:
    #   • If the oldest candidate is reachable from the newest via that
    #     chain, the relationship is linear (local ahead/behind) → the
    #     newest tip wins as primary.
    #   • Otherwise the branches have diverged (rebase / force-push / reset)
    #     → the oldest (established history) stays on lane 0.
    if primary:
        primary_candidates = [sha for sha, names in branch_tip_map.items()
                              if primary in names]
        if len(primary_candidates) <= 1:
            primary_tip = primary_candidates[0] if primary_candidates else None
        else:
            ordered = sorted(primary_candidates, key=lambda s: commit_index.get(s, 10**9))
            newest, oldest = ordered[0], ordered[-1]
            reachable = False
            sha = newest
            visited: set[str] = set()
            while sha in commit_sha_set and sha not in visited:
                visited.add(sha)
                if sha == oldest:
                    reachable = True
                    break
                c = commit_by_sha.get(sha)
                if not c or not c.parents:
                    break
                sha = c.parents[0]
            if reachable:
                primary_tip = newest
            else:
                if local_tip_shas:
                    remote_cands = [s for s in primary_candidates if s not in local_tip_shas]
                    primary_tip = remote_cands[0] if remote_cands else oldest
                else:
                    primary_tip = oldest
    else:
        primary_tip = None

    # ── Seed only lane 0 with the primary tip; allocate all others lazily ─
    lanes: list[Optional[str]] = []
    if primary_tip:
        lanes.append(primary_tip)

    # ── Pre-compute first-parent chain ownership ───────────────────────────
    # Non-main branches claim commits on their first-parent chain before main
    # does, so historical branch commits stay in their branch's lane even
    # after the branch has been merged into main.

    # Build main's first-parent set so non-main walks stop at the shared root.
    main_fp_set: set[str] = set()
    if primary_tip:
        sha = primary_tip
        while sha in commit_sha_set:
            main_fp_set.add(sha)
            c = commit_by_sha.get(sha)
            if not c or not c.parents:
                break
            sha = c.parents[0]

    commit_owner: dict[str, str] = {}   # sha → branch name

    def _walk_first_parent(tip_sha: str, branch_name: str,
                           stop_at: set[str] = set()) -> None:
        sha = tip_sha
        while sha in commit_sha_set and sha not in stop_at:
            if sha not in commit_owner:   # first write wins
                commit_owner[sha] = branch_name
            c = commit_by_sha.get(sha)
            if not c or not c.parents:
                break
            sha = c.parents[0]

    # Non-main branches go first (higher priority); stop when hitting main's chain
    for tip_sha, names in branch_tip_map.items():
        non_main = next(
            (n for n in names if n not in ('main', 'master', primary or '')), None
        )
        if non_main:
            _walk_first_parent(tip_sha, non_main, stop_at=main_fp_set)

    # Walk 2nd-parent chains from merge commits on each named branch's first-parent
    # chain.  This attributes commits merged INTO a branch (sync/squash merges) to
    # that branch, so the post-pass can correctly place them even when a new local
    # branch temporarily "steals" those commits via the free-slot mechanism.
    for _tip, _names in branch_tip_map.items():
        _bname = next(
            (n for n in _names if n not in ('main', 'master', primary or '')), None
        )
        if not _bname:
            continue
        _sha = _tip
        while _sha in commit_sha_set and _sha not in main_fp_set:
            _c = commit_by_sha.get(_sha)
            if not _c or not _c.parents:
                break
            if len(_c.parents) >= 2:
                _p2 = _c.parents[1]
                while _p2 in commit_sha_set and _p2 not in main_fp_set:
                    if _p2 not in commit_owner:
                        commit_owner[_p2] = _bname
                    _p2c = commit_by_sha.get(_p2)
                    if not _p2c or not _p2c.parents:
                        break
                    _p2 = _p2c.parents[0]
            _sha = _c.parents[0]

    # Mark main's first-parent chain (everything not already claimed)
    for sha in main_fp_set:
        if sha not in commit_owner:
            commit_owner[sha] = primary or 'main'

    _local = local_tip_shas or set()
    for tip_sha in sorted(
        (s for s in branch_tip_map if s != primary_tip and s in commit_sha_set),
        key=lambda s: (1 if s in _local else 0, commit_index.get(s, 10**9)),
    ):
        if not any(s == tip_sha for s in lanes):
            free = next((i for i, s in enumerate(lanes) if s is None), None)
            if free is not None:
                lanes[free] = tip_sha
            else:
                lanes.append(tip_sha)

    lane_branch: dict[int, str] = {}
    assignment: dict[str, int] = {}

    # ── 2nd-parent historical attribution (BFS) ───────────────────────────
    # For each merge commit reachable via 2nd-parent chains from main's
    # first-parent chain, walk the PR commits and attribute them to the
    # contributing branch.  BFS handles nested merges like:
    #   main_fp_set entry → 2nd parent: sync commit (e.g. "Merge branch
    #   'main' into brennen") → whose 2nd parent is the actual PR merge.
    # Non-greedy org/user segment so branch names containing "/" (e.g.
    # "feature/login-page") are captured in full rather than truncated to
    # their last path component.
    _MERGE_FROM = _re.compile(
        r'from\s+\S+?/(\S+)', _re.MULTILINE | _re.IGNORECASE
    )
    _bfs_queue: _collections.deque[str] = _collections.deque(
        sorted(
            (s for s in main_fp_set
             if commit_by_sha.get(s) and len(commit_by_sha[s].parents) >= 2),
            key=lambda s: commit_index.get(s, 10**9),
        )
    )
    _bfs_visited: set[str] = set()

    while _bfs_queue:
        mc_sha = _bfs_queue.popleft()
        if mc_sha in _bfs_visited:
            continue
        _bfs_visited.add(mc_sha)

        mc = commit_by_sha.get(mc_sha)
        if not mc or len(mc.parents) < 2:
            continue
        p2 = mc.parents[1]   # the PR head commit
        if p2 not in commit_sha_set:
            continue

        # If p2 is itself a merge commit outside main's chain, queue it too
        p2c = commit_by_sha.get(p2)
        if p2c and len(p2c.parents) >= 2 and p2 not in main_fp_set:
            _bfs_queue.append(p2)

        # Determine which branch this PR came from.
        # Priority: message parsing first (GitHub PR messages are authoritative),
        # then branch_tip_map name, then existing chain owner.
        attr: Optional[str] = None

        # 1. Parse "Merge pull request #N from Org/branch-name"
        _m = _MERGE_FROM.search(mc.message or '')
        if _m:
            _cand = _m.group(1)
            if _cand not in ('main', 'master', primary or ''):
                attr = _cand

        # 2. Fall back to branch_tip_map name
        if not attr and p2 in branch_tip_map:
            _names = branch_tip_map[p2]
            attr = next(
                (n for n in _names if n not in ('main', 'master', primary or '')),
                _names[0] if _names else None,
            )

        # 3. Fall back to existing chain owner
        if not attr:
            _o = commit_owner.get(p2, '')
            if _o not in ('main', 'master', primary or '', ''):
                attr = _o

        if not attr or _branch_base(attr) in ('main', 'master',
                                               _branch_base(primary or '')):
            continue

        # Walk the PR chain backward, stop when hitting main's chain
        sha = p2
        while sha in commit_sha_set and sha not in main_fp_set:
            if sha not in commit_owner:   # first write wins
                commit_owner[sha] = attr
            c2 = commit_by_sha.get(sha)
            if not c2 or not c2.parents:
                break
            sha = c2.parents[0]
    # ──────────────────────────────────────────────────────────────────────

    for commit in commits:
        sha = commit.sha

        # Ownership-aware lane selection: when multiple lanes compete for this
        # commit, prefer the named branch lane whose first-parent chain owns it.
        waiting = [i for i, s in enumerate(lanes) if s == sha]
        if len(waiting) > 1 and sha in commit_owner:
            preferred_name = commit_owner[sha]
            lane_idx = next(
                (i for i in waiting
                 if _branch_base(lane_branch.get(i, "")) == _branch_base(preferred_name)),
                waiting[0],
            )
        else:
            lane_idx = waiting[0] if waiting else None

        if lane_idx is None:
            # Prefer unnamed free slots; don't reuse closed named-branch lanes as
            # catch-alls (orphan commits would inherit the wrong branch label).
            free = next((i for i, s in enumerate(lanes) if s is None and i not in lane_branch), None)
            if free is not None:
                lane_idx = free
            else:
                lane_idx = len(lanes)
                lanes.append(None)

        assignment[sha] = lane_idx

        if sha in branch_tip_map and lane_idx not in lane_branch:
            names = branch_tip_map[sha]
            preferred = next((n for n in names if n == primary), names[0])
            lane_branch[lane_idx] = preferred

        for i in range(len(lanes)):
            if i != lane_idx and lanes[i] == sha:
                lanes[i] = None

        parents = commit.parents
        if not parents:
            lanes[lane_idx] = None
        else:
            parent0 = parents[0]
            if parent0 in branch_tip_map and parent0 not in assignment:
                p_names = branch_tip_map[parent0]
                current_branch = lane_branch.get(lane_idx, "")
                if any(_branch_base(n) == _branch_base(current_branch) for n in p_names):
                    lanes[lane_idx] = parent0
                elif sha in branch_tip_map:
                    if any(s == parent0 for s in lanes):
                        lanes[lane_idx] = None
                    else:
                        lanes[lane_idx] = None
                        new_lane_idx = len(lanes)
                        lanes.append(parent0)
                        p_pref = next((n for n in p_names if n == primary), p_names[0])
                        lane_branch[new_lane_idx] = p_pref
                else:
                    lanes[lane_idx] = parent0
            else:
                # parent0 is a regular (non-tip) commit — this lane's chain takes
                # priority.  Close any competing lane that was opened by a merge
                # commit and is also waiting for parent0; otherwise those
                # merge-opened lanes steal branch-history commits from their
                # natural lane.
                for j in range(len(lanes)):
                    if j != lane_idx and lanes[j] == parent0 and not lane_branch.get(j):
                        lanes[j] = None
                lanes[lane_idx] = parent0
            for p in parents[1:]:
                if not any(s == p for s in lanes):
                    free = next((i for i, s in enumerate(lanes) if s is None and i not in lane_branch), None)
                    if free is not None:
                        new_lane_idx = free
                        lanes[free] = p
                    else:
                        new_lane_idx = len(lanes)
                        lanes.append(p)
                    if p in branch_tip_map and new_lane_idx not in lane_branch:
                        p_names = branch_tip_map[p]
                        p_pref = next((n for n in p_names if n == primary), p_names[0])
                        lane_branch[new_lane_idx] = p_pref

    # ── Consolidate historically-attributed commits into their branch lanes ──
    # The streaming ownership-aware selection only fires when multiple lanes
    # compete.  Historical PR commits end up in their own pre-seeded lanes or
    # in unnamed lanes — trav's lane never competes for them because it stops
    # at the main merge point.  This post-pass explicitly moves any commit
    # that commit_owner says belongs to a named branch into that branch's lane.
    named_lanes: dict[str, int] = {}   # branch_base → lane_idx
    for _l, _n in lane_branch.items():
        _b = _branch_base(_n)
        if _b and _b not in named_lanes:
            named_lanes[_b] = _l

    for _sha, _lane in list(assignment.items()):
        _owned = commit_owner.get(_sha, '')
        if not _owned or _owned in ('main', 'master', primary or ''):
            continue
        _owned_base = _branch_base(_owned)
        _cur_base   = _branch_base(lane_branch.get(_lane, ''))
        if _cur_base != _owned_base and _owned_base in named_lanes:
            assignment[_sha] = named_lanes[_owned_base]

    # ── Build lane_branch fallback names ─────────────────────────────────
    for sha, lane_idx in assignment.items():
        if lane_idx not in lane_branch:
            names = branch_tip_map.get(sha, [])
            lane_branch[lane_idx] = names[0] if names else ""

    lane_branch.setdefault(0, primary or "main")

    # ── Re-order lanes by depth so nested branches sit further from main ──
    lane_depth: dict[int, int] = {0: 0}
    for commit in reversed(commits):
        lane = assignment.get(commit.sha, 0)
        if lane == 0 or not commit.parents or lane in lane_depth:
            continue
        parent_lane = assignment.get(commit.parents[0], 0)
        if parent_lane != lane:
            lane_depth[lane] = lane_depth.get(parent_lane, 0) + 1

    # ── Normalize depths for same-named sibling lanes ─────────────────────
    # Diverged local/remote tips of the same branch share the same
    # _branch_base name (e.g. "main" and "origin/main" both → "main").
    # Without this, the remote tip gets depth = local_depth + 1 because its
    # parent commit sits on the local branch's lane, pushing it far away
    # visually.  Force all same-named lanes to the group's minimum depth.
    _name_min_depth: dict[str, int] = {}
    for _l, _d in lane_depth.items():
        _b = _branch_base(lane_branch.get(_l, ''))
        if _b:
            _name_min_depth[_b] = min(_name_min_depth.get(_b, _d), _d)
    for _l in list(lane_depth):
        _b = _branch_base(lane_branch.get(_l, ''))
        if _b and _b in _name_min_depth:
            lane_depth[_l] = _name_min_depth[_b]

    _local_lanes = {assignment.get(s) for s in (local_tip_shas or set()) if s in assignment}
    non_main = sorted(
        {l for l in assignment.values() if l != 0},
        key=lambda l: (lane_depth.get(l, 0), 1 if l in _local_lanes else 0, l),
    )
    lane_remap: dict[int, int] = {0: 0}
    for new_idx, old_idx in enumerate(non_main, start=1):
        lane_remap[old_idx] = new_idx

    if any(k != v for k, v in lane_remap.items()):
        assignment  = {sha: lane_remap.get(l, l) for sha, l in assignment.items()}
        # Only keep lane_branch entries for lanes that were actually used by some
        # commit (i.e. present in lane_remap). A lane opened for a merge commit's
        # 2nd parent that itself falls outside the truncated commit window (rare,
        # large-history case) never appears in `assignment`, so its raw index
        # isn't remapped and could otherwise collide with another lane's new
        # (remapped) index, overwriting that lane's correct branch name.
        lane_branch = {lane_remap[l]: name for l, name in lane_branch.items()
                       if l in lane_remap}

    return assignment, lane_branch

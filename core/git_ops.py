from __future__ import annotations

import os
import subprocess
from urllib.parse import urlparse

import requests


def has_uncommitted_changes(path: str) -> bool:
    r = subprocess.run(
        ["git", "status", "--porcelain"],
        cwd=path, capture_output=True, text=True,
    )
    return bool(r.stdout.strip())


def get_stash_files(path: str, stash_id: str = "") -> list[str]:
    ref = ""
    if stash_id:
        r = subprocess.run(
            ["git", "stash", "list"],
            cwd=path, capture_output=True, text=True,
        )
        for line in r.stdout.strip().splitlines():
            if stash_id in line:
                ref = line.split(":")[0].strip()
                break
    args = ["git", "stash", "show", "--name-only"]
    if ref:
        args.append(ref)
    r = subprocess.run(args, cwd=path, capture_output=True, text=True)
    if r.returncode != 0:
        return []
    return [f.strip() for f in r.stdout.strip().splitlines() if f.strip()]


def create_auto_stash(path: str) -> tuple[list[str], str]:
    """Stash uncommitted changes. Returns (stashed_files, stash_id) or ([], '') on failure."""
    import uuid
    stash_id = "gitdummy-autostash-" + uuid.uuid4().hex[:8]

    # Try with untracked files first, fall back to tracked-only if that fails.
    for cmd in [
        ["git", "stash", "push", "--include-untracked", "-m", stash_id],
        ["git", "stash", "push", "-m", stash_id],
    ]:
        r = subprocess.run(cmd, cwd=path, capture_output=True, text=True)
        output = r.stdout + r.stderr
        if r.returncode == 0 and "No local changes" not in output:
            return get_stash_files(path), stash_id

    return [], ""


def pop_auto_stash(path: str, stash_id: str = "") -> bool:
    if stash_id:
        r = subprocess.run(
            ["git", "stash", "list"],
            cwd=path, capture_output=True, text=True,
        )
        for line in r.stdout.strip().splitlines():
            if stash_id in line:
                ref = line.split(":")[0].strip()
                r2 = subprocess.run(
                    ["git", "stash", "pop", ref],
                    cwd=path, capture_output=True, text=True,
                )
                return r2.returncode == 0
        return False
    r = subprocess.run(
        ["git", "stash", "pop"],
        cwd=path, capture_output=True, text=True,
    )
    return r.returncode == 0


def apply_stash(path: str, stash_ref: str) -> bool:
    """Apply a stash to the working directory without removing it from the stash list."""
    r = subprocess.run(
        ["git", "stash", "apply", stash_ref],
        cwd=path, capture_output=True, text=True,
    )
    return r.returncode == 0


def drop_stash(path: str, stash_ref: str) -> bool:
    """Remove a stash entry from the stash list without applying it."""
    r = subprocess.run(
        ["git", "stash", "drop", stash_ref],
        cwd=path, capture_output=True, text=True,
    )
    return r.returncode == 0


def reset_hard(path: str) -> bool:
    """Reset index and working tree to HEAD, aborting any partial stash apply."""
    r = subprocess.run(
        ["git", "reset", "--hard", "HEAD"],
        cwd=path, capture_output=True, text=True,
    )
    return r.returncode == 0


def checkout_commit(path: str, sha: str) -> tuple[bool, str]:
    r = subprocess.run(
        ["git", "checkout", sha],
        cwd=path, capture_output=True, text=True,
    )
    return r.returncode == 0, r.stderr.strip()


def checkout_branch(path: str, branch: str) -> tuple[bool, str]:
    r = subprocess.run(
        ["git", "checkout", branch],
        cwd=path, capture_output=True, text=True,
    )
    return r.returncode == 0, r.stderr.strip()


def current_branch(path: str) -> str:
    """Return the current branch name, or '' if in detached HEAD state."""
    r = subprocess.run(
        ["git", "rev-parse", "--abbrev-ref", "HEAD"],
        cwd=path, capture_output=True, text=True,
    )
    result = r.stdout.strip()
    return "" if result == "HEAD" else result


def branch_for_commit(path: str, sha: str) -> str:
    """Return a branch name that contains sha — used when in detached HEAD."""
    r = subprocess.run(
        ["git", "branch", "--contains", sha],
        cwd=path, capture_output=True, text=True,
    )
    for line in r.stdout.splitlines():
        name = line.strip().lstrip("* ").strip()
        if name and not name.startswith("("):
            return name
    return ""


def get_stash_ref_for_commit(path: str, commit_sha: str) -> str:
    """Return the stash ref (e.g. 'stash@{0}') whose parent is commit_sha, or ''."""
    r = subprocess.run(
        ["git", "stash", "list", "--format=%gd %P"],
        cwd=path, capture_output=True, text=True,
    )
    for line in r.stdout.strip().splitlines():
        parts = line.strip().split()
        if len(parts) >= 2 and parts[1] == commit_sha:
            return parts[0]
    return ""


def get_stash_diff_files(path: str, stash_ref: str) -> list[dict]:
    """Return per-file diff info for a stash, in the same format as commit_files."""
    r = subprocess.run(
        ["git", "show", "--format=", "--numstat", stash_ref],
        cwd=path, capture_output=True, text=True,
    )
    patch = subprocess.run(
        ["git", "stash", "show", "-p", stash_ref],
        cwd=path, capture_output=True, text=True,
    )

    # Build a map of file path → diff lines from the patch
    diff_by_path: dict[str, list] = {}
    current: list = []
    current_path = ""
    for line in patch.stdout.splitlines():
        if line.startswith("diff --git "):
            if current_path:
                diff_by_path[current_path] = current
            current = []
            current_path = ""
        elif line.startswith("+++ b/"):
            current_path = line[6:]
        elif line.startswith("--- a/") or line.startswith("+++ /dev/null"):
            pass
        elif current_path:
            if line.startswith("+") and not line.startswith("+++"):
                current.append(("added",   line[1:]))
            elif line.startswith("-") and not line.startswith("---"):
                current.append(("removed", line[1:]))
            elif line.startswith("@@"):
                current.append(("hunk",    line))
            elif line.startswith(" "):
                current.append(("context", line[1:]))
    if current_path:
        diff_by_path[current_path] = current

    result = []
    for line in r.stdout.strip().splitlines():
        if not line.strip():
            continue
        parts = line.split("\t")
        if len(parts) < 3:
            continue
        ins_s, dels_s, fpath = parts[0], parts[1], parts[2]
        is_binary = ins_s == "-"
        try:
            ins  = int(ins_s)  if not is_binary else 0
            dels = int(dels_s) if not is_binary else 0
        except ValueError:
            ins = dels = 0
        lines = diff_by_path.get(fpath, [])
        result.append({
            "path":       fpath,
            "name":       fpath.split("/")[-1],
            "status":     "modified",
            "insertions": ins,
            "deletions":  dels,
            "is_binary":  is_binary,
            "lines":      lines,
        })
    return result


def get_working_dir_diff_files(path: str) -> list[dict]:
    """Return per-file diff info for the current dirty working directory (staged + unstaged)."""
    import os as _os
    r = subprocess.run(
        ["git", "diff", "HEAD", "--numstat"],
        cwd=path, capture_output=True, text=True,
        encoding="utf-8", errors="replace",
    )
    patch = subprocess.run(
        ["git", "diff", "HEAD"],
        cwd=path, capture_output=True, text=True,
        encoding="utf-8", errors="replace",
    )

    diff_by_path: dict[str, list] = {}
    current: list = []
    current_path = ""
    for line in (patch.stdout or "").splitlines():
        if line.startswith("diff --git "):
            if current_path:
                diff_by_path[current_path] = current
            current = []
            current_path = ""
        elif line.startswith("+++ b/"):
            current_path = line[6:]
        elif line.startswith("--- a/") or line.startswith("+++ /dev/null"):
            pass
        elif current_path:
            if line.startswith("+") and not line.startswith("+++"):
                current.append(("added",   line[1:]))
            elif line.startswith("-") and not line.startswith("---"):
                current.append(("removed", line[1:]))
            elif line.startswith("@@"):
                current.append(("hunk",    line))
            elif line.startswith(" "):
                current.append(("context", line[1:]))
    if current_path:
        diff_by_path[current_path] = current

    result = []
    seen_paths: set[str] = set()

    for line in (r.stdout or "").strip().splitlines():
        if not line.strip():
            continue
        parts = line.split("\t")
        if len(parts) < 3:
            continue
        ins_s, dels_s, fpath = parts[0], parts[1], parts[2]
        is_binary = ins_s == "-"
        try:
            ins  = int(ins_s)  if not is_binary else 0
            dels = int(dels_s) if not is_binary else 0
        except ValueError:
            ins = dels = 0
        status = "deleted" if dels > 0 and ins == 0 else "modified"
        result.append({
            "path":       fpath,
            "name":       fpath.split("/")[-1],
            "status":     status,
            "insertions": ins,
            "deletions":  dels,
            "is_binary":  is_binary,
            "lines":      diff_by_path.get(fpath, []),
        })
        seen_paths.add(fpath)

    # Include untracked (new) files that git diff HEAD misses entirely
    untracked = subprocess.run(
        ["git", "ls-files", "--others", "--exclude-standard"],
        cwd=path, capture_output=True, text=True,
    )
    for fpath in untracked.stdout.strip().splitlines():
        fpath = fpath.strip()
        if not fpath or fpath in seen_paths:
            continue
        abs_path = _os.path.join(path, fpath.replace("/", _os.sep))
        lines: list = []
        ins = 0
        is_binary = False
        try:
            with open(abs_path, "r", encoding="utf-8", errors="replace") as f:
                for i, raw in enumerate(f):
                    if i >= 500:
                        break
                    lines.append(("added", raw.rstrip("\n")))
                    ins += 1
        except Exception:
            is_binary = True
        result.append({
            "path":       fpath,
            "name":       fpath.split("/")[-1],
            "status":     "added",
            "insertions": ins,
            "deletions":  0,
            "is_binary":  is_binary,
            "lines":      lines,
        })

    return result


def get_stash_commit_shas(path: str) -> set[str]:
    """Return the set of commit SHAs that have a stash sitting on top of them."""
    r = subprocess.run(
        ["git", "stash", "list", "--format=%P"],
        cwd=path, capture_output=True, text=True,
    )
    shas = set()
    for line in r.stdout.strip().splitlines():
        parts = line.strip().split()
        if parts:
            shas.add(parts[0])
    return shas


def get_stash_list_id(path: str) -> str:
    """Return a cheap fingerprint of the current stash list for change detection."""
    r = subprocess.run(
        ["git", "stash", "list", "--format=%H"],
        cwd=path, capture_output=True, text=True,
    )
    return r.stdout.strip()


def pull_ff(path: str, branch: str) -> tuple[bool, str]:
    """Fast-forward a local branch to its remote without needing to check it out."""
    return _run(path, ["git", "fetch", "origin", f"{branch}:{branch}"], timeout=30)


def get_conflict_content(repo_path: str, file_path: str) -> tuple:
    """Parse conflict markers, return (original_lines, orig_start, incoming_lines, inc_start).
    Line numbers correspond to their actual position in the file."""
    import os as _os
    abs_path = _os.path.join(repo_path, file_path.replace("/", _os.sep))
    try:
        with open(abs_path, "r", encoding="utf-8", errors="replace") as f:
            lines = f.readlines()
    except Exception:
        return [], 1, [], 1
    original, incoming = [], []
    orig_start = inc_start = 1
    state = "normal"
    for lineno, line in enumerate(lines, 1):
        s = line.rstrip("\n")
        if s.startswith("<<<<<<<"):
            state = "original"
            orig_start = lineno + 1
        elif s == "=======" and state == "original":
            state = "incoming"
            inc_start = lineno + 1
        elif s.startswith(">>>>>>>") and state == "incoming":
            break
        elif state == "original":
            original.append(s)
        elif state == "incoming":
            incoming.append(s)
    # Both sections represent the same file region — use orig_start for both
    return original, orig_start, incoming, orig_start


def get_conflict_files(path: str) -> list:
    """Return list of files with unresolved merge conflicts (call before git merge --abort)."""
    try:
        r = subprocess.run(
            ["git", "diff", "--name-only", "--diff-filter=U"],
            cwd=path, capture_output=True, text=True, timeout=10,
        )
        return [f for f in r.stdout.strip().splitlines() if f]
    except Exception:
        return []


def push_branch(path: str, branch: str) -> tuple[bool, str, list, dict]:
    r = subprocess.run(
        ["git", "push", "-u", "origin", branch],
        cwd=path, capture_output=True, text=True, timeout=60,
    )
    if r.returncode == 0:
        return True, "", [], {}

    # git puts [rejected] / non-fast-forward in stdout; errors in stderr
    combined = (r.stdout + r.stderr).lower()

    if "non-fast-forward" in combined or "rejected" in combined:
        ok2, err2 = _run(path, ["git", "fetch", "origin"], timeout=30)
        if not ok2:
            return False, err2, [], {}

        r3 = subprocess.run(
            ["git", "merge", f"origin/{branch}"],
            cwd=path, capture_output=True, text=True, timeout=30,
        )
        if r3.returncode != 0:
            combined3 = (r3.stdout + r3.stderr).lower()
            conflict_files = get_conflict_files(path)
            content = {f: get_conflict_content(path, f) for f in conflict_files}
            subprocess.run(["git", "merge", "--abort"],
                           cwd=path, capture_output=True, text=True, timeout=10)
            if "conflict" in combined3:
                return False, "merge_conflict", conflict_files, content
            return False, r3.stderr.strip() or r3.stdout.strip(), [], {}

        ok4, err4 = _run(path, ["git", "push", "-u", "origin", branch], timeout=60)
        return ok4, err4, [], {}

    return False, r.stderr.strip() or r.stdout.strip(), [], {}


def save_stash_as_commit(path: str, stash_ref: str = "", message: str = "",
                         branch: str = "") -> tuple[bool, str, list, dict]:
    """Commit saved changes at the tip of branch.

    Two paths depending on whether the target branch already exists locally:

    A) Remote-only branch (no local ref):
       Detached HEAD is at the same commit as origin/branch, so checking out
       -b preserves the working tree.  Checkout FIRST, then commit directly —
       produces one clean commit with no spurious intermediate D + merge M.

    B) Local branch exists (possibly at a different tip):
       Commit in detached HEAD → D, checkout branch, merge --no-ff D.
       On conflict: abort, restore original position.
    """
    original_sha = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=path, capture_output=True, text=True, timeout=5,
    ).stdout.strip()

    # 1. Apply stash so working tree has the changes.
    if stash_ref:
        r = subprocess.run(
            ["git", "stash", "apply", stash_ref],
            cwd=path, capture_output=True, text=True, timeout=30,
        )
        if r.returncode != 0:
            return False, (r.stderr.strip() or r.stdout.strip() or
                           "Could not apply saved changes."), [], {}

    # Determine whether we need to switch branches.
    cur = subprocess.run(
        ["git", "rev-parse", "--abbrev-ref", "HEAD"],
        cwd=path, capture_output=True, text=True, timeout=5,
    ).stdout.strip()
    need_switch = bool(branch) and cur != branch

    if need_switch:
        local_exists = subprocess.run(
            ["git", "rev-parse", "--verify", f"refs/heads/{branch}"],
            cwd=path, capture_output=True, text=True, timeout=5,
        ).returncode == 0

        if not local_exists:
            # ── Path A: remote-only branch ────────────────────────────────
            # Detached HEAD is at origin/branch tip (same commit) so -b
            # checkout doesn't change any files — working tree is preserved.
            ok_co, err_co = _run(
                path, ["git", "checkout", "-b", branch, f"origin/{branch}"]
            )
            if not ok_co:
                return False, f"Could not create local branch '{branch}': {err_co}", [], {}
            # Fall through to the shared stage-and-commit block below.

        else:
            # ── Path B: local branch exists at a (possibly different) tip ─
            # Commit here first (tree clean after), then merge onto branch tip.
            subprocess.run(["git", "add", "-A"], cwd=path, capture_output=True, timeout=10)
            status = subprocess.run(
                ["git", "status", "--porcelain"],
                cwd=path, capture_output=True, text=True, timeout=10,
            ).stdout.strip()
            if not status:
                return False, "Nothing new to commit — changes already in branch.", [], {}

            ok, err = _run(path, ["git", "commit", "-m", message or "saved changes"])
            if not ok:
                subprocess.run(["git", "reset", "HEAD"], cwd=path,
                               capture_output=True, timeout=10)
                return False, err, [], {}

            saved_sha = subprocess.run(
                ["git", "rev-parse", "HEAD"],
                cwd=path, capture_output=True, text=True, timeout=5,
            ).stdout.strip()

            ok_co, err_co = _run(path, ["git", "checkout", branch])
            if not ok_co:
                subprocess.run(["git", "checkout", original_sha],
                               cwd=path, capture_output=True, timeout=10)
                subprocess.run(["git", "cherry-pick", "--no-commit", saved_sha],
                               cwd=path, capture_output=True, timeout=30)
                return False, f"Could not switch to '{branch}': {err_co}", [], {}

            ok_m, err_m = _run(path, ["git", "merge", "--no-ff", saved_sha,
                                       "-m", message or "saved changes"])
            if not ok_m:
                conflict_files   = get_conflict_files(path)
                conflict_content = {f: get_conflict_content(path, f) for f in conflict_files}
                subprocess.run(["git", "merge", "--abort"],
                               cwd=path, capture_output=True, timeout=10)
                subprocess.run(["git", "checkout", original_sha],
                               cwd=path, capture_output=True, timeout=10)
                subprocess.run(["git", "cherry-pick", "--no-commit", saved_sha],
                               cwd=path, capture_output=True, timeout=30)
                return False, "save_conflict", conflict_files, conflict_content

            if stash_ref:
                subprocess.run(["git", "stash", "drop", stash_ref],
                               cwd=path, capture_output=True, text=True, timeout=10)
            return True, "", [], {}

    # ── Shared: stage + commit directly on the current (or freshly-checked-out) branch ──
    subprocess.run(["git", "add", "-A"], cwd=path, capture_output=True, timeout=10)
    status = subprocess.run(
        ["git", "status", "--porcelain"],
        cwd=path, capture_output=True, text=True, timeout=10,
    ).stdout.strip()
    if not status:
        return False, "Nothing new to commit — changes already in branch.", [], {}

    ok, err = _run(path, ["git", "commit", "-m", message or "saved changes"])
    if not ok:
        subprocess.run(["git", "reset", "HEAD"], cwd=path,
                       capture_output=True, timeout=10)
        return False, err, [], {}

    if stash_ref:
        subprocess.run(["git", "stash", "drop", stash_ref],
                       cwd=path, capture_output=True, text=True, timeout=10)
    return True, "", [], {}


def pull_stash_apply(path: str, branch: str) -> tuple[bool, str]:
    """Stash changes, fast-forward to remote, re-apply stash."""
    ok, err = _run(path, ["git", "stash"])
    if not ok:
        return False, err
    ok, err = _run(path, ["git", "fetch", "origin"])
    if not ok:
        # Restore stash before returning — user's changes must not be lost.
        subprocess.run(["git", "stash", "pop"], cwd=path, capture_output=True, timeout=30)
        return False, err
    ok, err = _run(path, ["git", "reset", "--hard", f"origin/{branch}"])
    if not ok:
        subprocess.run(["git", "stash", "pop"], cwd=path, capture_output=True, timeout=30)
        return False, err
    r = subprocess.run(["git", "stash", "pop"],
                       cwd=path, capture_output=True, text=True, timeout=30)
    if r.returncode != 0:
        # Pop conflicted — reset working tree cleanly; stash entry is preserved.
        subprocess.run(["git", "reset", "--hard", "HEAD"],
                       cwd=path, capture_output=True, text=True, timeout=10)
        return False, "stash_conflict"
    return True, ""


def pull_save_merge(path: str, branch: str) -> tuple[bool, str, list]:
    """Commit unsaved changes then merge remote into local."""
    for cmd in (["git", "add", "-A"],
                ["git", "commit", "-m", "saved changes before pull"],
                ["git", "fetch", "origin"]):
        ok, err = _run(path, cmd)
        if not ok:
            return False, err, []
    ok3, err3 = _run(path, ["git", "merge", f"origin/{branch}"])
    if not ok3:
        conflict_files = get_conflict_files(path)
        subprocess.run(["git", "merge", "--abort"],
                       cwd=path, capture_output=True, text=True, timeout=10)
        if "conflict" in err3.lower() or "CONFLICT" in err3:
            return False, "merge_conflict", conflict_files
        return False, err3, []
    return True, "", []


def pull_discard(path: str, branch: str) -> tuple[bool, str]:
    """Discard all local changes and fast-forward to remote."""
    for cmd in (["git", "reset", "--hard", "HEAD"],
                ["git", "clean", "-fd"],
                ["git", "fetch", "origin"],
                ["git", "reset", "--hard", f"origin/{branch}"]):
        ok, err = _run(path, cmd)
        if not ok:
            return False, err
    return True, ""


def merge_branch(path: str, source_branch: str) -> tuple[bool, str, list, dict]:
    """Merge source_branch into the currently checked-out branch.
    On conflict: reads content while markers are present, aborts, returns content for dialog."""
    r = subprocess.run(
        ["git", "merge", "--no-ff", source_branch],
        cwd=path, capture_output=True, text=True, timeout=60,
    )
    if r.returncode == 0:
        combined = (r.stdout + r.stderr).lower()
        if "already up to date" in combined:
            return True, "already_up_to_date", [], {}
        return True, "", [], {}
    err = r.stderr.strip() or r.stdout.strip()
    if "conflict" in err.lower() or "CONFLICT" in err:
        files = get_conflict_files(path)
        # Capture content NOW — markers still present in files
        content = {f: get_conflict_content(path, f) for f in files}
        # Abort so VSCode files go back to clean state
        subprocess.run(["git", "merge", "--abort"],
                       cwd=path, capture_output=True, text=True, timeout=10)
        return False, "merge_conflict", files, content
    subprocess.run(["git", "merge", "--abort"],
                   cwd=path, capture_output=True, text=True, timeout=10)
    return False, err, [], {}


def merge_with_decisions(path: str, source_branch: str, decisions: dict) -> tuple[bool, str]:
    """Re-merge then apply per-file ours/theirs decisions, then commit."""
    _run(path, ["git", "merge", "--no-ff", "--no-commit", source_branch], timeout=60)
    # Apply per-file decisions regardless of whether merge itself had conflicts.
    all_ok = True
    for filepath, choice in decisions.items():
        flag = "--ours" if choice == "ours" else "--theirs"
        ok_f, _ = _run(path, ["git", "checkout", flag, filepath])
        if ok_f:
            _run(path, ["git", "add", filepath])
        else:
            all_ok = False
    if not all_ok:
        subprocess.run(["git", "merge", "--abort"],
                       cwd=path, capture_output=True, text=True, timeout=10)
        return False, "Could not apply all file decisions — merge aborted."
    ok2, err2 = _run(path, ["git", "commit", "--no-edit"], timeout=30)
    if not ok2:
        subprocess.run(["git", "merge", "--abort"],
                       cwd=path, capture_output=True, text=True, timeout=10)
    return ok2, err2


def merge_use_theirs(path: str, source_branch: str) -> tuple[bool, str]:
    """Re-merge using theirs (-X theirs) strategy — no conflict markers in files."""
    ok, err = _run(path, ["git", "merge", "--no-ff", "-X", "theirs", source_branch], timeout=60)
    return ok, err


def merge_use_ours(path: str, source_branch: str) -> tuple[bool, str]:
    """Re-merge using ours (-X ours) strategy — no conflict markers in files."""
    ok, err = _run(path, ["git", "merge", "--no-ff", "-X", "ours", source_branch], timeout=60)
    return ok, err


def merge_abort(path: str) -> tuple[bool, str]:
    return _run(path, ["git", "merge", "--abort"])


def conflict_discard_local(path: str, branch: str) -> tuple[bool, str]:
    """Discard local commits, reset to remote, force-push."""
    for cmd in (["git", "fetch", "origin"],
                ["git", "reset", "--hard", f"origin/{branch}"]):
        ok, err = _run(path, cmd)
        if not ok:
            return False, err
    return _run(path, ["git", "push", "--force", "origin", branch], timeout=60)


def conflict_keep_local(path: str, branch: str) -> tuple[bool, str]:
    """Re-apply local file changes on top of remote as a single new commit, then push."""
    try:
        diff_r = subprocess.run(
            ["git", "diff", f"origin/{branch}...HEAD"],
            cwd=path, capture_output=True, text=True, timeout=30,
        )
        patch = diff_r.stdout
    except Exception as e:
        return False, str(e)

    for cmd in (["git", "fetch", "origin"],
                ["git", "reset", "--hard", f"origin/{branch}"]):
        ok, err = _run(path, cmd)
        if not ok:
            return False, err

    if patch.strip():
        try:
            r = subprocess.run(
                ["git", "apply", "--whitespace=fix"],
                input=patch, cwd=path, capture_output=True, text=True, timeout=30,
            )
            if r.returncode != 0:
                return False, r.stderr.strip() or r.stdout.strip()
        except Exception as e:
            return False, str(e)
        for cmd in (["git", "add", "-A"],
                    ["git", "commit", "-m", "local changes on top of remote"]):
            ok, err = _run(path, cmd)
            if not ok:
                return False, err

    return _run(path, ["git", "push", "-u", "origin", branch], timeout=60)


def discard_all_changes(path: str) -> tuple[bool, str]:
    for cmd in (["git", "reset", "--hard", "HEAD"], ["git", "clean", "-fd"]):
        ok, err = _run(path, cmd)
        if not ok:
            return False, err
    return True, ""


def _run(path: str, cmd: list, timeout: int = 30) -> tuple[bool, str]:
    """Run a git command with a timeout. Returns (ok, error_message)."""
    try:
        r = subprocess.run(cmd, cwd=path, capture_output=True, text=True, timeout=timeout)
        if r.returncode != 0:
            return False, r.stderr.strip() or r.stdout.strip()
        return True, ""
    except subprocess.TimeoutExpired:
        return False, "timed_out"


def hard_revert_to(path: str, branch: str, target_sha: str) -> tuple[bool, str]:
    try:
        cur = subprocess.run(["git", "rev-parse", "--abbrev-ref", "HEAD"],
                             cwd=path, capture_output=True, text=True, timeout=5)
        current = cur.stdout.strip()
        if current == "HEAD":
            current = ""
    except Exception:
        current = ""
    if current != branch:
        ok, err = _run(path, ["git", "checkout", branch])
        if not ok:
            return False, err
    ok, err = _run(path, ["git", "reset", "--hard", target_sha])
    if not ok:
        return False, err
    # Only push if the branch actually exists on origin — skip for local-only repos.
    ls = subprocess.run(
        ["git", "ls-remote", "--heads", "origin", branch],
        cwd=path, capture_output=True, text=True, timeout=10,
    )
    if ls.returncode == 0 and ls.stdout.strip():
        r = subprocess.run(
            ["git", "push", "--force", "origin", branch],
            cwd=path, capture_output=True, text=True, timeout=30,
        )
        if r.returncode != 0:
            remote_err = r.stderr.strip() or r.stdout.strip()
            return False, f"Local branch reverted, but remote push failed: {remote_err}"
    return True, ""


def soft_revert_to(path: str, branch: str, tip_sha: str, parent_sha: str = "") -> tuple[bool, str]:
    target = parent_sha if parent_sha else f"{tip_sha}^"
    short  = parent_sha[:7] if parent_sha else "prev"
    msg    = f"reverted to {short}"

    try:
        cur = subprocess.run(["git", "rev-parse", "--abbrev-ref", "HEAD"],
                             cwd=path, capture_output=True, text=True, timeout=5)
        current = cur.stdout.strip()
        if current == "HEAD":
            current = ""
    except Exception:
        current = ""
    if current != branch:
        ok, err = _run(path, ["git", "checkout", branch])
        if not ok:
            return False, err

    # Restore files from target commit into working tree.
    ok, err = _run(path, ["git", "checkout", target, "--", "."])
    if not ok:
        # Unstage anything that landed before failing.
        subprocess.run(["git", "reset", "HEAD"], cwd=path, capture_output=True, timeout=10)
        return False, err

    ok, err = _run(path, ["git", "add", "-A"])
    if not ok:
        subprocess.run(["git", "reset", "HEAD"], cwd=path, capture_output=True, timeout=10)
        return False, err

    ok, err = _run(path, ["git", "commit", "-m", msg])
    if not ok:
        # Uncommit the staged changes so the working tree is not left dirty-staged.
        subprocess.run(["git", "reset", "HEAD"], cwd=path, capture_output=True, timeout=10)
        return False, err
    return True, ""


def branch_unique_commits(path: str, source: str, target: str) -> list[str]:
    """Return commit messages on source that are not reachable from target."""
    try:
        r = subprocess.run(
            ["git", "log", "--format=%s", f"{target}..{source}"],
            cwd=path, capture_output=True, text=True, timeout=10,
        )
        return [m.strip() for m in r.stdout.strip().splitlines() if m.strip()]
    except Exception:
        return []


def delete_branch_full(path: str, branch: str, fallback_sha: str = "") -> tuple[bool, str]:
    cur = subprocess.run(
        ["git", "rev-parse", "--abbrev-ref", "HEAD"],
        cwd=path, capture_output=True, text=True, timeout=10,
    )
    on_branch = cur.stdout.strip() == branch

    if on_branch:
        target = fallback_sha or "HEAD~1"
        checkout_target = None

        # Try to find another local branch that contains the parent commit
        try:
            r = subprocess.run(
                ["git", "branch", "--contains", target],
                cwd=path, capture_output=True, text=True, timeout=5,
            )
            for line in r.stdout.strip().splitlines():
                name = line.strip().lstrip("* ")
                # Skip the branch being deleted and any detached HEAD entries
                if name and name != branch and not name.startswith("("):
                    checkout_target = name
                    break
        except Exception:
            pass

        # Fall back to main / master if --contains found nothing usable
        if not checkout_target:
            for candidate in ("main", "master"):
                if candidate == branch:
                    continue
                r = subprocess.run(
                    ["git", "rev-parse", "--verify", candidate],
                    cwd=path, capture_output=True, text=True, timeout=5,
                )
                if r.returncode == 0:
                    checkout_target = candidate
                    break

        # Last resort: detached checkout to the parent SHA
        if not checkout_target:
            checkout_target = target

        ok, err = _run(path, ["git", "checkout", checkout_target])
        if not ok:
            return False, err

    ok, err = _run(path, ["git", "branch", "-D", branch])
    if not ok:
        return False, err

    # Only attempt remote delete when the branch actually exists on origin
    ls = subprocess.run(
        ["git", "ls-remote", "--heads", "origin", branch],
        cwd=path, capture_output=True, text=True, timeout=10,
    )
    if ls.returncode == 0 and ls.stdout.strip():
        r = subprocess.run(
            ["git", "push", "origin", "--delete", branch],
            cwd=path, capture_output=True, text=True, timeout=30,
        )
        if r.returncode != 0:
            stderr = r.stderr.strip()
            if "refusing to delete the current branch" in stderr:
                return False, (
                    f"Local branch deleted, but '{branch}' is the default branch on GitHub — "
                    "change the default branch in GitHub → Settings → Branches, then delete."
                )
            return False, f"Local branch deleted, but remote delete failed: {stderr}"

    return True, ""


def create_branch_with_commit(path: str, branch_name: str, from_sha: str) -> tuple[bool, str]:
    ok, err = _run(path, ["git", "checkout", "-b", branch_name, from_sha])
    if not ok:
        return False, err
    ok2, err2 = _run(path, ["git", "commit", "--allow-empty", "-m", f"created branch {branch_name}"])
    if not ok2:
        # Branch was created but commit failed — delete the branch and go back.
        subprocess.run(["git", "checkout", from_sha],
                       cwd=path, capture_output=True, text=True, timeout=10)
        subprocess.run(["git", "branch", "-D", branch_name],
                       cwd=path, capture_output=True, text=True, timeout=10)
        return False, err2
    return True, ""


def init_repo(path: str, user_name: str = "", user_email: str = "") -> tuple[bool, str]:
    try:
        r = subprocess.run(["git", "init", "-b", "main"], cwd=path, capture_output=True, text=True)
        if r.returncode != 0:
            return False, r.stderr.strip()

        # Set identity from the logged-in user; fall back only if nothing provided
        subprocess.run(["git", "config", "user.name",  user_name  or "User"],               cwd=path)
        subprocess.run(["git", "config", "user.email", user_email or "user@gitdummy.local"], cwd=path)

        subprocess.run(["git", "add", "."], cwd=path, capture_output=True)
        c = subprocess.run(
            ["git", "commit", "--allow-empty", "-m", "Initial commit"],
            cwd=path, capture_output=True, text=True,
        )
        return c.returncode == 0, c.stderr.strip()
    except Exception as e:
        return False, str(e)


def clone_repo(url: str, dest_parent: str) -> tuple[bool, str, str]:
    """Clone url into dest_parent/<repo-name>. Returns (ok, error, cloned_path)."""
    try:
        name = url.rstrip("/").rstrip(".git").split("/")[-1]
        dest = os.path.join(dest_parent, name)
        r = subprocess.run(
            ["git", "clone", url, dest],
            capture_output=True, text=True, timeout=120,
        )
        if r.returncode != 0:
            return False, r.stderr.strip(), ""
        return True, "", dest
    except Exception as e:
        return False, str(e), ""


def create_github_repo(name: str, private: bool, token: str) -> tuple[bool, str, str]:
    """Returns (success, error, clone_url)."""
    try:
        resp = requests.post(
            "https://api.github.com/user/repos",
            json={"name": name, "private": private, "auto_init": False},
            headers={
                "Authorization": f"Bearer {token}",
                "Accept": "application/vnd.github+json",
            },
            timeout=15,
        )
        body = resp.json()
        if resp.status_code == 201:
            return True, "", body["clone_url"]
        return False, body.get("message", f"HTTP {resp.status_code}"), ""
    except Exception as e:
        return False, str(e), ""


def push_to_github(
    path: str,
    clone_url: str,
    username: str,
    token: str,
    user_name: str = "",
    user_email: str = "",
) -> tuple[bool, str]:
    """
    Stages everything, makes an initial commit if needed, adds remote, pushes.
    Returns (success, error).
    """
    try:
        def run(*args, **kw):
            r = subprocess.run(
                list(args), cwd=path,
                capture_output=True, text=True, **kw,
            )
            if r.returncode != 0:
                raise RuntimeError(r.stderr.strip() or r.stdout.strip())
            return r

        subprocess.run(["git", "config", "user.name",  user_name  or username or "User"],       cwd=path)
        subprocess.run(["git", "config", "user.email", user_email or "user@gitdummy.local"],   cwd=path)

        # Stage and commit if no commits yet
        log = subprocess.run(
            ["git", "log", "--oneline", "-1"],
            cwd=path, capture_output=True,
        )
        if log.returncode != 0 or not log.stdout.strip():
            run("git", "add", ".")
            run("git", "commit", "--allow-empty", "-m", "Initial commit")

        # Embed token into HTTPS URL so Git doesn't prompt
        parsed = urlparse(clone_url)
        auth_url = f"https://{username}:{token}@{parsed.netloc}{parsed.path}"

        # Add remote (remove existing one silently first)
        subprocess.run(["git", "remote", "remove", "origin"], cwd=path, capture_output=True)
        run("git", "remote", "add", "origin", auth_url)
        run("git", "push", "-u", "origin", "HEAD")

        return True, ""
    except RuntimeError as e:
        return False, str(e)
    except Exception as e:
        return False, str(e)

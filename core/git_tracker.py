from __future__ import annotations

import os
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

import git  # gitpython


@dataclass
class CommitInfo:
    sha: str
    short_sha: str
    message: str
    author: str
    author_email: str
    date: datetime
    branch: str
    tags: list[str] = field(default_factory=list)
    parents: list[str] = field(default_factory=list)

    @property
    def date_str(self) -> str:
        return self.date.strftime("%Y-%m-%d %H:%M")

    @property
    def relative_date(self) -> str:
        delta = datetime.now() - self.date.replace(tzinfo=None)
        s = delta.total_seconds()
        if s < 60:
            return "just now"
        if s < 3600:
            return f"{int(s // 60)}m ago"
        if s < 86400:
            return f"{int(s // 3600)}h ago"
        if s < 86400 * 7:
            return f"{int(s // 86400)}d ago"
        if s < 86400 * 30:
            return f"{int(s // (86400 * 7))}w ago"
        if s < 86400 * 365:
            return f"{int(s // (86400 * 30))}mo ago"
        return f"{int(s // (86400 * 365))}y ago"


class GitTracker:
    """
    Thin wrapper around gitpython that reads commit history from a local repo.

    All methods are synchronous — call from a worker thread if needed to keep
    the UI responsive on large histories.
    """

    def __init__(self, repo_path: str):
        self._path = repo_path
        self._repo: Optional[git.Repo] = None

    def open(self):
        self._repo = git.Repo(self._path)

    def close(self):
        if self._repo:
            self._repo.close()
            self._repo = None

    @property
    def repo_name(self) -> str:
        return os.path.basename(self._path)

    @property
    def active_branch(self) -> str:
        try:
            return self._repo.active_branch.name
        except TypeError:
            return "No branch"

    def branches(self) -> list[str]:
        return [b.name for b in self._repo.branches]

    def commits(self, branch: str = "HEAD", max_count: int = 500) -> list[CommitInfo]:
        """Return up to max_count commits from the given branch/ref."""
        if not self._repo:
            return []

        # Build tag map: sha -> [tag names]
        tag_map: dict[str, list[str]] = {}
        for tag in self._repo.tags:
            sha = tag.commit.hexsha
            tag_map.setdefault(sha, []).append(tag.name)

        results: list[CommitInfo] = []
        try:
            for c in self._repo.iter_commits(branch, max_count=max_count):
                dt = datetime.fromtimestamp(c.committed_date)
                results.append(
                    CommitInfo(
                        sha=c.hexsha,
                        short_sha=c.hexsha[:7],
                        message=c.message.strip().splitlines()[0],
                        author=c.author.name or "",
                        author_email=c.author.email or "",
                        date=dt,
                        branch=branch,
                        tags=tag_map.get(c.hexsha, []),
                        parents=[p.hexsha for p in c.parents],
                    )
                )
        except git.GitCommandError:
            pass

        return results

    def graph_commits(self, max_count: int = 600) -> tuple[list["CommitInfo"], dict[str, list[str]]]:
        """
        Returns (commits, branch_tip_map) for the spatial canvas.

        Remote (origin) is always the source of truth.  Falls back to local
        branches only if the repo has no remotes configured.

        Uses git's --topo-order across ALL refs at once so commits arrive in
        true topological order (children before parents), which the streaming
        lane algorithm in spatial_canvas.py requires.
        """
        if not self._repo:
            return [], {}

        tag_map: dict[str, list[str]] = {}
        for tag in self._repo.tags:
            tag_map.setdefault(tag.commit.hexsha, []).append(tag.name)

        # ── Collect refs (iter_name, display_name, tip_sha) ──────────────
        ref_list: list[tuple[str, str, str]] = []

        remotes_map = {r.name: r for r in self._repo.remotes}
        chosen = remotes_map.get("origin") or next(iter(remotes_map.values()), None)
        if chosen:
            for ref in chosen.refs:
                if ref.remote_head == "HEAD":
                    continue
                try:
                    ref_list.append((ref.name, ref.remote_head, ref.commit.hexsha))
                except Exception:
                    pass

        local_only: set[str] = set()

        # Fall back to local branches if no remote exists
        if not ref_list:
            for b in self._repo.branches:
                try:
                    ref_list.append((b.name, b.name, b.commit.hexsha))
                except Exception:
                    pass
        else:
            # Also include local branches whose tip isn't on any remote ref
            remote_tip_shas = {sha for _, _, sha in ref_list}
            for b in self._repo.branches:
                try:
                    if b.commit.hexsha not in remote_tip_shas:
                        ref_list.append((b.name, b.name, b.commit.hexsha))
                        local_only.add(b.name)
                except Exception:
                    pass

        if not ref_list:
            return [], {}, set()

        # ── branch_tip_map ────────────────────────────────────────────────
        branch_tip_map: dict[str, list[str]] = {}
        for _, display_name, tip_sha in ref_list:
            branch_tip_map.setdefault(tip_sha, []).append(display_name)

        # ── Single topological traversal across all refs ──────────────────
        # Passing a list of ref names to iter_commits issues:
        #   git rev-list ref1 ref2 ... --topo-order
        # giving TRUE topological order (children always before parents).
        iter_refs = [r[0] for r in ref_list]
        try:
            raw = list(self._repo.iter_commits(iter_refs, topo_order=True, max_count=max_count))
        except Exception:
            raw = []

        commits: list[CommitInfo] = []
        for c in raw:
            commits.append(CommitInfo(
                sha=c.hexsha,
                short_sha=c.hexsha[:7],
                message=c.message.strip().splitlines()[0],
                author=c.author.name or "",
                author_email=c.author.email or "",
                date=datetime.fromtimestamp(c.committed_date),
                branch="",          # set later by the lane algorithm
                tags=tag_map.get(c.hexsha, []),
                parents=[p.hexsha for p in c.parents],
            ))

        return commits, branch_tip_map, local_only

    def get_unpushed_shas(self) -> set[str]:
        """Return commit SHAs reachable from local branches but not from any remote ref."""
        if not self._repo or not self.has_remote():
            return set()
        import subprocess
        try:
            r = subprocess.run(
                ["git", "rev-list", "--branches", "--not", "--remotes"],
                cwd=self._path,
                capture_output=True, text=True,
            )
            if r.returncode == 0:
                return {s for s in r.stdout.strip().splitlines() if s}
        except Exception:
            pass
        return set()

    def has_remote(self) -> bool:
        return bool(self._repo and self._repo.remotes)

    def graph_commits_local(self, max_count: int = 600) -> tuple[list["CommitInfo"], dict[str, list[str]]]:
        """Same as graph_commits but reads local branches only."""
        if not self._repo:
            return [], {}

        tag_map: dict[str, list[str]] = {}
        for tag in self._repo.tags:
            tag_map.setdefault(tag.commit.hexsha, []).append(tag.name)

        ref_list: list[tuple[str, str, str]] = []
        for b in self._repo.branches:
            try:
                ref_list.append((b.name, b.name, b.commit.hexsha))
            except Exception:
                pass

        if not ref_list:
            return [], {}

        branch_tip_map: dict[str, list[str]] = {}
        for _, display_name, tip_sha in ref_list:
            branch_tip_map.setdefault(tip_sha, []).append(display_name)

        iter_refs = [r[0] for r in ref_list]
        try:
            raw = list(self._repo.iter_commits(iter_refs, topo_order=True, max_count=max_count))
        except Exception:
            raw = []

        commits: list[CommitInfo] = []
        for c in raw:
            commits.append(CommitInfo(
                sha=c.hexsha,
                short_sha=c.hexsha[:7],
                message=c.message.strip().splitlines()[0],
                author=c.author.name or "",
                author_email=c.author.email or "",
                date=datetime.fromtimestamp(c.committed_date),
                branch="",
                tags=tag_map.get(c.hexsha, []),
                parents=[p.hexsha for p in c.parents],
            ))

        return commits, branch_tip_map

    def get_collaborators(self, token: str) -> list[dict]:
        """
        Fetch contributors for this repo from GitHub's API.
        Returns a list of dicts: {login, avatar_url, contributions}.
        Returns [] if the repo has no GitHub remote or the request fails.
        """
        import re, requests as req

        if not self._repo:
            return []

        try:
            url = self._repo.remote("origin").url
        except Exception:
            return []

        # Parse owner/repo from HTTPS or SSH remote URL
        m = re.match(r"https://github\.com/([^/]+)/([^/]+?)(?:\.git)?$", url)
        if not m:
            m = re.match(r"git@github\.com:([^/]+)/([^/]+?)(?:\.git)?$", url)
        if not m:
            return []

        owner, repo = m.group(1), m.group(2)
        headers = {
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
        }
        try:
            resp = req.get(
                f"https://api.github.com/repos/{owner}/{repo}/contributors",
                headers=headers,
                params={"per_page": 50},
                timeout=10,
            )
            if resp.status_code != 200:
                return []
            contributors = resp.json()
        except Exception:
            return []

        # Enrich each contributor with their GitHub display name so the UI can
        # match them to git commit author names (which differ from logins).
        enriched = []
        for collab in contributors:
            login = collab.get("login", "")
            gh_name = ""
            try:
                r = req.get(
                    f"https://api.github.com/users/{login}",
                    headers=headers,
                    timeout=5,
                )
                if r.status_code == 200:
                    gh_name = r.json().get("name") or ""
            except Exception:
                pass
            enriched.append({**collab, "gh_name": gh_name})
        return enriched

    def commit_files(self, sha: str) -> list[dict]:
        """Return per-file diff info for a commit."""
        if not self._repo:
            return []
        try:
            c = self._repo.commit(sha)
            if not c.parents:
                return []

            result = []
            for d in c.parents[0].diff(c, create_patch=True):
                path = d.b_path or d.a_path or ""
                if not path:
                    continue

                if d.new_file:
                    status = "added"
                elif d.deleted_file:
                    status = "deleted"
                elif d.renamed_file:
                    status = "renamed"
                else:
                    status = "modified"

                raw = d.diff or b""
                is_binary = b"\x00" in raw[:512]

                lines, ins, dels = [], 0, 0
                if not is_binary and raw:
                    try:
                        for line in raw.decode("utf-8", errors="replace").splitlines():
                            if line.startswith("+") and not line.startswith("+++"):
                                lines.append(("added",   line[1:]))
                                ins += 1
                            elif line.startswith("-") and not line.startswith("---"):
                                lines.append(("removed", line[1:]))
                                dels += 1
                            elif line.startswith("@@"):
                                lines.append(("hunk",    line))
                            elif line.startswith(" "):
                                lines.append(("context", line[1:]))
                    except Exception:
                        is_binary = True
                        lines = []

                result.append({
                    "path":       path,
                    "name":       path.split("/")[-1],
                    "status":     status,
                    "insertions": ins,
                    "deletions":  dels,
                    "lines":      lines,
                    "is_binary":  is_binary,
                })
            return result
        except Exception:
            return []

    def commit_detail(self, sha: str) -> dict:
        """Return extended info for a single commit (stats, full message)."""
        if not self._repo:
            return {}
        try:
            c = self._repo.commit(sha)
            stats = c.stats.total
            return {
                "sha": sha,
                "message": c.message.strip(),
                "author": c.author.name,
                "author_email": c.author.email,
                "date": datetime.fromtimestamp(c.committed_date).strftime("%Y-%m-%d %H:%M:%S"),
                "insertions": stats.get("insertions", 0),
                "deletions": stats.get("deletions", 0),
                "files_changed": stats.get("files", 0),
                "parents": [p.hexsha[:7] for p in c.parents],
            }
        except Exception:
            return {}

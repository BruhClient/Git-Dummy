from __future__ import annotations

import os
import subprocess
import sys

_POPEN_FLAGS = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0

_commit_author: dict[str, str] = {}


def set_commit_author(name: str, email: str) -> None:
    global _commit_author
    _commit_author = {}
    if name:
        _commit_author["GIT_AUTHOR_NAME"]    = name
        _commit_author["GIT_COMMITTER_NAME"] = name
    if email:
        _commit_author["GIT_AUTHOR_EMAIL"]    = email
        _commit_author["GIT_COMMITTER_EMAIL"] = email


def clear_commit_author() -> None:
    global _commit_author
    _commit_author = {}


def _run(path: str, cmd: list, timeout: int = 30) -> tuple[bool, str]:
    """Run a git command with a timeout. Returns (ok, error_message)."""
    try:
        env = ({**os.environ, **_commit_author} if _commit_author else None)
        r = subprocess.run(cmd, cwd=path, capture_output=True, text=True, timeout=timeout,
                           encoding="utf-8", errors="replace", env=env,
                           creationflags=_POPEN_FLAGS)
        if r.returncode != 0:
            return False, r.stderr.strip() or r.stdout.strip()
        return True, ""
    except subprocess.TimeoutExpired:
        return False, "timed_out"


def has_uncommitted_changes(path: str) -> bool:
    try:
        r = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=path, capture_output=True, text=True, encoding="utf-8", errors="replace",
            timeout=15, creationflags=_POPEN_FLAGS,
        )
        return bool(r.stdout.strip())
    except subprocess.TimeoutExpired:
        return False


def checkout_commit(path: str, sha: str) -> tuple[bool, str]:
    try:
        r = subprocess.run(
            ["git", "checkout", sha],
            cwd=path, capture_output=True, text=True, encoding="utf-8", errors="replace",
            timeout=30, creationflags=_POPEN_FLAGS,
        )
        return r.returncode == 0, r.stderr.strip()
    except subprocess.TimeoutExpired:
        return False, "timed_out"


def checkout_branch(path: str, branch: str) -> tuple[bool, str]:
    try:
        r = subprocess.run(
            ["git", "checkout", branch],
            cwd=path, capture_output=True, text=True, encoding="utf-8", errors="replace",
            timeout=30, creationflags=_POPEN_FLAGS,
        )
        return r.returncode == 0, r.stderr.strip()
    except subprocess.TimeoutExpired:
        return False, "timed_out"


def current_branch(path: str) -> str:
    """Return the current branch name, or '' if in detached HEAD state."""
    try:
        r = subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            cwd=path, capture_output=True, text=True, encoding="utf-8", errors="replace",
            timeout=10, creationflags=_POPEN_FLAGS,
        )
        result = r.stdout.strip()
        return "" if result == "HEAD" else result
    except subprocess.TimeoutExpired:
        return ""


def reset_hard(path: str) -> bool:
    """Reset index and working tree to HEAD, aborting any partial stash apply."""
    try:
        r = subprocess.run(
            ["git", "reset", "--hard", "HEAD"],
            cwd=path, capture_output=True, text=True, encoding="utf-8", errors="replace",
            timeout=15, creationflags=_POPEN_FLAGS,
        )
        return r.returncode == 0
    except subprocess.TimeoutExpired:
        return False


def get_conflict_files(path: str) -> list:
    """Return list of files with unresolved merge conflicts (call before git merge --abort)."""
    try:
        r = subprocess.run(
            ["git", "diff", "--name-only", "--diff-filter=U"],
            cwd=path, capture_output=True, text=True, timeout=10,
            encoding="utf-8", errors="replace",
            creationflags=_POPEN_FLAGS,
        )
        return [f for f in r.stdout.strip().splitlines() if f]
    except Exception:
        return []


def parse_conflict_markers(lines: list) -> tuple:
    """Parse `<<<<<<<` / `=======` / `>>>>>>>` conflict markers out of `lines`.
    Returns (original_lines, orig_start, incoming_lines, inc_start), where
    *_start is the 1-based line number of the first line after the marker.

    Shared by `get_conflict_content` (reads a working-tree file) and
    `check_pr_conflicts` (reads the stdout of `git merge-file -p`)."""
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


def get_conflict_content(repo_path: str, file_path: str) -> tuple:
    """Parse conflict markers, return (original_lines, orig_start, incoming_lines, inc_start).
    Line numbers correspond to their actual position in the file."""
    abs_path = os.path.join(repo_path, file_path.replace("/", os.sep))
    try:
        with open(abs_path, "r", encoding="utf-8", errors="replace") as f:
            lines = f.readlines()
    except Exception:
        return [], 1, [], 1
    return parse_conflict_markers(lines)

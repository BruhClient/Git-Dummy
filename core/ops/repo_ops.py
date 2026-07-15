from __future__ import annotations

import os
import subprocess

from .base_ops import _run, get_conflict_files, _POPEN_FLAGS


def init_repo(path: str, user_name: str = "", user_email: str = "") -> tuple[bool, str]:
    try:
        r = subprocess.run(["git", "init", "-b", "main"], cwd=path, capture_output=True, text=True,
                           encoding="utf-8", errors="replace", creationflags=_POPEN_FLAGS)
        if r.returncode != 0:
            # git < 2.28 does not support -b; init then manually point HEAD at main.
            r = subprocess.run(["git", "init"], cwd=path, capture_output=True, text=True,
                               encoding="utf-8", errors="replace", creationflags=_POPEN_FLAGS)
            if r.returncode != 0:
                return False, r.stderr.strip()
            subprocess.run(
                ["git", "symbolic-ref", "HEAD", "refs/heads/main"],
                cwd=path, capture_output=True, text=True,
                encoding="utf-8", errors="replace", creationflags=_POPEN_FLAGS,
            )

        # Set identity from the logged-in user; fall back only if nothing provided
        subprocess.run(["git", "config", "user.name",  user_name  or "User"],
                       cwd=path, creationflags=_POPEN_FLAGS)
        subprocess.run(["git", "config", "user.email", user_email or "user@evogit.local"],
                       cwd=path, creationflags=_POPEN_FLAGS)

        subprocess.run(["git", "add", "."], cwd=path, capture_output=True, creationflags=_POPEN_FLAGS)
        c = subprocess.run(
            ["git", "commit", "--allow-empty", "-m", "Initial commit"],
            cwd=path, capture_output=True, text=True, encoding="utf-8", errors="replace",
            creationflags=_POPEN_FLAGS,
        )
        return c.returncode == 0, c.stderr.strip()
    except Exception as e:
        return False, str(e)


def clone_repo(url: str, dest_parent: str) -> tuple[bool, str, str]:
    """Clone url into dest_parent/<repo-name>. Returns (ok, error, cloned_path)."""
    try:
        name = url.rstrip("/").removesuffix(".git").split("/")[-1]
        dest = os.path.join(dest_parent, name)
        r = subprocess.run(
            ["git", "clone", url, dest],
            capture_output=True, text=True, timeout=120,
            encoding="utf-8", errors="replace", creationflags=_POPEN_FLAGS,
        )
        if r.returncode != 0:
            return False, r.stderr.strip(), ""
        return True, "", dest
    except Exception as e:
        return False, str(e), ""


def pull_ff(path: str, branch: str) -> tuple[bool, str, bool]:
    """Fast-forward a local branch to its remote without needing to check it out."""
    old_head = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=path, capture_output=True, text=True, encoding="utf-8", errors="replace",
        timeout=5, creationflags=_POPEN_FLAGS,
    ).stdout.strip()
    current = subprocess.run(
        ["git", "rev-parse", "--abbrev-ref", "HEAD"],
        cwd=path, capture_output=True, text=True, encoding="utf-8", errors="replace",
        timeout=5, creationflags=_POPEN_FLAGS,
    ).stdout.strip()
    if current == branch:
        ok, err = _run(path, ["git", "pull", "--ff-only", "origin", branch], timeout=30)
    else:
        ok, err = _run(path, ["git", "fetch", "origin", f"{branch}:{branch}"], timeout=30)
    stash_conflict = False
    if ok and old_head:
        from .stash_ops import migrate_stash_after_pull
        _, reason = migrate_stash_after_pull(path, old_head)
        stash_conflict = reason == "conflict"
    return ok, err, stash_conflict


def pull_stash_apply(path: str, branch: str) -> tuple[bool, str]:
    """Stash changes (including untracked files), fast-forward to remote, re-apply stash."""
    old_head = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=path, capture_output=True, text=True, encoding="utf-8", errors="replace",
        timeout=5, creationflags=_POPEN_FLAGS,
    ).stdout.strip()
    ok, err = _run(path, ["git", "stash", "--include-untracked"])
    if not ok:
        return False, err
    ok, err = _run(path, ["git", "fetch", "origin"])
    if not ok:
        # Restore stash before returning — user's changes must not be lost.
        subprocess.run(["git", "stash", "pop"], cwd=path, capture_output=True,
                       timeout=30, creationflags=_POPEN_FLAGS)
        return False, err
    ok, err = _run(path, ["git", "reset", "--hard", f"origin/{branch}"])
    if not ok:
        subprocess.run(["git", "stash", "pop"], cwd=path, capture_output=True,
                       timeout=30, creationflags=_POPEN_FLAGS)
        return False, err
    r = subprocess.run(["git", "stash", "pop"],
                       cwd=path, capture_output=True, text=True, timeout=30,
                       encoding="utf-8", errors="replace", creationflags=_POPEN_FLAGS)
    if r.returncode != 0:
        # Pop conflicted — reset working tree cleanly; stash entry is preserved.
        subprocess.run(["git", "reset", "--hard", "HEAD"],
                       cwd=path, capture_output=True, text=True, timeout=10,
                       encoding="utf-8", errors="replace", creationflags=_POPEN_FLAGS)
        return False, "stash_conflict"
    if old_head:
        from .stash_ops import migrate_stash_after_pull
        migrate_stash_after_pull(path, old_head)
    return True, ""


def pull_save_merge(path: str, branch: str) -> tuple[bool, str, list]:
    """Commit unsaved changes then merge remote into local."""
    _run(path, ["git", "add", "-A"])
    # Only commit when there are actual staged changes; nothing-to-commit is not an error.
    status_r = subprocess.run(
        ["git", "status", "--porcelain"],
        cwd=path, capture_output=True, text=True, timeout=5,
        encoding="utf-8", errors="replace", creationflags=_POPEN_FLAGS,
    )
    if status_r.stdout.strip():
        ok, err = _run(path, ["git", "commit", "-m", "saved changes before pull"])
        if not ok:
            return False, err, []
    ok, err = _run(path, ["git", "fetch", "origin"])
    if not ok:
        return False, err, []
    ok3, err3 = _run(path, ["git", "merge", f"origin/{branch}"])
    if not ok3:
        conflict_files = get_conflict_files(path)
        subprocess.run(["git", "merge", "--abort"],
                       cwd=path, capture_output=True, text=True, timeout=10,
                       encoding="utf-8", errors="replace", creationflags=_POPEN_FLAGS)
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

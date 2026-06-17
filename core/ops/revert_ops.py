from __future__ import annotations

import subprocess

from .base_ops import _run


def discard_all_changes(path: str) -> tuple[bool, str]:
    for cmd in (["git", "reset", "--hard", "HEAD"], ["git", "clean", "-fd"]):
        ok, err = _run(path, cmd)
        if not ok:
            return False, err
    return True, ""


def hard_revert_to(path: str, branch: str, target_sha: str) -> tuple[bool, str]:
    try:
        cur = subprocess.run(["git", "rev-parse", "--abbrev-ref", "HEAD"],
                             cwd=path, capture_output=True, text=True,
                             encoding="utf-8", errors="replace", timeout=5)
        current = cur.stdout.strip()
        if current == "HEAD":
            current = ""
    except Exception:
        current = ""
    if current != branch:
        ok, err = _run(path, ["git", "checkout", branch])
        if not ok:
            return False, err

    pre_r = subprocess.run(
        ["git", "rev-parse", branch],
        cwd=path, capture_output=True, text=True,
        encoding="utf-8", errors="replace", timeout=5,
    )
    pre_reset_sha = pre_r.stdout.strip() if pre_r.returncode == 0 else ""

    if not pre_reset_sha:
        return False, "Could not determine current branch tip — aborting to avoid leaving the repo in a broken state."

    ok, err = _run(path, ["git", "reset", "--hard", target_sha])
    if not ok:
        return False, err

    has_remote = subprocess.run(
        ["git", "remote", "get-url", "origin"],
        cwd=path, capture_output=True, timeout=5,
    ).returncode == 0
    if has_remote:
        r = subprocess.run(
            ["git", "push", "--force", "origin", branch],
            cwd=path, capture_output=True, text=True,
            encoding="utf-8", errors="replace", timeout=30,
        )
        if r.returncode != 0:
            if pre_reset_sha:
                _run(path, ["git", "reset", "--hard", pre_reset_sha])
            combined = r.stderr.strip() or r.stdout.strip()
            if "GH006" in combined or "protected branch" in combined.lower():
                return False, (
                    f"'{branch}' is protected on GitHub — force-push rejected. "
                    f"Remove branch protection in GitHub → Settings → Branches to hard revert."
                )
            return False, f"Remote push failed — nothing was changed: {combined}"
    return True, ""


def soft_revert_to(path: str, branch: str, tip_sha: str, parent_sha: str = "") -> tuple[bool, str]:
    target = parent_sha if parent_sha else f"{tip_sha}^"
    short  = parent_sha[:7] if parent_sha else "prev"
    msg    = f"reverted to {short}"

    try:
        cur = subprocess.run(["git", "rev-parse", "--abbrev-ref", "HEAD"],
                             cwd=path, capture_output=True, text=True,
                             encoding="utf-8", errors="replace", timeout=5)
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
    # Use read-tree --reset -u instead of "checkout <sha> -- ." because the latter
    # resolves "." against the current index — if the index is empty (e.g. the repo
    # was initialised on an empty directory) git raises "pathspec '.' did not match
    # any files known to git".  read-tree needs no pathspec, handles empty trees
    # gracefully, and also removes files not in the target (which checkout -- . misses).
    ok, err = _run(path, ["git", "read-tree", "--reset", "-u", target])
    if not ok:
        # Restore index to HEAD so the working tree is not left in a half-reset state.
        subprocess.run(["git", "reset", "HEAD"], cwd=path, capture_output=True, timeout=10)
        return False, err

    ok, err = _run(path, ["git", "add", "-A"])
    if not ok:
        subprocess.run(["git", "reset", "HEAD"], cwd=path, capture_output=True, timeout=10)
        return False, err

    ok, err = _run(path, ["git", "commit", "-m", msg])
    if not ok:
        subprocess.run(["git", "reset", "HEAD"], cwd=path, capture_output=True, timeout=10)
        if "nothing to commit" in err.lower():
            return False, (
                "Nothing to revert — the merged branch introduced no file changes, "
                "so this commit's content is identical to its parent. "
                "On a protected branch, Hard Revert (which removes commits from history) is blocked."
            )
        return False, err
    return True, ""

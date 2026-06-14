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

    # Remember the branch tip *before* the reset — this is the last state of
    # the branch this repo actually knew about. Used below to make sure a
    # force-push doesn't discard remote commits this repo never fetched.
    pre_r = subprocess.run(
        ["git", "rev-parse", branch],
        cwd=path, capture_output=True, text=True, timeout=5,
    )
    pre_reset_sha = pre_r.stdout.strip() if pre_r.returncode == 0 else ""

    ok, err = _run(path, ["git", "reset", "--hard", target_sha])
    if not ok:
        return False, err
    # Only push if the branch actually exists on origin — skip for local-only repos.
    ls = subprocess.run(
        ["git", "ls-remote", "--heads", "origin", branch],
        cwd=path, capture_output=True, text=True, timeout=10,
    )
    if ls.returncode == 0 and ls.stdout.strip():
        # Fetch first so origin/{branch} reflects the *current* remote state,
        # not a possibly-stale cached ref.
        _run(path, ["git", "fetch", "origin", branch], timeout=30)

        origin_r = subprocess.run(
            ["git", "rev-parse", f"origin/{branch}"],
            cwd=path, capture_output=True, text=True, timeout=5,
        )
        origin_sha = origin_r.stdout.strip() if origin_r.returncode == 0 else ""

        # If origin/{branch} has moved to a commit this repo didn't know about
        # before the revert (i.e. it isn't an ancestor of our pre-revert tip),
        # force-pushing now would silently discard those remote-only commits.
        if origin_sha and pre_reset_sha and origin_sha != pre_reset_sha:
            anc = subprocess.run(
                ["git", "merge-base", "--is-ancestor", origin_sha, pre_reset_sha],
                cwd=path, capture_output=True, text=True, timeout=10,
            )
            if anc.returncode != 0:
                return False, (
                    f"Local branch reverted, but '{branch}' was NOT force-pushed: "
                    f"origin/{branch} has commits this repo hadn't fetched yet. "
                    f"Fetch and review those changes before pushing manually."
                )

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
        # Uncommit the staged changes so the working tree is not left dirty-staged.
        subprocess.run(["git", "reset", "HEAD"], cwd=path, capture_output=True, timeout=10)
        return False, err
    return True, ""

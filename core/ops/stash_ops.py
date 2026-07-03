from __future__ import annotations

import subprocess

from .base_ops import _run, get_conflict_files, get_conflict_content, _POPEN_FLAGS


def get_stash_files(path: str, stash_id: str = "") -> list[str]:
    ref = ""
    if stash_id:
        r = subprocess.run(
            ["git", "stash", "list"],
            cwd=path, capture_output=True, text=True, encoding="utf-8", errors="replace",
            creationflags=_POPEN_FLAGS,
        )
        for line in r.stdout.strip().splitlines():
            if stash_id in line:
                ref = line.split(":")[0].strip()
                break
    args = ["git", "stash", "show", "--name-only"]
    if ref:
        args.append(ref)
    r = subprocess.run(args, cwd=path, capture_output=True, text=True, creationflags=_POPEN_FLAGS)
    if r.returncode != 0:
        return []
    return [f.strip() for f in r.stdout.strip().splitlines() if f.strip()]


def create_auto_stash(path: str) -> tuple[list[str], str]:
    """Stash uncommitted changes. Returns (stashed_files, stash_id) or ([], '') on failure."""
    import uuid
    stash_id = "evogit-autostash-" + uuid.uuid4().hex[:8]

    # Try with untracked files first, fall back to tracked-only if that fails.
    for cmd in [
        ["git", "stash", "push", "--include-untracked", "-m", stash_id],
        ["git", "stash", "push", "-m", stash_id],
    ]:
        r = subprocess.run(cmd, cwd=path, capture_output=True, text=True, creationflags=_POPEN_FLAGS)
        output = r.stdout + r.stderr
        if r.returncode == 0 and "No local changes" not in output:
            return get_stash_files(path), stash_id

    return [], ""


def pop_auto_stash(path: str, stash_id: str = "") -> bool:
    if stash_id:
        r = subprocess.run(
            ["git", "stash", "list"],
            cwd=path, capture_output=True, text=True, encoding="utf-8", errors="replace",
            creationflags=_POPEN_FLAGS,
        )
        for line in r.stdout.strip().splitlines():
            if stash_id in line:
                ref = line.split(":")[0].strip()
                r2 = subprocess.run(
                    ["git", "stash", "pop", ref],
                    cwd=path, capture_output=True, text=True, encoding="utf-8", errors="replace",
                    creationflags=_POPEN_FLAGS,
                )
                return r2.returncode == 0
        return False
    r = subprocess.run(
        ["git", "stash", "pop"],
        cwd=path, capture_output=True, text=True, encoding="utf-8", errors="replace",
        creationflags=_POPEN_FLAGS,
    )
    return r.returncode == 0


def apply_stash(path: str, stash_ref: str) -> bool:
    """Apply a stash to the working directory without removing it from the stash list."""
    r = subprocess.run(
        ["git", "stash", "apply", stash_ref],
        cwd=path, capture_output=True, text=True, encoding="utf-8", errors="replace",
        creationflags=_POPEN_FLAGS,
    )
    return r.returncode == 0


def drop_stash(path: str, stash_ref: str) -> bool:
    """Remove a stash entry from the stash list without applying it."""
    r = subprocess.run(
        ["git", "stash", "drop", stash_ref],
        cwd=path, capture_output=True, text=True, encoding="utf-8", errors="replace",
        creationflags=_POPEN_FLAGS,
    )
    return r.returncode == 0


def get_stash_ref_for_commit(path: str, commit_sha: str) -> str:
    """Return the stash ref (e.g. 'stash@{0}') whose parent is commit_sha, or ''."""
    r = subprocess.run(
        ["git", "stash", "list", "--format=%gd %P"],
        cwd=path, capture_output=True, text=True, encoding="utf-8", errors="replace",
        creationflags=_POPEN_FLAGS,
    )
    for line in r.stdout.strip().splitlines():
        parts = line.strip().split()
        if len(parts) >= 2 and parts[1] == commit_sha:
            return parts[0]
    return ""


def get_stash_commit_shas(path: str) -> set[str]:
    """Return the set of commit SHAs that have a stash sitting on top of them."""
    r = subprocess.run(
        ["git", "stash", "list", "--format=%P"],
        cwd=path, capture_output=True, text=True, encoding="utf-8", errors="replace",
        creationflags=_POPEN_FLAGS,
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
        cwd=path, capture_output=True, text=True, encoding="utf-8", errors="replace",
        creationflags=_POPEN_FLAGS,
    )
    return r.stdout.strip()


def migrate_stash_after_pull(path: str, old_head_sha: str) -> bool:
    """After a pull, apply and drop any stash whose parent was the old HEAD.

    This moves the stash's content into the working tree on the new HEAD so the
    stash indicator disappears from the old commit.  If the apply conflicts with
    the current working tree the stash is left untouched.
    """
    stash_ref = get_stash_ref_for_commit(path, old_head_sha)
    if not stash_ref:
        return False
    r = subprocess.run(
        ["git", "stash", "apply", stash_ref],
        cwd=path, capture_output=True, text=True, encoding="utf-8", errors="replace",
        timeout=30, creationflags=_POPEN_FLAGS,
    )
    if r.returncode != 0:
        return False
    subprocess.run(
        ["git", "stash", "drop", stash_ref],
        cwd=path, capture_output=True, text=True, encoding="utf-8", errors="replace",
        timeout=10, creationflags=_POPEN_FLAGS,
    )
    return True


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
        cwd=path, capture_output=True, text=True, encoding="utf-8", errors="replace",
        timeout=5, creationflags=_POPEN_FLAGS,
    ).stdout.strip()

    # 1. Apply stash so working tree has the changes.
    if stash_ref:
        r = subprocess.run(
            ["git", "stash", "apply", stash_ref],
            cwd=path, capture_output=True, text=True, encoding="utf-8", errors="replace",
            timeout=30, creationflags=_POPEN_FLAGS,
        )
        if r.returncode != 0:
            conflict_files = get_conflict_files(path)
            if conflict_files:
                content = {f: get_conflict_content(path, f) for f in conflict_files}
                subprocess.run(["git", "reset", "HEAD"], cwd=path, capture_output=True,
                               timeout=10, creationflags=_POPEN_FLAGS)
                subprocess.run(["git", "checkout", "--", "."], cwd=path, capture_output=True,
                               timeout=10, creationflags=_POPEN_FLAGS)
                subprocess.run(["git", "clean", "-fd"], cwd=path, capture_output=True,
                               timeout=10, creationflags=_POPEN_FLAGS)
                return False, "save_conflict", conflict_files, content
            return False, (r.stderr.strip() or r.stdout.strip() or
                           "Could not apply saved changes."), [], {}

    # Determine whether we need to switch branches.
    cur = subprocess.run(
        ["git", "rev-parse", "--abbrev-ref", "HEAD"],
        cwd=path, capture_output=True, text=True, encoding="utf-8", errors="replace",
        timeout=5, creationflags=_POPEN_FLAGS,
    ).stdout.strip()
    need_switch = bool(branch) and cur != branch

    if need_switch:
        local_exists = subprocess.run(
            ["git", "rev-parse", "--verify", f"refs/heads/{branch}"],
            cwd=path, capture_output=True, text=True, encoding="utf-8", errors="replace",
            timeout=5, creationflags=_POPEN_FLAGS,
        ).returncode == 0

        if not local_exists:
            # ── Path A: remote-only branch ────────────────────────────────
            ok_co, err_co = _run(
                path, ["git", "checkout", "-b", branch, f"origin/{branch}"]
            )
            if not ok_co:
                subprocess.run(["git", "checkout", "--", "."],
                               cwd=path, capture_output=True, timeout=10, creationflags=_POPEN_FLAGS)
                subprocess.run(["git", "clean", "-fd"],
                               cwd=path, capture_output=True, timeout=10, creationflags=_POPEN_FLAGS)
                return False, f"Could not create local branch '{branch}': {err_co}", [], {}
            # Fall through to the shared stage-and-commit block below.

        else:
            # ── Path B: local branch exists at a (possibly different) tip ─
            subprocess.run(["git", "add", "-A"], cwd=path, capture_output=True,
                           timeout=10, creationflags=_POPEN_FLAGS)
            status = subprocess.run(
                ["git", "status", "--porcelain"],
                cwd=path, capture_output=True, text=True, encoding="utf-8", errors="replace",
                timeout=10, creationflags=_POPEN_FLAGS,
            ).stdout.strip()
            if not status:
                return False, "Nothing new to commit — changes already in branch.", [], {}

            ok, err = _run(path, ["git", "commit", "-m", message or "saved changes"])
            if not ok:
                subprocess.run(["git", "reset", "HEAD"], cwd=path,
                               capture_output=True, timeout=10, creationflags=_POPEN_FLAGS)
                return False, err, [], {}

            saved_sha = subprocess.run(
                ["git", "rev-parse", "HEAD"],
                cwd=path, capture_output=True, text=True, encoding="utf-8", errors="replace",
                timeout=5, creationflags=_POPEN_FLAGS,
            ).stdout.strip()

            ok_co, err_co = _run(path, ["git", "checkout", branch])
            if not ok_co:
                subprocess.run(["git", "checkout", original_sha],
                               cwd=path, capture_output=True, timeout=10, creationflags=_POPEN_FLAGS)
                # Prefer re-applying the stash (never popped, still exists) over cherry-pick.
                restored = False
                if stash_ref:
                    r_sa = subprocess.run(
                        ["git", "stash", "apply", stash_ref],
                        cwd=path, capture_output=True, timeout=30, creationflags=_POPEN_FLAGS,
                    )
                    restored = r_sa.returncode == 0
                if not restored:
                    r_cp = subprocess.run(
                        ["git", "cherry-pick", "--no-commit", saved_sha],
                        cwd=path, capture_output=True, timeout=30, creationflags=_POPEN_FLAGS,
                    )
                    if r_cp.returncode != 0:
                        subprocess.run(["git", "cherry-pick", "--abort"],
                                       cwd=path, capture_output=True, timeout=10, creationflags=_POPEN_FLAGS)
                return False, f"Could not switch to '{branch}': {err_co}", [], {}

            ok_m, err_m = _run(path, ["git", "merge", "--no-ff", saved_sha,
                                       "-m", message or "saved changes"])
            if not ok_m:
                conflict_files   = get_conflict_files(path)
                conflict_content = {f: get_conflict_content(path, f) for f in conflict_files}
                subprocess.run(["git", "merge", "--abort"],
                               cwd=path, capture_output=True, timeout=10, creationflags=_POPEN_FLAGS)
                subprocess.run(["git", "checkout", original_sha],
                               cwd=path, capture_output=True, timeout=10, creationflags=_POPEN_FLAGS)
                # Prefer re-applying the stash (never popped, still exists) over cherry-pick.
                restored = False
                if stash_ref:
                    r_sa = subprocess.run(
                        ["git", "stash", "apply", stash_ref],
                        cwd=path, capture_output=True, timeout=30, creationflags=_POPEN_FLAGS,
                    )
                    restored = r_sa.returncode == 0
                if not restored:
                    r_cp = subprocess.run(
                        ["git", "cherry-pick", "--no-commit", saved_sha],
                        cwd=path, capture_output=True, timeout=30, creationflags=_POPEN_FLAGS,
                    )
                    if r_cp.returncode != 0:
                        subprocess.run(["git", "cherry-pick", "--abort"],
                                       cwd=path, capture_output=True, timeout=10, creationflags=_POPEN_FLAGS)
                return False, "save_conflict", conflict_files, conflict_content

            if stash_ref:
                subprocess.run(["git", "stash", "drop", stash_ref],
                               cwd=path, capture_output=True, text=True, encoding="utf-8",
                               errors="replace", timeout=10, creationflags=_POPEN_FLAGS)
            return True, "", [], {}

    # ── Shared: stage + commit directly on the current (or freshly-checked-out) branch ──
    subprocess.run(["git", "add", "-A"], cwd=path, capture_output=True,
                   timeout=10, creationflags=_POPEN_FLAGS)
    status = subprocess.run(
        ["git", "status", "--porcelain"],
        cwd=path, capture_output=True, text=True, encoding="utf-8", errors="replace",
        timeout=10, creationflags=_POPEN_FLAGS,
    ).stdout.strip()
    if not status:
        return False, "Nothing new to commit — changes already in branch.", [], {}

    ok, err = _run(path, ["git", "commit", "-m", message or "saved changes"])
    if not ok:
        subprocess.run(["git", "reset", "HEAD"], cwd=path,
                       capture_output=True, timeout=10, creationflags=_POPEN_FLAGS)
        return False, err, [], {}

    if stash_ref:
        subprocess.run(["git", "stash", "drop", stash_ref],
                       cwd=path, capture_output=True, text=True, encoding="utf-8",
                       errors="replace", timeout=10, creationflags=_POPEN_FLAGS)
    return True, "", [], {}


def save_stash_with_decisions(path: str, stash_ref: str, message: str,
                              decisions: dict) -> tuple[bool, str]:
    """Re-apply a conflicting stash, resolve per-file, commit."""
    subprocess.run(
        ["git", "stash", "apply", stash_ref],
        cwd=path, capture_output=True, text=True, encoding="utf-8", errors="replace",
        timeout=30, creationflags=_POPEN_FLAGS,
    )
    for filepath, choice in decisions.items():
        if choice == "ours":
            _run(path, ["git", "checkout", "--ours", filepath])
        else:
            _run(path, ["git", "checkout", "--theirs", filepath])
        _run(path, ["git", "add", filepath])
    subprocess.run(["git", "add", "-A"], cwd=path, capture_output=True,
                   timeout=10, creationflags=_POPEN_FLAGS)
    ok, err = _run(path, ["git", "commit", "-m", message or "saved changes"])
    if not ok:
        subprocess.run(["git", "merge", "--abort"], cwd=path, capture_output=True,
                       timeout=10, encoding="utf-8", errors="replace", creationflags=_POPEN_FLAGS)
        subprocess.run(["git", "reset", "HEAD"], cwd=path, capture_output=True,
                       timeout=10, creationflags=_POPEN_FLAGS)
        subprocess.run(["git", "checkout", "--", "."], cwd=path, capture_output=True,
                       timeout=10, creationflags=_POPEN_FLAGS)
        subprocess.run(["git", "clean", "-fd"], cwd=path, capture_output=True,
                       timeout=10, creationflags=_POPEN_FLAGS)
        return False, err
    if stash_ref:
        subprocess.run(["git", "stash", "drop", stash_ref],
                       cwd=path, capture_output=True, text=True, encoding="utf-8",
                       errors="replace", timeout=10, creationflags=_POPEN_FLAGS)
    return True, ""

from __future__ import annotations

import subprocess

from .base_ops import _run, _POPEN_FLAGS


def get_default_branch(path: str) -> str:
    """Detect the repo's default branch without hitting the network.

    Detection order:
    1. git symbolic-ref refs/remotes/origin/HEAD  (strips refs/remotes/origin/ prefix)
    2. git rev-parse --verify main
    3. git rev-parse --verify master
    4. Fallback: "main"
    """
    try:
        r = subprocess.run(
            ["git", "symbolic-ref", "refs/remotes/origin/HEAD"],
            cwd=path, capture_output=True, text=True, timeout=5,
            encoding="utf-8", errors="replace", creationflags=_POPEN_FLAGS,
        )
        if r.returncode == 0:
            ref = r.stdout.strip()
            prefix = "refs/remotes/origin/"
            if ref.startswith(prefix):
                return ref[len(prefix):]
    except Exception:
        pass

    for candidate in ("main", "master"):
        try:
            r = subprocess.run(
                ["git", "rev-parse", "--verify", candidate],
                cwd=path, capture_output=True, text=True, timeout=5,
                encoding="utf-8", errors="replace", creationflags=_POPEN_FLAGS,
            )
            if r.returncode == 0:
                return candidate
        except Exception:
            pass

    return "main"


def branch_for_commit(path: str, sha: str) -> str:
    """Return a branch name that contains sha — used when in detached HEAD."""
    try:
        r = subprocess.run(
            ["git", "branch", "--contains", sha],
            cwd=path, capture_output=True, text=True, encoding="utf-8", errors="replace",
            timeout=15, creationflags=_POPEN_FLAGS,
        )
    except subprocess.TimeoutExpired:
        return ""
    for line in r.stdout.splitlines():
        name = line.strip().lstrip("* ").strip()
        if name and not name.startswith("("):
            return name
    return ""


def get_branch_unique_commits(path: str, tip_sha: str, base: str = "main") -> tuple[bool, list[str]]:
    """Return SHAs reachable from tip_sha but not from base.
    Returns empty list for FF-merged branches (their commits are already on base)."""
    r = subprocess.run(
        ["git", "log", f"{base}..{tip_sha}", "--format=%H"],
        cwd=path, capture_output=True, text=True, timeout=30,
        encoding="utf-8", errors="replace", creationflags=_POPEN_FLAGS,
    )
    if r.returncode != 0:
        return False, []
    shas = [s.strip() for s in r.stdout.splitlines() if s.strip()]
    return True, shas


def branch_unique_count(path: str, branch: str, default_branch: str) -> int:
    """Return the number of commits on `branch` not reachable from `default_branch`."""
    try:
        r = subprocess.run(
            ["git", "rev-list", "--count", f"{default_branch}..{branch}"],
            cwd=path, capture_output=True, text=True, timeout=10,
            encoding="utf-8", errors="replace", creationflags=_POPEN_FLAGS,
        )
        return int(r.stdout.strip()) if r.returncode == 0 else 0
    except Exception:
        return 0


def delete_branch_full(path: str, branch: str, fallback_sha: str = "") -> tuple[bool, str]:
    cur = subprocess.run(
        ["git", "rev-parse", "--abbrev-ref", "HEAD"],
        cwd=path, capture_output=True, text=True, timeout=10,
        encoding="utf-8", errors="replace", creationflags=_POPEN_FLAGS,
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
                encoding="utf-8", errors="replace", creationflags=_POPEN_FLAGS,
            )
            for line in r.stdout.strip().splitlines():
                name = line.strip().lstrip("* ")
                # Skip the branch being deleted and any detached HEAD entries
                if name and name != branch and not name.startswith("("):
                    checkout_target = name
                    break
        except Exception:
            pass

        # Fall back to the repo's detected default branch if --contains found nothing usable
        if not checkout_target:
            default = get_default_branch(path)
            if default != branch:
                r = subprocess.run(
                    ["git", "rev-parse", "--verify", default],
                    cwd=path, capture_output=True, text=True, timeout=5,
                    encoding="utf-8", errors="replace", creationflags=_POPEN_FLAGS,
                )
                if r.returncode == 0:
                    checkout_target = default

        # Last resort: detached checkout to the parent SHA — but only if it exists.
        if not checkout_target:
            has_parent = subprocess.run(
                ["git", "rev-parse", "--verify", target],
                cwd=path, capture_output=True, text=True, timeout=5,
                encoding="utf-8", errors="replace", creationflags=_POPEN_FLAGS,
            ).returncode == 0
            if not has_parent:
                return False, (
                    f"Cannot delete '{branch}': it is the only branch and has no parent "
                    "commit to fall back to. Create another branch first."
                )
            checkout_target = target

        ok, err = _run(path, ["git", "checkout", checkout_target])
        if not ok:
            return False, err

    ok, err = _run(path, ["git", "branch", "-D", "--", branch])
    if not ok:
        return False, err

    # Only attempt remote delete when the branch actually exists on origin
    ls = subprocess.run(
        ["git", "ls-remote", "--heads", "origin", "--", branch],
        cwd=path, capture_output=True, text=True, timeout=10,
        encoding="utf-8", errors="replace", creationflags=_POPEN_FLAGS,
    )
    if ls.returncode == 0 and ls.stdout.strip():
        r = subprocess.run(
            ["git", "push", "origin", "--delete", "--", branch],
            cwd=path, capture_output=True, text=True, timeout=30,
            encoding="utf-8", errors="replace", creationflags=_POPEN_FLAGS,
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
                       cwd=path, capture_output=True, text=True, timeout=10,
                       encoding="utf-8", errors="replace", creationflags=_POPEN_FLAGS)
        subprocess.run(["git", "branch", "-D", branch_name],
                       cwd=path, capture_output=True, text=True, timeout=10,
                       encoding="utf-8", errors="replace", creationflags=_POPEN_FLAGS)
        return False, err2
    return True, ""

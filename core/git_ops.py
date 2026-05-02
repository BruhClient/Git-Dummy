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


def get_stash_files(path: str) -> list[str]:
    r = subprocess.run(
        ["git", "stash", "show", "--name-only"],
        cwd=path, capture_output=True, text=True,
    )
    if r.returncode != 0:
        return []
    return [f.strip() for f in r.stdout.strip().splitlines() if f.strip()]


def create_auto_stash(path: str) -> list[str]:
    """Stash uncommitted changes. Returns list of stashed files, or [] on failure."""
    from datetime import datetime
    msg = "Auto-stash: " + datetime.now().strftime("%b %d %I:%M %p")
    r = subprocess.run(
        ["git", "stash", "push", "-m", msg],
        cwd=path, capture_output=True, text=True,
    )
    if r.returncode != 0 or "No local changes" in r.stdout:
        return []
    return get_stash_files(path)


def pop_auto_stash(path: str) -> bool:
    r = subprocess.run(
        ["git", "stash", "pop"],
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
        ["git", "branch", "--show-current"],
        cwd=path, capture_output=True, text=True,
    )
    return r.stdout.strip()


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
            ["git", "commit", "-m", "First commit"],
            cwd=path, capture_output=True, text=True,
        )
        return c.returncode == 0, c.stderr.strip()
    except Exception as e:
        return False, str(e)


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
            run("git", "commit", "-m", "First commit")

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

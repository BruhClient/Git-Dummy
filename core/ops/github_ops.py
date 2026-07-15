from __future__ import annotations

import base64
import re
import subprocess
from urllib.parse import urlparse

import requests

from .base_ops import _run, _POPEN_FLAGS


def parse_github_owner_repo(url: str) -> "tuple[str, str] | None":
    """Extract (owner, repo) from a GitHub remote URL, or None if it doesn't match."""
    m = re.search(r"github\.com[:/]([^/]+)/([^/]+?)(?:\.git)?$", url or "")
    if not m:
        return None
    return m.group(1), m.group(2)


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


def push_branch(
    path: str,
    branch: str,
    username: str = "",
    token: str = "",
    remote_url: str = "",
) -> tuple[bool, str]:
    if username and token and remote_url:
        b64 = base64.b64encode(f"{username}:{token}".encode()).decode()
        subprocess.run(
            ["git", "config", "--local", f"http.{remote_url}.extraHeader",
             f"Authorization: Basic {b64}"],
            cwd=path, capture_output=True, creationflags=_POPEN_FLAGS,
        )
    try:
        r = subprocess.run(
            ["git", "push", "-u", "origin", "--", branch],
            cwd=path, capture_output=True, text=True, timeout=60,
            encoding="utf-8", errors="replace", creationflags=_POPEN_FLAGS,
        )
    except subprocess.TimeoutExpired:
        return False, "timed_out"
    if r.returncode == 0:
        return True, ""

    # git puts [rejected] / non-fast-forward in stdout; errors in stderr
    combined = (r.stdout + r.stderr).lower()

    if "non-fast-forward" in combined or "rejected" in combined:
        return False, "behind_remote"

    return False, r.stderr.strip() or r.stdout.strip()


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
                capture_output=True, text=True,
                encoding="utf-8", errors="replace",
                creationflags=_POPEN_FLAGS, **kw,
            )
            if r.returncode != 0:
                raise RuntimeError(r.stderr.strip() or r.stdout.strip())
            return r

        subprocess.run(["git", "config", "user.name",  user_name  or username or "User"],
                       cwd=path, creationflags=_POPEN_FLAGS)
        subprocess.run(["git", "config", "user.email", user_email or "user@evogit.local"],
                       cwd=path, creationflags=_POPEN_FLAGS)

        # Stage and commit if no commits yet
        log = subprocess.run(
            ["git", "log", "--oneline", "-1"],
            cwd=path, capture_output=True, creationflags=_POPEN_FLAGS,
        )
        if log.returncode != 0 or not log.stdout.strip():
            run("git", "add", ".")
            run("git", "commit", "--allow-empty", "-m", "Initial commit")

        # Add remote with the clean URL (no token embedded — stored as http header below).
        subprocess.run(["git", "remote", "remove", "origin"], cwd=path,
                       capture_output=True, creationflags=_POPEN_FLAGS)
        run("git", "remote", "add", "origin", clone_url)

        # Authenticate via HTTP Basic header so the token never appears in the remote URL
        # or in `git remote -v` output.  Disable the credential helper for GitHub so git
        # doesn't prompt or double-send credentials.
        b64 = base64.b64encode(f"{username}:{token}".encode()).decode()
        run("git", "config", "--local", "credential.https://github.com.helper", "")
        run("git", "config", "--local",
            f"http.{clone_url}.extraHeader", f"Authorization: Basic {b64}")

        run("git", "push", "-u", "origin", "HEAD")

        return True, ""
    except RuntimeError as e:
        return False, str(e)
    except Exception as e:
        return False, str(e)


def fork_repo(path: str, token: str, login: str) -> tuple[bool, str]:
    """Fork the origin repo to the user's account and set push URL to the fork."""
    try:
        r = subprocess.run(
            ["git", "remote", "get-url", "origin"],
            cwd=path, capture_output=True, text=True,
            encoding="utf-8", errors="replace", creationflags=_POPEN_FLAGS,
        )
        url = r.stdout.strip()
        parsed = parse_github_owner_repo(url)
        if not parsed:
            return False, "Could not parse remote URL."
        owner, repo = parsed

        resp = requests.post(
            f"https://api.github.com/repos/{owner}/{repo}/forks",
            headers={
                "Authorization": f"Bearer {token}",
                "Accept": "application/vnd.github+json",
            },
            timeout=30,
        )
        if resp.status_code not in (202, 200):
            msg = resp.json().get("message", f"HTTP {resp.status_code}")
            return False, msg

        fork_url = resp.json().get("clone_url", "")
        if not fork_url:
            return False, "Fork created but no clone URL returned."

        subprocess.run(
            ["git", "remote", "set-url", "origin", fork_url],
            cwd=path, capture_output=True, creationflags=_POPEN_FLAGS,
        )
        b64 = base64.b64encode(f"{login}:{token}".encode()).decode()
        subprocess.run(
            ["git", "config", "--local",
             f"http.{fork_url}.extraHeader", f"Authorization: Basic {b64}"],
            cwd=path, capture_output=True, creationflags=_POPEN_FLAGS,
        )
        return True, fork_url
    except Exception as e:
        return False, str(e)

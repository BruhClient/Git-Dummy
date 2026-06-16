from __future__ import annotations

import base64
import subprocess
from urllib.parse import urlparse

import requests

from .base_ops import _run


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
) -> tuple[bool, str, list, dict]:
    if username and token and remote_url:
        b64 = base64.b64encode(f"{username}:{token}".encode()).decode()
        subprocess.run(
            ["git", "config", "--local", f"http.{remote_url}.extraHeader",
             f"Authorization: Basic {b64}"],
            cwd=path, capture_output=True,
        )
    r = subprocess.run(
        ["git", "push", "-u", "origin", branch],
        cwd=path, capture_output=True, text=True, timeout=60,
    )
    if r.returncode == 0:
        return True, "", [], {}

    # git puts [rejected] / non-fast-forward in stdout; errors in stderr
    combined = (r.stdout + r.stderr).lower()

    if "non-fast-forward" in combined or "rejected" in combined:
        return False, "behind_remote", [], {}

    return False, r.stderr.strip() or r.stdout.strip(), [], {}


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
        subprocess.run(["git", "config", "user.email", user_email or "user@evogit.local"],   cwd=path)

        # Stage and commit if no commits yet
        log = subprocess.run(
            ["git", "log", "--oneline", "-1"],
            cwd=path, capture_output=True,
        )
        if log.returncode != 0 or not log.stdout.strip():
            run("git", "add", ".")
            run("git", "commit", "--allow-empty", "-m", "Initial commit")

        # Add remote with the clean URL (no token embedded — stored as http header below).
        subprocess.run(["git", "remote", "remove", "origin"], cwd=path, capture_output=True)
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

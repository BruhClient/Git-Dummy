from __future__ import annotations

import os
import subprocess
from urllib.parse import urlparse

import requests


def init_repo(path: str) -> tuple[bool, str]:
    try:
        r = subprocess.run(["git", "init", "-b", "main"], cwd=path, capture_output=True, text=True)
        if r.returncode != 0:
            return False, r.stderr.strip()

        # Set a local identity so the commit doesn't fail on unconfigured machines
        subprocess.run(["git", "config", "user.email", "gitdummy@local"], cwd=path)
        subprocess.run(["git", "config", "user.name", "Git Dummy"], cwd=path)

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

        # Ensure user identity is set (local scope only)
        subprocess.run(["git", "config", "user.email", "gitdummy@local"], cwd=path)
        subprocess.run(["git", "config", "user.name", "Git Dummy"], cwd=path)

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

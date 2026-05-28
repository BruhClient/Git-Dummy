from __future__ import annotations

import subprocess
from urllib.parse import urlparse

import requests

from .base_ops import _run, get_conflict_files, get_conflict_content


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


def push_branch(path: str, branch: str) -> tuple[bool, str, list, dict]:
    r = subprocess.run(
        ["git", "push", "-u", "origin", branch],
        cwd=path, capture_output=True, text=True, timeout=60,
    )
    if r.returncode == 0:
        return True, "", [], {}

    # git puts [rejected] / non-fast-forward in stdout; errors in stderr
    combined = (r.stdout + r.stderr).lower()

    if "non-fast-forward" in combined or "rejected" in combined:
        ok2, err2 = _run(path, ["git", "fetch", "origin"], timeout=30)
        if not ok2:
            return False, err2, [], {}

        r3 = subprocess.run(
            ["git", "merge", f"origin/{branch}"],
            cwd=path, capture_output=True, text=True, timeout=30,
        )
        if r3.returncode != 0:
            combined3 = (r3.stdout + r3.stderr).lower()
            conflict_files = get_conflict_files(path)
            content = {f: get_conflict_content(path, f) for f in conflict_files}
            subprocess.run(["git", "merge", "--abort"],
                           cwd=path, capture_output=True, text=True, timeout=10)
            if "conflict" in combined3:
                return False, "merge_conflict", conflict_files, content
            return False, r3.stderr.strip() or r3.stdout.strip(), [], {}

        ok4, err4 = _run(path, ["git", "push", "-u", "origin", branch], timeout=60)
        return ok4, err4, [], {}

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
        subprocess.run(["git", "config", "user.email", user_email or "user@gitdummy.local"],   cwd=path)

        # Stage and commit if no commits yet
        log = subprocess.run(
            ["git", "log", "--oneline", "-1"],
            cwd=path, capture_output=True,
        )
        if log.returncode != 0 or not log.stdout.strip():
            run("git", "add", ".")
            run("git", "commit", "--allow-empty", "-m", "Initial commit")

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

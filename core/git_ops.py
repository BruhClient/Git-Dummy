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


def get_stash_files(path: str, stash_id: str = "") -> list[str]:
    ref = ""
    if stash_id:
        r = subprocess.run(
            ["git", "stash", "list"],
            cwd=path, capture_output=True, text=True,
        )
        for line in r.stdout.strip().splitlines():
            if stash_id in line:
                ref = line.split(":")[0].strip()
                break
    args = ["git", "stash", "show", "--name-only"]
    if ref:
        args.append(ref)
    r = subprocess.run(args, cwd=path, capture_output=True, text=True)
    if r.returncode != 0:
        return []
    return [f.strip() for f in r.stdout.strip().splitlines() if f.strip()]


def create_auto_stash(path: str) -> tuple[list[str], str]:
    """Stash uncommitted changes. Returns (stashed_files, stash_id) or ([], '') on failure."""
    import uuid
    stash_id = "gitdummy-autostash-" + uuid.uuid4().hex[:8]

    # Try with untracked files first, fall back to tracked-only if that fails.
    for cmd in [
        ["git", "stash", "push", "--include-untracked", "-m", stash_id],
        ["git", "stash", "push", "-m", stash_id],
    ]:
        r = subprocess.run(cmd, cwd=path, capture_output=True, text=True)
        output = r.stdout + r.stderr
        if r.returncode == 0 and "No local changes" not in output:
            return get_stash_files(path), stash_id

    return [], ""


def pop_auto_stash(path: str, stash_id: str = "") -> bool:
    if stash_id:
        r = subprocess.run(
            ["git", "stash", "list"],
            cwd=path, capture_output=True, text=True,
        )
        for line in r.stdout.strip().splitlines():
            if stash_id in line:
                ref = line.split(":")[0].strip()
                r2 = subprocess.run(
                    ["git", "stash", "pop", ref],
                    cwd=path, capture_output=True, text=True,
                )
                return r2.returncode == 0
        return False
    r = subprocess.run(
        ["git", "stash", "pop"],
        cwd=path, capture_output=True, text=True,
    )
    return r.returncode == 0


def apply_stash(path: str, stash_ref: str) -> bool:
    """Apply a stash to the working directory without removing it from the stash list."""
    r = subprocess.run(
        ["git", "stash", "apply", stash_ref],
        cwd=path, capture_output=True, text=True,
    )
    return r.returncode == 0


def drop_stash(path: str, stash_ref: str) -> bool:
    """Remove a stash entry from the stash list without applying it."""
    r = subprocess.run(
        ["git", "stash", "drop", stash_ref],
        cwd=path, capture_output=True, text=True,
    )
    return r.returncode == 0


def reset_hard(path: str) -> bool:
    """Reset index and working tree to HEAD, aborting any partial stash apply."""
    r = subprocess.run(
        ["git", "reset", "--hard", "HEAD"],
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


def get_stash_ref_for_commit(path: str, commit_sha: str) -> str:
    """Return the stash ref (e.g. 'stash@{0}') whose parent is commit_sha, or ''."""
    r = subprocess.run(
        ["git", "stash", "list", "--format=%gd %P"],
        cwd=path, capture_output=True, text=True,
    )
    for line in r.stdout.strip().splitlines():
        parts = line.strip().split()
        if len(parts) >= 2 and parts[1] == commit_sha:
            return parts[0]
    return ""


def get_stash_diff_files(path: str, stash_ref: str) -> list[dict]:
    """Return per-file diff info for a stash, in the same format as commit_files."""
    r = subprocess.run(
        ["git", "show", "--format=", "--numstat", stash_ref],
        cwd=path, capture_output=True, text=True,
    )
    patch = subprocess.run(
        ["git", "stash", "show", "-p", stash_ref],
        cwd=path, capture_output=True, text=True,
    )

    # Build a map of file path → diff lines from the patch
    diff_by_path: dict[str, list] = {}
    current: list = []
    current_path = ""
    for line in patch.stdout.splitlines():
        if line.startswith("diff --git "):
            if current_path:
                diff_by_path[current_path] = current
            current = []
            current_path = ""
        elif line.startswith("+++ b/"):
            current_path = line[6:]
        elif line.startswith("--- a/") or line.startswith("+++ /dev/null"):
            pass
        elif current_path:
            if line.startswith("+") and not line.startswith("+++"):
                current.append(("added",   line[1:]))
            elif line.startswith("-") and not line.startswith("---"):
                current.append(("removed", line[1:]))
            elif line.startswith("@@"):
                current.append(("hunk",    line))
            elif line.startswith(" "):
                current.append(("context", line[1:]))
    if current_path:
        diff_by_path[current_path] = current

    result = []
    for line in r.stdout.strip().splitlines():
        if not line.strip():
            continue
        parts = line.split("\t")
        if len(parts) < 3:
            continue
        ins_s, dels_s, fpath = parts[0], parts[1], parts[2]
        is_binary = ins_s == "-"
        try:
            ins  = int(ins_s)  if not is_binary else 0
            dels = int(dels_s) if not is_binary else 0
        except ValueError:
            ins = dels = 0
        lines = diff_by_path.get(fpath, [])
        result.append({
            "path":       fpath,
            "name":       fpath.split("/")[-1],
            "status":     "modified",
            "insertions": ins,
            "deletions":  dels,
            "is_binary":  is_binary,
            "lines":      lines,
        })
    return result


def get_working_dir_diff_files(path: str) -> list[dict]:
    """Return per-file diff info for the current dirty working directory (staged + unstaged)."""
    import os as _os
    r = subprocess.run(
        ["git", "diff", "HEAD", "--numstat"],
        cwd=path, capture_output=True, text=True,
    )
    patch = subprocess.run(
        ["git", "diff", "HEAD"],
        cwd=path, capture_output=True, text=True,
    )

    diff_by_path: dict[str, list] = {}
    current: list = []
    current_path = ""
    for line in patch.stdout.splitlines():
        if line.startswith("diff --git "):
            if current_path:
                diff_by_path[current_path] = current
            current = []
            current_path = ""
        elif line.startswith("+++ b/"):
            current_path = line[6:]
        elif line.startswith("--- a/") or line.startswith("+++ /dev/null"):
            pass
        elif current_path:
            if line.startswith("+") and not line.startswith("+++"):
                current.append(("added",   line[1:]))
            elif line.startswith("-") and not line.startswith("---"):
                current.append(("removed", line[1:]))
            elif line.startswith("@@"):
                current.append(("hunk",    line))
            elif line.startswith(" "):
                current.append(("context", line[1:]))
    if current_path:
        diff_by_path[current_path] = current

    result = []
    seen_paths: set[str] = set()

    for line in r.stdout.strip().splitlines():
        if not line.strip():
            continue
        parts = line.split("\t")
        if len(parts) < 3:
            continue
        ins_s, dels_s, fpath = parts[0], parts[1], parts[2]
        is_binary = ins_s == "-"
        try:
            ins  = int(ins_s)  if not is_binary else 0
            dels = int(dels_s) if not is_binary else 0
        except ValueError:
            ins = dels = 0
        status = "deleted" if dels > 0 and ins == 0 else "modified"
        result.append({
            "path":       fpath,
            "name":       fpath.split("/")[-1],
            "status":     status,
            "insertions": ins,
            "deletions":  dels,
            "is_binary":  is_binary,
            "lines":      diff_by_path.get(fpath, []),
        })
        seen_paths.add(fpath)

    # Include untracked (new) files that git diff HEAD misses entirely
    untracked = subprocess.run(
        ["git", "ls-files", "--others", "--exclude-standard"],
        cwd=path, capture_output=True, text=True,
    )
    for fpath in untracked.stdout.strip().splitlines():
        fpath = fpath.strip()
        if not fpath or fpath in seen_paths:
            continue
        abs_path = _os.path.join(path, fpath.replace("/", _os.sep))
        lines: list = []
        ins = 0
        is_binary = False
        try:
            with open(abs_path, "r", encoding="utf-8", errors="replace") as f:
                for i, raw in enumerate(f):
                    if i >= 500:
                        break
                    lines.append(("added", raw.rstrip("\n")))
                    ins += 1
        except Exception:
            is_binary = True
        result.append({
            "path":       fpath,
            "name":       fpath.split("/")[-1],
            "status":     "added",
            "insertions": ins,
            "deletions":  0,
            "is_binary":  is_binary,
            "lines":      lines,
        })

    return result


def get_stash_commit_shas(path: str) -> set[str]:
    """Return the set of commit SHAs that have a stash sitting on top of them."""
    r = subprocess.run(
        ["git", "stash", "list", "--format=%P"],
        cwd=path, capture_output=True, text=True,
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
        cwd=path, capture_output=True, text=True,
    )
    return r.stdout.strip()


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

from __future__ import annotations

import os
import subprocess

from .base_ops import _POPEN_FLAGS


def _parse_patch_to_diff_by_path(patch_stdout: str) -> dict[str, list]:
    """Parse unified-diff patch text into {file path: [(kind, text), ...]}."""
    diff_by_path: dict[str, list] = {}
    current: list = []
    current_path = ""
    for line in (patch_stdout or "").splitlines():
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
    return diff_by_path


def get_stash_diff_files(path: str, stash_ref: str) -> list[dict]:
    """Return per-file diff info for a stash, in the same format as commit_files."""
    r = subprocess.run(
        ["git", "show", "--format=", "--numstat", stash_ref],
        cwd=path, capture_output=True, text=True,
        encoding="utf-8", errors="replace", creationflags=_POPEN_FLAGS,
    )
    patch = subprocess.run(
        ["git", "stash", "show", "-p", stash_ref],
        cwd=path, capture_output=True, text=True,
        encoding="utf-8", errors="replace", creationflags=_POPEN_FLAGS,
    )

    # Build a map of file path → diff lines from the patch
    diff_by_path = _parse_patch_to_diff_by_path(patch.stdout)

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
    r = subprocess.run(
        ["git", "diff", "HEAD", "--numstat"],
        cwd=path, capture_output=True, text=True,
        encoding="utf-8", errors="replace", creationflags=_POPEN_FLAGS,
    )
    patch = subprocess.run(
        ["git", "diff", "HEAD"],
        cwd=path, capture_output=True, text=True,
        encoding="utf-8", errors="replace", creationflags=_POPEN_FLAGS,
    )

    diff_by_path = _parse_patch_to_diff_by_path(patch.stdout)

    result = []
    seen_paths: set[str] = set()

    for line in (r.stdout or "").strip().splitlines():
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
        # numstat alone can't distinguish "file deleted" from "only lines
        # removed" (both show dels > 0, ins == 0) — check the working tree.
        abs_path = os.path.join(path, fpath.replace("/", os.sep))
        status = "deleted" if (dels > 0 and ins == 0 and not os.path.exists(abs_path)) else "modified"
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
        encoding="utf-8", errors="replace", creationflags=_POPEN_FLAGS,
    )
    for fpath in untracked.stdout.strip().splitlines():
        fpath = fpath.strip()
        if not fpath or fpath in seen_paths:
            continue
        abs_path = os.path.join(path, fpath.replace("/", os.sep))
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

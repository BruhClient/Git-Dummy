from __future__ import annotations

import subprocess

from .base_ops import _run, get_conflict_files, get_conflict_content


def merge_branch(path: str, source_branch: str) -> tuple[bool, str, list, dict]:
    """Merge source_branch into the currently checked-out branch.
    On conflict: reads content while markers are present, aborts, returns content for dialog."""
    r = subprocess.run(
        ["git", "merge", "--no-ff", source_branch],
        cwd=path, capture_output=True, text=True, timeout=60,
    )
    if r.returncode == 0:
        combined = (r.stdout + r.stderr).lower()
        if "already up to date" in combined:
            return True, "already_up_to_date", [], {}
        return True, "", [], {}
    err = r.stderr.strip() or r.stdout.strip()
    if "conflict" in err.lower() or "CONFLICT" in err:
        files = get_conflict_files(path)
        # Capture content NOW — markers still present in files
        content = {f: get_conflict_content(path, f) for f in files}
        # Abort so VSCode files go back to clean state
        subprocess.run(["git", "merge", "--abort"],
                       cwd=path, capture_output=True, text=True, timeout=10)
        return False, "merge_conflict", files, content
    subprocess.run(["git", "merge", "--abort"],
                   cwd=path, capture_output=True, text=True, timeout=10)
    return False, err, [], {}


def merge_with_decisions(path: str, source_branch: str, decisions: dict) -> tuple[bool, str]:
    """Re-merge then apply per-file ours/theirs decisions, then commit."""
    ok_m, err_m = _run(path, ["git", "merge", "--no-ff", "--no-commit", source_branch], timeout=60)
    # If the merge failed for a non-conflict reason (e.g. branch deleted), surface the real error.
    if not ok_m and "conflict" not in err_m.lower():
        return False, err_m
    # Apply per-file decisions regardless of whether merge itself had conflicts.
    all_ok = True
    for filepath, choice in decisions.items():
        flag = "--ours" if choice == "ours" else "--theirs"
        ok_f, _ = _run(path, ["git", "checkout", flag, filepath])
        if ok_f:
            _run(path, ["git", "add", filepath])
        else:
            all_ok = False
    if not all_ok:
        subprocess.run(["git", "merge", "--abort"],
                       cwd=path, capture_output=True, text=True, timeout=10)
        return False, "Could not apply all file decisions — merge aborted."
    ok2, err2 = _run(path, ["git", "commit", "--no-edit"], timeout=30)
    if not ok2:
        subprocess.run(["git", "merge", "--abort"],
                       cwd=path, capture_output=True, text=True, timeout=10)
    return ok2, err2


def merge_use_theirs(path: str, source_branch: str) -> tuple[bool, str]:
    """Re-merge using theirs (-X theirs) strategy — no conflict markers in files."""
    ok, err = _run(path, ["git", "merge", "--no-ff", "-X", "theirs", source_branch], timeout=60)
    return ok, err


def merge_use_ours(path: str, source_branch: str) -> tuple[bool, str]:
    """Re-merge using ours (-X ours) strategy — no conflict markers in files."""
    ok, err = _run(path, ["git", "merge", "--no-ff", "-X", "ours", source_branch], timeout=60)
    return ok, err


def merge_abort(path: str) -> tuple[bool, str]:
    return _run(path, ["git", "merge", "--abort"])


def conflict_discard_local(path: str, branch: str) -> tuple[bool, str]:
    """Discard local commits, reset to remote, force-push."""
    for cmd in (["git", "fetch", "origin"],
                ["git", "reset", "--hard", f"origin/{branch}"]):
        ok, err = _run(path, cmd)
        if not ok:
            return False, err
    return _run(path, ["git", "push", "--force", "origin", branch], timeout=60)


def conflict_keep_local(path: str, branch: str) -> tuple[bool, str]:
    """Re-apply local file changes on top of remote as a single new commit, then push."""
    try:
        diff_r = subprocess.run(
            ["git", "diff", f"origin/{branch}...HEAD"],
            cwd=path, capture_output=True, text=True, timeout=30,
        )
        patch = diff_r.stdout
    except Exception as e:
        return False, str(e)

    # Remember where we are so we can roll back if apply fails after the reset.
    saved_r = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=path, capture_output=True, text=True, timeout=5,
    )
    saved_sha = saved_r.stdout.strip()

    for cmd in (["git", "fetch", "origin"],
                ["git", "reset", "--hard", f"origin/{branch}"]):
        ok, err = _run(path, cmd)
        if not ok:
            return False, err

    if patch.strip():
        try:
            r = subprocess.run(
                ["git", "apply", "--whitespace=fix"],
                input=patch, cwd=path, capture_output=True, text=True, timeout=30,
            )
            if r.returncode != 0:
                # Apply failed — restore to our pre-reset state so no local work is lost.
                if saved_sha:
                    subprocess.run(
                        ["git", "reset", "--hard", saved_sha],
                        cwd=path, capture_output=True, text=True, timeout=10,
                    )
                return False, (r.stderr.strip() or r.stdout.strip() or
                               "Could not re-apply local changes after syncing to remote.")
        except Exception as e:
            if saved_sha:
                subprocess.run(
                    ["git", "reset", "--hard", saved_sha],
                    cwd=path, capture_output=True, text=True, timeout=10,
                )
            return False, str(e)
        for cmd in (["git", "add", "-A"],
                    ["git", "commit", "-m", "local changes on top of remote"]):
            ok, err = _run(path, cmd)
            if not ok:
                return False, err

    return _run(path, ["git", "push", "-u", "origin", branch], timeout=60)


def check_pr_conflicts(path: str, feature_branch: str,
                       target_branch: str = "main") -> tuple[bool, list, dict]:
    """
    Dry-run merge check using git merge-tree.
    Returns (has_conflicts, conflict_files, conflict_content).
    Never modifies the working tree.
    """
    try:
        # Fetch latest from remote so we're comparing current state
        subprocess.run(["git", "fetch", "origin"],
                       cwd=path, capture_output=True, text=True, timeout=30)

        # Resolve remote refs
        feat_ref   = f"origin/{feature_branch}"
        target_ref = f"origin/{target_branch}"

        # Find the merge base
        base_r = subprocess.run(
            ["git", "merge-base", target_ref, feat_ref],
            cwd=path, capture_output=True, text=True, timeout=10,
        )
        if base_r.returncode != 0:
            # No common ancestor — treat as no conflicts (GitHub will decide)
            return False, [], {}
        base_sha = base_r.stdout.strip()
        if not base_sha:
            return False, [], {}

        # Dry-run merge
        tree_r = subprocess.run(
            ["git", "merge-tree", base_sha, target_ref, feat_ref],
            cwd=path, capture_output=True, text=True, timeout=15,
        )
        output = tree_r.stdout
        if "<<<<<<<" not in output:
            return False, [], {}

        # Parse conflicting files and capture content
        conflict_files: list[str] = []
        conflict_content: dict    = {}
        current_file: str | None  = None
        current_lines: list[str]  = []

        for line in output.splitlines():
            if line.startswith("changed in both") or \
               line.startswith("+++ ") or line.startswith("--- "):
                # merge-tree section header — extract filename
                if line.startswith("+++ ") or line.startswith("--- "):
                    fname = line[4:].strip().lstrip("b/")
                    if fname and fname not in conflict_files:
                        if current_file and current_lines:
                            conflict_content[current_file] = "\n".join(current_lines)
                        current_file = fname
                        current_lines = []
                        conflict_files.append(fname)
            else:
                if current_file is not None:
                    current_lines.append(line)

        if current_file and current_lines:
            conflict_content[current_file] = "\n".join(current_lines)

        # Fallback: if we detected conflict markers but no filenames parsed
        if not conflict_files and "<<<<<<<" in output:
            return True, ["(unknown files — check manually)"], {}

        return bool(conflict_files), conflict_files, conflict_content

    except Exception:
        return False, [], {}


def merge_pr_locally(path: str, feature_branch: str, target_branch: str,
                     decisions: dict) -> tuple[bool, str]:
    """
    After the user resolves conflicts in _MergeConflictDialog, merge the
    feature branch into target_branch locally and push.

    decisions: {filepath: "ours"|"theirs"} from the conflict dialog.
    Returns (ok, err).
    """
    try:
        # Checkout target branch
        cur_r = subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            cwd=path, capture_output=True, text=True, timeout=5,
        )
        current = cur_r.stdout.strip()
        if current != target_branch:
            ok, err = _run(path, ["git", "checkout", target_branch])
            if not ok:
                return False, f"Could not checkout {target_branch}: {err}"

        # Pull latest target
        _run(path, ["git", "pull", "--ff-only", "origin", target_branch], timeout=30)

        # Attempt merge with no-commit to apply decisions
        _run(path, ["git", "merge", "--no-ff", "--no-commit", feature_branch], timeout=60)

        # Apply per-file decisions
        for filepath, choice in decisions.items():
            flag = "--ours" if choice == "ours" else "--theirs"
            ok_f, _ = _run(path, ["git", "checkout", flag, filepath])
            if ok_f:
                _run(path, ["git", "add", filepath])

        # Commit the merge
        ok_c, err_c = _run(
            path,
            ["git", "commit", "--no-edit", "-m",
             f"Merge branch '{feature_branch}' into {target_branch}"],
            timeout=30,
        )
        if not ok_c:
            subprocess.run(["git", "merge", "--abort"],
                           cwd=path, capture_output=True, text=True, timeout=10)
            return False, err_c

        # Push target branch
        ok_p, err_p = _run(path, ["git", "push", "origin", target_branch], timeout=60)
        if not ok_p:
            return False, f"Merged locally but push failed: {err_p}"

        return True, ""
    except Exception as e:
        try:
            subprocess.run(["git", "merge", "--abort"],
                           cwd=path, capture_output=True, text=True, timeout=10)
        except Exception:
            pass
        return False, str(e)

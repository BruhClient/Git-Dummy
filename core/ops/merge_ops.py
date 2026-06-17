from __future__ import annotations

import os
import subprocess
import tempfile

from .base_ops import _run, get_conflict_files, get_conflict_content, parse_conflict_markers


def merge_branch(path: str, source_branch: str) -> tuple[bool, str, list, dict]:
    """Merge source_branch into the currently checked-out branch.
    On conflict: reads content while markers are present, aborts, returns content for dialog."""
    r = subprocess.run(
        ["git", "merge", "--no-ff", source_branch],
        cwd=path, capture_output=True, text=True, timeout=60,
        encoding="utf-8", errors="replace",
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
                       cwd=path, capture_output=True, text=True, timeout=10,
                       encoding="utf-8", errors="replace")
        return False, "merge_conflict", files, content
    subprocess.run(["git", "merge", "--abort"],
                   cwd=path, capture_output=True, text=True, timeout=10,
                   encoding="utf-8", errors="replace")
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
        ls = subprocess.run(
            ["git", "ls-files", "--unmerged", filepath],
            cwd=path, capture_output=True, text=True, timeout=5,
            encoding="utf-8", errors="replace",
        )
        if ls.stdout.strip():
            # Parse which stages are present (1=base, 2=ours, 3=theirs).
            # modify/delete conflicts are missing stage 2 (we deleted) or stage 3 (they deleted).
            stages = {int(line.split()[2]) for line in ls.stdout.strip().splitlines() if line.strip()}
            if choice == "ours":
                if 2 not in stages:
                    # We deleted this file — remove it from the index
                    _run(path, ["git", "rm", "--cached", filepath])
                else:
                    ok_f, _ = _run(path, ["git", "checkout", "--ours", filepath])
                    if not ok_f:
                        all_ok = False
                        continue
                    _run(path, ["git", "add", filepath])
            else:
                if 3 not in stages:
                    # They deleted this file — remove it
                    _run(path, ["git", "rm", "--cached", filepath])
                else:
                    ok_f, _ = _run(path, ["git", "checkout", "--theirs", filepath])
                    if not ok_f:
                        all_ok = False
                        continue
                    _run(path, ["git", "add", filepath])
        else:
            _run(path, ["git", "add", filepath])
    if not all_ok:
        subprocess.run(["git", "merge", "--abort"],
                       cwd=path, capture_output=True, text=True, timeout=10,
                       encoding="utf-8", errors="replace")
        return False, "Could not apply all file decisions — merge aborted."
    ok2, err2 = _run(path, ["git", "commit", "--no-edit"], timeout=30)
    if not ok2:
        subprocess.run(["git", "merge", "--abort"],
                       cwd=path, capture_output=True, text=True, timeout=10,
                       encoding="utf-8", errors="replace")
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
            encoding="utf-8", errors="replace",
        )
        patch = diff_r.stdout
    except Exception as e:
        return False, str(e)

    # Remember where we are so we can roll back if apply fails after the reset.
    saved_r = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=path, capture_output=True, text=True, timeout=5,
        encoding="utf-8", errors="replace",
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
                encoding="utf-8", errors="replace",
            )
            if r.returncode != 0:
                # Apply failed — restore to our pre-reset state so no local work is lost.
                if saved_sha:
                    subprocess.run(
                        ["git", "reset", "--hard", saved_sha],
                        cwd=path, capture_output=True, text=True, timeout=10,
                        encoding="utf-8", errors="replace",
                    )
                return False, (r.stderr.strip() or r.stdout.strip() or
                               "Could not re-apply local changes after syncing to remote.")
        except Exception as e:
            if saved_sha:
                subprocess.run(
                    ["git", "reset", "--hard", saved_sha],
                    cwd=path, capture_output=True, text=True, timeout=10,
                    encoding="utf-8", errors="replace",
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
    Dry-run merge check using a disposable index (`git read-tree -m`).
    Returns (has_conflicts, conflict_files, conflict_content).
    Never modifies the working tree or the repo's real index.
    """
    try:
        # Fetch latest from remote so we're comparing current state
        subprocess.run(["git", "fetch", "origin"],
                       cwd=path, capture_output=True, text=True, timeout=30,
                       encoding="utf-8", errors="replace")

        # Resolve remote refs
        feat_ref   = f"origin/{feature_branch}"
        target_ref = f"origin/{target_branch}"

        # Find the merge base
        base_r = subprocess.run(
            ["git", "merge-base", target_ref, feat_ref],
            cwd=path, capture_output=True, text=True, timeout=10,
            encoding="utf-8", errors="replace",
        )
        if base_r.returncode != 0:
            # No common ancestor — treat as no conflicts (GitHub will decide)
            return False, [], {}
        base_sha = base_r.stdout.strip()
        if not base_sha:
            return False, [], {}

        # ── Reliable conflict + filename detection ──────────────────────────
        # Perform the 3-way merge into a disposable index (via GIT_INDEX_FILE)
        # so conflicted paths can be read back with `git ls-files --unmerged`
        # — a stable, well-documented format — instead of string-matching
        # `git merge-tree`'s plain-text diff output, whose section headers
        # vary across git versions.
        conflict_files: list[str] = []
        stages: dict[str, dict[str, str]] = {}

        fd, tmp_index = tempfile.mkstemp(prefix="evogit-merge-check-")
        os.close(fd)
        os.remove(tmp_index)  # let `git read-tree` create a fresh index here
        try:
            env = os.environ.copy()
            env["GIT_INDEX_FILE"] = tmp_index

            subprocess.run(
                ["git", "read-tree", "-m", base_sha, target_ref, feat_ref],
                cwd=path, env=env, capture_output=True, text=True, timeout=15,
                encoding="utf-8", errors="replace",
            )
            ls = subprocess.run(
                ["git", "ls-files", "--unmerged"],
                cwd=path, env=env, capture_output=True, text=True, timeout=10,
                encoding="utf-8", errors="replace",
            )
            for line in ls.stdout.strip().splitlines():
                # format: "<mode> <object> <stage>\t<path>"
                meta, _, fname = line.partition("\t")
                parts = meta.split()
                if len(parts) != 3 or not fname:
                    continue
                _mode, oid, stage = parts
                if fname not in stages:
                    stages[fname] = {}
                    conflict_files.append(fname)
                stages[fname][stage] = oid
        finally:
            if os.path.exists(tmp_index):
                try:
                    os.remove(tmp_index)
                except OSError:
                    pass

        if not conflict_files:
            return False, [], {}

        # ── Best-effort inline diff content for the conflict dialog ─────────
        # For each conflicting file, reconstruct the diff3 conflict-marker
        # text via `git merge-file -p` from the base/ours/theirs blobs in the
        # disposable index. If a file is missing one of the blobs (e.g. an
        # add/add or modify/delete conflict), it's left out of
        # conflict_content — the dialog falls back to an empty preview for
        # that file, but the (reliable) filename is still surfaced above.
        conflict_content: dict = {}
        for fname, blobs in stages.items():
            ours_oid, theirs_oid, base_oid = blobs.get("2"), blobs.get("3"), blobs.get("1")
            if not (ours_oid and theirs_oid):
                continue
            tmpdir = tempfile.mkdtemp(prefix="evogit-merge-check-")
            try:
                def _write_blob(oid: str | None, name: str) -> str:
                    dest = os.path.join(tmpdir, name)
                    if oid:
                        cat = subprocess.run(["git", "cat-file", "blob", oid],
                                              cwd=path, capture_output=True, timeout=10)
                        data = cat.stdout
                    else:
                        data = b""
                    with open(dest, "wb") as f:
                        f.write(data)
                    return dest

                ours_f   = _write_blob(ours_oid, "ours")
                theirs_f = _write_blob(theirs_oid, "theirs")
                base_f   = _write_blob(base_oid, "base")

                mf = subprocess.run(
                    ["git", "merge-file", "-p", ours_f, base_f, theirs_f],
                    capture_output=True, text=True, timeout=10,
                    encoding="utf-8", errors="replace",
                )
                orig, orig_start, inc, inc_start = parse_conflict_markers(
                    mf.stdout.splitlines(keepends=True)
                )
                if orig or inc:
                    conflict_content[fname] = (orig, orig_start, inc, inc_start)
            except Exception:
                pass  # conflict_files stays authoritative; content is best-effort
            finally:
                import shutil
                shutil.rmtree(tmpdir, ignore_errors=True)

        return True, conflict_files, conflict_content

    except Exception:
        # Could not determine conflict status reliably — fail safe (assume a
        # conflict so the user is shown the conflict dialog) rather than
        # silently letting a possibly-conflicting merge go straight to the
        # GitHub API merge call.
        return True, ["(unknown — could not verify, check manually)"], {}


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
            encoding="utf-8", errors="replace",
        )
        current = cur_r.stdout.strip()
        if current != target_branch:
            ok, err = _run(path, ["git", "checkout", target_branch])
            if not ok:
                return False, f"Could not checkout {target_branch}: {err}"

        # Pull latest target — must succeed (fast-forward only) before we merge
        # against it. If this fails (e.g. local target_branch has diverged from
        # origin), bail out now rather than merging onto a stale local tip and
        # then pushing over whatever is actually on origin/{target_branch}.
        ok_pull, err_pull = _run(path, ["git", "pull", "--ff-only", "origin", target_branch], timeout=30)
        if not ok_pull:
            return False, (
                f"Could not update local '{target_branch}' from origin "
                f"(it may have diverged) — aborted before merging: {err_pull}"
            )

        # Attempt merge with no-commit to apply decisions. A failure here is
        # only expected when it's a real conflict (which `decisions` resolves
        # below) — any other failure (e.g. feature branch missing) must abort
        # the merge and surface the real error instead of proceeding.
        ok_merge, err_merge = _run(path, ["git", "merge", "--no-ff", "--no-commit", feature_branch], timeout=60)
        if not ok_merge and "conflict" not in err_merge.lower():
            subprocess.run(["git", "merge", "--abort"],
                           cwd=path, capture_output=True, text=True, timeout=10,
                           encoding="utf-8", errors="replace")
            return False, err_merge

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
                           cwd=path, capture_output=True, text=True, timeout=10,
                           encoding="utf-8", errors="replace")
            return False, err_c

        # Push target branch
        ok_p, err_p = _run(path, ["git", "push", "origin", target_branch], timeout=60)
        if not ok_p:
            return False, f"Merged locally but push failed: {err_p}"

        return True, ""
    except Exception as e:
        try:
            subprocess.run(["git", "merge", "--abort"],
                           cwd=path, capture_output=True, text=True, timeout=10,
                           encoding="utf-8", errors="replace")
        except Exception:
            pass
        return False, str(e)

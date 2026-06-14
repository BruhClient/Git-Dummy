"""PR inbox + open-wizard + merge handlers for CommitViewPage.

This is a behavior-preserving mixin: the methods were moved verbatim out of
ui/commit_view.py to keep that module navigable. They reference only `self`
state (instance attributes, the PR-related pyqtSignals declared on
CommitViewPage, and helper methods such as `self._start_load`) plus names
imported locally inside each method, so the module needs no module-level
imports. `_PRMixin` must be listed before QWidget in CommitViewPage's bases
and must not define __init__. No behavior change.
"""
from __future__ import annotations


class _PRMixin:
    # ── PR Inbox loading ──────────────────────────────────────────────────────

    def _load_pr_inbox(self):
        """Load or refresh the PR inbox. Called when switching to Collaboration tab."""
        if not self._tracker:
            return
        login      = self._user.get("login", "")
        owner      = self._tracker.repo_owner()
        user_role  = self._collab_roles.get(login, "write")
        token      = self._user.get("access_token", "")

        self._pr_panel.update_commits(self._commits)
        if not self._pr_panel_loaded:
            self._pr_panel.load(self._tracker, self._user, user_role, token, self._commits)
            self._pr_panel_loaded = True
        else:
            self._pr_panel.set_user_role(user_role)

    # ── PR Open Wizard handlers ───────────────────────────────────────────────

    def _on_pr_open_requested(self, branch: str):
        """User clicked 'Open Pull Request' on a branch head."""
        if not self._tracker:
            return
        from core.ops import has_uncommitted_changes, get_uncommitted_files
        path         = self._tracker._path
        dirty_files  = []
        try:
            if has_uncommitted_changes(path):
                # Try to get file list; fall back gracefully
                try:
                    import subprocess
                    r = subprocess.run(
                        ["git", "status", "--porcelain"],
                        cwd=path, capture_output=True, text=True,
                    )
                    dirty_files = [l[3:].strip() for l in r.stdout.splitlines() if l.strip()]
                except Exception:
                    dirty_files = ["(modified files)"]
        except Exception:
            pass

        default_branch = getattr(self._settings_panel, "_default_branch", "main")
        self._pr_wizard.start(branch, default_branch, dirty_files, already_pushed=False)

    def _on_wizard_commit(self, branch: str, message: str):
        """Wizard Step 1: user wants to commit unsaved changes."""
        if not self._tracker:
            return
        path = self._tracker._path
        def _run():
            try:
                import subprocess
                subprocess.run(["git", "add", "-A"], cwd=path, capture_output=True, timeout=10)
                subprocess.run(
                    ["git", "commit", "-m", message],
                    cwd=path, capture_output=True, text=True, timeout=30,
                )
                ok, err = True, ""
            except Exception as e:
                ok, err = False, str(e)
            self._wizard_commit_done_sig.emit(ok, err)
        import threading as _threading
        _threading.Thread(target=_run, daemon=True).start()

    def _on_wizard_discard(self, branch: str):
        """Wizard Step 1: user wants to discard changes."""
        if not self._tracker:
            return
        path = self._tracker._path
        def _run():
            try:
                from core.ops import discard_all_changes
                ok, err = discard_all_changes(path)
            except Exception as e:
                ok, err = False, str(e)
            self._wizard_commit_done_sig.emit(ok, err)
        import threading as _threading
        _threading.Thread(target=_run, daemon=True).start()

    def _on_wizard_push(self, branch: str):
        """Wizard Step 2: push branch."""
        if not self._tracker:
            return
        path       = self._tracker._path
        username   = self._user.get("login", "")
        token      = self._user.get("access_token", "")
        remote_url = self._tracker.remote_url() if self._tracker else ""
        def _run():
            try:
                from core.ops import push_branch
                ok, err, _cf, _cc = push_branch(path, branch, username, token, remote_url)
            except Exception as e:
                ok, err = False, str(e)
            self._wizard_push_done_sig.emit(ok, err)
        import threading as _threading
        _threading.Thread(target=_run, daemon=True).start()

    def _on_wizard_pr_submit(self, branch: str, title: str, body: str, base: str):
        """Wizard Step 3: call GitHub API to create the PR."""
        if not self._tracker:
            return
        token = self._user.get("access_token", "")
        url   = self._tracker.remote_url()
        import re as _re
        m = _re.search(r'github\.com[:/]([^/]+)/([^/]+?)(?:\.git)?$', url)
        if not m or not token:
            self._pr_wizard.notify_pr_created(False, "No GitHub remote or token.")
            return
        owner, repo = m.group(1), m.group(2)

        def _run():
            try:
                import requests as _req
                r = _req.post(
                    f"https://api.github.com/repos/{owner}/{repo}/pulls",
                    json={"title": title, "body": body, "head": branch, "base": base},
                    headers={"Authorization": f"Bearer {token}",
                             "Accept": "application/vnd.github+json"},
                    timeout=15,
                )
                ok  = r.status_code in (200, 201)
                err = "" if ok else r.json().get("message", str(r.status_code))
            except Exception as e:
                ok, err = False, str(e)
            self._wizard_pr_done_sig.emit(ok, err)
        import threading as _threading
        _threading.Thread(target=_run, daemon=True).start()

    # ── PR Merge handler (from inbox) ─────────────────────────────────────────

    def _on_pr_merge_requested(self, pr: dict):
        """User clicked Merge on a PR row. Check for conflicts first."""
        if not self._tracker:
            return
        feature_branch = (pr.get("head") or {}).get("ref", "")
        target_branch  = (pr.get("base") or {}).get("ref", "main")
        path           = self._tracker._path

        self._toast.show_message("Checking for conflicts…", kind="loading")

        def _run():
            try:
                from core.ops import check_pr_conflicts
                has_conflicts, files, content = check_pr_conflicts(
                    path, feature_branch, target_branch
                )
            except Exception as e:
                has_conflicts, files, content = False, [], {}
            self._pr_conflict_check_sig.emit(has_conflicts, files, content, pr)
        import threading as _threading
        _threading.Thread(target=_run, daemon=True).start()

    def _on_pr_conflict_check(self, has_conflicts: bool, files: list,
                               content: object, pr: dict):
        if has_conflicts:
            # Show the existing merge conflict dialog
            source = (pr.get("head") or {}).get("ref", "?")
            target = (pr.get("base") or {}).get("ref", "main")
            self._pending_merge_pr = pr
            self._merge_conflict_dialog.show_for_conflict(
                source, target, files, prefetched_content=content or {}
            )
        else:
            # No conflicts — merge directly via GitHub API
            self._pr_panel.merge_via_api(pr)

    # ── PR Wizard done handlers (main thread) ─────────────────────────────────

    def _on_wizard_commit_done(self, ok: bool, err: str):
        if ok:
            self._pr_wizard.notify_commit_done()
            self._start_load()   # refresh graph
        else:
            self._pr_wizard.notify_push_done(False, f"Commit failed: {err}")

    def _on_wizard_push_done(self, ok: bool, err: str):
        if ok and err == "merged_before_push":
            # push_branch() pulled in new commits from origin and merged them
            # locally before the push succeeded — surface that so the user
            # isn't surprised by an extra merge commit. notify_push_done()
            # below ignores `err` on success, so this toast is the only
            # place this is communicated.
            self._toast.show_message(
                "Origin had new commits — merged automatically, then pushed.",
                kind="info", duration_ms=6000)
        self._pr_wizard.notify_push_done(ok, err)
        if ok:
            self._start_load()

    def _on_wizard_pr_done(self, ok: bool, err: str):
        self._pr_wizard.notify_pr_created(ok, err)
        if ok:
            # Switch to Collaboration tab so user sees their new PR.
            # _select emits tab_changed → _switch_tab → _load_pr_inbox.
            self._pr_panel_loaded = False   # force fresh fetch
            self._tab_bar._select("collaboration")

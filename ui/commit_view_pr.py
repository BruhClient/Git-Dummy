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
        token = self._user.get("access_token", "")

        self._pr_panel.update_commits(self._commits)
        if not self._pr_panel_loaded:
            self._pr_panel.load(self._tracker, self._user, token, self._commits)
            self._pr_panel_loaded = True

    # ── PR Open Wizard handlers ───────────────────────────────────────────────

    def _on_pr_open_requested(self, branch: str):
        """User clicked 'Open Pull Request' on a branch head."""
        if not self._tracker:
            return
        if self._last_dirty:
            self._toast.show_message(
                "Commit or discard your changes before opening a PR.", kind="error"
            )
            return
        default_branch = getattr(self._settings_panel, "_default_branch", "main")
        self._pr_wizard.start(branch, default_branch)

    def _on_wizard_push(self, branch: str):
        """Wizard Step 1: push branch."""
        if not self._tracker:
            return
        self._panel_op_active = True
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
        """Wizard Step 2: call GitHub API to create the PR."""
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
        self._panel_op_active = True
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
                self._pr_conflict_check_sig.emit(has_conflicts, files, content, pr)
            except Exception as e:
                self._pr_conflict_check_err_sig.emit(str(e))
        import threading as _threading
        _threading.Thread(target=_run, daemon=True).start()

    def _on_pr_conflict_check_err(self, err: str):
        self._panel_op_active = False
        self._toast.show_message(f"Conflict check failed: {err}", kind="error")

    def _on_pr_conflict_check(self, has_conflicts: bool, files: list,
                               content: object, pr: dict):
        if has_conflicts:
            source = (pr.get("head") or {}).get("ref", "?")
            target = (pr.get("base") or {}).get("ref", "main")
            self._pending_merge_pr = pr
            self._panel_op_active = False
            self._merge_conflict_dialog.show_for_conflict(
                source, target, files, prefetched_content=content or {}
            )
        else:
            self._panel_op_active = False
            self._pr_panel.merge_via_api(pr)

    # ── PR Wizard done handlers (main thread) ─────────────────────────────────

    def _on_wizard_push_done(self, ok: bool, err: str):
        if not ok:
            self._panel_op_active = False
        self._pr_wizard.notify_push_done(ok, err)
        if ok:
            self._start_load()

    def _on_wizard_pr_done(self, ok: bool, err: str):
        self._panel_op_active = False
        self._pr_wizard.notify_pr_created(ok, err)
        if ok:
            # Switch to Collaboration tab so user sees their new PR.
            self._pr_panel_loaded = False   # force fresh fetch
            self._tab_bar._select("collaboration")

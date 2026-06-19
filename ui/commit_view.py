from __future__ import annotations

from typing import Optional

import hashlib
import os
import re
import threading

from PyQt5.QtCore import Qt, QThread, QObject, QTimer, QFileSystemWatcher, pyqtSlot, pyqtSignal
from PyQt5.QtGui import QPainter, QColor, QBrush, QPen, QPixmap, QPainterPath, QFont
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QScrollArea, QStackedWidget,
    QMessageBox,
)
from styles.theme import COLORS
from core.git_tracker import GitTracker, CommitInfo
from core.ops import (current_branch, branch_for_commit,
                      has_uncommitted_changes, create_auto_stash,
                      pop_auto_stash, apply_stash, drop_stash,
                      checkout_commit, checkout_branch,
                      get_stash_files, get_stash_ref_for_commit,
                      get_branch_unique_commits)
from core import settings_store
from ui.canvas import SpatialCanvas, MiniMap, ORIENT_LR
from ui.panels import DetailPanel, ChangesPanel, PANEL_W as DETAIL_PANEL_W, CHANGES_W
from ui.panels.position_panel import PositionPanel
from ui.panels.settings_panel import SettingsPanel
from ui.panels.pr_panel import PullRequestsPanel

# ── Extracted submodules ──────────────────────────────────────────────────────
from ui.components.avatar import _AVATAR_CACHE, _AVATAR_DIR, _avatar_disk_path, _load_avatar, _save_avatar
from ui.workers.commit_workers import (
    _CollabLoader, _Loader, _CommitDetailWorker, _VisibilityWorker,
    _FetchWorker, _UncommittedRefreshWorker, _NavigateWorker,
    _FirstCommitWorker, _CreateRepoWorker,
)
from ui.dialogs.github_connect import _GitHubConnectDialog
from ui.components.loading_overlay import _LoadingOverlay
from ui.components.no_remote_view import _NoRemoteView, _NoRemoteBanner
from ui.components.header_bar import _Header
from ui.components.zoom_bar import ZoomBar
from ui.components.legend import _Legend
from ui.components.collaborator_panel import (
    _COLLAB_PALETTE, _person_color, _SkeletonRow, _AvatarDot, _CollabRow, CollaboratorPanel,
)
from ui.components.explore_banner import _ExploreBanner
from ui.components.toast import _Toast
from ui.dialogs.conflict_dialog import (
    _numbered, _ConflictDialog, _PullDirtyDialog, _NavigateDirtyDialog, _MergeConflictDialog,
)
from ui.commit_view_widgets import _FilterPanel, _OrientBar, _TabBar, _CreateRemoteDialog
from ui.commit_view_pr import _PRMixin


def _compute_branch_depths(commits: list, local_tip_branch: dict,
                           default_branch: str = "main") -> dict[str, int]:
    """Return branch_name → nesting depth (0 = default branch, 1 = off default, 2 = off level-1, …)."""
    sha_to_branch = {c.sha: (local_tip_branch.get(c.sha) or c.branch) for c in commits}

    # For each branch record which branch it first diverged from.
    branch_parent: dict[str, str] = {}
    for commit in commits:
        if not commit.parents:
            continue
        cb = local_tip_branch.get(commit.sha) or commit.branch
        pb = sha_to_branch.get(commit.parents[0], "")
        if cb and pb and pb != cb and cb not in branch_parent:
            branch_parent[cb] = pb

    # Seed the default branch at depth 0.
    depths: dict[str, int] = (
        {default_branch: 0} if any(c.branch == default_branch for c in commits) else {}
    )

    # Iteratively assign depths from parents.
    changed = True
    while changed:
        changed = False
        for branch, parent in branch_parent.items():
            if branch not in depths and parent in depths:
                depths[branch] = depths[parent] + 1
                changed = True

    # Any branch still unknown → default to depth 1 (direct off main).
    for c in commits:
        if c.branch and c.branch not in depths:
            depths[c.branch] = 1

    return depths


class CommitViewPage(_PRMixin, QWidget):
    _op_done        = pyqtSignal(bool, str, str, str, bool)  # ok, err, success_msg, fail_prefix, close_panel
    _push_done_sig      = pyqtSignal(bool, str, str, list, object)  # ok, err, branch, conflict_files, content
    _conflict_done_sig      = pyqtSignal(bool, str, str)         # ok, err, branch
    _merge_done_sig         = pyqtSignal(bool, str, list, str, str, object)  # ok, err, files, source, target, content
    _merge_resolve_done_sig = pyqtSignal(bool, str, str)             # ok, err, success_msg
    _pull_done_sig      = pyqtSignal(bool, str, str, list)  # ok, err, success_msg, conflict_files
    _auto_pull_done_sig = pyqtSignal(bool, str, str, str)    # ok, err, pulled, failed
    _create_done_sig= pyqtSignal(bool, str, str)             # ok, err, branch_name
    _stash_done_sig = pyqtSignal(bool, str, list, object)   # ok, msg, conflict_files, conflict_content
    # PR wizard signals (thread → main)
    _wizard_push_done_sig   = pyqtSignal(bool, str)          # ok, err
    _wizard_pr_done_sig     = pyqtSignal(bool, str)          # ok, err
    # PR merge conflict check (thread → main)
    _pr_conflict_check_sig      = pyqtSignal(bool, list, object, object)  # has_conflicts, files, content, pr
    _pr_conflict_check_err_sig  = pyqtSignal(str)                         # err
    # Emitted when repo access is denied (private / inaccessible) — carries repo path
    access_denied           = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._tracker: Optional[GitTracker] = None
        self._thread:  Optional[QThread]    = None
        self._setup_ui()

    def _setup_ui(self):
        self.setStyleSheet(f"background: {COLORS['bg_primary']};")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self._header = _Header()
        layout.addWidget(self._header)

        self._no_remote_banner = _NoRemoteBanner()
        self._no_remote_banner.hide()   # replaced by header status badge
        layout.addWidget(self._no_remote_banner)

        self._tab_bar = _TabBar()
        self._tab_bar.tab_changed.connect(self._switch_tab)
        self._header.set_center(self._tab_bar)

        self._content_stack = QStackedWidget()
        layout.addWidget(self._content_stack)

        self._canvas = SpatialCanvas()
        self._content_stack.addWidget(self._canvas)   # index 0 — Schema

        self._settings_panel = SettingsPanel()
        self._content_stack.addWidget(self._settings_panel)  # index 1 — Settings

        self._panel    = DetailPanel(self)
        self._panel.raise_()
        self._settings_panel._branch_protection_sig.connect(self._on_branch_protection_state)

        self._changes_panel = ChangesPanel(self)
        self._changes_panel.raise_()



        self._position_panel = PositionPanel(self)
        self._position_panel.raise_()

        self._zoom_bar = ZoomBar(self._canvas, self)
        self._zoom_bar.raise_()

        self._minimap = MiniMap(self._canvas, self)
        self._minimap.raise_()

        self._orient_bar = _OrientBar(self)
        self._orient_bar.raise_()
        self._orient_bar.orientation_changed.connect(self._set_orientation)

        self._filter_panel = _FilterPanel(self)
        self._filter_panel.raise_()

        self._filter_panel.filter_changed.connect(self._apply_canvas_filter)

        self._filter_btn = QPushButton("⊟ Filter", self)
        self._filter_btn.setFixedHeight(34)
        self._filter_btn.setCursor(Qt.PointingHandCursor)
        self._filter_btn.setStyleSheet(f"""
            QPushButton {{
                background: {COLORS['bg_card']}; border: 1px solid {COLORS['border']};
                border-radius: 8px; color: {COLORS['text_muted']};
                font-size: 12px; padding: 0 12px;
            }}
            QPushButton:hover {{ color: {COLORS['text_primary']}; background: {COLORS['bg_hover']}; }}
            QPushButton:checked {{ color: {COLORS['accent']}; border-color: {COLORS['accent']}; }}
        """)
        self._filter_btn.setCheckable(True)
        self._filter_btn.clicked.connect(self.toggle_filter_panel)
        self._filter_btn.raise_()

        # PR Inbox — lives in the Collaboration tab (content stack index 2)
        self._pr_panel = PullRequestsPanel()
        self._pr_panel.pr_hovered.connect(self._canvas.set_pr_highlight)
        self._pr_panel.pr_cleared.connect(lambda: self._canvas.set_pr_highlight(set()))
        self._pr_panel.merge_requested.connect(self._on_pr_merge_requested)
        self._content_stack.addWidget(self._pr_panel)   # index 2 — Collaboration

        # PR Open Wizard — full-screen modal overlay
        from ui.dialogs.pr_open_wizard import PROpenWizard
        self._pr_wizard = PROpenWizard(self)
        self._pr_wizard.push_requested.connect(self._on_wizard_push)
        self._pr_wizard.pr_submitted.connect(self._on_wizard_pr_submit)
        self._pr_wizard.cancelled.connect(lambda: None)
        self._pr_wizard.raise_()

        self._conflict_dialog = _ConflictDialog(self)
        self._conflict_dialog._conflict_choice.connect(self._on_conflict_choice)
        self._conflict_dialog.raise_()

        self._pull_dirty_dialog = _PullDirtyDialog(self)
        self._pull_dirty_dialog._pull_dirty_choice.connect(self._on_pull_dirty_choice)
        self._pull_dirty_dialog.raise_()

        self._navigate_dirty_dialog = _NavigateDirtyDialog(self)
        self._navigate_dirty_dialog._navigate_dirty_choice.connect(self._on_navigate_dirty_choice)
        self._navigate_dirty_dialog.raise_()

        self._merge_conflict_dialog = _MergeConflictDialog(self)
        self._merge_conflict_dialog._merge_conflict_choice.connect(self._on_merge_conflict_choice)
        self._merge_conflict_dialog.raise_()

        self._loading = _LoadingOverlay(self)
        self._toast   = _Toast(self)
        self._loading.hide()

        self._github_connect_dialog = _GitHubConnectDialog(self)
        self._github_connect_dialog._connect_choice.connect(self._on_github_connect)
        self._github_connect_dialog.raise_()
        self._header.connect_requested.connect(self._on_connect_requested)

        self._settings_loaded = False
        self._op_done.connect(self._on_branch_op_done)
        self._push_done_sig.connect(self._on_push_done)
        self._conflict_done_sig.connect(self._on_conflict_done)
        self._merge_done_sig.connect(self._on_merge_done)
        self._merge_resolve_done_sig.connect(self._on_merge_resolve_done)
        self._pull_done_sig.connect(self._on_pull_done)
        self._auto_pull_done_sig.connect(self._on_auto_pull_done)
        self._create_done_sig.connect(self._on_branch_create_done)
        self._stash_done_sig.connect(self._on_clear_stash_done)
        # PR wizard / inbox signals
        self._wizard_push_done_sig.connect(self._on_wizard_push_done)
        self._wizard_pr_done_sig.connect(self._on_wizard_pr_done)
        self._pr_conflict_check_sig.connect(self._on_pr_conflict_check)
        self._pr_conflict_check_err_sig.connect(self._on_pr_conflict_check_err)
        self._pending_merge_pr: dict = {}

        self._orientation: str = ORIENT_LR
        self._author_display_map: dict[str, str] = {}
        self._filter_rebuilding: bool = False

        self._user: dict = {}
        self._pr_panel_loaded:      bool = False
        self._collab_thread:        Optional[QThread] = None
        self._collab_worker         = None
        self._pending_create_remote: bool = False
        self._create_remote_dlg                        = None
        self._fetch_thread:     Optional[QThread] = None
        self._detail_thread:    Optional[QThread] = None
        self._detail_gen: int   = 0
        self._vis_thread:       Optional[QThread] = None
        self._navigate_thread:  Optional[QThread] = None
        self._navigate_worker   = None
        self._nav_gen:          int  = 0
        self._navigating:       bool = False
        self._last_pull_branch: str  = ""
        self._last_dirty:       bool = False
        self._last_stash_id:    str  = ""
        self._uncommitted_thread: Optional[QThread] = None
        self._uncommitted_worker  = None
        self._commits: list = []
        self._collaborators: list = []
        self._collab_cache: dict[str, list[dict]] = {}
        self._you_shas: set = set()
        self._last_head_sha: str = ""
        self._last_commit_shas: tuple = ()
        self._last_branch_tips: dict = {}
        self._last_local_only: set = set()
        self._last_unpushed: set = set()
        self._last_stash_shas: set = set()
        self._local_tip_shas:   set  = set()
        self._local_tip_branch: dict = {}
        self._local_branch_tip: dict = {}   # {branch_name: sha} — all local refs
        self._remote_tip_shas:  set  = set()
        self._branch_head_shas: set  = set()
        self._branch_depths: dict    = {}
        self._jump_to_head:        bool = False
        self._jump_to_sha:         str  = ""    # specific SHA to jump to after canvas rebuild
        self._reload_from_remote:  bool = False
        self._last_remote_pusher:  str  = ""
        self._panel_op_active:     bool = False
        self._pending_init_path: str  = ""
        self._current_tab:         str  = "schema"
        self._inflight: list = []   # keeps (thread, worker) pairs alive until C++ threads finish

        self._poll_timer = QTimer()
        self._poll_timer.setInterval(30_000)
        self._poll_timer.timeout.connect(self._poll_remote)

        self._uncommitted_timer = QTimer()
        self._uncommitted_timer.setInterval(2_000)
        self._uncommitted_timer.timeout.connect(self._poll_uncommitted)

        # Filesystem watcher — instant detection of any .git change
        self._fs_watcher = QFileSystemWatcher()
        self._fs_watcher.fileChanged.connect(self._on_git_file_changed)
        self._fs_watcher.directoryChanged.connect(self._on_git_dir_changed)

        # Short debounce so rapid multi-file git ops don't fire multiple reloads
        self._reload_debounce = QTimer()
        self._reload_debounce.setSingleShot(True)
        self._reload_debounce.setInterval(150)
        self._reload_debounce.timeout.connect(self._start_load)
        self._canvas.commit_clicked.connect(self._on_commit_clicked)
        self._canvas.contributor_badge_clicked.connect(self._on_collaborator_clicked)
        self._panel.panel_toggled.connect(lambda v: self._changes_panel.hide_panel() if not v else None)
        self._panel.file_selected.connect(self._changes_panel.show_file)
        self._panel.stash_file_selected.connect(
            lambda info: self._changes_panel.show_file(info, source="stash")
        )
        self._position_panel.jump_requested.connect(self._canvas.jump_to_commit)
        self._position_panel.pull_requested.connect(self._on_pull_branch)
        self._panel.navigate_requested.connect(self._on_navigate)
        self._panel.branch_create_requested.connect(self._on_branch_create)
        self._panel.push_requested.connect(self._on_push_branch)
        self._panel.pr_open_requested.connect(self._on_pr_open_requested)
        self._panel.pull_requested.connect(self._on_pull_branch)
        self._panel.sync_requested.connect(self._on_sync_branch)
        self._panel.merge_requested.connect(self._on_merge_branch)
        self._panel.save_stash_requested.connect(self._on_save_stash)
        self._panel.clear_stash_requested.connect(self._on_clear_stash)
        self._panel.hard_revert_requested.connect(self._on_hard_revert)
        self._panel.soft_revert_requested.connect(self._on_soft_revert)
        self._panel.delete_branch_requested.connect(self._on_delete_branch)

    # ── Public ────────────────────────────────────────────────────────────

    def set_user(self, user: dict):
        self._user = user
        from core.ops.base_ops import set_commit_author
        name  = user.get("name") or user.get("login", "")
        login = user.get("login", "")
        email = user.get("email") or (f"{login}@users.noreply.github.com" if login else "")
        set_commit_author(name, email)

    def reset(self):
        """Full teardown — called on sign out."""
        from core.ops.base_ops import clear_commit_author
        clear_commit_author()
        self._stop_all_threads()
        if self._tracker:
            self._tracker.close()
            self._tracker = None
        if self._create_remote_dlg:
            self._create_remote_dlg.hide()
            self._create_remote_dlg = None
        self._pending_create_remote = False
        self._thread = self._collab_thread = None
        self._commits = []
        self._collaborators = []
        self._you_shas = set()
        self._last_head_sha = ""
        self._last_commit_shas = ()
        self._last_branch_tips = {}
        self._last_local_only = set()
        self._last_unpushed = set()
        self._sha_to_branch: dict = {}
        self._user = {}
        self._poll_timer.stop()
        self._uncommitted_timer.stop()
        self._reload_debounce.stop()
        self._teardown_fs_watcher()
        self._canvas.load_graph([], {})
        self._changes_panel.hide_panel()
        self._panel.hide_panel()
        self._position_panel.clear()
        self._last_head_sha = ""
        self._header.set_repo("—")

    def _stop_all_threads(self):
        # 1. Disconnect all worker signals FIRST so no callbacks fire after this point
        for attr in ("_worker", "_collab_worker", "_fetch_worker",
                     "_detail_worker", "_vis_worker",
                     "_create_worker", "_first_commit_worker",
                     "_uncommitted_worker", "_navigate_worker"):
            w = getattr(self, attr, None)
            if w is not None:
                try:
                    w.finished.disconnect()
                except Exception:
                    pass

        # 2. Quit all threads and move them to _inflight so Python GC
        #    cannot delete the objects while the C++ thread is still running.
        for t_attr, w_attr in (
            ("_thread",             "_worker"),
            ("_collab_thread",      "_collab_worker"),
            ("_fetch_thread",       "_fetch_worker"),
            ("_detail_thread",      "_detail_worker"),
            ("_vis_thread",         "_vis_worker"),
            ("_navigate_thread",    "_navigate_worker"),
            ("_uncommitted_thread", "_uncommitted_worker"),
            ("_create_thread",      "_create_worker"),
            ("_first_commit_thread","_first_commit_worker"),
        ):
            t = getattr(self, t_attr, None)
            w = getattr(self, w_attr, None)
            if t and t.isRunning():
                t.quit()
                pair = [t, w]
                self._inflight.append(pair)
                t.finished.connect(lambda _=None, p=pair: self._drop_inflight(p))

    def _drop_inflight(self, pair: list):
        try:
            self._inflight.remove(pair)
        except ValueError:
            pass

    def load_repo(self, repo_path: str):
        self._stop_all_threads()
        self._tab_bar._select("schema")

        # Clear the canvas and show the overlay immediately so the old project's
        # graph is never visible when this page becomes visible after the switch.
        self._canvas.load_graph([], {})
        self._pending_create_remote = False
        if self._create_remote_dlg:
            self._create_remote_dlg.hide()
            self._create_remote_dlg = None
        self._loading.show()
        self._loading.raise_()

        if self._tracker:
            self._tracker.close()

        self._commits        = []
        self._branch_tip_map = {}
        self._collaborators  = []
        self._you_shas       = set()
        self._last_commit_shas = ()
        self._last_head_sha    = ""
        self._last_branch_tips = {}
        self._last_local_only  = set()
        self._last_unpushed    = set()
        self._last_stash_shas  = set()
        self._sha_to_branch: dict = {}
        self._tracker = GitTracker(repo_path)
        self._panel.set_repo_path(repo_path)
        try:
            self._tracker.open()
        except Exception:
            # Not a git repo — auto-init silently then reload
            self._tracker = None
            self._pending_init_path = repo_path
            user_name  = self._user.get("name") or self._user.get("login", "")
            user_email = self._user.get("email", "")
            def _auto_init():
                try:
                    from core.ops import init_repo
                    init_repo(repo_path, user_name, user_email)
                except Exception:
                    pass
                from PyQt5.QtCore import QTimer
                QTimer.singleShot(0, lambda: self._reload_after_init(repo_path))
            import threading as _t
            _t.Thread(target=_auto_init, daemon=True).start()
            return

        self._header.set_repo(self._tracker.repo_name)
        self._header.set_local_path(repo_path)
        self._header.set_operation("")
        self._panel.hide_panel()
        self._filter_panel.hide()
        self._filter_panel.show_collaborators_loading()
        orientations = settings_store.get("repo_orientations", {})
        self._orientation = orientations.get(repo_path, ORIENT_LR)
        self._orient_bar.set_orientation(self._orientation)

        self._settings_loaded    = False
        self._pr_panel_loaded    = False
        has_remote = self._tracker.has_remote()
        self._no_remote_banner.hide()
        self._header.set_connection_state(has_remote)
        token = self._user.get("access_token", "")
        if has_remote:
            self._header.set_url(self._tracker.remote_url())   # show URL immediately, badge loads async
            if token:
                self._vis_thread  = QThread()
                self._vis_worker  = _VisibilityWorker(self._tracker._path, token)
                self._vis_worker.moveToThread(self._vis_thread)
                self._vis_thread.started.connect(self._vis_worker.run)
                self._vis_worker.finished.connect(self._on_visibility_ready)
                self._vis_worker.finished.connect(self._vis_thread.quit)
                self._vis_thread.start()
        else:
            self._header.set_url("")
        self._poll_timer.stop()
        if has_remote:
            self._poll_timer.start()
            self._poll_remote()
        self._last_dirty    = False
        self._last_stash_id = ""
        self._uncommitted_timer.start()
        self._setup_fs_watcher(self._tracker._repo.git_dir)

        if not has_remote:
            self._pending_create_remote = True
            self._show_create_remote_dialog(
                "Create GitHub Repository",
                "This repository isn't on GitHub yet. Create one to enable collaboration and backups.",
                self._tracker.repo_name,
            )
            return

        self._start_load(initial=True)
        self._load_collaborators()

    # ── Internal ──────────────────────────────────────────────────────────

    def _start_load(self, initial: bool = False):
        if not self._tracker:
            return
        if self._pending_create_remote:
            return

        # If a load is already running, queue another attempt instead of blocking
        if self._thread and self._thread.isRunning():
            self._reload_debounce.start()
            return

        # Only show the loading overlay on the very first open — background
        # refreshes (watcher / remote poll) update silently to avoid flicker
        if initial:
            self._loading.show()
            self._loading.raise_()

        self._thread = QThread()
        self._worker = _Loader(self._tracker._path)
        self._worker.moveToThread(self._thread)
        self._thread.started.connect(self._worker.run)
        self._worker.finished.connect(self._on_loaded)
        self._worker.finished.connect(self._thread.quit)
        self._thread.start()

    def _on_visibility_ready(self, url: str, visibility: str):
        self._header.set_url(url, visibility)
        owner = self._tracker.repo_owner() if self._tracker else ""
        is_owner = bool(owner) and self._user.get("login", "") == owner
        if visibility == "not_found" and self._tracker and is_owner:
            self._loading.show()
            self._loading.raise_()
            self._pending_create_remote = True
            self._show_create_remote_dialog(
                "Remote Repository Deleted",
                f'The GitHub repository for "{self._tracker.repo_name}" no longer exists. Recreate it to restore your backup.',
                self._tracker.repo_name,
            )
            return


    def _poll_remote(self):
        if not self._tracker or not self._tracker.has_remote():
            return
        if self._fetch_thread and self._fetch_thread.isRunning():
            return
        self._fetch_thread  = QThread()
        self._fetch_worker  = _FetchWorker(self._tracker._path)
        self._fetch_worker.moveToThread(self._fetch_thread)
        self._fetch_thread.started.connect(self._fetch_worker.run)
        self._fetch_worker.finished.connect(self._on_fetch_done)
        self._fetch_worker.finished.connect(self._fetch_thread.quit)
        self._fetch_thread.start()

    # ── Branch count worker ────────────────────────────────────────────────────

    def _on_branch_count_done(self, counts: dict):
        default = getattr(self._settings_panel, "_default_branch", "main")
        main_count = counts.get(default, counts.get("master", 0))
        self._header.set_count(main_count, default)

    # ── Fetch ──────────────────────────────────────────────────────────────────

    def _on_fetch_done(self, changed: bool, last_pusher: str = ""):
        self._last_remote_pusher = last_pusher
        if changed:
            self._reload_from_remote = True
        if self._tracker and not self._panel_op_active:
            self._try_auto_pull()
        else:
            self._start_load()

    def _try_auto_pull(self):
        path = self._tracker._path
        def _run():
            try:
                import subprocess as _sp
                from core.ops import has_uncommitted_changes, pull_ff, current_branch
                cur = current_branch(path)
                if cur == "HEAD":
                    self._auto_pull_done_sig.emit(True, "", "", "")
                    return
                dirty = has_uncommitted_changes(path)
                # Collect local branches that are behind their remote
                r = _sp.run(
                    ["git", "for-each-ref", "refs/heads/", "--format=%(refname:short) %(upstream:short) %(upstream:trackshort)"],
                    cwd=path, capture_output=True, text=True, timeout=5,
                    encoding="utf-8", errors="replace",
                )
                behind_branches = []
                all_local = []
                for line in (r.stdout or "").strip().splitlines():
                    parts = line.strip().split()
                    if not parts:
                        continue
                    all_local.append(parts[0])
                    if len(parts) >= 3 and parts[2] == "<":
                        behind_branches.append(parts[0])
                # Also check branches without tracking that have a matching origin/<name>
                for branch in all_local:
                    if branch in behind_branches:
                        continue
                    cnt = _sp.run(
                        ["git", "rev-list", "--count", f"{branch}..origin/{branch}"],
                        cwd=path, capture_output=True, text=True, timeout=5,
                        encoding="utf-8", errors="replace",
                    )
                    if cnt.returncode == 0 and cnt.stdout.strip() not in ("", "0"):
                        cnt2 = _sp.run(
                            ["git", "rev-list", "--count", f"origin/{branch}..{branch}"],
                            cwd=path, capture_output=True, text=True, timeout=5,
                            encoding="utf-8", errors="replace",
                        )
                        if cnt2.returncode != 0 or cnt2.stdout.strip() in ("", "0"):
                            behind_branches.append(branch)
                if not behind_branches:
                    self._auto_pull_done_sig.emit(True, "", "", "")
                    return
                pulled = []
                failed = []
                for branch in behind_branches:
                    if branch == cur and dirty:
                        continue
                    old_tip = _sp.run(
                        ["git", "rev-parse", branch],
                        cwd=path, capture_output=True, text=True, timeout=5,
                        encoding="utf-8", errors="replace",
                    ).stdout.strip()
                    ok, err = pull_ff(path, branch)
                    if ok:
                        pulled.append(branch)
                        if old_tip:
                            from core.ops import migrate_stash_after_pull
                            migrate_stash_after_pull(path, old_tip)
                    else:
                        failed.append((branch, err))
                first_err = failed[0][1] if failed else ""
                self._auto_pull_done_sig.emit(not failed, first_err,
                    ", ".join(pulled) if pulled else "",
                    ", ".join(b for b, _ in failed) if failed else "")
            except Exception:
                self._auto_pull_done_sig.emit(False, "", "", "")
        import threading as _threading
        _threading.Thread(target=_run, daemon=True).start()

    def _on_auto_pull_done(self, ok: bool, err: str, pulled: str = "", failed: str = ""):
        if pulled:
            self._toast.show_message(f"Synced: {pulled}", kind="success", duration_ms=4000)
        if not ok and err:
            if "non-fast-forward" in err or "rejected" in err or "diverge" in err.lower():
                self._toast.show_message(
                    "Branch has diverged from remote — use Sync to merge.", kind="error", duration_ms=6000)
            elif failed:
                self._toast.show_message(
                    f"Couldn't sync: {failed}", kind="error", duration_ms=5000)
            else:
                self._toast.show_message(
                    "Auto-pull failed — pull manually to update.", kind="error", duration_ms=5000)
        self._start_load()

    def _find_nearest_surviving_ancestor(self, deleted_sha: str, new_sha_set: set) -> str:
        """BFS up the old commit graph from deleted_sha, returning the first
        ancestor SHA that exists in new_sha_set.  Uses self._commits (the
        pre-rebuild snapshot) so must be called before self._commits is updated.
        Returns "" if no surviving ancestor is found.
        """
        parent_map = {c.sha: c.parents for c in self._commits}
        visited: set = set()
        queue = [deleted_sha]
        while queue:
            sha = queue.pop(0)
            if sha in visited:
                continue
            visited.add(sha)
            if sha != deleted_sha and sha in new_sha_set:
                return sha          # nearest surviving ancestor
            queue.extend(p for p in parent_map.get(sha, []) if p not in visited)
        return ""

    def _handle_remote_deleted_commit(self, sha: str, new_sha_set: set):
        """Called when the commit currently open in the detail panel no longer
        exists after a remote fetch.  Hides the panel, queues a jump to the
        nearest surviving ancestor (or HEAD as fallback), and shows a toast.

        Any unsaved stash for the deleted SHA is silently orphaned — the user
        accepted this behaviour.
        """
        self._panel.hide_panel()

        target = self._find_nearest_surviving_ancestor(sha, new_sha_set)
        if target:
            self._jump_to_sha = target
        else:
            self._jump_to_head = True       # fallback: go to HEAD

        short  = sha[:7]
        dest   = target[:7] if target else "HEAD"
        pusher = self._last_remote_pusher
        if pusher:
            msg = f"Commit {short} was removed by {pusher} — moved to {dest}"
        else:
            msg = f"Commit {short} was removed from remote — moved to {dest}"
        self._toast.show_message(msg, kind="info", duration_ms=7000)

    def _setup_fs_watcher(self, git_dir: str):
        self._teardown_fs_watcher()
        paths = []
        for name in ("HEAD", "packed-refs", "ORIG_HEAD"):
            p = os.path.join(git_dir, name)
            if os.path.exists(p):
                paths.append(p)
        # Watch .git/ root and every directory under refs/ recursively
        # so loose ref updates (push, fetch, branch create) are caught at any depth
        for dirpath, dirnames, _ in os.walk(git_dir):
            rel = os.path.relpath(dirpath, git_dir)
            if rel == "." or rel.startswith("refs"):
                paths.append(dirpath)
            # Don't descend into object store — too many dirs, not useful
            dirnames[:] = [d for d in dirnames if d not in ("objects", "logs")]
        if paths:
            self._fs_watcher.addPaths(paths)

    def _teardown_fs_watcher(self):
        files = self._fs_watcher.files()
        dirs  = self._fs_watcher.directories()
        if files:
            self._fs_watcher.removePaths(files)
        if dirs:
            self._fs_watcher.removePaths(dirs)

    def _on_git_file_changed(self, path: str):
        if not self._tracker:
            return
        if not os.path.isdir(self._tracker._path):
            self._teardown_fs_watcher()
            return
        if os.path.exists(path) and path not in self._fs_watcher.files():
            self._fs_watcher.addPath(path)
        if self._navigating or self._panel_op_active:
            return
        self._header.set_operation(self._tracker.operation_in_progress())
        self._reload_debounce.start()

    def _on_git_dir_changed(self, path: str):
        if not self._tracker:
            return
        if not os.path.isdir(self._tracker._path):
            self._teardown_fs_watcher()
            return
        if self._navigating or self._panel_op_active:
            return
        self._header.set_operation(self._tracker.operation_in_progress())
        self._reload_debounce.start()

    def _start_create_repo(self, name: str, private: bool):
        if not self._tracker:
            return
        token      = self._user.get("access_token", "")
        username   = self._user.get("login", "")
        user_name  = self._user.get("name") or username
        user_email = self._user.get("email", "")
        if not token or not username:
            return
        if self._create_remote_dlg:
            self._create_remote_dlg.set_creating(True)
        self._create_thread  = QThread()
        self._create_worker  = _CreateRepoWorker(
            self._tracker._path, name, token, username, private, user_name, user_email,
        )
        self._create_worker.moveToThread(self._create_thread)
        self._create_thread.started.connect(self._create_worker.run)
        self._create_worker.finished.connect(self._on_create_done)
        self._create_worker.finished.connect(self._create_thread.quit)
        self._create_thread.start()

    def _on_create_done(self, success: bool, error: str, clone_url: str):
        if not success:
            if self._create_remote_dlg:
                self._create_remote_dlg.set_error(error or "Something went wrong.")
            return
        # Success — close dialog, clear pending flag, proceed with normal load
        if self._create_remote_dlg:
            self._create_remote_dlg.hide()
            self._create_remote_dlg = None
        self._pending_create_remote = False
        self._tracker.close()
        self._tracker.open()
        token = self._user.get("access_token", "")
        self._header.set_url(self._tracker.remote_url())
        self._header.set_connection_state(True)
        if token:
            self._vis_thread  = QThread()
            self._vis_worker  = _VisibilityWorker(self._tracker._path, token)
            self._vis_worker.moveToThread(self._vis_thread)
            self._vis_thread.started.connect(self._vis_worker.run)
            self._vis_worker.finished.connect(self._on_visibility_ready)
            self._vis_worker.finished.connect(self._vis_thread.quit)
            self._vis_thread.start()
        self._poll_timer.start()
        self._start_load(initial=True)
        self._load_collaborators()

    def _show_create_remote_dialog(self, title: str, subtitle: str, repo_name: str):
        if self._create_remote_dlg:
            self._create_remote_dlg.hide()
        dlg = _CreateRemoteDialog(self)
        dlg.setup(title, subtitle, repo_name)
        dlg.create_requested.connect(self._on_create_remote_requested)
        dlg.cancelled.connect(self._on_create_remote_cancelled)
        self._create_remote_dlg = dlg
        dlg.show()
        dlg.raise_()

    def _on_create_remote_requested(self, name: str, is_private: bool):
        self._start_create_repo(name, is_private)

    def _on_create_remote_cancelled(self):
        self._pending_create_remote = False
        if self._create_remote_dlg:
            self._create_remote_dlg.hide()
            self._create_remote_dlg = None
        path = self._tracker._path if self._tracker else ""
        self.access_denied.emit(path)

    def _on_loaded(self, commits: list[CommitInfo], branch_tip_map: dict,
                   local_only: set, unpushed: set, stash_shas: set = None,
                   remote_tip_shas: set = None):
        if not commits and self._tracker:
            self._make_first_commit()
            return

        new_shas = tuple(c.sha for c in commits)

        stash_shas = stash_shas or set()

        # Strip FF-merged branches via first-parent chain traversal.
        # c.branch is NOT yet set here (load_graph sets it later), so we walk
        # the default branch's first-parent ancestry using commit.parents.
        _dflt_now = getattr(self._settings_panel, "_default_branch", "main")
        _dflt_tip = next(
            (sha for sha, names in branch_tip_map.items() if _dflt_now in names),
            None,
        )
        _main_chain: set[str] = set()
        if _dflt_tip:
            _by_sha = {c.sha: c for c in commits}
            _cur = _dflt_tip
            while _cur and _cur in _by_sha:
                _main_chain.add(_cur)
                _p = _by_sha[_cur].parents
                _cur = _p[0] if _p else None
        _keep_names = {_dflt_now, f'origin/{_dflt_now}', 'main', 'master', 'origin/main', 'origin/master'}
        _ff = {
            name
            for sha, names in branch_tip_map.items()
            if sha in _main_chain
            for name in names
            if name not in _keep_names
        }
        if _ff:
            branch_tip_map = {
                sha: [n for n in names if n not in _ff]
                for sha, names in branch_tip_map.items()
            }
            branch_tip_map = {sha: ns for sha, ns in branch_tip_map.items() if ns}

        # Always rebuild local tip map — use subprocess, NOT GitPython, because
        # GitPython caches b.commit.hexsha in memory and returns stale SHAs after
        # back-to-back merges (e.g. A→B then immediately B→A).
        import subprocess as _sp
        _dflt = getattr(self._settings_panel, "_default_branch", "main")
        self._local_tip_shas   = set()
        self._local_tip_branch = {}
        self._local_branch_tip = {}
        try:
            _r = _sp.run(
                ["git", "for-each-ref",
                 "--format=%(objectname) %(refname:short)", "refs/heads/"],
                cwd=self._tracker._path, capture_output=True, text=True,
                encoding="utf-8", errors="replace", timeout=5,
            )
            for _line in (_r.stdout or "").strip().splitlines():
                _parts = _line.strip().split(None, 1)
                if len(_parts) == 2:
                    sha, name = _parts[0], _parts[1]
                    self._local_tip_shas.add(sha)
                    self._local_branch_tip[name] = sha
                    # Prefer the default branch when two local branches share a tip SHA
                    # (e.g. new-branch created at main's tip before any new commits).
                    if sha not in self._local_tip_branch or name == _dflt:
                        self._local_tip_branch[sha] = name
        except Exception:
            pass

        # _branch_head_shas must stay in sync before the early-return guard.
        # _branch_depths is computed AFTER load_graph (which sets commit.branch);
        # on early returns the old value is still valid since nothing changed.
        self._branch_head_shas = self._local_tip_shas

        # ── Remote deletion check ─────────────────────────────────────────────
        # Must run before the early-return guard so self._commits (old graph)
        # is still available for the ancestor BFS.
        if self._reload_from_remote:
            self._reload_from_remote = False
            panel_sha = getattr(self._panel, "_current_sha", "")
            _new_sha_set = {c.sha for c in commits}
            if (panel_sha
                    and getattr(self._panel, "_visible", False)
                    and panel_sha not in _new_sha_set
                    and not self._jump_to_head):
                self._handle_remote_deleted_commit(panel_sha, _new_sha_set)
        # ─────────────────────────────────────────────────────────────────────

        # Skip full canvas rebuild when nothing has changed
        if (new_shas == self._last_commit_shas
                and branch_tip_map == self._last_branch_tips
                and local_only == self._last_local_only
                and unpushed == self._last_unpushed
                and stash_shas == self._last_stash_shas):
            self._loading.hide()
            self._update_position_panel(commits)
            return

        is_initial = not bool(self._last_commit_shas)

        self._last_commit_shas = new_shas
        self._last_branch_tips = branch_tip_map
        self._last_local_only  = local_only
        self._last_unpushed    = unpushed
        self._last_stash_shas  = stash_shas

        self._commits        = commits
        self._branch_tip_map = branch_tip_map
        self._panel.set_stash_shas(stash_shas)
        # Use the ground-truth remote tip SHAs from git for-each-ref refs/remotes/
        # rather than a heuristic derived from branch_tip_map.  The heuristic
        # incorrectly excluded the actual remote tip when local is *behind* remote
        # (both SHAs share the same display name, and the newer remote SHA was
        # filtered out because it wasn't in local_tip_branch).
        self._remote_tip_shas: set[str] = remote_tip_shas or set()

        # Local tip is always the authoritative head — show the hollow ring on it
        # regardless of whether remote is ahead or behind.
        # Remote filled-dot is shown separately for awareness, but actions and
        # head-tracking always follow the local tip.
        local_tip_visible: set[str] = set(self._local_tip_branch.keys())

        self._you_shas = self._compute_you_shas(commits)


        self._canvas.load_graph(commits, branch_tip_map,
                                you_shas=self._you_shas,
                                local_only_branches=local_only,
                                unpushed_shas=unpushed,
                                stash_shas=stash_shas,
                                orientation=self._orientation,
                                head_sha=self._last_head_sha or (self._tracker.head_sha() if self._tracker else ""),
                                is_initial=is_initial,
                                local_tip_shas=local_tip_visible,
                                remote_tip_shas=self._remote_tip_shas,
                                action_head_shas=self._branch_head_shas)
        # commit.branch is now set for all commits by load_graph.
        self._sha_to_branch = {c.sha: c.branch for c in commits}
        self._update_position_panel(commits)
        self._branch_depths = _compute_branch_depths(commits, self._local_tip_branch, _dflt)
        self._loading.hide()

        if self._jump_to_sha:
            target = self._jump_to_sha
            self._jump_to_sha = ""
            self._canvas.jump_to_commit(target)
        elif self._jump_to_head:
            self._jump_to_head = False
            head = self._tracker.head_sha() if self._tracker else ""
            if head:
                self._canvas.jump_to_commit(head)

        all_branches = sorted(
            {c.branch for c in commits if c.branch}
        )

        self._filter_rebuilding = True
        self._filter_panel.set_branches(all_branches)

        # Branch list panel — count using effective_branch so FF-merged tips count
        # toward their own branch name, not the lane (main) they sit on.
        _lane_counts: dict[str, int] = {}
        for _c in commits:
            _tip = branch_tip_map.get(_c.sha, [])
            _nm  = [_n for _n in _tip if _n not in ('main', 'master')]
            _eff = _nm[0] if (_nm and _c.branch in ('main', 'master')) else _c.branch
            if _eff:
                _lane_counts[_eff] = _lane_counts.get(_eff, 0) + 1
        for _names in branch_tip_map.values():
            for _n in _names:
                if _n and _n not in _lane_counts:
                    _lane_counts[_n] = 0
        if _lane_counts:
            self._on_branch_count_done(_lane_counts)
        self._filter_rebuilding = False
        self._canvas.apply_commit_filter(set())

        if self._collaborators:
            self._place_contributor_badges()

    def _update_position_panel(self, commits: list):
        if not self._tracker:
            return
        head_sha = self._tracker.head_sha()
        if not head_sha or head_sha == self._last_head_sha:
            return
        head_commit = next((c for c in commits if c.sha == head_sha), None)
        if head_commit:
            branch = current_branch(self._tracker._path)
            if not branch:
                # Detached HEAD — use persistent sha→branch map built from the
                # last load_graph run (valid even in the early-return path where
                # fresh CommitInfo objects have branch="" before load_graph runs)
                branch = self._sha_to_branch.get(head_sha, "") or self._branch_for_head()
            avatar_url = self._avatar_url_for_author(head_commit.author)
            self._position_panel.load(head_commit.message, branch, head_commit.sha, head_commit.author, avatar_url)
            self._reposition_position()

            # Show pull button when HEAD branch is behind its remote tip
            commit_order = {c.sha: i for i, c in enumerate(commits)}
            local_sha = next((s for s, n in self._local_tip_branch.items() if n == branch), None)
            remote_sha = next(
                (s for s, names in self._last_branch_tips.items()
                 if branch in names and s not in self._local_tip_branch),
                None
            )
            is_behind = bool(local_sha and remote_sha and local_sha != remote_sha
                             and commit_order.get(remote_sha, 10**9)
                             < commit_order.get(local_sha, 10**9))
            self._position_panel.set_pull_state(is_behind)

        self._canvas.set_head_sha(head_sha)
        self._panel.set_head_sha(head_sha)
        self._last_head_sha = head_sha

    def _make_first_commit(self):
        self._first_commit_thread  = QThread()
        self._first_commit_worker  = _FirstCommitWorker(self._tracker._path)
        self._first_commit_worker.moveToThread(self._first_commit_thread)
        self._first_commit_thread.started.connect(self._first_commit_worker.run)
        self._first_commit_worker.finished.connect(
            lambda ok: self._start_load() if ok else self._loading.hide()
        )
        self._first_commit_worker.finished.connect(self._first_commit_thread.quit)
        self._first_commit_thread.start()

    def _load_collaborators(self):
        token = self._user.get("access_token", "")
        if not token or not self._tracker:
            return

        cache_key = self._tracker.remote_url()
        if cache_key and cache_key in self._collab_cache:
            self._on_collabs_loaded(self._collab_cache[cache_key])
            return

        if self._collab_thread and self._collab_thread.isRunning():
            return

        self._collab_thread  = QThread()
        self._collab_worker  = _CollabLoader(self._tracker._path, token)
        self._collab_worker.moveToThread(self._collab_thread)
        self._collab_thread.started.connect(self._collab_worker.run)
        self._collab_worker.finished.connect(self._on_collabs_loaded)
        self._collab_worker.finished.connect(self._collab_thread.quit)
        self._collab_thread.start()

    def _on_collabs_loaded(self, collabs: list[dict]):
        login = self._user.get("login", "")
        is_real_collab = bool(login) and any(c.get("login") == login for c in collabs)
        if login and not is_real_collab:
            collabs = [{
                "login":         login,
                "avatar_url":    self._user.get("avatar_url", ""),
                "contributions": 0,
                "gh_name":       self._user.get("name") or login,
                "role":          "write",
            }] + collabs
        owner = self._tracker.repo_owner() if self._tracker else ""
        for c in collabs:
            c["is_owner"] = (c.get("login") == owner)
            if c.get("login") == owner:
                c["role"] = "owner"
        self._collaborators = collabs

        if self._tracker:
            cache_key = self._tracker.remote_url()
            if cache_key:
                self._collab_cache[cache_key] = collabs

        token = self._user.get("access_token", "")
        if not self._settings_loaded and self._tracker:
            self._settings_panel.setup(self._tracker, self._user, token)
            self._settings_loaded = True
        self._settings_panel.load_collaborators(collabs, current_login=login)

        if self._commits:
            self._place_contributor_badges()

    def _on_branch_protection_state(self, branch: str, protected: bool):
        self._panel.set_branch_protection(branch if protected else None)

    @staticmethod
    def _pr_btn_style(protected: bool) -> str:
        if protected:
            return (f"QPushButton {{ background: {COLORS['accent_dim']};"
                    f" border: 1px solid {COLORS['accent']}; border-radius: 8px;"
                    f" color: {COLORS['accent']}; font-size: 12px; font-weight: 600; font-family: 'Tilt Warp';"
                    f" padding: 0 12px; }}"
                    f"QPushButton:hover {{ background: {COLORS['accent']};"
                    f" color: {COLORS['text_on_accent']}; }}")
        return (f"QPushButton {{ background: {COLORS['bg_card']};"
                f" border: 1px solid {COLORS['border']}; border-radius: 8px;"
                f" color: {COLORS['text_muted']}; font-size: 12px; font-weight: 600; font-family: 'Tilt Warp';"
                f" padding: 0 12px; }}"
                f"QPushButton:hover {{ color: {COLORS['text_primary']};"
                f" background: {COLORS['bg_hover']}; }}")

    def _switch_tab(self, tab: str):
        if tab == "schema":
            self._content_stack.setCurrentIndex(0)
            for w in [self._zoom_bar, self._minimap, self._orient_bar, self._filter_btn]:
                w.show()
            if getattr(self, "_pos_panel_was_visible", False):
                self._position_panel.show()
                self._reposition_position()
        elif tab == "collaboration":
            if self._current_tab == "schema":
                self._pos_panel_was_visible = self._position_panel.isVisible()
            self._content_stack.setCurrentIndex(2)
            for w in [self._zoom_bar, self._minimap, self._orient_bar,
                      self._filter_btn, self._filter_panel, self._position_panel]:
                w.hide()
            self._panel.hide_panel()
            self._changes_panel.hide_panel()
            # Load inbox on first visit
            self._load_pr_inbox()
        else:
            # "settings"
            if self._current_tab == "schema":
                self._pos_panel_was_visible = self._position_panel.isVisible()
            self._content_stack.setCurrentIndex(1)
            for w in [self._zoom_bar, self._minimap, self._orient_bar,
                      self._filter_btn, self._filter_panel, self._position_panel]:
                w.hide()
            self._panel.hide_panel()
            self._changes_panel.hide_panel()
            # Initialise settings if collabs haven't loaded yet (e.g. no remote)
            if not self._settings_loaded and self._tracker:
                self._settings_panel.setup(
                    self._tracker, self._user,
                    self._user.get("access_token", ""),
                )
                self._settings_loaded = True
        self._current_tab = tab

    def _on_clear_stash(self, sha: str, stash_ref: str):
        if not self._tracker or self._panel_op_active:
            return
        self._panel_op_active = True
        path = self._tracker._path
        if stash_ref:
            self._toast.show_message("Clearing stash…", kind="loading")
            def _run():
                try:
                    from core.ops import drop_stash
                    ok = drop_stash(path, stash_ref)
                    err = "" if ok else "drop failed"
                except Exception as exc:
                    ok, err = False, str(exc)
                self._stash_done_sig.emit(ok, "Stash cleared.", [], {})
        else:
            self._toast.show_message("Discarding changes…", kind="loading")
            def _run():
                try:
                    from core.ops import discard_all_changes
                    ok, err = discard_all_changes(path)
                except Exception as exc:
                    ok, err = False, str(exc)
                self._stash_done_sig.emit(ok, "Changes discarded." if ok else err, [], {})
        import threading as _threading
        _threading.Thread(target=_run, daemon=True).start()

    def _on_clear_stash_done(self, ok: bool, msg: str, conflict_files: list, conflict_content: object):
        if ok:
            self._panel_op_active = False
            self._panel.unlock_actions()
            self._toast.show_message(msg, kind="success")
            self._panel.refresh_stash_section()
            self._start_load()
        elif msg == "save_conflict":
            branch = getattr(self._panel, "_action_branch", "")
            self._save_conflict_stash_ref = getattr(self._panel, "_stash_ref", "")
            self._merge_conflict_dialog.show_for_conflict(
                "stash", branch, conflict_files,
                prefetched_content=conflict_content or {})
            self._start_load()
        else:
            self._panel_op_active = False
            self._panel.unlock_actions()
            self._toast.show_message("Something went wrong — your changes are still safe. Try again.", kind="error", duration_ms=8000)
            self._start_load()

    def _on_connect_requested(self):
        if self._tracker:
            self._github_connect_dialog.show_near(self._tracker._path)

    def _on_github_connect(self, name: str, is_private: bool):
        if not self._tracker:
            return
        path       = self._tracker._path
        token      = self._user.get("access_token", "")
        username   = self._user.get("login", "")
        user_name  = self._user.get("name") or username
        user_email = self._user.get("email", "")
        if not token:
            self._toast.show_message("Not signed in to GitHub.", kind="error", duration_ms=6000)
            return
        self._toast.show_message("Connecting to GitHub…", kind="loading")
        def _run():
            try:
                from core.ops import create_github_repo, push_to_github
                ok, err, clone_url = create_github_repo(name, is_private, token)
                if not ok:
                    self._push_done_sig.emit(False, err, "", [], {})
                    return
                ok2, err2 = push_to_github(path, clone_url, username, token, user_name, user_email)
                # empty branch signals "_on_push_done" this is a connect, not a push
                self._push_done_sig.emit(ok2, err2 if not ok2 else "", "", [], {})
            except Exception as exc:
                self._push_done_sig.emit(False, str(exc), "", [], {})
        import threading as _threading
        _threading.Thread(target=_run, daemon=True).start()

    def _reload_after_init(self, path: str):
        self._pending_init_path = ""
        self.load_repo(path)

    def _on_merge_branch(self, source: str, target: str):
        if not self._tracker or self._panel_op_active:
            return
        self._panel_op_active = True
        self._navigating = True
        self._reload_debounce.stop()
        self._toast.show_message("Merging…", kind="loading")
        path = self._tracker._path
        def _run():
            try:
                from core.ops import merge_branch, checkout_branch
                from core.ops import current_branch as _cur

                if _cur(path) != target:
                    ok_co, err_co = checkout_branch(path, target)
                    if not ok_co:
                        self._merge_done_sig.emit(False, err_co, [], source, target, {})
                        return
                git_source = source if source in self._local_branch_tip else f"origin/{source}"
                ok, err, files, content = merge_branch(path, git_source)
            except Exception as exc:
                ok, err, files, content = False, str(exc), [], {}
            self._merge_done_sig.emit(ok, err, files, source, target, content)
        import threading as _threading
        _threading.Thread(target=_run, daemon=True).start()

    def _on_merge_done(self, ok: bool, err: str, files: list, source: str, target: str, content: object):
        if ok:
            self._panel_op_active = False
            self._navigating = False
            if err in ("already_up_to_date",) or err.startswith("already_merged:"):
                self._toast.show_message(
                    f"'{source}' is already fully merged into '{target}'.", kind="success", duration_ms=5000)
            elif err.startswith("empty_branch_deleted:"):
                deleted = err.split(":", 1)[1]
                self._toast.show_message(
                    f"'{deleted}' had no commits — branch deleted.", kind="success", duration_ms=5000)
            else:
                self._toast.show_message(
                    f"Merged '{source}' into '{target}'.", kind="success", duration_ms=5000)
            self._panel.hide_panel()
            self._last_branch_tips = {}
            self._last_head_sha    = ""
            self._panel.unlock_actions()
            self._start_load()
        elif err == "merge_conflict":
            self._merge_conflict_dialog.show_for_conflict(
                source, target, files, prefetched_content=content or {})
        else:
            self._panel_op_active = False
            self._navigating = False
            msg = "Timed out." if err == "timed_out" else "Merge failed — try again or check for conflicting changes."
            self._toast.show_message(msg, kind="error", duration_ms=6000)
            self._panel.unlock_actions()

    def _on_merge_conflict_choice(self, decisions, source: str, target: str):
        path = self._tracker._path
        if decisions is None:
            # Cancel — merge was already aborted, nothing to do
            self._panel_op_active = False
            self._navigating = False
            self._panel.unlock_actions()
            return
        # decisions is a dict {filepath: "ours"|"theirs"}
        if source == "stash":
            stash_ref = getattr(self, "_save_conflict_stash_ref", "")
            def _run():
                try:
                    from core.ops import save_stash_with_decisions
                    ok, err = save_stash_with_decisions(path, stash_ref, "saved changes", decisions)
                except Exception as exc:
                    ok, err = False, str(exc)
                self._merge_resolve_done_sig.emit(ok, err, "Changes saved as commit.")
            import threading as _threading
            _threading.Thread(target=_run, daemon=True).start()
            return
        def _run():
            try:
                from core.ops import merge_with_decisions
                git_source = source if source.startswith("origin/") or source in self._local_branch_tip else f"origin/{source}"
                ok, err = merge_with_decisions(path, git_source, decisions)
                if ok and source.startswith("origin/"):
                    from core.ops import _run as git_run
                    push_branch = source.removeprefix("origin/")
                    push_ok, push_err = git_run(path, ["git", "push", "origin", push_branch], timeout=30)
                    if not push_ok:
                        ok, err = False, push_err
            except Exception as exc:
                ok, err = False, str(exc)
            msg = f"Merged '{source}' into '{target}'."
            self._merge_resolve_done_sig.emit(ok, err, msg)
        import threading as _threading
        _threading.Thread(target=_run, daemon=True).start()

    def _on_merge_resolve_done(self, ok: bool, err: str, success_msg: str):
        self._panel_op_active = False
        self._navigating = False
        if ok:
            self._toast.show_message(success_msg, kind="success", duration_ms=5000)
            self._start_load()
        else:
            msg = "Timed out." if err == "timed_out" else "Couldn't finish the merge — try again."
            self._toast.show_message(msg, kind="error", duration_ms=6000)
        self._panel.unlock_actions()

    def _on_save_stash(self, sha: str, stash_ref: str, message: str, branch: str = ""):
        if not self._tracker or self._panel_op_active:
            return
        self._panel_op_active = True   # block poll so stash section stays visible
        path = self._tracker._path
        def _run():
            try:
                from core.ops import save_stash_as_commit
                ok, err, cf, cc = save_stash_as_commit(path, stash_ref, message, branch)
            except Exception as exc:
                ok, err, cf, cc = False, str(exc), [], {}
            self._stash_done_sig.emit(ok, "Changes saved as commit." if ok else err, cf, cc)
        import threading as _threading
        _threading.Thread(target=_run, daemon=True).start()

    def _on_sync_branch(self, branch: str):
        if not self._tracker or self._panel_op_active:
            return
        self._panel_op_active = True
        self._navigating = True
        self._reload_debounce.stop()
        self._toast.show_message("Syncing with remote…", kind="loading")
        path = self._tracker._path
        def _run():
            try:
                from core.ops import _run as git_run, merge_branch, checkout_branch
                import subprocess
                cur = subprocess.run(
                    ["git", "rev-parse", "--abbrev-ref", "HEAD"],
                    cwd=path, capture_output=True, text=True,
                    encoding="utf-8", errors="replace", timeout=5,
                ).stdout.strip()
                switched = False
                if cur != branch:
                    ok_co, err_co = checkout_branch(path, branch)
                    if not ok_co:
                        self._merge_done_sig.emit(False, err_co, [], f"origin/{branch}", branch, {})
                        return
                    switched = True
                old_head = subprocess.run(
                    ["git", "rev-parse", "HEAD"],
                    cwd=path, capture_output=True, text=True,
                    encoding="utf-8", errors="replace", timeout=5,
                ).stdout.strip()
                fetch_ok, fetch_err = git_run(path, ["git", "fetch", "origin"], timeout=30)
                ok, err, files, content = merge_branch(path, f"origin/{branch}")
                if ok:
                    push_ok, push_err = git_run(path, ["git", "push", "origin", branch], timeout=30)
                    if not push_ok:
                        ok, err = False, push_err
                if ok and old_head:
                    from core.ops import migrate_stash_after_pull
                    migrate_stash_after_pull(path, old_head)
                if switched:
                    checkout_branch(path, cur)
            except Exception as exc:
                ok, err, files, content = False, str(exc), [], {}
            self._merge_done_sig.emit(ok, err, files, f"origin/{branch}", branch, content)
        import threading as _threading
        _threading.Thread(target=_run, daemon=True).start()

    def _on_pull_branch(self, branch: str):
        if not self._tracker or self._panel_op_active:
            return
        from core.ops import has_uncommitted_changes
        if has_uncommitted_changes(self._tracker._path):
            self._panel.unlock_actions()
            self._pull_dirty_dialog.show_for_branch(branch)
        else:
            self._panel_op_active = True
            self._reload_debounce.stop()
            self._do_clean_pull(branch)

    def _do_clean_pull(self, branch: str):
        self._last_pull_branch = branch
        self._toast.show_message("Pulling…", kind="loading")
        path = self._tracker._path
        def _run():
            try:
                from core.ops import pull_ff
                ok, err = pull_ff(path, branch)
            except Exception as exc:
                ok, err = False, str(exc)
            self._pull_done_sig.emit(ok, err, f"Pulled latest '{branch}'.", [])
        import threading as _threading
        _threading.Thread(target=_run, daemon=True).start()

    def _on_pull_dirty_choice(self, choice: str, branch: str):
        if choice == "cancel":
            self._panel.unlock_actions()
            return
        self._last_pull_branch = branch
        self._panel_op_active = True
        self._navigating = True
        self._reload_debounce.stop()
        self._toast.show_message("Pulling…", kind="loading")
        path = self._tracker._path
        if choice == "stash_pull":
            success_msg = f"Stash re-applied on top of '{branch}'."
            def _run():
                try:
                    from core.ops import pull_stash_apply
                    ok, err = pull_stash_apply(path, branch)
                except Exception as exc:
                    ok, err = False, str(exc)
                self._pull_done_sig.emit(ok, err, success_msg, [])
        elif choice == "save_merge":
            success_msg = f"Saved changes merged with '{branch}'."
            def _run():
                try:
                    from core.ops import pull_save_merge
                    ok, err, cfiles = pull_save_merge(path, branch)
                except Exception as exc:
                    ok, err, cfiles = False, str(exc), []
                self._pull_done_sig.emit(ok, err, success_msg, cfiles)
        else:  # discard_pull
            success_msg = f"Pulled '{branch}' — local changes discarded."
            def _run():
                try:
                    from core.ops import pull_discard
                    ok, err = pull_discard(path, branch)
                except Exception as exc:
                    ok, err = False, str(exc)
                self._pull_done_sig.emit(ok, err, success_msg, [])
        import threading as _threading
        _threading.Thread(target=_run, daemon=True).start()

    def _on_pull_done(self, ok: bool, err: str, success_msg: str, conflict_files: list):
        self._panel_op_active = False
        self._navigating = False
        if ok:
            self._toast.show_message(success_msg, kind="success", duration_ms=5000)
            self._start_load()
            self._panel.unlock_actions()
        elif err == "stash_conflict":
            # Re-lock while the conflict dialog is open — _on_conflict_done will release.
            self._panel_op_active = True
            self._conflict_dialog.show_for_branch(
                getattr(self, "_last_pull_branch", ""), "PULL CONFLICT", [], arrow="←", repo_path=self._tracker._path if self._tracker else "")
        elif err == "merge_conflict":
            # Re-lock while the conflict dialog is open — _on_conflict_done will release.
            self._panel_op_active = True
            self._conflict_dialog.show_for_branch(
                getattr(self, "_last_pull_branch", ""), "PULL CONFLICT", conflict_files, arrow="←", repo_path=self._tracker._path if self._tracker else "")
        else:
            if err == "timed_out":
                msg = "Timed out."
            elif "non-fast-forward" in err or "rejected" in err or "diverge" in err.lower():
                msg = "Can't pull — your branch has diverged from remote. Merge or force-push to resolve."
            else:
                msg = "Couldn't pull — check your internet connection and try again."
            self._toast.show_message(msg, kind="error", duration_ms=6000)
            self._panel.unlock_actions()

    def _on_push_branch(self, branch: str):
        if not self._tracker or self._panel_op_active:
            return
        self._panel_op_active = True
        self._reload_debounce.stop()
        self._toast.show_message("Pushing…", kind="loading")
        path       = self._tracker._path
        username   = self._user.get("login", "")
        token      = self._user.get("access_token", "")
        remote_url = self._tracker.remote_url() if self._tracker else ""
        def _run():
            try:
                from core.ops import push_branch
                ok, err, conflict_files, conflict_content = push_branch(path, branch, username, token, remote_url)
            except Exception as exc:
                ok, err, conflict_files, conflict_content = False, str(exc), [], {}
            self._push_done_sig.emit(ok, err, branch, conflict_files, conflict_content)
        import threading as _threading
        _threading.Thread(target=_run, daemon=True).start()

    def _on_push_done(self, ok: bool, err: str, branch: str, conflict_files: list, conflict_content: object = None):
        self._panel_op_active = False
        if ok:
            if branch:
                self._toast.show_message(f"'{branch}' pushed to remote.", kind="success")
                self._panel.set_push_state(False)
            else:
                self._toast.show_message("Connected to GitHub.", kind="success", duration_ms=5000)
                self._header.set_connection_state(True)
            self._start_load()
        elif err == "behind_remote":
            self._toast.show_message(
                f"Remote has new commits — pull '{branch}' first, then push.",
                kind="error", duration_ms=6000)
            self._start_load()
            self._panel.unlock_actions()
            return
        elif err == "merge_conflict":
            self._panel_op_active = True
            self._conflict_dialog.show_for_branch(
                branch, "PUSH CONFLICT", conflict_files, arrow="→",
                prefetched_content=conflict_content or {})
            return
        else:
            msg = "Timed out." if err == "timed_out" else "Couldn't push — check your connection and try again."
            self._toast.show_message(msg, kind="error", duration_ms=6000)
        self._panel.unlock_actions()

    def _on_conflict_choice(self, choice: str, branch: str):
        if choice == "cancel":
            self._panel_op_active = False
            self._panel.unlock_actions()
            self._start_load()
            return
        self._toast.show_message("Resolving conflict…", kind="loading")
        path = self._tracker._path
        if choice == "discard":
            fn_name = "conflict_discard_local"
            success_msg = f"Local commits discarded — '{branch}' synced to remote."
        else:
            fn_name = "conflict_keep_local"
            success_msg = f"Local changes kept as new commit on '{branch}'."
        def _run():
            try:
                fn = __import__("core.ops", fromlist=[fn_name])
                ok, err = getattr(fn, fn_name)(path, branch)
            except Exception as exc:
                ok, err = False, str(exc)
            self._conflict_done_sig.emit(ok, err, success_msg)
        import threading as _threading
        _threading.Thread(target=_run, daemon=True).start()

    def _on_conflict_done(self, ok: bool, err: str, success_msg: str):
        self._panel_op_active = False
        if ok:
            self._toast.show_message(success_msg, kind="success", duration_ms=5000)
            self._start_load()
        else:
            msg = "Timed out." if err == "timed_out" else "Couldn't resolve the conflict — try again."
            self._toast.show_message(msg, kind="error", duration_ms=6000)
            self._start_load()
        self._panel.unlock_actions()

    def _on_hard_revert(self, branch: str, target_sha: str):
        _fp = not getattr(self, "_last_detail_diverged", False)
        self._run_branch_op(
            lambda p: __import__("core.ops", fromlist=["hard_revert_to"]).hard_revert_to(p, branch, target_sha, force_push=_fp),
            success_msg=f"Hard reverted '{branch}'.",
            fail_prefix="Hard revert failed",
            start_msg=f"Hard reverting '{branch}'…",
            close_panel=True,
        )

    def _on_soft_revert(self, branch: str, tip_sha: str, parent_sha: str):
        self._run_branch_op(
            lambda p: __import__("core.ops", fromlist=["soft_revert_to"]).soft_revert_to(p, branch, tip_sha, parent_sha),
            success_msg=f"Soft reverted '{branch}'.",
            fail_prefix="Soft revert failed",
            start_msg=f"Soft reverting '{branch}'…",
        )

    def _on_delete_branch(self, branch: str, parent_sha: str):
        self._run_branch_op(
            lambda p: __import__("core.ops", fromlist=["delete_branch_full"]).delete_branch_full(p, branch, parent_sha),
            success_msg=f"Branch '{branch}' deleted.",
            fail_prefix="Delete failed",
            close_panel=True,
            start_msg=f"Deleting '{branch}'…",
        )

    def _run_branch_op(self, op, success_msg: str, fail_prefix: str,
                       close_panel: bool = False, start_msg: str = ""):
        if not self._tracker or self._panel_op_active:
            return
        self._panel_op_active = True
        self._navigating = True
        # Suppress watcher reloads while the op runs — intermediate git
        # checkout/add steps would otherwise trigger a mid-op canvas rebuild.
        self._reload_debounce.stop()
        path = self._tracker._path
        def _run():
            try:
                ok, err = op(path)
            except Exception as exc:
                ok, err = False, str(exc)
            self._op_done.emit(ok, err, success_msg, fail_prefix, close_panel)
        import threading as _threading
        _threading.Thread(target=_run, daemon=True).start()

    def _on_branch_op_done(self, ok: bool, err: str, success_msg: str,
                           fail_prefix: str, close_panel: bool):
        self._panel_op_active = False
        self._navigating = False
        if ok:
            self._toast.show_message(success_msg, kind="success", duration_ms=5000)
            if close_panel:
                self._panel.hide_panel()
                self._last_branch_tips = {}
                self._last_head_sha    = ""
                self._last_stash_shas  = set()
            self._jump_to_head = True   # always scroll to new HEAD after any successful op
            self._start_load()
        else:
            msg = "Timed out." if err == "timed_out" else "Something went wrong — try again."
            self._toast.show_message(msg, kind="error", duration_ms=6000)
            if close_panel:
                self._panel.hide_panel()
                self._last_branch_tips = {}
                self._last_head_sha    = ""
                self._last_stash_shas  = set()
                self._start_load()
        self._panel.unlock_actions()

    def _on_branch_create(self, sha: str, branch_name: str):
        if not self._tracker or self._panel_op_active:
            return
        self._panel_op_active = True
        self._reload_debounce.stop()
        path = self._tracker._path
        def _run():
            try:
                from core.ops import create_branch_with_commit
                ok, err = create_branch_with_commit(path, branch_name, sha)
            except Exception as exc:
                ok, err = False, str(exc)
            self._create_done_sig.emit(ok, err, branch_name)
        import threading as _threading
        _threading.Thread(target=_run, daemon=True).start()

    def _on_branch_create_done(self, ok: bool, err: str, branch_name: str):
        self._panel_op_active = False
        if ok:
            self._toast.show_message(f"Branch '{branch_name}' created.", kind="success")
            self._panel.hide_panel()           # close stale panel (HEAD has moved to new branch)
            self._last_branch_tips = {}        # force full graph redraw
            self._last_head_sha    = ""        # so load_graph reads actual HEAD (new empty commit)
            self._last_stash_shas  = set()     # defensive cleanup
            self._jump_to_head     = True      # scroll canvas to new branch's tip commit
            self._start_load()
        else:
            self._toast.show_message("Couldn't create that branch — the name may already be taken.", kind="error", duration_ms=6000)
            self._start_load()
        self._panel.unlock_actions()

    @staticmethod
    def _alpha(s: str) -> str:
        return re.sub(r'[^a-z]', '', s.lower())

    def _compute_you_shas(self, commits, gh_name: str = "") -> set:
        """Return SHAs of all commits authored by the logged-in user.
        Every such commit shows 'You' as the text label for consistency."""
        login = self._user.get("login", "")
        if not login:
            return set()
        nl = self._alpha(login)
        nn = self._alpha(gh_name)
        result = set()
        for commit in commits:
            na = self._alpha(commit.author)
            if not na:
                continue
            if (nl and (nl == na or nl in na or na in nl)) or \
               (nn and (nn == na or nn in na or na in nn)):
                result.add(commit.sha)
        return result

    def _find_latest_commit_for_login(self, login: str, gh_name: str = "",
                                       tip_shas: set = None) -> Optional[CommitInfo]:
        """Find the latest commit by this user.
        When tip_shas is provided, prefer a tip commit over a non-tip one
        so the avatar badge lands on the user's latest pushed/local head —
        but only when that tip commit is at least as recent as their overall
        latest commit.  This prevents stale remote branches (merged into main
        but never deleted) from pulling the badge back to an older commit."""
        if not self._commits:
            return None
        nl = self._alpha(login)
        nn = self._alpha(gh_name)
        user_commits = []
        for commit in self._commits:
            na = self._alpha(commit.author)
            if not na:
                continue
            if (nl and (nl == na or nl in na or na in nl)) or \
               (nn and (nn == na or nn in na or na in nn)):
                user_commits.append(commit)
        if not user_commits:
            return None
        best_overall = max(user_commits, key=lambda c: c.date)
        if tip_shas:
            tip_matches = [c for c in user_commits if c.sha in tip_shas]
            if tip_matches:
                best_tip = max(tip_matches, key=lambda c: c.date)
                if best_tip.date >= best_overall.date:
                    return best_tip
        return best_overall

    def _place_contributor_badges(self):
        enriched    = []
        badge_data  = []
        known_authors: set[str] = set()

        _has_remote = bool(self._tracker and self._tracker.has_remote())
        _badge_tips = self._remote_tip_shas if _has_remote else set(self._local_tip_branch.keys())

        for collab in self._collaborators:
            login   = collab.get("login", "")
            gh_name = collab.get("gh_name", "")
            commit  = self._find_latest_commit_for_login(login, gh_name, tip_shas=_badge_tips)
            is_self = login == self._user.get("login", "")
            enriched.append({**collab, "display_name": "You" if is_self else (commit.author if commit else None)})
            if commit:
                badge_data.append({
                    "login":      login,
                    "avatar_url": collab.get("avatar_url", ""),
                    "sha":        commit.sha,
                    "color":      _person_color(login),
                })
            # Collect every git author name that maps to this collaborator
            nl = self._alpha(login)
            nn = self._alpha(gh_name)
            for c in self._commits:
                na = self._alpha(c.author)
                if (nl and (nl == na or nl in na or na in nl)) or \
                   (nn and (nn == na or nn in na or na in nn)):
                    known_authors.add(c.author)

        you_gh_name = next(
            (c.get("gh_name", "") for c in self._collaborators
             if c.get("login") == self._user.get("login")), ""
        )
        self._you_shas = self._compute_you_shas(self._commits, you_gh_name)
        self._canvas.refresh_you_labels(self._you_shas)
        self._canvas.set_known_authors(known_authors)

        author_display: dict[str, str] = {}
        for entry in enriched:
            display = entry.get("display_name") or ""
            if display:
                for c in self._commits:
                    nl = self._alpha(entry.get("login", ""))
                    nn = self._alpha(entry.get("gh_name", ""))
                    na = self._alpha(c.author)
                    if (nl and (nl == na or nl in na or na in nl)) or \
                       (nn and (nn == na or nn in na or na in nn)):
                        author_display[c.author] = display
        self._author_display_map = author_display

        collab_names = [e["display_name"] for e in enriched if e.get("display_name")]
        self._filter_rebuilding = True
        self._filter_panel.set_authors(collab_names)
        self._filter_rebuilding = False

        self._settings_panel.load_collaborators(enriched, current_login=self._user.get("login", ""))
        self._canvas.load_contributor_avatars(badge_data)

    def _on_collaborator_clicked(self, login: str):
        collab  = next((c for c in self._collaborators if c.get("login") == login), {})
        gh_name = collab.get("gh_name", "")
        commit  = self._find_latest_commit_for_login(login, gh_name)
        if not commit:
            return
        self._canvas.jump_to_commit(commit.sha)
        detail = self._tracker.commit_detail(commit.sha) if self._tracker else {}
        files  = self._tracker.commit_files(commit.sha) if self._tracker else []
        is_you = commit.sha in self._you_shas
        if is_you:
            display_author = "You"
        else:
            display_author = collab.get("gh_name") or collab.get("login", "")
        self._panel.show_commit(commit, detail, collab.get("avatar_url", ""), display_author, files)

    def _on_commit_clicked(self, commit: CommitInfo):
        self._changes_panel.hide_panel()
        self._panel.deselect_files()
        if not self._tracker:
            return


        if self._detail_thread and self._detail_thread.isRunning():
            self._detail_thread.quit()
            # Park in _inflight so Python doesn't GC the wrapper while C++ thread is live
            pair = [self._detail_thread, self._detail_worker]
            self._inflight.append(pair)
            self._detail_thread.finished.connect(lambda p=pair: self._drop_inflight(p))

        self._detail_gen += 1
        gen = self._detail_gen

        thread = QThread()
        worker = _CommitDetailWorker(self._tracker._path, commit, gen)
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.finished.connect(self._on_commit_detail_ready)
        worker.finished.connect(thread.quit)
        thread.finished.connect(lambda t=thread: self._on_detail_thread_done(t))
        self._detail_thread = thread
        self._detail_worker = worker
        thread.start()

    def _on_commit_detail_ready(self, commit: CommitInfo, detail: dict, files: list, gen: int):
        if gen != self._detail_gen:
            return
        is_you = commit.sha in self._you_shas
        collab = next(
            (c for c in self._collaborators
             if self._alpha(c.get("login", "")) and
             (self._alpha(c.get("login", "")) in self._alpha(commit.author) or
              self._alpha(commit.author) in self._alpha(c.get("login", "")) or
              (c.get("gh_name") and self._alpha(c.get("gh_name", "")) in self._alpha(commit.author)))),
            {}
        )
        if is_you:
            display_author = "You"
        elif collab:
            display_author = collab.get("gh_name") or collab.get("login", "")
        else:
            display_author = ""   # not a known collaborator — show "—"
        self._panel.show_commit(commit, detail, collab.get("avatar_url", ""), display_author, files)
        has_remote = bool(self._tracker and self._tracker.has_remote())
        can_push = has_remote and (commit.sha in self._last_unpushed or
                                   commit.branch in self._last_local_only)
        # True when the branch exists on remote (not local-only) and a remote is configured.
        is_remote_branch = has_remote and commit.branch not in self._last_local_only
        # Determine branch state: ahead / behind / diverged
        local_sha  = next((s for s, n in self._local_tip_branch.items()
                           if n == commit.branch), None)
        remote_sha = next(
            (s for s, names in self._last_branch_tips.items()
             if commit.branch in names and s not in self._local_tip_branch),
            None
        )
        is_behind = False
        is_diverged = False
        if local_sha and remote_sha and local_sha != remote_sha:
            _cmap = {c.sha: c for c in self._commits}
            _sha, _vis = local_sha, set()
            _local_ahead = False
            while _sha and _sha in _cmap and _sha not in _vis:
                _vis.add(_sha)
                if _sha == remote_sha:
                    _local_ahead = True
                    break
                _c = _cmap[_sha]
                _sha = _c.parents[0] if _c.parents else None
            _sha, _vis = remote_sha, set()
            _local_behind = False
            while _sha and _sha in _cmap and _sha not in _vis:
                _vis.add(_sha)
                if _sha == local_sha:
                    _local_behind = True
                    break
                _c = _cmap[_sha]
                _sha = _c.parents[0] if _c.parents else None
            is_behind = _local_behind
            is_diverged = not _local_ahead and not _local_behind

        self._last_detail_diverged = is_diverged

        # Mutually exclusive: Upload / Pull / Sync
        if is_diverged:
            is_local_tip = commit.sha in self._local_tip_shas
            is_current_head = commit.sha == self._last_head_sha
            self._panel.set_push_state(False, commit.branch)
            self._panel.set_pull_state(False, commit.branch)
            self._panel.set_sync_state(is_local_tip, commit.branch)
        elif is_behind:
            self._panel.set_push_state(False, commit.branch)
            self._panel.set_pull_state(True, commit.branch)
            self._panel.set_sync_state(False, commit.branch)
        else:
            self._panel.set_push_state(can_push, commit.branch)
            self._panel.set_pull_state(False, commit.branch)
            self._panel.set_sync_state(False, commit.branch)

        # Commit actions — follow same source of truth as the red dot.
        # Suppress all actions while another operation is in progress.
        is_head = commit.sha in self._branch_head_shas and not self._panel_op_active
        # Remote tip: a branch tip that exists on the remote but not locally checked out.
        # Used to gate the Delete button for remote-only / multi-commit branches.
        is_remote_head = (commit.sha in self._remote_tip_shas) and not self._panel_op_active
        # Use the real git branch name for this tip, not the lane algo's assignment
        branch     = self._local_tip_branch.get(commit.sha, commit.branch)

        # Merge button — shown on branch heads, but not on merge commits
        # (re-merging from a merge commit causes broken state)
        # Use branch_tip_map (includes remote-only labels) filtered to commits
        # currently visible in the graph. Remote-only branches are resolved to
        # origin/<name> at merge time (see _on_merge_branch).
        _visible = {c.sha for c in self._commits}
        _seen: set = set()
        _all: list = []
        for _tip_sha, _names in self._branch_tip_map.items():
            if _tip_sha in _visible:
                for _name in _names:
                    if _name != branch and _name not in _seen:
                        _seen.add(_name)
                        _all.append(_name)
        all_branches = sorted(_all)
        is_merge_commit = len(commit.parents) > 1
        show_merge = is_head and bool(branch) and len(all_branches) > 0
        print(f"[merge] sha={commit.sha[:8]} branch={branch} is_head={is_head} all_branches={all_branches} is_merge_commit={is_merge_commit} show_merge={show_merge}")
        _dflt = getattr(self._settings_panel, "_default_branch", "main")
        _branch_colors = getattr(self._canvas, "_branch_colors", {})
        self._panel.set_merge_state(show_merge, branch, all_branches,
                                    default_branch=_dflt, branch_colors=_branch_colors)
        has_parent = len(commit.parents) > 0
        parent_sha = commit.parents[0] if commit.parents else ""
        # "Main" = default branch by name, OR any branch that exists on remote
        is_main = branch == getattr(self._settings_panel, "_default_branch", "main")

        parent_branch = self._sha_to_branch.get(parent_sha, "")
        canonical_branch = commit.branch  # lane-assigned; stable when multiple local branches share a SHA
        branch_commit_count = sum(1 for b in self._sha_to_branch.values() if b == canonical_branch)
        is_first = not has_parent or (
            not is_merge_commit
            and parent_branch
            and parent_branch != canonical_branch
            and branch_commit_count <= 1
        )

        self._panel.set_commit_actions(
            branch=branch,
            parent_sha=parent_sha,
            has_parent=has_parent,
            is_first_of_branch=is_first,
            is_main=is_main,
            is_head=is_head,
            is_remote_head=is_remote_head,
            is_merge_commit=is_merge_commit,
            branch_depth=self._branch_depths.get(branch, 0),
            is_remote_branch=is_remote_branch,
            is_remote_only=commit.sha in self._canvas._future_shas,
        )

    def _on_detail_thread_done(self, thread: QThread):
        if self._detail_thread is thread:
            self._detail_thread = None

    def _on_navigate(self, sha: str):
        if not self._tracker:
            return
        if self._panel_op_active:
            self._toast.show_message("Another operation is in progress — please wait.", kind="info")
            return
        if self._navigate_thread and self._navigate_thread.isRunning():
            self._toast.show_message("Navigation already in progress — please wait.", kind="info")
            return

        # If there are unsaved changes, auto-stash and navigate immediately.
        if self._last_dirty:
            self._launch_navigate(sha, discard=False)
            return

        self._launch_navigate(sha)

    def _launch_navigate(self, sha: str, discard: bool = False):
        """Spawn the navigate worker. Called directly (no dirty changes) or
        after the user has made a choice in _NavigateDirtyDialog."""
        # Block fs watcher reloads for the entire duration of the checkout
        # so the Loader thread can't start reading git state mid-checkout.
        self._navigating = True
        self._panel_op_active = True
        self._reload_debounce.stop()
        self._toast.show_message("Switching…", kind="loading")

        self._nav_gen += 1
        gen = self._nav_gen
        current_head = self._tracker.head_sha()
        self._navigate_thread = QThread()
        self._navigate_worker = _NavigateWorker(
            self._tracker._path, sha, current_head, discard=discard,
        )
        self._navigate_worker.moveToThread(self._navigate_thread)
        self._navigate_thread.started.connect(self._navigate_worker.run)
        self._navigate_worker.finished.connect(lambda ok, err, _gen=gen: self._on_navigate_done(ok, err, _gen))
        self._navigate_worker.finished.connect(self._navigate_thread.quit)
        self._navigate_thread.finished.connect(lambda: setattr(self, '_navigate_thread', None))
        self._navigate_thread.start()

    def _on_navigate_dirty_choice(self, choice: str, sha: str):
        if choice == "cancel":
            self._panel.unlock_actions()
            return
        self._launch_navigate(sha, discard=(choice == "discard"))

    def _on_navigate_done(self, ok: bool, err: str, gen: int = 0):
        # Stale-worker guard: if a newer navigate was launched, ignore this result.
        if gen != 0 and gen != self._nav_gen:
            return
        self._navigating = False
        self._panel_op_active = False
        self._panel.unlock_actions()
        if not ok:
            if err == "auto-save-failed":
                self._toast.show_message(
                    "Couldn't auto-save your changes. Commit them first, then retry.",
                    kind="error", duration_ms=7000,
                )
            elif err.startswith("discard-failed"):
                self._toast.show_message(
                    "Couldn't discard changes — try manually with git reset.",
                    kind="error", duration_ms=6000,
                )
            else:
                self._toast.show_message(
                    "Couldn't switch to that snapshot — try again.",
                    kind="error",
                )
            self._start_load()
            return
        if err == "stash-conflict":
            self._toast.show_message(
                "Switched to snapshot — saved changes couldn't be restored (conflict).",
                kind="error", duration_ms=6000,
            )
        self._start_load()

    def _poll_uncommitted(self):
        if not self._tracker or self._navigating or self._panel_op_active:
            return
        if self._uncommitted_thread is not None:
            return
        thread = QThread()
        worker = _UncommittedRefreshWorker(self._tracker._path)
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.finished.connect(self._on_uncommitted_done)
        worker.finished.connect(thread.quit)
        # Clear the thread ref once it stops so the next poll can proceed.
        # Do NOT call worker.deleteLater — Python owns the worker via
        # self._uncommitted_worker; mixing deleteLater with Python GC causes a
        # double-free that crashes the process.
        thread.finished.connect(self._on_uncommitted_thread_done)
        self._uncommitted_thread = thread
        self._uncommitted_worker = worker
        thread.start()

    def _on_uncommitted_thread_done(self):
        self._uncommitted_thread = None
        # Leave _uncommitted_worker — Python drops it naturally when the next
        # poll overwrites the reference (safe: the thread has already stopped).

    def _on_uncommitted_done(self, dirty: bool, files: list, stash_id: str):
        if not self._tracker:
            return
        head_sha = self._tracker.head_sha()

        stash_changed = stash_id != self._last_stash_id
        dirty_changed = dirty != self._last_dirty
        if stash_changed:
            self._last_stash_id = stash_id
        if dirty_changed:
            self._last_dirty = dirty

        # Trigger a graph rebuild whenever state changes (updates amber dots etc.)
        if dirty_changed or stash_changed:
            self._start_load()

        # Always push the current file list into the panel if it is open and
        # showing HEAD — this handles additions, removals, and going fully clean.
        if self._panel._visible:
            panel_sha = getattr(self._panel, "_current_sha", "")
            if panel_sha == head_sha:
                self._panel.update_uncommitted_files(files)
            elif stash_changed:
                self._panel.refresh_stash_section()

    def _branch_for_head(self) -> str:
        if not self._tracker:
            return ""
        path   = self._tracker._path
        branch = current_branch(path)
        if branch:
            return branch
        head = self._tracker.head_sha()
        if head:
            return branch_for_commit(path, head)
        return ""

    def _avatar_url_for_author(self, author: str) -> str:
        na = re.sub(r'[^a-z]', '', author.lower())
        for collab in self._collaborators:
            nl = re.sub(r'[^a-z]', '', collab.get("login", "").lower())
            nn = re.sub(r'[^a-z]', '', (collab.get("gh_name", "") or "").lower())
            if (nl and (nl == na or nl in na or na in nl)) or \
               (nn and (nn == na or nn in na or na in nn)):
                return collab.get("avatar_url", "")
        return ""

    def _reposition_position(self):
        margin = 16
        pp = self._position_panel
        pp.adjustSize()
        pp.move(margin, self._header.height() + margin)

    def toggle_filter_panel(self):
        visible = not self._filter_panel.isVisible()
        self._filter_panel.setVisible(visible)
        self._filter_btn.setChecked(visible)
        if visible:
            self._filter_panel.raise_()
            self._reposition_filter()

    def _set_orientation(self, orient: str):
        if orient == self._orientation:
            return
        self._orientation = orient
        self._orient_bar.set_orientation(orient)
        if self._tracker:
            orientations = settings_store.get("repo_orientations", {})
            orientations[self._tracker._path] = orient
            settings_store.save({"repo_orientations": orientations})
        if self._commits:
            # is_initial=True: prev_centre is captured in the OLD orientation's
            # coordinate space, but lane/row axes swap between orientations, so
            # those scene coordinates point at an unrelated spot in the new
            # layout. Skip restoring prev_centre and re-centre on HEAD instead
            # (load_graph falls back to an orientation-appropriate default if
            # head_sha isn't found).
            self._canvas.load_graph(
                self._commits,
                self._last_branch_tips,
                you_shas=self._you_shas,
                local_only_branches=self._last_local_only,
                unpushed_shas=self._last_unpushed,
                remote_tip_shas=self._remote_tip_shas,
                orientation=orient,
                head_sha=self._last_head_sha,
                is_initial=True,
            )

    def _apply_canvas_filter(self):
        if self._filter_rebuilding or not self._commits:
            return
        active_branches = self._filter_panel.active_branches()
        active_authors  = self._filter_panel.active_authors()
        all_branches    = self._filter_panel._all_branches()
        all_authors     = self._filter_panel._all_authors()
        if active_branches == all_branches and active_authors == all_authors:
            self._canvas.apply_commit_filter(set())
            return
        dimmed: set[str] = set()
        for commit in self._commits:
            display   = self._author_display_map.get(commit.author, commit.author)
            tip_names = self._branch_tip_map.get(commit.sha, [])
            non_main_tips = [n for n in tip_names if n not in ('main', 'master')]
            effective_branch = (
                non_main_tips[0]
                if (non_main_tips and commit.branch in ('main', 'master'))
                else commit.branch
            )
            branch_ok = (
                (not effective_branch)
                or (effective_branch in active_branches)
            )
            author_ok = (display in active_authors) if (display in all_authors) else True
            if not branch_ok or not author_ok:
                dimmed.add(commit.sha)
        self._canvas.apply_commit_filter(dimmed)

    def _reposition_filter(self):
        fp = self._filter_panel
        fp.adjustSize()
        fb = self._filter_btn
        # Align left edge with button, pop up above it
        x = fb.x()
        y = fb.y() - fp.height() - 8
        # Clamp so panel doesn't clip outside the window
        x = max(8, min(x, self.width() - fp.width() - 8))
        y = max(self._header.height() + 8, y)
        fp.move(x, y)

    # ── Resize ────────────────────────────────────────────────────────────

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._panel.reposition()
        self._changes_panel.reposition()
        self._loading.setGeometry(self.rect())
        if self._conflict_dialog.isVisible():
            self._conflict_dialog.setGeometry(self.rect())
        if self._pull_dirty_dialog.isVisible():
            self._pull_dirty_dialog.setGeometry(self.rect())
        if self._navigate_dirty_dialog.isVisible():
            self._navigate_dirty_dialog.setGeometry(self.rect())
        if self._github_connect_dialog.isVisible():
            self._github_connect_dialog.setGeometry(self.rect())
        if self._merge_conflict_dialog.isVisible():
            self._merge_conflict_dialog.setGeometry(self.rect())
        margin = 16
        mm = self._minimap
        mm.move(margin, self.height() - mm.MAP_H - margin)
        zb = self._zoom_bar
        zb.move(margin + mm.MAP_W + margin,
                self.height() - zb.height() - margin)
        ob = self._orient_bar
        ob.adjustSize()
        ob.move(margin + mm.MAP_W + margin + zb.width() + margin,
                self.height() - ob.height() - margin)
        fb = self._filter_btn
        fb.adjustSize()
        fb.move(margin + mm.MAP_W + margin + zb.width() + margin + ob.width() + margin,
                self.height() - fb.height() - margin)
        # PR panel is now in the content stack — no float button to reposition
        if self._position_panel.isVisible():
            self._reposition_position()
        if self._filter_panel.isVisible():
            self._reposition_filter()
        self._toast.reposition()


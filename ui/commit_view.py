from __future__ import annotations

from typing import Optional

import hashlib
import os
import re
import threading

from PyQt5.QtCore import Qt, QThread, QObject, QTimer, QFileSystemWatcher, pyqtSlot, pyqtSignal
from PyQt5.QtGui import QPainter, QColor, QBrush, QPen, QPixmap, QPainterPath, QFont
from PyQt5.QtCore import QRect, QPropertyAnimation, QEasingCurve
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QScrollArea, QFrame, QLineEdit, QCheckBox, QStackedWidget, QSizePolicy,
)
from styles.theme import COLORS
from core.git_tracker import GitTracker, CommitInfo
from core.git_ops import (current_branch, branch_for_commit,
                          has_uncommitted_changes, create_auto_stash,
                          pop_auto_stash, apply_stash, drop_stash,
                          checkout_commit, checkout_branch,
                          get_stash_files, get_stash_ref_for_commit)
from core import settings_store
from core import collab_cache
from ui.spatial_canvas import SpatialCanvas, MiniMap, ORIENT_TB, ORIENT_BT, ORIENT_LR, ORIENT_RL
from ui.detail_panel import DetailPanel, ChangesPanel, PANEL_W as DETAIL_PANEL_W, CHANGES_W, _VScrollArea
from ui.position_panel import PositionPanel
from ui.settings_panel import SettingsPanel
from ui.pr_panel import PullRequestsPanel


# ── Avatar disk + memory cache ────────────────────────────────────────────────
_AVATAR_CACHE: dict[str, QPixmap] = {}
_AVATAR_DIR = os.path.join(os.path.expanduser("~"), ".gitdummy_cache", "avatars")
os.makedirs(_AVATAR_DIR, exist_ok=True)


def _avatar_disk_path(url: str) -> str:
    return os.path.join(_AVATAR_DIR, hashlib.md5(url.encode()).hexdigest() + ".png")


def _load_avatar(url: str) -> "QPixmap | None":
    if url in _AVATAR_CACHE:
        return _AVATAR_CACHE[url]
    path = _avatar_disk_path(url)
    if os.path.exists(path):
        pm = QPixmap(path)
        if not pm.isNull():
            _AVATAR_CACHE[url] = pm
            return pm
    return None


def _save_avatar(url: str, pm: QPixmap):
    _AVATAR_CACHE[url] = pm
    try:
        pm.save(_avatar_disk_path(url), "PNG")
    except Exception:
        pass


# ── Background loaders ───────────────────────────────────────────────────────

class _CollabLoader(QObject):
    """Fetches collaborators on a worker thread, emits list to main thread."""
    finished = pyqtSignal(list)

    def __init__(self, path: str, token: str):
        super().__init__()
        self._path  = path
        self._token = token

    @pyqtSlot()
    def run(self):
        t = GitTracker(self._path)
        try:
            t.open()
            result = t.get_collaborators(self._token)
        except Exception:
            result = []
        finally:
            t.close()
        self.finished.emit(result)


class _Loader(QObject):
    finished = pyqtSignal(list, dict, set, set, set)  # commits, branch_tip_map, local_only, unpushed, stash_shas

    def __init__(self, path: str):
        super().__init__()
        self._path = path

    @pyqtSlot()
    def run(self):
        t = GitTracker(self._path)
        try:
            t.open()
            commits, branch_tip_map, local_only = t.graph_commits()
            unpushed = t.get_unpushed_shas()
            from core.git_ops import get_stash_commit_shas, has_uncommitted_changes
            stash_shas = get_stash_commit_shas(self._path)
            # Always mark HEAD with the dot when the working tree is dirty,
            # even before the user has navigated anywhere (no stash yet).
            if has_uncommitted_changes(self._path):
                head = t.head_sha()
                if head:
                    stash_shas = stash_shas | {head}
        except Exception:
            commits, branch_tip_map, local_only, unpushed, stash_shas = [], {}, set(), set(), set()
        finally:
            t.close()
        self.finished.emit(commits, branch_tip_map, local_only, unpushed, stash_shas)


class _CommitDetailWorker(QObject):
    finished = pyqtSignal(object, dict, list, int)   # commit, detail, files, gen

    def __init__(self, path: str, commit, gen: int):
        super().__init__()
        self._path   = path
        self._commit = commit
        self._gen    = gen

    @pyqtSlot()
    def run(self):
        t = GitTracker(self._path)
        try:
            t.open()
            detail = t.commit_detail(self._commit.sha)
            files  = t.commit_files(self._commit.sha)
        except Exception:
            detail, files = {}, []
        finally:
            t.close()
        self.finished.emit(self._commit, detail, files, self._gen)


class _VisibilityWorker(QObject):
    finished = pyqtSignal(str, str)   # url, visibility

    def __init__(self, path: str, token: str):
        super().__init__()
        self._path  = path
        self._token = token

    @pyqtSlot()
    def run(self):
        t = GitTracker(self._path)
        try:
            t.open()
            url = t.remote_url()
            vis = t.repo_visibility(self._token)
        except Exception:
            url, vis = "", ""
        finally:
            t.close()
        self.finished.emit(url, vis)


class _FetchWorker(QObject):
    finished = pyqtSignal(bool)   # True = something changed

    def __init__(self, path: str):
        super().__init__()
        self._path = path

    @pyqtSlot()
    def run(self):
        t = GitTracker(self._path)
        try:
            t.open()
            changed = t.fetch()
        except Exception:
            changed = False
        finally:
            t.close()
        self.finished.emit(changed)


class _UncommittedRefreshWorker(QObject):
    """Lightweight background poll: dirty-state check + live diff + stash fingerprint."""
    finished = pyqtSignal(bool, list, str)   # dirty, files, stash_id

    def __init__(self, path: str):
        super().__init__()
        self._path = path

    @pyqtSlot()
    def run(self):
        from core.git_ops import has_uncommitted_changes, get_working_dir_diff_files, get_stash_list_id
        dirty = has_uncommitted_changes(self._path)
        files = get_working_dir_diff_files(self._path) if dirty else []
        stash_id = get_stash_list_id(self._path)
        self.finished.emit(dirty, files, stash_id)


class _NavigateWorker(QObject):
    """Runs stash-save / checkout / stash-restore on a background thread."""
    finished = pyqtSignal(bool, str)   # ok, error_message

    def __init__(self, path: str, sha: str, current_head: str):
        super().__init__()
        self._path         = path
        self._sha          = sha
        self._current_head = current_head

    @pyqtSlot()
    def run(self):
        from core.git_ops import (
            has_uncommitted_changes, get_stash_ref_for_commit,
            drop_stash, create_auto_stash, pop_auto_stash,
            checkout_commit, apply_stash, reset_hard,
        )
        path = self._path
        sha  = self._sha

        created_stash_id = None
        if has_uncommitted_changes(path):
            if self._current_head:
                old_ref = get_stash_ref_for_commit(path, self._current_head)
                if old_ref:
                    drop_stash(path, old_ref)
            stashed_files, created_stash_id = create_auto_stash(path)
            if not created_stash_id and has_uncommitted_changes(path):
                self.finished.emit(False, "auto-save-failed")
                return

        ok, err = checkout_commit(path, sha)
        if not ok:
            if created_stash_id:
                pop_auto_stash(path, created_stash_id)
            self.finished.emit(False, err)
            return

        target_ref = get_stash_ref_for_commit(path, sha)
        if target_ref:
            if not apply_stash(path, target_ref):
                # Stash had conflicts — abort the partial apply so the index
                # isn't left with unmerged paths (which would break the next
                # navigation attempt with an "auto-save-failed" error).
                reset_hard(path)
                self.finished.emit(True, "stash-conflict")
                return

        self.finished.emit(True, "")


class _FirstCommitWorker(QObject):
    finished = pyqtSignal(bool)

    def __init__(self, path: str):
        super().__init__()
        self._path = path

    @pyqtSlot()
    def run(self):
        import subprocess
        subprocess.run(["git", "add", "."], cwd=self._path, capture_output=True)
        r = subprocess.run(
            ["git", "commit", "-m", "First commit"],
            cwd=self._path, capture_output=True,
        )
        self.finished.emit(r.returncode == 0)


class _CreateRepoWorker(QObject):
    finished = pyqtSignal(bool, str, str)   # success, error, clone_url

    def __init__(self, repo_path: str, repo_name: str, token: str, username: str,
                 private: bool = True, user_name: str = "", user_email: str = ""):
        super().__init__()
        self._path       = repo_path
        self._name       = repo_name
        self._token      = token
        self._username   = username
        self._private    = private
        self._user_name  = user_name
        self._user_email = user_email

    @pyqtSlot()
    def run(self):
        from core.git_ops import create_github_repo, push_to_github
        ok, err, clone_url = create_github_repo(self._name, self._private, self._token)
        if not ok:
            self.finished.emit(False, err, "")
            return
        ok, err = push_to_github(self._path, clone_url, self._username, self._token,
                                 self._user_name, self._user_email)
        self.finished.emit(ok, err, clone_url)


# ── Loading overlay ───────────────────────────────────────────────────────────

class _LoadingOverlay(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setStyleSheet(f"background: {COLORS['bg_primary']};")
        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignCenter)
        lbl = QLabel("Loading commits…")
        lbl.setStyleSheet(f"background: transparent; font-size: 15px; color: {COLORS['text_muted']};")
        layout.addWidget(lbl)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if self.parent():
            self.setGeometry(self.parent().rect())


# ── Tab bar ───────────────────────────────────────────────────────────────────

class _TabBar(QWidget):
    tab_changed = pyqtSignal(str)   # "local" or "remote"

    _ACTIVE = f"""
        QPushButton {{
            background: {COLORS['accent']}; border: none; border-radius: 6px;
            color: white; font-size: 12px; font-weight: 600; padding: 4px 16px;
        }}
    """
    _INACTIVE = f"""
        QPushButton {{
            background: transparent; border: none; border-radius: 6px;
            color: {COLORS['text_muted']}; font-size: 12px; padding: 4px 16px;
        }}
        QPushButton:hover {{ color: {COLORS['text_primary']}; }}
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setStyleSheet(f"background: {COLORS['bg_primary']}; border-radius: 8px;")

        layout = QHBoxLayout(self)
        layout.setContentsMargins(3, 3, 3, 3)
        layout.setSpacing(0)

        self._local  = QPushButton("Local")
        self._remote = QPushButton("Remote")
        for btn in (self._local, self._remote):
            btn.setCursor(Qt.PointingHandCursor)
            layout.addWidget(btn)

        self._local.clicked.connect(lambda: self._activate("local"))
        self._remote.clicked.connect(lambda: self._activate("remote"))
        self._activate("remote", emit=False)

    def _activate(self, mode: str, emit: bool = True):
        self._local.setStyleSheet( self._ACTIVE   if mode == "local"  else self._INACTIVE)
        self._remote.setStyleSheet(self._ACTIVE   if mode == "remote" else self._INACTIVE)
        if emit:
            self.tab_changed.emit(mode)

    def set_mode(self, mode: str):
        self._activate(mode, emit=False)


# ── No-remote prompt ──────────────────────────────────────────────────────────

class _NoRemoteView(QWidget):
    create_requested = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setStyleSheet(f"background: {COLORS['bg_primary']};")

        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignCenter)
        layout.setSpacing(12)

        icon = QLabel("☁")
        icon.setStyleSheet(f"background: transparent; font-size: 52px; color: {COLORS['text_muted']};")
        icon.setAlignment(Qt.AlignCenter)
        layout.addWidget(icon)

        title = QLabel("Not on GitHub yet")
        title.setStyleSheet(
            f"background: transparent; font-size: 17px; font-weight: 700; color: {COLORS['text_primary']};"
        )
        title.setAlignment(Qt.AlignCenter)
        layout.addWidget(title)

        sub = QLabel("Create a GitHub repository to back up your commits to the cloud.")
        sub.setStyleSheet(f"background: transparent; font-size: 13px; color: {COLORS['text_muted']};")
        sub.setAlignment(Qt.AlignCenter)
        sub.setWordWrap(True)
        layout.addWidget(sub)

        layout.addSpacing(8)

        self._btn = QPushButton("Create Repository →")
        self._btn.setFixedHeight(44)
        self._btn.setCursor(Qt.PointingHandCursor)
        self._btn.setStyleSheet(f"""
            QPushButton {{
                background: {COLORS['accent']}; border: none; border-radius: 8px;
                color: white; font-size: 13px; font-weight: 600; padding: 0 28px;
            }}
            QPushButton:hover {{ background: {COLORS['accent_dim']}; }}
            QPushButton:disabled {{ background: {COLORS['border']}; color: {COLORS['text_muted']}; }}
        """)
        self._btn.clicked.connect(self.create_requested)
        layout.addWidget(self._btn, 0, Qt.AlignCenter)

        self._status = QLabel("")
        self._status.setStyleSheet(f"background: transparent; font-size: 12px; color: {COLORS['text_muted']};")
        self._status.setAlignment(Qt.AlignCenter)
        layout.addWidget(self._status)

    def set_creating(self, creating: bool):
        self._btn.setEnabled(not creating)
        self._btn.setText("Creating…" if creating else "Create Repository →")
        self._status.setText("This may take a moment…" if creating else "")

    def set_error(self, msg: str):
        self._btn.setEnabled(True)
        self._btn.setText("Try again →")
        self._status.setStyleSheet(f"background: transparent; font-size: 12px; color: #ef4444;")
        self._status.setText(msg)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if self.parent():
            self.setGeometry(self.parent().rect())


# ── No-remote banner ─────────────────────────────────────────────────────────

class _NoRemoteBanner(QWidget):
    create_requested = pyqtSignal(str, bool)  # name, is_private

    _PILL = """
        QPushButton {{
            background: {bg}; border: 1px solid {border};
            border-radius: 5px; color: {fg};
            font-size: 11px; font-weight: 600; padding: 3px 12px;
        }}
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setStyleSheet(f"background: #13131f; border-bottom: 1px solid {COLORS['border']};")
        self.setFixedHeight(52)
        self._is_private = True

        layout = QHBoxLayout(self)
        layout.setContentsMargins(20, 0, 20, 0)
        layout.setSpacing(10)

        icon = QLabel("☁")
        icon.setStyleSheet(f"background: transparent; font-size: 15px; color: {COLORS['text_muted']};")
        layout.addWidget(icon)

        msg = QLabel("Not on GitHub yet —")
        msg.setStyleSheet(f"background: transparent; font-size: 12px; color: {COLORS['text_muted']};")
        layout.addWidget(msg)

        self._name_input = QLineEdit()
        self._name_input.setPlaceholderText("repository name")
        self._name_input.setFixedSize(180, 30)
        self._name_input.setStyleSheet(f"""
            QLineEdit {{
                background: {COLORS['bg_card']}; border: 1px solid {COLORS['border']};
                border-radius: 6px; color: {COLORS['text_primary']};
                font-size: 12px; padding: 0 10px;
            }}
            QLineEdit:focus {{ border-color: {COLORS['accent']}; }}
        """)
        layout.addWidget(self._name_input)

        self._priv_btn = QPushButton("Private")
        self._pub_btn  = QPushButton("Public")
        for btn in (self._priv_btn, self._pub_btn):
            btn.setCursor(Qt.PointingHandCursor)
            btn.setFixedHeight(30)
        self._priv_btn.clicked.connect(lambda: self._set_privacy(True))
        self._pub_btn.clicked.connect(lambda: self._set_privacy(False))
        layout.addWidget(self._priv_btn)
        layout.addWidget(self._pub_btn)
        self._set_privacy(True, emit=False)

        layout.addStretch()

        self._btn = QPushButton("Create →")
        self._btn.setCursor(Qt.PointingHandCursor)
        self._btn.setFixedHeight(30)
        self._btn.setStyleSheet(f"""
            QPushButton {{
                background: {COLORS['accent']}; border: none; border-radius: 6px;
                color: white; font-size: 12px; font-weight: 600; padding: 0 16px;
            }}
            QPushButton:hover {{ background: {COLORS['accent_dim']}; }}
            QPushButton:disabled {{ background: {COLORS['border']}; color: {COLORS['text_muted']}; }}
        """)
        self._btn.clicked.connect(self._emit_create)
        layout.addWidget(self._btn)

    def set_repo_name(self, name: str):
        self._name_input.setText(name)

    def _set_privacy(self, private: bool, emit: bool = True):
        self._is_private = private
        active_style   = self._PILL.format(bg=COLORS['accent'], border=COLORS['accent'], fg="white")
        inactive_style = self._PILL.format(bg="transparent", border=COLORS['border'], fg=COLORS['text_muted'])
        self._priv_btn.setStyleSheet(active_style   if private else inactive_style)
        self._pub_btn.setStyleSheet( inactive_style if private else active_style)

    def _emit_create(self):
        name = self._name_input.text().strip()
        if name:
            self.create_requested.emit(name, self._is_private)

    def set_creating(self, creating: bool):
        self._btn.setEnabled(not creating)
        self._name_input.setEnabled(not creating)
        self._priv_btn.setEnabled(not creating)
        self._pub_btn.setEnabled(not creating)
        self._btn.setText("Creating…" if creating else "Create →")

    def set_error(self, msg: str):
        self.set_creating(False)
        self._btn.setText("Try again →")

    def show_deleted(self):
        """Switch banner to 'repo was deleted' warning state."""
        self.setStyleSheet("background: #2d1515; border-bottom: 1px solid #4a2020;")
        self._name_input.show()
        self._priv_btn.show()
        self._pub_btn.show()
        self._btn.show()
        self._btn.setText("Recreate →")
        # Update the message label
        for i in range(self.layout().count()):
            w = self.layout().itemAt(i).widget()
            if isinstance(w, QLabel) and "yet" in (w.text() or ""):
                w.setText("Remote repository was deleted —")
                w.setStyleSheet(f"background: transparent; font-size: 12px; color: #ef4444;")
                break


# ── Header bar ────────────────────────────────────────────────────────────────

class _Header(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("commitHeader")
        self.setFixedHeight(52)
        self.setStyleSheet(f"""
            #commitHeader {{
                background: {COLORS['bg_secondary']};
                border-bottom: 1px solid {COLORS['border']};
            }}
        """)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(24, 0, 24, 0)
        layout.setSpacing(10)

        name_block = QVBoxLayout()
        name_block.setSpacing(1)
        name_block.setAlignment(Qt.AlignVCenter)

        self._name = QLabel("—")
        self._name.setStyleSheet(
            f"background: transparent; font-size: 14px; font-weight: 600; color: {COLORS['text_primary']};"
        )
        name_block.addWidget(self._name)

        self._url = QLabel("")
        self._url.setStyleSheet(
            f"background: transparent; font-size: 11px; color: {COLORS['accent']};"
        )
        self._url.setOpenExternalLinks(True)
        self._url.hide()
        name_block.addWidget(self._url)

        layout.addLayout(name_block)
        layout.addStretch(1)

        self._center = QWidget()
        self._center.setStyleSheet("background: transparent;")
        self._center_layout = QHBoxLayout(self._center)
        self._center_layout.setContentsMargins(0, 0, 0, 0)
        self._center_layout.setSpacing(0)
        layout.addWidget(self._center)

        layout.addStretch(1)

        self._op_badge = QLabel("")
        self._op_badge.setStyleSheet(f"""
            background: #2d2010; border: 1px solid {COLORS['warning']};
            border-radius: 5px; color: {COLORS['warning']};
            font-size: 11px; font-weight: 600; padding: 2px 10px;
        """)
        self._op_badge.hide()
        layout.addWidget(self._op_badge)

        self._count = QLabel("")
        self._count.setStyleSheet(f"background: transparent; font-size: 12px; color: {COLORS['text_muted']};")
        layout.addWidget(self._count)

    def set_center(self, widget: QWidget):
        self._center_layout.addWidget(widget)

    def set_repo(self, name: str):
        self._name.setText(name)

    def set_operation(self, op: str):
        if op:
            self._op_badge.setText(f"⚙ {op}…")
            self._op_badge.show()
        else:
            self._op_badge.hide()

    def set_url(self, url: str, visibility: str = ""):
        if visibility == "not_found":
            self._url.setText(
                '<span style="color:#ef4444; font-size:11px;">⚠ Repository deleted on GitHub</span>'
            )
            self._url.setFixedHeight(16)
            self.setFixedHeight(64)
            self._url.show()
        elif url:
            badge = ""
            if visibility == "private":
                badge = ' <span style="font-size:10px; color:#6b7280;">· Private</span>'
            elif visibility == "public":
                badge = ' <span style="font-size:10px; color:#6b7280;">· Public</span>'
            self._url.setText(
                f'<a href="{url}" style="color:{COLORS["accent"]}; text-decoration:none;">{url}</a>{badge}'
            )
            self._url.setFixedHeight(16)
            self.setFixedHeight(64)
            self._url.show()
        else:
            self._url.hide()
            self.setFixedHeight(52)

    def set_count(self, n: int):
        self._count.setText(f"{n} commit{'s' if n != 1 else ''}")


# ── Zoom bar ──────────────────────────────────────────────────────────────────

class ZoomBar(QWidget):
    _BTN = f"""
        QPushButton {{
            background: transparent; border: none;
            color: {COLORS['text_secondary']};
            font-size: 16px; font-weight: 600; padding: 0 4px;
        }}
        QPushButton:hover {{ color: {COLORS['text_primary']}; }}
        QPushButton:disabled {{ color: {COLORS['text_muted']}; }}
    """
    _LBL = f"""
        QPushButton {{
            background: transparent; border: none;
            color: {COLORS['text_muted']};
            font-size: 12px; font-weight: 500; min-width: 46px;
        }}
        QPushButton:hover {{ color: {COLORS['text_primary']}; }}
    """

    def __init__(self, canvas: SpatialCanvas, parent=None):
        super().__init__(parent)
        self.setObjectName("zoomBar")
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setStyleSheet(f"""
            #zoomBar {{
                background: {COLORS['bg_card']};
                border: 1px solid {COLORS['border']};
                border-radius: 8px;
            }}
        """)
        self.setFixedHeight(34)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(6, 0, 6, 0)
        layout.setSpacing(0)
        layout.setAlignment(Qt.AlignVCenter)

        self._minus = QPushButton("−")
        self._minus.setStyleSheet(self._BTN)
        self._minus.setFixedSize(34, 34)
        self._minus.setCursor(Qt.PointingHandCursor)
        self._minus.setToolTip("Zoom out")
        self._minus.clicked.connect(canvas.zoom_out)
        layout.addWidget(self._minus)

        self._pct = QPushButton("100%")
        self._pct.setStyleSheet(self._LBL)
        self._pct.setFixedHeight(34)
        self._pct.setCursor(Qt.PointingHandCursor)
        self._pct.setToolTip("Reset zoom")
        self._pct.clicked.connect(canvas.reset_zoom)
        layout.addWidget(self._pct)

        self._plus = QPushButton("+")
        self._plus.setStyleSheet(self._BTN)
        self._plus.setFixedSize(34, 34)
        self._plus.setCursor(Qt.PointingHandCursor)
        self._plus.setToolTip("Zoom in")
        self._plus.clicked.connect(canvas.zoom_in)
        layout.addWidget(self._plus)

        self.adjustSize()
        canvas.zoom_changed.connect(self._on_zoom)

    def _on_zoom(self, pct: int):
        self._pct.setText(f"{pct}%")
        from ui.spatial_canvas import ZOOM_MIN, ZOOM_MAX
        self._minus.setEnabled(pct / 100 > ZOOM_MIN + 0.01)
        self._plus.setEnabled(pct / 100 < ZOOM_MAX - 0.01)


# ── Canvas legend ─────────────────────────────────────────────────────────────

class _Legend(QWidget):
    """Small floating key explaining the visual symbols on the canvas."""

    _ITEMS = [
        ("●", "A snapshot of your code"),
        ("──", "Version history"),
        ("┄→", "Where a version was combined"),
        ("┄┄", "Where this version started"),
        ("⚑", "First commit on this branch"),
    ]

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("canvasLegend")
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setStyleSheet(f"""
            #canvasLegend {{
                background: {COLORS['bg_card']};
                border: 1px solid {COLORS['border']};
                border-radius: 8px;
            }}
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 10, 14, 10)
        layout.setSpacing(5)

        title = QLabel("KEY")
        title.setStyleSheet(
            f"background: transparent; font-size: 9px; font-weight: 700; color: {COLORS['text_muted']};"
            " letter-spacing: 0.08em;"
        )
        layout.addWidget(title)

        for symbol, description in self._ITEMS:
            row = QHBoxLayout()
            row.setSpacing(8)
            sym_lbl = QLabel(symbol)
            sym_lbl.setFixedWidth(20)
            sym_lbl.setStyleSheet(f"background: transparent; font-size: 11px; color: {COLORS['accent']};")
            desc_lbl = QLabel(description)
            desc_lbl.setStyleSheet(f"background: transparent; font-size: 10px; color: {COLORS['text_muted']};")
            row.addWidget(sym_lbl)
            row.addWidget(desc_lbl)
            layout.addLayout(row)

        self.adjustSize()



# ── Collaborator panel ───────────────────────────────────────────────────────

_COLLAB_PALETTE = [
    "#6366f1", "#f59e0b", "#ef4444", "#8b5cf6",
    "#06b6d4", "#f97316", "#ec4899", "#14b8a6",
    "#84cc16", "#a78bfa",
]

def _person_color(login: str) -> str:
    idx = int(hashlib.md5(login.encode()).hexdigest(), 16) % len(_COLLAB_PALETTE)
    return _COLLAB_PALETTE[idx]


class _SkeletonRow(QWidget):
    """Grey placeholder row shown while collaborators are loading."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(48)

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        base = QColor(COLORS["border"])
        base.setAlpha(120)
        p.setBrush(QBrush(base))
        p.setPen(Qt.NoPen)

        # Avatar circle placeholder
        p.drawEllipse(0, 8, 32, 32)

        # Name bar
        p.drawRoundedRect(42, 12, 90, 10, 4, 4)

        # Sub-line bar
        dim = QColor(COLORS["border"])
        dim.setAlpha(70)
        p.setBrush(QBrush(dim))
        p.drawRoundedRect(42, 28, 60, 8, 4, 4)
        p.end()


class _AvatarDot(QWidget):
    """32px circular avatar — starts with initials, upgrades to real photo."""

    def __init__(self, login: str, color: str, size: int = 32, parent=None):
        super().__init__(parent)
        self.setFixedSize(size, size)
        self._size   = size
        self._login  = login
        self._color  = QColor(color)
        self._pixmap: QPixmap | None = None

    def set_pixmap(self, pm: QPixmap):
        self._pixmap = pm.scaled(
            self._size, self._size,
            Qt.KeepAspectRatioByExpanding,
            Qt.SmoothTransformation,
        )
        self.update()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        s = self._size

        clip = QPainterPath()
        clip.addEllipse(0, 0, s, s)
        p.setClipPath(clip)

        if self._pixmap:
            src = self._pixmap
            x = (src.width()  - s) // 2
            y = (src.height() - s) // 2
            p.drawPixmap(0, 0, src, x, y, s, s)
        else:
            p.setBrush(QBrush(QColor(self._color.red(),
                                     self._color.green(),
                                     self._color.blue(), 40)))
            p.setPen(Qt.NoPen)
            p.drawEllipse(0, 0, s, s)
            p.setClipping(False)
            p.setPen(QPen(self._color))
            font = QFont("Inter", s // 3, QFont.Bold)
            p.setFont(font)
            p.drawText(self.rect(), Qt.AlignCenter,
                       self._login[:2].upper())

        p.setClipping(False)
        p.setPen(QPen(self._color, 2))
        p.setBrush(Qt.NoBrush)
        p.drawEllipse(1, 1, s - 2, s - 2)
        p.end()


class _CollabRow(QWidget):
    clicked = pyqtSignal(str)   # login

    def __init__(self, login: str, contributions: int, avatar_url: str,
                 display_name: Optional[str] = None, is_owner: bool = False, parent=None):
        super().__init__(parent)
        self._login = login
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setStyleSheet("background: transparent; border-radius: 6px;")
        self.setCursor(Qt.PointingHandCursor)
        color = _person_color(login)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(4, 8, 4, 8)
        layout.setSpacing(10)

        self._dot = _AvatarDot(login, color, 36)
        layout.addWidget(self._dot)

        info = QVBoxLayout()
        info.setSpacing(1)

        name_row = QHBoxLayout()
        name_row.setSpacing(5)
        name_row.setContentsMargins(0, 0, 0, 0)

        raw_name = display_name or login
        name_lbl = QLabel(raw_name if len(raw_name) <= 18 else raw_name[:17] + "…")
        name_lbl.setToolTip(raw_name)
        name_lbl.setStyleSheet(
            f"background: transparent; font-size: 12px; font-weight: 600; color: {COLORS['text_primary']};"
        )
        name_row.addWidget(name_lbl)

        if is_owner:
            crown = QLabel("👑")
            crown.setStyleSheet("background: transparent; font-size: 11px;")
            name_row.addWidget(crown)

        name_row.addStretch()
        info.addLayout(name_row)

        commits_lbl = QLabel(f"{contributions} commit{'s' if contributions != 1 else ''}")
        commits_lbl.setStyleSheet(f"background: transparent; font-size: 11px; color: {COLORS['text_muted']};")

        info.addWidget(commits_lbl)
        layout.addLayout(info)

        if avatar_url:
            cached = _load_avatar(avatar_url)
            if cached:
                self._dot.set_pixmap(cached)
            else:
                threading.Thread(
                    target=self._fetch, args=(avatar_url,), daemon=True
                ).start()

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.clicked.emit(self._login)
        super().mousePressEvent(event)

    def enterEvent(self, _):
        self.setStyleSheet("background: rgba(255,255,255,15); border-radius: 6px;")

    def leaveEvent(self, _):
        self.setStyleSheet("background: transparent; border-radius: 6px;")

    def _fetch(self, url: str):
        try:
            import requests
            resp = requests.get(url, timeout=10)
            if resp.status_code == 200:
                pm = QPixmap()
                pm.loadFromData(resp.content)
                if not pm.isNull():
                    _save_avatar(url, pm)
                    self._dot.set_pixmap(pm)
        except Exception:
            pass


class CollaboratorPanel(QWidget):
    """Floating panel showing repo contributors — always visible top-right."""

    PANEL_W = 210
    collaborator_clicked = pyqtSignal(str)   # login

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("collabPanel")
        self.setFixedWidth(self.PANEL_W)
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setStyleSheet(f"""
            #collabPanel {{
                background: {COLORS['bg_card']};
                border: 1px solid {COLORS['border']};
                border-radius: 10px;
            }}
        """)
        self.hide()

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        hdr = QWidget()
        hdr.setObjectName("cpHdr")
        hdr.setFixedHeight(38)
        hdr.setStyleSheet(f"""
            #cpHdr {{
                background: {COLORS['bg_secondary']};
                border-bottom: 1px solid {COLORS['border']};
                border-radius: 10px 10px 0 0;
            }}
        """)
        hdr_layout = QHBoxLayout(hdr)
        hdr_layout.setContentsMargins(14, 0, 8, 0)
        title = QLabel("Collaborators")
        title.setStyleSheet(
            f"background: transparent; font-size: 12px; font-weight: 600; color: {COLORS['text_muted']};"
            " letter-spacing: 0.04em;"
        )
        hdr_layout.addWidget(title)

        self._count_lbl = QLabel("")
        self._count_lbl.setFixedHeight(18)
        self._count_lbl.setAlignment(Qt.AlignCenter)
        self._count_lbl.setStyleSheet(
            f"background: {COLORS['bg_primary']}; border-radius: 9px;"
            f" font-size: 10px; font-weight: 600; color: {COLORS['text_muted']};"
            f" padding: 0 8px;"
        )
        self._count_lbl.hide()
        hdr_layout.addWidget(self._count_lbl)
        hdr_layout.addStretch()

        self._toggle_btn = QPushButton("▾")
        self._toggle_btn.setFixedSize(24, 24)
        self._toggle_btn.setCursor(Qt.PointingHandCursor)
        self._toggle_btn.setStyleSheet(f"""
            QPushButton {{
                background: transparent; border: none;
                color: {COLORS['text_muted']}; font-size: 11px;
            }}
            QPushButton:hover {{ color: {COLORS['text_primary']}; }}
        """)
        self._toggle_btn.clicked.connect(self._toggle)
        hdr_layout.addWidget(self._toggle_btn)
        root.addWidget(hdr)

        self._scroll = _VScrollArea()
        scroll = self._scroll
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setStyleSheet(f"""
            QScrollArea {{ background: transparent; border: none; }}
            QScrollBar:vertical {{
                background: transparent; width: 4px; margin: 0;
            }}
            QScrollBar::handle:vertical {{
                background: {COLORS['border']}; border-radius: 2px; min-height: 20px;
            }}
            QScrollBar::handle:vertical:hover {{
                background: {COLORS['text_muted']};
            }}
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
            QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{ background: transparent; }}
        """)
        scroll.setMaximumHeight(480)

        self._container = QWidget()
        self._container.setStyleSheet("background: transparent;")
        self._list = QVBoxLayout(self._container)
        self._list.setContentsMargins(12, 6, 12, 8)
        self._list.setSpacing(0)
        self._list.addStretch()

        scroll.setWidget(self._container)
        scroll.viewport().setStyleSheet("background: transparent;")
        root.addWidget(scroll)

    def _clear(self):
        while self._list.count() > 1:
            item = self._list.takeAt(0)
            w = item.widget()
            if w:
                w.setParent(None)

    def show_loading(self, rows: int = 3):
        self._clear()
        for _ in range(rows):
            self._list.insertWidget(self._list.count() - 1, _SkeletonRow())
        self._scroll.show()
        self._toggle_btn.setText("▾")
        self.adjustSize()
        self.show()

    def load(self, collaborators: list[dict]):
        self._clear()
        n = len(collaborators)
        if n > 0:
            self._count_lbl.setText(str(n))
            self._count_lbl.show()
        else:
            self._count_lbl.hide()

        if not collaborators:
            lbl = QLabel("No collaborators yet")
            lbl.setAlignment(Qt.AlignCenter)
            lbl.setStyleSheet(
                f"background: transparent; font-size: 12px; color: {COLORS['text_muted']}; padding: 12px 0;"
            )
            self._list.insertWidget(0, lbl)
            self._scroll.show()
            self._toggle_btn.setText("▾")
            self.adjustSize()
            self.show()
            return

        for collab in collaborators:
            row = _CollabRow(
                login=collab.get("login", "?"),
                contributions=collab.get("contributions", 0),
                avatar_url=collab.get("avatar_url", ""),
                display_name=collab.get("display_name"),
                is_owner=collab.get("is_owner", False),
            )
            row.clicked.connect(self.collaborator_clicked)
            self._list.insertWidget(self._list.count() - 1, row)

        self._scroll.show()
        self._toggle_btn.setText("▾")
        self.adjustSize()
        self.show()

    def _toggle(self):
        if self._scroll.isVisible():
            self._scroll.setMaximumHeight(0)
            self._scroll.hide()
            self._toggle_btn.setText("▸")
            self.setFixedHeight(38)
        else:
            self._scroll.setMaximumHeight(280)
            self._scroll.show()
            self._toggle_btn.setText("▾")
            self.adjustSize()
            self.setFixedHeight(self.sizeHint().height())


# ── Exploration banner ────────────────────────────────────────────────────────

class _ExploreBanner(QWidget):
    return_requested = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setStyleSheet(f"""
            background: {COLORS['accent']}1a;
            border-bottom: 1px solid {COLORS['accent']}60;
        """)
        self.setFixedHeight(44)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(20, 0, 20, 0)
        layout.setSpacing(12)

        icon = QLabel("🔍")
        icon.setStyleSheet("background: transparent; font-size: 14px;")
        layout.addWidget(icon)

        msg = QLabel("You're exploring the past — your current work is safe.")
        msg.setStyleSheet(
            f"background: transparent; font-size: 12px; color: {COLORS['text_primary']};"
        )
        layout.addWidget(msg)
        layout.addStretch()

        btn = QPushButton("Go back to my work →")
        btn.setCursor(Qt.PointingHandCursor)
        btn.setStyleSheet(f"""
            QPushButton {{
                background: {COLORS['accent']}; border: none; border-radius: 6px;
                color: white; font-size: 12px; font-weight: 600; padding: 5px 14px;
            }}
            QPushButton:hover {{ background: {COLORS['accent_dim']}; }}
        """)
        btn.clicked.connect(self.return_requested)
        layout.addWidget(btn)


# ── Toast notification ────────────────────────────────────────────────────────

class _Toast(QWidget):
    _STYLES = {
        "loading": (COLORS["warning"],  "⏳"),
        "success": (COLORS["accent"],   "✓"),
        "error":   (COLORS["danger"],   "✕"),
        "info":    (COLORS["text_muted"],"ℹ"),
    }
    _MARGIN = 20

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("toastWidget")
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        self.setMaximumWidth(340)
        self.hide()

        from PyQt5.QtWidgets import QGraphicsOpacityEffect
        self._opacity = QGraphicsOpacityEffect(self)
        self._opacity.setOpacity(1.0)
        self.setGraphicsEffect(self._opacity)

        self._slide = QPropertyAnimation(self, b"pos")
        self._slide.setDuration(260)
        self._slide.setEasingCurve(QEasingCurve.OutCubic)

        self._fade = QPropertyAnimation(self._opacity, b"opacity")
        self._fade.setDuration(220)
        self._fade.setEasingCurve(QEasingCurve.InCubic)
        self._fade.finished.connect(self.hide)

        self._timer = QTimer()
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self._dismiss)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(14, 11, 14, 11)
        layout.setSpacing(10)

        self._icon_lbl = QLabel("")
        self._icon_lbl.setStyleSheet("background: transparent; font-size: 14px;")
        layout.addWidget(self._icon_lbl)

        self._msg = QLabel("")
        self._msg.setWordWrap(True)
        self._msg.setStyleSheet(
            f"background: transparent; font-size: 12px; color: {COLORS['text_primary']};"
        )
        layout.addWidget(self._msg)

    def show_message(self, text: str, kind: str = "info", duration_ms: int = 4000):
        color, icon = self._STYLES.get(kind, self._STYLES["info"])
        self._icon_lbl.setText(icon)
        self._icon_lbl.setStyleSheet(f"background: transparent; font-size: 14px; color: {color};")
        self._msg.setText(text)
        self.setStyleSheet(f"""
            #toastWidget {{
                background: {COLORS['bg_card']};
                border: 1px solid {color}60;
                border-radius: 10px;
            }}
        """)
        self.adjustSize()
        self._position_target()
        self._opacity.setOpacity(1.0)
        self._fade.stop()
        self._slide.stop()

        if self.parent():
            p = self.parent()
            off_x = p.width()
            target = self._target_pos()
            self.move(off_x, target.y())
            self.raise_()
            self.show()
            self._slide.setStartValue(self.pos())
            self._slide.setEndValue(target)
            self._slide.start()

        self._timer.stop()
        if duration_ms > 0:
            self._timer.start(duration_ms)

    def _target_pos(self):
        from PyQt5.QtCore import QPoint
        if not self.parent():
            return QPoint(0, 0)
        p = self.parent()
        return QPoint(p.width() - self.width() - self._MARGIN,
                      p.height() - self.height() - self._MARGIN)

    def _position_target(self):
        if self.isVisible():
            self.move(self._target_pos())

    def _dismiss(self):
        self._fade.setStartValue(1.0)
        self._fade.setEndValue(0.0)
        self._fade.start()

    def reposition(self):
        if self.isVisible():
            self.move(self._target_pos())


# ── Filter panel ──────────────────────────────────────────────────────────────

class _FilterPanel(QWidget):
    filter_changed = pyqtSignal()

    PANEL_W = 220
    _CB_STYLE = f"""
        QCheckBox {{
            background: transparent; font-size: 12px;
            color: {COLORS['text_primary']}; spacing: 6px;
        }}
        QCheckBox::indicator {{
            width: 14px; height: 14px;
            border: 1px solid {COLORS['border']};
            border-radius: 3px; background: transparent;
        }}
        QCheckBox::indicator:checked {{
            background: {COLORS['accent']}; border-color: {COLORS['accent']};
        }}
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedWidth(self.PANEL_W)
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setObjectName("filterPanel")
        self.setStyleSheet(f"""
            #filterPanel {{
                background: {COLORS['bg_card']};
                border: 1px solid {COLORS['border']};
                border-radius: 10px;
            }}
        """)
        self.hide()

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        hdr = QWidget()
        hdr.setObjectName("fpHdr")
        hdr.setFixedHeight(38)
        hdr.setStyleSheet(f"""
            #fpHdr {{
                background: {COLORS['bg_secondary']};
                border-bottom: 1px solid {COLORS['border']};
                border-radius: 10px 10px 0 0;
            }}
        """)
        hl = QHBoxLayout(hdr)
        hl.setContentsMargins(14, 0, 8, 0)
        title_lbl = QLabel("Filters")
        title_lbl.setStyleSheet(
            f"background: transparent; font-size: 12px; font-weight: 600;"
            f" color: {COLORS['text_muted']};"
        )
        hl.addWidget(title_lbl)
        hl.addStretch()
        reset_btn = QPushButton("Reset")
        reset_btn.setCursor(Qt.PointingHandCursor)
        reset_btn.setStyleSheet(f"""
            QPushButton {{ background: transparent; border: none;
                font-size: 11px; color: {COLORS['accent']}; }}
            QPushButton:hover {{ color: {COLORS['text_primary']}; }}
        """)
        reset_btn.clicked.connect(self._reset)
        hl.addWidget(reset_btn)
        root.addWidget(hdr)

        _scroll_style = f"""
            QScrollArea {{ background: transparent; border: none; }}
            QScrollBar:vertical {{
                background: transparent; width: 4px; margin: 0;
            }}
            QScrollBar::handle:vertical {{
                background: {COLORS['border']}; border-radius: 2px; min-height: 20px;
            }}
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
        """

        body = QVBoxLayout()
        body.setContentsMargins(12, 8, 12, 12)
        body.setSpacing(4)

        bl = QLabel("BRANCHES")
        bl.setStyleSheet(
            f"background: transparent; font-size: 10px; font-weight: 700;"
            f" color: {COLORS['text_muted']}; letter-spacing: 0.06em;"
        )
        body.addWidget(bl)

        self._branch_container = QWidget()
        self._branch_container.setStyleSheet("background: transparent;")
        self._branch_layout = QVBoxLayout(self._branch_container)
        self._branch_layout.setContentsMargins(0, 0, 0, 0)
        self._branch_layout.setSpacing(2)

        branch_scroll = _VScrollArea()
        branch_scroll.setWidgetResizable(True)
        branch_scroll.setFrameShape(QFrame.NoFrame)
        branch_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        branch_scroll.setStyleSheet(_scroll_style)
        branch_scroll.setMaximumHeight(160)
        branch_scroll.setWidget(self._branch_container)
        branch_scroll.viewport().setStyleSheet("background: transparent;")
        body.addWidget(branch_scroll)

        div = QFrame()
        div.setFrameShape(QFrame.HLine)
        div.setStyleSheet(f"background: {COLORS['border']}; max-height: 1px; margin: 4px 0;")
        body.addWidget(div)

        al = QLabel("COLLABORATORS")
        al.setStyleSheet(
            f"background: transparent; font-size: 10px; font-weight: 700;"
            f" color: {COLORS['text_muted']}; letter-spacing: 0.06em;"
        )
        body.addWidget(al)

        self._collab_loading = QLabel("Loading…")
        self._collab_loading.setStyleSheet(
            f"background: transparent; font-size: 12px; color: {COLORS['text_muted']}; padding: 6px 0;"
        )
        body.addWidget(self._collab_loading)

        self._author_container = QWidget()
        self._author_container.setStyleSheet("background: transparent;")
        self._author_layout = QVBoxLayout(self._author_container)
        self._author_layout.setContentsMargins(0, 0, 0, 0)
        self._author_layout.setSpacing(2)

        author_scroll = _VScrollArea()
        author_scroll.setWidgetResizable(True)
        author_scroll.setFrameShape(QFrame.NoFrame)
        author_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        author_scroll.setStyleSheet(_scroll_style)
        author_scroll.setMaximumHeight(260)
        author_scroll.setWidget(self._author_container)
        author_scroll.viewport().setStyleSheet("background: transparent;")
        author_scroll.hide()
        self._author_scroll = author_scroll
        body.addWidget(author_scroll)

        body_widget = QWidget()
        body_widget.setStyleSheet("background: transparent;")
        body_widget.setLayout(body)
        root.addWidget(body_widget)

        self._branch_checks: dict[str, QCheckBox] = {}
        self._author_checks: dict[str, QCheckBox] = {}

    def _make_cb(self, name: str, layout: QVBoxLayout, store: dict):
        cb = QCheckBox(name)
        cb.setChecked(True)
        cb.setStyleSheet(self._CB_STYLE)
        cb.stateChanged.connect(lambda _: self.filter_changed.emit())
        layout.addWidget(cb)
        store[name] = cb

    def _clear_layout(self, layout: QVBoxLayout, store: dict):
        while layout.count():
            w = layout.takeAt(0).widget()
            if w:
                w.setParent(None)
        store.clear()

    def set_branches(self, names: list[str]):
        self._clear_layout(self._branch_layout, self._branch_checks)
        for n in names:
            self._make_cb(n, self._branch_layout, self._branch_checks)

    def set_authors(self, names: list[str]):
        self._clear_layout(self._author_layout, self._author_checks)
        for n in names:
            self._make_cb(n, self._author_layout, self._author_checks)
        self._collab_loading.hide()
        self._author_scroll.show()

    def show_collaborators_loading(self):
        self._clear_layout(self._author_layout, self._author_checks)
        self._author_scroll.hide()
        self._collab_loading.show()

    def active_branches(self) -> set[str]:
        return {n for n, cb in self._branch_checks.items() if cb.isChecked()}

    def active_authors(self) -> set[str]:
        return {n for n, cb in self._author_checks.items() if cb.isChecked()}

    def _all_branches(self) -> set[str]:
        return set(self._branch_checks.keys())

    def _all_authors(self) -> set[str]:
        return set(self._author_checks.keys())

    def _reset(self):
        for cb in list(self._branch_checks.values()) + list(self._author_checks.values()):
            cb.setChecked(True)


class _OrientBar(QWidget):
    orientation_changed = pyqtSignal(str)

    _BUTTONS = [
        (ORIENT_BT, "↓", "Top to bottom — oldest to newest"),
        (ORIENT_TB, "↑", "Bottom to top — newest to oldest"),
        (ORIENT_LR, "→", "Left to right — oldest to newest"),
        (ORIENT_RL, "←", "Right to left — newest to oldest"),
    ]
    _ACTIVE = f"""
        QPushButton {{
            background: {COLORS['accent']}; border: none; border-radius: 6px;
            color: white; font-size: 14px; font-weight: 600;
        }}
    """
    _INACTIVE = f"""
        QPushButton {{
            background: transparent; border: none; border-radius: 6px;
            color: {COLORS['text_muted']}; font-size: 14px;
        }}
        QPushButton:hover {{ color: {COLORS['text_primary']}; }}
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("orientBar")
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setStyleSheet(f"""
            #orientBar {{
                background: {COLORS['bg_card']};
                border: 1px solid {COLORS['border']};
                border-radius: 8px;
            }}
        """)
        self.setFixedHeight(34)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(4, 0, 4, 0)
        layout.setSpacing(0)

        self._btns: dict[str, QPushButton] = {}
        for orient, icon, tip in self._BUTTONS:
            btn = QPushButton(icon)
            btn.setFixedSize(34, 34)
            btn.setCursor(Qt.PointingHandCursor)
            btn.setToolTip(tip)
            btn.clicked.connect(lambda _, o=orient: self.orientation_changed.emit(o))
            layout.addWidget(btn)
            self._btns[orient] = btn

        self._set_active(ORIENT_LR)

    def set_orientation(self, orient: str):
        self._set_active(orient)

    def _set_active(self, orient: str):
        for o, btn in self._btns.items():
            btn.setStyleSheet(self._ACTIVE if o == orient else self._INACTIVE)


# ── Page ──────────────────────────────────────────────────────────────────────

class _TabBar(QWidget):
    tab_changed = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet("background: transparent;")
        self._active = "schema"
        self._buttons: dict[str, QPushButton] = {}

        hl = QHBoxLayout(self)
        hl.setContentsMargins(16, 0, 16, 0)
        hl.setSpacing(0)
        for key, label in [("schema", "Schema"), ("settings", "Settings")]:
            btn = QPushButton(label)
            btn.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Expanding)
            btn.setCursor(Qt.PointingHandCursor)
            btn.setCheckable(True)
            btn.setChecked(key == "schema")
            btn.setStyleSheet(self._btn_style(key == "schema"))
            btn.clicked.connect(lambda _, k=key: self._select(k))
            hl.addWidget(btn)
            self._buttons[key] = btn
        hl.addStretch()

        self._indicator = QWidget(self)
        self._indicator.setFixedHeight(2)
        self._indicator.setStyleSheet(f"background: {COLORS['accent']};")
        self._ind_anim = QPropertyAnimation(self._indicator, b"geometry")
        self._ind_anim.setDuration(200)
        self._ind_anim.setEasingCurve(QEasingCurve.OutCubic)
        QTimer.singleShot(0, self._place_indicator)

    def _btn_style(self, active: bool) -> str:
        color  = COLORS["text_primary"] if active else COLORS["text_muted"]
        weight = "600" if active else "400"
        return (f"QPushButton {{ background: transparent; border: none;"
                f" font-size: 13px; font-weight: {weight}; color: {color};"
                f" padding: 0 20px; }}"
                f"QPushButton:hover {{ color: {COLORS['text_primary']}; }}")

    def _select(self, key: str):
        if key == self._active:
            return
        self._active = key
        for k, btn in self._buttons.items():
            btn.setChecked(k == key)
            btn.setStyleSheet(self._btn_style(k == key))
        self._place_indicator(animate=True)
        self.tab_changed.emit(key)

    def _place_indicator(self, animate: bool = False):
        btn = self._buttons.get(self._active)
        if not btn:
            return
        g = btn.geometry()
        target = QRect(g.x(), self.height() - 2, g.width(), 2)
        if animate:
            self._ind_anim.stop()
            self._ind_anim.setStartValue(self._indicator.geometry())
            self._ind_anim.setEndValue(target)
            self._ind_anim.start()
        else:
            self._indicator.setGeometry(target)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._place_indicator()

    def select(self, key: str):
        self._select(key)


class CommitViewPage(QWidget):
    _op_done        = pyqtSignal(bool, str, str, str, bool)  # ok, err, success_msg, fail_prefix, close_panel
    _push_done_sig  = pyqtSignal(bool, str, str)             # ok, err, branch
    _create_done_sig= pyqtSignal(bool, str, str)             # ok, err, branch_name
    _stash_done_sig = pyqtSignal(bool, str)                  # ok, success_msg

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
        self._no_remote_banner.create_requested.connect(self._start_create_repo)
        self._no_remote_banner.hide()
        layout.addWidget(self._no_remote_banner)

        self._tab_bar = _TabBar()
        self._tab_bar.tab_changed.connect(self._switch_tab)
        self._header.set_center(self._tab_bar)

        self._content_stack = QStackedWidget()
        layout.addWidget(self._content_stack)

        self._canvas = SpatialCanvas()
        self._content_stack.addWidget(self._canvas)   # index 0 — Schema

        self._settings_panel = SettingsPanel()
        self._settings_panel.protection_changed.connect(self._on_protection_changed)
        self._content_stack.addWidget(self._settings_panel)  # index 1 — Settings

        self._panel    = DetailPanel(self)
        self._panel.raise_()

        self._changes_panel = ChangesPanel(self)
        self._changes_panel.raise_()

        self._collab_panel = CollaboratorPanel(self)
        self._collab_panel.raise_()

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

        self._pr_float_btn = QPushButton("○  Pull Requests", self)
        self._pr_float_btn.setFixedHeight(34)
        self._pr_float_btn.setCursor(Qt.PointingHandCursor)
        self._pr_float_btn.setStyleSheet(self._pr_btn_style(False))
        self._pr_float_btn.clicked.connect(self._on_pr_requested)
        self._pr_float_btn.raise_()

        self._pr_panel = PullRequestsPanel(self)
        self._pr_panel.pr_hovered.connect(self._canvas.set_pr_highlight)
        self._pr_panel.pr_cleared.connect(lambda: self._canvas.set_pr_highlight(set()))
        self._pr_panel.close_requested.connect(lambda: self._tab_bar.select("schema"))
        self._pr_panel.raise_()

        self._loading = _LoadingOverlay(self)
        self._toast   = _Toast(self)
        self._loading.hide()

        self._settings_loaded = False
        self._op_done.connect(self._on_branch_op_done)
        self._push_done_sig.connect(self._on_push_done)
        self._create_done_sig.connect(self._on_branch_create_done)
        self._stash_done_sig.connect(self._on_clear_stash_done)

        self._orientation: str = ORIENT_LR
        self._author_display_map: dict[str, str] = {}
        self._filter_rebuilding: bool = False

        self._user: dict = {}
        self._protection_enabled: bool = False
        self._pr_panel_loaded:   bool = False
        self._collab_thread:    Optional[QThread] = None
        self._collab_worker     = None
        self._fetch_thread:     Optional[QThread] = None
        self._detail_thread:    Optional[QThread] = None
        self._detail_gen: int   = 0
        self._vis_thread:       Optional[QThread] = None
        self._navigate_thread:  Optional[QThread] = None
        self._navigate_worker   = None
        self._navigating:       bool = False
        self._last_dirty:       bool = False
        self._last_stash_id:    str  = ""
        self._uncommitted_thread: Optional[QThread] = None
        self._uncommitted_worker  = None
        self._commits: list = []
        self._collaborators: list = []
        self._you_shas: set = set()
        self._last_head_sha: str = ""
        self._collab_cache: dict[str, list[dict]] = {}
        self._last_commit_shas: tuple = ()
        self._last_branch_tips: dict = {}
        self._last_local_only: set = set()
        self._last_unpushed: set = set()
        self._last_stash_shas: set = set()
        self._local_tip_shas:   set  = set()
        self._local_tip_branch: dict = {}
        self._branch_head_shas: set  = set()
        self._panel_op_active:  bool = False
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
        self._changes_panel.panel_toggled.connect(self._reposition_collab)
        self._position_panel.jump_requested.connect(self._canvas.jump_to_commit)
        self._panel.navigate_requested.connect(self._on_navigate)
        self._panel.branch_create_requested.connect(self._on_branch_create)
        self._panel.push_requested.connect(self._on_push_branch)
        self._panel.clear_stash_requested.connect(self._on_clear_stash)
        self._panel.hard_revert_requested.connect(self._on_hard_revert)
        self._panel.soft_revert_requested.connect(self._on_soft_revert)
        self._panel.delete_branch_requested.connect(self._on_delete_branch)

    # ── Public ────────────────────────────────────────────────────────────

    def set_user(self, user: dict):
        self._user = user

    def reset(self):
        """Full teardown — called on sign out."""
        self._stop_all_threads()
        if self._tracker:
            self._tracker.close()
            self._tracker = None
        self._thread = self._collab_thread = None
        self._commits = []
        self._collaborators = []
        self._you_shas = set()
        self._last_head_sha = ""
        self._last_commit_shas = ()
        self._last_branch_tips = {}
        self._last_local_only = set()
        self._last_unpushed = set()
        self._user = {}
        self._poll_timer.stop()
        self._uncommitted_timer.stop()
        self._reload_debounce.stop()
        self._teardown_fs_watcher()
        self._canvas.load_graph([], {})
        self._collab_panel.hide()
        self._changes_panel.hide_panel()
        self._panel.hide_panel()
        self._position_panel.clear()
        self._last_head_sha = ""
        self._header.set_repo("—")

    def _stop_all_threads(self):
        # 1. Disconnect all worker signals FIRST so no callbacks fire after this point
        for attr in ("_worker", "_collab_worker", "_fetch_worker",
                     "_detail_worker", "_vis_worker"):
            w = getattr(self, attr, None)
            if w is not None:
                try:
                    w.finished.disconnect()
                except Exception:
                    pass

        # 2. Quit all threads and move them to _inflight so Python GC
        #    cannot delete the objects while the C++ thread is still running.
        for t_attr, w_attr in (
            ("_thread",          "_worker"),
            ("_collab_thread",   "_collab_worker"),
            ("_fetch_thread",    "_fetch_worker"),
            ("_detail_thread",   "_detail_worker"),
            ("_vis_thread",      "_vis_worker"),
            ("_navigate_thread",    "_navigate_worker"),
            ("_uncommitted_thread", "_uncommitted_worker"),
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

        if self._tracker:
            self._tracker.close()

        self._commits = []
        self._collaborators = []
        self._you_shas = set()
        self._last_commit_shas = ()
        self._last_head_sha    = ""
        self._last_branch_tips = {}
        self._last_local_only  = set()
        self._last_unpushed    = set()
        self._last_stash_shas  = set()
        self._tracker = GitTracker(repo_path)
        self._panel.set_repo_path(repo_path)
        try:
            self._tracker.open()
        except Exception:
            self._tracker = None
            self._loading.hide()
            return

        self._header.set_repo(self._tracker.repo_name)
        self._header.set_operation("")
        self._panel.hide_panel()
        self._filter_panel.hide()
        self._filter_panel.show_collaborators_loading()
        orientations = settings_store.get("repo_orientations", {})
        self._orientation = orientations.get(repo_path, ORIENT_LR)
        self._orient_bar.set_orientation(self._orientation)

        self._settings_loaded    = False
        self._protection_enabled = False
        self._pr_panel_loaded    = False
        self._on_protection_changed(False)
        has_remote = self._tracker.has_remote()
        self._no_remote_banner.set_repo_name(self._tracker.repo_name)
        self._no_remote_banner.setVisible(not has_remote)
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
        self._last_dirty    = False
        self._last_stash_id = ""
        self._uncommitted_timer.start()
        self._setup_fs_watcher(self._tracker._repo.git_dir)
        self._start_load(initial=True)
        self._load_collaborators()

    # ── Internal ──────────────────────────────────────────────────────────

    def _start_load(self, initial: bool = False):
        if not self._tracker:
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
        if visibility == "not_found" and self._tracker:
            self._no_remote_banner.set_repo_name(self._tracker.repo_name)
            self._no_remote_banner.show_deleted()
            self._no_remote_banner.show()

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

    def _on_fetch_done(self, changed: bool):
        if changed:
            self._start_load()

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
        self._no_remote_banner.set_creating(True)
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
            self._no_remote_banner.set_creating(False)
            self._no_remote_banner.set_error(error or "Something went wrong.")
            return
        self._tracker.close()
        self._tracker.open()
        self._no_remote_banner.hide()
        token = self._user.get("access_token", "")
        self._header.set_url(self._tracker.remote_url())
        if token:
            self._vis_thread  = QThread()
            self._vis_worker  = _VisibilityWorker(self._tracker, token)
            self._vis_worker.moveToThread(self._vis_thread)
            self._vis_thread.started.connect(self._vis_worker.run)
            self._vis_worker.finished.connect(self._on_visibility_ready)
            self._vis_worker.finished.connect(self._vis_thread.quit)
            self._vis_thread.start()
        self._start_load()
        self._load_collaborators()

    def _on_loaded(self, commits: list[CommitInfo], branch_tip_map: dict,
                   local_only: set, unpushed: set, stash_shas: set = None):
        if not commits and self._tracker:
            self._make_first_commit()
            return

        new_shas = tuple(c.sha for c in commits)

        stash_shas = stash_shas or set()

        # Always rebuild local tip map — must run before the early-return guard
        # so it stays current even when the commit graph itself hasn't changed.
        self._local_tip_shas   = set()
        self._local_tip_branch = {}
        try:
            for b in self._tracker._repo.branches:
                sha = b.commit.hexsha
                self._local_tip_shas.add(sha)
                self._local_tip_branch[sha] = b.name
        except Exception:
            pass

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

        self._commits  = commits
        self._you_shas = self._compute_you_shas(commits)
        self._panel.set_stash_shas(stash_shas)
        self._update_position_panel(commits)
        # Red-dot display: remote tips are source of truth, local fallback.
        remote_head_shas: set[str] = set()
        try:
            if self._tracker and self._tracker.has_remote():
                for rem in self._tracker._repo.remotes:
                    for ref in rem.refs:
                        if not ref.remote_head.upper().startswith("HEAD"):
                            remote_head_shas.add(ref.commit.hexsha)
        except Exception:
            pass
        branch_head_shas = remote_head_shas if remote_head_shas else self._local_tip_shas

        # Action buttons: union of remote + local so local-only branches get actions too.
        self._branch_head_shas = branch_head_shas | self._local_tip_shas

        self._canvas.load_graph(commits, branch_tip_map,
                                you_shas=self._you_shas,
                                local_only_branches=local_only,
                                unpushed_shas=unpushed,
                                stash_shas=stash_shas,
                                orientation=self._orientation,
                                head_sha=self._last_head_sha,
                                is_initial=is_initial,
                                branch_head_shas=branch_head_shas)
        self._header.set_count(len(commits))
        self._loading.hide()

        all_branches = sorted({c.branch for c in commits if c.branch})
        self._filter_rebuilding = True
        self._filter_panel.set_branches(all_branches)
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
            branch     = self._branch_for_head()
            avatar_url = self._avatar_url_for_author(head_commit.author)
            self._position_panel.load(head_commit.message, branch, head_commit.sha, head_commit.author, avatar_url)
            self._reposition_position()
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

        # 1. Session memory cache — instant, no spinner
        if cache_key and cache_key in self._collab_cache:
            self._on_collabs_loaded(self._collab_cache[cache_key])
            return

        # 2. Disk cache — instant if fresh, silent background refresh if stale
        if cache_key:
            disk_data, is_stale = collab_cache.get(cache_key)
            if disk_data is not None:
                self._on_collabs_loaded(disk_data)
                if not is_stale:
                    return
                # Stale: refresh silently without showing a spinner

        # 3. Nothing cached — show spinner and fetch
        if self._collab_thread and self._collab_thread.isRunning():
            self._collab_thread.quit()
            self._collab_thread.wait()

        if not (cache_key and collab_cache.get(cache_key)[0] is not None):
            pass  # collab panel moved to settings tab

        self._collab_thread  = QThread()
        self._collab_worker  = _CollabLoader(self._tracker._path, token)
        self._collab_worker.moveToThread(self._collab_thread)
        self._collab_thread.started.connect(self._collab_worker.run)
        self._collab_worker.finished.connect(self._on_collabs_loaded)
        self._collab_worker.finished.connect(self._collab_thread.quit)
        self._collab_thread.start()

    def _reposition_collab(self, _=None):
        margin = 16
        cp = self._collab_panel
        cp.adjustSize()
        detail_offset  = DETAIL_PANEL_W if self._panel._visible else 0
        changes_offset = CHANGES_W if self._changes_panel._visible else 0
        cp.move(self.width() - detail_offset - changes_offset - cp.PANEL_W - margin,
                self._header.height() + margin)

    def _on_collabs_loaded(self, collabs: list[dict]):
        login = self._user.get("login", "")
        if login and not any(c.get("login") == login for c in collabs):
            collabs = [{
                "login":         login,
                "avatar_url":    self._user.get("avatar_url", ""),
                "contributions": 0,
                "gh_name":       self._user.get("name") or login,
            }] + collabs
        owner = self._tracker.repo_owner() if self._tracker else ""
        for c in collabs:
            c["is_owner"] = (c.get("login") == owner)
        self._collaborators = collabs

        if self._tracker:
            cache_key = self._tracker.remote_url()
            if cache_key:
                self._collab_cache[cache_key] = collabs
                collab_cache.save(cache_key, collabs)

        is_owner = bool(owner) and self._user.get("login", "") == owner
        token = self._user.get("access_token", "")
        if not self._settings_loaded and self._tracker:
            self._settings_panel.setup(self._tracker, self._user, is_owner, token)
            self._settings_loaded = True
        self._settings_panel.load_collaborators(collabs)

        if self._commits:
            self._place_contributor_badges()

    @staticmethod
    def _pr_btn_style(protected: bool) -> str:
        if protected:
            return (f"QPushButton {{ background: {COLORS['accent_dim']};"
                    f" border: 1px solid {COLORS['accent']}; border-radius: 8px;"
                    f" color: {COLORS['accent']}; font-size: 12px; font-weight: 600;"
                    f" padding: 0 12px; }}"
                    f"QPushButton:hover {{ background: {COLORS['accent']};"
                    f" color: {COLORS['text_on_accent']}; }}")
        return (f"QPushButton {{ background: {COLORS['bg_card']};"
                f" border: 1px solid {COLORS['border']}; border-radius: 8px;"
                f" color: {COLORS['text_muted']}; font-size: 12px; font-weight: 600;"
                f" padding: 0 12px; }}"
                f"QPushButton:hover {{ color: {COLORS['text_primary']};"
                f" background: {COLORS['bg_hover']}; }}")

    def _on_protection_changed(self, enabled: bool):
        self._protection_enabled = enabled
        self._pr_float_btn.setText("●  Pull Requests" if enabled else "○  Pull Requests")
        self._pr_float_btn.setStyleSheet(self._pr_btn_style(enabled))
        self._pr_panel.set_protection(enabled)

    def _switch_tab(self, tab: str):
        if tab == "schema":
            self._content_stack.setCurrentIndex(0)
            for w in [self._zoom_bar, self._minimap, self._orient_bar,
                      self._filter_btn, self._pr_float_btn]:
                w.show()
            if getattr(self, "_pos_panel_was_visible", False):
                self._position_panel.show()
        else:
            self._pos_panel_was_visible = self._position_panel.isVisible()
            self._content_stack.setCurrentIndex(1)
            for w in [self._zoom_bar, self._minimap, self._orient_bar,
                      self._filter_btn, self._filter_panel, self._position_panel,
                      self._pr_float_btn]:
                w.hide()
            self._panel.hide_panel()
            self._changes_panel.hide_panel()
            self._pr_panel.hide_panel()
            # Initialise settings if collabs haven't loaded yet (e.g. no remote)
            if not self._settings_loaded and self._tracker:
                owner    = self._tracker.repo_owner()
                is_owner = bool(owner) and self._user.get("login", "") == owner
                self._settings_panel.setup(
                    self._tracker, self._user, is_owner,
                    self._user.get("access_token", ""),
                )
                self._settings_loaded = True

    def _on_clear_stash(self, sha: str, stash_ref: str):
        if not self._tracker:
            return
        path = self._tracker._path
        if stash_ref:
            self._toast.show_message("Clearing stash…", kind="loading")
            def _run():
                try:
                    from core.git_ops import drop_stash
                    ok = drop_stash(path, stash_ref)
                    err = "" if ok else "drop failed"
                except Exception as exc:
                    ok, err = False, str(exc)
                self._stash_done_sig.emit(ok, "Stash cleared.")
        else:
            self._toast.show_message("Discarding changes…", kind="loading")
            def _run():
                try:
                    from core.git_ops import discard_all_changes
                    ok, _ = discard_all_changes(path)
                except Exception as exc:
                    ok = False
                self._stash_done_sig.emit(ok, "Changes discarded.")
        import threading as _threading
        _threading.Thread(target=_run, daemon=True).start()

    def _on_clear_stash_done(self, ok: bool, success_msg: str):
        if ok:
            self._toast.show_message(success_msg, kind="success")
            self._panel.refresh_stash_section()
            self._start_load()
        else:
            self._toast.show_message("Failed.", kind="error", duration_ms=6000)

    def _on_push_branch(self, branch: str):
        if not self._tracker or self._panel_op_active:
            return
        self._panel_op_active = True
        self._reload_debounce.stop()
        path = self._tracker._path
        def _run():
            try:
                from core.git_ops import push_branch
                ok, err = push_branch(path, branch)
            except Exception as exc:
                ok, err = False, str(exc)
            self._push_done_sig.emit(ok, err, branch)
        import threading as _threading
        _threading.Thread(target=_run, daemon=True).start()

    def _on_push_done(self, ok: bool, err: str, branch: str):
        self._panel_op_active = False
        if ok:
            self._toast.show_message(f"'{branch}' pushed to remote.", kind="success")
            self._panel.set_push_state(False)
            self._start_load()
        else:
            msg = "Timed out." if err == "timed_out" else f"Push failed: {err[:120]}"
            self._toast.show_message(msg, kind="error", duration_ms=6000)
        self._panel.unlock_actions()

    def _on_hard_revert(self, branch: str, target_sha: str):
        self._run_branch_op(
            lambda p: __import__("core.git_ops", fromlist=["hard_revert_to"]).hard_revert_to(p, branch, target_sha),
            success_msg=f"Hard reverted '{branch}'.",
            fail_prefix="Hard revert failed",
            start_msg=f"Hard reverting '{branch}'…",
        )

    def _on_soft_revert(self, branch: str, tip_sha: str, parent_sha: str):
        self._run_branch_op(
            lambda p: __import__("core.git_ops", fromlist=["soft_revert_to"]).soft_revert_to(p, branch, tip_sha, parent_sha),
            success_msg=f"Soft reverted '{branch}'.",
            fail_prefix="Soft revert failed",
            start_msg=f"Soft reverting '{branch}'…",
        )

    def _on_delete_branch(self, branch: str, parent_sha: str):
        self._run_branch_op(
            lambda p: __import__("core.git_ops", fromlist=["delete_branch_full"]).delete_branch_full(p, branch, parent_sha),
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
        if ok:
            self._toast.show_message(success_msg, kind="success", duration_ms=5000)
            if close_panel:
                self._panel.hide_panel()
                self._last_branch_tips = {}
                self._last_head_sha    = ""
            self._start_load()
        else:
            msg = "Timed out." if err == "timed_out" else f"{fail_prefix}: {err[:120]}"
            self._toast.show_message(msg, kind="error", duration_ms=6000)
        self._panel.unlock_actions()

    def _on_branch_create(self, sha: str, branch_name: str):
        if not self._tracker or self._panel_op_active:
            return
        self._panel_op_active = True
        self._reload_debounce.stop()
        path = self._tracker._path
        def _run():
            try:
                from core.git_ops import create_branch_with_commit
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
            self._start_load()
        else:
            self._toast.show_message(f"Failed: {err[:120]}", kind="error", duration_ms=6000)
        self._panel.unlock_actions()

    def _on_pr_requested(self):
        self._tab_bar.select("schema")
        self._switch_tab("schema")
        if self._tracker:
            if not self._pr_panel_loaded:
                owner  = self._tracker.repo_owner()
                is_own = self._user.get("login", "") == owner
                self._pr_panel.load(
                    self._tracker, self._user, is_own,
                    self._user.get("access_token", ""),
                    self._commits,
                )
                self._pr_panel_loaded = True
            else:
                # Panel already has PRs — just refresh the commit list for hover
                self._pr_panel.update_commits(self._commits)
        self._pr_panel.set_protection(self._protection_enabled)
        self._pr_panel.show_panel()

    @staticmethod
    def _alpha(s: str) -> str:
        return re.sub(r'[^a-z]', '', s.lower())

    def _compute_you_shas(self, commits, gh_name: str = "") -> set:
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

    def _find_latest_commit_for_login(self, login: str, gh_name: str = "") -> Optional[CommitInfo]:
        if not self._commits:
            return None
        nl = self._alpha(login)
        nn = self._alpha(gh_name)
        best: Optional[CommitInfo] = None
        for commit in self._commits:
            na = self._alpha(commit.author)
            if not na:
                continue
            login_hit = nl and (nl == na or nl in na or na in nl)
            name_hit  = nn and (nn == na or nn in na or na in nn)
            if login_hit or name_hit:
                if best is None or commit.date > best.date:
                    best = commit
        return best

    def _place_contributor_badges(self):
        enriched    = []
        badge_data  = []
        known_authors: set[str] = set()

        for collab in self._collaborators:
            login   = collab.get("login", "")
            gh_name = collab.get("gh_name", "")
            commit  = self._find_latest_commit_for_login(login, gh_name)
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

        self._settings_panel.load_collaborators(enriched)
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
        can_push = (commit.sha in self._last_unpushed or
                    commit.branch in self._last_local_only)
        self._panel.set_push_state(can_push, commit.branch)

        # Commit actions — follow same source of truth as the red dot.
        # Suppress all actions while another operation is in progress.
        is_head = commit.sha in self._branch_head_shas and not self._panel_op_active
        # Use the real git branch name for this tip, not the lane algo's assignment
        branch     = self._local_tip_branch.get(commit.sha, commit.branch)
        has_parent = len(commit.parents) > 0
        parent_sha = commit.parents[0] if commit.parents else ""
        # "Main" = default branch by name, OR any branch that exists on remote
        is_main = branch in ("main", "master")

        # "First of branch": parent belongs to a different branch (the branch point).
        # If parent isn't in the canvas at all, default to True — the branch
        # diverges from outside our graph window, so it's effectively a new branch.
        is_first = not has_parent
        if has_parent and branch:
            parent_commit = next((c for c in self._commits if c.sha == parent_sha), None)
            if parent_commit is None:
                is_first = True   # parent outside graph — treat as first
            else:
                parent_branch = self._local_tip_branch.get(parent_sha, "") or parent_commit.branch
                is_first = bool(parent_branch) and parent_branch != branch

        self._panel.set_commit_actions(
            branch=branch,
            parent_sha=parent_sha,
            has_parent=has_parent,
            is_first_of_branch=is_first,
            is_main=is_main,
            is_head=is_head,
        )

    def _on_detail_thread_done(self, thread: QThread):
        if self._detail_thread is thread:
            self._detail_thread = None

    def _on_navigate(self, sha: str):
        if not self._tracker:
            return
        if self._navigate_thread and self._navigate_thread.isRunning():
            return

        # Block fs watcher reloads for the entire duration of the checkout
        # so the Loader thread can't start reading git state mid-checkout.
        self._navigating = True
        self._reload_debounce.stop()

        current_head = self._tracker.head_sha()
        self._navigate_thread = QThread()
        self._navigate_worker = _NavigateWorker(self._tracker._path, sha, current_head)
        self._navigate_worker.moveToThread(self._navigate_thread)
        self._navigate_thread.started.connect(self._navigate_worker.run)
        self._navigate_worker.finished.connect(self._on_navigate_done)
        self._navigate_worker.finished.connect(self._navigate_thread.quit)
        self._navigate_thread.start()

    def _on_navigate_done(self, ok: bool, err: str):
        self._navigating = False
        self._panel.unlock_actions()
        if not ok:
            if err == "auto-save-failed":
                self._toast.show_message(
                    "Couldn't auto-save your changes. Commit them first, then retry.",
                    kind="error", duration_ms=7000,
                )
            else:
                self._toast.show_message(
                    f"Couldn't switch to that commit: {err[:120]}",
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
        if self._uncommitted_thread and self._uncommitted_thread.isRunning():
            return
        self._uncommitted_thread = QThread()
        self._uncommitted_worker = _UncommittedRefreshWorker(self._tracker._path)
        self._uncommitted_worker.moveToThread(self._uncommitted_thread)
        self._uncommitted_thread.started.connect(self._uncommitted_worker.run)
        self._uncommitted_worker.finished.connect(self._on_uncommitted_done)
        self._uncommitted_worker.finished.connect(lambda *_: self._uncommitted_thread.quit())
        self._uncommitted_thread.start()

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
                # Non-HEAD commit — only refresh if its stash entry changed
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
            self._canvas.load_graph(
                self._commits,
                self._last_branch_tips,
                you_shas=self._you_shas,
                local_only_branches=self._last_local_only,
                unpushed_shas=self._last_unpushed,
                orientation=orient,
                head_sha=self._last_head_sha,
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
            branch_ok = (not commit.branch) or (commit.branch in active_branches)
            author_ok = (display in active_authors) if (display in all_authors) else True
            if not branch_ok or not author_ok:
                dimmed.add(commit.sha)
        self._canvas.apply_commit_filter(dimmed)

    def _reposition_filter(self):
        fp = self._filter_panel
        fp.adjustSize()
        fp.move(16, self._header.height() + 16)

    # ── Resize ────────────────────────────────────────────────────────────

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._panel.reposition()
        self._changes_panel.reposition()
        self._loading.setGeometry(self.rect())
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
        self._pr_panel.reposition()
        pb = self._pr_float_btn
        pb.adjustSize()
        pb.move(margin + mm.MAP_W + margin + zb.width() + margin + ob.width() + margin + fb.width() + margin,
                self.height() - pb.height() - margin)
        if self._position_panel.isVisible():
            self._reposition_position()
        if self._filter_panel.isVisible():
            self._reposition_filter()
        self._toast.reposition()


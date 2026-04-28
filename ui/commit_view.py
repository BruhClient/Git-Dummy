from __future__ import annotations

from typing import Optional

import hashlib
import re
import threading

from PyQt5.QtCore import Qt, QThread, QObject, pyqtSlot, pyqtSignal
from PyQt5.QtGui import QPainter, QColor, QBrush, QPen, QPixmap, QPainterPath, QFont
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QScrollArea, QFrame,
)
from styles.theme import COLORS
from core.git_tracker import GitTracker, CommitInfo
from ui.spatial_canvas import SpatialCanvas, MiniMap
from ui.detail_panel import DetailPanel, ChangesPanel, PANEL_W as DETAIL_PANEL_W, CHANGES_W


# ── Background loaders ───────────────────────────────────────────────────────

class _CollabLoader(QObject):
    """Fetches collaborators on a worker thread, emits list to main thread."""
    finished = pyqtSignal(list)

    def __init__(self, tracker: GitTracker, token: str):
        super().__init__()
        self._tracker = tracker
        self._token   = token

    @pyqtSlot()
    def run(self):
        self.finished.emit(self._tracker.get_collaborators(self._token))


class _Loader(QObject):
    finished = pyqtSignal(list, dict, set)

    def __init__(self, tracker: GitTracker):
        super().__init__()
        self._tracker = tracker

    @pyqtSlot()
    def run(self):
        commits, branch_tip_map, local_only = self._tracker.graph_commits()
        self.finished.emit(commits, branch_tip_map, local_only)


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

    def __init__(self, repo_path: str, repo_name: str, token: str, username: str):
        super().__init__()
        self._path     = repo_path
        self._name     = repo_name
        self._token    = token
        self._username = username

    @pyqtSlot()
    def run(self):
        from core.git_ops import create_github_repo, push_to_github
        ok, err, clone_url = create_github_repo(self._name, True, self._token)
        if not ok:
            self.finished.emit(False, err, "")
            return
        ok, err = push_to_github(self._path, clone_url, self._username, self._token)
        self.finished.emit(ok, err, clone_url)


# ── Loading overlay ───────────────────────────────────────────────────────────

class _LoadingOverlay(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setStyleSheet(f"background: {COLORS['bg_primary']};")
        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignCenter)
        lbl = QLabel("Loading your saves…")
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

        sub = QLabel("Create a GitHub repository to back up your saves to the cloud.")
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

        self._name = QLabel("—")
        self._name.setStyleSheet(
            f"background: transparent; font-size: 14px; font-weight: 600; color: {COLORS['text_primary']};"
        )
        layout.addWidget(self._name)
        layout.addStretch()

        self._count = QLabel("")
        self._count.setStyleSheet(f"background: transparent; font-size: 12px; color: {COLORS['text_muted']};")
        layout.addWidget(self._count)

    def set_repo(self, name: str):
        self._name.setText(name)

    def set_count(self, n: int):
        self._count.setText(f"{n} save{'s' if n != 1 else ''}")


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

        self._minus = QPushButton("−")
        self._minus.setStyleSheet(self._BTN)
        self._minus.setFixedSize(40, 40)
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
        self._plus.setFixedSize(40, 40)
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
        ("⚑", "First save on this version"),
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
                 display_name: Optional[str] = None, parent=None):
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

        name_lbl = QLabel(display_name or login)
        name_lbl.setStyleSheet(
            f"background: transparent; font-size: 12px; font-weight: 600; color: {COLORS['text_primary']};"
        )
        commits_lbl = QLabel(f"{contributions} save{'s' if contributions != 1 else ''}")
        commits_lbl.setStyleSheet(f"background: transparent; font-size: 11px; color: {COLORS['text_muted']};")

        info.addWidget(name_lbl)
        info.addWidget(commits_lbl)
        layout.addLayout(info)

        # Download avatar in background
        if avatar_url:
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

        self._scroll = QScrollArea()
        scroll = self._scroll
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
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
        scroll.setMaximumHeight(280)

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

        if not collaborators:
            self.hide()
            return

        for collab in collaborators:
            row = _CollabRow(
                login=collab.get("login", "?"),
                contributions=collab.get("contributions", 0),
                avatar_url=collab.get("avatar_url", ""),
                display_name=collab.get("display_name"),
            )
            row.clicked.connect(self.collaborator_clicked)
            self._list.insertWidget(self._list.count() - 1, row)

        self._scroll.show()
        self._toggle_btn.setText("▾")
        self.adjustSize()
        self.show()

    def _toggle(self):
        if self._scroll.isVisible():
            self._scroll.hide()
            self._toggle_btn.setText("▸")
            self.setFixedHeight(38)   # just the header
        else:
            self._scroll.show()
            self._toggle_btn.setText("▾")
            self.setFixedHeight(self.sizeHint().height())
            self.adjustSize()


# ── Page ──────────────────────────────────────────────────────────────────────

class CommitViewPage(QWidget):
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

        self._canvas = SpatialCanvas()
        layout.addWidget(self._canvas)

        self._panel    = DetailPanel(self)
        self._panel.raise_()

        self._changes_panel = ChangesPanel(self)
        self._changes_panel.raise_()

        self._collab_panel = CollaboratorPanel(self)
        self._collab_panel.raise_()


        self._zoom_bar = ZoomBar(self._canvas, self)
        self._zoom_bar.raise_()

        self._minimap = MiniMap(self._canvas, self)
        self._minimap.raise_()

        self._loading = _LoadingOverlay(self)
        self._loading.hide()


        self._user: dict = {}
        self._collab_thread: Optional[QThread] = None
        self._collab_worker = None
        self._commits: list = []
        self._collaborators: list = []
        self._you_shas: set = set()
        self._canvas.commit_clicked.connect(self._on_commit_clicked)
        self._canvas.contributor_badge_clicked.connect(self._on_collaborator_clicked)
        self._collab_panel.collaborator_clicked.connect(self._on_collaborator_clicked)
        self._panel.panel_toggled.connect(self._reposition_collab)
        self._panel.panel_toggled.connect(lambda v: self._changes_panel.hide_panel() if not v else None)
        self._panel.file_selected.connect(self._changes_panel.show_file)
        self._changes_panel.panel_toggled.connect(self._reposition_collab)

    # ── Public ────────────────────────────────────────────────────────────

    def set_user(self, user: dict):
        self._user = user

    def reset(self):
        """Full teardown — called on sign out."""
        if self._tracker:
            self._tracker.close()
            self._tracker = None
        for thread in (self._thread, self._collab_thread):
            if thread and thread.isRunning():
                thread.quit()
                thread.wait()
        self._thread = self._collab_thread = None
        self._commits = []
        self._collaborators = []
        self._you_shas = set()
        self._user = {}
        self._canvas.load_graph([], {})
        self._collab_panel.hide()
        self._changes_panel.hide_panel()
        self._panel.hide_panel()
        self._header.set_repo("—")

    def load_repo(self, repo_path: str):
        if self._tracker:
            self._tracker.close()

        self._commits = []
        self._collaborators = []
        self._you_shas = set()
        self._tracker = GitTracker(repo_path)
        self._tracker.open()

        self._header.set_repo(self._tracker.repo_name)
        self._panel.hide_panel()
        self._collab_panel.hide()
        self._start_load()
        self._load_collaborators()

    # ── Internal ──────────────────────────────────────────────────────────

    def _start_load(self):
        if not self._tracker:
            return

        self._loading.show()
        self._loading.raise_()

        if self._thread and self._thread.isRunning():
            self._thread.quit()
            self._thread.wait()

        self._thread = QThread()
        self._worker = _Loader(self._tracker)
        self._worker.moveToThread(self._thread)
        self._thread.started.connect(self._worker.run)
        self._worker.finished.connect(self._on_loaded)
        self._worker.finished.connect(self._thread.quit)
        self._thread.start()

    def _on_loaded(self, commits: list[CommitInfo], branch_tip_map: dict, local_only: set):
        if not commits and self._tracker:
            self._make_first_commit()
            return

        self._commits  = commits
        self._you_shas = self._compute_you_shas(commits)
        self._canvas.load_graph(commits, branch_tip_map,
                                you_shas=self._you_shas,
                                local_only_branches=local_only)
        self._header.set_count(len(commits))
        self._loading.hide()
        if self._collaborators:
            self._place_contributor_badges()

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

        if self._collab_thread and self._collab_thread.isRunning():
            self._collab_thread.quit()
            self._collab_thread.wait()

        self._collab_thread  = QThread()
        self._collab_worker  = _CollabLoader(self._tracker, token)
        self._collab_worker.moveToThread(self._collab_thread)
        self._collab_thread.started.connect(self._collab_worker.run)
        self._collab_worker.finished.connect(self._on_collabs_loaded)
        self._collab_worker.finished.connect(self._collab_thread.quit)
        self._collab_panel.show_loading()
        self._reposition_collab()
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
        self._collaborators = collabs
        if self._commits:
            self._place_contributor_badges()
        else:
            self._collab_panel.load(collabs)
            self._reposition_collab()

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
        enriched   = []
        badge_data = []
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
        you_gh_name = next(
            (c.get("gh_name", "") for c in self._collaborators
             if c.get("login") == self._user.get("login")), ""
        )
        self._you_shas = self._compute_you_shas(self._commits, you_gh_name)
        self._canvas.refresh_you_labels(self._you_shas)
        self._collab_panel.load(enriched)
        self._reposition_collab()
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
        self._panel.show_commit(commit, detail, collab.get("avatar_url", ""), "You" if is_you else None, files)

    def _on_commit_clicked(self, commit: CommitInfo):
        self._changes_panel.hide_panel()
        self._panel.deselect_files()
        detail = self._tracker.commit_detail(commit.sha) if self._tracker else {}
        files  = self._tracker.commit_files(commit.sha)  if self._tracker else []
        is_you = commit.sha in self._you_shas
        collab = next(
            (c for c in self._collaborators
             if self._alpha(c.get("login", "")) and
             (self._alpha(c.get("login", "")) in self._alpha(commit.author) or
              self._alpha(commit.author) in self._alpha(c.get("login", "")) or
              (c.get("gh_name") and self._alpha(c.get("gh_name", "")) in self._alpha(commit.author)))),
            {}
        )
        display_author = "You" if is_you else None
        self._panel.show_commit(commit, detail, collab.get("avatar_url", ""), display_author, files)

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
        cp = self._collab_panel
        detail_offset = DETAIL_PANEL_W if self._panel._visible else 0
        cp.move(self.width() - detail_offset - cp.PANEL_W - margin,
                self._header.height() + margin)

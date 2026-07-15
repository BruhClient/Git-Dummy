"""Collaborator panel — skeleton rows, avatar dots, rows, and the main panel."""
from __future__ import annotations

import hashlib
import threading
from typing import Optional

import qtawesome as qta

from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtGui import QPainter, QColor, QBrush, QPen, QPixmap, QPainterPath, QFont
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QFrame,
)

from styles.theme import COLORS, scrollbar_style
from ui.components.avatar import _load_avatar, _save_avatar
from ui.panels.diff_renderer import _VScrollArea


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

        p.drawEllipse(0, 8, 32, 32)

        p.drawRoundedRect(42, 12, 90, 10, 4, 4)

        dim = QColor(COLORS["border"])
        dim.setAlpha(70)
        p.setBrush(QBrush(dim))
        p.drawRoundedRect(42, 28, 60, 8, 4, 4)
        p.end()


class _AvatarDot(QWidget):
    """Circular avatar — starts with initials, upgrades to real photo."""

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
            font = QFont("Urbanist", s // 3, QFont.Bold)
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
            crown = QLabel()
            crown.setPixmap(qta.icon("fa5s.crown", color=COLORS["warning"]).pixmap(12, 12))
            crown.setStyleSheet("background: transparent;")
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
        self.setStyleSheet(f"background: {COLORS['bg_hover']}; border-radius: 6px;")

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
        title = QLabel("Contributors")
        title.setStyleSheet(
            f"background: transparent; font-size: 12px; font-weight: 600; color: {COLORS['text_muted']};"
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
        scroll.setStyleSheet("QScrollArea { background: transparent; border: none; }\n" + scrollbar_style())
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
            lbl = QLabel("No contributors yet")
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

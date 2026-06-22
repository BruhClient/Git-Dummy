from __future__ import annotations

import threading

from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtGui import QPainter, QColor, QBrush, QPen, QPainterPath, QPixmap, QFont
from PyQt5.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton
from styles.theme import COLORS, hash_color

PANEL_W = 240


class _Avatar(QWidget):
    SIZE = 32
    _pixmap_ready = pyqtSignal(object)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(self.SIZE, self.SIZE)
        self._initials = ""
        self._color = QColor("#6366f1")
        self._pixmap: QPixmap | None = None
        self._pixmap_ready.connect(self._apply)

    def _apply(self, pm: QPixmap):
        s = self.SIZE
        self._pixmap = pm.scaled(s, s, Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation)
        self.update()

    def set_author(self, name: str, avatar_url: str = ""):
        self._initials = (name[:1] + (name.split()[-1][:1] if " " in name else "")).upper()
        self._color = QColor(hash_color(name))
        self._pixmap = None
        self.update()
        if avatar_url:
            threading.Thread(target=self._fetch, args=(avatar_url,), daemon=True).start()

    def _fetch(self, url: str):
        try:
            import requests
            resp = requests.get(url, timeout=10)
            if resp.status_code == 200:
                pm = QPixmap()
                pm.loadFromData(resp.content)
                if not pm.isNull():
                    self._pixmap_ready.emit(pm)
        except Exception:
            pass

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        s = self.SIZE

        clip = QPainterPath()
        clip.addEllipse(0, 0, s, s)
        p.setClipPath(clip)

        if self._pixmap:
            src = self._pixmap
            x = (src.width() - s) // 2
            y = (src.height() - s) // 2
            p.drawPixmap(0, 0, src, x, y, s, s)
        else:
            bg = QColor(self._color.red(), self._color.green(), self._color.blue(), 50)
            p.setBrush(QBrush(bg))
            p.setPen(Qt.NoPen)
            p.drawEllipse(0, 0, s, s)
            p.setClipping(False)
            p.setPen(QPen(self._color))
            p.setFont(QFont("Urbanist", s // 4, QFont.Bold))
            p.drawText(self.rect(), Qt.AlignCenter, self._initials)

        p.setClipping(False)
        p.setBrush(Qt.NoBrush)
        p.setPen(QPen(self._color, 1.5))
        p.drawEllipse(1, 1, s - 2, s - 2)
        p.end()


class PositionPanel(QWidget):
    """Floating panel showing the commit currently checked out in the local repo."""

    PANEL_W = PANEL_W
    jump_requested   = pyqtSignal(str)
    return_requested = pyqtSignal()
    pull_requested   = pyqtSignal(str)  # emits branch name

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("positionPanel")
        self.setFixedWidth(self.PANEL_W)
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setStyleSheet(f"""
            #positionPanel {{
                background: {COLORS['bg_card']};
                border: 1px solid {COLORS['border']};
                border-radius: 10px;
            }}
        """)
        self.hide()

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # Header
        hdr = QWidget()
        hdr.setObjectName("ppHdr")
        hdr.setFixedHeight(38)
        hdr.setStyleSheet(f"""
            #ppHdr {{
                background: {COLORS['bg_secondary']};
                border-bottom: 1px solid {COLORS['border']};
                border-radius: 10px 10px 0 0;
            }}
        """)
        hl = QHBoxLayout(hdr)
        hl.setContentsMargins(14, 0, 12, 0)

        self._dot = QLabel("●")
        self._dot.setStyleSheet(f"background: transparent; font-size: 8px; color: {COLORS['accent']};")
        hl.addWidget(self._dot)

        self._title = QLabel("Where you are now")
        self._title.setStyleSheet(
            f"background: transparent; font-size: 12px; font-weight: 600;"
            f" color: {COLORS['text_muted']};"
        )
        hl.addWidget(self._title)
        hl.addStretch()

        self._explore_badge = QLabel("Exploring")
        self._explore_badge.setStyleSheet(f"""
            background: {COLORS['warning']}22;
            border: 1px solid {COLORS['warning']}80;
            border-radius: 4px;
            color: {COLORS['warning']};
            font-size: 9px; font-weight: 700;
            padding: 2px 6px;
        """)
        self._explore_badge.hide()
        hl.addWidget(self._explore_badge)

        root.addWidget(hdr)

        # Body
        body = QWidget()
        body.setStyleSheet("background: transparent;")
        bl = QVBoxLayout(body)
        bl.setContentsMargins(14, 12, 14, 14)
        bl.setSpacing(10)

        # Author row
        author_row = QHBoxLayout()
        author_row.setSpacing(10)
        author_row.setContentsMargins(0, 0, 0, 0)

        self._avatar = _Avatar()
        author_row.addWidget(self._avatar)

        author_block = QVBoxLayout()
        author_block.setSpacing(1)
        author_block.setContentsMargins(0, 0, 0, 0)

        made_by_lbl = QLabel("Made by")
        made_by_lbl.setStyleSheet(
            f"background: transparent; font-size: 9px; font-weight: 400;"
            f" color: {COLORS['text_muted']};"
        )
        author_block.addWidget(made_by_lbl)

        self._author_lbl = QLabel("—")
        self._author_lbl.setStyleSheet(
            f"background: transparent; font-size: 12px; color: {COLORS['text_primary']};"
        )
        author_block.addWidget(self._author_lbl)
        author_row.addLayout(author_block)
        author_row.addStretch()
        bl.addLayout(author_row)

        # Divider
        div = QWidget()
        div.setFixedHeight(1)
        div.setAttribute(Qt.WA_StyledBackground, True)
        div.setStyleSheet(f"background: {COLORS['border']};")
        bl.addWidget(div)

        self._name_lbl   = _Field("Description", "—")
        self._branch_lbl = _Field("Branch", "—")
        self._sha_lbl    = _Field("ID",     "—")

        bl.addWidget(self._name_lbl)
        bl.addWidget(self._branch_lbl)
        bl.addWidget(self._sha_lbl)

        self._jump_btn = QPushButton("Find on timeline →")
        self._jump_btn.setCursor(Qt.PointingHandCursor)
        self._jump_btn.setStyleSheet(f"""
            QPushButton {{
                background: {COLORS['accent']}; border: none; border-radius: 8px;
                color: {COLORS['text_on_accent']}; font-size: 12px; font-weight: 600;
                padding: 8px 16px;
            }}
            QPushButton:hover {{ background: {COLORS['accent_dim']}; }}
        """)
        self._jump_btn.clicked.connect(self._on_jump)
        bl.addWidget(self._jump_btn)

        self._pull_btn = QPushButton("↓ Pull to latest")
        self._pull_btn.setCursor(Qt.PointingHandCursor)
        self._pull_btn.setStyleSheet(f"""
            QPushButton {{
                background: {COLORS['accent']}; border: none; border-radius: 8px;
                color: {COLORS['text_on_accent']}; font-size: 12px; font-weight: 600;
                padding: 8px 16px;
            }}
            QPushButton:hover {{ background: {COLORS['accent_dim']}; }}
        """)
        self._pull_btn.clicked.connect(lambda: self.pull_requested.emit(self._current_branch))
        self._pull_btn.hide()
        bl.addWidget(self._pull_btn)

        self._return_btn = QPushButton("Go back to my work →")
        self._return_btn.setCursor(Qt.PointingHandCursor)
        self._return_btn.setStyleSheet(f"""
            QPushButton {{
                background: {COLORS['warning']}22;
                border: 1px solid {COLORS['warning']}80;
                border-radius: 8px;
                color: {COLORS['warning']};
                font-size: 12px; font-weight: 600;
                padding: 8px 16px;
            }}
            QPushButton:hover {{ background: {COLORS['warning']}33; }}
        """)
        self._return_btn.clicked.connect(self.return_requested)
        self._return_btn.hide()
        bl.addWidget(self._return_btn)

        self._stash_lbl = QLabel("")
        self._stash_lbl.setStyleSheet(
            f"background: transparent; font-size: 11px; font-weight: 600; color: {COLORS['text_muted']};"
        )
        self._stash_lbl.hide()
        bl.addWidget(self._stash_lbl)

        self._stash_files_lbl = QLabel("")
        self._stash_files_lbl.setWordWrap(True)
        self._stash_files_lbl.setStyleSheet(
            f"background: transparent; font-size: 10px; color: {COLORS['text_muted']};"
        )
        self._stash_files_lbl.hide()
        bl.addWidget(self._stash_files_lbl)

        root.addWidget(body)

        self._current_sha    = ""
        self._current_branch = ""

    def _on_jump(self):
        if self._current_sha:
            self.jump_requested.emit(self._current_sha)

    def set_pull_state(self, can_pull: bool):
        self._pull_btn.setVisible(can_pull)

    def set_exploring(self, exploring: bool, stashed_files: list[str] | None = None):
        self._explore_badge.setVisible(exploring)
        self._return_btn.setVisible(exploring)
        self._jump_btn.setVisible(not exploring)
        if exploring:
            self._pull_btn.hide()
            self._title.setText("Exploring the past")
            self._dot.setStyleSheet(
                f"background: transparent; font-size: 8px; color: {COLORS['warning']};"
            )
            if stashed_files:
                self._stash_lbl.setText("Saved changes")
                self._stash_lbl.show()
                self._render_stash_files(stashed_files)
            else:
                self._stash_lbl.hide()
                self._stash_files_lbl.hide()
        else:
            self._title.setText("Where you are now")
            self._dot.setStyleSheet(
                f"background: transparent; font-size: 8px; color: {COLORS['accent']};"
            )
            self._stash_lbl.hide()
            self._stash_files_lbl.hide()
        self.adjustSize()

    def update_stash_files(self, files: list[str]):
        if not files:
            return
        self._render_stash_files(files)
        self.adjustSize()

    def _render_stash_files(self, files: list[str]):
        MAX = 5
        lines = [f"  {f}" for f in files[:MAX]]
        if len(files) > MAX:
            lines.append(f"  …and {len(files) - MAX} more")
        self._stash_files_lbl.setText("\n".join(lines))
        self._stash_files_lbl.show()

    def load(self, message: str, branch: str, sha: str, author: str = "", avatar_url: str = ""):
        self._current_sha    = sha
        self._current_branch = branch
        self._avatar.set_author(author or "?", avatar_url)
        self._author_lbl.setText(author or "—")
        self._name_lbl.set_value(message.splitlines()[0] if message else "—")
        self._branch_lbl.set_value(branch or "—")
        self._sha_lbl.set_value(sha[:7] if sha else "—")
        self.adjustSize()
        self.show()

    def clear(self):
        self._author_lbl.setText("—")
        self._name_lbl.set_value("—")
        self._branch_lbl.set_value("—")
        self._sha_lbl.set_value("—")
        self.set_exploring(False)
        self.set_pull_state(False)
        self.adjustSize()
        self.hide()


class _Field(QWidget):
    def __init__(self, label: str, value: str, parent=None):
        super().__init__(parent)
        self.setStyleSheet("background: transparent;")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(2)

        lbl = QLabel(label)
        lbl.setStyleSheet(
            f"background: transparent; font-size: 9px; font-weight: 400;"
            f" color: {COLORS['text_muted']};"
        )
        layout.addWidget(lbl)

        self._val = QLabel(value)
        self._val.setWordWrap(True)
        self._val.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self._val.setStyleSheet(
            f"background: transparent; font-size: 12px; color: {COLORS['text_primary']};"
        )
        layout.addWidget(self._val)

    def set_value(self, value: str):
        self._val.setText(value)

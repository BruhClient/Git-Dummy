"""Top header bar for CommitViewPage."""
from __future__ import annotations

import qtawesome as qta

from PyQt5.QtCore import Qt, QSize, pyqtSignal
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
)

from styles.theme import COLORS


class _Header(QWidget):
    connect_requested = pyqtSignal()

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
            f"background: transparent; font-size: 14px; font-weight: 600; font-family: 'Tilt Warp'; color: {COLORS['text_primary']};"
        )
        name_block.addWidget(self._name)

        self._url = QLabel("")
        self._url.setStyleSheet(
            f"background: transparent; font-size: 11px; color: {COLORS['accent']};"
        )
        self._url.setOpenExternalLinks(True)
        self._url.hide()
        name_block.addWidget(self._url)

        self._local_path = QLabel("")
        self._local_path.setStyleSheet(
            f"background: transparent; font-size: 11px; color: {COLORS['text_muted']};"
        )
        self._local_path.hide()
        name_block.addWidget(self._local_path)

        layout.addLayout(name_block)
        layout.addStretch(1)

        self._center = QWidget()
        self._center.setStyleSheet("background: transparent;")
        self._center_layout = QHBoxLayout(self._center)
        self._center_layout.setContentsMargins(0, 0, 0, 0)
        self._center_layout.setSpacing(0)
        layout.addWidget(self._center)

        layout.addStretch(1)

        self._op_icon = QLabel()
        self._op_icon.setPixmap(qta.icon("fa5s.cog", color=COLORS["warning"]).pixmap(12, 12))
        self._op_icon.setStyleSheet("background: transparent;")
        self._op_icon.hide()
        layout.addWidget(self._op_icon)

        self._op_badge = QLabel("")
        self._op_badge.setStyleSheet(f"""
            background: #2d2010; border: 1px solid {COLORS['warning']};
            border-radius: 5px; color: {COLORS['warning']};
            font-size: 11px; font-weight: 600; font-family: 'Tilt Warp'; padding: 2px 10px;
        """)
        self._op_badge.hide()
        layout.addWidget(self._op_badge)

        self._status_badge = QLabel("● Local")
        self._status_badge.setStyleSheet(
            f"background: transparent; font-size: 11px; font-weight: 600; font-family: 'Tilt Warp';"
            f" color: {COLORS['text_muted']};"
        )
        self._status_badge.hide()
        layout.addWidget(self._status_badge)

        self._connect_btn = QPushButton("Connect →")
        self._connect_btn.setFixedHeight(26)
        self._connect_btn.setCursor(Qt.PointingHandCursor)
        self._connect_btn.setStyleSheet(f"""
            QPushButton {{
                background: transparent; border: 1px solid {COLORS['border']};
                border-radius: 5px; color: {COLORS['text_muted']};
                font-size: 11px; font-weight: 600; font-family: 'Tilt Warp'; padding: 0 10px;
            }}
            QPushButton:hover {{ border-color: {COLORS['accent']}; color: {COLORS['accent']}; }}
        """)
        self._connect_btn.clicked.connect(self.connect_requested)
        self._connect_btn.hide()
        layout.addWidget(self._connect_btn)

        self._viewer_badge = QLabel("Viewing")
        self._viewer_badge.setStyleSheet(
            f"background: transparent; color: {COLORS['accent']};"
            f" font-size: 11px; font-weight: 600; font-family: 'Tilt Warp';"
        )
        self._viewer_badge.hide()
        layout.addWidget(self._viewer_badge)

        self._count = QLabel("")
        self._count.setStyleSheet(f"background: transparent; font-size: 12px; color: {COLORS['text_muted']};")
        layout.addWidget(self._count)

    def set_center(self, widget: QWidget):
        self._center_layout.addWidget(widget)

    def set_repo(self, name: str):
        self._name.setText(name)

    def set_operation(self, op: str):
        if op:
            self._op_badge.setText(f"{op}…")
            self._op_icon.show()
            self._op_badge.show()
        else:
            self._op_icon.hide()
            self._op_badge.hide()

    def _update_height(self):
        """Resize the header to fit however many sub-rows are visible."""
        h = 52
        if not self._url.isHidden():
            h += 14
        if not self._local_path.isHidden():
            h += 14
        self.setFixedHeight(h)

    def set_url(self, url: str, visibility: str = ""):
        if visibility == "not_found":
            self._url.setText(
                '<span style="color:#ef4444; font-size:11px;">Repository deleted on GitHub</span>'
            )
            self._url.setFixedHeight(16)
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
            self._url.show()
        else:
            self._url.hide()
        self._update_height()

    def set_local_path(self, path: str):
        if path:
            self._local_path.setText(path)
            self._local_path.setFixedHeight(16)
            self._local_path.show()
        else:
            self._local_path.hide()
        self._update_height()

    def set_connection_state(self, has_remote: bool):
        if has_remote:
            self._status_badge.setText("● Remote")
            self._status_badge.setStyleSheet(
                f"background: transparent; font-size: 11px; font-weight: 600; font-family: 'Tilt Warp';"
                f" color: {COLORS['accent']};"
            )
            self._status_badge.show()
            self._connect_btn.hide()
        else:
            self._status_badge.setText("● Local")
            self._status_badge.setStyleSheet(
                f"background: transparent; font-size: 11px; font-weight: 600; font-family: 'Tilt Warp';"
                f" color: {COLORS['text_muted']};"
            )
            self._status_badge.show()
            self._connect_btn.show()

    def set_count(self, n: int, branch: str = "main"):
        self._count.setText(f"{n} on {branch}")

    def set_viewer_mode(self, is_viewer: bool):
        self._viewer_badge.setVisible(is_viewer)

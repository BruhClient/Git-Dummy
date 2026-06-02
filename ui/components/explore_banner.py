"""Banner shown when the user is exploring a past commit."""
from __future__ import annotations

import qtawesome as qta

from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtWidgets import QWidget, QHBoxLayout, QLabel, QPushButton

from styles.theme import COLORS


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

        icon = QLabel()
        icon.setPixmap(qta.icon("fa5s.search", color=COLORS["text_muted"]).pixmap(14, 14))
        icon.setStyleSheet("background: transparent;")
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
                color: white; font-size: 12px; font-weight: 600; font-family: 'Tilt Warp'; padding: 5px 14px;
            }}
            QPushButton:hover {{ background: {COLORS['accent_dim']}; }}
        """)
        btn.clicked.connect(self.return_requested)
        layout.addWidget(btn)

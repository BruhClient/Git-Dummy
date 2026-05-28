"""Full-page loading overlay widget."""
from __future__ import annotations

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QWidget, QVBoxLayout, QLabel

from styles.theme import COLORS


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

"""Canvas legend widget — explains the visual symbols."""
from __future__ import annotations

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel

from styles.theme import COLORS


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

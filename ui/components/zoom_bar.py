"""Zoom control bar that wraps a SpatialCanvas."""
from __future__ import annotations

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QWidget, QHBoxLayout, QPushButton

from styles.theme import COLORS


class ZoomBar(QWidget):
    _BTN = f"""
        QPushButton {{
            background: transparent; border: none;
            color: {COLORS['text_secondary']};
            font-size: 16px; font-weight: 600; font-family: 'Tilt Warp'; padding: 0 4px;
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

    def __init__(self, canvas, parent=None):
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
        from ui.canvas.constants import ZOOM_MIN, ZOOM_MAX
        self._minus.setEnabled(pct / 100 > ZOOM_MIN + 0.01)
        self._plus.setEnabled(pct / 100 < ZOOM_MAX - 0.01)

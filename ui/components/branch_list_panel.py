from __future__ import annotations
from typing import Optional

from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QScrollArea, QFrame,
)
from styles.theme import COLORS


class BranchListPanel(QWidget):
    """Floating overlay — top-right of canvas — listing each branch and its
    commit count in the currently loaded graph."""

    branch_focused = pyqtSignal(str)  # name, or "" to clear focus

    WIDTH = 210

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setObjectName("BranchListPanel")
        self.setFixedWidth(self.WIDTH)
        self._focused: Optional[str] = None
        self._rows: dict[str, _BranchRow] = {}
        self._build_ui()
        self._apply_style()

    # ── construction ──────────────────────────────────────────────────────────

    def _build_ui(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(10, 8, 10, 8)
        outer.setSpacing(6)

        header = QLabel("Branches")
        header.setObjectName("blpHeader")
        outer.addWidget(header)

        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setFrameShape(QFrame.NoFrame)
        self._scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._scroll.setMaximumHeight(240)

        self._container = QWidget()
        self._container.setObjectName("blpContainer")
        self._rows_layout = QVBoxLayout(self._container)
        self._rows_layout.setContentsMargins(0, 0, 0, 0)
        self._rows_layout.setSpacing(2)
        self._rows_layout.addStretch()

        self._scroll.setWidget(self._container)
        outer.addWidget(self._scroll)

    def _apply_style(self):
        self.setStyleSheet(f"""
            #BranchListPanel {{
                background: {COLORS['bg_card']};
                border: 1px solid {COLORS['border']};
                border-radius: 8px;
            }}
            #blpHeader {{
                color: {COLORS['text_muted']};
                font-size: 10px;
                font-weight: 600; font-family: 'Tilt Warp';
            }}
            QScrollArea {{
                background: transparent;
                border: none;
            }}
            #blpContainer {{
                background: transparent;
            }}
        """)

    # ── internal ──────────────────────────────────────────────────────────────

    def _on_row_clicked(self, name: str):
        if self._focused == name:
            self._focused = None
            self._update_row_states()
            self.branch_focused.emit("")
        else:
            self._focused = name
            self._update_row_states()
            self.branch_focused.emit(name)

    def _update_row_states(self):
        for name, row in self._rows.items():
            row.set_focused(name == self._focused)

    # ── public API ────────────────────────────────────────────────────────────

    def clear_focus(self):
        if self._focused:
            self._focused = None
            self._update_row_states()
            self.branch_focused.emit("")

    def update_branches(self, branch_counts: dict[str, int]):
        """Repopulate rows. branch_counts is {name: count}, sorted by caller."""
        while self._rows_layout.count() > 1:
            item = self._rows_layout.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()
        self._rows.clear()
        self._focused = None

        for branch, count in branch_counts.items():
            row = _BranchRow(branch, count, self._on_row_clicked, self._container)
            self._rows[branch] = row
            self._rows_layout.insertWidget(self._rows_layout.count() - 1, row)

        self.adjustSize()


class _BranchRow(QWidget):
    def __init__(self, branch: str, count: int, clicked_cb, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WA_StyledBackground, True)
        self._branch = branch
        self._clicked_cb = clicked_cb
        self.setCursor(Qt.PointingHandCursor)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 2, 0, 2)
        layout.setSpacing(6)

        self._name_lbl = QLabel(branch)
        self._name_lbl.setStyleSheet(
            f"color: {COLORS['text_primary']}; font-size: 12px; background: transparent;"
        )
        self._name_lbl.setMaximumWidth(145)
        self._name_lbl.setWordWrap(False)
        self._name_lbl.setTextInteractionFlags(Qt.NoTextInteraction)

        badge = QLabel(str(count))
        badge.setAlignment(Qt.AlignCenter)
        badge.setFixedSize(34, 18)
        badge.setStyleSheet(f"""
            background: {COLORS['accent_dim']};
            color: {COLORS['accent']};
            border-radius: 9px;
            font-size: 10px;
            font-weight: 600; font-family: 'Tilt Warp';
        """)

        layout.addWidget(self._name_lbl, 1)
        layout.addWidget(badge)

    def set_focused(self, focused: bool):
        if focused:
            self._name_lbl.setStyleSheet(
                f"color: {COLORS['accent']}; font-size: 12px; font-weight: 700; font-family: 'Tilt Warp'; background: transparent;"
            )
        else:
            self._name_lbl.setStyleSheet(
                f"color: {COLORS['text_primary']}; font-size: 12px; background: transparent;"
            )

    def mousePressEvent(self, event):
        self._clicked_cb(self._branch)
        super().mousePressEvent(event)

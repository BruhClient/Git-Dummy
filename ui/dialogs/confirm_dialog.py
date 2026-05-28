"""Styled confirmation and alert dialogs, plus convenience helpers."""
from __future__ import annotations

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QWidget,
)
from styles.theme import COLORS


class ConfirmDialog(QDialog):
    """Styled confirmation dialog — title, body text, Cancel + confirm button."""

    def __init__(self, parent=None, title: str = "", body: str = "",
                 confirm_text: str = "Yes", danger: bool = True):
        super().__init__(parent)
        self.setWindowFlags(Qt.Dialog | Qt.FramelessWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setFixedWidth(380)
        self._setup_ui(title, body, confirm_text, danger)

    def _setup_ui(self, title: str, body: str, confirm_text: str, danger: bool):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)

        card = QWidget()
        card.setStyleSheet(f"background: {COLORS['bg_card']}; border-radius: 12px;")
        vl = QVBoxLayout(card)
        vl.setContentsMargins(24, 24, 24, 24)
        vl.setSpacing(14)

        title_lbl = QLabel(title)
        title_lbl.setStyleSheet(
            f"font-size: 15px; font-weight: 700; color: {COLORS['text_primary']};"
            f" background: transparent;"
        )
        vl.addWidget(title_lbl)

        body_lbl = QLabel(body)
        body_lbl.setStyleSheet(
            f"font-size: 13px; color: {COLORS['text_muted']}; background: transparent;"
        )
        body_lbl.setWordWrap(True)
        vl.addWidget(body_lbl)

        btn_row = QHBoxLayout()
        btn_row.setSpacing(8)
        btn_row.addStretch()

        cancel_btn = QPushButton("Cancel")
        cancel_btn.setFixedHeight(38)
        cancel_btn.setMinimumWidth(80)
        cancel_btn.setCursor(Qt.PointingHandCursor)
        cancel_btn.setStyleSheet(f"""
            QPushButton {{
                background: transparent; border: 1px solid {COLORS['border']};
                border-radius: 8px; color: {COLORS['text_secondary']};
                font-size: 13px; font-weight: 600; padding: 0 16px;
            }}
            QPushButton:hover {{ border-color: {COLORS['text_secondary']}; }}
        """)
        cancel_btn.clicked.connect(self.reject)
        btn_row.addWidget(cancel_btn)

        confirm_bg = COLORS['danger'] if danger else COLORS['accent']
        confirm_hover = "#c53030" if danger else COLORS.get('accent_hover', COLORS['accent'])
        confirm_btn = QPushButton(confirm_text)
        confirm_btn.setFixedHeight(38)
        confirm_btn.setMinimumWidth(80)
        confirm_btn.setCursor(Qt.PointingHandCursor)
        confirm_btn.setStyleSheet(f"""
            QPushButton {{
                background: {confirm_bg}; border: none;
                border-radius: 8px; color: white;
                font-size: 13px; font-weight: 700; padding: 0 16px;
            }}
            QPushButton:hover {{ background: {confirm_hover}; }}
        """)
        confirm_btn.clicked.connect(self.accept)
        btn_row.addWidget(confirm_btn)

        vl.addLayout(btn_row)
        root.addWidget(card)


class AlertDialog(QDialog):
    """Styled alert dialog — title, body text, single OK button."""

    def __init__(self, parent=None, title: str = "", body: str = ""):
        super().__init__(parent)
        self.setWindowFlags(Qt.Dialog | Qt.FramelessWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setFixedWidth(380)
        self._setup_ui(title, body)

    def _setup_ui(self, title: str, body: str):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)

        card = QWidget()
        card.setStyleSheet(f"background: {COLORS['bg_card']}; border-radius: 12px;")
        vl = QVBoxLayout(card)
        vl.setContentsMargins(24, 24, 24, 24)
        vl.setSpacing(14)

        title_lbl = QLabel(title)
        title_lbl.setStyleSheet(
            f"font-size: 15px; font-weight: 700; color: {COLORS['text_primary']};"
            f" background: transparent;"
        )
        vl.addWidget(title_lbl)

        body_lbl = QLabel(body)
        body_lbl.setStyleSheet(
            f"font-size: 13px; color: {COLORS['text_muted']}; background: transparent;"
        )
        body_lbl.setWordWrap(True)
        vl.addWidget(body_lbl)

        btn_row = QHBoxLayout()
        btn_row.addStretch()

        ok_btn = QPushButton("OK")
        ok_btn.setFixedHeight(38)
        ok_btn.setMinimumWidth(80)
        ok_btn.setCursor(Qt.PointingHandCursor)
        ok_btn.setStyleSheet(f"""
            QPushButton {{
                background: transparent; border: 1px solid {COLORS['border']};
                border-radius: 8px; color: {COLORS['text_secondary']};
                font-size: 13px; font-weight: 600; padding: 0 16px;
            }}
            QPushButton:hover {{ border-color: {COLORS['text_secondary']}; }}
        """)
        ok_btn.clicked.connect(self.accept)
        btn_row.addWidget(ok_btn)

        vl.addLayout(btn_row)
        root.addWidget(card)


# ── Convenience functions ──────────────────────────────────────────────────────

def confirm(parent, title: str, body: str,
            confirm_text: str = "Yes", danger: bool = True) -> bool:
    """Show a styled confirmation dialog. Returns True if the user confirmed."""
    dlg = ConfirmDialog(parent, title, body, confirm_text, danger)
    return dlg.exec_() == QDialog.Accepted


def alert(parent, title: str, body: str) -> None:
    """Show a styled alert dialog with a single OK button."""
    AlertDialog(parent, title, body).exec_()

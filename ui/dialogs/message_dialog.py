"""Dark-themed single-line input dialog for commit messages, branch names, etc."""
from __future__ import annotations

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QWidget, QLineEdit,
)

from styles.theme import COLORS


class CommitMessageDialog(QDialog):
    """Dark-themed single-line input dialog (commit message, branch name, etc.)."""

    def __init__(self, parent=None, title: str = "Save Changes",
                 placeholder: str = "Commit message…"):
        super().__init__(parent)
        self.setWindowFlags(Qt.Dialog | Qt.FramelessWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setFixedWidth(420)

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)

        card = QWidget()
        card.setObjectName("cmCard")
        card.setAttribute(Qt.WA_StyledBackground, True)
        card.setStyleSheet(f"""
            #cmCard {{
                background: {COLORS['bg_card']};
                border: 1px solid {COLORS['border']};
                border-radius: 12px;
            }}
        """)
        vl = QVBoxLayout(card)
        vl.setContentsMargins(24, 20, 24, 20)
        vl.setSpacing(14)

        title_lbl = QLabel(title)
        title_lbl.setStyleSheet(
            f"font-size: 15px; font-weight: 700; font-family: 'Tilt Warp'; color: {COLORS['text_primary']};"
            f" background: transparent;"
        )
        vl.addWidget(title_lbl)

        self._input = QLineEdit()
        self._input.setPlaceholderText(placeholder)
        self._input.setStyleSheet(f"""
            QLineEdit {{
                background: {COLORS['bg_primary']};
                border: 1px solid {COLORS['border']};
                border-radius: 8px;
                color: {COLORS['text_primary']};
                font-size: 13px;
                padding: 9px 12px;
            }}
            QLineEdit:focus {{ border-color: {COLORS['accent']}; }}
        """)
        self._input.returnPressed.connect(self._on_save)
        vl.addWidget(self._input)

        btn_row = QHBoxLayout()
        btn_row.setSpacing(8)

        cancel_btn = QPushButton("Cancel")
        cancel_btn.setFixedHeight(38)
        cancel_btn.setCursor(Qt.PointingHandCursor)
        cancel_btn.setStyleSheet(f"""
            QPushButton {{
                background: transparent;
                border: 1px solid {COLORS['border']};
                border-radius: 8px;
                color: {COLORS['text_secondary']};
                font-size: 12px; font-weight: 600; font-family: 'Tilt Warp';
            }}
            QPushButton:hover {{ border-color: {COLORS['text_secondary']}; }}
        """)
        cancel_btn.clicked.connect(self.reject)

        save_btn = QPushButton("Save")
        save_btn.setFixedHeight(38)
        save_btn.setCursor(Qt.PointingHandCursor)
        save_btn.setStyleSheet(f"""
            QPushButton {{
                background: {COLORS['accent']};
                border: none;
                border-radius: 8px;
                color: {COLORS['text_on_accent']};
                font-size: 12px; font-weight: 700; font-family: 'Tilt Warp';
            }}
            QPushButton:hover {{ background: {COLORS.get('accent_hover', COLORS['accent'])}; }}
            QPushButton:disabled {{ background: {COLORS['border']}; color: {COLORS['text_muted']}; }}
        """)
        save_btn.clicked.connect(self._on_save)

        btn_row.addWidget(cancel_btn)
        btn_row.addWidget(save_btn)
        vl.addLayout(btn_row)

        root.addWidget(card)

    def _on_save(self):
        if self._input.text().strip():
            self.accept()

    def get_message(self) -> str:
        return self._input.text().strip()

    def showEvent(self, event):
        super().showEvent(event)
        self._input.clear()
        self._input.setFocus()


# Backward-compat alias used by detail_panel.py
_CommitMessageDialog = CommitMessageDialog

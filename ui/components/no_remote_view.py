"""No-remote placeholder view and compact banner."""
from __future__ import annotations

import qtawesome as qta

from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QLineEdit,
)

from styles.theme import COLORS


class _NoRemoteView(QWidget):
    create_requested = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setStyleSheet(f"background: {COLORS['bg_primary']};")

        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignCenter)
        layout.setSpacing(12)

        icon = QLabel()
        icon.setPixmap(qta.icon("fa5s.cloud", color=COLORS["text_muted"]).pixmap(52, 52))
        icon.setAlignment(Qt.AlignCenter)
        layout.addWidget(icon)

        title = QLabel("Not on GitHub yet")
        title.setStyleSheet(
            f"background: transparent; font-size: 17px; font-weight: 700; color: {COLORS['text_primary']};"
        )
        title.setAlignment(Qt.AlignCenter)
        layout.addWidget(title)

        sub = QLabel("Create a GitHub repository to back up your commits to the cloud.")
        sub.setStyleSheet(f"background: transparent; font-size: 13px; color: {COLORS['text_muted']};")
        sub.setAlignment(Qt.AlignCenter)
        sub.setWordWrap(True)
        layout.addWidget(sub)

        layout.addSpacing(8)

        self._btn = QPushButton("Create Repository →")
        self._btn.setFixedHeight(44)
        self._btn.setCursor(Qt.PointingHandCursor)
        self._btn.setStyleSheet(f"""
            QPushButton {{
                background: {COLORS['accent']}; border: none; border-radius: 8px;
                color: white; font-size: 13px; font-weight: 600; padding: 0 28px;
            }}
            QPushButton:hover {{ background: {COLORS['accent_dim']}; }}
            QPushButton:disabled {{ background: {COLORS['border']}; color: {COLORS['text_muted']}; }}
        """)
        self._btn.clicked.connect(self.create_requested)
        layout.addWidget(self._btn, 0, Qt.AlignCenter)

        self._status = QLabel("")
        self._status.setStyleSheet(f"background: transparent; font-size: 12px; color: {COLORS['text_muted']};")
        self._status.setAlignment(Qt.AlignCenter)
        layout.addWidget(self._status)

    def set_creating(self, creating: bool):
        self._btn.setEnabled(not creating)
        self._btn.setText("Creating…" if creating else "Create Repository →")
        self._status.setText("This may take a moment…" if creating else "")

    def set_error(self, msg: str):
        self._btn.setEnabled(True)
        self._btn.setText("Try again →")
        self._status.setStyleSheet(f"background: transparent; font-size: 12px; color: #ef4444;")
        self._status.setText(msg)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if self.parent():
            self.setGeometry(self.parent().rect())


class _NoRemoteBanner(QWidget):
    create_requested = pyqtSignal(str, bool)  # name, is_private

    _PILL = """
        QPushButton {{
            background: {bg}; border: 1px solid {border};
            border-radius: 5px; color: {fg};
            font-size: 11px; font-weight: 600; padding: 3px 12px;
        }}
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setStyleSheet(f"background: #13131f; border-bottom: 1px solid {COLORS['border']};")
        self.setFixedHeight(52)
        self._is_private = True

        layout = QHBoxLayout(self)
        layout.setContentsMargins(20, 0, 20, 0)
        layout.setSpacing(10)

        icon = QLabel()
        icon.setPixmap(qta.icon("fa5s.cloud", color=COLORS["text_muted"]).pixmap(15, 15))
        icon.setStyleSheet("background: transparent;")
        layout.addWidget(icon)

        self._msg_lbl = QLabel("Not on GitHub yet —")
        self._msg_lbl.setStyleSheet(f"background: transparent; font-size: 12px; color: {COLORS['text_muted']};")
        layout.addWidget(self._msg_lbl)

        self._name_input = QLineEdit()
        self._name_input.setPlaceholderText("repository name")
        self._name_input.setFixedSize(180, 30)
        self._name_input.setStyleSheet(f"""
            QLineEdit {{
                background: {COLORS['bg_card']}; border: 1px solid {COLORS['border']};
                border-radius: 6px; color: {COLORS['text_primary']};
                font-size: 12px; padding: 0 10px;
            }}
            QLineEdit:focus {{ border-color: {COLORS['accent']}; }}
        """)
        layout.addWidget(self._name_input)

        self._priv_btn = QPushButton("Private")
        self._pub_btn  = QPushButton("Public")
        for btn in (self._priv_btn, self._pub_btn):
            btn.setCursor(Qt.PointingHandCursor)
            btn.setFixedHeight(30)
        self._priv_btn.clicked.connect(lambda: self._set_privacy(True))
        self._pub_btn.clicked.connect(lambda: self._set_privacy(False))
        layout.addWidget(self._priv_btn)
        layout.addWidget(self._pub_btn)
        self._set_privacy(True, emit=False)

        layout.addStretch()

        self._btn = QPushButton("Create →")
        self._btn.setCursor(Qt.PointingHandCursor)
        self._btn.setFixedHeight(30)
        self._btn.setStyleSheet(f"""
            QPushButton {{
                background: {COLORS['accent']}; border: none; border-radius: 6px;
                color: white; font-size: 12px; font-weight: 600; padding: 0 16px;
            }}
            QPushButton:hover {{ background: {COLORS['accent_dim']}; }}
            QPushButton:disabled {{ background: {COLORS['border']}; color: {COLORS['text_muted']}; }}
        """)
        self._btn.clicked.connect(self._emit_create)
        layout.addWidget(self._btn)

    def set_repo_name(self, name: str):
        self._name_input.setText(name)

    def _set_privacy(self, private: bool, emit: bool = True):
        self._is_private = private
        active_style   = self._PILL.format(bg=COLORS['accent'], border=COLORS['accent'], fg="white")
        inactive_style = self._PILL.format(bg="transparent", border=COLORS['border'], fg=COLORS['text_muted'])
        self._priv_btn.setStyleSheet(active_style   if private else inactive_style)
        self._pub_btn.setStyleSheet( inactive_style if private else active_style)

    def _emit_create(self):
        name = self._name_input.text().strip()
        if name:
            self.create_requested.emit(name, self._is_private)

    def set_creating(self, creating: bool):
        self._btn.setEnabled(not creating)
        self._name_input.setEnabled(not creating)
        self._priv_btn.setEnabled(not creating)
        self._pub_btn.setEnabled(not creating)
        self._btn.setText("Creating…" if creating else "Create →")

    def set_error(self, msg: str):
        self.set_creating(False)
        self._btn.setText("Try again →")

    def show_deleted(self):
        """Switch banner to 'repo was deleted' warning state."""
        self.setStyleSheet("background: #2d1515; border-bottom: 1px solid #4a2020;")
        self._name_input.show()
        self._priv_btn.show()
        self._pub_btn.show()
        self._btn.show()
        self._btn.setText("Recreate →")
        self._msg_lbl.setText("Remote repository was deleted —")
        self._msg_lbl.setStyleSheet(f"background: transparent; font-size: 12px; color: #ef4444;")

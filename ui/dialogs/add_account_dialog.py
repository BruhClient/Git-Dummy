"""Modal dialog for adding a GitHub account via PAT or switching to an existing one."""
from __future__ import annotations

import webbrowser

import qtawesome as qta

from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QWidget,
    QFrame, QLineEdit, QSizePolicy, QSpacerItem,
)
from styles.theme import COLORS, BTN_PRIMARY
from auth.github_auth import PAT_CREATE_URL


class AddAccountDialog(QDialog):
    """Modal dialog for entering a GitHub PAT or selecting an existing account."""

    account_selected = pyqtSignal(str)

    def __init__(self, github_auth, parent=None):
        super().__init__(parent)
        self.setWindowFlags(Qt.Dialog | Qt.FramelessWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setFixedWidth(420)
        self._auth = github_auth
        self._eye_visible = False
        self._setup_ui()
        self._refresh_accounts()
        self._auth.auth_success.connect(self._on_auth_success)
        self._auth.auth_failed.connect(self._on_auth_failed)

    def _setup_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)

        card = QWidget()
        card.setObjectName("addAccountCard")
        card.setStyleSheet(f"""
            #addAccountCard {{
                background: {COLORS['bg_card']};
                border: 1px solid {COLORS['border']};
                border-radius: 12px;
            }}
        """)
        cl = QVBoxLayout(card)
        cl.setContentsMargins(28, 28, 28, 28)
        cl.setSpacing(14)

        # Title row with close button
        title_row = QHBoxLayout()
        title_row.setContentsMargins(0, 0, 0, 0)
        title = QLabel("Add account")
        title.setStyleSheet(
            f"font-size: 17px; font-weight: 700; font-family: 'Tilt Warp'; "
            f"color: {COLORS['text_primary']}; background: transparent;"
        )
        title_row.addWidget(title)
        title_row.addStretch()

        close_btn = QPushButton()
        close_btn.setFixedSize(28, 28)
        close_btn.setCursor(Qt.PointingHandCursor)
        close_btn.setIcon(qta.icon("fa5s.times", color=COLORS["text_muted"]))
        close_btn.setStyleSheet(
            f"QPushButton {{ background: transparent; border: none; border-radius: 14px; }}"
            f"QPushButton:hover {{ background: {COLORS['bg_hover']}; }}"
        )
        close_btn.clicked.connect(self.reject)
        title_row.addWidget(close_btn)
        cl.addLayout(title_row)

        # Description
        desc = QLabel("Paste a GitHub Personal Access Token.")
        desc.setStyleSheet(
            f"font-size: 13px; color: {COLORS['text_secondary']}; background: transparent;"
        )
        cl.addWidget(desc)

        # "Create a token" link
        link_row = QHBoxLayout()
        link_row.setContentsMargins(0, 0, 0, 0)
        link_row.setSpacing(4)
        link_btn = QPushButton("Create a token on GitHub")
        link_btn.setCursor(Qt.PointingHandCursor)
        link_btn.setStyleSheet(f"""
            QPushButton {{
                background: transparent; border: none; color: {COLORS['accent']};
                font-size: 12px; font-weight: 600; text-decoration: underline;
                padding: 0; text-align: left;
            }}
            QPushButton:hover {{ color: {COLORS.get('accent_hover', COLORS['accent'])}; }}
        """)
        link_btn.clicked.connect(lambda: webbrowser.open(PAT_CREATE_URL))
        link_row.addWidget(link_btn)
        ext_icon = QLabel()
        ext_icon.setPixmap(qta.icon("fa5s.external-link-alt", color=COLORS["accent"]).pixmap(10, 10))
        ext_icon.setStyleSheet("background: transparent;")
        link_row.addWidget(ext_icon)
        link_row.addStretch()
        cl.addLayout(link_row)

        # Divider
        div = QFrame()
        div.setFrameShape(QFrame.HLine)
        div.setStyleSheet(f"background-color: {COLORS['border']}; max-height: 1px;")
        cl.addWidget(div)

        # Existing accounts section
        self._accounts_section = QWidget()
        self._accounts_section.setStyleSheet("background: transparent;")
        acc_layout = QVBoxLayout(self._accounts_section)
        acc_layout.setContentsMargins(0, 0, 0, 0)
        acc_layout.setSpacing(6)

        acc_label = QLabel("Your accounts")
        acc_label.setStyleSheet(
            f"background: transparent; font-size: 12px; font-weight: 600; "
            f"color: {COLORS['text_secondary']};"
        )
        acc_layout.addWidget(acc_label)

        self._accounts_list = QVBoxLayout()
        self._accounts_list.setContentsMargins(0, 0, 0, 0)
        self._accounts_list.setSpacing(4)
        acc_layout.addLayout(self._accounts_list)

        acc_div = QFrame()
        acc_div.setFrameShape(QFrame.HLine)
        acc_div.setStyleSheet(f"background-color: {COLORS['border']}; max-height: 1px;")
        acc_layout.addWidget(acc_div)

        self._accounts_section.hide()
        cl.addWidget(self._accounts_section)

        # Token input label
        token_label = QLabel("Personal Access Token")
        token_label.setStyleSheet(
            f"background: transparent; font-size: 12px; font-weight: 600; "
            f"color: {COLORS['text_secondary']};"
        )
        cl.addWidget(token_label)

        # Token input
        self._token_input = QLineEdit()
        self._token_input.setPlaceholderText("ghp_xxxxxxxxxxxxxxxxxxxx")
        self._token_input.setEchoMode(QLineEdit.Password)
        self._token_input.setStyleSheet(f"""
            QLineEdit {{
                background: {COLORS['bg_secondary']}; border: 1px solid {COLORS['border']};
                border-radius: 8px; color: {COLORS['text_primary']};
                font-size: 13px; font-family: 'Consolas', 'Courier New', monospace;
                padding: 10px 40px 10px 12px;
            }}
            QLineEdit:focus {{ border-color: {COLORS['accent']}; }}
        """)
        self._token_input.setFixedHeight(42)
        self._token_input.textChanged.connect(self._on_text_changed)
        self._token_input.returnPressed.connect(self._on_submit)
        cl.addWidget(self._token_input)

        # Eye toggle
        self._eye_btn = QPushButton(self._token_input)
        self._eye_btn.setFixedSize(28, 28)
        self._eye_btn.setCursor(Qt.PointingHandCursor)
        self._eye_btn.setStyleSheet("QPushButton { background: transparent; border: none; }")
        self._update_eye_icon()
        self._eye_btn.clicked.connect(self._toggle_visibility)

        # Continue button
        self._continue_btn = QPushButton("Continue")
        self._continue_btn.setStyleSheet(BTN_PRIMARY)
        self._continue_btn.setFixedHeight(44)
        self._continue_btn.setCursor(Qt.PointingHandCursor)
        self._continue_btn.setEnabled(False)
        self._continue_btn.clicked.connect(self._on_submit)
        cl.addWidget(self._continue_btn)

        # Status
        self._status = QLabel("")
        self._status.setStyleSheet(
            f"background: transparent; font-size: 12px; color: {COLORS['text_muted']};"
        )
        self._status.setAlignment(Qt.AlignCenter)
        self._status.setWordWrap(True)
        cl.addWidget(self._status)

        # Error
        self._error = QLabel("")
        self._error.setStyleSheet(
            f"font-size: 12px; color: {COLORS['danger']}; "
            f"background: {COLORS['danger_dim']}; border-radius: 6px; padding: 8px 12px;"
        )
        self._error.setWordWrap(True)
        self._error.hide()
        cl.addWidget(self._error)

        # Legal note
        note = QLabel(
            "Your token is stored locally and only used to\n"
            "communicate with GitHub on your behalf."
        )
        note.setStyleSheet(
            f"background: transparent; font-size: 11px; color: {COLORS['text_muted']};"
        )
        note.setWordWrap(True)
        note.setAlignment(Qt.AlignCenter)
        cl.addWidget(note)

        root.addWidget(card)

    # ── accounts list ────────────────────────────────────────────────────────

    def _refresh_accounts(self):
        while self._accounts_list.count():
            item = self._accounts_list.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        accounts = self._auth.get_accounts()
        if not accounts:
            self._accounts_section.hide()
            return

        for acc in accounts:
            login = acc.get("login", "")
            name = acc.get("name", login)
            btn = QPushButton(f"  {name}  (@{login})")
            btn.setCursor(Qt.PointingHandCursor)
            btn.setFixedHeight(38)
            btn.setStyleSheet(f"""
                QPushButton {{
                    background: {COLORS['bg_secondary']}; border: 1px solid {COLORS['border']};
                    border-radius: 8px; color: {COLORS['text_primary']};
                    font-size: 12px; text-align: left; padding: 0 12px;
                }}
                QPushButton:hover {{ border-color: {COLORS['accent']}; background: {COLORS['bg_hover']}; }}
            """)
            btn.clicked.connect(lambda _=False, l=login: self._on_account_click(l))
            self._accounts_list.addWidget(btn)

        self._accounts_section.show()

    def _on_account_click(self, login: str):
        self.account_selected.emit(login)
        self.accept()

    # ── eye toggle ───────────────────────────────────────────────────────────

    def _update_eye_icon(self):
        icon_name = "fa5s.eye" if self._eye_visible else "fa5s.eye-slash"
        self._eye_btn.setIcon(qta.icon(icon_name, color=COLORS["text_muted"]))

    def _toggle_visibility(self):
        self._eye_visible = not self._eye_visible
        self._token_input.setEchoMode(
            QLineEdit.Normal if self._eye_visible else QLineEdit.Password
        )
        self._update_eye_icon()

    def _position_eye_btn(self):
        inp = self._token_input
        self._eye_btn.move(inp.width() - 36, (inp.height() - 28) // 2)

    # ── form handlers ────────────────────────────────────────────────────────

    def _on_text_changed(self, text: str):
        self._continue_btn.setEnabled(bool(text.strip()))
        self._error.hide()

    def _on_submit(self):
        token = self._token_input.text().strip()
        if not token:
            return
        self._token_input.setEnabled(False)
        self._continue_btn.setEnabled(False)
        self._continue_btn.setText("Validating…")
        self._status.setText("Checking your token with GitHub…")
        self._error.hide()
        self._auth.add_account(token)

    def _on_auth_success(self, user: dict):
        self.accept()

    def _on_auth_failed(self, message: str):
        self._token_input.setEnabled(True)
        self._continue_btn.setEnabled(bool(self._token_input.text().strip()))
        self._continue_btn.setText("Continue")
        self._status.setText("")
        self._error.setText(message)
        self._error.show()

    # ── lifecycle ────────────────────────────────────────────────────────────

    def showEvent(self, event):
        super().showEvent(event)
        self._token_input.setFocus()
        from PyQt5.QtCore import QTimer
        QTimer.singleShot(50, self._position_eye_btn)

    def _disconnect_signals(self):
        try:
            self._auth.auth_success.disconnect(self._on_auth_success)
        except TypeError:
            pass
        try:
            self._auth.auth_failed.disconnect(self._on_auth_failed)
        except TypeError:
            pass

    def reject(self):
        self._disconnect_signals()
        super().reject()

    def accept(self):
        self._disconnect_signals()
        super().accept()

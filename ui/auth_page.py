import os
import webbrowser

import qtawesome as qta

from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtGui import QPixmap, QPainter, QColor, QPen, QBrush, QPainterPath
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QSizePolicy,
    QFrame, QSpacerItem, QScrollArea, QLineEdit,
)
from styles.theme import (
    COLORS, BTN_PRIMARY, BTN_SECONDARY, GLOBAL_STYLE, LOGO_FONT,
)
from auth.github_auth import PAT_CREATE_URL


class LogoMark(QLabel):
    """Git Dummy branded logo mark."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(48, 48)
        _logo_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "logo", "logo.png")
        src = QPixmap(_logo_path).scaled(48, 48, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        tinted = QPixmap(src.size())
        tinted.fill(Qt.transparent)
        tp = QPainter(tinted)
        tp.drawPixmap(0, 0, src)
        tp.setCompositionMode(QPainter.CompositionMode_SourceIn)
        tp.fillRect(tinted.rect(), QColor(COLORS["accent"]))
        tp.end()
        rounded = QPixmap(48, 48)
        rounded.fill(Qt.transparent)
        painter = QPainter(rounded)
        painter.setRenderHint(QPainter.Antialiasing)
        clip = QPainterPath()
        clip.addRoundedRect(0, 0, 48, 48, 10, 10)
        painter.setClipPath(clip)
        painter.drawPixmap(0, 0, tinted)
        painter.end()
        self.setPixmap(rounded)


class AuthPage(QWidget):
    """Full-screen sign-in page — Personal Access Token entry."""

    account_selected = pyqtSignal(str)

    def __init__(self, github_auth, parent=None):
        super().__init__(parent)
        self._auth = github_auth
        self._setup_ui()

    def _setup_ui(self):
        self.setStyleSheet(GLOBAL_STYLE + f"QWidget {{ background-color: {COLORS['bg_primary']}; }}")

        root = QHBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ── Left panel: branding ──────────────────────────────────────────────
        left = QWidget()
        left.setObjectName("authLeft")
        left.setStyleSheet(f"""
            #authLeft {{
                background-color: {COLORS['bg_secondary']};
                border-right: 1px solid {COLORS['border']};
            }}
        """)
        left.setFixedWidth(420)
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(48, 48, 48, 48)
        left_layout.setSpacing(0)

        logo_row = QHBoxLayout()
        logo_row.setSpacing(12)
        logo_row.addWidget(LogoMark())
        app_name = QLabel("Git Dummy")
        app_name.setStyleSheet(f"background: transparent; font-size: 20px; font-weight: 700; font-family: {LOGO_FONT}; color: {COLORS['text_primary']};")
        logo_row.addWidget(app_name)
        logo_row.addStretch()
        left_layout.addLayout(logo_row)

        left_layout.addSpacerItem(QSpacerItem(0, 48, QSizePolicy.Minimum, QSizePolicy.Fixed))

        tagline = QLabel("Every change you've made,\nbeautifully visualised.")
        tagline.setStyleSheet(f"background: transparent; font-size: 28px; font-weight: 700; color: {COLORS['text_primary']}; line-height: 1.3;")
        tagline.setWordWrap(True)
        left_layout.addWidget(tagline)

        left_layout.addSpacerItem(QSpacerItem(0, 16, QSizePolicy.Minimum, QSizePolicy.Fixed))

        sub = QLabel(
            "See every commit your team has made, explore your project's\n"
            "full history, and understand changes at a glance."
        )
        sub.setStyleSheet(f"background: transparent; font-size: 14px; color: {COLORS['text_secondary']}; line-height: 1.6;")
        sub.setWordWrap(True)
        left_layout.addWidget(sub)

        left_layout.addStretch()

        for text in ["Visual commit history", "See all your versions", "GitHub integration"]:
            pill_row = QWidget()
            pill_row.setStyleSheet("background: transparent;")
            pill_layout = QHBoxLayout(pill_row)
            pill_layout.setContentsMargins(0, 0, 0, 6)
            pill_layout.setSpacing(6)
            check_lbl = QLabel()
            check_lbl.setPixmap(qta.icon("fa5s.check", color=COLORS["accent"]).pixmap(10, 10))
            check_lbl.setStyleSheet("background: transparent;")
            pill_layout.addWidget(check_lbl)
            text_lbl = QLabel(text)
            text_lbl.setStyleSheet(f"background: transparent; font-size: 13px; color: {COLORS['accent']};")
            pill_layout.addWidget(text_lbl)
            pill_layout.addStretch()
            left_layout.addWidget(pill_row)

        left_layout.addSpacerItem(QSpacerItem(0, 32, QSizePolicy.Minimum, QSizePolicy.Fixed))

        footer = QLabel("© 2026 Git Dummy")
        footer.setStyleSheet(f"background: transparent; font-size: 12px; color: {COLORS['text_muted']};")
        left_layout.addWidget(footer)

        root.addWidget(left)

        # ── Right panel ───────────────────────────────────────────────────────
        right = QWidget()
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setAlignment(Qt.AlignCenter)

        card = QWidget()
        card.setObjectName("loginCard")
        card.setFixedWidth(380)
        card.setStyleSheet(f"""
            #loginCard {{
                background-color: {COLORS['bg_card']};
                border: 1px solid {COLORS['border']};
                border-radius: 12px;
            }}
        """)

        self._card_layout = QVBoxLayout(card)
        self._card_layout.setContentsMargins(36, 36, 36, 36)
        self._card_layout.setSpacing(16)

        # ── Sign-in block ─────────────────────────────────────────────────────
        self._signin_block = QWidget()
        self._signin_block.setStyleSheet("background: transparent;")
        sb_layout = QVBoxLayout(self._signin_block)
        sb_layout.setContentsMargins(0, 0, 0, 0)
        sb_layout.setSpacing(14)

        title = QLabel("Sign in")
        title.setStyleSheet(f"background: transparent; font-size: 22px; font-weight: 700; color: {COLORS['text_primary']};")
        sb_layout.addWidget(title)

        desc = QLabel("Paste a GitHub Personal Access Token\nto get started.")
        desc.setStyleSheet(f"background: transparent; font-size: 13px; color: {COLORS['text_secondary']}; line-height: 1.5;")
        sb_layout.addWidget(desc)

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
        sb_layout.addLayout(link_row)

        divider = QFrame()
        divider.setFrameShape(QFrame.HLine)
        divider.setStyleSheet(f"background-color: {COLORS['border']}; max-height: 1px;")
        sb_layout.addWidget(divider)

        # Existing accounts section (shown when adding another account)
        self._accounts_section = QWidget()
        self._accounts_section.setStyleSheet("background: transparent;")
        acc_layout = QVBoxLayout(self._accounts_section)
        acc_layout.setContentsMargins(0, 0, 0, 0)
        acc_layout.setSpacing(6)

        acc_label = QLabel("Your accounts")
        acc_label.setStyleSheet(f"background: transparent; font-size: 12px; font-weight: 600; color: {COLORS['text_secondary']};")
        acc_layout.addWidget(acc_label)

        self._accounts_list = QVBoxLayout()
        self._accounts_list.setContentsMargins(0, 0, 0, 0)
        self._accounts_list.setSpacing(4)
        acc_layout.addLayout(self._accounts_list)

        acc_divider = QFrame()
        acc_divider.setFrameShape(QFrame.HLine)
        acc_divider.setStyleSheet(f"background-color: {COLORS['border']}; max-height: 1px;")
        acc_layout.addWidget(acc_divider)

        self._accounts_section.hide()
        sb_layout.addWidget(self._accounts_section)

        # Token input
        token_label = QLabel("Personal Access Token")
        token_label.setStyleSheet(f"background: transparent; font-size: 12px; font-weight: 600; color: {COLORS['text_secondary']};")
        sb_layout.addWidget(token_label)

        input_row = QHBoxLayout()
        input_row.setContentsMargins(0, 0, 0, 0)
        input_row.setSpacing(0)

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
        sb_layout.addWidget(self._token_input)

        # Eye toggle (overlaid on the input)
        self._eye_btn = QPushButton(self._token_input)
        self._eye_btn.setFixedSize(28, 28)
        self._eye_btn.setCursor(Qt.PointingHandCursor)
        self._eye_btn.setStyleSheet(f"""
            QPushButton {{
                background: transparent; border: none; padding: 0;
            }}
        """)
        self._eye_visible = False
        self._update_eye_icon()
        self._eye_btn.clicked.connect(self._toggle_visibility)

        # Continue button
        self._continue_btn = QPushButton("Continue")
        self._continue_btn.setStyleSheet(BTN_PRIMARY)
        self._continue_btn.setFixedHeight(44)
        self._continue_btn.setCursor(Qt.PointingHandCursor)
        self._continue_btn.setEnabled(False)
        self._continue_btn.clicked.connect(self._on_submit)
        sb_layout.addWidget(self._continue_btn)

        # Status
        self._status = QLabel("")
        self._status.setStyleSheet(f"background: transparent; font-size: 12px; color: {COLORS['text_muted']}; text-align: center;")
        self._status.setAlignment(Qt.AlignCenter)
        self._status.setWordWrap(True)
        sb_layout.addWidget(self._status)

        # Error
        self._error = QLabel("")
        self._error.setStyleSheet(
            f"font-size: 12px; color: {COLORS['danger']}; "
            f"background: {COLORS['danger_dim']}; border-radius: 6px; padding: 8px 12px;"
        )
        self._error.setWordWrap(True)
        self._error.hide()
        sb_layout.addWidget(self._error)

        sb_layout.addSpacerItem(QSpacerItem(0, 4, QSizePolicy.Minimum, QSizePolicy.Fixed))

        note = QLabel(
            "Your token is stored locally and only used to\n"
            "communicate with GitHub on your behalf."
        )
        note.setStyleSheet(f"background: transparent; font-size: 11px; color: {COLORS['text_muted']}; line-height: 1.5;")
        note.setWordWrap(True)
        note.setAlignment(Qt.AlignCenter)
        sb_layout.addWidget(note)

        self._card_layout.addWidget(self._signin_block)

        right_layout.addWidget(card)
        root.addWidget(right)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._position_eye_btn()

    def _position_eye_btn(self):
        inp = self._token_input
        self._eye_btn.move(inp.width() - 36, (inp.height() - 28) // 2)

    def _update_eye_icon(self):
        icon_name = "fa5s.eye" if self._eye_visible else "fa5s.eye-slash"
        self._eye_btn.setIcon(qta.icon(icon_name, color=COLORS["text_muted"]))

    def _toggle_visibility(self):
        self._eye_visible = not self._eye_visible
        self._token_input.setEchoMode(
            QLineEdit.Normal if self._eye_visible else QLineEdit.Password
        )
        self._update_eye_icon()

    # ── public ────────────────────────────────────────────────────────────────

    def show_sign_in(self):
        self._signin_block.show()
        self._refresh_accounts_section()
        self._token_input.setFocus()
        from PyQt5.QtCore import QTimer
        QTimer.singleShot(100, self._position_eye_btn)

    def show_checking_session(self):
        """Shown briefly on launch while we try to restore a saved sign-in."""
        self._status.setText("Checking your saved session…")
        self._error.hide()
        self._token_input.setEnabled(False)
        self._continue_btn.setEnabled(False)
        self.show_sign_in()

    def show_error(self, message: str):
        self._token_input.setEnabled(True)
        self._continue_btn.setEnabled(bool(self._token_input.text().strip()))
        self._continue_btn.setText("Continue")
        self._status.setText("")
        self._error.setText(message)
        self._error.show()

    def reset(self):
        self._token_input.setEnabled(True)
        self._token_input.clear()
        self._continue_btn.setEnabled(False)
        self._continue_btn.setText("Continue")
        self._status.setText("")
        self._error.hide()
        self.show_sign_in()

    # ── internals ────────────────────────────────────────────────────────────

    def _refresh_accounts_section(self):
        accounts = self._auth.get_accounts()
        while self._accounts_list.count():
            item = self._accounts_list.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

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

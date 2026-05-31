import os
import threading

import qtawesome as qta

from PyQt5.QtCore import Qt, QSize, pyqtSignal
from PyQt5.QtGui import QFont, QPixmap, QPainter, QColor, QPen, QBrush, QPainterPath
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QSizePolicy,
    QFrame, QSpacerItem, QScrollArea,
)
from styles.theme import (
    COLORS, BTN_PRIMARY, BTN_SECONDARY, GLOBAL_STYLE,
)


class GitHubIcon(QWidget):
    """Simple GitHub Octocat SVG-like icon drawn with QPainter."""

    def __init__(self, size=24, color=None, parent=None):
        super().__init__(parent)
        self._size = size
        self._color = color or COLORS["text_on_accent"]
        self.setFixedSize(size, size)

    def paintEvent(self, _event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        c = QColor(self._color)
        painter.setBrush(QBrush(c))
        painter.setPen(Qt.NoPen)
        s = self._size
        painter.drawEllipse(1, 1, s - 2, s - 2)
        painter.setBrush(QBrush(QColor(self._color if self._color != COLORS["text_on_accent"] else "#3ecf8e")))
        painter.setPen(Qt.NoPen)
        painter.drawEllipse(s // 4, s // 5, s // 2, s // 2)
        painter.end()


class LogoMark(QLabel):
    """Evo Git branded logo mark."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(48, 48)
        _logo_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "logo", "optimised_logo1.png")
        src = QPixmap(_logo_path).scaled(48, 48, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        rounded = QPixmap(48, 48)
        rounded.fill(Qt.transparent)
        painter = QPainter(rounded)
        painter.setRenderHint(QPainter.Antialiasing)
        clip = QPainterPath()
        clip.addRoundedRect(0, 0, 48, 48, 10, 10)
        painter.setClipPath(clip)
        painter.drawPixmap(0, 0, src)
        painter.end()
        self.setPixmap(rounded)


class _MiniAvatar(QWidget):
    """Small circular avatar with initials fallback."""

    def __init__(self, size=32, parent=None):
        super().__init__(parent)
        self.setFixedSize(size, size)
        self._size = size
        self._initials = ""
        self._pixmap: QPixmap | None = None

    def set_initials(self, initials: str):
        self._initials = initials
        self._pixmap = None
        self.update()

    def set_pixmap(self, pixmap: QPixmap):
        s = self._size
        self._pixmap = pixmap.scaled(s, s, Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation)
        self.update()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        s = self._size
        clip = QPainterPath()
        clip.addEllipse(0, 0, s, s)
        p.setClipPath(clip)
        if self._pixmap:
            src = self._pixmap
            p.drawPixmap(0, 0, src, (src.width() - s) // 2, (src.height() - s) // 2, s, s)
        else:
            p.setBrush(QBrush(QColor(COLORS["accent_dim"])))
            p.setPen(Qt.NoPen)
            p.drawEllipse(0, 0, s, s)
            p.setClipping(False)
            p.setPen(QPen(QColor(COLORS["accent"])))
            p.setFont(QFont("Inter", s // 3, QFont.Bold))
            p.drawText(self.rect(), Qt.AlignCenter, self._initials)
        p.setClipping(False)
        p.setPen(QPen(QColor(COLORS["accent"]), 1.5))
        p.setBrush(Qt.NoBrush)
        p.drawEllipse(1, 1, s - 2, s - 2)
        p.end()


def _fetch_avatar(url: str, widget: _MiniAvatar):
    try:
        import requests
        r = requests.get(url, timeout=8)
        if r.status_code == 200:
            pm = QPixmap()
            pm.loadFromData(r.content)
            if not pm.isNull():
                widget.set_pixmap(pm)
    except Exception:
        pass


class AuthPage(QWidget):
    """
    Full-screen login/account-picker page.

    Signals:
        account_selected(str)  — login of the saved account the user clicked
        add_account_clicked()  — user wants to add a new account via OAuth
    """

    account_selected = pyqtSignal(str)
    add_account_clicked = pyqtSignal()

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
        app_name = QLabel("Evo Git")
        app_name.setStyleSheet(f"background: transparent; font-size: 20px; font-weight: 700; color: {COLORS['text_primary']};")
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

        footer = QLabel("© 2026 Evo Git")
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
        card.setFixedWidth(360)
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
        sb_layout.setSpacing(16)

        title = QLabel("Sign in")
        title.setStyleSheet(f"background: transparent; font-size: 22px; font-weight: 700; color: {COLORS['text_primary']};")
        sb_layout.addWidget(title)

        desc = QLabel("Connect your GitHub account to explore\nyour projects and their full history.")
        desc.setStyleSheet(f"background: transparent; font-size: 13px; color: {COLORS['text_secondary']}; line-height: 1.5;")
        sb_layout.addWidget(desc)

        divider = QFrame()
        divider.setFrameShape(QFrame.HLine)
        divider.setStyleSheet(f"background-color: {COLORS['border']}; max-height: 1px;")
        sb_layout.addWidget(divider)

        self._github_btn = QPushButton("  Continue with GitHub")
        self._github_btn.setStyleSheet(BTN_PRIMARY)
        self._github_btn.setFixedHeight(44)
        self._github_btn.setCursor(Qt.PointingHandCursor)
        self._github_btn.clicked.connect(self._on_github_click)
        sb_layout.addWidget(self._github_btn)

        self._status = QLabel("")
        self._status.setStyleSheet(f"background: transparent; font-size: 12px; color: {COLORS['text_muted']}; text-align: center;")
        self._status.setAlignment(Qt.AlignCenter)
        self._status.setWordWrap(True)
        sb_layout.addWidget(self._status)

        self._error = QLabel("")
        self._error.setStyleSheet(
            f"font-size: 12px; color: {COLORS['danger']}; "
            f"background: #2d1515; border-radius: 6px; padding: 8px 12px;"
        )
        self._error.setWordWrap(True)
        self._error.hide()
        sb_layout.addWidget(self._error)

        sb_layout.addSpacerItem(QSpacerItem(0, 8, QSizePolicy.Minimum, QSizePolicy.Fixed))

        note = QLabel(
            "By continuing, you agree to our Terms of Service.\n"
            "Evo Git only reads your projects — it never makes changes."
        )
        note.setStyleSheet(f"background: transparent; font-size: 11px; color: {COLORS['text_muted']}; line-height: 1.5;")
        note.setWordWrap(True)
        note.setAlignment(Qt.AlignCenter)
        sb_layout.addWidget(note)

        self._card_layout.addWidget(self._signin_block)

        # ── Account picker block ──────────────────────────────────────────────
        self._picker_block = QWidget()
        self._picker_block.setStyleSheet("background: transparent;")
        pb_layout = QVBoxLayout(self._picker_block)
        pb_layout.setContentsMargins(0, 0, 0, 0)
        pb_layout.setSpacing(12)

        picker_title = QLabel("Choose an account")
        picker_title.setStyleSheet(
            f"background: transparent; font-size: 22px; font-weight: 700; color: {COLORS['text_primary']};"
        )
        pb_layout.addWidget(picker_title)

        picker_sub = QLabel("Select an account to continue, or add a new one.")
        picker_sub.setStyleSheet(
            f"background: transparent; font-size: 13px; color: {COLORS['text_secondary']};"
        )
        pb_layout.addWidget(picker_sub)

        # Account rows container (rebuilt on each show_account_picker call)
        self._accounts_container = QWidget()
        self._accounts_container.setStyleSheet("background: transparent;")
        self._accounts_layout = QVBoxLayout(self._accounts_container)
        self._accounts_layout.setContentsMargins(0, 0, 0, 0)
        self._accounts_layout.setSpacing(6)
        pb_layout.addWidget(self._accounts_container)

        add_btn = QPushButton("+ Add account")
        add_btn.setFixedHeight(40)
        add_btn.setCursor(Qt.PointingHandCursor)
        add_btn.setStyleSheet(f"""
            QPushButton {{
                background: transparent;
                border: 1px solid {COLORS['border']};
                border-radius: 8px;
                font-size: 13px;
                font-weight: 600;
                color: {COLORS['accent']};
            }}
            QPushButton:hover {{
                background: {COLORS['bg_hover']};
                border-color: {COLORS['accent']};
            }}
        """)
        add_btn.clicked.connect(self._on_add_account_click)
        pb_layout.addWidget(add_btn)

        self._picker_block.hide()
        self._card_layout.addWidget(self._picker_block)

        right_layout.addWidget(card)
        root.addWidget(right)

    # ── public ────────────────────────────────────────────────────────────────

    def show_sign_in(self):
        self._picker_block.hide()
        self._signin_block.show()

    def show_account_picker(self, accounts: list[dict]):
        self._signin_block.hide()

        # Rebuild account rows
        while self._accounts_layout.count():
            item = self._accounts_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        for acc in accounts:
            login = acc.get("login", "")
            name = acc.get("name") or login
            avatar_url = acc.get("avatar_url", "")
            row = self._make_account_row(login, name, avatar_url)
            self._accounts_layout.addWidget(row)

        self._picker_block.show()

    def show_error(self, message: str):
        self._github_btn.setEnabled(True)
        self._github_btn.setText("  Continue with GitHub")
        self._status.setText("")
        self._error.setText(f"Error: {message}")
        self._error.show()

    def reset(self):
        self._github_btn.setEnabled(True)
        self._github_btn.setText("  Continue with GitHub")
        self._status.setText("")
        self._error.hide()
        self.show_sign_in()

    # ── internals ────────────────────────────────────────────────────────────

    def _make_account_row(self, login: str, name: str, avatar_url: str) -> QPushButton:
        row = QPushButton()
        row.setFlat(True)
        row.setCursor(Qt.PointingHandCursor)
        row.setFixedHeight(52)
        row.setStyleSheet(f"""
            QPushButton {{
                background: {COLORS['bg_secondary']};
                border: 1px solid {COLORS['border']};
                border-radius: 8px;
                text-align: left;
                padding: 0;
            }}
            QPushButton:hover {{
                background: {COLORS['bg_hover']};
                border-color: {COLORS['accent']};
            }}
        """)

        h = QHBoxLayout(row)
        h.setContentsMargins(12, 0, 12, 0)
        h.setSpacing(12)

        avatar = _MiniAvatar(32)
        avatar.set_initials((name[:2].upper()) if name else "EG")
        if avatar_url:
            threading.Thread(target=_fetch_avatar, args=(avatar_url, avatar), daemon=True).start()
        h.addWidget(avatar)

        text_col = QVBoxLayout()
        text_col.setSpacing(1)

        name_lbl = QLabel(name)
        name_lbl.setStyleSheet(
            f"background: transparent; font-size: 13px; font-weight: 600; color: {COLORS['text_primary']};"
        )
        text_col.addWidget(name_lbl)

        login_lbl = QLabel(f"@{login}")
        login_lbl.setStyleSheet(
            f"background: transparent; font-size: 11px; color: {COLORS['text_muted']};"
        )
        text_col.addWidget(login_lbl)

        h.addLayout(text_col)
        h.addStretch()

        arrow = QLabel("→")
        arrow.setStyleSheet(f"background: transparent; font-size: 14px; color: {COLORS['text_muted']};")
        h.addWidget(arrow)

        row.clicked.connect(lambda _=False, l=login: self.account_selected.emit(l))
        return row

    def _on_github_click(self):
        self._github_btn.setEnabled(False)
        self._github_btn.setText("  Opening browser...")
        self._status.setText("Waiting for GitHub authorisation in your browser…")
        self._error.hide()
        self._auth.start_oauth_flow()

    def _on_add_account_click(self):
        self.add_account_clicked.emit()

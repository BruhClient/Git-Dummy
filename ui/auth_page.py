import os

import qtawesome as qta

from PyQt5.QtCore import Qt, QSize
from PyQt5.QtGui import QFont, QPixmap, QPainter, QColor, QPen, QBrush, QPainterPath
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QSizePolicy,
    QFrame, QSpacerItem,
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
        # Draw a circle as placeholder for the GitHub logo
        painter.drawEllipse(1, 1, s - 2, s - 2)

        # Draw a small cutout to hint at octocat head
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


class AuthPage(QWidget):
    """
    Full-screen login page shown before the user authenticates.
    Emits no signals directly — parent connects to GitHubAuth signals.
    """

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

        # Logo + name
        logo_row = QHBoxLayout()
        logo_row.setSpacing(12)
        logo_row.addWidget(LogoMark())
        app_name = QLabel("Evo Git")
        app_name.setStyleSheet(f"background: transparent; font-size: 20px; font-weight: 700; color: {COLORS['text_primary']};")
        logo_row.addWidget(app_name)
        logo_row.addStretch()
        left_layout.addLayout(logo_row)

        left_layout.addSpacerItem(QSpacerItem(0, 48, QSizePolicy.Minimum, QSizePolicy.Fixed))

        # Tagline
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

        # Feature pills
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

        # ── Right panel: login card ───────────────────────────────────────────
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

        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(36, 36, 36, 36)
        card_layout.setSpacing(16)

        # Card header
        title = QLabel("Sign in")
        title.setStyleSheet(f"background: transparent; font-size: 22px; font-weight: 700; color: {COLORS['text_primary']};")
        card_layout.addWidget(title)

        desc = QLabel("Connect your GitHub account to explore\nyour projects and their full history.")
        desc.setStyleSheet(f"background: transparent; font-size: 13px; color: {COLORS['text_secondary']}; line-height: 1.5;")
        card_layout.addWidget(desc)

        divider = QFrame()
        divider.setFrameShape(QFrame.HLine)
        divider.setStyleSheet(f"background-color: {COLORS['border']}; max-height: 1px;")
        card_layout.addWidget(divider)

        # GitHub button
        self._github_btn = QPushButton("  Continue with GitHub")
        self._github_btn.setStyleSheet(BTN_PRIMARY)
        self._github_btn.setFixedHeight(44)
        self._github_btn.setCursor(Qt.PointingHandCursor)
        self._github_btn.clicked.connect(self._on_github_click)
        card_layout.addWidget(self._github_btn)

        # Status label
        self._status = QLabel("")
        self._status.setStyleSheet(f"background: transparent; font-size: 12px; color: {COLORS['text_muted']}; text-align: center;")
        self._status.setAlignment(Qt.AlignCenter)
        self._status.setWordWrap(True)
        card_layout.addWidget(self._status)

        # Error label (hidden by default)
        self._error = QLabel("")
        self._error.setStyleSheet(
            f"font-size: 12px; color: {COLORS['danger']}; "
            f"background: #2d1515; border-radius: 6px; padding: 8px 12px;"
        )
        self._error.setWordWrap(True)
        self._error.hide()
        card_layout.addWidget(self._error)

        card_layout.addSpacerItem(QSpacerItem(0, 8, QSizePolicy.Minimum, QSizePolicy.Fixed))

        note = QLabel(
            "By continuing, you agree to our Terms of Service.\n"
            "Evo Git only reads your projects — it never makes changes."
        )
        note.setStyleSheet(f"background: transparent; font-size: 11px; color: {COLORS['text_muted']}; line-height: 1.5;")
        note.setWordWrap(True)
        note.setAlignment(Qt.AlignCenter)
        card_layout.addWidget(note)

        right_layout.addWidget(card)
        root.addWidget(right)

    # ── slots ─────────────────────────────────────────────────────────────────

    def _on_github_click(self):
        self._github_btn.setEnabled(False)
        self._github_btn.setText("  Opening browser...")
        self._status.setText("Waiting for GitHub authorisation in your browser…")
        self._error.hide()
        self._auth.start_oauth_flow()

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

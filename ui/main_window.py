import os
import threading

from PyQt5.QtCore import Qt, pyqtSignal, QObject, pyqtSlot
from PyQt5.QtGui import QFont, QPainter, QColor, QBrush, QPen, QPixmap, QPainterPath
from PyQt5.QtWidgets import (
    QMainWindow, QWidget, QHBoxLayout, QVBoxLayout, QLabel,
    QPushButton, QStackedWidget,
)
from styles.theme import COLORS, make_global_style


def _LogoMark(parent=None):
    lbl = QLabel(parent)
    lbl.setFixedSize(28, 28)
    _logo_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "logo", "optimised_logo1.png")
    src = QPixmap(_logo_path).scaled(28, 28, Qt.KeepAspectRatio, Qt.SmoothTransformation)
    rounded = QPixmap(28, 28)
    rounded.fill(Qt.transparent)
    p = QPainter(rounded)
    p.setRenderHint(QPainter.Antialiasing)
    clip = QPainterPath()
    clip.addRoundedRect(0, 0, 28, 28, 6, 6)
    p.setClipPath(clip)
    p.drawPixmap(0, 0, src)
    p.end()
    lbl.setPixmap(rounded)
    return lbl


class _AvatarCircle(QWidget):
    def __init__(self, size=30, parent=None):
        super().__init__(parent)
        self.setFixedSize(size, size)
        self._size = size
        self._initials = "EG"
        self._pixmap: QPixmap | None = None

    def set_initials(self, initials: str):
        self._initials = initials
        self._pixmap = None
        self.update()

    def set_pixmap(self, pixmap: QPixmap):
        self._pixmap = pixmap.scaled(
            self._size, self._size,
            Qt.KeepAspectRatioByExpanding,
            Qt.SmoothTransformation,
        )
        self.update()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        s = self._size

        # Circular clip
        clip = QPainterPath()
        clip.addEllipse(0, 0, s, s)
        p.setClipPath(clip)

        if self._pixmap:
            # Centre-crop the image into the circle
            src = self._pixmap
            x_off = (src.width()  - s) // 2
            y_off = (src.height() - s) // 2
            p.drawPixmap(0, 0, src, x_off, y_off, s, s)
        else:
            p.setBrush(QBrush(QColor(COLORS["accent_dim"])))
            p.setPen(Qt.NoPen)
            p.drawEllipse(0, 0, s, s)
            p.setClipping(False)
            p.setPen(QPen(QColor(COLORS["accent"])))
            font = QFont("Inter", s // 3, QFont.Bold)
            p.setFont(font)
            p.drawText(self.rect(), Qt.AlignCenter, self._initials)

        p.setClipping(False)
        # Accent border ring
        p.setPen(QPen(QColor(COLORS["accent"]), 2))
        p.setBrush(Qt.NoBrush)
        p.drawEllipse(1, 1, s - 2, s - 2)
        p.end()


class TopNav(QWidget):
    """Slim top navigation bar — no sidebar."""

    back_clicked = pyqtSignal()
    logout_clicked = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("topNav")
        self.setFixedHeight(52)
        self.setStyleSheet(f"""
            #topNav {{
                background-color: {COLORS['bg_primary']};
                border-bottom: 1px solid {COLORS['border']};
            }}
        """)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(24, 0, 24, 0)
        layout.setSpacing(12)

        # Left: logo + app name
        logo = _LogoMark()
        layout.addWidget(logo)

        self._app_name = QLabel("Evo Git")
        self._app_name.setStyleSheet(
            f"font-size: 14px; font-weight: 700; color: {COLORS['text_primary']};"
        )
        layout.addWidget(self._app_name)

        layout.addSpacing(16)

        # Back button (hidden on repos page)
        self._back_btn = QPushButton("← Projects")
        self._back_btn.setCursor(Qt.PointingHandCursor)
        self._back_btn.setStyleSheet(f"""
            QPushButton {{
                background: transparent;
                border: none;
                color: {COLORS['text_muted']};
                font-size: 13px;
                padding: 4px 0;
            }}
            QPushButton:hover {{
                color: {COLORS['text_primary']};
            }}
        """)
        self._back_btn.clicked.connect(self.back_clicked.emit)
        self._back_btn.hide()
        layout.addWidget(self._back_btn)

        # Breadcrumb separator + repo name (hidden on repos page)
        self._sep = QLabel("›")
        self._sep.setStyleSheet(f"color: {COLORS['text_muted']}; font-size: 13px;")
        self._sep.hide()
        layout.addWidget(self._sep)

        self._page_label = QLabel("")
        self._page_label.setStyleSheet(
            f"font-size: 13px; font-weight: 600; color: {COLORS['text_primary']};"
        )
        self._page_label.hide()
        layout.addWidget(self._page_label)

        layout.addStretch()

        # Right: avatar + logout
        self._avatar = _AvatarCircle(30)
        layout.addWidget(self._avatar)

        self._username = QLabel("")
        self._username.setStyleSheet(f"background: transparent; font-size: 13px; color: {COLORS['text_secondary']};")
        layout.addWidget(self._username)

        _nav_btn_style = f"""
            QPushButton {{
                background: transparent;
                border: 1px solid {COLORS['border']};
                border-radius: 6px;
                color: {COLORS['text_muted']};
                font-size: 12px;
                padding: 4px 12px;
            }}
            QPushButton:hover {{
                background: {COLORS['bg_hover']};
                color: {COLORS['text_primary']};
            }}
        """

        logout_btn = QPushButton("Sign out")
        logout_btn.setCursor(Qt.PointingHandCursor)
        logout_btn.setStyleSheet(_nav_btn_style)
        logout_btn.clicked.connect(self.logout_clicked.emit)
        layout.addWidget(logout_btn)

    def set_user(self, user: dict):
        login = user.get("login", "")
        name  = user.get("name") or login
        self._avatar.set_initials(name[:2].upper() if name else "EG")
        self._username.setText(f"@{login}")

        avatar_url = user.get("avatar_url", "")
        if avatar_url:
            threading.Thread(
                target=self._download_avatar,
                args=(avatar_url, self._avatar),
                daemon=True,
            ).start()

    @staticmethod
    def _download_avatar(url: str, widget: "_AvatarCircle"):
        try:
            import requests
            resp = requests.get(url, timeout=10)
            if resp.status_code == 200:
                pm = QPixmap()
                pm.loadFromData(resp.content)
                if not pm.isNull():
                    widget.set_pixmap(pm)
        except Exception:
            pass

    def show_repos_state(self):
        self._back_btn.hide()
        self._sep.hide()
        self._page_label.hide()
        self._app_name.show()

    def show_commits_state(self, repo_name: str = ""):
        self._back_btn.show()
        self._sep.show()
        self._page_label.setText(repo_name)
        self._page_label.show()
        # Hide the app name when the breadcrumb is showing — avoids
        # "Evo Git › Evo Git" when the project has the same name
        self._app_name.hide()

class MainWindow(QMainWindow):
    PAGE_REPOS = "repos"
    PAGE_COMMITS = "commits"
    logout_requested = pyqtSignal()

    def __init__(self, github_auth, parent=None):
        super().__init__(parent)
        self._auth = github_auth
        self.setWindowTitle("Evo Git")
        self.setMinimumSize(1100, 680)
        self.setStyleSheet(make_global_style())

        self._central = QWidget()
        self._central.setObjectName("root")
        self._central.setStyleSheet(f"#root {{ background: {COLORS['bg_primary']}; }}")
        self.setCentralWidget(self._central)

        layout = QVBoxLayout(self._central)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self.topnav = TopNav()
        self.topnav.back_clicked.connect(self._on_back)
        self.topnav.logout_clicked.connect(self._on_logout)
        layout.addWidget(self.topnav)

        self._stack = QStackedWidget()
        self._stack.setStyleSheet(f"background: {COLORS['bg_primary']};")
        layout.addWidget(self._stack)

        self._pages: dict[str, QWidget] = {}
        self._current_repo_name = ""

    def add_page(self, key: str, widget: QWidget):
        self._stack.addWidget(widget)
        self._pages[key] = widget

    def show_page(self, key: str, repo_name: str = ""):
        widget = self._pages.get(key)
        if widget:
            self._stack.setCurrentWidget(widget)

        if key == self.PAGE_REPOS:
            self.topnav.show_repos_state()
        elif key == self.PAGE_COMMITS:
            self.topnav.show_commits_state(repo_name or self._current_repo_name)

    def set_user(self, user: dict):
        self.topnav.set_user(user)

    def set_repo_name(self, name: str):
        self._current_repo_name = name

    def _on_back(self):
        self.show_page(self.PAGE_REPOS)

    def _on_logout(self):
        self._auth.logout()
        self.logout_requested.emit()

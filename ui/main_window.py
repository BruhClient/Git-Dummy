import os
import threading

from PyQt5.QtCore import Qt, pyqtSignal, QObject, pyqtSlot, QPoint
from PyQt5.QtGui import QFont, QPainter, QColor, QBrush, QPen, QPixmap, QPainterPath
from PyQt5.QtWidgets import (
    QMainWindow, QWidget, QHBoxLayout, QVBoxLayout, QLabel,
    QPushButton, QStackedWidget, QFrame, QApplication,
)
from styles.theme import COLORS, make_global_style
from ui.components.toast import _Toast


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

        clip = QPainterPath()
        clip.addEllipse(0, 0, s, s)
        p.setClipPath(clip)

        if self._pixmap:
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
            font = QFont("Tilt Warp", s // 3, QFont.Bold)
            p.setFont(font)
            p.drawText(self.rect(), Qt.AlignCenter, self._initials)

        p.setClipping(False)
        p.setPen(QPen(QColor(COLORS["accent"]), 2))
        p.setBrush(Qt.NoBrush)
        p.drawEllipse(1, 1, s - 2, s - 2)
        p.end()


class _AccountDropdown(QFrame):
    """Floating popup listing all saved accounts plus Add / Sign out actions."""

    account_clicked = pyqtSignal(str)   # login
    add_clicked = pyqtSignal()
    signout_clicked = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent, Qt.Popup | Qt.FramelessWindowHint)
        self.setObjectName("accountDropdown")
        self.setStyleSheet(f"""
            #accountDropdown {{
                background: {COLORS['bg_secondary']};
                border: 1px solid {COLORS['border']};
                border-radius: 8px;
            }}
        """)
        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(6, 6, 6, 6)
        self._layout.setSpacing(2)
        self._accounts: list[dict] = []
        self._active_login = ""

    def populate(self, accounts: list[dict], active_login: str):
        self._accounts = accounts
        self._active_login = active_login

        # Clear existing rows
        while self._layout.count():
            item = self._layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        for acc in accounts:
            login = acc.get("login", "")
            name = acc.get("name") or login
            avatar_url = acc.get("avatar_url", "")
            is_active = (login == active_login)
            row = self._make_account_row(login, name, avatar_url, is_active)
            self._layout.addWidget(row)

        sep1 = self._make_separator()
        self._layout.addWidget(sep1)

        add_btn = self._make_action_row("+ Add account", COLORS["accent"])
        add_btn.clicked.connect(self.add_clicked.emit)
        self._layout.addWidget(add_btn)

        sep2 = self._make_separator()
        self._layout.addWidget(sep2)

        signout_btn = self._make_action_row("Sign out", COLORS["text_muted"])
        signout_btn.clicked.connect(self.signout_clicked.emit)
        self._layout.addWidget(signout_btn)

        self.adjustSize()

    def _make_account_row(self, login: str, name: str, avatar_url: str, active: bool) -> QWidget:
        row = QPushButton()
        row.setFlat(True)
        row.setCursor(Qt.PointingHandCursor)
        row.setFixedHeight(44)
        row.setMinimumWidth(220)
        row.setStyleSheet(f"""
            QPushButton {{
                background: {'rgba(255,255,255,0.05)' if active else 'transparent'};
                border: none;
                border-radius: 6px;
                text-align: left;
                padding: 0 8px;
            }}
            QPushButton:hover {{
                background: {COLORS['bg_hover']};
            }}
        """)

        h = QHBoxLayout(row)
        h.setContentsMargins(8, 0, 8, 0)
        h.setSpacing(10)

        avatar = _AvatarCircle(28)
        display = name[:2].upper() if name else "EG"
        avatar.set_initials(display)
        if avatar_url:
            threading.Thread(
                target=_download_avatar_async, args=(avatar_url, avatar), daemon=True
            ).start()
        h.addWidget(avatar)

        text_col = QVBoxLayout()
        text_col.setSpacing(0)

        name_lbl = QLabel(name)
        name_lbl.setStyleSheet(
            f"font-size: 13px; font-weight: 600; font-family: 'Tilt Warp'; color: {COLORS['text_primary']}; background: transparent;"
        )
        text_col.addWidget(name_lbl)

        login_lbl = QLabel(f"@{login}")
        login_lbl.setStyleSheet(
            f"font-size: 11px; color: {COLORS['text_muted']}; background: transparent;"
        )
        text_col.addWidget(login_lbl)
        h.addLayout(text_col)
        h.addStretch()

        if active:
            check = QLabel("✓")
            check.setStyleSheet(f"font-size: 13px; color: {COLORS['accent']}; background: transparent;")
            h.addWidget(check)

        row.clicked.connect(lambda _=False, l=login: self.account_clicked.emit(l))
        return row

    def _make_separator(self) -> QFrame:
        sep = QFrame()
        sep.setFrameShape(QFrame.HLine)
        sep.setFixedHeight(1)
        sep.setStyleSheet(f"background: {COLORS['border']}; border: none;")
        return sep

    def _make_action_row(self, label: str, color: str) -> QPushButton:
        btn = QPushButton(label)
        btn.setFlat(True)
        btn.setCursor(Qt.PointingHandCursor)
        btn.setFixedHeight(34)
        btn.setStyleSheet(f"""
            QPushButton {{
                background: transparent;
                border: none;
                border-radius: 6px;
                text-align: left;
                padding: 0 12px;
                font-size: 13px;
                color: {color};
            }}
            QPushButton:hover {{
                background: {COLORS['bg_hover']};
            }}
        """)
        return btn


def _download_avatar_async(url: str, widget: _AvatarCircle):
    try:
        import requests as _requests
        resp = _requests.get(url, timeout=10)
        if resp.status_code == 200:
            pm = QPixmap()
            pm.loadFromData(resp.content)
            if not pm.isNull():
                widget.set_pixmap(pm)
    except Exception:
        pass


class TopNav(QWidget):
    """Slim top navigation bar — no sidebar."""

    back_clicked = pyqtSignal()
    logout_clicked = pyqtSignal()
    switch_account_requested = pyqtSignal(str)   # login
    add_account_requested = pyqtSignal()

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
            f"font-size: 14px; font-weight: 700; font-family: 'Tilt Warp'; color: {COLORS['text_primary']};"
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
            f"font-size: 13px; font-weight: 600; font-family: 'Tilt Warp'; color: {COLORS['text_primary']};"
        )
        self._page_label.hide()
        layout.addWidget(self._page_label)

        layout.addStretch()

        # Right: clickable account area (avatar + username + chevron) opens dropdown
        self._account_btn = QPushButton()
        self._account_btn.setFlat(True)
        self._account_btn.setCursor(Qt.PointingHandCursor)
        self._account_btn.setFixedHeight(36)
        self._account_btn.setStyleSheet(f"""
            QPushButton {{
                background: transparent;
                border: 1px solid transparent;
                border-radius: 18px;
                padding: 0 8px;
            }}
            QPushButton:hover {{
                border-color: {COLORS['border']};
                background: {COLORS['bg_hover']};
            }}
        """)
        self._account_btn.clicked.connect(self._toggle_dropdown)

        acc_h = QHBoxLayout(self._account_btn)
        acc_h.setContentsMargins(4, 0, 8, 0)
        acc_h.setSpacing(8)

        self._avatar = _AvatarCircle(28)
        acc_h.addWidget(self._avatar)



        layout.addWidget(self._account_btn)

        self._dropdown: _AccountDropdown | None = None
        self._accounts: list[dict] = []
        self._active_login = ""

    def set_user(self, user: dict):
        name = user.get("name") or user.get("login", "")
        self._avatar.set_initials(name[:2].upper() if name else "EG")

        avatar_url = user.get("avatar_url", "")
        if avatar_url:
            threading.Thread(
                target=_download_avatar_async,
                args=(avatar_url, self._avatar),
                daemon=True,
            ).start()

    def set_accounts(self, accounts: list[dict], active_login: str):
        self._accounts = accounts
        self._active_login = active_login
        if self._dropdown and self._dropdown.isVisible():
            self._dropdown.populate(accounts, active_login)

    def _toggle_dropdown(self):
        if self._dropdown and self._dropdown.isVisible():
            self._dropdown.hide()
            return

        # Find the top-level window to parent the popup
        top = self.window()
        if not self._dropdown:
            self._dropdown = _AccountDropdown(top)
            self._dropdown.account_clicked.connect(self._on_account_clicked)
            self._dropdown.add_clicked.connect(self.add_account_requested.emit)
            self._dropdown.signout_clicked.connect(self._on_signout)

        self._dropdown.populate(self._accounts, self._active_login)

        # Position below the account button (global coords — it's a Qt.Popup window)
        btn_br = self._account_btn.mapToGlobal(
            QPoint(self._account_btn.width(), self._account_btn.height() + 4)
        )
        self._dropdown.move(btn_br.x() - self._dropdown.width(), btn_br.y())
        self._dropdown.show()
        self._dropdown.raise_()

    def _on_account_clicked(self, login: str):
        if self._dropdown:
            self._dropdown.hide()
        if login != self._active_login:
            self.switch_account_requested.emit(login)

    def _on_signout(self):
        if self._dropdown:
            self._dropdown.hide()
        self.logout_clicked.emit()

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
        self._app_name.hide()


class MainWindow(QMainWindow):
    PAGE_REPOS = "repos"
    PAGE_COMMITS = "commits"
    logout_requested = pyqtSignal()
    switch_account_requested = pyqtSignal(str)
    add_account_requested = pyqtSignal()

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
        self.topnav.switch_account_requested.connect(self.switch_account_requested.emit)
        self.topnav.add_account_requested.connect(self.add_account_requested.emit)
        layout.addWidget(self.topnav)

        self._stack = QStackedWidget()
        self._stack.setStyleSheet(f"background: {COLORS['bg_primary']};")
        layout.addWidget(self._stack)

        self._pages: dict[str, QWidget] = {}
        self._current_repo_name = ""
        self._toast = _Toast(self._central)

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

    def set_accounts(self, accounts: list[dict], active_login: str):
        self.topnav.set_accounts(accounts, active_login)

    def show_toast(self, msg: str, kind: str = "info", duration_ms: int = 6000):
        self._toast.show_message(msg, kind=kind, duration_ms=duration_ms)

    def set_repo_name(self, name: str):
        self._current_repo_name = name

    def _on_back(self):
        self.show_page(self.PAGE_REPOS)

    def _on_logout(self):
        self._auth.logout()
        self.logout_requested.emit()

import os
import threading
from datetime import datetime

import qtawesome as qta

from PyQt5.QtCore import Qt, pyqtSignal, QPoint
from PyQt5.QtGui import QFont, QPainter, QColor, QBrush, QPen, QPixmap, QPainterPath
from PyQt5.QtWidgets import (
    QMainWindow, QWidget, QHBoxLayout, QVBoxLayout, QLabel,
    QPushButton, QStackedWidget, QFrame,
)
from styles.theme import COLORS, make_global_style


def _LogoMark(parent=None):
    lbl = QLabel(parent)
    sz = 42
    lbl.setFixedSize(sz, sz)
    from utils import resource_path
    _logo_path = resource_path(os.path.join("logo", "logo.png"))
    src = QPixmap(_logo_path).scaled(sz, sz, Qt.KeepAspectRatio, Qt.SmoothTransformation)
    lbl.setPixmap(src)
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
            font = QFont("Urbanist", s // 3, QFont.Bold)
            p.setFont(font)
            p.drawText(self.rect(), Qt.AlignCenter, self._initials)

        p.setClipping(False)
        p.setPen(QPen(QColor(COLORS["accent"]), 2))
        p.setBrush(Qt.NoBrush)
        p.drawEllipse(1, 1, s - 2, s - 2)
        p.end()


class _AccountPopup(QFrame):
    """Floating popup showing saved accounts with switch / add / sign-out."""

    signout_clicked = pyqtSignal()
    switch_account = pyqtSignal(str)
    add_account_clicked = pyqtSignal()

    def __init__(self, auth, parent=None):
        super().__init__(parent, Qt.Popup | Qt.FramelessWindowHint)
        self._auth = auth
        self.setObjectName("accountPopup")
        self.setFixedWidth(240)
        self.setStyleSheet(f"""
            #accountPopup {{
                background: {COLORS['bg_secondary']};
                border: 1px solid {COLORS['border']};
                border-radius: 8px;
            }}
        """)
        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(6, 6, 6, 6)
        self._layout.setSpacing(2)

        self._accounts_container = QWidget()
        self._accounts_layout = QVBoxLayout(self._accounts_container)
        self._accounts_layout.setContentsMargins(0, 0, 0, 0)
        self._accounts_layout.setSpacing(2)
        self._layout.addWidget(self._accounts_container)

        self._layout.addWidget(self._make_separator())

        add_btn = self._make_action_row("Add another account", COLORS["accent"])
        add_btn.clicked.connect(self.add_account_clicked.emit)
        self._layout.addWidget(add_btn)

        signout_btn = self._make_action_row("Sign out", COLORS["text_muted"])
        signout_btn.clicked.connect(self.signout_clicked.emit)
        self._layout.addWidget(signout_btn)

    def set_user(self, user: dict):
        self._rebuild_accounts()

    def _rebuild_accounts(self):
        while self._accounts_layout.count():
            item = self._accounts_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        accounts = self._auth.get_accounts()
        for acc in accounts:
            row = self._make_account_row(acc)
            self._accounts_layout.addWidget(row)
        self.adjustSize()

    def _make_account_row(self, acc: dict) -> QWidget:
        login = acc.get("login", "")
        name = acc.get("name", login)
        is_active = acc.get("is_active", False)
        token_expires = acc.get("token_expires", "")

        # Parse expiry
        expiry_text, expiry_color = self._format_token_expiry(token_expires)

        row = QPushButton()
        row.setFlat(True)
        row.setCursor(Qt.PointingHandCursor)
        row.setFixedHeight(58)
        row.setStyleSheet(f"""
            QPushButton {{
                background: {"" + COLORS['bg_hover'] if is_active else "transparent"};
                border: none; border-radius: 6px;
                text-align: left; padding: 0 10px;
            }}
            QPushButton:hover {{ background: {COLORS['bg_hover']}; }}
        """)

        h = QHBoxLayout(row)
        h.setContentsMargins(0, 0, 0, 0)
        h.setSpacing(8)

        avatar = _AvatarCircle(26)
        avatar.set_initials(name[:2].upper() if name else "EG")
        avatar_url = acc.get("avatar_url", "")
        if avatar_url:
            threading.Thread(
                target=_download_avatar_async, args=(avatar_url, avatar), daemon=True
            ).start()
        h.addWidget(avatar)

        text_col = QVBoxLayout()
        text_col.setSpacing(1)
        name_lbl = QLabel(name)
        name_lbl.setStyleSheet(
            f"font-size: 12px; font-weight: 600; color: {COLORS['text_primary']}; background: transparent;"
        )
        text_col.addWidget(name_lbl)
        login_lbl = QLabel(f"@{login}")
        login_lbl.setStyleSheet(
            f"font-size: 10px; color: {COLORS['text_muted']}; background: transparent;"
        )
        text_col.addWidget(login_lbl)
        token_lbl = QLabel(expiry_text)
        token_lbl.setStyleSheet(
            f"font-size: 9px; color: {expiry_color}; background: transparent;"
        )
        text_col.addWidget(token_lbl)
        h.addLayout(text_col)
        h.addStretch()

        if is_active:
            import qtawesome as qta
            check = QLabel()
            check.setPixmap(qta.icon("fa5s.check", color=COLORS["accent"]).pixmap(12, 12))
            check.setStyleSheet("background: transparent;")
            h.addWidget(check)

        if not is_active:
            row.clicked.connect(lambda _=False, l=login: self._on_switch(l))

        return row

    @staticmethod
    def _format_token_expiry(token_expires: str) -> tuple[str, str]:
        if not token_expires:
            return "Token · No expiration", COLORS["text_muted"]
        try:
            exp = datetime.strptime(token_expires, "%Y-%m-%d %H:%M:%S %Z")
            now = datetime.utcnow()
            if exp < now:
                return "Token · Expired", COLORS.get("danger", "#ef4444")
            days = (exp - now).days
            if days <= 7:
                return f"Token · Expires in {days}d", COLORS.get("warning", "#f59e0b")
            if days <= 30:
                return f"Token · Expires in {days}d", COLORS.get("warning", "#f59e0b")
            return f"Token · Expires {exp.strftime('%b %d, %Y')}", COLORS["text_muted"]
        except (ValueError, TypeError):
            return "Token · Active", COLORS["text_muted"]

    def _on_switch(self, login: str):
        self.hide()
        self.switch_account.emit(login)

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
    add_account_clicked = pyqtSignal()
    switch_account = pyqtSignal(str)

    def __init__(self, auth=None, parent=None):
        super().__init__(parent)
        self._auth = auth
        self.setObjectName("topNav")
        self.setFixedHeight(52)
        self.setStyleSheet(f"""
            #topNav {{
                background-color: {COLORS['bg_primary']};
                border-bottom: 1px solid {COLORS['border']};
            }}
        """)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(24, 8, 24, 0)
        layout.setSpacing(12)

        # Left: logo only
        logo = _LogoMark()
        layout.addWidget(logo, 0, Qt.AlignVCenter)

        # Back button (hidden on repos page)
        self._back_btn = QPushButton("Projects")
        self._back_btn.setIcon(qta.icon("fa5s.arrow-left", color=COLORS['text_muted']))
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

        # Right: clickable account area (avatar) opens the account popup
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
        self._account_btn.clicked.connect(self._toggle_popup)

        acc_h = QHBoxLayout(self._account_btn)
        acc_h.setContentsMargins(4, 0, 8, 0)
        acc_h.setSpacing(8)

        self._avatar = _AvatarCircle(28)
        acc_h.addWidget(self._avatar)



        layout.addWidget(self._account_btn)

        self._popup: _AccountPopup | None = None
        self._user: dict = {}

    def set_user(self, user: dict):
        self._user = user
        name = user.get("name") or user.get("login", "")
        self._avatar.set_initials(name[:2].upper() if name else "EG")

        avatar_url = user.get("avatar_url", "")
        if avatar_url:
            threading.Thread(
                target=_download_avatar_async,
                args=(avatar_url, self._avatar),
                daemon=True,
            ).start()

        if self._popup:
            self._popup.set_user(user)

    def _toggle_popup(self):
        if self._popup and self._popup.isVisible():
            self._popup.hide()
            return

        # Find the top-level window to parent the popup
        top = self.window()
        if not self._popup:
            self._popup = _AccountPopup(self._auth, top)
            self._popup.signout_clicked.connect(self._on_signout)
            self._popup.switch_account.connect(self.switch_account.emit)
            self._popup.add_account_clicked.connect(self._on_add_account)

        self._popup.set_user(self._user)

        # Position below the account button (global coords — it's a Qt.Popup window)
        btn_br = self._account_btn.mapToGlobal(
            QPoint(self._account_btn.width(), self._account_btn.height() + 4)
        )
        self._popup.move(btn_br.x() - self._popup.width(), btn_br.y())
        self._popup.show()
        self._popup.raise_()

    def _on_signout(self):
        if self._popup:
            self._popup.hide()
        self.logout_clicked.emit()

    def _on_add_account(self):
        if self._popup:
            self._popup.hide()
        self.add_account_clicked.emit()

    def show_repos_state(self):
        self._back_btn.hide()
        self._sep.hide()
        self._page_label.hide()

    def show_commits_state(self, repo_name: str = ""):
        self._back_btn.show()
        self._sep.show()
        self._page_label.setText(repo_name)
        self._page_label.show()


class MainWindow(QMainWindow):
    PAGE_REPOS = "repos"
    PAGE_COMMITS = "commits"
    logout_requested = pyqtSignal()
    add_account_requested = pyqtSignal()
    switch_account_requested = pyqtSignal(str)

    def __init__(self, github_auth, parent=None):
        super().__init__(parent)
        self._auth = github_auth
        self.setWindowTitle("Git Dummy")
        self.setMinimumSize(1100, 680)
        self.setStyleSheet(make_global_style())

        self._central = QWidget()
        self._central.setObjectName("root")
        self._central.setStyleSheet(f"#root {{ background: {COLORS['bg_primary']}; }}")
        self.setCentralWidget(self._central)

        layout = QVBoxLayout(self._central)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self.topnav = TopNav(auth=github_auth)
        self.topnav.back_clicked.connect(self._on_back)
        self.topnav.logout_clicked.connect(self._on_logout)
        self.topnav.add_account_clicked.connect(self.add_account_requested.emit)
        self.topnav.switch_account.connect(self.switch_account_requested.emit)
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
        cp = self._pages.get(self.PAGE_COMMITS)
        if cp and hasattr(cp, "_stop_all_threads"):
            cp._stop_all_threads()
        self.show_page(self.PAGE_REPOS)

    def _on_logout(self):
        self._auth.logout()
        self.logout_requested.emit()

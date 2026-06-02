import sys
import os

sys.path.insert(0, os.path.dirname(__file__))

# Qt converts QT_QPA_PLATFORM_PLUGIN_PATH through the Windows ANSI codepage,
# which can't encode emoji. Use GetShortPathNameW to get an ASCII-safe 8.3
# path before handing it to Qt.
def _qt_plugins_path() -> str:
    try:
        import PyQt5 as _p
        path = os.path.join(os.path.dirname(_p.__file__), "Qt5", "plugins")
        if not os.path.isdir(path):
            path = os.path.join(os.path.dirname(_p.__file__), "Qt", "plugins")
        if sys.platform == "win32":
            import ctypes
            buf = ctypes.create_unicode_buffer(512)
            ctypes.windll.kernel32.GetShortPathNameW(path, buf, 512)
            if buf.value:
                return buf.value
        return path
    except Exception:
        return ""

_p = _qt_plugins_path()
if _p:
    os.environ["QT_QPA_PLATFORM_PLUGIN_PATH"] = _p

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QApplication, QStackedWidget

from auth.github_auth import GitHubAuth
from ui.auth_page import AuthPage
from ui.main_window import MainWindow
from ui.repo_page import RepoPage
from ui.commit_view import CommitViewPage
from styles.theme import make_global_style


class App(QStackedWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Evo Git")
        self.setMinimumSize(1100, 700)

        self._auth = GitHubAuth(self)

        from PyQt5.QtGui import QFontDatabase
        _fonts_dir = os.path.join(os.path.dirname(__file__), "fonts")
        for _fname in (
            "TiltWarp-Regular.ttf",
            "Urbanist-Regular.ttf",
            "Urbanist-Medium.ttf",
            "Urbanist-SemiBold.ttf",
            "Urbanist-Bold.ttf",
        ):
            QFontDatabase.addApplicationFont(os.path.join(_fonts_dir, _fname))

        self.setStyleSheet(make_global_style())

        self._auth_page = AuthPage(self._auth)
        self._main_window = MainWindow(self._auth)

        self._repo_page = RepoPage()
        self._commit_page = CommitViewPage()

        self._main_window.add_page(MainWindow.PAGE_REPOS, self._repo_page)
        self._main_window.add_page(MainWindow.PAGE_COMMITS, self._commit_page)

        self.addWidget(self._auth_page)
        self.addWidget(self._main_window)

        self._auth.auth_success.connect(self._on_auth_success)
        self._auth.auth_failed.connect(self._on_auth_failed)
        self._auth.account_added.connect(self._on_account_added)
        self._auth.add_account_failed.connect(self._on_add_account_failed)
        self._auth.add_account_needs_signout.connect(self._on_add_account_needs_signout)
        self._repo_page.repo_selected.connect(self._on_repo_selected)
        self._commit_page.access_denied.connect(self._on_access_denied)
        self._main_window.logout_requested.connect(self._on_logout)
        self._main_window.switch_account_requested.connect(self._auth.switch_account)
        self._main_window.add_account_requested.connect(self._on_add_account_requested)
        self._auth_page.account_selected.connect(self._auth.switch_account)
        self._auth_page.add_account_clicked.connect(self._auth.start_oauth_flow)

        if self._auth.has_saved_token():
            self._auth_page.show_account_picker(self._auth.get_all_accounts())
        else:
            self._auth_page.show_sign_in()
        self.setCurrentWidget(self._auth_page)

    def _on_auth_success(self, user: dict):
        self._main_window.set_user(user)
        self._repo_page.set_user(user)
        self._commit_page.set_user(user)
        self._main_window.set_accounts(self._auth.get_all_accounts(), user.get("login", ""))
        self._main_window.show_page(MainWindow.PAGE_REPOS)
        self.setCurrentWidget(self._main_window)

    def _on_account_added(self, user: dict):
        """New account added while already logged in — switch to it."""
        self._on_auth_success(user)

    def _on_add_account_requested(self):
        import webbrowser
        from PyQt5.QtWidgets import QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton
        from styles.theme import COLORS

        dlg = QDialog(self._main_window)
        dlg.setWindowTitle("Add GitHub Account")
        dlg.setFixedWidth(420)
        dlg.setStyleSheet(f"""
            QDialog {{ background: {COLORS['bg_secondary']}; }}
            QLabel  {{ background: transparent; color: {COLORS['text_primary']}; }}
        """)

        layout = QVBoxLayout(dlg)
        layout.setContentsMargins(24, 24, 24, 20)
        layout.setSpacing(12)

        heading = QLabel("Sign out of GitHub first")
        heading.setStyleSheet(f"font-size: 15px; font-weight: 700; font-family: 'Tilt Warp'; color: {COLORS['text_primary']};")
        layout.addWidget(heading)

        body = QLabel(
            "GitHub will return your <b>current active account</b> unless you sign out first.\n\n"
            "Sign out of GitHub in your browser, then click <b>I've signed out</b> to authorize a new account."
        )
        body.setWordWrap(True)
        body.setStyleSheet(f"font-size: 13px; color: {COLORS['text_secondary']};")
        layout.addWidget(body)

        logout_btn = QPushButton("Open GitHub logout")
        logout_btn.setCursor(Qt.PointingHandCursor)
        logout_btn.setStyleSheet(f"""
            QPushButton {{
                background: transparent;
                border: 1px solid {COLORS['border']};
                border-radius: 6px;
                color: {COLORS['text_primary']};
                font-size: 13px;
                padding: 8px 14px;
                text-align: left;
            }}
            QPushButton:hover {{
                border-color: {COLORS['accent']};
                color: {COLORS['accent']};
            }}
        """)
        logout_btn.clicked.connect(lambda: webbrowser.open("https://github.com/logout"))
        layout.addWidget(logout_btn)

        layout.addSpacing(4)

        btn_row = QHBoxLayout()
        btn_row.setSpacing(8)
        btn_row.addStretch()

        cancel_btn = QPushButton("Cancel")
        cancel_btn.setCursor(Qt.PointingHandCursor)
        cancel_btn.setStyleSheet(f"""
            QPushButton {{
                background: transparent;
                border: 1px solid {COLORS['border']};
                border-radius: 6px;
                color: {COLORS['text_muted']};
                font-size: 13px;
                padding: 7px 16px;
            }}
            QPushButton:hover {{
                border-color: {COLORS['text_muted']};
                color: {COLORS['text_primary']};
            }}
        """)
        cancel_btn.clicked.connect(dlg.reject)
        btn_row.addWidget(cancel_btn)

        ready_btn = QPushButton("I've signed out →")
        ready_btn.setCursor(Qt.PointingHandCursor)
        ready_btn.setStyleSheet(f"""
            QPushButton {{
                background: {COLORS['accent']};
                border: none;
                border-radius: 6px;
                color: #fff;
                font-size: 13px;
                font-weight: 600; font-family: 'Tilt Warp';
                padding: 7px 16px;
            }}
            QPushButton:hover {{
                background: {COLORS['accent_hover']};
            }}
        """)
        ready_btn.clicked.connect(dlg.accept)
        btn_row.addWidget(ready_btn)

        layout.addLayout(btn_row)

        if dlg.exec_() == QDialog.Accepted:
            self._auth.start_add_account_flow()

    def _on_add_account_needs_signout(self, login: str):
        import webbrowser
        from PyQt5.QtWidgets import QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton
        from styles.theme import COLORS

        dlg = QDialog(self._main_window)
        dlg.setWindowTitle("Sign out of GitHub first")
        dlg.setFixedWidth(420)
        dlg.setStyleSheet(f"""
            QDialog {{ background: {COLORS['bg_secondary']}; }}
            QLabel  {{ background: transparent; color: {COLORS['text_primary']}; }}
        """)

        layout = QVBoxLayout(dlg)
        layout.setContentsMargins(24, 24, 24, 20)
        layout.setSpacing(12)

        heading = QLabel(f"Still signed in as @{login}")
        heading.setStyleSheet(f"font-size: 15px; font-weight: 700; font-family: 'Tilt Warp'; color: {COLORS['text_primary']};")
        layout.addWidget(heading)

        body = QLabel(
            f"GitHub returned <b>@{login}</b>, which is already in your accounts.\n\n"
            "Sign out of GitHub in your browser, then click <b>Try Again</b> to authorize a new account."
        )
        body.setWordWrap(True)
        body.setStyleSheet(f"font-size: 13px; color: {COLORS['text_secondary']};")
        layout.addWidget(body)

        logout_btn = QPushButton("Open GitHub logout")
        logout_btn.setCursor(Qt.PointingHandCursor)
        logout_btn.setStyleSheet(f"""
            QPushButton {{
                background: transparent;
                border: 1px solid {COLORS['border']};
                border-radius: 6px;
                color: {COLORS['text_primary']};
                font-size: 13px;
                padding: 8px 14px;
                text-align: left;
            }}
            QPushButton:hover {{
                border-color: {COLORS['accent']};
                color: {COLORS['accent']};
            }}
        """)
        logout_btn.clicked.connect(lambda: webbrowser.open("https://github.com/logout"))
        layout.addWidget(logout_btn)

        layout.addSpacing(4)

        btn_row = QHBoxLayout()
        btn_row.setSpacing(8)
        btn_row.addStretch()

        cancel_btn = QPushButton("Cancel")
        cancel_btn.setCursor(Qt.PointingHandCursor)
        cancel_btn.setStyleSheet(f"""
            QPushButton {{
                background: transparent;
                border: 1px solid {COLORS['border']};
                border-radius: 6px;
                color: {COLORS['text_muted']};
                font-size: 13px;
                padding: 7px 16px;
            }}
            QPushButton:hover {{
                border-color: {COLORS['text_muted']};
                color: {COLORS['text_primary']};
            }}
        """)
        cancel_btn.clicked.connect(dlg.reject)
        btn_row.addWidget(cancel_btn)

        try_again_btn = QPushButton("Try Again →")
        try_again_btn.setCursor(Qt.PointingHandCursor)
        try_again_btn.setStyleSheet(f"""
            QPushButton {{
                background: {COLORS['accent']};
                border: none;
                border-radius: 6px;
                color: #fff;
                font-size: 13px;
                font-weight: 600; font-family: 'Tilt Warp';
                padding: 7px 16px;
            }}
            QPushButton:hover {{
                background: {COLORS['accent_hover']};
            }}
        """)
        try_again_btn.clicked.connect(dlg.accept)
        btn_row.addWidget(try_again_btn)

        layout.addLayout(btn_row)

        if dlg.exec_() == QDialog.Accepted:
            self._auth.start_add_account_flow()

    def _on_add_account_failed(self, message: str):
        self._main_window.show_toast(message, kind="error")

    def _on_auth_failed(self, message: str):
        self.setCurrentWidget(self._auth_page)
        self._auth_page.show_error(message)

    def _on_logout(self):
        self._commit_page.reset()
        self._main_window.show_page(MainWindow.PAGE_REPOS)
        self._auth_page.reset()  # calls show_sign_in() — all accounts were cleared by logout
        self.setCurrentWidget(self._auth_page)

    def _on_repo_selected(self, repo_path: str):
        import os
        if not os.path.isdir(repo_path):
            self._repo_page._validate_paths()
            return
        repo_name = os.path.basename(repo_path)
        self._main_window.set_repo_name(repo_name)
        self._commit_page.load_repo(repo_path)
        self._main_window.show_page(MainWindow.PAGE_COMMITS, repo_name)

    def _on_access_denied(self, repo_path: str):
        self._main_window.show_page(MainWindow.PAGE_REPOS)
        if repo_path:
            self._repo_page.remove_repo(repo_path)


def main():
    QApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)
    QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps, True)

    app = QApplication(sys.argv)
    app.setApplicationName("Evo Git")
    app.setOrganizationName("EvoGit")

    window = App()
    window.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()

import sys
import os
import subprocess

sys.path.insert(0, os.path.dirname(__file__))

from utils import resource_path
from version import __version__

# Qt converts QT_QPA_PLATFORM_PLUGIN_PATH through the Windows ANSI codepage,
# which can't encode emoji. Use GetShortPathNameW to get an ASCII-safe 8.3
# path before handing it to Qt.
def _qt_plugins_path() -> str:
    if getattr(sys, 'frozen', False):
        return ""
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

from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtWidgets import QApplication, QStackedWidget, QMessageBox

from auth.github_auth import GitHubAuth
from ui.auth_page import AuthPage
from ui.main_window import MainWindow
from ui.repo_page import RepoPage
from ui.commit_view import CommitViewPage
from ui.welcome_splash import WelcomeSplash
from styles.theme import make_global_style


def _check_git_installed() -> bool:
    try:
        subprocess.run(
            ["git", "--version"],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
        )
        return True
    except FileNotFoundError:
        return False


class App(QStackedWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(f"Git Dummy v{__version__}")
        self.setMinimumSize(1100, 700)

        self._auth = GitHubAuth(self)

        from PyQt5.QtGui import QFontDatabase
        _fonts_dir = resource_path("fonts")
        for _fname in (
            "TiltWarp-Regular.ttf",
            "Urbanist-Regular.ttf",
            "Urbanist-Medium.ttf",
            "Urbanist-SemiBold.ttf",
            "Urbanist-Bold.ttf",
        ):
            QFontDatabase.addApplicationFont(os.path.join(_fonts_dir, _fname))

        self.setStyleSheet(make_global_style())

        self._splash = WelcomeSplash()

        self._auth_page = AuthPage(self._auth)
        self._main_window = MainWindow(self._auth)

        self._repo_page = RepoPage()
        self._commit_page = CommitViewPage()

        self._main_window.add_page(MainWindow.PAGE_REPOS, self._repo_page)
        self._main_window.add_page(MainWindow.PAGE_COMMITS, self._commit_page)

        self.addWidget(self._splash)
        self.addWidget(self._auth_page)
        self.addWidget(self._main_window)

        self._auth.auth_success.connect(self._on_auth_success)
        self._auth.auth_failed.connect(self._on_auth_failed)
        self._repo_page.repo_selected.connect(self._on_repo_selected)
        self._commit_page.access_denied.connect(self._on_access_denied)
        self._commit_page.repo_forked.connect(self._repo_page._refresh_cards)
        self._main_window.logout_requested.connect(self._on_logout)
        self._main_window.add_account_requested.connect(self._on_add_account)
        self._main_window.switch_account_requested.connect(self._on_switch_account)
        self._main_window.change_token_requested.connect(self._on_change_token)
        self._auth_page.account_selected.connect(self._on_switch_account)

        self._auth_page.show_sign_in()

        self._splash_active = True
        self._pending_page = None
        self._splash.finished.connect(self._on_splash_finished)
        self.setCurrentWidget(self._splash)
        QTimer.singleShot(0, self._splash.play)

        if self._auth.has_saved_token():
            # Restoring a saved session makes a network call (up to ~10s on a
            # slow connection). Show the sign-in screen first and defer the
            # check to the next event-loop tick, so the window appears right
            # away instead of staying blank while we verify the session. This
            # runs concurrently underneath the splash, not gated by it.
            self._auth_page.show_checking_session()
            QTimer.singleShot(0, self._auth.load_saved_token)

    def _on_splash_finished(self):
        self._splash_active = False
        self.setCurrentWidget(self._pending_page or self._auth_page)
        self._pending_page = None

    def _on_auth_success(self, user: dict):
        self._main_window.set_user(user)
        self._repo_page.set_user(user)
        self._commit_page.set_user(user)
        self._main_window.show_page(MainWindow.PAGE_REPOS)
        if self._splash_active:
            self._pending_page = self._main_window
            return
        self.setCurrentWidget(self._main_window)

    def _on_auth_failed(self, message: str):
        if self._splash_active:
            self._pending_page = self._auth_page
            self._auth_page.show_error(message)
            return
        self.setCurrentWidget(self._auth_page)
        self._auth_page.show_error(message)

    def _on_logout(self):
        self._commit_page.reset()
        self._main_window.show_page(MainWindow.PAGE_REPOS)
        self._auth_page.reset()
        self.setCurrentWidget(self._auth_page)

    def _on_add_account(self):
        from ui.dialogs.add_account_dialog import AddAccountDialog
        dlg = AddAccountDialog(self._auth, parent=self._main_window)
        dlg.account_selected.connect(self._on_switch_account)
        dlg.exec_()

    def _on_switch_account(self, login: str):
        self._auth.switch_account(login)

    def _on_change_token(self, login: str):
        from ui.dialogs.add_account_dialog import AddAccountDialog
        dlg = AddAccountDialog(self._auth, parent=self._main_window, change_token_login=login)
        dlg.exec_()

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
        self._commit_page._stop_all_threads()
        self._main_window.show_page(MainWindow.PAGE_REPOS)
        if repo_path:
            self._repo_page.remove_repo(repo_path)


def main():
    QApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)
    QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps, True)

    app = QApplication(sys.argv)
    app.setApplicationName("Git Dummy")
    app.setOrganizationName("GitDummy")

    from PyQt5.QtGui import QIcon
    ico_path = resource_path(os.path.join("logo", "logo.ico"))
    if os.path.isfile(ico_path):
        app.setWindowIcon(QIcon(ico_path))
    else:
        app.setWindowIcon(QIcon(resource_path(os.path.join("logo", "logo.png"))))

    if not _check_git_installed():
        QMessageBox.critical(
            None, "Git Not Found",
            "Git Dummy requires Git to be installed on your computer.\n\n"
            "Please install Git from https://git-scm.com and try again.",
        )
        sys.exit(1)

    window = App()
    window.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()

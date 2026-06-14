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
        self._repo_page.repo_selected.connect(self._on_repo_selected)
        self._commit_page.access_denied.connect(self._on_access_denied)
        self._main_window.logout_requested.connect(self._on_logout)

        self._auth_page.show_sign_in()
        self.setCurrentWidget(self._auth_page)
        if self._auth.has_saved_token():
            self._auth.load_saved_token()

    def _on_auth_success(self, user: dict):
        self._main_window.set_user(user)
        self._repo_page.set_user(user)
        self._commit_page.set_user(user)
        self._main_window.show_page(MainWindow.PAGE_REPOS)
        self.setCurrentWidget(self._main_window)

    def _on_auth_failed(self, message: str):
        self.setCurrentWidget(self._auth_page)
        self._auth_page.show_error(message)

    def _on_logout(self):
        self._commit_page.reset()
        self._main_window.show_page(MainWindow.PAGE_REPOS)
        self._auth_page.reset()  # calls show_sign_in() — saved session was cleared by logout
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

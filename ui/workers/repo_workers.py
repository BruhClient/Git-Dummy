"""Background QThread workers for repo fetching and cloning."""
from __future__ import annotations

from PyQt5.QtCore import QObject, pyqtSignal


class _FetchReposWorker(QObject):
    finished = pyqtSignal(list)   # list of repo dicts; [] on any failure

    def __init__(self, token: str):
        super().__init__()
        self._token = token

    def run(self):
        try:
            import requests
            r = requests.get(
                "https://api.github.com/user/repos",
                headers={"Authorization": f"Bearer {self._token}",
                         "Accept": "application/vnd.github+json"},
                params={"per_page": 100, "sort": "updated"},
                timeout=12,
            )
            self.finished.emit(r.json() if r.status_code == 200 else [])
        except Exception:
            self.finished.emit([])


# Public aliases used in dialogs
FetchReposWorker = _FetchReposWorker


class _CloneWorker(QObject):
    finished = pyqtSignal(bool, str, str)   # ok, error, cloned_path

    def __init__(self, url: str, dest: str):
        super().__init__()
        self._url  = url
        self._dest = dest

    def run(self):
        from core.ops import clone_repo
        ok, err, path = clone_repo(self._url, self._dest)
        self.finished.emit(ok, err, path)


# Public alias
CloneWorker = _CloneWorker

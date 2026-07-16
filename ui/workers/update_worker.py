"""Background QThread worker for checking GitHub Releases for a newer version."""
from __future__ import annotations

from PyQt5.QtCore import QObject, pyqtSignal

_RELEASES_URL = "https://api.github.com/repos/BruhClient/Git-Dummy/releases/latest"


def _parse_version(s: str) -> tuple[int, ...]:
    parts = []
    for p in s.strip().lstrip("v").split("."):
        try:
            parts.append(int(p))
        except ValueError:
            parts.append(0)
    return tuple(parts)


class _CheckUpdateWorker(QObject):
    finished = pyqtSignal(bool, str, str)   # update_available, latest_version, html_url

    def __init__(self, current_version: str):
        super().__init__()
        self._current_version = current_version

    def run(self):
        try:
            import requests
            resp = requests.get(
                _RELEASES_URL,
                headers={"Accept": "application/vnd.github+json"},
                timeout=8,
            )
            if resp.status_code != 200:
                self.finished.emit(False, "", "")
                return
            data = resp.json()
            tag = str(data.get("tag_name", "")).lstrip("v")
            url = data.get("html_url", "")
            if not tag:
                self.finished.emit(False, "", "")
                return
            update_available = _parse_version(tag) > _parse_version(self._current_version)
            self.finished.emit(update_available, tag, url)
        except requests.exceptions.RequestException:
            self.finished.emit(False, "", "")
        except Exception:
            self.finished.emit(False, "", "")


# Public alias
CheckUpdateWorker = _CheckUpdateWorker

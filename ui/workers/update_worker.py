"""Background QThread workers for checking GitHub Releases and installing updates."""
from __future__ import annotations

import os
import subprocess
import tempfile

from PyQt5.QtCore import QObject, pyqtSignal

from core.ops.base_ops import _POPEN_FLAGS

_RELEASES_URL = "https://api.github.com/repos/BruhClient/Git-Dummy/releases/latest"
_WINDOWS_ASSET_NAME = "GitDummy-windows.exe"


def _parse_version(s: str) -> tuple[int, ...]:
    parts = []
    for p in s.strip().lstrip("v").split("."):
        try:
            parts.append(int(p))
        except ValueError:
            parts.append(0)
    return tuple(parts)


class _CheckUpdateWorker(QObject):
    finished = pyqtSignal(bool, str, str, str)   # update_available, latest_version, html_url, download_url

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
                self.finished.emit(False, "", "", "")
                return
            data = resp.json()
            tag = str(data.get("tag_name", "")).lstrip("v")
            url = data.get("html_url", "")
            if not tag:
                self.finished.emit(False, "", "", "")
                return
            download_url = ""
            for asset in data.get("assets", []):
                if asset.get("name") == _WINDOWS_ASSET_NAME:
                    download_url = asset.get("browser_download_url", "")
                    break
            update_available = _parse_version(tag) > _parse_version(self._current_version)
            self.finished.emit(update_available, tag, url, download_url)
        except requests.exceptions.RequestException:
            self.finished.emit(False, "", "", "")
        except Exception:
            self.finished.emit(False, "", "", "")


class _DownloadInstallWorker(QObject):
    progress = pyqtSignal(int)          # 0-100
    finished = pyqtSignal(bool, str)    # ok, installer_path_or_error

    def __init__(self, download_url: str, version: str):
        super().__init__()
        self._url = download_url
        self._version = version

    def run(self):
        try:
            import requests
            resp = requests.get(self._url, stream=True, timeout=30)
            if resp.status_code != 200:
                self.finished.emit(False, f"HTTP {resp.status_code}")
                return
            total = int(resp.headers.get("Content-Length", 0))
            dest = os.path.join(tempfile.gettempdir(), f"GitDummy-Setup-v{self._version}.exe")
            downloaded = 0
            last_pct = -1
            with open(dest, "wb") as f:
                for chunk in resp.iter_content(chunk_size=262144):
                    if not chunk:
                        continue
                    f.write(chunk)
                    downloaded += len(chunk)
                    if total:
                        pct = int(downloaded * 100 / total)
                        if pct != last_pct:
                            last_pct = pct
                            self.progress.emit(pct)
            subprocess.Popen([dest, "/S"], creationflags=_POPEN_FLAGS)
            self.finished.emit(True, dest)
        except requests.exceptions.RequestException as e:
            self.finished.emit(False, str(e))
        except Exception as e:
            self.finished.emit(False, str(e))


# Public aliases
CheckUpdateWorker = _CheckUpdateWorker
DownloadInstallWorker = _DownloadInstallWorker

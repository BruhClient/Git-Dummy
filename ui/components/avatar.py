"""Avatar disk + memory cache helpers."""
from __future__ import annotations

import hashlib
import os

from PyQt5.QtGui import QPixmap

_AVATAR_CACHE: dict[str, QPixmap] = {}
_AVATAR_DIR = os.path.join(os.path.expanduser("~"), ".evogit_cache", "avatars")
os.makedirs(_AVATAR_DIR, exist_ok=True)


def _avatar_disk_path(url: str) -> str:
    return os.path.join(_AVATAR_DIR, hashlib.md5(url.encode()).hexdigest() + ".png")


def _load_avatar(url: str) -> "QPixmap | None":
    if url in _AVATAR_CACHE:
        return _AVATAR_CACHE[url]
    path = _avatar_disk_path(url)
    if os.path.exists(path):
        pm = QPixmap(path)
        if not pm.isNull():
            _AVATAR_CACHE[url] = pm
            return pm
    return None


def _save_avatar(url: str, pm: QPixmap):
    _AVATAR_CACHE[url] = pm
    try:
        pm.save(_avatar_disk_path(url), "PNG")
    except Exception:
        pass

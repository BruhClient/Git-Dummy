from __future__ import annotations

import json
import os
import time

_FILE = os.path.join(os.path.expanduser("~"), ".gitdummy_collab_cache.json")
_TTL  = 3600  # seconds before a cache entry is considered stale


def _load_store() -> dict:
    try:
        with open(_FILE, encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def get(remote_url: str) -> tuple[list | None, bool]:
    """Return (data, is_stale).  data is None on a full cache miss."""
    store = _load_store()
    entry = store.get(remote_url)
    if not entry:
        return None, True
    is_stale = (time.time() - entry.get("fetched_at", 0)) > _TTL
    return entry["data"], is_stale


def save(remote_url: str, data: list):
    store = _load_store()
    store[remote_url] = {"data": data, "fetched_at": time.time()}
    with open(_FILE, "w", encoding="utf-8") as f:
        json.dump(store, f)

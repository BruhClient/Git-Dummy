import json
import os
import tempfile

_FILE = os.path.join(os.path.expanduser("~"), ".evogit_settings.json")

_cache: dict | None = None


def load() -> dict:
    global _cache
    if _cache is not None:
        return _cache
    try:
        with open(_FILE) as f:
            _cache = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        _cache = {}
    return _cache


def save(data: dict):
    global _cache
    existing = load()
    existing.update(data)
    _dir = os.path.dirname(_FILE)
    fd, tmp = tempfile.mkstemp(dir=_dir, suffix=".tmp")
    try:
        with os.fdopen(fd, "w") as f:
            json.dump(existing, f, indent=2)
        os.replace(tmp, _FILE)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise
    _cache = existing


def get(key: str, default=None):
    return load().get(key, default)

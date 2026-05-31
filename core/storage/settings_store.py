import json
import os

_FILE = os.path.join(os.path.expanduser("~"), ".evogit_settings.json")


def load() -> dict:
    try:
        with open(_FILE) as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def save(data: dict):
    existing = load()
    existing.update(data)
    with open(_FILE, "w") as f:
        json.dump(existing, f, indent=2)


def get(key: str, default=None):
    return load().get(key, default)

import json
import os

_STORE = os.path.join(os.path.expanduser("~"), ".gitdummy_repos.json")


def load() -> list[str]:
    try:
        with open(_STORE) as f:
            data = json.load(f)
        return data if isinstance(data, list) else []
    except (FileNotFoundError, json.JSONDecodeError):
        return []


def save(paths: list[str]):
    with open(_STORE, "w") as f:
        json.dump(paths, f, indent=2)

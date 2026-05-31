import json
import os

_STORE = os.path.join(os.path.expanduser("~"), ".evogit_repos.json")


def load(login: str) -> list[str]:
    try:
        with open(_STORE) as f:
            data = json.load(f)
        if isinstance(data, dict):
            return data.get(login, [])
        # Legacy flat list — discard (can't attribute to an account)
        return []
    except (FileNotFoundError, json.JSONDecodeError):
        return []


def save(login: str, paths: list[str]):
    try:
        with open(_STORE) as f:
            data = json.load(f)
        if not isinstance(data, dict):
            data = {}
    except (FileNotFoundError, json.JSONDecodeError):
        data = {}
    data[login] = paths
    with open(_STORE, "w") as f:
        json.dump(data, f, indent=2)

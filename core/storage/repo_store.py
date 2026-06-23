import json
import os
import tempfile

_STORE = os.path.join(os.path.expanduser("~"), ".evogit_repos.json")


def load(login: str) -> list[str]:
    try:
        with open(_STORE) as f:
            data = json.load(f)
        if isinstance(data, dict):
            return data.get(login, [])
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
    _dir = os.path.dirname(_STORE)
    fd, tmp = tempfile.mkstemp(dir=_dir, suffix=".tmp")
    try:
        with os.fdopen(fd, "w") as f:
            json.dump(data, f, indent=2)
        os.replace(tmp, _STORE)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise

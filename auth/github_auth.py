from __future__ import annotations

import json
import os
import threading
from pathlib import Path

import requests
from PyQt5.QtCore import QObject, pyqtSignal

ACCOUNTS_FILE = os.path.join(os.path.expanduser("~"), ".evogit_accounts.json")
_LEGACY_TOKEN_FILE = os.path.join(os.path.expanduser("~"), ".evogit_token.json")

REQUIRED_SCOPES = {"repo", "read:user"}

PAT_CREATE_URL = (
    "https://github.com/settings/tokens/new"
    "?scopes=repo,read:user"
    "&description=Evo%20Git"
)


class GitHubAuth(QObject):
    """
    Manages GitHub authentication via Personal Access Tokens.

    Signals:
        auth_success(dict)   — emitted with user profile on login / session restore
        auth_failed(str)     — emitted with error message on failure
        token_expired(str)   — emitted with login when a saved token is no longer valid
    """

    auth_success = pyqtSignal(dict)
    auth_failed = pyqtSignal(str)
    token_expired = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._user: dict | None = None
        self._migrate_legacy()

    # ── public ───────────────────────────────────────────────────────────────

    def has_saved_token(self) -> bool:
        data = self._load_accounts_file()
        return bool(data.get("accounts")) and bool(data.get("active"))

    def load_saved_token(self):
        """Try to restore the active saved session; emits auth_success or auth_failed."""
        data = self._load_accounts_file()
        accounts = data.get("accounts", {})
        active = data.get("active", "")
        if not accounts:
            self.auth_failed.emit("No saved accounts.")
            return
        if active not in accounts:
            active = next(iter(accounts))
        account = accounts[active]
        token = account.get("access_token", "")
        user, scopes = self._validate_token(token)
        if user:
            user["access_token"] = token
            self._user = user
            self._save_account(user, token)
            self.auth_success.emit(user)
        else:
            self.auth_failed.emit("Saved token expired or invalid. Please sign in again.")

    def add_account(self, token: str):
        """Validate a PAT and add it as an account. Runs validation on a background thread."""
        token = token.strip()
        if not token:
            self.auth_failed.emit("Token cannot be empty.")
            return

        def _validate():
            user, scopes = self._validate_token(token)
            if not user:
                self.auth_failed.emit(
                    "Invalid token — check that you copied the full token, "
                    "or the token may have expired."
                )
                return
            missing = REQUIRED_SCOPES - scopes
            if missing:
                names = ", ".join(sorted(missing))
                self.auth_failed.emit(
                    f"Your token is missing required permissions: {names}.\n"
                    f"Create a new token with repo and read:user scopes."
                )
                return
            user["access_token"] = token
            self._save_account(user, token)
            self._user = user
            self.auth_success.emit(user)

        threading.Thread(target=_validate, daemon=True).start()

    def switch_account(self, login: str):
        """Switch to a different saved account."""
        data = self._load_accounts_file()
        accounts = data.get("accounts", {})
        if login not in accounts:
            self.auth_failed.emit(f"Account '{login}' not found.")
            return
        data["active"] = login
        self._write_accounts_file(data)
        account = accounts[login]
        token = account.get("access_token", "")
        user, _ = self._validate_token(token)
        if user:
            user["access_token"] = token
            self._user = user
            self._save_account(user, token)
            self.auth_success.emit(user)
        else:
            self.remove_account(login)
            self.token_expired.emit(login)
            self.auth_failed.emit(f"Token for '{login}' has expired. Please sign in again.")

    def get_accounts(self) -> list[dict]:
        """Return list of saved accounts (without tokens)."""
        data = self._load_accounts_file()
        accounts = data.get("accounts", {})
        active = data.get("active", "")
        result = []
        for login, info in accounts.items():
            result.append({
                "login": info.get("login", login),
                "name": info.get("name", login),
                "avatar_url": info.get("avatar_url", ""),
                "is_active": login == active,
            })
        return result

    def remove_account(self, login: str):
        """Remove a specific account from storage."""
        data = self._load_accounts_file()
        accounts = data.get("accounts", {})
        accounts.pop(login, None)
        if data.get("active") == login:
            data["active"] = next(iter(accounts), "")
        data["accounts"] = accounts
        if accounts:
            self._write_accounts_file(data)
        elif os.path.exists(ACCOUNTS_FILE):
            os.remove(ACCOUNTS_FILE)

    def logout(self):
        """Clear the active session without removing the account from storage."""
        if self._user:
            login = self._user.get("login", "")
            if login:
                data = self._load_accounts_file()
                if data.get("active") == login:
                    data["active"] = ""
                    self._write_accounts_file(data)
        self._user = None

    @property
    def user(self):
        return self._user

    # ── internals ────────────────────────────────────────────────────────────

    def _validate_token(self, token: str) -> tuple[dict | None, set[str]]:
        """Validate a token against the GitHub API. Returns (user_dict, scopes) or (None, set())."""
        try:
            resp = requests.get(
                "https://api.github.com/user",
                headers={
                    "Authorization": f"Bearer {token}",
                    "Accept": "application/vnd.github+json",
                },
                timeout=10,
            )
            if resp.status_code == 200:
                scopes_header = resp.headers.get("X-OAuth-Scopes", "")
                scopes = {s.strip() for s in scopes_header.split(",") if s.strip()}
                return resp.json(), scopes
        except requests.exceptions.ConnectionError:
            self.auth_failed.emit("Couldn't reach GitHub — check your internet connection.")
            return None, set()
        except Exception:
            pass
        return None, set()

    def _save_account(self, user: dict, token: str):
        login = user.get("login", "")
        if not login:
            return
        data = self._load_accounts_file()
        accounts = data.get("accounts", {})
        accounts[login] = {
            "access_token": token,
            "login": login,
            "name": user.get("name") or login,
            "avatar_url": user.get("avatar_url", ""),
        }
        data["active"] = login
        data["accounts"] = accounts
        self._write_accounts_file(data)

    def _load_accounts_file(self) -> dict:
        try:
            with open(ACCOUNTS_FILE) as f:
                data = json.load(f)
            if isinstance(data, dict):
                return data
        except (FileNotFoundError, json.JSONDecodeError):
            pass
        return {"active": "", "accounts": {}}

    def _write_accounts_file(self, data: dict):
        with open(ACCOUNTS_FILE, "w") as f:
            json.dump(data, f, indent=2)

    def _migrate_legacy(self):
        """One-time migration from the old single-token file."""
        if os.path.exists(ACCOUNTS_FILE) or not os.path.exists(_LEGACY_TOKEN_FILE):
            return
        try:
            with open(_LEGACY_TOKEN_FILE) as f:
                old = json.load(f)
            token = old.get("access_token", "")
            if token:
                user, _ = self._validate_token(token)
                if user:
                    user["access_token"] = token
                    self._save_account(user, token)
            os.remove(_LEGACY_TOKEN_FILE)
        except Exception:
            pass

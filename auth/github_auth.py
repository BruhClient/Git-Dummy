import json
import os
import secrets
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import parse_qs, urlparse
from pathlib import Path

import requests
from dotenv import load_dotenv
from PyQt5.QtCore import QObject, pyqtSignal

# Load .env from the project root (two levels up from this file)
load_dotenv(Path(__file__).resolve().parent.parent / ".env")

# ── GitHub OAuth app credentials ─────────────────────────────────────────────
CLIENT_ID = os.environ.get("GITHUB_CLIENT_ID", "")
CLIENT_SECRET = os.environ.get("GITHUB_CLIENT_SECRET", "")
REDIRECT_URI = "http://localhost:9876/callback"
SCOPES = "read:user repo"

ACCOUNTS_FILE = os.path.join(os.path.expanduser("~"), ".evogit_accounts.json")
_LEGACY_TOKEN_FILE = os.path.join(os.path.expanduser("~"), ".evogit_token.json")


class _CallbackHandler(BaseHTTPRequestHandler):
    """Handles the single OAuth redirect from GitHub."""

    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path != "/callback":
            self._respond(404, "Not found")
            return

        params = parse_qs(parsed.query)
        code = params.get("code", [None])[0]
        state = params.get("state", [None])[0]

        if code and state == self.server.expected_state:
            self.server.auth_code = code
            self._respond(200, _SUCCESS_HTML)
        else:
            self._respond(400, "Bad request — state mismatch or missing code.")

    def _respond(self, status, body):
        body_bytes = body.encode()
        self.send_response(status)
        self.send_header("Content-Type", "text/html")
        self.send_header("Content-Length", len(body_bytes))
        self.end_headers()
        self.wfile.write(body_bytes)

    def log_message(self, *_):
        pass  # suppress default stderr logging


_SUCCESS_HTML = """
<!DOCTYPE html><html><head><meta charset="utf-8">
<style>
  body { background:#0f0f0f; color:#ededed; font-family:system-ui;
         display:flex; flex-direction:column; align-items:center;
         justify-content:center; height:100vh; margin:0; }
  h1   { color:#e05535; font-size:2rem; margin-bottom:.5rem; }
  p    { color:#a1a1a1; }
</style></head><body>
<h1>Authenticated!</h1>
<p>You can close this tab and return to Evo Git.</p>
</body></html>
"""


class GitHubAuth(QObject):
    """
    Manages GitHub OAuth web flow for a single signed-in account.

    Signals:
        auth_success(dict)   — emitted with user profile on login / session restore
        auth_failed(str)     — emitted with error message on failure
    """

    auth_success = pyqtSignal(dict)
    auth_failed = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._user: dict | None = None
        self._migrate_legacy()

    # ── public ───────────────────────────────────────────────────────────────

    def has_saved_token(self) -> bool:
        data = self._load_accounts_file()
        return bool(data.get("accounts"))

    def load_saved_token(self):
        """Try to restore the active saved session; emits auth_success or auth_failed."""
        data = self._load_accounts_file()
        accounts = data.get("accounts", {})
        active = data.get("active", "")
        if not accounts:
            self.auth_failed.emit("No saved accounts.")
            return
        # Fall back to first account if active key is missing
        if active not in accounts:
            active = next(iter(accounts))
        account = accounts[active]
        token = account.get("access_token", "")
        user = self._fetch_user(token)
        if user:
            user["access_token"] = token
            self._user = user
            self._save_account(user, token)  # refresh cached profile
            self.auth_success.emit(user)
        else:
            self.logout()
            self.auth_failed.emit("Saved token expired.")

    def start_oauth_flow(self):
        """Open browser and spin up local callback server on a background thread."""
        if not CLIENT_ID:
            self.auth_failed.emit(
                "GITHUB_CLIENT_ID is not set.\n"
                "Create a GitHub OAuth App and set the env vars:\n"
                "  GITHUB_CLIENT_ID\n  GITHUB_CLIENT_SECRET"
            )
            return
        state = secrets.token_urlsafe(16)
        server = self._make_server(state)   # bind port BEFORE opening browser
        webbrowser.open(self._build_auth_url(state))
        threading.Thread(
            target=self._wait_for_callback, args=(server,), daemon=True
        ).start()

    def logout(self):
        self._user = None
        if os.path.exists(ACCOUNTS_FILE):
            os.remove(ACCOUNTS_FILE)

    @property
    def user(self):
        return self._user

    # ── internals ────────────────────────────────────────────────────────────

    def _build_auth_url(self, state: str) -> str:
        return (
            f"https://github.com/login/oauth/authorize"
            f"?client_id={CLIENT_ID}"
            f"&redirect_uri={REDIRECT_URI}"
            f"&scope={SCOPES}"
            f"&state={state}"
        )

    def _make_server(self, state: str) -> HTTPServer:
        server = HTTPServer(("localhost", 9876), _CallbackHandler)
        server.expected_state = state
        server.auth_code = None
        server.timeout = 1
        return server

    def _wait_for_callback(self, server: HTTPServer):
        for _ in range(300):
            server.handle_request()
            if server.auth_code:
                break
        else:
            self.auth_failed.emit("OAuth timed out — no response from GitHub.")
            return

        token = self._exchange_code(server.auth_code)
        if not token:
            self.auth_failed.emit("Failed to exchange code for token.")
            return

        user = self._fetch_user(token)
        if not user:
            self.auth_failed.emit("Failed to fetch GitHub user profile.")
            return

        user["access_token"] = token
        self._save_account(user, token)
        self._user = user
        self.auth_success.emit(user)

    def _exchange_code(self, code: str) -> str | None:
        try:
            resp = requests.post(
                "https://github.com/login/oauth/access_token",
                data={
                    "client_id": CLIENT_ID,
                    "client_secret": CLIENT_SECRET,
                    "code": code,
                    "redirect_uri": REDIRECT_URI,
                },
                headers={"Accept": "application/json"},
                timeout=10,
            )
            return resp.json().get("access_token")
        except Exception:
            return None

    def _fetch_user(self, token: str) -> dict | None:
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
                return resp.json()
        except Exception:
            pass
        return None

    def _save_account(self, user: dict, token: str):
        login = user.get("login", "")
        if not login:
            return
        data = {
            "active": login,
            "accounts": {
                login: {
                    "access_token": token,
                    "login": login,
                    "name": user.get("name") or login,
                    "avatar_url": user.get("avatar_url", ""),
                }
            },
        }
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
                user = self._fetch_user(token)
                if user:
                    user["access_token"] = token
                    self._save_account(user, token)
            os.remove(_LEGACY_TOKEN_FILE)
        except Exception:
            pass

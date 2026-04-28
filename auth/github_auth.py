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

TOKEN_FILE = os.path.join(os.path.expanduser("~"), ".gitdummy_token.json")


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
  h1   { color:#3ecf8e; font-size:2rem; margin-bottom:.5rem; }
  p    { color:#a1a1a1; }
</style></head><body>
<h1>Authenticated!</h1>
<p>You can close this tab and return to Git Dummy.</p>
</body></html>
"""


class GitHubAuth(QObject):
    """
    Manages GitHub OAuth device/web flow.

    Signals:
        auth_success(dict)  — emitted with user profile on success
        auth_failed(str)    — emitted with error message on failure
    """

    auth_success = pyqtSignal(dict)
    auth_failed = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._user: dict | None = None

    # ── public ───────────────────────────────────────────────────────────────

    def has_saved_token(self) -> bool:
        return os.path.exists(TOKEN_FILE)

    def load_saved_token(self):
        """Try to restore a saved session; emits auth_success or auth_failed."""
        try:
            with open(TOKEN_FILE) as f:
                data = json.load(f)
            token = data.get("access_token", "")
            user = self._fetch_user(token)
            if user:
                user["access_token"] = token
                self._user = user
                self.auth_success.emit(user)
            else:
                os.remove(TOKEN_FILE)
                self.auth_failed.emit("Saved token expired.")
        except Exception as e:
            self.auth_failed.emit(str(e))

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
        auth_url = (
            f"https://github.com/login/oauth/authorize"
            f"?client_id={CLIENT_ID}"
            f"&redirect_uri={REDIRECT_URI}"
            f"&scope={SCOPES}"
            f"&state={state}"
        )
        webbrowser.open(auth_url)
        threading.Thread(
            target=self._wait_for_callback, args=(state,), daemon=True
        ).start()

    def logout(self):
        self._user = None
        if os.path.exists(TOKEN_FILE):
            os.remove(TOKEN_FILE)

    @property
    def user(self):
        return self._user

    # ── internals ────────────────────────────────────────────────────────────

    def _wait_for_callback(self, state: str):
        server = HTTPServer(("localhost", 9876), _CallbackHandler)
        server.expected_state = state
        server.auth_code = None
        server.timeout = 1

        # Poll until we get the code (max 5 min)
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
        self._user = user
        self._save_token(token)
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

    def _save_token(self, token: str):
        with open(TOKEN_FILE, "w") as f:
            json.dump({"access_token": token}, f)

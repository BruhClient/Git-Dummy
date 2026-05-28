from __future__ import annotations

import os

from PyQt5.QtCore import Qt, QThread, QObject, pyqtSignal
from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QLineEdit, QCheckBox, QStackedWidget, QWidget, QSizePolicy,
)
from styles.theme import COLORS, BTN_PRIMARY, BTN_SECONDARY, INPUT_STYLE
from core import ops as git_ops


# ── background worker ─────────────────────────────────────────────────────────

class _Worker(QObject):
    done = pyqtSignal(bool, str)   # success, message

    def __init__(self, fn, *args):
        super().__init__()
        self._fn = fn
        self._args = args

    def run(self):
        ok, msg = self._fn(*self._args)
        self.done.emit(ok, msg)


# ── step widgets ──────────────────────────────────────────────────────────────

def _label(text, size=13, color=None, bold=False, wrap=False) -> QLabel:
    lbl = QLabel(text)
    weight = "font-weight: 600;" if bold else ""
    col = color or COLORS["text_primary"]
    lbl.setStyleSheet(f"background: transparent; font-size: {size}px; color: {col}; {weight}")
    if wrap:
        lbl.setWordWrap(True)
    return lbl


def _divider():
    from PyQt5.QtWidgets import QFrame
    d = QFrame()
    d.setFrameShape(QFrame.HLine)
    d.setStyleSheet(f"background: {COLORS['border']}; max-height: 1px;")
    return d


class _StepInit(QWidget):
    """Step 1 — confirm git init."""

    confirmed = pyqtSignal()
    cancelled = pyqtSignal()

    def __init__(self, folder: str, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setSpacing(16)

        layout.addWidget(_label("This folder isn't tracked yet", 18, bold=True))
        layout.addWidget(_label(
            f"<b>{os.path.basename(folder)}</b> isn't being tracked by Git Dummy.",
            13, COLORS["text_secondary"], wrap=True,
        ))
        layout.addWidget(_label(folder, 11, COLORS["text_muted"]))
        layout.addWidget(_divider())
        layout.addWidget(_label(
            "Would you like to start tracking changes in this folder?",
            13, wrap=True,
        ))
        layout.addStretch()

        row = QHBoxLayout()
        cancel = QPushButton("Not now")
        cancel.setStyleSheet(BTN_SECONDARY)
        cancel.setFixedHeight(38)
        cancel.setCursor(Qt.PointingHandCursor)
        cancel.clicked.connect(self.cancelled.emit)
        row.addWidget(cancel)

        init_btn = QPushButton("Start Tracking")
        init_btn.setStyleSheet(BTN_PRIMARY)
        init_btn.setFixedHeight(38)
        init_btn.setCursor(Qt.PointingHandCursor)
        init_btn.clicked.connect(self.confirmed.emit)
        row.addWidget(init_btn)
        layout.addLayout(row)


class _StepGitHub(QWidget):
    """Step 2 — offer to push to GitHub."""

    push_requested = pyqtSignal(str, bool)  # repo_name, private
    skipped = pyqtSignal()

    def __init__(self, folder: str, has_token: bool, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setSpacing(16)

        layout.addWidget(_label("Tracking started!", 18, COLORS["accent"], bold=True))
        layout.addWidget(_divider())

        if not has_token:
            layout.addWidget(_label(
                "Sign in with GitHub to back up this folder online.",
                13, COLORS["text_secondary"], wrap=True,
            ))
            layout.addStretch()
            close_btn = QPushButton("Close")
            close_btn.setStyleSheet(BTN_SECONDARY)
            close_btn.setFixedHeight(38)
            close_btn.setCursor(Qt.PointingHandCursor)
            close_btn.clicked.connect(self.skipped.emit)
            layout.addWidget(close_btn)
            return

        layout.addWidget(_label("Back up to GitHub?", 14, bold=True))
        layout.addWidget(_label(
            "Save a copy of this folder online so it's safe and shareable.",
            13, COLORS["text_secondary"], wrap=True,
        ))

        name_label = _label("Project name", 12, COLORS["text_muted"])
        layout.addWidget(name_label)
        self._name_input = QLineEdit(os.path.basename(folder))
        self._name_input.setStyleSheet(INPUT_STYLE)
        self._name_input.setFixedHeight(38)
        layout.addWidget(self._name_input)

        self._private_cb = QCheckBox("Make private")
        self._private_cb.setStyleSheet(f"background: transparent; font-size: 13px; color: {COLORS['text_secondary']};")
        self._private_cb.setChecked(True)
        layout.addWidget(self._private_cb)

        layout.addStretch()

        row = QHBoxLayout()
        skip = QPushButton("Skip")
        skip.setStyleSheet(BTN_SECONDARY)
        skip.setFixedHeight(38)
        skip.setCursor(Qt.PointingHandCursor)
        skip.clicked.connect(self.skipped.emit)
        row.addWidget(skip)

        push_btn = QPushButton("Push to GitHub")
        push_btn.setStyleSheet(BTN_PRIMARY)
        push_btn.setFixedHeight(38)
        push_btn.setCursor(Qt.PointingHandCursor)
        push_btn.clicked.connect(
            lambda: self.push_requested.emit(
                self._name_input.text().strip(),
                self._private_cb.isChecked(),
            )
        )
        row.addWidget(push_btn)
        layout.addLayout(row)


class _StepProgress(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignCenter)
        self._label = _label("Working…", 15, COLORS["text_secondary"])
        self._label.setAlignment(Qt.AlignCenter)
        layout.addWidget(self._label)

    def set_text(self, text: str):
        self._label.setText(text)


class _StepDone(QWidget):
    closed = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setSpacing(16)

        self._icon = _label("", 32, COLORS["accent"])
        self._icon.setAlignment(Qt.AlignCenter)
        layout.addWidget(self._icon)

        self._title = _label("", 18, bold=True)
        self._title.setAlignment(Qt.AlignCenter)
        layout.addWidget(self._title)

        self._body = _label("", 13, COLORS["text_secondary"], wrap=True)
        self._body.setAlignment(Qt.AlignCenter)
        layout.addWidget(self._body)

        layout.addStretch()

        close_btn = QPushButton("Done")
        close_btn.setStyleSheet(BTN_PRIMARY)
        close_btn.setFixedHeight(38)
        close_btn.setCursor(Qt.PointingHandCursor)
        close_btn.clicked.connect(self.closed.emit)
        layout.addWidget(close_btn)

    def show_success(self, title: str, body: str):
        self._icon.setText("✓")
        self._icon.setStyleSheet(f"background: transparent; font-size: 40px; color: {COLORS['accent']};")
        self._title.setText(title)
        self._title.setStyleSheet(f"background: transparent; font-size: 18px; font-weight: 600; color: {COLORS['text_primary']};")
        self._body.setText(body)

    def show_error(self, title: str, body: str):
        self._icon.setText("✕")
        self._icon.setStyleSheet(f"background: transparent; font-size: 40px; color: {COLORS['danger']};")
        self._title.setText(title)
        self._title.setStyleSheet(f"background: transparent; font-size: 18px; font-weight: 600; color: {COLORS['danger']};")
        self._body.setText(body)


# ── dialog shell ──────────────────────────────────────────────────────────────

class InitDialog(QDialog):
    """
    Multi-step dialog: git init → push to GitHub.

    Parameters
    ----------
    folder_path : str
        The folder the user dropped (no .git inside).
    user : dict | None
        GitHub user dict from GitHubAuth (contains access_token, login).
        Pass None if not authenticated.
    repo_added : callable(str)
        Called with folder_path after successful git init so the page
        can add it to the tracked list.
    """

    def __init__(self, folder_path: str, user: dict | None, repo_added, parent=None):
        super().__init__(parent)
        self._path = folder_path
        self._user = user
        self._repo_added = repo_added
        self._thread: QThread | None = None

        self.setWindowTitle("Set Up Project")
        self.setModal(True)
        self.setFixedSize(460, 340)
        self.setStyleSheet(f"""
            QDialog {{
                background: {COLORS['bg_card']};
                border: 1px solid {COLORS['border']};
                border-radius: 12px;
            }}
        """)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(32, 28, 32, 28)

        self._stack = QStackedWidget()
        outer.addWidget(self._stack)

        has_token = bool(user and user.get("access_token"))

        self._step_init = _StepInit(folder_path)
        self._step_github = _StepGitHub(folder_path, has_token)
        self._step_progress = _StepProgress()
        self._step_done = _StepDone()

        self._stack.addWidget(self._step_init)
        self._stack.addWidget(self._step_github)
        self._stack.addWidget(self._step_progress)
        self._stack.addWidget(self._step_done)

        # Wire signals
        self._step_init.confirmed.connect(self._do_init)
        self._step_init.cancelled.connect(self.reject)
        self._step_github.push_requested.connect(self._do_push)
        self._step_github.skipped.connect(self.accept)
        self._step_done.closed.connect(self.accept)

    # ── steps ─────────────────────────────────────────────────────────────────

    def _do_init(self):
        self._step_progress.set_text("Setting up tracking…")
        self._stack.setCurrentWidget(self._step_progress)

        u = self._user or {}
        name  = u.get("name") or u.get("login", "")
        email = u.get("email", "")
        self._run_in_thread(
            lambda: git_ops.init_repo(self._path, name, email),
            self._on_init_done,
        )

    def _on_init_done(self, ok: bool, msg: str):
        if not ok:
            self._step_done.show_error("Initialisation failed", msg or "Unknown error.")
            self._stack.setCurrentWidget(self._step_done)
            return

        self._repo_added(self._path)
        self._stack.setCurrentWidget(self._step_github)

    def _do_push(self, repo_name: str, private: bool):
        if not repo_name:
            return

        token      = self._user["access_token"]
        login      = self._user.get("login", "")
        user_name  = self._user.get("name") or login
        user_email = self._user.get("email", "")

        self._step_progress.set_text("Creating your GitHub project…")
        self._stack.setCurrentWidget(self._step_progress)

        def _work():
            ok, err, clone_url = git_ops.create_github_repo(repo_name, private, token)
            if not ok:
                return False, f"Could not create repo: {err}"
            self._step_progress.set_text("Uploading your files…")
            ok2, err2 = git_ops.push_to_github(self._path, clone_url, login, token, user_name, user_email)
            if not ok2:
                return False, f"Push failed: {err2}"
            return True, clone_url

        self._run_in_thread(_work, self._on_push_done)

    def _on_push_done(self, ok: bool, msg: str):
        if ok:
            self._step_done.show_success(
                "Pushed to GitHub!",
                f"Your repository is now live.\n{msg}",
            )
        else:
            self._step_done.show_error("Push failed", msg)
        self._stack.setCurrentWidget(self._step_done)

    # ── thread helper ─────────────────────────────────────────────────────────

    def _run_in_thread(self, fn, callback):
        self._thread = QThread()
        self._worker = _Worker(fn)
        self._worker.moveToThread(self._thread)
        self._thread.started.connect(self._worker.run)
        self._worker.done.connect(callback)
        self._worker.done.connect(self._thread.quit)
        self._thread.start()

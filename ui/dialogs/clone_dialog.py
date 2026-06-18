"""CloneDialog and RepoRow — dialog for cloning a remote repo."""
from __future__ import annotations

import os

from PyQt5.QtCore import Qt, pyqtSignal, QThread
from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QFileDialog, QScrollArea, QSizePolicy,
    QLineEdit, QWidget,
)
from styles.theme import COLORS
from core import settings_store
from ui.workers.repo_workers import _FetchReposWorker, _CloneWorker


def _rel_time(iso: str) -> str:
    """Convert ISO 8601 timestamp to a human-readable relative string."""
    from datetime import datetime, timezone
    try:
        dt = datetime.fromisoformat(iso.replace("Z", "+00:00"))
        delta = datetime.now(timezone.utc) - dt
        s = delta.total_seconds()
        if s < 3600:  return f"{int(s // 60)}m ago"
        if s < 86400: return f"{int(s // 3600)}h ago"
        d = int(s // 86400)
        if d == 1:    return "yesterday"
        if d < 30:    return f"{d} days ago"
        if d < 365:   return f"{d // 30} months ago"
        return f"{d // 365} years ago"
    except Exception:
        return ""


def _remote_url(repo_path: str) -> str:
    """Return the origin remote URL for a local repo, or '' if not found."""
    import configparser
    try:
        cfg = configparser.ConfigParser()
        cfg.read(os.path.join(repo_path, ".git", "config"), encoding="utf-8")
        return cfg.get('remote "origin"', "url", fallback="")
    except Exception:
        return ""


class _RepoRow(QWidget):
    """Compact clickable row for one GitHub repo in the clone dialog list."""
    clicked = pyqtSignal(dict)

    def __init__(self, repo: dict, parent=None):
        super().__init__(parent)
        self._repo = repo
        self._selected = False
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setCursor(Qt.PointingHandCursor)
        self.setFixedHeight(44)
        self._apply_style(False)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 0, 12, 0)
        layout.setSpacing(8)

        name_lbl = QLabel(repo.get("name", ""))
        name_lbl.setStyleSheet(
            f"background: transparent; font-size: 13px; font-weight: 600; font-family: 'Tilt Warp'; color: {COLORS['text_primary']};"
        )
        name_lbl.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        layout.addWidget(name_lbl)

        is_private = repo.get("private", False)
        badge = QLabel(" private " if is_private else " public ")
        if is_private:
            badge.setStyleSheet(
                f"background: {COLORS['accent_dim']}; color: {COLORS['accent']};"
                f" font-size: 10px; font-weight: 600; font-family: 'Tilt Warp'; border-radius: 4px; padding: 1px 0;"
            )
        else:
            badge.setStyleSheet(
                f"background: {COLORS['bg_hover']}; color: {COLORS['text_muted']};"
                f" font-size: 10px; font-weight: 600; font-family: 'Tilt Warp'; border-radius: 4px; padding: 1px 0;"
            )
        badge.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        layout.addWidget(badge)

        layout.addStretch()

        date_lbl = QLabel(_rel_time(repo.get("updated_at", "")))
        date_lbl.setStyleSheet(
            f"background: transparent; font-size: 11px; color: {COLORS['text_muted']};"
        )
        date_lbl.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        layout.addWidget(date_lbl)

    def set_selected(self, selected: bool):
        self._selected = selected
        self._apply_style(selected)

    def _apply_style(self, selected: bool):
        bg = COLORS["accent_dim"] if selected else "transparent"
        border = COLORS["accent"] if selected else "transparent"
        self.setStyleSheet(f"background: {bg}; border-left: 2px solid {border};")

    def enterEvent(self, _):
        if not self._selected:
            self.setStyleSheet(f"background: {COLORS['bg_hover']}; border-left: 2px solid transparent;")

    def leaveEvent(self, _):
        self._apply_style(self._selected)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.clicked.emit(self._repo)
        super().mousePressEvent(event)


# Public alias
RepoRow = _RepoRow


class CloneDialog(QDialog):
    """Dialog to clone a remote repo — shows the user's GitHub repos for quick access
    plus a URL input fallback."""

    cloned = pyqtSignal(str)   # emits the cloned (or already-tracked) repo path

    def __init__(self, parent=None, user: dict | None = None,
                 existing_repos: list | None = None):
        super().__init__(parent)
        self.setWindowFlags(Qt.Dialog | Qt.FramelessWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setFixedWidth(500)
        self._user           = user or {}
        self._token          = self._user.get("access_token", "")
        self._has_auth       = bool(self._token)
        self._existing_repos = existing_repos or []
        self._all_repos: list = []
        self._selected_row: _RepoRow | None = None
        self._dest = settings_store.get("last_clone_dest", os.path.expanduser("~"))
        # Two independent thread pairs
        self._fetch_thread = self._fetch_worker = None
        self._clone_thread = self._clone_worker = None
        self._setup_ui()
        if self._has_auth:
            self._start_fetch()

    # ── UI construction ────────────────────────────────────────────────────────

    def _setup_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)

        card = QWidget()
        card.setStyleSheet(f"""
            background: {COLORS['bg_card']};
            border-radius: 12px;
        """)
        vl = QVBoxLayout(card)
        vl.setContentsMargins(24, 24, 24, 24)
        vl.setSpacing(14)

        # Title
        title = QLabel("Connect to a repo")
        title.setStyleSheet(
            f"font-size: 16px; font-weight: 700; font-family: 'Tilt Warp'; color: {COLORS['text_primary']}; background: transparent;"
        )
        vl.addWidget(title)

        # ── Repo list section (authenticated only) ─────────────────────────
        self._repo_section = QWidget()
        self._repo_section.setStyleSheet("background: transparent;")
        rs_vl = QVBoxLayout(self._repo_section)
        rs_vl.setContentsMargins(0, 0, 0, 0)
        rs_vl.setSpacing(8)

        rs_header = QLabel("Your repositories")
        rs_header.setStyleSheet(
            f"font-size: 12px; color: {COLORS['text_muted']}; background: transparent;"
        )
        rs_vl.addWidget(rs_header)

        self._search_input = QLineEdit()
        self._search_input.setPlaceholderText("Search repositories…")
        self._search_input.setStyleSheet(f"""
            QLineEdit {{
                background: {COLORS['bg_primary']}; border: 1px solid {COLORS['border']};
                border-radius: 8px; color: {COLORS['text_primary']};
                font-size: 13px; padding: 7px 12px;
            }}
            QLineEdit:focus {{ border-color: {COLORS['accent']}; }}
        """)
        self._search_input.textChanged.connect(self._apply_filter)
        rs_vl.addWidget(self._search_input)

        self._loading_label = QLabel("Loading repositories…")
        self._loading_label.setStyleSheet(
            f"font-size: 12px; color: {COLORS['text_muted']}; background: transparent;"
        )
        rs_vl.addWidget(self._loading_label)

        self._empty_label = QLabel("No repositories found.")
        self._empty_label.setStyleSheet(
            f"font-size: 12px; color: {COLORS['text_muted']}; background: transparent;"
        )
        self._empty_label.setWordWrap(True)
        self._empty_label.hide()
        rs_vl.addWidget(self._empty_label)

        # Scroll area for repo rows
        scroll = QScrollArea()
        scroll.setFixedHeight(220)
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setStyleSheet(f"""
            QScrollArea {{
                border: 1px solid {COLORS['border']}; border-radius: 8px;
                background: {COLORS['bg_primary']};
            }}
            QScrollBar:vertical {{
                background: {COLORS['bg_primary']}; width: 6px; border: none;
            }}
            QScrollBar::handle:vertical {{
                background: {COLORS['border']}; border-radius: 3px; min-height: 20px;
            }}
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
        """)

        self._list_widget = QWidget()
        self._list_widget.setStyleSheet(f"background: {COLORS['bg_primary']};")
        self._list_layout = QVBoxLayout(self._list_widget)
        self._list_layout.setContentsMargins(0, 4, 0, 4)
        self._list_layout.setSpacing(0)
        self._list_layout.setAlignment(Qt.AlignTop)
        scroll.setWidget(self._list_widget)
        self._list_widget.hide()
        rs_vl.addWidget(scroll)

        vl.addWidget(self._repo_section)

        # ── "or enter a URL" separator (authenticated only) ────────────────
        self._sep_widget = QWidget()
        self._sep_widget.setStyleSheet("background: transparent;")
        sep_hl = QHBoxLayout(self._sep_widget)
        sep_hl.setContentsMargins(0, 0, 0, 0)
        sep_lbl = QLabel("or enter a URL")
        sep_lbl.setAlignment(Qt.AlignCenter)
        sep_lbl.setStyleSheet(
            f"font-size: 11px; color: {COLORS['text_muted']}; background: transparent;"
        )
        sep_hl.addWidget(sep_lbl)
        vl.addWidget(self._sep_widget)

        # ── URL input ──────────────────────────────────────────────────────
        url_label = QLabel("Repository URL")
        url_label.setStyleSheet(
            f"font-size: 12px; color: {COLORS['text_muted']}; background: transparent;"
        )
        vl.addWidget(url_label)

        self._url_input = QLineEdit()
        self._url_input.setPlaceholderText("https://github.com/user/repo.git")
        self._url_input.setStyleSheet(f"""
            QLineEdit {{
                background: {COLORS['bg_primary']}; border: 1px solid {COLORS['border']};
                border-radius: 8px; color: {COLORS['text_primary']};
                font-size: 13px; padding: 8px 12px;
            }}
            QLineEdit:focus {{ border-color: {COLORS['accent']}; }}
        """)
        self._url_input.textChanged.connect(self._on_url_changed)
        vl.addWidget(self._url_input)

        # ── Destination folder ──────────────────────────────────────────────
        dest_label = QLabel("Save to folder")
        dest_label.setStyleSheet(
            f"font-size: 12px; color: {COLORS['text_muted']}; background: transparent;"
        )
        vl.addWidget(dest_label)

        dest_row = QHBoxLayout()
        dest_row.setSpacing(8)
        self._dest_label = QLabel(self._dest)
        self._dest_label.setStyleSheet(f"""
            background: {COLORS['bg_primary']}; border: 1px solid {COLORS['border']};
            border-radius: 8px; color: {COLORS['text_secondary']};
            font-size: 12px; padding: 8px 12px;
        """)
        self._dest_label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self._dest_label.setFixedHeight(36)
        dest_row.addWidget(self._dest_label)

        browse_btn = QPushButton("Browse")
        browse_btn.setFixedSize(72, 36)
        browse_btn.setCursor(Qt.PointingHandCursor)
        browse_btn.setStyleSheet(f"""
            QPushButton {{
                background: {COLORS['bg_primary']}; border: 1px solid {COLORS['border']};
                border-radius: 8px; color: {COLORS['text_secondary']};
                font-size: 12px; font-weight: 600; font-family: 'Tilt Warp';
            }}
            QPushButton:hover {{ border-color: {COLORS['accent']}; color: {COLORS['accent']}; }}
        """)
        browse_btn.clicked.connect(self._pick_dest)
        dest_row.addWidget(browse_btn)
        vl.addLayout(dest_row)

        # ── Error label ────────────────────────────────────────────────────
        self._error_label = QLabel("")
        self._error_label.setStyleSheet(
            f"font-size: 12px; color: {COLORS['danger']}; background: transparent;"
        )
        self._error_label.setWordWrap(True)
        self._error_label.hide()
        vl.addWidget(self._error_label)

        # ── Buttons ────────────────────────────────────────────────────────
        btn_row = QHBoxLayout()
        btn_row.setSpacing(8)

        cancel_btn = QPushButton("Cancel")
        cancel_btn.setFixedHeight(40)
        cancel_btn.setCursor(Qt.PointingHandCursor)
        cancel_btn.setStyleSheet(f"""
            QPushButton {{
                background: transparent; border: 1px solid {COLORS['border']};
                border-radius: 8px; color: {COLORS['text_secondary']};
                font-size: 13px; font-weight: 600; font-family: 'Tilt Warp';
            }}
            QPushButton:hover {{ border-color: {COLORS['text_secondary']}; }}
        """)
        cancel_btn.clicked.connect(self.reject)
        btn_row.addWidget(cancel_btn)

        self._clone_btn = QPushButton("Clone")
        self._clone_btn.setFixedHeight(40)
        self._clone_btn.setCursor(Qt.PointingHandCursor)
        self._clone_btn.setStyleSheet(f"""
            QPushButton {{
                background: {COLORS['accent']}; border: none;
                border-radius: 8px; color: {COLORS['text_on_accent']};
                font-size: 13px; font-weight: 700; font-family: 'Tilt Warp';
            }}
            QPushButton:hover {{ background: {COLORS.get('accent_hover', COLORS['accent'])}; }}
            QPushButton:disabled {{ background: {COLORS['border']}; color: {COLORS['text_muted']}; }}
        """)
        self._clone_btn.clicked.connect(self._start_clone)
        btn_row.addWidget(self._clone_btn)
        vl.addLayout(btn_row)

        root.addWidget(card)

        # Hide authenticated-only widgets if not logged in
        if not self._has_auth:
            self._repo_section.hide()
            self._sep_widget.hide()

    # ── Fetch GitHub repos ─────────────────────────────────────────────────────

    def _start_fetch(self):
        self._loading_label.show()
        self._list_widget.hide()
        self._empty_label.hide()
        self._fetch_thread = QThread()
        self._fetch_worker = _FetchReposWorker(self._token)
        self._fetch_worker.moveToThread(self._fetch_thread)
        self._fetch_thread.started.connect(self._fetch_worker.run)
        self._fetch_worker.finished.connect(self._on_repos_fetched)
        self._fetch_worker.finished.connect(self._fetch_thread.quit)
        self._fetch_thread.finished.connect(self._on_fetch_thread_done)
        self._fetch_thread.start()

    def _on_repos_fetched(self, repos: list):
        self._all_repos = repos
        self._loading_label.hide()
        if not repos:
            self._empty_label.setText(
                "No repositories found. Check your connection or enter a URL below."
            )
            self._empty_label.show()
            self._list_widget.hide()
        else:
            self._list_widget.show()
            self._apply_filter(self._search_input.text())
        self.adjustSize()

    def _on_fetch_thread_done(self):
        self._fetch_thread = None
        self._fetch_worker = None

    # ── Filtering & selection ─────────────────────────────────────────────────

    def _apply_filter(self, text: str):
        query = text.strip().lower()
        # Destroy existing rows and reset selection
        self._selected_row = None
        while self._list_layout.count():
            item = self._list_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        filtered = [r for r in self._all_repos if query in r.get("name", "").lower()]

        if not filtered:
            self._empty_label.setText("No matches found." if query else "No repositories found.")
            self._empty_label.show()
            self._list_widget.hide()
        else:
            self._empty_label.hide()
            self._list_widget.show()
            for repo in filtered:
                row = _RepoRow(repo)
                row.clicked.connect(self._on_repo_clicked)
                self._list_layout.addWidget(row)

    def _on_repo_clicked(self, repo: dict):
        if self._selected_row is not None:
            self._selected_row.set_selected(False)
        for i in range(self._list_layout.count()):
            w = self._list_layout.itemAt(i).widget()
            if isinstance(w, _RepoRow) and w._repo is repo:
                w.set_selected(True)
                self._selected_row = w
                break
        # Fill URL field without triggering deselection
        self._url_input.blockSignals(True)
        self._url_input.setText(repo.get("clone_url", ""))
        self._url_input.blockSignals(False)
        self._error_label.hide()

    def _on_url_changed(self, _text: str):
        """User manually edited the URL field — deselect any highlighted repo row."""
        if self._selected_row is not None:
            self._selected_row.set_selected(False)
            self._selected_row = None

    # ── Clone ─────────────────────────────────────────────────────────────────

    def _pick_dest(self):
        folder = QFileDialog.getExistingDirectory(self, "Choose parent folder", self._dest)
        if folder:
            self._dest = folder
            self._dest_label.setText(folder)
            settings_store.save({"last_clone_dest": folder})

    def _start_clone(self):
        url = self._url_input.text().strip()
        if not url:
            self._show_error("Please enter a repository URL.")
            return

        # If this URL is already tracked locally, just open it — don't re-clone
        def _norm(u: str) -> str:
            return u.rstrip("/").removesuffix(".git").lower()
        for path in self._existing_repos:
            existing_url = _remote_url(path)
            if existing_url and _norm(existing_url) == _norm(url):
                self.cloned.emit(path)
                self.accept()
                return

        self._error_label.hide()
        self._clone_btn.setEnabled(False)
        self._clone_btn.setText("Cloning…")
        if self._has_auth:
            self._repo_section.setEnabled(False)

        self._clone_thread = QThread()
        self._clone_worker = _CloneWorker(url, self._dest)
        self._clone_worker.moveToThread(self._clone_thread)
        self._clone_thread.started.connect(self._clone_worker.run)
        self._clone_worker.finished.connect(self._on_done)
        self._clone_worker.finished.connect(self._clone_thread.quit)
        self._clone_thread.finished.connect(self._on_clone_thread_done)
        self._clone_thread.start()

    def _on_done(self, ok: bool, err: str, path: str):
        if ok:
            self.cloned.emit(path)
            self.accept()
        else:
            self._show_error("Clone failed — check the URL and your internet connection.")
            self._clone_btn.setEnabled(True)
            self._clone_btn.setText("Clone")
            if self._has_auth:
                self._repo_section.setEnabled(True)

    def _on_clone_thread_done(self):
        self._clone_thread = None
        self._clone_worker = None

    def _show_error(self, msg: str):
        self._error_label.setText(msg)
        self._error_label.show()
        self.adjustSize()

    def closeEvent(self, event):
        for attr in ("_fetch_thread", "_clone_thread"):
            t = getattr(self, attr, None)
            if t is not None:
                t.quit()
                t.wait(500)
        super().closeEvent(event)

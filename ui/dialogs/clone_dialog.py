"""CloneDialog and RepoRow — dialog for cloning a remote repo."""
from __future__ import annotations

import os

import qtawesome as qta
from PyQt5.QtCore import Qt, QSize, pyqtSignal, QThread
from PyQt5.QtGui import QPalette, QColor
from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QFileDialog, QScrollArea, QSizePolicy,
    QLineEdit, QWidget, QFrame, QStackedWidget,
)
from styles.theme import COLORS, scrollbar_style
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
    """Minimal clickable row for one GitHub repo."""
    clicked = pyqtSignal(dict)

    def __init__(self, repo: dict, parent=None):
        super().__init__(parent)
        self._repo = repo
        self._selected = False
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setCursor(Qt.PointingHandCursor)
        self.setFixedHeight(36)
        self._apply_style(False)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 0, 10, 0)
        layout.setSpacing(0)

        name_lbl = QLabel(repo.get("name", ""))
        name_lbl.setStyleSheet(
            f"font-size: 13px; font-weight: 500; color: {COLORS['text_primary']};"
        )
        name_lbl.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        layout.addWidget(name_lbl)

        layout.addStretch()

        is_private = repo.get("private", False)
        if is_private:
            lock_lbl = QLabel()
            lock_lbl.setPixmap(
                qta.icon("fa5s.lock", color=COLORS["text_muted"]).pixmap(10, 10)
            )
            lock_lbl.setFixedSize(14, 14)
            lock_lbl.setAttribute(Qt.WA_TransparentForMouseEvents, True)
            layout.addWidget(lock_lbl)
            layout.addSpacing(8)

        date_lbl = QLabel(_rel_time(repo.get("updated_at", "")))
        date_lbl.setStyleSheet(
            f"font-size: 11px; color: {COLORS['text_muted']};"
        )
        date_lbl.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        layout.addWidget(date_lbl)

    def set_selected(self, selected: bool):
        self._selected = selected
        self._apply_style(selected)

    def _apply_style(self, selected: bool):
        if selected:
            self.setStyleSheet(
                f"background: {COLORS['accent_dim']}; border-radius: 6px;"
            )
        else:
            self.setStyleSheet("background: transparent; border-radius: 6px;")

    def enterEvent(self, _):
        if not self._selected:
            self.setStyleSheet(f"background: {COLORS['bg_hover']}; border-radius: 6px;")

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
    _init_done_sig = pyqtSignal(bool, str, str)  # ok, err, folder

    def __init__(self, parent=None, user: dict | None = None,
                 existing_repos: list | None = None):
        super().__init__(parent)
        self.setWindowFlags(Qt.Dialog | Qt.FramelessWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setFixedWidth(480)
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
        self._init_folder = ""
        self._init_done_sig.connect(self._on_init_done)
        self._setup_ui()
        if self._has_auth:
            self._start_fetch()

    # ── UI construction ────────────────────────────────────────────────────────

    def _setup_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)

        card = QWidget()
        card.setObjectName("cloneCard")
        card.setStyleSheet(f"""
            #cloneCard {{
                background: {COLORS['bg_card']};
                border: 1px solid {COLORS['border']};
                border-radius: 12px;
            }}
            #cloneCard QWidget {{
                background: transparent;
            }}
            #cloneCard QLineEdit {{
                background: {COLORS['bg_primary']};
            }}
        """)
        vl = QVBoxLayout(card)
        vl.setContentsMargins(24, 20, 24, 24)
        vl.setSpacing(14)

        # ── Title row with close button ────────────────────────────────────
        title_row = QHBoxLayout()
        title_row.setContentsMargins(0, 0, 0, 0)
        title = QLabel("Track a Project")
        title.setStyleSheet(
            f"font-size: 15px; font-weight: 700; font-family: 'Tilt Warp'; "
            f"color: {COLORS['text_primary']};"
        )
        title_row.addWidget(title)
        title_row.addStretch()

        close_btn = QPushButton()
        close_btn.setFixedSize(28, 28)
        close_btn.setCursor(Qt.PointingHandCursor)
        close_btn.setIcon(qta.icon("fa5s.times", color=COLORS["text_muted"]))
        close_btn.setStyleSheet(
            f"QPushButton {{ background: transparent; border: none; border-radius: 14px; }}"
            f"QPushButton:hover {{ background: {COLORS['bg_hover']}; }}"
        )
        close_btn.clicked.connect(self.reject)
        title_row.addWidget(close_btn)
        vl.addLayout(title_row)

        # ── Tab bar ────────────────────────────────────────────────────────
        tab_row = QHBoxLayout()
        tab_row.setSpacing(0)
        tab_row.setContentsMargins(0, 0, 0, 0)
        self._tab_browse = QPushButton("Browse folder")
        self._tab_clone  = QPushButton("Clone repository")
        _tab_active = (
            f"QPushButton {{ background: transparent; border: none; border-bottom: 2px solid {COLORS['accent']};"
            f" color: {COLORS['text_primary']}; font-size: 13px; font-weight: 600;"
            f" font-family: 'Tilt Warp'; padding: 6px 16px; }}"
        )
        _tab_inactive = (
            f"QPushButton {{ background: transparent; border: none; border-bottom: 2px solid transparent;"
            f" color: {COLORS['text_muted']}; font-size: 13px; font-weight: 600;"
            f" font-family: 'Tilt Warp'; padding: 6px 16px; }}"
            f"QPushButton:hover {{ color: {COLORS['text_secondary']}; }}"
        )
        self._tab_active_style = _tab_active
        self._tab_inactive_style = _tab_inactive
        for btn in (self._tab_browse, self._tab_clone):
            btn.setCursor(Qt.PointingHandCursor)
            btn.setFixedHeight(34)
        self._tab_browse.setStyleSheet(_tab_active)
        self._tab_clone.setStyleSheet(_tab_inactive)
        tab_row.addWidget(self._tab_browse)
        tab_row.addWidget(self._tab_clone)
        tab_row.addStretch()
        vl.addLayout(tab_row)

        self._stack = QStackedWidget()

        # ── Browse tab (with inline init flow) ─────────────────────────────
        self._browse_stack = QStackedWidget()
        self._browse_stack.setStyleSheet("")

        # Page 0: drop zone + choose folder
        drop_page = QWidget()
        drop_page.setAcceptDrops(True)
        drop_page.dragEnterEvent = self._drop_drag_enter
        drop_page.dropEvent = self._drop_drop
        bp_vl = QVBoxLayout(drop_page)
        bp_vl.setContentsMargins(0, 8, 0, 0)
        bp_vl.setSpacing(14)

        drop_box = QWidget()
        drop_box.setObjectName("dropBox")
        drop_box.setMinimumHeight(120)
        drop_box.setCursor(Qt.PointingHandCursor)
        drop_box.setStyleSheet(f"""
            #dropBox {{
                background: transparent;
                border: 2px dashed {COLORS['border']};
                border-radius: 10px;
            }}
            #dropBox:hover {{
                border-color: {COLORS['accent']};
            }}
        """)
        dl = QVBoxLayout(drop_box)
        dl.setAlignment(Qt.AlignCenter)
        dl.setSpacing(8)
        di = QLabel()
        di.setPixmap(qta.icon("fa5s.upload", color=COLORS["text_muted"]).pixmap(28, 28))
        di.setAlignment(Qt.AlignCenter)
        di.setStyleSheet("border: none;")
        dl.addWidget(di)
        dt = QLabel("Drop a project folder here")
        dt.setAlignment(Qt.AlignCenter)
        dt.setStyleSheet(
            f"border: none; font-size: 13px; font-weight: 600;"
            f" font-family: 'Tilt Warp'; color: {COLORS['text_secondary']};"
        )
        dl.addWidget(dt)
        drop_box.mousePressEvent = lambda _: self._browse_folder()
        bp_vl.addWidget(drop_box)
        drop_page.setStyleSheet("")
        self._browse_stack.addWidget(drop_page)

        # Page 1: init confirmation
        init_page = QWidget()
        init_page.setStyleSheet("")
        ip_vl = QVBoxLayout(init_page)
        ip_vl.setContentsMargins(0, 8, 0, 0)
        ip_vl.setSpacing(12)
        self._init_title = QLabel()
        self._init_title.setStyleSheet(
            f"font-size: 14px; font-weight: 700; font-family: 'Tilt Warp'; color: {COLORS['text_primary']};"
        )
        ip_vl.addWidget(self._init_title)
        self._init_desc = QLabel()
        self._init_desc.setWordWrap(True)
        self._init_desc.setStyleSheet(f"font-size: 12px; color: {COLORS['text_muted']};")
        ip_vl.addWidget(self._init_desc)
        ip_vl.addStretch()
        self._init_status = QLabel("")
        self._init_status.setStyleSheet(f"font-size: 12px; color: {COLORS['text_muted']};")
        self._init_status.hide()
        ip_vl.addWidget(self._init_status)
        init_row = QHBoxLayout()
        init_row.setSpacing(8)
        back_btn = QPushButton("Back")
        back_btn.setFixedHeight(36)
        back_btn.setCursor(Qt.PointingHandCursor)
        back_btn.setStyleSheet(f"""
            QPushButton {{
                background: transparent; border: 1px solid {COLORS['border']};
                border-radius: 8px; color: {COLORS['text_secondary']};
                font-size: 13px; font-weight: 600; padding: 0 20px;
            }}
            QPushButton:hover {{ border-color: {COLORS['text_secondary']}; }}
        """)
        back_btn.clicked.connect(lambda: self._browse_stack.setCurrentIndex(0))
        init_row.addWidget(back_btn)
        self._init_btn = QPushButton("Start Tracking")
        self._init_btn.setFixedHeight(36)
        self._init_btn.setCursor(Qt.PointingHandCursor)
        self._init_btn.setStyleSheet(f"""
            QPushButton {{
                background: {COLORS['accent']}; border: none;
                border-radius: 8px; color: {COLORS['text_on_accent']};
                font-size: 13px; font-weight: 700; padding: 0 20px;
            }}
            QPushButton:hover {{ background: {COLORS.get('accent_hover', COLORS['accent'])}; }}
        """)
        self._init_btn.clicked.connect(self._do_init)
        init_row.addWidget(self._init_btn)
        ip_vl.addLayout(init_row)
        self._browse_stack.addWidget(init_page)

        self._stack.addWidget(self._browse_stack)

        # ── Clone tab ──────────────────────────────────────────────────────
        clone_page = QWidget()
        clone_vl = QVBoxLayout(clone_page)
        clone_vl.setContentsMargins(0, 8, 0, 0)
        clone_vl.setSpacing(14)
        self._clone_vl = clone_vl
        self._stack.addWidget(clone_page)

        self._tab_browse.clicked.connect(lambda: self._switch_tab(0))
        self._tab_clone.clicked.connect(lambda: self._switch_tab(1))
        vl.addWidget(self._stack)

        # ── Repo list section (authenticated only) ─────────────────────────
        self._repo_section = QWidget()
        rs_vl = QVBoxLayout(self._repo_section)
        rs_vl.setContentsMargins(0, 0, 0, 0)
        rs_vl.setSpacing(8)

        self._search_input = QLineEdit()
        self._search_input.setPlaceholderText("Search your repositories…")
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
            f"font-size: 12px; color: {COLORS['text_muted']};"
        )
        rs_vl.addWidget(self._loading_label)

        self._empty_label = QLabel("No repositories found.")
        self._empty_label.setStyleSheet(
            f"font-size: 12px; color: {COLORS['text_muted']};"
        )
        self._empty_label.setWordWrap(True)
        self._empty_label.hide()
        rs_vl.addWidget(self._empty_label)

        # Scroll area for repo rows
        scroll = QScrollArea()
        scroll.setFixedHeight(200)
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setFrameShape(QFrame.NoFrame)
        pal = scroll.palette()
        pal.setColor(QPalette.Window, QColor(COLORS['bg_card']))
        scroll.setPalette(pal)
        scroll.viewport().setPalette(pal)
        scroll.viewport().setAutoFillBackground(True)
        scroll.setStyleSheet(scrollbar_style())

        self._list_widget = QWidget()
        self._list_layout = QVBoxLayout(self._list_widget)
        self._list_layout.setContentsMargins(2, 2, 2, 2)
        self._list_layout.setSpacing(1)
        self._list_layout.setAlignment(Qt.AlignTop)
        lp = self._list_widget.palette()
        lp.setColor(QPalette.Window, QColor(COLORS['bg_card']))
        self._list_widget.setPalette(lp)
        self._list_widget.setAutoFillBackground(True)
        scroll.setWidget(self._list_widget)
        self._list_widget.hide()
        rs_vl.addWidget(scroll)

        clone_vl.addWidget(self._repo_section)

        # ── Separator ─────────────────────────────────────────────────────
        self._sep_widget = QWidget()
        sep_hl = QHBoxLayout(self._sep_widget)
        sep_hl.setContentsMargins(0, 2, 0, 2)
        sep_hl.setSpacing(12)
        _sep_line_style = f"background: {COLORS['border']}; max-height: 1px; border: none;"
        sep_left = QFrame()
        sep_left.setFrameShape(QFrame.HLine)
        sep_left.setStyleSheet(_sep_line_style)
        sep_hl.addWidget(sep_left)
        sep_lbl = QLabel("or enter a URL")
        sep_lbl.setStyleSheet(
            f"font-size: 11px; color: {COLORS['text_muted']};"
        )
        sep_hl.addWidget(sep_lbl)
        sep_right = QFrame()
        sep_right.setFrameShape(QFrame.HLine)
        sep_right.setStyleSheet(_sep_line_style)
        sep_hl.addWidget(sep_right)
        clone_vl.addWidget(self._sep_widget)

        # ── URL input ──────────────────────────────────────────────────────
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
        clone_vl.addWidget(self._url_input)

        # ── Destination folder ──────────────────────────────────────────────
        dest_label = QLabel("Clone to")
        dest_label.setStyleSheet(
            f"font-size: 12px; color: {COLORS['text_muted']};"
        )
        clone_vl.addWidget(dest_label)

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
        browse_btn.setIcon(qta.icon("fa5s.folder-open", color=COLORS['text_secondary']))
        browse_btn.setFixedSize(72, 36)
        browse_btn.setCursor(Qt.PointingHandCursor)
        browse_btn.setStyleSheet(f"""
            QPushButton {{
                background: {COLORS['bg_primary']}; border: 1px solid {COLORS['border']};
                border-radius: 8px; color: {COLORS['text_secondary']};
                font-size: 12px; font-weight: 600;
            }}
            QPushButton:hover {{ border-color: {COLORS['accent']}; color: {COLORS['accent']}; }}
        """)
        browse_btn.clicked.connect(self._pick_dest)
        dest_row.addWidget(browse_btn)
        clone_vl.addLayout(dest_row)

        # ── Error label ────────────────────────────────────────────────────
        self._error_label = QLabel("")
        self._error_label.setStyleSheet(
            f"font-size: 12px; color: {COLORS['danger']};"
        )
        self._error_label.setWordWrap(True)
        self._error_label.hide()
        clone_vl.addWidget(self._error_label)

        # ── Buttons ────────────────────────────────────────────────────────
        btn_row = QHBoxLayout()
        btn_row.setSpacing(8)

        cancel_btn = QPushButton("Cancel")
        cancel_btn.setFixedHeight(36)
        cancel_btn.setCursor(Qt.PointingHandCursor)
        cancel_btn.setStyleSheet(f"""
            QPushButton {{
                background: transparent; border: 1px solid {COLORS['border']};
                border-radius: 8px; color: {COLORS['text_secondary']};
                font-size: 13px; font-weight: 600; padding: 0 20px;
            }}
            QPushButton:hover {{ border-color: {COLORS['text_secondary']}; }}
        """)
        cancel_btn.clicked.connect(self.reject)
        btn_row.addWidget(cancel_btn)

        self._clone_btn = QPushButton("Clone")
        self._clone_btn.setIcon(qta.icon("fa5s.download", color=COLORS['text_on_accent']))
        self._clone_btn.setFixedHeight(36)
        self._clone_btn.setCursor(Qt.PointingHandCursor)
        self._clone_btn.setStyleSheet(f"""
            QPushButton {{
                background: {COLORS['accent']}; border: none;
                border-radius: 8px; color: {COLORS['text_on_accent']};
                font-size: 13px; font-weight: 700; padding: 0 20px;
            }}
            QPushButton:hover {{ background: {COLORS.get('accent_hover', COLORS['accent'])}; }}
            QPushButton:disabled {{ background: {COLORS['border']}; color: {COLORS['text_muted']}; }}
        """)
        self._clone_btn.clicked.connect(self._start_clone)
        btn_row.addWidget(self._clone_btn)
        clone_vl.addLayout(btn_row)

        root.addWidget(card)

        if not self._has_auth:
            self._repo_section.hide()
            self._sep_widget.hide()

    def _switch_tab(self, idx: int):
        self._stack.setCurrentIndex(idx)
        self._tab_browse.setStyleSheet(self._tab_active_style if idx == 0 else self._tab_inactive_style)
        self._tab_clone.setStyleSheet(self._tab_active_style if idx == 1 else self._tab_inactive_style)
        self.adjustSize()

    def _browse_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "Select a git repository", os.path.expanduser("~"))
        if folder:
            self._handle_folder(folder)

    def _handle_folder(self, folder: str):
        if os.path.isdir(os.path.join(folder, ".git")):
            self.cloned.emit(folder)
            self.accept()
        else:
            self._init_folder = folder
            self._init_title.setText(f"'{os.path.basename(folder)}' isn't a git repo yet")
            self._init_desc.setText(f"Would you like to start tracking changes?\n{folder}")
            self._init_status.hide()
            self._init_btn.setEnabled(True)
            self._browse_stack.setCurrentIndex(1)

    def _do_init(self):
        self._init_btn.setEnabled(False)
        self._init_status.setText("Setting up...")
        self._init_status.show()
        import threading
        folder = self._init_folder
        u = self._user
        def _run():
            from core import ops as git_ops
            name = (u.get("name") or u.get("login", "")) if u else ""
            email = u.get("email", "") if u else ""
            ok, err = git_ops.init_repo(folder, name, email)
            self._init_done_sig.emit(ok, err, folder)
        threading.Thread(target=_run, daemon=True).start()

    def _on_init_done(self, ok: bool, err: str, folder: str):
        if ok:
            self.cloned.emit(folder)
            self.accept()
        else:
            self._init_status.setText(f"Failed: {err}")
            self._init_status.setStyleSheet(f"font-size: 12px; color: {COLORS['danger']};")
            self._init_btn.setEnabled(True)

    def _drop_drag_enter(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
        else:
            event.ignore()

    def _drop_drop(self, event):
        for url in event.mimeData().urls():
            path = url.toLocalFile()
            if path and os.path.isdir(path):
                self._handle_folder(path)
                return

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

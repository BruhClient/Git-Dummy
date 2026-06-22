from __future__ import annotations

import configparser
import os
import re
import subprocess
import threading

import qtawesome as qta

from PyQt5.QtCore import Qt, QSize, pyqtSignal
from PyQt5.QtGui import QPainter, QColor, QPen, QBrush
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QFileDialog, QScrollArea, QFrame, QSizePolicy, QGridLayout,
)
from styles.theme import COLORS, card_shadow
from core import repo_store
from ui.dialogs import alert
from ui.dialogs.clone_dialog import CloneDialog


def _remote_owner(repo_path: str) -> str:
    """Get the GitHub owner login by reading .git/config directly — no subprocess."""
    try:
        cfg = configparser.ConfigParser()
        cfg.read(os.path.join(repo_path, ".git", "config"), encoding="utf-8")
        url = cfg.get('remote "origin"', "url", fallback="")
        if url:
            m = re.search(r"github\.com[:/]([^/]+)/", url)
            return m.group(1) if m else ""
    except Exception:
        pass
    return ""


def _remote_url(repo_path: str) -> str:
    """Return the origin remote URL for a local repo, or '' if not found."""
    try:
        cfg = configparser.ConfigParser()
        cfg.read(os.path.join(repo_path, ".git", "config"), encoding="utf-8")
        return cfg.get('remote "origin"', "url", fallback="")
    except Exception:
        return ""


def _remote_repo(repo_path: str) -> str:
    """Get the GitHub repo name from .git/config origin URL."""
    try:
        cfg = configparser.ConfigParser()
        cfg.read(os.path.join(repo_path, ".git", "config"), encoding="utf-8")
        url = cfg.get('remote "origin"', "url", fallback="")
        if url:
            m = re.search(r"github\.com[:/][^/]+/([^/]+?)(?:\.git)?$", url)
            return m.group(1) if m else ""
    except Exception:
        pass
    return ""


class _RoleBadge(QLabel):
    """Pill badge showing the current user's role in a repo."""

    _role_ready = pyqtSignal(str)

    _LABELS = {
        "owner": "Owner",
        "admin": "Admin",
        "collaborator": "Collaborator",
        "viewer": "Viewer",
    }

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        self._role_ready.connect(self._apply)

    def start(self, owner: str, repo: str, login: str, token: str):
        if login and login == owner:
            self._apply("owner")
        elif login and token and owner and repo:
            threading.Thread(
                target=self._fetch, args=(owner, repo, login, token), daemon=True
            ).start()

    def _fetch(self, owner: str, repo: str, login: str, token: str):
        try:
            import requests
            r = requests.get(
                f"https://api.github.com/repos/{owner}/{repo}/collaborators/{login}/permission",
                headers={"Authorization": f"Bearer {token}",
                         "Accept": "application/vnd.github+json"},
                timeout=8,
            )
            if r.status_code == 200:
                perm = r.json().get("permission", "none")
                if perm == "admin":
                    self._role_ready.emit("admin")
                elif perm in ("write", "maintain"):
                    self._role_ready.emit("collaborator")
                else:
                    self._role_ready.emit("viewer")
            elif r.status_code in (403, 404):
                self._role_ready.emit("viewer")
        except Exception:
            pass

    def _apply(self, role: str):
        if role not in self._LABELS:
            return
        self.setText(self._LABELS[role])
        color = COLORS.get("warning", "#f59e0b") if role == "viewer" else COLORS["text_muted"]
        self.setStyleSheet(
            f"background: transparent; color: {color}; font-size: 12px;"
        )
        self.show()


# ── Drop zone ─────────────────────────────────────────────────────────────────

class DropZone(QWidget):
    browse_clicked = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("dropZone")
        self.setMinimumHeight(160)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self._active = False

        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignCenter)
        layout.setSpacing(8)

        self._icon = QLabel()
        self._icon.setPixmap(qta.icon("fa5s.upload", color=COLORS["text_muted"]).pixmap(32, 32))
        self._icon.setAlignment(Qt.AlignCenter)
        self._icon.setStyleSheet("background: transparent;")
        layout.addWidget(self._icon)

        self._title = QLabel("Drop a project folder here")
        self._title.setAlignment(Qt.AlignCenter)
        self._title.setStyleSheet(
            f"background: transparent; font-size: 15px; font-weight: 600; color: {COLORS['text_secondary']};"
        )
        layout.addWidget(self._title)

        sub_row = QHBoxLayout()
        sub_row.setAlignment(Qt.AlignCenter)
        sub_row.setSpacing(6)
        sub = QLabel("or")
        sub.setStyleSheet(f"background: transparent; font-size: 13px; color: {COLORS['text_muted']};")
        sub_row.addWidget(sub)

        browse = QPushButton("browse folder")
        browse.setCursor(Qt.PointingHandCursor)
        browse.setStyleSheet(f"""
            QPushButton {{
                background: transparent; border: none;
                color: {COLORS['accent']}; font-size: 13px; padding: 0;
            }}
            QPushButton:hover {{ color: {COLORS['accent_hover']}; }}
        """)
        browse.clicked.connect(self.browse_clicked.emit)
        sub_row.addWidget(browse)
        layout.addLayout(sub_row)

    def set_active(self, active: bool):
        self._active = active
        accent = COLORS["accent"]
        muted = COLORS["text_muted"]
        secondary = COLORS["text_secondary"]
        self._icon.setStyleSheet(
            f"background: transparent; font-size: 32px; color: {accent if active else muted};"
        )
        self._title.setStyleSheet(
            f"background: transparent; font-size: 15px; font-weight: 600; "
            f"color: {accent if active else secondary};"
        )
        self.update()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        color = COLORS["accent"] if self._active else COLORS["border"]
        pen = QPen(QColor(color), 2, Qt.DashLine)
        pen.setDashPattern([6, 4])
        p.setPen(pen)
        p.setBrush(QBrush(QColor(COLORS["accent_dim"])) if self._active else QBrush(Qt.NoBrush))
        p.drawRoundedRect(1, 1, self.width() - 2, self.height() - 2, 10, 10)
        p.end()


# ── Cards ─────────────────────────────────────────────────────────────────────

class RepoCard(QWidget):
    open_requested   = pyqtSignal(str)
    remove_requested = pyqtSignal(str)
    _stats_ready     = pyqtSignal(int, int, int, int)

    def __init__(self, repo_path: str, user: dict = None, parent=None):
        super().__init__(parent)
        self._path = repo_path
        self.setObjectName("repoCard")
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setCursor(Qt.PointingHandCursor)
        self.setFixedHeight(120)
        self._hovered = False
        self._apply_style(False)
        card_shadow(self)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(0)

        top_row = QHBoxLayout()
        top_row.setSpacing(0)
        top_row.setContentsMargins(0, 0, 0, 0)
        name_label = QLabel(os.path.basename(self._path))
        name_label.setStyleSheet(
            f"font-size: 15px; font-weight: 700;"
            f" color: {COLORS['text_primary']};"
        )
        name_label.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        top_row.addWidget(name_label)
        top_row.addStretch()

        self._rm_btn = QPushButton()
        self._rm_btn.setIcon(qta.icon("fa5s.times", color=COLORS["text_muted"]))
        self._rm_btn.setIconSize(QSize(10, 10))
        self._rm_btn.setFixedSize(24, 24)
        self._rm_btn.setCursor(Qt.PointingHandCursor)
        self._rm_btn.setStyleSheet(
            f"QPushButton {{ background: transparent; border: none; }}"
            f"QPushButton:hover {{ background: {COLORS['bg_hover']}; border-radius: 4px; }}"
        )
        self._rm_btn.clicked.connect(lambda: self.remove_requested.emit(self._path))
        self._rm_btn.hide()
        top_row.addWidget(self._rm_btn)
        layout.addLayout(top_row)

        owner = _remote_owner(repo_path)
        repo  = _remote_repo(repo_path)
        owner_label = QLabel(f"owned by {owner}" if owner else "local project")
        owner_label.setStyleSheet(
            f"font-size: 11px; color: {COLORS['text_muted']};"
        )
        owner_label.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        layout.addWidget(owner_label)

        layout.addStretch()

        self._stats_row = QHBoxLayout()
        self._stats_row.setSpacing(12)
        self._stats_row.setContentsMargins(0, 0, 0, 0)
        self._stats_row.addStretch()
        layout.addLayout(self._stats_row)

        layout.addSpacing(6)

        bottom_row = QHBoxLayout()
        bottom_row.setSpacing(0)
        bottom_row.setContentsMargins(0, 0, 0, 0)
        bottom_row.addStretch()
        self._role_badge = _RoleBadge()
        self._role_badge.hide()
        bottom_row.addWidget(self._role_badge)
        layout.addLayout(bottom_row)

        if owner and repo:
            token = (user or {}).get("access_token", "")
            login = (user or {}).get("login", "")
            self._role_badge.start(owner, repo, login, token)

        self._stats_ready.connect(self._on_stats)
        threading.Thread(target=self._fetch_stats,
                         args=(repo_path, owner, repo, (user or {}).get("access_token", "")),
                         daemon=True).start()

    def _fetch_stats(self, path: str, owner: str, repo: str, token: str):
        commits = 0
        try:
            r = subprocess.run(["git", "rev-list", "--count", "HEAD"],
                               cwd=path, capture_output=True, text=True, timeout=5)
            if r.returncode == 0:
                commits = int(r.stdout.strip())
        except Exception:
            pass
        stars = watchers = forks = -1
        if owner and repo and token:
            try:
                import requests
                r = requests.get(f"https://api.github.com/repos/{owner}/{repo}",
                                 headers={"Authorization": f"Bearer {token}",
                                          "Accept": "application/vnd.github+json"},
                                 timeout=8)
                if r.status_code == 200:
                    d = r.json()
                    stars = d.get("stargazers_count", 0)
                    watchers = d.get("subscribers_count", 0)
                    forks = d.get("forks_count", 0)
            except Exception:
                pass
        try:
            self._stats_ready.emit(stars, watchers, forks, commits)
        except RuntimeError:
            pass

    def _on_stats(self, stars: int, watchers: int, forks: int, commits: int):
        while self._stats_row.count() > 1:
            item = self._stats_row.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        items = []
        if stars >= 0:
            items.append(("fa5s.star", str(stars)))
        if watchers >= 0:
            items.append(("fa5s.eye", str(watchers)))
        if forks >= 0:
            items.append(("fa5s.code-branch", str(forks)))
        items.append(("fa5s.history", f"{commits}"))
        pos = 0
        for icon_name, text in items:
            w = QWidget()
            w.setAttribute(Qt.WA_TransparentForMouseEvents, True)
            h = QHBoxLayout(w)
            h.setContentsMargins(0, 0, 0, 0)
            h.setSpacing(4)
            ic = QLabel()
            ic.setPixmap(qta.icon(icon_name, color=COLORS["text_muted"]).pixmap(12, 12))
            ic.setFixedSize(12, 12)
            h.addWidget(ic)
            lbl = QLabel(text)
            lbl.setStyleSheet(f"font-size: 11px; color: {COLORS['text_muted']};")
            h.addWidget(lbl)
            self._stats_row.insertWidget(pos, w)
            pos += 1

    def _apply_style(self, hovered: bool):
        border = COLORS['accent'] if hovered else COLORS['border']
        bg = COLORS['bg_hover'] if hovered else COLORS['bg_card']
        self.setStyleSheet(
            f"#repoCard {{ background: {bg}; border: 1px solid {border}; border-radius: 12px; }}"
            f"#repoCard * {{ background: transparent; border: none; }}"
        )

    def enterEvent(self, _):
        self._hovered = True
        self._rm_btn.show()
        self._apply_style(True)

    def leaveEvent(self, _):
        self._hovered = False
        self._rm_btn.hide()
        self._apply_style(False)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.open_requested.emit(self._path)
        super().mousePressEvent(event)


class MissingRepoCard(QWidget):
    """Card shown when a saved repo path no longer exists."""

    locate_requested = pyqtSignal(str)   # old path
    remove_requested = pyqtSignal(str)

    def __init__(self, repo_path: str, parent=None):
        super().__init__(parent)
        self._path = repo_path
        self.setObjectName("missingCard")
        self.setStyleSheet(f"""
            #missingCard {{
                background-color: {COLORS['bg_card']};
                border: 1px solid {COLORS['danger_border']};
                border-radius: 8px;
            }}
        """)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(20, 14, 16, 14)
        layout.setSpacing(14)

        icon = QLabel()
        icon.setFixedWidth(28)
        icon.setPixmap(qta.icon("fa5s.exclamation-triangle", color=COLORS["warning"]).pixmap(20, 20))
        icon.setStyleSheet("background: transparent;")
        layout.addWidget(icon)

        info = QVBoxLayout()
        info.setSpacing(2)
        name_label = QLabel(os.path.basename(self._path))
        name_label.setStyleSheet(
            f"background: transparent; font-size: 14px; font-weight: 600; color: {COLORS['text_muted']};"
        )
        path_label = QLabel(self._path)
        path_label.setStyleSheet(f"background: transparent; font-size: 12px; color: {COLORS['text_muted']};")
        info.addWidget(name_label)
        info.addWidget(path_label)
        layout.addLayout(info)
        layout.addStretch()

        missing_badge = QLabel(" not found ")
        missing_badge.setStyleSheet(f"""
            font-size: 11px; font-weight: 600;            color: {COLORS['warning']}; background: {COLORS['warning_dim']};
            border-radius: 4px; padding: 2px 8px;
        """)
        layout.addWidget(missing_badge)

        locate_btn = QPushButton("Find it →")
        locate_btn.setFixedSize(90, 34)
        locate_btn.setCursor(Qt.PointingHandCursor)
        locate_btn.setStyleSheet(f"""
            QPushButton {{
                background: transparent; border: 1px solid {COLORS['border']};
                border-radius: 6px; color: {COLORS['text_secondary']};
                font-size: 13px; font-weight: 500;
            }}
            QPushButton:hover {{
                background: {COLORS['bg_hover']}; color: {COLORS['text_primary']};
            }}
        """)
        locate_btn.clicked.connect(lambda: self.locate_requested.emit(self._path))
        layout.addWidget(locate_btn)

        rm_btn = QPushButton()
        rm_btn.setIcon(qta.icon("fa5s.times", color=COLORS["text_muted"]))
        rm_btn.setIconSize(QSize(12, 12))
        rm_btn.setToolTip("Remove from tracking")
        rm_btn.setFixedSize(34, 34)
        rm_btn.setCursor(Qt.PointingHandCursor)
        rm_btn.setStyleSheet(f"""
            QPushButton {{
                background: transparent; border: 1px solid {COLORS['border']};
                border-radius: 6px; color: {COLORS['text_muted']}; font-size: 13px;
            }}
            QPushButton:hover {{
                background: {COLORS['danger_dim']}; border-color: {COLORS['danger']};
                color: {COLORS['danger']};
            }}
        """)
        rm_btn.clicked.connect(lambda: self.remove_requested.emit(self._path))
        layout.addWidget(rm_btn)



# ── Repo page ─────────────────────────────────────────────────────────────────

class RepoPage(QWidget):
    repo_selected = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._repos: list[str] = []    # only valid (existing) paths
        self._missing: list[str] = []  # paths that no longer exist
        self._user: dict | None = None
        self.setAcceptDrops(True)
        self._setup_ui()

    def set_user(self, user: dict):
        self._user = user
        self._repos = []
        self._missing = []
        self._load_saved()
        self._refresh_cards()

    # ── UI ────────────────────────────────────────────────────────────────────

    def _setup_ui(self):
        self.setStyleSheet(f"background: {COLORS['bg_primary']};")
        root = QVBoxLayout(self)
        root.setContentsMargins(24, 20, 24, 20)
        root.setSpacing(0)

        header_row = QHBoxLayout()
        header_row.setSpacing(12)

        title = QLabel("Your Projects")
        title.setStyleSheet(
            f"background: transparent; font-size: 22px; font-weight: 700; color: {COLORS['text_primary']};"
        )
        header_row.addWidget(title)
        header_row.addStretch()

        track_btn = QPushButton("  Track a Project")
        track_btn.setIcon(qta.icon("mdi.connection", color=COLORS["text_secondary"]))
        track_btn.setIconSize(QSize(12, 12))
        track_btn.setFixedHeight(36)
        track_btn.setCursor(Qt.PointingHandCursor)
        track_btn.setStyleSheet(f"""
            QPushButton {{
                background: transparent; border: 1px solid {COLORS['border']};
                border-radius: 8px; color: {COLORS['text_secondary']};
                font-size: 13px; font-weight: 600; padding: 0 14px;
            }}
            QPushButton:hover {{ border-color: {COLORS['accent']}; color: {COLORS['accent']}; }}
        """)
        track_btn.clicked.connect(self._open_clone_dialog)
        header_row.addWidget(track_btn)

        info_btn = QPushButton()
        info_btn.setIcon(qta.icon("mdi.help-circle-outline", color=COLORS["text_secondary"]))
        info_btn.setIconSize(QSize(18, 18))
        info_btn.setFixedSize(36, 36)
        info_btn.setCursor(Qt.PointingHandCursor)
        info_btn.setStyleSheet(f"""
            QPushButton {{
                background: transparent; border: 1px solid {COLORS['border']};
                border-radius: 18px;
            }}
            QPushButton:hover {{ border-color: {COLORS['accent']}; }}
        """)
        info_btn.clicked.connect(self._open_instructions)
        header_row.addWidget(info_btn)

        root.addLayout(header_row)
        root.addSpacing(12)

        self._section_label = QLabel(self)
        self._section_label.setFixedSize(0, 0)
        self._section_label.hide()

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setStyleSheet("background: transparent;")

        self._cards_container = QWidget()
        self._cards_container.setStyleSheet("background: transparent;")
        self._cards_layout = QGridLayout(self._cards_container)
        self._cards_layout.setContentsMargins(0, 0, 0, 0)
        self._cards_layout.setHorizontalSpacing(8)
        self._cards_layout.setVerticalSpacing(8)
        self._cards_layout.setAlignment(Qt.AlignTop | Qt.AlignLeft)

        scroll.setWidget(self._cards_container)
        scroll.viewport().setStyleSheet("background: transparent;")
        root.addWidget(scroll)

    # ── persistence ───────────────────────────────────────────────────────────

    def _load_saved(self):
        login = self._user.get("login", "") if self._user else ""
        if not login:
            return
        saved = repo_store.load(login)
        for path in saved:
            if os.path.isdir(os.path.join(path, ".git")):
                if path not in self._repos:
                    self._repos.append(path)
            elif path not in self._missing:
                self._missing.append(path)
        self._refresh_cards()

    def _validate_paths(self):
        changed = False
        for path in list(self._repos):
            if not os.path.isdir(os.path.join(path, ".git")):
                self._repos.remove(path)
                if path not in self._missing:
                    self._missing.append(path)
                changed = True
        for path in list(self._missing):
            if os.path.isdir(os.path.join(path, ".git")):
                self._missing.remove(path)
                if path not in self._repos:
                    self._repos.append(path)
                changed = True
        if changed:
            self._persist()
            self._refresh_cards()

    def showEvent(self, event):
        super().showEvent(event)
        self._validate_paths()

    def _persist(self):
        login = self._user.get("login", "") if self._user else ""
        if login:
            repo_store.save(login, self._repos + self._missing)

    # ── drag & drop ───────────────────────────────────────────────────────────

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
        else:
            event.ignore()

    def dragMoveEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dragLeaveEvent(self, _):
        pass

    def dropEvent(self, event):
        for url in event.mimeData().urls():
            path = url.toLocalFile()
            if path:
                self._handle_path(path)
        event.acceptProposedAction()

    # ── public ────────────────────────────────────────────────────────────────

    def add_repo(self, path: str):
        if path not in self._repos:
            self._repos.append(path)
            if path in self._missing:
                self._missing.remove(path)
            self._persist()
            self._refresh_cards()

    def remove_repo(self, path: str):
        for lst in (self._repos, self._missing):
            if path in lst:
                lst.remove(path)
        self._persist()
        self._refresh_cards()

    # ── internals ────────────────────────────────────────────────────────────

    def _open_instructions(self):
        from ui.dialogs import InstructionsDialog
        InstructionsDialog(self).exec_()

    def _open_clone_dialog(self):
        dlg = CloneDialog(self, user=self._user, existing_repos=self._repos)
        dlg.cloned.connect(self._on_cloned)
        dlg.exec_()

    def _on_cloned(self, path: str):
        self.add_repo(path)
        self.repo_selected.emit(path)

    def _pick_folder(self):
        folder = QFileDialog.getExistingDirectory(
            self, "Select a git repository folder", os.path.expanduser("~")
        )
        if folder:
            self._handle_path(folder)

    def _handle_path(self, path: str):
        """Decide what to do with a dropped/browsed path."""
        if path in self._repos:
            self.repo_selected.emit(path)  # already tracked — just navigate
            return

        git_dir = os.path.join(path, ".git")
        if os.path.isdir(git_dir):
            self.add_repo(path)
            self.repo_selected.emit(path)
        else:
            self._prompt_init(path)

    def _prompt_init(self, path: str):
        from ui.dialogs.init_dialog import InitDialog
        dlg = InitDialog(
            folder_path=path,
            user=self._user,
            repo_added=self.add_repo,
            parent=self,
        )
        dlg.exec_()
        # Navigate after dialog closes if init succeeded
        if path in self._repos:
            self.repo_selected.emit(path)

    def _locate_missing(self, old_path: str):
        """Let user point to the new location of a missing repo."""
        folder = QFileDialog.getExistingDirectory(
            self,
            f"Locate '{os.path.basename(old_path)}'",
            os.path.expanduser("~"),
        )
        if not folder:
            return
        if not os.path.isdir(os.path.join(folder, ".git")):
            alert(self, "Folder not recognised",
                  f"This doesn't look like a tracked project folder:\n{folder}")
            return
        # Replace old path with new one and navigate immediately
        if old_path in self._missing:
            self._missing.remove(old_path)
        if folder not in self._repos:
            self._repos.append(folder)
        self._persist()
        self._refresh_cards()
        self.repo_selected.emit(folder)

    def _refresh_cards(self):
        while self._cards_layout.count():
            item = self._cards_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        total = len(self._repos) + len(self._missing)
        self._section_label.setVisible(total > 0)

        cols = 3
        idx = 0

        for path in self._missing:
            card = MissingRepoCard(path)
            card.locate_requested.connect(self._locate_missing)
            card.remove_requested.connect(self.remove_repo)
            self._cards_layout.addWidget(card, idx // cols, idx % cols)
            idx += 1

        for path in self._repos:
            card = RepoCard(path, user=self._user)
            card.open_requested.connect(self.repo_selected.emit)
            card.remove_requested.connect(self.remove_repo)
            self._cards_layout.addWidget(card, idx // cols, idx % cols)
            idx += 1

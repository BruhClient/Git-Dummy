from __future__ import annotations

import configparser
import os
import re
import threading

from PyQt5.QtCore import Qt, pyqtSignal, QObject, QThread
from PyQt5.QtGui import QPainter, QColor, QPen, QBrush, QPainterPath, QPixmap, QFont
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QFileDialog, QScrollArea, QFrame, QSizePolicy, QMessageBox,
    QLineEdit, QDialog, QGraphicsOpacityEffect,
)
from styles.theme import COLORS, BTN_PRIMARY
from core import repo_store


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


class _OwnerAvatar(QWidget):
    """Small circular avatar showing the repo owner."""

    _pixmap_ready = pyqtSignal()
    SIZE = 28

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(self.SIZE, self.SIZE)
        self._pixmap: QPixmap | None = None
        self._initials = ""
        self._pixmap_ready.connect(self.update)

    def set_owner(self, login: str, token: str):
        self._initials = login[:2].upper() if login else ""
        self.update()
        if login and token:
            threading.Thread(target=self._fetch, args=(login, token), daemon=True).start()

    def _fetch(self, login: str, token: str):
        try:
            import requests
            r = requests.get(
                f"https://api.github.com/users/{login}",
                headers={"Authorization": f"Bearer {token}",
                         "Accept": "application/vnd.github+json"},
                timeout=8,
            )
            if r.status_code == 200:
                avatar_url = r.json().get("avatar_url", "")
                if avatar_url:
                    img = requests.get(avatar_url, timeout=8)
                    if img.status_code == 200:
                        pm = QPixmap()
                        pm.loadFromData(img.content)
                        if not pm.isNull():
                            s = self.SIZE
                            self._pixmap = pm.scaled(s, s, Qt.KeepAspectRatioByExpanding,
                                                     Qt.SmoothTransformation)
                            self._pixmap_ready.emit()
        except Exception:
            pass

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        s = self.SIZE
        clip = QPainterPath()
        clip.addEllipse(0, 0, s, s)
        p.setClipPath(clip)
        if self._pixmap:
            src = self._pixmap
            x = (src.width() - s) // 2
            y = (src.height() - s) // 2
            p.drawPixmap(0, 0, src, x, y, s, s)
        else:
            p.setBrush(QBrush(QColor(COLORS["accent_dim"])))
            p.setPen(Qt.NoPen)
            p.drawEllipse(0, 0, s, s)
            if self._initials:
                p.setClipping(False)
                p.setPen(QPen(QColor(COLORS["accent"])))
                p.setFont(QFont("Inter", s // 4, QFont.Bold))
                p.drawText(self.rect(), Qt.AlignCenter, self._initials)
        p.setClipping(False)
        p.setBrush(Qt.NoBrush)
        p.setPen(QPen(QColor(COLORS["border"]), 1))
        p.drawEllipse(0, 0, s, s)
        p.end()


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

        self._icon = QLabel("⬇")
        self._icon.setAlignment(Qt.AlignCenter)
        self._icon.setStyleSheet(f"background: transparent; font-size: 32px; color: {COLORS['text_muted']};")
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

    def __init__(self, repo_path: str, user: dict = None, parent=None):
        super().__init__(parent)
        self._path = repo_path
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setCursor(Qt.PointingHandCursor)
        self.setFixedHeight(56)
        self._apply_style(False)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(16, 0, 12, 0)
        layout.setSpacing(12)

        info = QVBoxLayout()
        info.setSpacing(2)
        info.setAlignment(Qt.AlignVCenter)

        name_label = QLabel(os.path.basename(self._path))
        name_label.setStyleSheet(
            f"background: transparent; font-size: 14px; font-weight: 600; color: {COLORS['text_primary']};"
        )
        name_label.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        info.addWidget(name_label)
        layout.addLayout(info)
        layout.addStretch()

        # Owner avatar + name (right side, always visible when remote exists)
        self._avatar = _OwnerAvatar()
        self._avatar.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        self._avatar.hide()

        self._owner_label = QLabel("")
        self._owner_label.setStyleSheet(
            f"background: transparent; font-size: 12px; color: {COLORS['text_muted']};"
        )
        self._owner_label.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        self._owner_label.hide()

        layout.addWidget(self._avatar)
        layout.addWidget(self._owner_label)

        owner = _remote_owner(repo_path)
        if owner:
            token = (user or {}).get("access_token", "")
            self._owner_label.setText(owner)
            self._owner_label.show()
            self._avatar.show()
            self._avatar.set_owner(owner, token)

        self._rm_btn = QPushButton("✕")
        self._rm_btn.setFixedSize(28, 28)
        self._rm_btn.setCursor(Qt.PointingHandCursor)
        self._rm_btn.setStyleSheet(f"""
            QPushButton {{
                background: transparent; border: none;
                color: {COLORS['text_muted']}; font-size: 12px;
            }}
            QPushButton:hover {{ color: {COLORS['danger']}; }}
        """)
        self._rm_btn.clicked.connect(lambda: self.remove_requested.emit(self._path))
        layout.addWidget(self._rm_btn)

    def _apply_style(self, hovered: bool):
        bg = COLORS['bg_hover'] if hovered else "transparent"
        self.setStyleSheet(f"background: {bg}; border-radius: 8px;")

    def enterEvent(self, _):
        self._apply_style(True)

    def leaveEvent(self, _):
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
                border: 1px solid #4a2020;
                border-radius: 8px;
            }}
        """)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(20, 14, 16, 14)
        layout.setSpacing(14)

        icon = QLabel("⚠")
        icon.setFixedWidth(28)
        icon.setStyleSheet(f"background: transparent; font-size: 18px; color: {COLORS['warning']};")
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
            font-size: 11px; font-weight: 600;
            color: {COLORS['warning']}; background: #2d2010;
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

        rm_btn = QPushButton("✕")
        rm_btn.setToolTip("Remove from tracking")
        rm_btn.setFixedSize(34, 34)
        rm_btn.setCursor(Qt.PointingHandCursor)
        rm_btn.setStyleSheet(f"""
            QPushButton {{
                background: transparent; border: 1px solid {COLORS['border']};
                border-radius: 6px; color: {COLORS['text_muted']}; font-size: 13px;
            }}
            QPushButton:hover {{
                background: #2d1515; border-color: {COLORS['danger']};
                color: {COLORS['danger']};
            }}
        """)
        rm_btn.clicked.connect(lambda: self.remove_requested.emit(self._path))
        layout.addWidget(rm_btn)


# ── Clone dialog ──────────────────────────────────────────────────────────────

class _CloneWorker(QObject):
    finished = pyqtSignal(bool, str, str)   # ok, error, cloned_path

    def __init__(self, url: str, dest: str):
        super().__init__()
        self._url  = url
        self._dest = dest

    def run(self):
        from core.git_ops import clone_repo
        ok, err, path = clone_repo(self._url, self._dest)
        self.finished.emit(ok, err, path)


class CloneDialog(QDialog):
    """Small dialog to clone a remote repo into a chosen folder."""

    cloned = pyqtSignal(str)   # emits the cloned repo path on success

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowFlags(Qt.Dialog | Qt.FramelessWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setFixedWidth(440)
        self._thread = None
        self._worker = None
        self._dest   = os.path.expanduser("~")
        self._setup_ui()

    def _setup_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)

        card = QWidget()
        card.setStyleSheet(f"""
            background: {COLORS['bg_card']};
            border: 1px solid {COLORS['border']};
            border-radius: 12px;
        """)
        vl = QVBoxLayout(card)
        vl.setContentsMargins(24, 24, 24, 24)
        vl.setSpacing(16)

        title = QLabel("Connect to a repo")
        title.setStyleSheet(f"font-size: 16px; font-weight: 700; color: {COLORS['text_primary']}; background: transparent;")
        vl.addWidget(title)

        # URL input
        url_label = QLabel("Repository URL")
        url_label.setStyleSheet(f"font-size: 12px; color: {COLORS['text_muted']}; background: transparent;")
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
        vl.addWidget(self._url_input)

        # Destination folder
        dest_label = QLabel("Save to folder")
        dest_label.setStyleSheet(f"font-size: 12px; color: {COLORS['text_muted']}; background: transparent;")
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
                font-size: 12px; font-weight: 600;
            }}
            QPushButton:hover {{ border-color: {COLORS['accent']}; color: {COLORS['accent']}; }}
        """)
        browse_btn.clicked.connect(self._pick_dest)
        dest_row.addWidget(browse_btn)
        vl.addLayout(dest_row)

        self._error_label = QLabel("")
        self._error_label.setStyleSheet(f"font-size: 12px; color: {COLORS['danger']}; background: transparent;")
        self._error_label.hide()
        vl.addWidget(self._error_label)

        # Buttons
        btn_row = QHBoxLayout()
        btn_row.setSpacing(8)

        cancel_btn = QPushButton("Cancel")
        cancel_btn.setFixedHeight(40)
        cancel_btn.setCursor(Qt.PointingHandCursor)
        cancel_btn.setStyleSheet(f"""
            QPushButton {{
                background: transparent; border: 1px solid {COLORS['border']};
                border-radius: 8px; color: {COLORS['text_secondary']};
                font-size: 13px; font-weight: 600;
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
                border-radius: 8px; color: white;
                font-size: 13px; font-weight: 700;
            }}
            QPushButton:hover {{ background: {COLORS.get('accent_hover', COLORS['accent'])}; }}
            QPushButton:disabled {{ background: {COLORS['border']}; color: {COLORS['text_muted']}; }}
        """)
        self._clone_btn.clicked.connect(self._start_clone)
        btn_row.addWidget(self._clone_btn)
        vl.addLayout(btn_row)

        root.addWidget(card)

    def _pick_dest(self):
        folder = QFileDialog.getExistingDirectory(self, "Choose parent folder", self._dest)
        if folder:
            self._dest = folder
            self._dest_label.setText(folder)

    def _start_clone(self):
        url = self._url_input.text().strip()
        if not url:
            self._show_error("Please enter a repository URL.")
            return
        self._error_label.hide()
        self._clone_btn.setEnabled(False)
        self._clone_btn.setText("Cloning…")

        self._thread = QThread()
        self._worker = _CloneWorker(url, self._dest)
        self._worker.moveToThread(self._thread)
        self._thread.started.connect(self._worker.run)
        self._worker.finished.connect(self._on_done)
        self._worker.finished.connect(self._thread.quit)
        self._thread.finished.connect(self._on_thread_done)
        self._thread.start()

    def _on_done(self, ok: bool, err: str, path: str):
        if ok:
            self.cloned.emit(path)
            self.accept()
        else:
            self._show_error(err[:160] if err else "Clone failed.")
            self._clone_btn.setEnabled(True)
            self._clone_btn.setText("Clone")

    def _on_thread_done(self):
        self._thread = None
        self._worker = None

    def _show_error(self, msg: str):
        self._error_label.setText(msg)
        self._error_label.show()
        self.adjustSize()


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
        self._load_saved()

    def set_user(self, user: dict):
        self._user = user
        self._refresh_cards()

    # ── UI ────────────────────────────────────────────────────────────────────

    def _setup_ui(self):
        self.setStyleSheet(f"background: {COLORS['bg_primary']};")
        root = QVBoxLayout(self)
        root.setContentsMargins(40, 32, 40, 32)
        root.setSpacing(0)

        header_row = QHBoxLayout()
        header_row.setSpacing(12)

        title = QLabel("Your Projects")
        title.setStyleSheet(
            f"background: transparent; font-size: 22px; font-weight: 700; color: {COLORS['text_primary']};"
        )
        header_row.addWidget(title)
        header_row.addStretch()

        clone_btn = QPushButton("⇩  Connect to repo")
        clone_btn.setFixedHeight(36)
        clone_btn.setCursor(Qt.PointingHandCursor)
        clone_btn.setStyleSheet(f"""
            QPushButton {{
                background: transparent; border: 1px solid {COLORS['border']};
                border-radius: 8px; color: {COLORS['text_secondary']};
                font-size: 13px; font-weight: 600; padding: 0 14px;
            }}
            QPushButton:hover {{ border-color: {COLORS['accent']}; color: {COLORS['accent']}; }}
        """)
        clone_btn.clicked.connect(self._open_clone_dialog)
        header_row.addWidget(clone_btn)
        root.addLayout(header_row)
        root.addSpacing(4)

        sub = QLabel("Drop a project folder below, or browse to add it.")
        sub.setStyleSheet(f"background: transparent; font-size: 13px; color: {COLORS['text_muted']};")
        root.addWidget(sub)
        root.addSpacing(20)

        self._drop_zone = DropZone()
        self._drop_zone.browse_clicked.connect(self._pick_folder)
        root.addWidget(self._drop_zone)
        root.addSpacing(28)

        self._section_label = QLabel("ADDED PROJECTS")
        self._section_label.setStyleSheet(
            f"background: transparent; font-size: 10px; font-weight: 600; color: {COLORS['text_muted']}; letter-spacing: 0.08em;"
        )
        self._section_label.hide()
        root.addWidget(self._section_label)
        root.addSpacing(10)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setStyleSheet("background: transparent;")

        self._cards_container = QWidget()
        self._cards_container.setStyleSheet("background: transparent;")
        self._cards_layout = QVBoxLayout(self._cards_container)
        self._cards_layout.setContentsMargins(0, 0, 0, 0)
        self._cards_layout.setSpacing(2)
        self._cards_layout.addStretch()

        scroll.setWidget(self._cards_container)
        scroll.viewport().setStyleSheet("background: transparent;")
        root.addWidget(scroll)

    # ── persistence ───────────────────────────────────────────────────────────

    def _load_saved(self):
        saved = repo_store.load()
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
        repo_store.save(self._repos + self._missing)

    # ── drag & drop ───────────────────────────────────────────────────────────

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
            self._drop_zone.set_active(True)
        else:
            event.ignore()

    def dragMoveEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dragLeaveEvent(self, _):
        self._drop_zone.set_active(False)

    def dropEvent(self, event):
        self._drop_zone.set_active(False)
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

    def _open_clone_dialog(self):
        dlg = CloneDialog(self)
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
        from ui.init_dialog import InitDialog
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
            QMessageBox.warning(
                self, "Folder not recognised",
                f"This doesn't look like a tracked project folder:\n{folder}",
            )
            return
        # Replace old path with new one and navigate immediately
        if old_path in self._missing:
            self._missing.remove(old_path)
        self._repos.append(folder)
        self._persist()
        self._refresh_cards()
        self.repo_selected.emit(folder)

    def _refresh_cards(self):
        # Clear all card widgets (keep trailing stretch)
        while self._cards_layout.count() > 1:
            item = self._cards_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        total = len(self._repos) + len(self._missing)
        self._section_label.setVisible(total > 0)

        insert_pos = 0

        # Missing cards first (they need attention)
        for path in self._missing:
            card = MissingRepoCard(path)
            card.locate_requested.connect(self._locate_missing)
            card.remove_requested.connect(self.remove_repo)
            self._cards_layout.insertWidget(insert_pos, card)
            insert_pos += 1

        # Valid cards
        for path in self._repos:
            card = RepoCard(path, user=self._user)
            card.open_requested.connect(self.repo_selected.emit)
            card.remove_requested.connect(self.remove_repo)
            self._cards_layout.insertWidget(insert_pos, card)
            insert_pos += 1

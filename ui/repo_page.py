from __future__ import annotations

import os

from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtGui import QPainter, QColor, QPen, QBrush
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QFileDialog, QScrollArea, QFrame, QSizePolicy, QMessageBox,
)
from styles.theme import COLORS, BTN_PRIMARY
from core import repo_store


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
    open_requested = pyqtSignal(str)
    remove_requested = pyqtSignal(str)

    def __init__(self, repo_path: str, parent=None):
        super().__init__(parent)
        self._path = repo_path
        self.setObjectName("repoCard")
        self.setStyleSheet(f"""
            #repoCard {{
                background-color: {COLORS['bg_card']};
                border: 1px solid {COLORS['border']};
                border-radius: 8px;
            }}
            #repoCard:hover {{ border-color: {COLORS['border_focus']}; }}
        """)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(20, 14, 16, 14)
        layout.setSpacing(14)

        icon = QLabel("◫")
        icon.setFixedWidth(28)
        icon.setStyleSheet(f"background: transparent; font-size: 20px; color: {COLORS['accent']};")
        layout.addWidget(icon)

        info = QVBoxLayout()
        info.setSpacing(2)
        name_label = QLabel(os.path.basename(self._path))
        name_label.setStyleSheet(
            f"background: transparent; font-size: 14px; font-weight: 600; color: {COLORS['text_primary']};"
        )
        path_label = QLabel(self._path)
        path_label.setStyleSheet(f"background: transparent; font-size: 12px; color: {COLORS['text_muted']};")
        path_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        info.addWidget(name_label)
        info.addWidget(path_label)
        layout.addLayout(info)
        layout.addStretch()

        git_badge = QLabel(" tracked ")
        git_badge.setStyleSheet(f"""
            font-size: 11px; font-weight: 600;
            color: {COLORS['tag_text']}; background: {COLORS['tag_bg']};
            border-radius: 4px; padding: 2px 8px;
        """)
        layout.addWidget(git_badge)

        open_btn = QPushButton("Explore →")
        open_btn.setStyleSheet(BTN_PRIMARY)
        open_btn.setFixedSize(100, 34)
        open_btn.setCursor(Qt.PointingHandCursor)
        open_btn.clicked.connect(lambda: self.open_requested.emit(self._path))
        layout.addWidget(open_btn)

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

    # ── UI ────────────────────────────────────────────────────────────────────

    def _setup_ui(self):
        self.setStyleSheet(f"background: {COLORS['bg_primary']};")
        root = QVBoxLayout(self)
        root.setContentsMargins(40, 32, 40, 32)
        root.setSpacing(0)

        title = QLabel("Your Projects")
        title.setStyleSheet(
            f"background: transparent; font-size: 22px; font-weight: 700; color: {COLORS['text_primary']};"
        )
        root.addWidget(title)
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
        scroll.setStyleSheet("background: transparent;")

        self._cards_container = QWidget()
        self._cards_container.setStyleSheet("background: transparent;")
        self._cards_layout = QVBoxLayout(self._cards_container)
        self._cards_layout.setContentsMargins(0, 0, 0, 0)
        self._cards_layout.setSpacing(10)
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
            card = RepoCard(path)
            card.open_requested.connect(self.repo_selected.emit)
            card.remove_requested.connect(self.remove_repo)
            self._cards_layout.insertWidget(insert_pos, card)
            insert_pos += 1

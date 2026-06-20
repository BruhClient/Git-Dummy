"""Main commit detail panel — slides in from the right."""
from __future__ import annotations

import hashlib
import threading

import qtawesome as qta

from PyQt5.QtCore import Qt, QSize, QPropertyAnimation, QEasingCurve, QRect, QPoint, QTimer, pyqtSignal
from PyQt5.QtGui import QPainter, QColor, QBrush, QPen, QPainterPath, QPixmap, QFont
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QFrame, QLineEdit,
)

from styles.theme import COLORS, scrollbar_style
from ui.dialogs import confirm
from ui.dialogs.message_dialog import _CommitMessageDialog
from .diff_renderer import (
    _VScrollArea, _trunc, _close_btn_style,
    _STATUS_COLOR, _MiniBar, _fade_in, _fade_out_and_remove, _divider, _Row,
    PANEL_W, CHANGES_W, SWIPE_THRESHOLD,
)
from .all_changes_popup import AllChangesPopup

# Roles that can act directly on main; write-level users get the branch redirect.

_PALETTE = [
    "#6366f1", "#f59e0b", "#ef4444", "#8b5cf6",
    "#06b6d4", "#f97316", "#ec4899", "#14b8a6",
    "#84cc16", "#a78bfa",
]

def _author_color(name: str) -> str:
    idx = int(hashlib.md5(name.encode()).hexdigest(), 16) % len(_PALETTE)
    return _PALETTE[idx]

_STATUS_LABEL = {
    "added":    "Added",
    "deleted":  "Deleted",
    "modified": "Edited",
    "renamed":  "Renamed",
}


class _HeaderAvatar(QWidget):
    """Circular avatar in the detail panel header — initials first, photo on load."""

    SIZE = 40

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(self.SIZE, self.SIZE)
        self._initials = ""
        self._color    = QColor("#6366f1")
        self._pixmap: QPixmap | None = None

    def set_author(self, name: str, avatar_url: str = ""):
        self._initials = (name[:1] + (name.split()[-1][:1] if " " in name else "")).upper()
        self._color    = QColor(_author_color(name))
        self._pixmap   = None
        self.update()
        if avatar_url:
            threading.Thread(target=self._fetch, args=(avatar_url,), daemon=True).start()

    def _fetch(self, url: str):
        try:
            import requests
            resp = requests.get(url, timeout=10)
            if resp.status_code == 200:
                pm = QPixmap()
                pm.loadFromData(resp.content)
                if not pm.isNull():
                    s = self.SIZE
                    self._pixmap = pm.scaled(s, s, Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation)
                    self.update()
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
            x = (src.width()  - s) // 2
            y = (src.height() - s) // 2
            p.drawPixmap(0, 0, src, x, y, s, s)
        else:
            bg = QColor(self._color.red(), self._color.green(), self._color.blue(), 50)
            p.setBrush(QBrush(bg))
            p.setPen(Qt.NoPen)
            p.drawEllipse(0, 0, s, s)
            p.setClipping(False)
            p.setPen(QPen(self._color))
            p.setFont(QFont("Tilt Warp", s // 4, QFont.Bold))
            p.drawText(self.rect(), Qt.AlignCenter, self._initials)

        p.setClipping(False)
        p.setBrush(Qt.NoBrush)
        p.setPen(QPen(self._color, 1.5))
        p.drawEllipse(1, 1, s - 2, s - 2)
        p.end()


class _FileCard(QWidget):
    """Card showing one changed file. Click to open the changes panel."""

    file_clicked = pyqtSignal(dict)

    def __init__(self, info: dict, parent=None):
        super().__init__(parent)
        self._info     = info
        self._selected = False
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setCursor(Qt.PointingHandCursor)
        self._apply_style()

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        hdr = QWidget()
        hdr.setAttribute(Qt.WA_StyledBackground, True)
        hdr.setObjectName("fcHdr")
        self._hdr = hdr
        self._update_hdr_style()
        hdr.setFixedHeight(54)

        hl = QHBoxLayout(hdr)
        hl.setContentsMargins(12, 0, 12, 0)
        hl.setSpacing(8)

        color = _STATUS_COLOR.get(info["status"], COLORS["accent"])
        dot = QLabel("●")
        dot.setFixedWidth(12)
        dot.setStyleSheet(f"background: transparent; font-size: 9px; color: {color};")
        hl.addWidget(dot)

        nb = QVBoxLayout()
        nb.setSpacing(1)
        nb.setAlignment(Qt.AlignVCenter)

        name_lbl = QLabel(_trunc(info["name"], 36))
        name_lbl.setToolTip(info["name"])
        name_lbl.setStyleSheet(
            f"background: transparent; font-size: 12px; font-weight: 600; font-family: 'Tilt Warp';"
            f" color: {COLORS['text_primary']};"
        )
        nb.addWidget(name_lbl)

        parts = info["path"].split("/")
        if len(parts) > 1:
            dir_text = "/".join(parts[:-1])
            dir_lbl = QLabel(_trunc(dir_text, 32))
            dir_lbl.setToolTip(dir_text)
            dir_lbl.setStyleSheet(
                f"background: transparent; font-size: 10px; color: {COLORS['text_muted']};"
            )
            nb.addWidget(dir_lbl)

        hl.addLayout(nb)
        hl.addStretch()

        if info["is_binary"]:
            bin_lbl = QLabel("binary")
            bin_lbl.setStyleSheet(f"background: transparent; font-size: 10px; color: {COLORS['text_muted']};")
            hl.addWidget(bin_lbl)
        else:
            counts = QLabel(f"+{info['insertions']}  −{info['deletions']}")
            counts.setStyleSheet(
                f"background: transparent; font-size: 11px;"
                f" color: {COLORS['text_muted']}; font-family: monospace;"
            )
            hl.addWidget(counts)
            hl.addWidget(_MiniBar(info["insertions"], info["deletions"]))

        chevron = QLabel("›")
        chevron.setStyleSheet(f"background: transparent; font-size: 16px; color: {COLORS['text_muted']};")
        hl.addWidget(chevron)

        root.addWidget(hdr)

    def set_selected(self, selected: bool):
        self._selected = selected
        self._update_hdr_style()

    def _apply_style(self):
        self.setStyleSheet("background: transparent; border-radius: 6px;")

    def _update_hdr_style(self):
        if self._selected:
            border_color = COLORS["accent"]
            bg = COLORS["bg_hover"]
        else:
            border_color = COLORS["border"]
            bg = COLORS["bg_card"]
        self._hdr.setStyleSheet(f"""
            #fcHdr {{
                background: {bg};
                border: 1px solid {border_color};
                border-radius: 6px;
            }}
        """) if hasattr(self, "_hdr") else None

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.file_clicked.emit(self._info)
        super().mousePressEvent(event)

    def enterEvent(self, _):
        # _hdr fills the card and is opaque, so the hover highlight must be
        # applied to it (not `self`) to be visible.
        if not self._selected:
            self._hdr.setStyleSheet(f"""
                #fcHdr {{
                    background: {COLORS['bg_hover']};
                    border: 1px solid {COLORS['border']};
                    border-radius: 6px;
                }}
            """)

    def leaveEvent(self, _):
        self._update_hdr_style()


class DetailPanel(QWidget):
    """
    Slides in from the right edge of its parent when show_commit() is called.
    Parent must call reposition() whenever its size changes.
    """
    panel_toggled        = pyqtSignal(bool)
    file_selected        = pyqtSignal(dict)
    stash_file_selected  = pyqtSignal(dict)
    navigate_requested      = pyqtSignal(str)        # commit sha
    branch_create_requested = pyqtSignal(str, str)   # sha, branch_name
    push_requested          = pyqtSignal(str)          # branch name (kept for compat)
    pr_open_requested       = pyqtSignal(str)          # branch name → triggers PR wizard
    pull_requested          = pyqtSignal(str)          # branch name
    sync_requested          = pyqtSignal(str)          # branch name (merge remote into local)
    merge_requested         = pyqtSignal(str, str)    # source_branch, target_branch
    save_stash_requested    = pyqtSignal(str, str, str, str)  # commit sha, stash_ref, message, branch
    clear_stash_requested   = pyqtSignal(str, str)    # commit sha, stash_ref
    hard_revert_requested   = pyqtSignal(str, str)   # branch, target_sha
    soft_revert_requested   = pyqtSignal(str, str, str)   # branch, tip_sha, parent_sha
    delete_branch_requested = pyqtSignal(str, str)    # branch name, parent sha

    def __init__(self, parent: QWidget):
        super().__init__(parent)
        self.setFixedWidth(PANEL_W)
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setStyleSheet(f"""
            DetailPanel {{
                background: {COLORS['bg_secondary']};
                border-left: 1px solid {COLORS['border']};
            }}
        """)
        self.raise_()

        self._anim = QPropertyAnimation(self, b"geometry")
        self._anim.setDuration(220)
        self._anim.setEasingCurve(QEasingCurve.OutCubic)

        self._visible = False
        self._protected_branch_name: str | None = None
        self._current_action_branch: str = ""
        self._viewer_mode: bool = False
        self._setup_ui()
        self._place(visible=False, animate=False)

    # ── UI ────────────────────────────────────────────────────────────────────

    def _setup_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        header = QWidget()
        header.setObjectName("panelHeader")
        header.setFixedHeight(64)
        header.setStyleSheet(f"""
            #panelHeader {{
                background: {COLORS['bg_card']};
                border-bottom: 1px solid {COLORS['border']};
            }}
        """)
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(20, 0, 16, 0)
        header_layout.setSpacing(14)

        self._header_avatar = _HeaderAvatar()
        header_layout.addWidget(self._header_avatar)

        name_block = QVBoxLayout()
        name_block.setSpacing(2)
        name_block.setContentsMargins(0, 0, 0, 0)
        name_block.setAlignment(Qt.AlignVCenter)

        self._header_name = QLabel("—")
        self._header_name.setStyleSheet(
            f"background: transparent; font-size: 14px; font-weight: 600; font-family: 'Tilt Warp'; color: {COLORS['text_primary']};"
        )
        self._header_branch = QLabel("—")
        self._header_branch.setStyleSheet(
            f"background: transparent; font-size: 11px; color: {COLORS['text_muted']}; letter-spacing: 0.02em;"
        )
        _warn = COLORS.get("warning", "#f59e0b")
        self._protected_badge = QWidget()
        self._protected_badge.setStyleSheet("background: transparent;")
        _badge_hl = QHBoxLayout(self._protected_badge)
        _badge_hl.setContentsMargins(0, 0, 0, 0)
        _badge_hl.setSpacing(3)
        _badge_icon = QLabel()
        _badge_icon.setPixmap(qta.icon("ph.lock", color=_warn).pixmap(10, 10))
        _badge_icon.setStyleSheet("background: transparent;")
        _badge_text = QLabel("Protected")
        _badge_text.setStyleSheet(f"background: transparent; font-size: 10px; color: {_warn};")
        _badge_hl.addWidget(_badge_icon)
        _badge_hl.addWidget(_badge_text)
        self._protected_badge.hide()

        branch_row = QHBoxLayout()
        branch_row.setSpacing(6)
        branch_row.setContentsMargins(0, 0, 0, 0)
        branch_row.addWidget(self._header_branch)
        branch_row.addWidget(self._protected_badge)
        branch_row.addStretch()

        name_block.addWidget(self._header_name)
        name_block.addLayout(branch_row)
        header_layout.addLayout(name_block)
        header_layout.addStretch()

        close_btn = QPushButton()
        close_btn.setIcon(qta.icon("fa5s.times", color=COLORS["text_muted"]))
        close_btn.setIconSize(QSize(12, 12))
        close_btn.setFixedSize(40, 40)
        close_btn.setCursor(Qt.PointingHandCursor)
        close_btn.setStyleSheet(_close_btn_style(COLORS))
        close_btn.clicked.connect(self.hide_panel)
        header_layout.addWidget(close_btn)
        root.addWidget(header)

        scroll = _VScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setStyleSheet("QScrollArea { background: transparent; border: none; }\n" + scrollbar_style())

        content = QWidget()
        content.setStyleSheet("background: transparent;")
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(20, 20, 20, 20)
        content_layout.setSpacing(16)

        self._sha    = _Row("Committed on")
        self._branch = _Row("Branch")
        self._author = _Row("Made by")
        self._date   = _Row("When")

        content_layout.addWidget(self._sha)
        content_layout.addWidget(_divider())
        content_layout.addWidget(self._branch)
        content_layout.addWidget(self._author)
        content_layout.addWidget(self._date)
        content_layout.addWidget(_divider())

        msg_label = QLabel("DESCRIPTION")
        msg_label.setStyleSheet(
            f"background: transparent; font-size: 10px; font-weight: 600; font-family: 'Tilt Warp'; color: {COLORS['text_muted']}; letter-spacing: 0.07em;"
        )
        content_layout.addWidget(msg_label)

        self._message = QLabel("—")
        self._message.setWordWrap(True)
        self._message.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self._message.setStyleSheet(f"background: transparent; font-size: 13px; color: {COLORS['text_primary']}; line-height: 1.5;")
        content_layout.addWidget(self._message)

        content_layout.addWidget(_divider())

        self._goto_btn = QPushButton("Go to this snapshot")
        self._goto_btn.setIcon(qta.icon("fa5s.arrow-right", color=COLORS['text_on_accent']))
        self._goto_btn.setCursor(Qt.PointingHandCursor)
        self._goto_btn.setStyleSheet(f"""
            QPushButton {{
                background: {COLORS['accent']}; border: none; border-radius: 8px;
                color: {COLORS['text_on_accent']}; font-size: 12px; font-weight: 600; font-family: 'Tilt Warp'; padding: 9px 16px;
            }}
            QPushButton:hover {{ background: {COLORS['accent_dim']}; }}
        """)
        self._goto_btn.clicked.connect(self._on_goto)
        content_layout.addWidget(self._goto_btn)

        self._branch_btn = QPushButton("Create new branch")
        self._branch_btn.setIcon(qta.icon("fa5s.code-branch", color=COLORS['text_secondary']))
        self._branch_btn.setCursor(Qt.PointingHandCursor)
        self._branch_btn.setStyleSheet(f"""
            QPushButton {{
                background: transparent;
                border: 1px solid {COLORS['border']};
                border-radius: 8px;
                color: {COLORS['text_secondary']};
                font-size: 12px; font-weight: 600; font-family: 'Tilt Warp'; padding: 9px 16px;
            }}
            QPushButton:hover {{
                border-color: {COLORS['accent']};
                color: {COLORS['accent']};
            }}
        """)
        self._branch_btn.clicked.connect(self._on_create_branch)
        content_layout.addWidget(self._branch_btn)

        self._push_btn = QPushButton("Upload")
        self._push_btn.setIcon(qta.icon("mdi.upload", color=COLORS['text_secondary']))
        self._push_btn.setCursor(Qt.PointingHandCursor)
        self._push_btn.setStyleSheet(f"""
            QPushButton {{
                background: transparent;
                border: 1px solid {COLORS['border']};
                border-radius: 8px;
                color: {COLORS['text_secondary']};
                font-size: 12px; font-weight: 600; font-family: 'Tilt Warp'; padding: 9px 16px;
            }}
            QPushButton:hover {{
                border-color: {COLORS['accent']};
                color: {COLORS['accent']};
            }}
        """)
        self._push_btn.clicked.connect(self._on_push)
        self._push_btn.hide()
        content_layout.addWidget(self._push_btn)

        self._pull_btn = QPushButton("Pull latest")
        self._pull_btn.setIcon(qta.icon("fa5s.cloud-download-alt", color=COLORS['text_secondary']))
        self._pull_btn.setCursor(Qt.PointingHandCursor)
        self._pull_btn.setStyleSheet(f"""
            QPushButton {{
                background: transparent;
                border: 1px solid {COLORS['border']};
                border-radius: 8px;
                color: {COLORS['text_secondary']};
                font-size: 12px; font-weight: 600; font-family: 'Tilt Warp'; padding: 9px 16px;
            }}
            QPushButton:hover {{
                border-color: {COLORS['accent']};
                color: {COLORS['accent']};
            }}
        """)
        self._pull_btn.clicked.connect(self._on_pull)
        self._pull_btn.hide()
        content_layout.addWidget(self._pull_btn)

        self._sync_btn = QPushButton("Sync with remote")
        self._sync_btn.setIcon(qta.icon("fa5s.sync", color=COLORS['text_secondary']))
        self._sync_btn.setCursor(Qt.PointingHandCursor)
        self._sync_btn.setStyleSheet(f"""
            QPushButton {{
                background: transparent;
                border: 1px solid {COLORS['border']};
                border-radius: 8px;
                color: {COLORS['text_secondary']};
                font-size: 12px; font-weight: 600; font-family: 'Tilt Warp'; padding: 9px 16px;
            }}
            QPushButton:hover {{
                border-color: {COLORS['accent']};
                color: {COLORS['accent']};
            }}
        """)
        self._sync_btn.setToolTip("Your branch has diverged from remote — merge remote changes into local and create a merge commit")
        self._sync_btn.clicked.connect(self._on_sync)
        self._sync_btn.hide()
        content_layout.addWidget(self._sync_btn)

        def _action_style(color: str) -> str:
            return (f"QPushButton {{ background: transparent;"
                    f" border: 1px solid {color}; border-radius: 8px;"
                    f" color: {color}; font-size: 12px; font-weight: 600; font-family: 'Tilt Warp'; padding: 9px 16px; }}"
                    f"QPushButton:hover {{ background: {color}; color: {COLORS['text_on_accent']}; }}"
                    f"QPushButton:disabled {{ border-color: {COLORS['border']};"
                    f" color: {COLORS['text_muted']}; }}")


        self._save_stash_btn = QPushButton("Save Changes")
        self._save_stash_btn.setCursor(Qt.PointingHandCursor)
        self._save_stash_btn.setStyleSheet(_action_style(COLORS["accent"]))
        self._save_stash_btn.clicked.connect(self._on_save_stash)
        self._save_stash_btn.hide()
        content_layout.addWidget(self._save_stash_btn)

        self._clear_stash_btn = QPushButton("Clear Changes")
        self._clear_stash_btn.setCursor(Qt.PointingHandCursor)
        self._clear_stash_btn.setStyleSheet(_action_style(COLORS["danger"]))
        self._clear_stash_btn.clicked.connect(self._on_clear_stash)
        self._clear_stash_btn.hide()
        content_layout.addWidget(self._clear_stash_btn)

        self._hard_revert_btn = QPushButton("Hard Revert")
        self._hard_revert_btn.setCursor(Qt.PointingHandCursor)
        self._hard_revert_btn.setStyleSheet(_action_style(COLORS["warning"]))
        self._hard_revert_btn.clicked.connect(self._on_hard_revert)
        self._hard_revert_btn.hide()
        content_layout.addWidget(self._hard_revert_btn)

        self._soft_revert_btn = QPushButton("Soft Revert")
        self._soft_revert_btn.setCursor(Qt.PointingHandCursor)
        self._soft_revert_btn.setStyleSheet(_action_style(COLORS["text_secondary"]))
        self._soft_revert_btn.clicked.connect(self._on_soft_revert)
        self._soft_revert_btn.hide()
        content_layout.addWidget(self._soft_revert_btn)

        self._merge_btn = QPushButton("Merge into…")
        self._merge_btn.setCursor(Qt.PointingHandCursor)
        self._merge_btn.setStyleSheet(f"""
            QPushButton {{
                background: transparent; border: 1px solid {COLORS['border']};
                border-radius: 8px; color: {COLORS['text_secondary']};
                font-size: 12px; font-weight: 600; font-family: 'Tilt Warp'; padding: 9px 16px;
            }}
            QPushButton:hover {{ border-color: {COLORS['accent']}; color: {COLORS['accent']}; }}
            QPushButton:disabled {{ color: {COLORS['text_muted']}; }}
        """)
        self._merge_btn.clicked.connect(self._on_merge)
        self._merge_btn.hide()
        content_layout.addWidget(self._merge_btn)

        self._delete_branch_btn = QPushButton("Delete Branch")
        self._delete_branch_btn.setCursor(Qt.PointingHandCursor)
        self._delete_branch_btn.setStyleSheet(_action_style(COLORS["danger"]))
        self._delete_branch_btn.clicked.connect(self._on_delete_branch)
        self._delete_branch_btn.hide()
        content_layout.addWidget(self._delete_branch_btn)

        self._stash_section = QWidget()
        self._stash_section.setStyleSheet("background: transparent;")
        self._stash_section.hide()
        stash_vl = QVBoxLayout(self._stash_section)
        stash_vl.setContentsMargins(0, 0, 0, 0)
        stash_vl.setSpacing(6)

        stash_hdr = QWidget()
        stash_hdr.setStyleSheet("background: transparent;")
        stash_hl = QHBoxLayout(stash_hdr)
        stash_hl.setContentsMargins(0, 0, 0, 0)
        stash_hl.setSpacing(0)

        self._stash_label = QLabel("UNSAVED")
        self._stash_label.setStyleSheet(
            f"background: transparent; font-size: 10px; font-weight: 600; font-family: 'Tilt Warp';"
            f" color: {COLORS['warning']}; letter-spacing: 0.07em;"
        )
        stash_hl.addWidget(self._stash_label)
        stash_hl.addStretch()

        self._view_stash_btn = QPushButton("View all →")
        self._view_stash_btn.setCursor(Qt.PointingHandCursor)
        self._view_stash_btn.setStyleSheet(f"""
            QPushButton {{
                background: transparent; border: none;
                font-size: 10px; color: {COLORS['warning']};
                padding: 0;
            }}
            QPushButton:hover {{ color: {COLORS['text_primary']}; }}
        """)
        self._view_stash_btn.hide()
        self._view_stash_btn.clicked.connect(self._open_stash_view)
        stash_hl.addWidget(self._view_stash_btn)

        stash_vl.addWidget(stash_hdr)

        self._stash_files_container = QWidget()
        self._stash_files_container.setStyleSheet("background: transparent;")
        self._stash_files_layout = QVBoxLayout(self._stash_files_container)
        self._stash_files_layout.setContentsMargins(0, 0, 0, 0)
        self._stash_files_layout.setSpacing(6)
        stash_vl.addWidget(self._stash_files_container)

        content_layout.addWidget(self._stash_section)
        content_layout.addWidget(_divider())

        files_hdr = QWidget()
        files_hdr.setStyleSheet("background: transparent;")
        fhl = QHBoxLayout(files_hdr)
        fhl.setContentsMargins(0, 0, 0, 0)
        fhl.setSpacing(0)

        self._files_label = QLabel("CHANGES")
        self._files_label.setStyleSheet(
            f"background: transparent; font-size: 10px; font-weight: 600; font-family: 'Tilt Warp';"
            f" color: {COLORS['text_muted']}; letter-spacing: 0.07em;"
        )
        fhl.addWidget(self._files_label)
        fhl.addStretch()

        self._view_all_btn = QPushButton("View all →")
        self._view_all_btn.setCursor(Qt.PointingHandCursor)
        self._view_all_btn.setStyleSheet(f"""
            QPushButton {{
                background: transparent; border: none;
                font-size: 10px; color: {COLORS['accent']};
                padding: 0;
            }}
            QPushButton:hover {{ color: {COLORS['text_primary']}; }}
        """)
        self._view_all_btn.hide()
        self._view_all_btn.clicked.connect(self._open_all_changes)
        fhl.addWidget(self._view_all_btn)
        content_layout.addWidget(files_hdr)

        self._files_container = QWidget()
        self._files_container.setStyleSheet("background: transparent;")
        self._files_layout = QVBoxLayout(self._files_container)
        self._files_layout.setContentsMargins(0, 0, 0, 0)
        self._files_layout.setSpacing(6)
        content_layout.addWidget(self._files_container)

        content_layout.addStretch()
        scroll.setWidget(content)
        scroll.viewport().setStyleSheet("background: transparent;")
        root.addWidget(scroll)

    # ── Public ────────────────────────────────────────────────────────────────

    def _populate_files(self, files: list):
        self._files_data = files
        while self._files_layout.count():
            item = self._files_layout.takeAt(0)
            w = item.widget()
            if w:
                w.setParent(None)
        self._file_cards: list[_FileCard] = []
        self._selected_card: _FileCard | None = None
        n = len(files)
        self._files_label.setText(f"CHANGES  —  {n} file{'s' if n != 1 else ''}")
        self._view_all_btn.setVisible(n > 0)
        for info in files:
            card = _FileCard(info)
            card.file_clicked.connect(self._on_file_card_clicked)
            self._files_layout.addWidget(card)
            self._file_cards.append(card)

    def _open_all_changes(self):
        files = getattr(self, "_files_data", [])
        if not files:
            return
        commit_label = self._header_branch.text()
        popup = AllChangesPopup(files, commit_label, self.parent())
        popup.show()

    def _on_file_card_clicked(self, info: dict):
        for card in getattr(self, "_stash_cards", []):
            card.set_selected(False)
        for card in self._file_cards:
            card.set_selected(card._info is info)
        self._selected_card = next((c for c in self._file_cards if c._info is info), None)
        self.file_selected.emit(info)

    def _on_stash_card_clicked(self, info: dict):
        for card in getattr(self, "_file_cards", []):
            card.set_selected(False)
        self._selected_card = None
        for card in getattr(self, "_stash_cards", []):
            card.set_selected(card._info is info)
        self.stash_file_selected.emit(info)

    def deselect_files(self):
        for card in getattr(self, "_file_cards", []):
            card.set_selected(False)
        for card in getattr(self, "_stash_cards", []):
            card.set_selected(False)
        self._selected_card = None

    def lock_actions(self):
        for btn in (self._goto_btn, self._branch_btn, self._push_btn,
                    self._pull_btn, self._sync_btn, self._merge_btn, self._hard_revert_btn,
                    self._soft_revert_btn, self._delete_branch_btn,
                    self._save_stash_btn, self._clear_stash_btn):
            btn.setEnabled(False)

    def unlock_actions(self):
        self._refresh_goto_btn()
        self._branch_btn.setEnabled(True)
        self._merge_btn.setEnabled(True)
        for btn in (self._push_btn, self._pull_btn, self._sync_btn,
                    self._hard_revert_btn, self._soft_revert_btn,
                    self._delete_branch_btn):
            if btn.isVisible():
                btn.setEnabled(True)
        self._apply_hard_revert_protection()

    def set_merge_state(self, show: bool, source_branch: str, all_branches: list,
                        default_branch: str = "main", branch_colors: dict = None):
        self._merge_source = source_branch
        self._merge_branches = [b for b in all_branches if b != source_branch]
        self._merge_default = default_branch
        self._merge_branch_colors = branch_colors or {}
        self._merge_btn.setVisible(show)

    def _on_merge(self):
        current_branch = getattr(self, "_merge_source", "")
        branches = getattr(self, "_merge_branches", [])
        default = getattr(self, "_merge_default", "main")
        colors = getattr(self, "_merge_branch_colors", {})
        if not current_branch or not branches:
            return
        from ui.dialogs.confirm_dialog import MergeDialog
        dlg = MergeDialog(self, source_branch=current_branch,
                          branches=branches, default_branch=default,
                          branch_colors=colors)
        if dlg.exec_() == MergeDialog.Accepted:
            target = dlg.get_target()
            if target:
                self.lock_actions()
                self.merge_requested.emit(target, current_branch)

    def set_pull_state(self, can_pull: bool, branch: str):
        self._pull_branch = branch
        self._pull_btn.setVisible(can_pull)
        self._pull_btn.setEnabled(can_pull)

    def set_sync_state(self, is_diverged: bool, branch: str):
        self._sync_branch = branch
        self._sync_btn.setVisible(is_diverged)
        self._sync_btn.setEnabled(is_diverged)

    def _on_sync(self):
        branch = getattr(self, "_sync_branch", "")
        if branch:
            self.lock_actions()
            self.sync_requested.emit(branch)

    def _on_pull(self):
        branch = getattr(self, "_pull_branch", "")
        if branch:
            self.lock_actions()
            self.pull_requested.emit(branch)

    def _on_save_stash(self):
        sha       = getattr(self, "_current_sha", "")
        stash_ref = getattr(self, "_stash_ref", "")
        if not sha:
            return
        dlg = _CommitMessageDialog(self)
        if dlg.exec_() != _CommitMessageDialog.Accepted:
            return
        msg = dlg.get_message()
        if not msg:
            return
        branch = getattr(self, "_action_branch", "")
        self.lock_actions()
        self.save_stash_requested.emit(sha, stash_ref, msg, branch)

    def set_commit_actions(self, branch: str, parent_sha: str,
                            has_parent: bool, is_first_of_branch: bool,
                            is_main: bool, is_head: bool,
                            is_remote_head: bool = False,
                            is_merge_commit: bool = False,
                            branch_depth: int = 0,
                            is_remote_branch: bool = False,
                            is_remote_only: bool = False,
                            is_protected: bool = False,
                            can_push: bool = True):
        self._last_action_kwargs = dict(
            branch=branch, parent_sha=parent_sha, has_parent=has_parent,
            is_first_of_branch=is_first_of_branch, is_main=is_main,
            is_head=is_head, is_remote_head=is_remote_head,
            is_merge_commit=is_merge_commit,
            branch_depth=branch_depth, is_remote_branch=is_remote_branch,
        )

        self._action_branch          = branch
        self._action_parent_sha      = parent_sha
        self._action_is_merge_commit = is_merge_commit
        self._is_remote_head         = is_remote_head
        self._current_action_branch  = branch
        self._viewer_mode            = not can_push
        if is_protected:
            self._protected_branch_name = branch
        elif self._protected_branch_name == branch:
            self._protected_branch_name = None
        self._protected_badge.setVisible(is_protected)
        self._protected_badge.setToolTip(
            "This branch is protected on GitHub.\n"
            "Direct pushes are blocked — use a Pull Request instead."
            if is_protected else "")

        if not can_push:
            self._branch_btn.hide()
            self._hard_revert_btn.hide()
            self._soft_revert_btn.hide()
            self._delete_branch_btn.hide()
            self._merge_btn.hide()
            return

        if is_remote_only:
            self._goto_btn.hide()
            self._branch_btn.hide()
            self._hard_revert_btn.hide()
            self._soft_revert_btn.hide()
            self._delete_branch_btn.hide()
            return

        can_branch = branch_depth < 2
        self._branch_btn.setVisible(can_branch)
        self._branch_btn.setEnabled(can_branch)

        if not is_head:
            self._hard_revert_btn.hide()
            self._soft_revert_btn.hide()
            if not is_remote_head:
                self._delete_branch_btn.hide()
                return

        show_delete = not is_main and bool(branch) and (is_head or is_remote_head) and not is_merge_commit and is_first_of_branch
        self._delete_branch_btn.setVisible(show_delete)
        self._delete_branch_btn.setEnabled(show_delete)

        if is_first_of_branch:
            self._hard_revert_btn.hide()
            self._soft_revert_btn.hide()
        else:
            show_hard = has_parent and bool(branch)
            show_soft = show_hard
            self._hard_revert_btn.setVisible(show_hard)
            self._hard_revert_btn.setEnabled(show_hard)
            self._soft_revert_btn.setVisible(show_soft)
            self._soft_revert_btn.setEnabled(show_soft)

        self._current_action_branch = branch or ""
        self._apply_hard_revert_protection()

    def _on_goto(self):
        if getattr(self, "_current_sha", None):
            self.lock_actions()
            self.navigate_requested.emit(self._current_sha)

    def _on_create_branch(self):
        sha = getattr(self, "_current_sha", None)
        if not sha:
            return
        dlg = _CommitMessageDialog(self, title="Create Branch",
                                   placeholder="Branch name…")
        if dlg.exec_() != _CommitMessageDialog.Accepted:
            return
        name = dlg.get_message()
        if name:
            self.lock_actions()
            self.branch_create_requested.emit(sha, name)

    def set_branch_protection(self, protected_branch: str | None):
        self._protected_branch_name = protected_branch
        self._apply_hard_revert_protection()
        self._refresh_push_btn_label()

    def _refresh_push_btn_label(self):
        branch = getattr(self, "_push_branch", "")
        protected = bool(self._protected_branch_name) and branch == self._protected_branch_name
        self._push_btn.setText("Open Pull Request" if protected else "Upload")

    def _apply_hard_revert_protection(self):
        protected = (
            bool(self._protected_branch_name)
            and self._current_action_branch == self._protected_branch_name
            and self._hard_revert_btn.isVisible()
        )
        self._hard_revert_btn.setEnabled(not protected)
        self._hard_revert_btn.setToolTip(
            "This branch is protected on GitHub — hard revert is blocked" if protected else ""
        )
        self._protected_badge.setVisible(protected)

    def set_push_state(self, can_push: bool, branch: str = "", is_protected: bool = False):
        self._push_branch = branch
        self._push_btn.setVisible(can_push)
        self._push_btn.setEnabled(can_push)
        self._refresh_push_btn_label()

    def _on_push(self):
        branch = getattr(self, "_push_branch", "")
        if branch:
            self.lock_actions()
            if self._protected_branch_name and branch == self._protected_branch_name:
                self.pr_open_requested.emit(branch)
            else:
                self.push_requested.emit(branch)

    def _on_hard_revert(self):
        branch   = getattr(self, "_action_branch", "")
        sha      = getattr(self, "_action_parent_sha", "")
        is_merge = getattr(self, "_action_is_merge_commit", False)
        if not branch or not sha:
            return
        if is_merge:
            title = "Undo Merge"
            body  = (f"Undo the merge on '{branch}'?\n\n"
                     f"This resets '{branch}' to its state before the merge. "
                     f"The merge commit will be removed and this cannot be undone.")
        else:
            title = "Hard Revert"
            body  = (f"Hard revert '{branch}'? "
                     f"This permanently discards the latest commit and cannot be undone.")
        if confirm(self, title, body, "Yes"):
            self.lock_actions()
            self.hard_revert_requested.emit(branch, sha)

    def _on_soft_revert(self):
        branch = getattr(self, "_action_branch", "")
        tip    = getattr(self, "_current_sha", "")
        parent = getattr(self, "_action_parent_sha", "")
        if branch and tip:
            self.lock_actions()
            self.soft_revert_requested.emit(branch, tip, parent)

    def _on_delete_branch(self):
        branch = getattr(self, "_action_branch", "")
        if not branch:
            return
        if confirm(self, "Delete branch",
                   f"Delete '{branch}' locally and from remote?", "Delete"):
            self.lock_actions()
            parent_sha = getattr(self, "_action_parent_sha", "")
            self.delete_branch_requested.emit(branch, parent_sha)

    def _on_clear_stash(self):
        sha       = getattr(self, "_current_sha", "")
        stash_ref = getattr(self, "_stash_ref", "")
        if sha:
            if confirm(self, "Clear unsaved changes",
                       "Permanently discard all unsaved changes? This cannot be undone."):
                self.lock_actions()
                self.clear_stash_requested.emit(sha, stash_ref)

    def set_head_sha(self, head_sha: str):
        self._head_sha = head_sha
        self._refresh_goto_btn()

    def _refresh_goto_btn(self):
        is_current = bool(
            getattr(self, "_current_sha", None) and
            self._current_sha == getattr(self, "_head_sha", "")
        )
        self._goto_btn.setText("You are here" if is_current else "Go to this snapshot")
        self._goto_btn.setEnabled(not is_current)
        self._goto_btn.setStyleSheet(f"""
            QPushButton {{
                background: {'transparent' if is_current else COLORS['accent']};
                border: {'1px solid ' + COLORS['border'] if is_current else 'none'};
                border-radius: 8px;
                color: {COLORS['text_muted'] if is_current else COLORS['text_on_accent']};
                font-size: 12px; font-weight: 600; font-family: 'Tilt Warp'; padding: 9px 16px;
            }}
            QPushButton:hover {{
                background: {COLORS['bg_hover'] if is_current else COLORS['accent_dim']};
            }}
        """)

    def set_repo_path(self, path: str):
        self._repo_path = path

    def set_stash_shas(self, shas: set):
        self._stash_shas = shas

    def show_commit(self, commit, detail: dict, avatar_url: str = "",
                    display_author: str = None, files: list = None):
        self._current_sha = commit.sha
        self._refresh_goto_btn()
        self._save_stash_btn.hide()
        self._clear_stash_btn.hide()
        has_stash = commit.sha in getattr(self, "_stash_shas", set())
        print(f"[show_commit] sha={commit.sha[:8]} has_stash={has_stash} stash_shas={getattr(self, '_stash_shas', set())} is_remote_head={getattr(self, '_is_remote_head', '?')} head_sha={getattr(self, '_head_sha', '?')[:8] if getattr(self, '_head_sha', '') else '?'}")
        self._stash_section.setVisible(has_stash)
        if has_stash:
            self._populate_stash_files()
        shown_name = display_author or commit.author
        self._header_avatar.set_author(commit.author, avatar_url)
        self._header_name.setText(shown_name)
        self._header_branch.setText(commit.branch or "—")

        d = commit.date
        saved_at = f"{d.day} {d.strftime('%b')} {d.year}  {d.strftime('%H:%M')}"
        self._sha.set(saved_at, color=COLORS["text_secondary"])
        self._branch.set(commit.branch)
        self._author.set(commit.author, color=COLORS["text_secondary"])
        self._date.set(commit.date_str, color=COLORS["text_secondary"])
        self._message.setText(detail.get("message", commit.message))
        self._populate_files(files or [])

        if not self._visible:
            self._place(visible=True, animate=True)

    def _populate_stash_files(self):
        from core.ops import (get_stash_ref_for_commit, get_stash_diff_files,
                              has_uncommitted_changes, get_working_dir_diff_files)
        repo_path = getattr(self, "_repo_path", "")
        if not repo_path or not self._current_sha:
            return

        while self._stash_files_layout.count():
            item = self._stash_files_layout.takeAt(0)
            w = item.widget()
            if w:
                w.setParent(None)
        self._stash_cards_by_path: dict[str, _FileCard] = {}

        stash_ref = get_stash_ref_for_commit(repo_path, self._current_sha)
        is_head   = self._current_sha == getattr(self, "_head_sha", "")
        self._stash_ref = stash_ref
        print(f"[_populate_stash_files] sha={self._current_sha[:8]} stash_ref={stash_ref} is_head={is_head} is_remote_head={getattr(self, '_is_remote_head', '?')}")

        if stash_ref:
            files = get_stash_diff_files(repo_path, stash_ref)
        elif is_head and has_uncommitted_changes(repo_path):
            files = get_working_dir_diff_files(repo_path)
        else:
            print(f"[_populate_stash_files] no stash_ref and not head with changes, hiding")
            self._stash_section.hide()
            return

        n = len(files)
        print(f"[_populate_stash_files] {n} files, showing buttons (is_remote_head={getattr(self, '_is_remote_head', '?')})")
        self._stash_label.setText(f"UNSAVED  —  {n} file{'s' if n != 1 else ''}")
        self._view_stash_btn.setVisible(n > 0)
        if not getattr(self, "_is_remote_head", False) and not getattr(self, "_viewer_mode", False):
            self._clear_stash_btn.setVisible(n > 0)
            self._clear_stash_btn.setEnabled(n > 0)
            self._save_stash_btn.setVisible(n > 0)
            self._save_stash_btn.setEnabled(n > 0)
        self._stash_data = files

        for info in files:
            card = _FileCard(info)
            card.file_clicked.connect(self._on_stash_card_clicked)
            self._stash_files_layout.addWidget(card)
            _fade_in(card)
            self._stash_cards_by_path[info["path"]] = card

    def update_uncommitted_files(self, files: list):
        old_cards: dict[str, _FileCard] = getattr(self, "_stash_cards_by_path", {})
        old_info:  dict[str, dict]      = getattr(self, "_stash_info_by_path",  {})
        new_paths = {f["path"] for f in files}

        for path, card in list(old_cards.items()):
            if path not in new_paths:
                _fade_out_and_remove(card, self._stash_files_layout)
                del old_cards[path]
                old_info.pop(path, None)

        for info in files:
            path = info["path"]
            prev = old_info.get(path)
            stats_changed = (prev is None or
                             prev.get("insertions") != info.get("insertions") or
                             prev.get("deletions")  != info.get("deletions")  or
                             prev.get("status")     != info.get("status"))
            if path not in old_cards:
                card = _FileCard(info)
                card.file_clicked.connect(self._on_stash_card_clicked)
                self._stash_files_layout.addWidget(card)
                _fade_in(card)
                old_cards[path] = card
                old_info[path]  = info
            elif stats_changed:
                old_card = old_cards[path]
                idx = self._stash_files_layout.indexOf(old_card)
                old_card.setParent(None)
                card = _FileCard(info)
                card.file_clicked.connect(self._on_stash_card_clicked)
                if idx >= 0:
                    self._stash_files_layout.insertWidget(idx, card)
                else:
                    self._stash_files_layout.addWidget(card)
                old_cards[path] = card
                old_info[path]  = info

        self._stash_cards_by_path = old_cards
        self._stash_info_by_path  = old_info
        self._stash_data = files

        n = len(files)
        self._stash_label.setText(f"UNSAVED  —  {n} file{'s' if n != 1 else ''}")
        self._view_stash_btn.setVisible(n > 0)
        if not getattr(self, "_is_remote_head", False) and not getattr(self, "_viewer_mode", False):
            self._clear_stash_btn.setVisible(n > 0)
            self._clear_stash_btn.setEnabled(n > 0)
            self._save_stash_btn.setVisible(n > 0)
            self._save_stash_btn.setEnabled(n > 0)
        if files:
            self._stash_section.show()
        else:
            QTimer.singleShot(260, lambda: self._stash_section.hide() if not self._stash_data else None)

    def refresh_stash_section(self):
        from core.ops import (get_stash_ref_for_commit, get_stash_diff_files,
                              has_uncommitted_changes, get_working_dir_diff_files)
        repo_path = getattr(self, "_repo_path", "")
        if not repo_path or not self._current_sha:
            return

        stash_ref = get_stash_ref_for_commit(repo_path, self._current_sha)

        if stash_ref:
            files = get_stash_diff_files(repo_path, stash_ref)
        elif has_uncommitted_changes(repo_path):
            files = get_working_dir_diff_files(repo_path)
        else:
            files = []

        old_cards: dict[str, _FileCard] = getattr(self, "_stash_cards_by_path", {})
        new_paths = {f["path"] for f in files}

        for path, card in list(old_cards.items()):
            if path not in new_paths:
                _fade_out_and_remove(card, self._stash_files_layout)
                del old_cards[path]

        for info in files:
            path = info["path"]
            if path not in old_cards:
                card = _FileCard(info)
                card.file_clicked.connect(self._on_stash_card_clicked)
                self._stash_files_layout.addWidget(card)
                _fade_in(card)
                old_cards[path] = card

        self._stash_cards_by_path = old_cards
        self._stash_data = files

        n = len(files)
        if files:
            self._stash_label.setText(f"UNSAVED  —  {n} file{'s' if n != 1 else ''}")
            self._view_stash_btn.setVisible(True)
            self._clear_stash_btn.setVisible(True)
            self._clear_stash_btn.setEnabled(True)
            self._save_stash_btn.setVisible(True)
            self._save_stash_btn.setEnabled(True)
            self._stash_section.show()
        else:
            self._view_stash_btn.setVisible(False)
            self._clear_stash_btn.setVisible(False)
            self._save_stash_btn.setVisible(False)
            QTimer.singleShot(260, lambda: self._stash_section.hide() if not self._stash_data else None)

    def _open_stash_view(self):
        files = getattr(self, "_stash_data", [])
        if not files:
            return
        popup = AllChangesPopup(files, f"Unsaved at {self._current_sha[:7]}", self.parent())
        popup.show()

    def hide_panel(self):
        if self._visible:
            self.deselect_files()
            self._place(visible=False, animate=True)

    def reposition(self):
        self._place(visible=self._visible, animate=False)

    def mousePressEvent(self, event):
        self._swipe_start: QPoint = event.pos()
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event):
        if hasattr(self, "_swipe_start"):
            if event.pos().x() - self._swipe_start.x() > SWIPE_THRESHOLD:
                self.hide_panel()
        super().mouseReleaseEvent(event)

    def _place(self, visible: bool, animate: bool):
        prev = self._visible
        self._visible = visible
        if visible != prev:
            self.panel_toggled.emit(visible)
        p = self.parent()
        if p is None:
            return

        h = p.height()
        x_shown  = p.width() - PANEL_W
        x_hidden = p.width()

        target = QRect(x_shown if visible else x_hidden, 0, PANEL_W, h)

        if animate:
            self._anim.stop()
            self._anim.setStartValue(self.geometry())
            self._anim.setEndValue(target)
            self._anim.start()
        else:
            self.setGeometry(target)

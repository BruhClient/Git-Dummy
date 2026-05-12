"""Pull Requests panel — slides in from the right over the canvas."""
from __future__ import annotations

import re
import threading
from datetime import datetime, timezone

import requests

from PyQt5.QtCore import (Qt, QPropertyAnimation, QEasingCurve, QRect,
                           QTimer, pyqtSignal)
from PyQt5.QtGui import QPainter, QColor, QBrush, QPen, QPixmap, QFont
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QScrollArea, QFrame, QSizePolicy,
)
from styles.theme import COLORS


class _VScrollArea(QScrollArea):
    def resizeEvent(self, event):
        super().resizeEvent(event)
        w = self.widget()
        if w:
            w.setMaximumWidth(self.viewport().width())

    def scrollContentsBy(self, dx: int, dy: int):
        super().scrollContentsBy(0, dy)

    def wheelEvent(self, event):
        if abs(event.angleDelta().x()) > abs(event.angleDelta().y()):
            event.ignore()
        else:
            super().wheelEvent(event)

PANEL_W = 360

_STATE_COLORS = {
    "open":   "#3ecf8e",
    "closed": "#666666",
    "merged": "#8b5cf6",
}


def _relative_date(iso: str) -> str:
    try:
        dt = datetime.fromisoformat(iso.replace("Z", "+00:00"))
        delta = datetime.now(timezone.utc) - dt
        s = delta.total_seconds()
        if s < 3600:   return f"{int(s // 60)}m ago"
        if s < 86400:  return f"{int(s // 3600)}h ago"
        return f"{int(s // 86400)}d ago"
    except Exception:
        return ""


def _pr_branch_shas(commits, head_ref: str, head_sha: str) -> set[str]:
    """Return SHAs that belong to this PR's branch (for canvas dimming)."""
    # Primary: match by branch name
    by_branch = {c.sha for c in commits if c.branch == head_ref}
    if by_branch:
        return by_branch
    # Fallback: BFS from head_sha (stops when commit not in canvas)
    sha_map = {c.sha: c for c in commits}
    result: set[str] = set()
    queue = [head_sha]
    while queue:
        sha = queue.pop()
        if sha in result or sha not in sha_map:
            continue
        result.add(sha)
        queue.extend(sha_map[sha].parents[:1])  # only follow first parent to stay on branch
    return result


# ── PR row ────────────────────────────────────────────────────────────────────

class _PRRow(QWidget):
    hovered   = pyqtSignal(set)   # SHAs to KEEP bright (pr branch)
    unhovered = pyqtSignal()
    approve_clicked = pyqtSignal(int)  # pr number

    def __init__(self, pr: dict, commits: list, is_owner: bool, parent=None):
        super().__init__(parent)
        self._pr     = pr
        self._commits = commits
        self._number  = pr.get("number", 0)

        state = pr.get("state", "open")
        if pr.get("merged_at"):
            state = "merged"

        self.setAttribute(Qt.WA_StyledBackground, True)
        self._set_bg(False)

        root = QVBoxLayout(self)
        root.setContentsMargins(12, 10, 12, 10)
        root.setSpacing(6)

        # ── Top row: state dot + title + number ──────────────────────────────
        top = QHBoxLayout()
        top.setSpacing(8)
        top.setContentsMargins(0, 0, 0, 0)

        dot = QLabel("●")
        dot.setFixedWidth(12)
        dot.setStyleSheet(
            f"background: transparent; font-size: 9px;"
            f" color: {_STATE_COLORS.get(state, COLORS['text_muted'])};"
        )
        top.addWidget(dot)

        title = QLabel(pr.get("title", "(untitled)"))
        title.setStyleSheet(
            f"background: transparent; font-size: 13px; font-weight: 600;"
            f" color: {COLORS['text_primary']};"
        )
        title.setWordWrap(True)
        title.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        top.addWidget(title)

        num_lbl = QLabel(f"#{self._number}")
        num_lbl.setStyleSheet(
            f"background: transparent; font-size: 11px; color: {COLORS['text_muted']};"
            f" font-family: monospace;"
        )
        top.addWidget(num_lbl)
        root.addLayout(top)

        # ── Bottom row: author → base branch ← head branch + date ────────────
        bottom = QHBoxLayout()
        bottom.setSpacing(8)
        bottom.setContentsMargins(20, 0, 0, 0)

        author = (pr.get("user") or {}).get("login", "?")
        author_lbl = QLabel(f"@{author}")
        author_lbl.setStyleSheet(
            f"background: transparent; font-size: 11px; color: {COLORS['text_muted']};"
        )
        bottom.addWidget(author_lbl)

        base_ref = (pr.get("base") or {}).get("ref", "main")
        head_ref = (pr.get("head") or {}).get("ref", "")
        branch_text = f"{base_ref} ← {head_ref}"
        if len(branch_text) > 34:
            branch_text = branch_text[:33] + "…"
        branch_lbl = QLabel(branch_text)
        branch_lbl.setStyleSheet(
            f"background: transparent; font-size: 11px; color: {COLORS['accent']};"
            f" font-family: monospace;"
        )
        bottom.addWidget(branch_lbl)
        bottom.addStretch()

        date_str = pr.get("created_at", "")
        date_lbl = QLabel(_relative_date(date_str))
        date_lbl.setStyleSheet(
            f"background: transparent; font-size: 11px; color: {COLORS['text_muted']};"
        )
        bottom.addWidget(date_lbl)
        root.addLayout(bottom)

        # ── Approve button (owner only, open PRs) ─────────────────────────────
        if is_owner and state == "open":
            self._approve_btn = QPushButton("Approve")
            self._approve_btn.setFixedHeight(28)
            self._approve_btn.setCursor(Qt.PointingHandCursor)
            self._approve_btn.setStyleSheet(f"""
                QPushButton {{
                    background: {COLORS['accent_dim']}; border: 1px solid {COLORS['accent']};
                    border-radius: 6px; font-size: 11px; font-weight: 600;
                    color: {COLORS['accent']}; padding: 0 12px;
                }}
                QPushButton:hover {{
                    background: {COLORS['accent']}; color: {COLORS['text_on_accent']};
                }}
            """)
            self._approve_btn.clicked.connect(lambda: self.approve_clicked.emit(self._number))
            root.addWidget(self._approve_btn)
        else:
            self._approve_btn = None

        # Precompute branch shas for hover
        head_ref = (pr.get("head") or {}).get("ref", "")
        head_sha = (pr.get("head") or {}).get("sha", "")
        self._branch_shas = _pr_branch_shas(commits, head_ref, head_sha)

    def _set_bg(self, hovered: bool):
        bg = COLORS["bg_hover"] if hovered else COLORS["bg_card"]
        self.setStyleSheet(f"""
            background: {bg};
            border: 1px solid {COLORS['border']};
            border-radius: 8px;
        """)

    def enterEvent(self, _):
        self._set_bg(True)
        self.hovered.emit(self._branch_shas)

    def leaveEvent(self, _):
        self._set_bg(False)
        self.unhovered.emit()


# ── PR panel ──────────────────────────────────────────────────────────────────

class PullRequestsPanel(QWidget):
    pr_hovered      = pyqtSignal(set)
    pr_cleared      = pyqtSignal()
    close_requested = pyqtSignal()
    _prs_ready      = pyqtSignal(list)   # thread → main: PRs fetched
    _fetch_error    = pyqtSignal()        # thread → main: fetch failed

    def __init__(self, parent=None):
        super().__init__(parent)
        self._visible = False
        self._commits: list = []
        self._is_owner = False
        self._token  = ""
        self._owner  = ""
        self._repo   = ""
        self._filter = "open"

        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setStyleSheet(f"""
            background: {COLORS['bg_card']};
            border-left: 1px solid {COLORS['border']};
        """)
        self.hide()

        self._anim = QPropertyAnimation(self, b"geometry")
        self._anim.setDuration(220)
        self._anim.setEasingCurve(QEasingCurve.OutCubic)

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ── Header ────────────────────────────────────────────────────────────
        hdr = QWidget()
        hdr.setObjectName("prHdr")
        hdr.setAttribute(Qt.WA_StyledBackground, True)
        hdr.setStyleSheet(f"""
            #prHdr {{
                background: {COLORS['bg_secondary']};
                border-bottom: 1px solid {COLORS['border']};
            }}
        """)
        hl = QHBoxLayout(hdr)
        hl.setContentsMargins(16, 12, 12, 12)
        hl.setSpacing(0)

        title_col = QVBoxLayout()
        title_col.setSpacing(2)
        title_col.setAlignment(Qt.AlignVCenter)

        title = QLabel("Pull Requests")
        title.setStyleSheet(
            f"background: transparent; font-size: 14px; font-weight: 700;"
            f" color: {COLORS['text_primary']};"
        )
        title_col.addWidget(title)

        self._protection_lbl = QLabel("")
        self._protection_lbl.setStyleSheet(
            f"background: transparent; font-size: 10px; color: {COLORS['text_muted']};"
        )
        title_col.addWidget(self._protection_lbl)

        hl.addLayout(title_col)
        hl.addStretch()

        close_btn = QPushButton("✕")
        close_btn.setFixedSize(28, 28)
        close_btn.setCursor(Qt.PointingHandCursor)
        close_btn.setStyleSheet(f"""
            QPushButton {{ background: transparent; border: none;
                font-size: 12px; color: {COLORS['text_muted']}; }}
            QPushButton:hover {{ color: {COLORS['text_primary']}; }}
        """)
        close_btn.clicked.connect(self.hide_panel)
        hl.addWidget(close_btn)
        root.addWidget(hdr)

        # ── Filter tabs: Open / Closed / All ─────────────────────────────────
        filter_bar = QWidget()
        filter_bar.setAttribute(Qt.WA_StyledBackground, True)
        filter_bar.setFixedHeight(36)
        filter_bar.setStyleSheet(f"""
            background: {COLORS['bg_primary']};
            border-bottom: 1px solid {COLORS['border']};
        """)
        fl = QHBoxLayout(filter_bar)
        fl.setContentsMargins(12, 0, 12, 0)
        fl.setSpacing(4)
        self._filter_btns: dict[str, QPushButton] = {}
        for key, label in [("open", "Open"), ("closed", "Closed"), ("all", "All")]:
            btn = QPushButton(label)
            btn.setFixedHeight(26)
            btn.setCursor(Qt.PointingHandCursor)
            btn.setCheckable(True)
            btn.setChecked(key == "open")
            btn.setStyleSheet(self._filter_btn_style(key == "open"))
            btn.clicked.connect(lambda _, k=key: self._set_filter(k))
            fl.addWidget(btn)
            self._filter_btns[key] = btn
        fl.addStretch()
        root.addWidget(filter_bar)

        # ── Status label (outside scroll — no layout thrashing) ───────────────
        self._status_lbl = QLabel("Loading…")
        self._status_lbl.setAlignment(Qt.AlignCenter)
        self._status_lbl.setWordWrap(True)
        self._status_lbl.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self._status_lbl.setStyleSheet(
            f"background: transparent; font-size: 13px; color: {COLORS['text_muted']};"
        )
        root.addWidget(self._status_lbl)

        # ── Scroll list ───────────────────────────────────────────────────────
        scroll = _VScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setStyleSheet(f"""
            QScrollArea {{ background: transparent; border: none; }}
            QScrollBar:vertical {{
                background: transparent; width: 4px; margin: 0;
            }}
            QScrollBar::handle:vertical {{
                background: {COLORS['border']}; border-radius: 2px; min-height: 20px;
            }}
            QScrollBar::handle:vertical:hover {{ background: {COLORS['text_muted']}; }}
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
        """)
        self._list_container = QWidget()
        self._list_container.setStyleSheet("background: transparent;")
        self._list_layout = QVBoxLayout(self._list_container)
        self._list_layout.setContentsMargins(12, 12, 12, 12)
        self._list_layout.setSpacing(8)
        self._list_layout.addStretch()
        scroll.setWidget(self._list_container)
        scroll.viewport().setStyleSheet("background: transparent;")
        self._scroll = scroll
        self._scroll.hide()
        root.addWidget(self._scroll)

        self._all_prs: list[dict] = []
        self._prs_ready.connect(self._on_prs_loaded)
        self._fetch_error.connect(lambda: self._status_lbl.setText("Error"))

    # ── Public ────────────────────────────────────────────────────────────────

    def set_protection(self, enabled: bool):
        if enabled:
            self._protection_lbl.setText("● Branch protection enabled")
            self._protection_lbl.setStyleSheet(
                f"background: transparent; font-size: 10px; color: {COLORS['accent']};"
            )
        else:
            self._protection_lbl.setText("○ Branch protection disabled")
            self._protection_lbl.setStyleSheet(
                f"background: transparent; font-size: 10px; color: {COLORS['text_muted']};"
            )

    def update_commits(self, commits: list):
        """Refresh the commit list used for hover highlighting without re-fetching PRs."""
        self._commits = commits

    def load(self, tracker, user: dict, is_owner: bool, token: str, commits: list):
        self._commits   = commits
        self._is_owner  = is_owner
        self._token     = token
        self._all_prs   = []

        url = tracker.remote_url() if tracker else ""
        m = re.search(r'github\.com[:/]([^/]+)/([^/]+?)(?:\.git)?$', url)
        if m:
            self._owner = m.group(1)
            self._repo  = m.group(2)

        self._clear_rows()
        self._scroll.hide()
        self._status_lbl.setText("Loading…")
        self._status_lbl.show()

        if self._owner and self._repo and token:
            threading.Thread(target=self._fetch_prs, daemon=True).start()
        else:
            self._status_lbl.setText("No GitHub remote found.")

    def show_panel(self):
        self._place(True, True)

    def hide_panel(self):
        self.pr_cleared.emit()
        was_visible = self._visible
        self._place(False, True)
        if was_visible:
            self.close_requested.emit()

    def reposition(self):
        self._place(self._visible, False)

    # ── Internal ──────────────────────────────────────────────────────────────

    def _place(self, visible: bool, animate: bool):
        self._visible = visible
        p = self.parent()
        if not p:
            return
        h = p.height()
        x_shown  = p.width() - PANEL_W
        x_hidden = p.width()
        target = QRect(x_shown if visible else x_hidden, 0, PANEL_W, h)
        if animate:
            self._anim.stop()
            self._anim.setStartValue(self.geometry())
            self._anim.setEndValue(target)
            if visible:
                self.show()
            else:
                self._anim.finished.connect(self._on_hide_done)
            self._anim.start()
        else:
            self.setGeometry(target)
            self.setVisible(visible)

    def _on_hide_done(self):
        self.hide()
        try:
            self._anim.finished.disconnect(self._on_hide_done)
        except Exception:
            pass

    def _filter_btn_style(self, active: bool) -> str:
        if active:
            return f"""
                QPushButton {{
                    background: {COLORS['accent_dim']}; border: 1px solid {COLORS['accent']};
                    border-radius: 5px; font-size: 11px; font-weight: 600;
                    color: {COLORS['accent']}; padding: 0 10px;
                }}
            """
        return f"""
            QPushButton {{
                background: transparent; border: none;
                border-radius: 5px; font-size: 11px;
                color: {COLORS['text_muted']}; padding: 0 10px;
            }}
            QPushButton:hover {{ color: {COLORS['text_primary']}; }}
        """

    def _set_filter(self, key: str):
        self._filter = key
        for k, btn in self._filter_btns.items():
            btn.setChecked(k == key)
            btn.setStyleSheet(self._filter_btn_style(k == key))
        self._render_prs()

    def _fetch_prs(self):
        try:
            r = requests.get(
                f"https://api.github.com/repos/{self._owner}/{self._repo}/pulls",
                params={"state": "all", "per_page": 50},
                headers={"Authorization": f"Bearer {self._token}",
                         "Accept": "application/vnd.github+json"},
                timeout=15,
            )
            if r.status_code == 200:
                self._prs_ready.emit(r.json())
            else:
                self._fetch_error.emit()
        except Exception:
            self._fetch_error.emit()

    def _on_prs_loaded(self, prs: list[dict]):
        self._all_prs = prs
        self._render_prs()

    def _render_prs(self):
        self._clear_rows()

        filtered = [pr for pr in self._all_prs if self._matches_filter(pr)]

        if not filtered:
            self._status_lbl.setText(f"No {self._filter} pull requests.")
            self._status_lbl.show()
            self._scroll.hide()
            return

        self._status_lbl.hide()
        self._scroll.show()
        for pr in filtered:
            row = _PRRow(pr, self._commits, self._is_owner)
            row.hovered.connect(self.pr_hovered)
            row.unhovered.connect(self.pr_cleared)
            row.approve_clicked.connect(self._approve_pr)
            self._list_layout.insertWidget(self._list_layout.count() - 1, row)

    def _matches_filter(self, pr: dict) -> bool:
        if self._filter == "all":
            return True
        if self._filter == "open":
            return pr.get("state") == "open"
        if self._filter == "closed":
            return pr.get("state") == "closed" or bool(pr.get("merged_at"))
        return True

    def _clear_rows(self):
        while self._list_layout.count() > 1:
            item = self._list_layout.takeAt(0)
            w = item.widget()
            if w:
                w.setParent(None)

    def _approve_pr(self, pr_number: int):
        if not self._is_owner:
            return
        threading.Thread(
            target=self._submit_approval, args=(pr_number,), daemon=True
        ).start()

    def _submit_approval(self, pr_number: int):
        try:
            r = requests.post(
                f"https://api.github.com/repos/{self._owner}/{self._repo}"
                f"/pulls/{pr_number}/reviews",
                json={"event": "APPROVE"},
                headers={"Authorization": f"Bearer {self._token}",
                         "Accept": "application/vnd.github+json"},
                timeout=15,
            )
            ok = r.status_code in (200, 201)
            msg = "Approved!" if ok else "Approval failed — check permissions."
            QTimer.singleShot(0, lambda m=msg: self._flash_status(m))
        except Exception:
            QTimer.singleShot(0, lambda: self._flash_status("Network error."))

    def _flash_status(self, msg: str):
        self._status_lbl.setText(msg)
        self._status_lbl.show()
        QTimer.singleShot(3000, self._status_lbl.hide)

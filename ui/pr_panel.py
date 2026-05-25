"""Pull Requests inbox — lives in the Collaboration tab."""
from __future__ import annotations

import re
import threading
from datetime import datetime, timezone

import requests

from PyQt5.QtCore import Qt, QTimer, pyqtSignal
from PyQt5.QtGui import QColor, QBrush, QPainter, QPixmap
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QScrollArea, QFrame, QSizePolicy,
)
from styles.theme import COLORS


# ── Helpers ───────────────────────────────────────────────────────────────────

_STATE_COLORS = {
    "open":   "#3ecf8e",
    "closed": "#666666",
    "merged": "#8b5cf6",
}

_CAN_MERGE = {"owner", "admin", "maintain"}


def _relative_date(iso: str) -> str:
    try:
        dt = datetime.fromisoformat(iso.replace("Z", "+00:00"))
        delta = datetime.now(timezone.utc) - dt
        s = delta.total_seconds()
        if s < 3600:  return f"{int(s // 60)}m ago"
        if s < 86400: return f"{int(s // 3600)}h ago"
        return f"{int(s // 86400)}d ago"
    except Exception:
        return ""


def _pr_state(pr: dict) -> str:
    """Return 'open', 'merged', or 'closed'."""
    if pr.get("merged_at"):
        return "merged"
    return pr.get("state", "open")


def _pr_branch_shas(commits, head_ref: str, head_sha: str) -> set[str]:
    """Return SHAs that belong to this PR's branch (for canvas dimming)."""
    by_branch = {c.sha for c in commits if c.branch == head_ref}
    if by_branch:
        return by_branch
    sha_map = {c.sha: c for c in commits}
    result: set[str] = set()
    queue = [head_sha]
    while queue:
        sha = queue.pop()
        if sha in result or sha not in sha_map:
            continue
        result.add(sha)
        queue.extend(sha_map[sha].parents[:1])
    return result


def _action_btn(text: str, accent: bool = True) -> QPushButton:
    btn = QPushButton(text)
    btn.setFixedHeight(28)
    btn.setCursor(Qt.PointingHandCursor)
    if accent:
        btn.setStyleSheet(f"""
            QPushButton {{
                background: {COLORS['accent_dim']}; border: 1px solid {COLORS['accent']};
                border-radius: 6px; font-size: 11px; font-weight: 600;
                color: {COLORS['accent']}; padding: 0 12px;
            }}
            QPushButton:hover {{
                background: {COLORS['accent']}; color: white;
            }}
        """)
    else:
        btn.setStyleSheet(f"""
            QPushButton {{
                background: transparent; border: 1px solid {COLORS['border']};
                border-radius: 6px; font-size: 11px; font-weight: 500;
                color: {COLORS['text_muted']}; padding: 0 12px;
            }}
            QPushButton:hover {{
                border-color: {COLORS['text_secondary']};
                color: {COLORS['text_primary']};
            }}
        """)
    return btn


# ── PR Row ────────────────────────────────────────────────────────────────────

class _PRRow(QWidget):
    hovered          = pyqtSignal(set)   # SHAs to keep bright
    unhovered        = pyqtSignal()
    approve_clicked  = pyqtSignal(int)   # pr number
    merge_clicked    = pyqtSignal(dict)  # full PR dict
    close_clicked    = pyqtSignal(int)   # pr number

    def __init__(self, pr: dict, commits: list, user_role: str, parent=None):
        super().__init__(parent)
        self._pr        = pr
        self._commits   = commits
        self._number    = pr.get("number", 0)
        self._user_role = user_role
        state           = _pr_state(pr)

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

        # ── Bottom row: author + branch flow + date ───────────────────────────
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
        branch_text = f"{head_ref} → {base_ref}"
        if len(branch_text) > 36:
            branch_text = branch_text[:35] + "…"
        branch_lbl = QLabel(branch_text)
        branch_lbl.setStyleSheet(
            f"background: transparent; font-size: 11px; color: {COLORS['accent']};"
            f" font-family: monospace;"
        )
        bottom.addWidget(branch_lbl)
        bottom.addStretch()

        date_str = pr.get("updated_at") or pr.get("created_at", "")
        date_lbl = QLabel(_relative_date(date_str))
        date_lbl.setStyleSheet(
            f"background: transparent; font-size: 11px; color: {COLORS['text_muted']};"
        )
        bottom.addWidget(date_lbl)
        root.addLayout(bottom)

        # ── Action buttons (role-gated) ───────────────────────────────────────
        can_act = user_role in _CAN_MERGE
        if state == "open" and can_act:
            btn_row = QHBoxLayout()
            btn_row.setSpacing(6)
            btn_row.setContentsMargins(20, 2, 0, 0)

            approve_btn = _action_btn("✓  Approve", accent=True)
            approve_btn.clicked.connect(lambda: self.approve_clicked.emit(self._number))
            btn_row.addWidget(approve_btn)

            merge_btn = _action_btn("⤵  Merge", accent=True)
            merge_btn.clicked.connect(lambda: self.merge_clicked.emit(self._pr))
            btn_row.addWidget(merge_btn)

            close_btn = _action_btn("✕  Close", accent=False)
            close_btn.clicked.connect(lambda: self.close_clicked.emit(self._number))
            btn_row.addWidget(close_btn)

            btn_row.addStretch()
            root.addLayout(btn_row)

        # Precompute branch SHAs for hover dimming
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


# ── Scroll area ───────────────────────────────────────────────────────────────

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


# ── PR Inbox ──────────────────────────────────────────────────────────────────

class PullRequestsPanel(QWidget):
    """Full-page PR inbox shown in the Collaboration tab."""

    pr_hovered       = pyqtSignal(set)    # canvas: keep these SHAs bright
    pr_cleared       = pyqtSignal()       # canvas: clear highlight
    merge_requested  = pyqtSignal(dict)   # → commit_view: handle merge + conflict check
    _prs_ready       = pyqtSignal(list)   # thread → main
    _fetch_error     = pyqtSignal()       # thread → main
    _action_done     = pyqtSignal(bool, str)   # thread → main: ok, message

    def __init__(self, parent=None):
        super().__init__(parent)
        self._commits:            list  = []
        self._user_role:          str   = "write"
        self._protection_enabled: bool  = False
        self._token:     str   = ""
        self._owner:     str   = ""
        self._repo:      str   = ""
        self._filter:    str   = "open"
        self._all_prs:   list  = []

        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setStyleSheet(f"background: {COLORS['bg_primary']};")

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ── Header ────────────────────────────────────────────────────────────
        hdr = QWidget()
        hdr.setObjectName("prInboxHdr")
        hdr.setAttribute(Qt.WA_StyledBackground, True)
        hdr.setStyleSheet(f"""
            #prInboxHdr {{
                background: {COLORS['bg_secondary']};
                border-bottom: 1px solid {COLORS['border']};
            }}
        """)
        hl = QHBoxLayout(hdr)
        hl.setContentsMargins(20, 14, 16, 14)
        hl.setSpacing(0)

        title = QLabel("Pull Requests")
        title.setStyleSheet(
            f"background: transparent; font-size: 16px; font-weight: 700;"
            f" color: {COLORS['text_primary']};"
        )
        hl.addWidget(title)
        hl.addStretch()

        self._refresh_btn = QPushButton("↻  Refresh")
        self._refresh_btn.setFixedHeight(30)
        self._refresh_btn.setCursor(Qt.PointingHandCursor)
        self._refresh_btn.setStyleSheet(f"""
            QPushButton {{
                background: transparent; border: 1px solid {COLORS['border']};
                border-radius: 6px; font-size: 11px; font-weight: 600;
                color: {COLORS['text_muted']}; padding: 0 12px;
            }}
            QPushButton:hover {{
                border-color: {COLORS['accent']}; color: {COLORS['accent']};
            }}
        """)
        self._refresh_btn.clicked.connect(self._do_refresh)
        hl.addWidget(self._refresh_btn)
        root.addWidget(hdr)

        # ── Filter tabs: Open / Closed / Merged ───────────────────────────────
        filter_bar = QWidget()
        filter_bar.setAttribute(Qt.WA_StyledBackground, True)
        filter_bar.setFixedHeight(40)
        filter_bar.setStyleSheet(f"""
            background: {COLORS['bg_primary']};
            border-bottom: 1px solid {COLORS['border']};
        """)
        fl = QHBoxLayout(filter_bar)
        fl.setContentsMargins(20, 0, 20, 0)
        fl.setSpacing(4)
        self._filter_btns: dict[str, QPushButton] = {}
        for key, label in [("open", "Open"), ("closed", "Closed"), ("merged", "Merged")]:
            btn = QPushButton(label)
            btn.setFixedHeight(28)
            btn.setCursor(Qt.PointingHandCursor)
            btn.setCheckable(True)
            btn.setChecked(key == "open")
            btn.setStyleSheet(self._filter_style(key == "open"))
            btn.clicked.connect(lambda _, k=key: self._set_filter(k))
            fl.addWidget(btn)
            self._filter_btns[key] = btn
        fl.addStretch()
        root.addWidget(filter_bar)

        # ── Status label ──────────────────────────────────────────────────────
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
        self._list_layout.setContentsMargins(20, 16, 20, 16)
        self._list_layout.setSpacing(8)
        self._list_layout.addStretch()
        scroll.setWidget(self._list_container)
        scroll.viewport().setStyleSheet("background: transparent;")
        self._scroll = scroll
        self._scroll.hide()
        root.addWidget(self._scroll)

        self._prs_ready.connect(self._on_prs_loaded)
        self._fetch_error.connect(lambda: self._show_status("Could not load pull requests."))
        self._action_done.connect(self._on_action_done)

    # ── Public ────────────────────────────────────────────────────────────────

    def load(self, tracker, user: dict, user_role: str, token: str, commits: list):
        """Load the PR inbox for a repo. user_role: 'owner'|'admin'|'maintain'|'write'|'read'."""
        self._commits   = commits
        self._user_role = user_role
        self._token     = token
        self._all_prs   = []

        url = tracker.remote_url() if tracker else ""
        m = re.search(r'github\.com[:/]([^/]+)/([^/]+?)(?:\.git)?$', url)
        if m:
            self._owner = m.group(1)
            self._repo  = m.group(2)

        self._clear_rows()
        self._scroll.hide()
        self._show_status("Loading…")

        if self._owner and self._repo and token:
            threading.Thread(target=self._fetch_prs, daemon=True).start()
        else:
            self._show_status("No GitHub remote found.")

    def update_commits(self, commits: list):
        """Refresh commits for hover highlighting without re-fetching PRs."""
        self._commits = commits

    def set_user_role(self, role: str):
        """Update the current user's role (re-renders rows)."""
        self._user_role = role
        if self._all_prs:
            self._render_prs()

    # ── Internal ──────────────────────────────────────────────────────────────

    def _do_refresh(self):
        self._clear_rows()
        self._scroll.hide()
        self._show_status("Loading…")
        if self._owner and self._repo and self._token:
            threading.Thread(target=self._fetch_prs, daemon=True).start()

    def _show_status(self, msg: str):
        self._status_lbl.setText(msg)
        self._status_lbl.show()

    def _filter_style(self, active: bool) -> str:
        if active:
            return f"""
                QPushButton {{
                    background: {COLORS['accent_dim']}; border: 1px solid {COLORS['accent']};
                    border-radius: 5px; font-size: 11px; font-weight: 600;
                    color: {COLORS['accent']}; padding: 0 12px;
                }}
            """
        return f"""
            QPushButton {{
                background: transparent; border: none;
                border-radius: 5px; font-size: 11px;
                color: {COLORS['text_muted']}; padding: 0 12px;
            }}
            QPushButton:hover {{ color: {COLORS['text_primary']}; }}
        """

    def _set_filter(self, key: str):
        self._filter = key
        for k, btn in self._filter_btns.items():
            btn.setChecked(k == key)
            btn.setStyleSheet(self._filter_style(k == key))
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

    def _on_prs_loaded(self, prs: list):
        self._all_prs = prs
        self._render_prs()

    def _render_prs(self):
        self._clear_rows()
        filtered = [pr for pr in self._all_prs if _pr_state(pr) == self._filter]

        if not filtered:
            labels = {"open": "open", "closed": "closed", "merged": "merged"}
            self._show_status(f"No {labels.get(self._filter, '')} pull requests.")
            self._scroll.hide()
            return

        self._status_lbl.hide()
        self._scroll.show()
        for pr in filtered:
            # When protection is off, all collaborators are treated as admins.
            effective_role = ("admin" if not self._protection_enabled
                              and self._user_role not in _CAN_MERGE
                              else self._user_role)
            row = _PRRow(pr, self._commits, effective_role)
            row.hovered.connect(self.pr_hovered)
            row.unhovered.connect(self.pr_cleared)
            row.approve_clicked.connect(self._on_approve)
            row.merge_clicked.connect(self.merge_requested)   # commit_view handles this
            row.close_clicked.connect(self._on_close)
            self._list_layout.insertWidget(self._list_layout.count() - 1, row)

    def _clear_rows(self):
        while self._list_layout.count() > 1:
            item = self._list_layout.takeAt(0)
            w = item.widget()
            if w:
                w.setParent(None)

    # ── GitHub actions ────────────────────────────────────────────────────────

    def _on_approve(self, pr_number: int):
        if self._user_role not in _CAN_MERGE and self._protection_enabled:
            return
        threading.Thread(target=self._submit_approve, args=(pr_number,), daemon=True).start()

    def _submit_approve(self, pr_number: int):
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
            msg = "PR approved." if ok else f"Approval failed ({r.status_code})."
            self._action_done.emit(ok, msg)
        except Exception:
            self._action_done.emit(False, "Network error.")

    def _on_close(self, pr_number: int):
        if self._user_role not in _CAN_MERGE and self._protection_enabled:
            return
        threading.Thread(target=self._submit_close, args=(pr_number,), daemon=True).start()

    def _submit_close(self, pr_number: int):
        try:
            r = requests.patch(
                f"https://api.github.com/repos/{self._owner}/{self._repo}"
                f"/pulls/{pr_number}",
                json={"state": "closed"},
                headers={"Authorization": f"Bearer {self._token}",
                         "Accept": "application/vnd.github+json"},
                timeout=15,
            )
            ok = r.status_code == 200
            msg = "PR closed." if ok else f"Close failed ({r.status_code})."
            self._action_done.emit(ok, msg)
            if ok:
                # Refresh the list to move it to Closed tab
                QTimer.singleShot(500, self._do_refresh)
        except Exception:
            self._action_done.emit(False, "Network error.")

    def merge_via_api(self, pr: dict):
        """Called by commit_view after conflict check passes (no conflicts)."""
        pr_number = pr.get("number", 0)
        threading.Thread(target=self._submit_merge, args=(pr_number,), daemon=True).start()

    def _submit_merge(self, pr_number: int):
        try:
            r = requests.put(
                f"https://api.github.com/repos/{self._owner}/{self._repo}"
                f"/pulls/{pr_number}/merge",
                json={"merge_method": "merge"},
                headers={"Authorization": f"Bearer {self._token}",
                         "Accept": "application/vnd.github+json"},
                timeout=15,
            )
            ok = r.status_code in (200, 201)
            msg = "PR merged successfully." if ok else f"Merge failed ({r.status_code})."
            self._action_done.emit(ok, msg)
            if ok:
                QTimer.singleShot(500, self._do_refresh)
        except Exception:
            self._action_done.emit(False, "Network error.")

    def _on_action_done(self, ok: bool, msg: str):
        self._show_status(msg)
        QTimer.singleShot(3000, lambda: self._status_lbl.hide()
                          if self._status_lbl.text() == msg else None)

    # ── Kept for backward compat with commit_view signal connections ──────────
    def set_protection(self, enabled: bool):
        """Store protection state; re-render rows so action buttons reflect admin elevation."""
        self._protection_enabled = enabled
        if self._all_prs:
            self._render_prs()

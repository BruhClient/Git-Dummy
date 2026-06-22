"""Pull Requests inbox — lives in the Collaboration tab."""
from __future__ import annotations

import re
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

import requests

import qtawesome as qta

from PyQt5.QtCore import Qt, QSize, QTimer, pyqtSignal

from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QScrollArea, QFrame, QSizePolicy,
)
from styles.theme import COLORS, scrollbar_style


# ── Helpers ───────────────────────────────────────────────────────────────────

_STATE_COLORS = {
    "open":   "#3ecf8e",
    "closed": COLORS["text_muted"],
    "merged": "#8b5cf6",
}

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




# ── PR Row ────────────────────────────────────────────────────────────────────

def _pill_style(color: str, fill: bool = False) -> str:
    if fill:
        return f"""
            QPushButton {{
                background: {color}; border: none; border-radius: 12px;
                font-size: 11px; font-weight: 600; font-family: 'Tilt Warp';
                color: {COLORS['text_on_accent']}; padding: 0 14px;
            }}
            QPushButton:hover {{ opacity: 0.85; }}
        """
    return f"""
        QPushButton {{
            background: transparent; border: 1px solid {color}; border-radius: 12px;
            font-size: 11px; font-weight: 600; font-family: 'Tilt Warp';
            color: {color}; padding: 0 14px;
        }}
        QPushButton:hover {{ background: {color}; color: {COLORS['text_on_accent']}; }}
    """


class _PRRow(QWidget):
    hovered          = pyqtSignal(set)   # SHAs to keep bright
    unhovered        = pyqtSignal()
    approve_clicked  = pyqtSignal(int)   # pr number
    merge_clicked    = pyqtSignal(dict)  # full PR dict
    close_clicked    = pyqtSignal(int)   # pr number
    _detail_ready    = pyqtSignal(dict)  # thread → main

    def __init__(self, pr: dict, commits: list, token: str = "", owner: str = "", repo: str = "",
                 required_approvals: int = 0, parent=None):
        super().__init__(parent)
        self._pr      = pr
        self._commits = commits
        self._number  = pr.get("number", 0)
        self._token   = token
        self._owner   = owner
        self._repo    = repo
        self._required_approvals = required_approvals
        self._expanded = False
        self._detail_fetched = False
        state         = _pr_state(pr)

        self.setObjectName("prRow")
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setCursor(Qt.PointingHandCursor)
        self._set_bg(False)

        root = QVBoxLayout(self)
        root.setContentsMargins(16, 10, 16, 10)
        root.setSpacing(4)

        _lbl_base = "background: transparent; border: none;"

        # ── Row 1: title + #number · date ────────────────────────────────────
        top = QHBoxLayout()
        top.setSpacing(8)
        top.setContentsMargins(0, 0, 0, 0)

        title = QLabel(pr.get("title", "(untitled)"))
        title.setStyleSheet(
            f"{_lbl_base} font-size: 13px; font-weight: 600; font-family: 'Tilt Warp';"
            f" color: {COLORS['text_primary']};"
        )
        title.setWordWrap(True)
        title.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        top.addWidget(title)

        date_str = pr.get("updated_at") or pr.get("created_at", "")
        meta_lbl = QLabel(f"#{self._number}  ·  {_relative_date(date_str)}")
        meta_lbl.setStyleSheet(f"{_lbl_base} font-size: 11px; color: {COLORS['text_muted']};")
        top.addWidget(meta_lbl)
        root.addLayout(top)

        # ── Row 2: author + branch + conflict badge + action buttons ─────────
        bottom = QHBoxLayout()
        bottom.setSpacing(8)
        bottom.setContentsMargins(0, 0, 0, 0)

        author = (pr.get("user") or {}).get("login", "?")
        author_lbl = QLabel(f"@{author}")
        author_lbl.setStyleSheet(f"{_lbl_base} font-size: 11px; color: {COLORS['text_muted']};")
        bottom.addWidget(author_lbl)

        base_ref = (pr.get("base") or {}).get("ref", "main")
        head_ref = (pr.get("head") or {}).get("ref", "")
        branch_text = f"{head_ref} → {base_ref}"
        if len(branch_text) > 36:
            branch_text = branch_text[:35] + "…"
        branch_lbl = QLabel(branch_text)
        branch_lbl.setStyleSheet(
            f"{_lbl_base} font-size: 11px; color: {COLORS['accent']}; font-family: monospace;"
        )
        bottom.addWidget(branch_lbl)

        _loading_style = f"{_lbl_base} font-size: 11px; color: {COLORS['text_muted']}; font-style: italic;"

        self._conflict_badge = QLabel()
        self._conflict_badge.setStyleSheet(f"{_lbl_base} font-size: 11px;")
        bottom.addWidget(self._conflict_badge)

        self._meta_lbl = QLabel()
        self._meta_lbl.setStyleSheet(f"{_lbl_base} font-size: 11px;")
        bottom.addWidget(self._meta_lbl)

        if state == "open":
            self._conflict_badge.setText("Loading…")
            self._conflict_badge.setStyleSheet(_loading_style)
        else:
            self._meta_lbl.setText("Loading…")
            self._meta_lbl.setStyleSheet(_loading_style)

        self._approval_status_lbl = QLabel()
        self._approval_status_lbl.setStyleSheet(f"{_lbl_base} font-size: 11px; color: {COLORS['text_muted']};")
        bottom.addWidget(self._approval_status_lbl)

        bottom.addStretch()

        self._approve_btn = None
        self._merge_btn = None
        self._close_btn = None
        if state == "open":
            self._approve_btn = QPushButton("Approve")
            self._approve_btn.setFixedHeight(24)
            self._approve_btn.setCursor(Qt.PointingHandCursor)
            self._approve_btn.setStyleSheet(_pill_style(COLORS['accent']))
            self._approve_btn.clicked.connect(lambda: self.approve_clicked.emit(self._number))
            bottom.addWidget(self._approve_btn)

            self._merge_btn = QPushButton("Merge")
            self._merge_btn.setFixedHeight(24)
            self._merge_btn.setCursor(Qt.PointingHandCursor)
            self._merge_btn.setStyleSheet(_pill_style("#3ecf8e", fill=True))
            self._merge_btn.clicked.connect(lambda: self.merge_clicked.emit(self._pr))
            bottom.addWidget(self._merge_btn)

            self._close_btn = QPushButton("Close")
            self._close_btn.setFixedHeight(24)
            self._close_btn.setCursor(Qt.PointingHandCursor)
            self._close_btn.setStyleSheet(_pill_style(COLORS['text_muted']))
            self._close_btn.clicked.connect(lambda: self.close_clicked.emit(self._number))
            bottom.addWidget(self._close_btn)

            if self._required_approvals > 0:
                self._merge_btn.hide()
            else:
                self._approve_btn.hide()

        root.addLayout(bottom)

        # ── Expandable detail section (hidden by default) ────────────────────
        self._detail_widget = QWidget()
        self._detail_widget.setStyleSheet(f"{_lbl_base}")
        self._detail_widget.hide()
        dl = QVBoxLayout(self._detail_widget)
        dl.setContentsMargins(0, 8, 0, 2)
        dl.setSpacing(6)

        sep = QWidget()
        sep.setFixedHeight(1)
        sep.setStyleSheet(f"background: {COLORS['border']}; border: none;")
        dl.addWidget(sep)

        self._desc_lbl = QLabel()
        self._desc_lbl.setWordWrap(True)
        self._desc_lbl.setStyleSheet(
            f"{_lbl_base} font-size: 12px; color: {COLORS['text_secondary']}; padding: 2px 0;"
        )
        dl.addWidget(self._desc_lbl)

        self._status_row = QHBoxLayout()
        self._status_row.setSpacing(12)
        self._status_row.setContentsMargins(0, 0, 0, 0)

        self._files_lbl = QLabel()
        self._files_lbl.setStyleSheet(f"{_lbl_base} font-size: 11px; color: {COLORS['text_muted']};")
        self._status_row.addWidget(self._files_lbl)

        self._reviewers_lbl = QLabel()
        self._reviewers_lbl.setStyleSheet(f"{_lbl_base} font-size: 11px; color: {COLORS['text_muted']};")
        self._status_row.addWidget(self._reviewers_lbl)
        self._status_row.addStretch()
        dl.addLayout(self._status_row)

        root.addWidget(self._detail_widget)

        head_sha = (pr.get("head") or {}).get("sha", "")
        self._branch_shas = _pr_branch_shas(commits, head_ref, head_sha)

        self._detail_ready.connect(self._apply_detail)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton:
            child = self.childAt(event.pos())
            if not isinstance(child, QPushButton):
                self._toggle_expand()
        super().mouseReleaseEvent(event)

    def _toggle_expand(self):
        self._expanded = not self._expanded
        self._detail_widget.setVisible(self._expanded)
        if self._expanded and not self._desc_lbl.text():
            body = self._pr.get("body") or ""
            self._desc_lbl.setText(body if body else "No description.")

    def _fetch_detail(self):
        try:
            headers = {"Authorization": f"Bearer {self._token}",
                       "Accept": "application/vnd.github+json"}
            base = f"https://api.github.com/repos/{self._owner}/{self._repo}"
            r = requests.get(f"{base}/pulls/{self._number}", headers=headers, timeout=10)
            if r.status_code != 200:
                return
            data = r.json()
            state = _pr_state(self._pr)
            if state in ("merged", "open"):
                rv = requests.get(f"{base}/pulls/{self._number}/reviews", headers=headers, timeout=10)
                if rv.status_code == 200:
                    approvers = [rev["user"]["login"] for rev in rv.json()
                                 if rev.get("state") == "APPROVED"]
                    data["_approvers"] = list(dict.fromkeys(approvers))
            if state == "closed":
                ev = requests.get(f"{base}/issues/{self._number}/events", headers=headers, timeout=10)
                if ev.status_code == 200:
                    for e in reversed(ev.json()):
                        if e.get("event") == "closed":
                            data["_closed_by"] = (e.get("actor") or {}).get("login", "")
                            break
            self._detail_ready.emit(data)
        except Exception:
            pass

    def _apply_detail(self, data: dict):
        self._detail_fetched = True
        _base = "background: transparent; border: none; font-size: 11px;"
        mergeable = data.get("mergeable")
        if mergeable is True:
            self._conflict_badge.setText("No conflicts")
            self._conflict_badge.setStyleSheet(f"{_base} color: #3ecf8e;")
        elif mergeable is False:
            self._conflict_badge.setText("Has conflicts")
            self._conflict_badge.setStyleSheet(f"{_base} color: #ef4444;")
        else:
            self._conflict_badge.setText("")

        body = data.get("body") or ""
        self._desc_lbl.setText(body if body else "No description.")

        changed = data.get("changed_files", 0)
        adds = data.get("additions", 0)
        dels = data.get("deletions", 0)
        self._files_lbl.setText(f"{changed} file{'s' if changed != 1 else ''}  +{adds} −{dels}")

        reviewers = data.get("requested_reviewers") or []
        if reviewers:
            names = ", ".join(r.get("login", "?") for r in reviewers[:3])
            self._reviewers_lbl.setText(f"Reviewers: {names}")

        approvers = data.get("_approvers", [])
        merged_by = (data.get("merged_by") or {}).get("login", "")
        closed_by = data.get("_closed_by", "")
        state = _pr_state(self._pr)

        if state == "open":
            got = len(approvers)
            need = self._required_approvals
            if need > 0 and got < need:
                remaining = need - got
                s = "s" if remaining != 1 else ""
                self._approval_status_lbl.setText(f"{remaining} approval{s} required")
                self._approval_status_lbl.setStyleSheet(f"{_base} color: #f59e0b; font-weight: 600;")
                if self._merge_btn:
                    self._merge_btn.hide()
            else:
                self._approval_status_lbl.setText("Ready to merge")
                self._approval_status_lbl.setStyleSheet(f"{_base} color: #22d3ee; font-weight: 600;")
                if self._approve_btn:
                    self._approve_btn.hide()
                if self._merge_btn:
                    self._merge_btn.show()

        if approvers:
            self._meta_lbl.setText(f"Approved by @{', @'.join(approvers[:2])}")
            self._meta_lbl.setStyleSheet(f"{_base} color: #3ecf8e;")
            if merged_by:
                self._reviewers_lbl.setText(f"Approved by @{', @'.join(approvers)}  ·  Merged by @{merged_by}")
        elif merged_by:
            self._meta_lbl.setText(f"Merged by @{merged_by}")
            self._meta_lbl.setStyleSheet(f"{_base} color: #8b5cf6;")
        elif closed_by:
            self._meta_lbl.setText(f"Closed by @{closed_by}")
            self._meta_lbl.setStyleSheet(f"{_base} color: {COLORS['text_muted']};")

    def fetch_detail(self):
        if self._token and self._owner and self._repo and not self._detail_fetched:
            threading.Thread(target=self._fetch_detail, daemon=True).start()

    def _set_bg(self, hovered: bool):
        bg = COLORS["bg_hover"] if hovered else COLORS["bg_card"]
        self.setStyleSheet(
            f"#prRow {{ background: {bg}; border: 1px solid {COLORS['border']}; border-radius: 8px; }}"
        )

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
    toast_requested  = pyqtSignal(str, str)  # → commit_view: (message, kind)
    _prs_ready       = pyqtSignal(list)   # thread → main
    _fetch_error     = pyqtSignal()       # thread → main
    _action_done     = pyqtSignal(bool, str)   # thread → main: ok, message

    def __init__(self, parent=None):
        super().__init__(parent)
        self._commits:  list = []
        self._token:    str  = ""
        self._owner:     str   = ""
        self._repo:      str   = ""
        self._filter:    str   = "open"
        self._all_prs:   list  = []
        self._required_approvals: int = 0
        self._detail_pool = ThreadPoolExecutor(max_workers=3)

        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setStyleSheet(f"background: {COLORS['bg_primary']};")

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ── Filter tabs: Open / Closed / Merged + refresh icon ─────────────────
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
            btn = QPushButton(f"  {label}")
            btn.setFixedHeight(28)
            btn.setCursor(Qt.PointingHandCursor)
            btn.setCheckable(True)
            btn.setChecked(key == "open")
            dot_color = _STATE_COLORS.get(key, COLORS['text_muted'])
            btn.setIcon(qta.icon("fa5s.circle", color=dot_color, scale_factor=0.4))
            btn.setIconSize(QSize(8, 8))
            btn.setStyleSheet(self._filter_style(key == "open"))
            btn.clicked.connect(lambda _, k=key: self._set_filter(k))
            fl.addWidget(btn)
            self._filter_btns[key] = btn
        fl.addStretch()

        self._refresh_btn = QPushButton()
        self._refresh_btn.setFixedSize(28, 28)
        self._refresh_btn.setCursor(Qt.PointingHandCursor)
        self._refresh_btn.setIcon(qta.icon("ph.arrow-clockwise", color=COLORS['text_muted']))
        self._refresh_btn.setIconSize(QSize(14, 14))
        self._refresh_btn.setToolTip("Refresh")
        self._refresh_btn.setStyleSheet(f"""
            QPushButton {{
                background: transparent; border: none; border-radius: 6px;
            }}
            QPushButton:hover {{
                background: {COLORS['bg_hover']};
            }}
        """)
        self._refresh_btn.clicked.connect(self._do_refresh)
        fl.addWidget(self._refresh_btn)

        root.addWidget(filter_bar)

        # ── Approval requirement banner ───────────────────────────────────────
        self._approval_row = QWidget()
        self._approval_row.setStyleSheet(f"background: transparent; border-bottom: 1px solid {COLORS['border']};")
        self._approval_row.setFixedHeight(28)
        ahl = QHBoxLayout(self._approval_row)
        ahl.setContentsMargins(20, 0, 20, 0)
        ahl.setSpacing(6)
        self._approval_icon = QLabel()
        self._approval_icon.setStyleSheet("background: transparent; border: none;")
        ahl.addWidget(self._approval_icon)
        self._approval_lbl = QLabel()
        self._approval_lbl.setStyleSheet(f"background: transparent; border: none; font-size: 11px; color: {COLORS['text_muted']};")
        ahl.addWidget(self._approval_lbl, 1)
        self._approval_row.hide()
        root.addWidget(self._approval_row)

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
        scroll.setStyleSheet("QScrollArea { background: transparent; border: none; }\n" + scrollbar_style())
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

    def set_approval_count(self, count: int):
        self._required_approvals = count
        if count > 0:
            s = "s" if count != 1 else ""
            color = COLORS.get("warning", "#f59e0b")
            self._approval_icon.setPixmap(
                qta.icon("ph.git-pull-request", color=color).pixmap(11, 11))
            self._approval_lbl.setText(f"Each PR requires {count} approval{s} to merge")
            self._approval_lbl.setStyleSheet(
                f"background: transparent; font-size: 11px; font-weight: 600; color: {color};")
        else:
            color = COLORS["text_muted"]
            self._approval_icon.setPixmap(
                qta.icon("ph.git-pull-request", color=color).pixmap(11, 11))
            self._approval_lbl.setText("No approval required to merge")
            self._approval_lbl.setStyleSheet(
                f"background: transparent; font-size: 11px; color: {color};")
        self._approval_row.show()

    def load(self, tracker, user: dict, token: str, commits: list):
        """Load the PR inbox for a repo."""
        self._commits = commits
        self._token   = token
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
                    border-radius: 5px; font-size: 11px; font-weight: 600; font-family: 'Tilt Warp';
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
        self._update_filter_counts()
        self._render_prs()

    def _update_filter_counts(self):
        counts = {"open": 0, "closed": 0, "merged": 0}
        for pr in self._all_prs:
            counts[_pr_state(pr)] = counts.get(_pr_state(pr), 0) + 1
        labels = {"open": "Open", "closed": "Closed", "merged": "Merged"}
        for key, btn in self._filter_btns.items():
            btn.setText(f"  {labels[key]}  {counts.get(key, 0)}")

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
        rows: list[_PRRow] = []
        for pr in filtered:
            row = _PRRow(pr, self._commits, self._token, self._owner, self._repo,
                         self._required_approvals)
            row.hovered.connect(self.pr_hovered)
            row.unhovered.connect(self.pr_cleared)
            row.approve_clicked.connect(self._on_approve)
            row.merge_clicked.connect(self.merge_requested)   # commit_view handles this
            row.close_clicked.connect(self._on_close)
            self._list_layout.insertWidget(self._list_layout.count() - 1, row)
            rows.append(row)
        for row in rows:
            self._detail_pool.submit(row._fetch_detail)

    def _clear_rows(self):
        while self._list_layout.count() > 1:
            item = self._list_layout.takeAt(0)
            w = item.widget()
            if w:
                w.setParent(None)

    # ── GitHub actions ────────────────────────────────────────────────────────

    def _on_approve(self, pr_number: int):
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
            msg = "PR approved." if ok else "Couldn't approve this PR — try again."
            self._action_done.emit(ok, msg)
        except Exception:
            self._action_done.emit(False, "Network error.")

    def _on_close(self, pr_number: int):
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
            msg = "PR closed." if ok else "Couldn't close this PR — try again."
            self._action_done.emit(ok, msg)
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
            msg = "PR merged successfully." if ok else "Couldn't merge this PR — try again."
            self._action_done.emit(ok, msg)
        except Exception:
            self._action_done.emit(False, "Network error.")

    def _on_action_done(self, ok: bool, msg: str):
        self.toast_requested.emit(msg, "success" if ok else "error")


"""Settings panel — repo info and collaborators."""
from __future__ import annotations

import hashlib
import os
import re
import threading

import qtawesome as qta
import requests

from PyQt5.QtCore import (Qt, QPropertyAnimation, QEasingCurve,
                           pyqtSignal, pyqtProperty, QRectF)
from PyQt5.QtGui import QPainter, QColor, QBrush, QPen, QPixmap, QFont
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QScrollArea, QFrame, QSizePolicy,
)
from styles.theme import COLORS, scrollbar_style

# ── Shared avatar cache (separate from commit_view cache) ─────────────────────

_AVATAR_CACHE: dict[str, QPixmap] = {}
_PALETTE = [
    "#6366f1", "#f59e0b", "#ef4444", "#8b5cf6",
    "#06b6d4", "#f97316", "#ec4899", "#14b8a6",
]

def _person_color(login: str) -> str:
    idx = int(hashlib.md5(login.encode()).hexdigest(), 16) % len(_PALETTE)
    return _PALETTE[idx]


# ── Toggle switch ─────────────────────────────────────────────────────────────

class _Toggle(QWidget):
    toggled = pyqtSignal(bool)
    W, H = 44, 24

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(self.W, self.H)
        self.setCursor(Qt.PointingHandCursor)
        self._on  = False
        self._tx  = 2.0
        self._anim = QPropertyAnimation(self, b"thumb_x")
        self._anim.setDuration(160)
        self._anim.setEasingCurve(QEasingCurve.OutCubic)

    @pyqtProperty(float)
    def thumb_x(self):
        return self._tx

    @thumb_x.setter
    def thumb_x(self, v: float):
        self._tx = v
        self.update()

    @property
    def is_on(self) -> bool:
        return self._on

    def set_state(self, on: bool, emit: bool = False):
        self._on = on
        self._anim.stop()
        self._anim.setStartValue(self._tx)
        self._anim.setEndValue(self.W - self.H + 2 if on else 2.0)
        self._anim.start()
        self.update()
        if emit:
            self.toggled.emit(on)

    def mousePressEvent(self, _):
        self.set_state(not self._on, emit=True)

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        r = self.H / 2
        track = COLORS["accent"] if self._on else COLORS["bg_hover"]
        p.setBrush(QBrush(QColor(track)))
        p.setPen(Qt.NoPen)
        p.drawRoundedRect(QRectF(0, 0, self.W, self.H), r, r)
        d = self.H - 4
        p.setBrush(QBrush(QColor("white")))
        p.drawEllipse(QRectF(self._tx, 2, d, d))
        p.end()


# ── Avatar circle ─────────────────────────────────────────────────────────────

class _Avatar(QWidget):
    def __init__(self, login: str, size: int = 32, parent=None):
        super().__init__(parent)
        self.setFixedSize(size, size)
        self._size  = size
        self._login = login
        self._color = QColor(_person_color(login))
        self._pixmap: QPixmap | None = None

    def set_pixmap(self, pm: QPixmap):
        self._pixmap = pm.scaled(self._size, self._size,
                                  Qt.KeepAspectRatioByExpanding,
                                  Qt.SmoothTransformation)
        self.update()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        s = self._size
        from PyQt5.QtGui import QPainterPath
        clip = QPainterPath()
        clip.addEllipse(0, 0, s, s)
        p.setClipPath(clip)
        if self._pixmap:
            src = self._pixmap
            x = (src.width()  - s) // 2
            y = (src.height() - s) // 2
            p.drawPixmap(0, 0, src, x, y, s, s)
        else:
            c = self._color
            p.setBrush(QBrush(QColor(c.red(), c.green(), c.blue(), 40)))
            p.setPen(Qt.NoPen)
            p.drawEllipse(0, 0, s, s)
            p.setClipping(False)
            p.setPen(QPen(self._color))
            p.setFont(QFont("Tilt Warp", s // 3, QFont.Bold))
            p.drawText(self.rect(), Qt.AlignCenter, self._login[:2].upper())
        p.setClipping(False)
        p.setPen(QPen(self._color, 1.5))
        p.setBrush(Qt.NoBrush)
        p.drawEllipse(1, 1, s - 2, s - 2)
        p.end()


# ── Collab row ────────────────────────────────────────────────────────────────

class _SCollabRow(QWidget):
    _ROLE_LABELS = {
        "owner":    "Owner",
        "admin":    "Admin",
        "maintain": "Admin",
        "write":    "Collaborator",
        "viewer":   "Viewer",
    }

    def __init__(self, login: str, contributions: int, avatar_url: str,
                 display_name: str | None = None, is_owner: bool = False,
                 role: str = "write", is_me: bool = False, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WA_StyledBackground, True)
        bg = COLORS["bg_hover"] if is_me else "transparent"
        self.setStyleSheet(f"background: {bg}; border-radius: 6px;")

        hl = QHBoxLayout(self)
        hl.setContentsMargins(4, 8, 4, 8)
        hl.setSpacing(10)

        self._av = _Avatar(login, 34)
        hl.addWidget(self._av)

        info = QVBoxLayout()
        info.setSpacing(1)

        name_row = QHBoxLayout()
        name_row.setSpacing(5)
        name_row.setContentsMargins(0, 0, 0, 0)
        raw = display_name or login
        nm = QLabel(raw if len(raw) <= 20 else raw[:19] + "…")
        nm.setToolTip(raw)
        nm.setStyleSheet(
            f"background: transparent; font-size: 12px; font-weight: 600; font-family: 'Tilt Warp';"
            f" color: {COLORS['text_primary']};"
        )
        name_row.addWidget(nm)

        # Crown icons based on role
        if role == "owner":
            crown = QLabel()
            crown.setPixmap(qta.icon("fa5s.crown", color=COLORS["warning"]).pixmap(12, 12))
            crown.setStyleSheet("background: transparent;")
            crown.setToolTip("Owner")
            name_row.addWidget(crown)
        elif role in ("admin", "maintain"):
            crown = QLabel()
            crown.setPixmap(qta.icon("fa5s.medal", color=COLORS["text_muted"]).pixmap(12, 12))
            crown.setStyleSheet("background: transparent;")
            crown.setToolTip("Admin")
            name_row.addWidget(crown)

        name_row.addStretch()

        # Role label badge (right-aligned)
        role_label = self._ROLE_LABELS.get(role, "Collaborator")
        role_lbl = QLabel(role_label)
        role_lbl.setStyleSheet(
            f"background: transparent; font-size: 10px; font-weight: 500;"
            f" color: {COLORS['text_muted']};"
        )
        name_row.addWidget(role_lbl)
        info.addLayout(name_row)

        sub = QLabel(f"{contributions} commit{'s' if contributions != 1 else ''}")
        sub.setStyleSheet(
            f"background: transparent; font-size: 11px; color: {COLORS['text_muted']};"
        )
        info.addWidget(sub)
        hl.addLayout(info)

        if avatar_url:
            cached = _AVATAR_CACHE.get(avatar_url)
            if cached:
                self._av.set_pixmap(cached)
            else:
                threading.Thread(target=self._fetch, args=(avatar_url,), daemon=True).start()

    def _fetch(self, url: str):
        try:
            r = requests.get(url, timeout=10)
            if r.status_code == 200:
                pm = QPixmap()
                pm.loadFromData(r.content)
                if not pm.isNull():
                    _AVATAR_CACHE[url] = pm
                    self._av.set_pixmap(pm)
        except Exception:
            pass


# ── Skeleton row ──────────────────────────────────────────────────────────────

class _Skeleton(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(50)

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        base = QColor(COLORS["border"])
        base.setAlpha(120)
        p.setBrush(QBrush(base))
        p.setPen(Qt.NoPen)
        p.drawEllipse(4, 9, 34, 34)
        p.drawRoundedRect(48, 14, 100, 10, 4, 4)
        dim = QColor(COLORS["border"])
        dim.setAlpha(60)
        p.setBrush(QBrush(dim))
        p.drawRoundedRect(48, 30, 70, 8, 4, 4)
        p.end()


# ── Section header ────────────────────────────────────────────────────────────

def _section_lbl(text: str) -> QLabel:
    lbl = QLabel(text)
    lbl.setStyleSheet(
        f"background: transparent; font-size: 10px; font-weight: 600; font-family: 'Tilt Warp';"
        f" color: {COLORS['text_muted']}; letter-spacing: 0.08em;"
    )
    return lbl


def _divider() -> QFrame:
    f = QFrame()
    f.setFrameShape(QFrame.HLine)
    f.setStyleSheet(f"background: {COLORS['border']}; max-height: 1px;")
    return f


_RULE_LABELS: dict[str, str] = {
    "pull_request":            "Require pull request",
    "non_fast_forward":        "Block force-push",
    "deletion":                "Block branch deletion",
    "required_signatures":     "Require signed commits",
    "required_linear_history": "Require linear history",
    "required_status_checks":  "Require status checks",
    "creation":                "Restrict branch creation",
    "update":                  "Restrict branch updates",
}


def _humanize_ref(pattern: str) -> str:
    if pattern == "~DEFAULT_BRANCH": return "default branch"
    if pattern == "~ALL":            return "all branches"
    return pattern.replace("refs/heads/", "")


# ── Icon stat widget ──────────────────────────────────────────────────────────

class _IconStat(QWidget):
    def __init__(self, icon_name: str, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WA_TranslucentBackground)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(4)
        icon_lbl = QLabel()
        icon_lbl.setPixmap(qta.icon(icon_name, color=COLORS["text_muted"]).pixmap(12, 12))
        icon_lbl.setStyleSheet("background: transparent;")
        lay.addWidget(icon_lbl)
        self._count_lbl = QLabel("—")
        self._count_lbl.setStyleSheet(
            f"background: transparent; font-size: 11px; color: {COLORS['text_muted']};"
        )
        lay.addWidget(self._count_lbl)

    def set_count(self, n: int):
        self._count_lbl.setText(str(n))


# ── Settings panel ────────────────────────────────────────────────────────────

class SettingsPanel(QWidget):
    _repo_info_ready    = pyqtSignal(dict, int)   # thread → main: (repo API data, generation)
    _rulesets_ready_sig    = pyqtSignal(list, str, int)  # thread → main: (rulesets, status, min_approvals)
    _branch_protection_sig = pyqtSignal(str, bool)  # thread → main: (branch_name, is_protected)
    protected_branches_ready = pyqtSignal(set)       # emitted with set of protected branch names
    approval_count_ready     = pyqtSignal(int)       # min required approvals for PRs

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setStyleSheet(f"background: {COLORS['bg_primary']}; border: none; outline: none;")

        self._tracker        = None
        self._user:          dict = {}
        self._token:         str  = ""
        self._default_branch: str = "main"
        self._branch_protected_state: tuple | None = None  # (branch, protected)
        self._all_branches: list[dict] = []  # [{"name": str, "protected": bool}, ...]
        self._gen: int = 0

        self._repo_info_ready.connect(self._apply_repo_info)
        self._rulesets_ready_sig.connect(lambda rs, st, n: self._on_rulesets_ready(rs, st, n))
        self._branch_protection_sig.connect(self._on_branch_protection)

        # Root scroll
        scroll = QScrollArea(self)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setStyleSheet("QScrollArea { background: transparent; border: none; }\n" + scrollbar_style())
        self._scroll = scroll

        content = QWidget()
        content.setStyleSheet("background: transparent; border: none;")
        self._content_layout = QVBoxLayout(content)
        self._content_layout.setContentsMargins(24, 24, 24, 32)
        self._content_layout.setSpacing(0)

        # ── Repo info card ───────────────────────────────────────────────────
        self._repo_card = QWidget()
        self._repo_card.setObjectName("repoCard")
        self._repo_card.setAttribute(Qt.WA_StyledBackground, True)
        self._repo_card.setStyleSheet(f"""
            #repoCard {{
                background: {COLORS['bg_card']};
                border: 1px solid {COLORS['border']};
                border-radius: 10px;
            }}
        """)
        rc_layout = QVBoxLayout(self._repo_card)
        rc_layout.setContentsMargins(16, 14, 16, 14)
        rc_layout.setSpacing(6)

        name_row = QHBoxLayout()
        name_row.setSpacing(8)
        self._repo_name_lbl = QLabel("—")
        self._repo_name_lbl.setStyleSheet(
            f"background: transparent; font-size: 15px; font-weight: 700; font-family: 'Tilt Warp';"
            f" color: {COLORS['text_primary']};"
        )
        name_row.addWidget(self._repo_name_lbl)

        self._vis_badge = QLabel("")
        self._vis_badge.setFixedHeight(18)
        self._vis_badge.setAlignment(Qt.AlignCenter)
        self._vis_badge.setStyleSheet(
            f"background: {COLORS['bg_secondary']}; border: 1px solid {COLORS['border']};"
            f" border-radius: 9px; font-size: 10px; color: {COLORS['text_muted']};"
            f" padding: 0 8px;"
        )
        name_row.addWidget(self._vis_badge)

        self._role_badge = QLabel("")
        self._role_badge.setFixedHeight(18)
        self._role_badge.setAlignment(Qt.AlignCenter)
        self._role_badge.hide()
        name_row.addWidget(self._role_badge)

        name_row.addStretch()
        rc_layout.addLayout(name_row)

        self._repo_desc = QLabel("")
        self._repo_desc.setWordWrap(True)
        self._repo_desc.setStyleSheet(
            f"background: transparent; font-size: 12px; color: {COLORS['text_secondary']};"
        )
        self._repo_desc.hide()
        rc_layout.addWidget(self._repo_desc)

        self._stats_row_w = QWidget()
        self._stats_row_w.setStyleSheet("background: transparent;")
        stats_row = QHBoxLayout(self._stats_row_w)
        stats_row.setContentsMargins(0, 4, 0, 0)
        stats_row.setSpacing(16)
        self._stars_stat = _IconStat("fa5s.star")
        self._forks_stat = _IconStat("fa5s.code-branch")
        self._watch_stat = _IconStat("fa5s.eye")
        for w in (self._stars_stat, self._forks_stat, self._watch_stat):
            stats_row.addWidget(w)
        stats_row.addStretch()
        rc_layout.addWidget(self._stats_row_w)

        self._repo_loading_lbl = QLabel("Loading…")
        self._repo_loading_lbl.setAlignment(Qt.AlignCenter)
        self._repo_loading_lbl.setStyleSheet(
            f"background: transparent; font-size: 12px; color: {COLORS['text_muted']};"
            f" padding: 8px 0;"
        )
        self._repo_loading_lbl.hide()
        rc_layout.addWidget(self._repo_loading_lbl)

        self._content_layout.addWidget(self._repo_card)
        self._content_layout.addSpacing(20)

        # ── Collaborators (collapsible) ───────────────────────────────────────
        self._content_layout.addWidget(_section_lbl("COLLABORATORS"))
        self._content_layout.addSpacing(10)

        self._collab_expanded = True
        collab_card = QWidget()
        collab_card.setObjectName("collabCard")
        collab_card.setAttribute(Qt.WA_StyledBackground, True)
        collab_card.setStyleSheet(f"""
            #collabCard {{
                background: {COLORS['bg_card']};
                border: 1px solid {COLORS['border']};
                border-radius: 8px;
            }}
        """)
        collab_card_vl = QVBoxLayout(collab_card)
        collab_card_vl.setContentsMargins(0, 0, 0, 0)
        collab_card_vl.setSpacing(0)

        # Header row inside the card
        collab_hdr = QWidget()
        collab_hdr.setFixedHeight(38)
        collab_hdr.setStyleSheet("background: transparent;")
        ch_layout = QHBoxLayout(collab_hdr)
        ch_layout.setContentsMargins(14, 0, 10, 0)
        ch_layout.setSpacing(8)
        ch_lbl = QLabel("Contributors")
        ch_lbl.setStyleSheet(
            f"background: transparent; font-size: 12px; font-weight: 600; font-family: 'Tilt Warp';"
            f" color: {COLORS['text_muted']};"
        )
        ch_layout.addWidget(ch_lbl)
        self._collab_count = QLabel("")
        self._collab_count.setFixedHeight(18)
        self._collab_count.setAlignment(Qt.AlignCenter)
        self._collab_count.setStyleSheet(
            f"background: {COLORS['bg_primary']}; border-radius: 9px;"
            f" font-size: 10px; font-weight: 600; font-family: 'Tilt Warp'; color: {COLORS['text_muted']};"
            f" padding: 0 8px;"
        )
        self._collab_count.setText("")
        ch_layout.addWidget(self._collab_count)
        ch_layout.addStretch()
        self._collab_toggle = QPushButton("▾")
        self._collab_toggle.setFixedSize(24, 24)
        self._collab_toggle.setCursor(Qt.PointingHandCursor)
        self._collab_toggle.setStyleSheet(f"""
            QPushButton {{ background: transparent; border: none;
                color: {COLORS['text_muted']}; font-size: 11px; }}
            QPushButton:hover {{ color: {COLORS['text_primary']}; }}
        """)
        self._collab_toggle.clicked.connect(self._toggle_collabs)
        ch_layout.addWidget(self._collab_toggle)
        collab_card_vl.addWidget(collab_hdr)

        # Thin divider between header and rows
        div = QFrame()
        div.setFrameShape(QFrame.HLine)
        div.setStyleSheet(f"background: {COLORS['border']}; max-height: 1px; border: none;")
        collab_card_vl.addWidget(div)

        # Rows container
        self._collab_body = QWidget()
        self._collab_body.setStyleSheet("background: transparent;")
        self._collab_list = QVBoxLayout(self._collab_body)
        self._collab_list.setContentsMargins(10, 6, 10, 8)
        self._collab_list.setSpacing(0)
        for _ in range(3):
            self._collab_list.addWidget(_Skeleton())
        collab_card_vl.addWidget(self._collab_body)

        self._content_layout.addWidget(collab_card)
        self._collab_card = collab_card

        self._content_layout.addSpacing(20)

        # ── Branch Rules (collapsible) ────────────────────────────────────────
        self._content_layout.addWidget(_section_lbl("BRANCH RULES"))
        self._content_layout.addSpacing(10)

        self._rules_expanded = True
        rules_card = QWidget()
        rules_card.setObjectName("rulesCard")
        rules_card.setAttribute(Qt.WA_StyledBackground, True)
        rules_card.setStyleSheet(f"""
            #rulesCard {{
                background: {COLORS['bg_card']};
                border: 1px solid {COLORS['border']};
                border-radius: 8px;
            }}
        """)
        rules_card_vl = QVBoxLayout(rules_card)
        rules_card_vl.setContentsMargins(0, 0, 0, 0)
        rules_card_vl.setSpacing(0)

        rules_hdr = QWidget()
        rules_hdr.setFixedHeight(38)
        rules_hdr.setStyleSheet("background: transparent;")
        rh_layout = QHBoxLayout(rules_hdr)
        rh_layout.setContentsMargins(14, 0, 10, 0)
        rh_layout.setSpacing(8)
        rh_lbl = QLabel("Branch Rules")
        rh_lbl.setStyleSheet(
            f"background: transparent; font-size: 12px; font-weight: 600; font-family: 'Tilt Warp';"
            f" color: {COLORS['text_muted']};"
        )
        rh_layout.addWidget(rh_lbl)
        rh_layout.addStretch()
        self._rules_toggle = QPushButton("▾")
        self._rules_toggle.setFixedSize(24, 24)
        self._rules_toggle.setCursor(Qt.PointingHandCursor)
        self._rules_toggle.setStyleSheet(f"""
            QPushButton {{ background: transparent; border: none;
                color: {COLORS['text_muted']}; font-size: 11px; }}
            QPushButton:hover {{ color: {COLORS['text_primary']}; }}
        """)
        self._rules_toggle.clicked.connect(self._toggle_rules)
        rh_layout.addWidget(self._rules_toggle)
        rules_card_vl.addWidget(rules_hdr)

        rdiv = QFrame()
        rdiv.setFrameShape(QFrame.HLine)
        rdiv.setStyleSheet(f"background: {COLORS['border']}; max-height: 1px; border: none;")
        rules_card_vl.addWidget(rdiv)

        self._rules_body = QWidget()
        self._rules_body.setStyleSheet("background: transparent;")
        self._rules_list = QVBoxLayout(self._rules_body)
        self._rules_list.setContentsMargins(10, 8, 10, 10)
        self._rules_list.setSpacing(8)

        _loading = QLabel("Loading…")
        _loading.setAlignment(Qt.AlignCenter)
        _loading.setStyleSheet(
            f"background: transparent; font-size: 12px; color: {COLORS['text_muted']}; padding: 8px 0;"
        )
        self._rules_list.addWidget(_loading)
        rules_card_vl.addWidget(self._rules_body)

        self._content_layout.addWidget(rules_card)
        self._rules_card = rules_card

        self._content_layout.addStretch()

        scroll.setWidget(content)
        scroll.viewport().setStyleSheet("background: transparent; border: none;")

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(scroll)

    # ── Public ────────────────────────────────────────────────────────────────

    def setup(self, tracker, user: dict, token: str):
        self._gen += 1
        self._tracker   = tracker
        self._user      = user
        self._token     = token
        self._branch_protected_state = None
        self._all_branches = []

        # Repo card — show loading, hide stale content
        self._repo_desc.hide()
        self._vis_badge.setText("")
        self._vis_badge.hide()
        self._role_badge.setText("")
        self._role_badge.hide()
        self._stats_row_w.hide()
        self._repo_loading_lbl.show()
        self._repo_name_lbl.setText(tracker.repo_name if tracker else "Loading…")

        # Collaborators — clear old rows, show skeleton placeholders
        while self._collab_list.count():
            item = self._collab_list.takeAt(0)
            if item.widget():
                item.widget().setParent(None)
        self._collab_count.setText("")
        for _ in range(3):
            self._collab_list.addWidget(_Skeleton())

        # Branch rules — clear old rows, show loading placeholder
        while self._rules_list.count():
            item = self._rules_list.takeAt(0)
            if item.widget():
                item.widget().setParent(None)
        _rl = QLabel("Loading…")
        _rl.setAlignment(Qt.AlignCenter)
        _rl.setStyleSheet(
            f"background: transparent; font-size: 12px; color: {COLORS['text_muted']}; padding: 8px 0;"
        )
        self._rules_list.addWidget(_rl)

        # Seed _default_branch from local git immediately (before async GitHub API fetch).
        if tracker:
            from core.ops import get_default_branch
            self._default_branch = get_default_branch(tracker._path)
        else:
            self._default_branch = "main"

        if tracker and token:
            gen = self._gen
            threading.Thread(target=self._fetch_repo_info, args=(gen,), daemon=True).start()

    def set_role(self, role: str):
        _ROLE_STYLES = {
            "Viewer": (COLORS.get("warning", "#f59e0b"), COLORS.get("warning", "#f59e0b")),
            "Owner": (COLORS["accent"], COLORS["accent"]),
            "Collaborator": (COLORS["accent"], COLORS["accent"]),
        }
        color, border = _ROLE_STYLES.get(role, (COLORS["text_muted"], COLORS["border"]))
        self._role_badge.setText(role)
        self._role_badge.setStyleSheet(
            f"background: transparent; border: 1px solid {border};"
            f" border-radius: 9px; font-size: 10px; color: {color};"
            f" padding: 0 8px;"
        )
        self._role_badge.show()

    def load_collaborators(self, collabs: list[dict], current_login: str = ""):
        while self._collab_list.count():
            item = self._collab_list.takeAt(0)
            w = item.widget()
            if w:
                w.setParent(None)

        n = len(collabs)
        self._collab_count.setText(str(n) if n else "")

        if not collabs:
            empty = QLabel("No contributors yet")
            empty.setAlignment(Qt.AlignCenter)
            empty.setStyleSheet(
                f"background: transparent; font-size: 12px;"
                f" color: {COLORS['text_muted']}; padding: 12px 0;"
            )
            self._collab_list.addWidget(empty)
            return

        from PyQt5.QtCore import QTimer
        self._collab_queue = list(collabs)
        self._collab_login = current_login
        self._drain_collab_queue()

    def _drain_collab_queue(self):
        BATCH = 3
        for _ in range(BATCH):
            if not self._collab_queue:
                return
            c = self._collab_queue.pop(0)
            login = c.get("login", "?")
            role = "owner" if c.get("is_owner") else c.get("role", "write")
            row = _SCollabRow(
                login=login,
                contributions=c.get("contributions", 0),
                avatar_url=c.get("avatar_url", ""),
                display_name=c.get("display_name") or c.get("gh_name"),
                is_owner=c.get("is_owner", False),
                role=role,
                is_me=(login == self._collab_login and bool(self._collab_login)),
            )
            self._collab_list.addWidget(row)
        if self._collab_queue:
            from PyQt5.QtCore import QTimer
            QTimer.singleShot(0, self._drain_collab_queue)

    # ── Internal ──────────────────────────────────────────────────────────────

    def _toggle_collabs(self):
        self._collab_expanded = not self._collab_expanded
        self._collab_body.setVisible(self._collab_expanded)
        self._collab_toggle.setText("▾" if self._collab_expanded else "▸")
        self._collab_card.adjustSize()
        self._scroll.widget().adjustSize()
        self._scroll.updateGeometry()


    def _fetch_repo_info(self, gen: int):
        try:
            url = self._tracker.remote_url()
            m = re.search(r'github\.com[:/]([^/]+)/([^/]+?)(?:\.git)?$', url)
            if not m:
                return
            owner, repo = m.group(1), m.group(2)
            r = requests.get(
                f"https://api.github.com/repos/{owner}/{repo}",
                headers={"Authorization": f"Bearer {self._token}",
                         "Accept": "application/vnd.github+json"},
                timeout=10,
            )
            if r.status_code == 200:
                data = r.json()
                self._repo_info_ready.emit(data, gen)
                default_branch = data.get("default_branch", "main")
                try:
                    br = requests.get(
                        f"https://api.github.com/repos/{owner}/{repo}/branches?per_page=100",
                        headers={"Authorization": f"Bearer {self._token}",
                                 "Accept": "application/vnd.github+json"},
                        timeout=10,
                    )
                    if br.status_code == 200:
                        protected = set()
                        self._all_branches = []
                        for b in br.json():
                            name = b.get("name", "")
                            is_prot = b.get("protected", False)
                            self._all_branches.append({"name": name, "protected": is_prot})
                            if is_prot:
                                protected.add(name)
                        self.protected_branches_ready.emit(protected)
                        is_default_protected = default_branch in protected
                        self._branch_protection_sig.emit(default_branch, is_default_protected)
                except Exception:
                    pass
            self._fetch_rulesets(owner, repo, self._token)
        except Exception:
            pass

    def _fetch_rulesets(self, owner: str, repo: str, token: str):
        headers = {"Authorization": f"Bearer {token}",
                   "Accept": "application/vnd.github+json"}
        try:
            r = requests.get(
                f"https://api.github.com/repos/{owner}/{repo}/rulesets",
                params={"includes_parents": "true"},
                headers=headers, timeout=10,
            )
            if r.status_code == 200:
                rulesets = r.json()
                active_ids = [
                    rs["id"] for rs in rulesets
                    if rs.get("enforcement") == "active" and rs.get("target") == "branch"
                ]
                max_approvals = 0
                for rs_id in active_ids:
                    try:
                        dr = requests.get(
                            f"https://api.github.com/repos/{owner}/{repo}/rulesets/{rs_id}",
                            headers=headers, timeout=10,
                        )
                        if dr.status_code == 200:
                            detail = dr.json()
                            for rule in detail.get("rules") or []:
                                if rule.get("type") == "pull_request":
                                    cnt = (rule.get("parameters") or {}).get(
                                        "required_approving_review_count", 0)
                                    max_approvals = max(max_approvals, cnt)
                            idx = next((i for i, rs in enumerate(rulesets) if rs.get("id") == rs_id), None)
                            if idx is not None:
                                rulesets[idx] = detail
                    except Exception:
                        pass
                self._rulesets_ready_sig.emit(rulesets, "", max_approvals)
            elif r.status_code == 403:
                self._rulesets_ready_sig.emit([], "pro_required", 0)
            else:
                self._rulesets_ready_sig.emit([], "error", 0)
        except Exception:
            self._rulesets_ready_sig.emit([], "error", 0)

    def _apply_repo_info(self, data: dict, gen: int):
        if gen != self._gen:
            return
        self._repo_loading_lbl.hide()
        self._vis_badge.show()
        self._stats_row_w.show()

        self._default_branch = data.get("default_branch") or self._default_branch
        self._repo_name_lbl.setText(data.get("name", "—"))
        vis = "Private" if data.get("private") else "Public"
        self._vis_badge.setText(vis)
        desc = data.get("description") or ""
        if desc:
            self._repo_desc.setText(desc)
            self._repo_desc.show()
        else:
            self._repo_desc.setText("No description")
            self._repo_desc.show()
        self._stars_stat.set_count(data.get("stargazers_count", 0))
        self._forks_stat.set_count(data.get("forks_count", 0))
        self._watch_stat.set_count(data.get("subscribers_count", 0))

    def _on_branch_protection(self, branch: str, protected: bool):
        self._branch_protected_state = (branch, protected)
        # Row insertion deferred to _on_rulesets_ready to avoid double-insert
        # and to allow the rulesets pass to upgrade protection state first.

    def _insert_protection_row(self, branch: str, protected: bool):
        row = QWidget()
        row.setStyleSheet("background: transparent;")
        hl = QHBoxLayout(row)
        hl.setContentsMargins(2, 0, 2, 4)
        hl.setSpacing(6)

        icon_name  = "ph.lock" if protected else "ph.lock-open"
        icon_color = COLORS.get("warning", "#f59e0b") if protected else COLORS["text_muted"]
        icon_lbl = QLabel()
        icon_lbl.setPixmap(qta.icon(icon_name, color=icon_color).pixmap(11, 11))
        icon_lbl.setStyleSheet("background: transparent;")
        hl.addWidget(icon_lbl)

        status = "Protected" if protected else "Not protected"
        color  = COLORS.get("warning", "#f59e0b") if protected else COLORS["text_muted"]
        text_lbl = QLabel(f"{branch}  ·  {status}")
        text_lbl.setStyleSheet(
            f"background: transparent; font-size: 12px; color: {color};"
        )
        hl.addWidget(text_lbl, 1)

        self._rules_list.addWidget(row)

    def _toggle_rules(self):
        self._rules_expanded = not self._rules_expanded
        self._rules_body.setVisible(self._rules_expanded)
        self._rules_toggle.setText("▾" if self._rules_expanded else "▸")
        self._rules_card.adjustSize()
        self._scroll.widget().adjustSize()
        self._scroll.updateGeometry()

    def _on_rulesets_ready(self, rulesets: list, status: str, min_approvals: int = 0):
        while self._rules_list.count():
            item = self._rules_list.takeAt(0)
            w = item.widget()
            if w:
                w.setParent(None)

        active = []
        if status == "pro_required":
            msg = QLabel("Requires GitHub Pro for private repos")
            msg.setAlignment(Qt.AlignCenter)
            msg.setWordWrap(True)
            msg.setStyleSheet(
                f"background: transparent; font-size: 12px; font-style: italic;"
                f" color: {COLORS['text_muted']}; padding: 8px 0;"
            )
            self._rules_list.addWidget(msg)
        else:
            active = [rs for rs in rulesets
                      if rs.get("enforcement") == "active" and rs.get("target") == "branch"]

            # Rulesets can enforce protection even when the branch API says protected=False.
            if active and self._default_branch:
                already = self._branch_protected_state and self._branch_protected_state[1]
                if not already:
                    self._branch_protected_state = (self._default_branch, True)
                    self._branch_protection_sig.emit(self._default_branch, True)

            if not active:
                empty = QLabel("No rules configured")
                empty.setAlignment(Qt.AlignCenter)
                empty.setStyleSheet(
                    f"background: transparent; font-size: 12px; font-style: italic;"
                    f" color: {COLORS['text_muted']}; padding: 8px 0;"
                )
                self._rules_list.addWidget(empty)
            else:
                for rs in active:
                    self._rules_list.addWidget(self._build_ruleset_card(rs))

        self.approval_count_ready.emit(min_approvals)

        # Show all branches in two groups: protected first, then unprotected
        if self._all_branches:
            protected_set = set()
            if active:
                protected_set.add(self._default_branch)
            prot = [b for b in self._all_branches if b["protected"] or b["name"] in protected_set]
            unprot = [b for b in self._all_branches if not b["protected"] and b["name"] not in protected_set]
            if prot:
                grp = QLabel("PROTECTED")
                grp.setStyleSheet(
                    f"background: transparent; font-size: 10px; font-weight: 700;"
                    f" color: {COLORS.get('warning', '#f59e0b')}; letter-spacing: 0.06em;"
                )
                self._rules_list.addWidget(grp)
                for b in prot:
                    self._insert_protection_row(b["name"], True)
            if unprot:
                grp2 = QLabel("UNPROTECTED")
                grp2.setStyleSheet(
                    f"background: transparent; font-size: 10px; font-weight: 700;"
                    f" color: {COLORS['text_muted']}; letter-spacing: 0.06em;"
                    + (f" padding-top: 8px;" if prot else "")
                )
                self._rules_list.addWidget(grp2)
                for b in unprot:
                    self._insert_protection_row(b["name"], False)
        elif self._branch_protected_state:
            self._insert_protection_row(*self._branch_protected_state)

    def _build_ruleset_card(self, rs: dict) -> QWidget:
        name  = rs.get("name") or "Unnamed ruleset"
        rules = rs.get("rules") or []

        card = QWidget()
        card.setStyleSheet("background: transparent;")
        vl = QVBoxLayout(card)
        vl.setContentsMargins(0, 2, 0, 4)
        vl.setSpacing(1)

        rule_count = len(rules)
        suffix = f"  ·  {rule_count} rule{'s' if rule_count != 1 else ''}" if rule_count else ""
        header = QLabel(f"• {name}{suffix}")
        header.setStyleSheet(
            f"background: transparent; font-size: 12px; color: {COLORS['text_secondary']};"
        )
        vl.addWidget(header)

        for rule in rules:
            rtype = rule.get("type", "")
            label = _RULE_LABELS.get(rtype)
            if not label:
                continue
            params = rule.get("parameters") or {}
            if rtype == "pull_request":
                cnt = params.get("required_approving_review_count", 0)
                if cnt:
                    label += f"  ·  {cnt} approval{'s' if cnt != 1 else ''}"
            rl = QLabel(f"    {label}")
            rl.setStyleSheet(
                f"background: transparent; font-size: 11px; color: {COLORS['text_muted']};"
            )
            vl.addWidget(rl)

        return card


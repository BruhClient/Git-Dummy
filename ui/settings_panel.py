"""Settings panel — repo info, collaborators, branch protection."""
from __future__ import annotations

import hashlib
import os
import re
import threading

import requests

from PyQt5.QtCore import (Qt, QPropertyAnimation, QEasingCurve, QTimer,
                           pyqtSignal, pyqtProperty, QRectF)
from PyQt5.QtGui import QPainter, QColor, QBrush, QPen, QPixmap, QFont
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QScrollArea, QFrame, QSizePolicy,
)
from styles.theme import COLORS

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
            p.setFont(QFont("Inter", s // 3, QFont.Bold))
            p.drawText(self.rect(), Qt.AlignCenter, self._login[:2].upper())
        p.setClipping(False)
        p.setPen(QPen(self._color, 1.5))
        p.setBrush(Qt.NoBrush)
        p.drawEllipse(1, 1, s - 2, s - 2)
        p.end()


# ── Collab row ────────────────────────────────────────────────────────────────

class _SCollabRow(QWidget):
    def __init__(self, login: str, contributions: int, avatar_url: str,
                 display_name: str | None = None, is_owner: bool = False, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setStyleSheet("background: transparent; border-radius: 6px;")

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
            f"background: transparent; font-size: 12px; font-weight: 600;"
            f" color: {COLORS['text_primary']};"
        )
        name_row.addWidget(nm)
        if is_owner:
            crown = QLabel("👑")
            crown.setStyleSheet("background: transparent; font-size: 11px;")
            name_row.addWidget(crown)
        name_row.addStretch()
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
        f"background: transparent; font-size: 10px; font-weight: 600;"
        f" color: {COLORS['text_muted']}; letter-spacing: 0.08em;"
    )
    return lbl


def _divider() -> QFrame:
    f = QFrame()
    f.setFrameShape(QFrame.HLine)
    f.setStyleSheet(f"background: {COLORS['border']}; max-height: 1px;")
    return f


# ── Settings panel ────────────────────────────────────────────────────────────

class SettingsPanel(QWidget):
    protection_changed  = pyqtSignal(bool)
    _protection_ready   = pyqtSignal(bool)   # thread → main: fetched state
    _push_done          = pyqtSignal(str)     # thread → main: result message

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setStyleSheet(f"background: {COLORS['bg_primary']}; border: none; outline: none;")

        self._tracker        = None
        self._user:          dict = {}
        self._is_owner:      bool = False
        self._token:         str  = ""
        self._protection_enabled: bool = False
        self._default_branch: str = "main"

        self._protection_ready.connect(self._apply_protection)
        self._push_done.connect(self._set_status)

        # Root scroll
        scroll = QScrollArea(self)
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
            f"background: transparent; font-size: 15px; font-weight: 700;"
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
        name_row.addStretch()
        rc_layout.addLayout(name_row)

        self._repo_desc = QLabel("")
        self._repo_desc.setWordWrap(True)
        self._repo_desc.setStyleSheet(
            f"background: transparent; font-size: 12px; color: {COLORS['text_secondary']};"
        )
        self._repo_desc.hide()
        rc_layout.addWidget(self._repo_desc)

        stats_row = QHBoxLayout()
        stats_row.setSpacing(16)
        stats_row.setContentsMargins(0, 4, 0, 0)
        self._stars_lbl   = self._stat_lbl("⭐ —")
        self._forks_lbl   = self._stat_lbl("⑂ —")
        self._issues_lbl  = self._stat_lbl("◎ —")
        self._lang_lbl    = self._stat_lbl("")
        for lbl in (self._stars_lbl, self._forks_lbl, self._issues_lbl, self._lang_lbl):
            stats_row.addWidget(lbl)
        stats_row.addStretch()
        rc_layout.addLayout(stats_row)
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
            f"background: transparent; font-size: 12px; font-weight: 600;"
            f" color: {COLORS['text_muted']};"
        )
        ch_layout.addWidget(ch_lbl)
        self._collab_count = QLabel("")
        self._collab_count.setFixedHeight(18)
        self._collab_count.setAlignment(Qt.AlignCenter)
        self._collab_count.setStyleSheet(
            f"background: {COLORS['bg_primary']}; border-radius: 9px;"
            f" font-size: 10px; font-weight: 600; color: {COLORS['text_muted']};"
            f" padding: 0 8px;"
        )
        self._collab_count.hide()
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

        # ── Branch protection (owner only) ────────────────────────────────────
        self._owner_section = QWidget()
        self._owner_section.setStyleSheet("background: transparent; border: none;")
        owner_vl = QVBoxLayout(self._owner_section)
        owner_vl.setContentsMargins(0, 0, 0, 0)
        owner_vl.setSpacing(10)

        owner_vl.addWidget(_divider())
        owner_vl.addSpacing(10)
        owner_vl.addWidget(_section_lbl("BRANCH PROTECTION"))
        owner_vl.addSpacing(10)

        protection_card = QWidget()
        protection_card.setObjectName("protCard")
        protection_card.setAttribute(Qt.WA_StyledBackground, True)
        protection_card.setStyleSheet(f"""
            #protCard {{
                background: {COLORS['bg_card']};
                border: 1px solid {COLORS['border']};
                border-radius: 8px;
            }}
        """)
        pc_layout = QVBoxLayout(protection_card)
        pc_layout.setContentsMargins(14, 12, 14, 12)
        pc_layout.setSpacing(10)

        toggle_row = QHBoxLayout()
        toggle_row.setSpacing(12)
        toggle_lbl_col = QVBoxLayout()
        toggle_lbl_col.setSpacing(2)
        prot_lbl = QLabel("Require pull requests")
        prot_lbl.setStyleSheet(
            f"background: transparent; font-size: 13px; font-weight: 600;"
            f" color: {COLORS['text_primary']};"
        )
        toggle_lbl_col.addWidget(prot_lbl)
        prot_sub = QLabel("Block direct pushes to the default branch.")
        prot_sub.setStyleSheet(
            f"background: transparent; font-size: 11px; color: {COLORS['text_muted']};"
        )
        toggle_lbl_col.addWidget(prot_sub)
        toggle_row.addLayout(toggle_lbl_col)
        toggle_row.addStretch()
        self._prot_toggle = _Toggle()
        self._prot_toggle.toggled.connect(self._on_protection_toggled)
        toggle_row.addWidget(self._prot_toggle)
        pc_layout.addLayout(toggle_row)

        self._prot_status = QLabel("")
        self._prot_status.setStyleSheet(
            f"background: transparent; font-size: 11px; color: {COLORS['text_muted']};"
        )
        self._prot_status.hide()
        pc_layout.addWidget(self._prot_status)

        owner_vl.addWidget(protection_card)

        self._content_layout.addWidget(self._owner_section)
        self._owner_section.hide()

        self._content_layout.addStretch()

        scroll.setWidget(content)
        scroll.viewport().setStyleSheet("background: transparent; border: none;")

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(scroll)

    # ── Public ────────────────────────────────────────────────────────────────

    def setup(self, tracker, user: dict, is_owner: bool, token: str):
        self._tracker   = tracker
        self._user      = user
        self._is_owner  = is_owner
        self._token     = token

        # Repo name placeholder
        if tracker:
            self._repo_name_lbl.setText(tracker.repo_name)

        self._owner_section.setVisible(is_owner)

        if tracker and token:
            threading.Thread(target=self._fetch_repo_info,  daemon=True).start()
            threading.Thread(target=self._fetch_protection, daemon=True).start()

    def load_collaborators(self, collabs: list[dict]):
        while self._collab_list.count():
            item = self._collab_list.takeAt(0)
            w = item.widget()
            if w:
                w.setParent(None)

        n = len(collabs)
        if n:
            self._collab_count.setText(str(n))
            self._collab_count.show()
        else:
            self._collab_count.hide()

        if not collabs:
            empty = QLabel("No contributors yet")
            empty.setAlignment(Qt.AlignCenter)
            empty.setStyleSheet(
                f"background: transparent; font-size: 12px;"
                f" color: {COLORS['text_muted']}; padding: 12px 0;"
            )
            self._collab_list.addWidget(empty)
            return

        for c in collabs:
            row = _SCollabRow(
                login=c.get("login", "?"),
                contributions=c.get("contributions", 0),
                avatar_url=c.get("avatar_url", ""),
                display_name=c.get("display_name") or c.get("gh_name"),
                is_owner=c.get("is_owner", False),
            )
            self._collab_list.addWidget(row)

    # ── Internal ──────────────────────────────────────────────────────────────

    def _toggle_collabs(self):
        self._collab_expanded = not self._collab_expanded
        self._collab_body.setVisible(self._collab_expanded)
        self._collab_toggle.setText("▾" if self._collab_expanded else "▸")
        self._collab_card.adjustSize()

    @staticmethod
    def _stat_lbl(text: str) -> QLabel:
        lbl = QLabel(text)
        lbl.setStyleSheet(
            f"background: transparent; font-size: 11px; color: {COLORS['text_muted']};"
        )
        return lbl

    def _fetch_repo_info(self):
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
                QTimer.singleShot(0, lambda d=data: self._apply_repo_info(d))
        except Exception:
            pass

    def _apply_repo_info(self, data: dict):
        self._default_branch = data.get("default_branch") or "main"
        self._repo_name_lbl.setText(data.get("name", "—"))
        vis = "Private" if data.get("private") else "Public"
        self._vis_badge.setText(vis)
        desc = data.get("description") or ""
        if desc:
            self._repo_desc.setText(desc)
            self._repo_desc.show()
        self._stars_lbl.setText(f"⭐ {data.get('stargazers_count', 0)}")
        self._forks_lbl.setText(f"⑂ {data.get('forks_count', 0)}")
        self._issues_lbl.setText(f"◎ {data.get('open_issues_count', 0)}")
        lang = data.get("language") or ""
        if lang:
            self._lang_lbl.setText(f"● {lang}")
            self._lang_lbl.show()
        else:
            self._lang_lbl.hide()

    def _fetch_protection(self):
        try:
            url = self._tracker.remote_url()
            m = re.search(r'github\.com[:/]([^/]+)/([^/]+?)(?:\.git)?$', url)
            if not m:
                return
            owner, repo = m.group(1), m.group(2)
            branch = self._default_branch
            r = requests.get(
                f"https://api.github.com/repos/{owner}/{repo}/branches/{branch}/protection",
                headers={"Authorization": f"Bearer {self._token}",
                         "Accept": "application/vnd.github+json"},
                timeout=10,
            )
            self._protection_ready.emit(r.status_code == 200)
        except Exception:
            pass

    def _apply_protection(self, enabled: bool):
        self._protection_enabled = enabled
        self._prot_toggle.set_state(enabled)
        self.protection_changed.emit(enabled)

    def _on_protection_toggled(self, on: bool):
        self._protection_enabled = on
        self.protection_changed.emit(on)
        self._prot_status.setText("Updating…")
        self._prot_status.show()
        threading.Thread(target=self._push_protection, args=(on,), daemon=True).start()

    def _push_protection(self, enable: bool):
        try:
            url = self._tracker.remote_url()
            m = re.search(r'github\.com[:/]([^/]+)/([^/]+?)(?:\.git)?$', url)
            if not m:
                return
            owner, repo = m.group(1), m.group(2)
            branch = self._default_branch
            api_url = f"https://api.github.com/repos/{owner}/{repo}/branches/{branch}/protection"
            hdrs = {"Authorization": f"Bearer {self._token}",
                    "Accept": "application/vnd.github+json"}
            if enable:
                body = {
                    "required_status_checks": None,
                    "enforce_admins": True,
                    "required_pull_request_reviews": {
                        "required_approving_review_count": 0,
                        "require_code_owner_reviews": False,
                    },
                    "restrictions": None,
                }
                r = requests.put(api_url, json=body, headers=hdrs, timeout=15)
                ok = r.status_code in (200, 201)
            else:
                r = requests.delete(api_url, headers=hdrs, timeout=15)
                ok = r.status_code == 204

            if ok:
                msg = "Protection enabled." if enable else "Protection disabled."
            else:
                msg = f"Failed ({r.status_code}) — check permissions."
            self._push_done.emit(msg)
        except Exception:
            self._push_done.emit("Error contacting GitHub.")

    def _set_status(self, msg: str):
        self._prot_status.setText(msg)
        self._prot_status.show()
        QTimer.singleShot(3000, self._prot_status.hide)

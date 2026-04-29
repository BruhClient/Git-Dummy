from __future__ import annotations

import hashlib
import re
import threading

from PyQt5.QtCore import Qt, QPropertyAnimation, QEasingCurve, QRect, QPoint, pyqtSignal
from PyQt5.QtGui import QPainter, QColor, QBrush, QPen, QPainterPath, QPixmap, QFont
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QScrollArea, QFrame, QSizePolicy,
)
from styles.theme import COLORS

_PALETTE = [
    "#6366f1", "#f59e0b", "#ef4444", "#8b5cf6",
    "#06b6d4", "#f97316", "#ec4899", "#14b8a6",
    "#84cc16", "#a78bfa",
]

def _author_color(name: str) -> str:
    idx = int(hashlib.md5(name.encode()).hexdigest(), 16) % len(_PALETTE)
    return _PALETTE[idx]


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
            p.setFont(QFont("Inter", s // 4, QFont.Bold))
            p.drawText(self.rect(), Qt.AlignCenter, self._initials)

        p.setClipping(False)
        p.setBrush(Qt.NoBrush)
        p.setPen(QPen(self._color, 1.5))
        p.drawEllipse(1, 1, s - 2, s - 2)
        p.end()

PANEL_W   = 320
CHANGES_W = 460

SWIPE_THRESHOLD = 70   # px rightward drag to dismiss a panel

def _filter_unchanged(removed: list, added: list) -> tuple[list, list]:
    """Drop lines that are positionally paired and content-identical — they only moved."""
    from difflib import SequenceMatcher
    if not removed or not added:
        return removed, added
    # Skip O(n²) filtering for large diffs — would freeze the UI
    if len(removed) > 300 or len(added) > 300:
        return removed, added
    sm = SequenceMatcher(None, [t for _, t in removed], [t for _, t in added], autojunk=False)
    keep_r = set(range(len(removed)))
    keep_a = set(range(len(added)))
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag == "equal":
            for i, j in zip(range(i1, i2), range(j1, j2)):
                keep_r.discard(i)
                keep_a.discard(j)
    return [removed[i] for i in sorted(keep_r)], \
           [added[j]   for j in sorted(keep_a)]


def _chunk_lines(lines: list) -> list[list]:
    """Split (line_num, text) pairs into consecutive groups."""
    if not lines:
        return []
    chunks, current = [], [lines[0]]
    for entry in lines[1:]:
        if entry[0] == current[-1][0] + 1:
            current.append(entry)
        else:
            chunks.append(current)
            current = [entry]
    chunks.append(current)
    return chunks


def _compute_hunks(lines: list) -> list[dict]:
    """Group diff lines into hunks [{removed:[(n,t)…], added:[(n,t)…]}]."""
    hunks: list[dict] = []
    cur_r: list = []
    cur_a: list = []
    old_num = new_num = 1
    started = False

    def _flush():
        if cur_r or cur_a:
            hunks.append({"removed": list(cur_r), "added": list(cur_a)})
        cur_r.clear()
        cur_a.clear()

    for kind, text in lines:
        if kind == "hunk":
            if started:
                _flush()
            m = re.search(r"@@ -(\d+)(?:,\d+)? \+(\d+)(?:,\d+)? @@", text)
            if m:
                old_num, new_num = int(m.group(1)), int(m.group(2))
            started = True
        elif kind == "removed":
            cur_r.append((old_num, text)); old_num += 1
        elif kind == "added":
            cur_a.append((new_num, text)); new_num += 1
        elif kind == "context":
            old_num += 1; new_num += 1
    _flush()
    return hunks


def _side_cell(entry, kind: str) -> QWidget:
    RED_BG  = "rgba(239,68,68,0.10)";  RED_NUM  = "rgba(239,68,68,0.06)"
    GRN_BG  = "rgba(34,197,94,0.10)";  GRN_NUM  = "rgba(34,197,94,0.06)"
    cell_bg = (RED_BG if kind == "removed" else GRN_BG) if entry else "transparent"
    num_bg  = (RED_NUM if kind == "removed" else GRN_NUM) if entry else "transparent"

    cell = QWidget()
    cell.setAttribute(Qt.WA_StyledBackground, True)
    cell.setStyleSheet(f"background: {cell_bg};")
    cl = QHBoxLayout(cell)
    cl.setContentsMargins(0, 2, 4, 2)
    cl.setSpacing(0)

    if entry:
        num, text = entry
        nl = QLabel(str(num))
        nl.setFixedWidth(36)
        nl.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        nl.setStyleSheet(
            f"background: {num_bg}; font-family: Consolas, monospace;"
            f" font-size: 10px; color: {COLORS['text_muted']}; padding-right: 6px;"
        )
        cl.addWidget(nl)
        tl = QLabel(text or " ")
        tl.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        tl.setTextInteractionFlags(Qt.TextSelectableByMouse)
        tl.setStyleSheet(
            f"background: transparent; font-family: Consolas, monospace;"
            f" font-size: 11px; color: {COLORS['text_primary']}; padding-left: 6px;"
        )
        cl.addWidget(tl, 1)
    return cell


def _side_row(old_e, new_e) -> QWidget:
    w = QWidget()
    rl = QHBoxLayout(w)
    rl.setContentsMargins(0, 0, 0, 0)
    rl.setSpacing(0)
    rl.addWidget(_side_cell(old_e, "removed"), 1)
    div = QWidget()
    div.setFixedWidth(1)
    div.setAttribute(Qt.WA_StyledBackground, True)
    div.setStyleSheet(f"background: {COLORS['border']};")
    rl.addWidget(div)
    rl.addWidget(_side_cell(new_e, "added"), 1)
    return w


def _side_gap() -> QWidget:
    w = QWidget()
    rl = QHBoxLayout(w)
    rl.setContentsMargins(0, 0, 0, 0)
    rl.setSpacing(0)
    for i in range(2):
        lbl = QLabel("· · ·")
        lbl.setAlignment(Qt.AlignCenter)
        lbl.setStyleSheet(
            f"background: transparent; color: {COLORS['text_muted']}; font-size: 11px; padding: 4px 0;"
        )
        rl.addWidget(lbl, 1)
        if i == 0:
            div = QWidget()
            div.setFixedWidth(1)
            div.setAttribute(Qt.WA_StyledBackground, True)
            div.setStyleSheet(f"background: {COLORS['border']};")
            rl.addWidget(div)
    return w


def _side_header() -> QWidget:
    w = QWidget()
    w.setAttribute(Qt.WA_StyledBackground, True)
    rl = QHBoxLayout(w)
    rl.setContentsMargins(0, 0, 0, 0)
    rl.setSpacing(0)
    for i, (label, color, bg) in enumerate([
        ("BEFORE", "#ef4444", "rgba(239,68,68,0.08)"),
        ("AFTER",  "#22c55e", "rgba(34,197,94,0.08)"),
    ]):
        cell = QWidget()
        cell.setAttribute(Qt.WA_StyledBackground, True)
        cell.setStyleSheet(f"background: {bg};")
        cell.setFixedHeight(28)
        cl = QHBoxLayout(cell)
        cl.setContentsMargins(40, 0, 12, 0)
        lbl = QLabel(label)
        lbl.setStyleSheet(
            f"background: transparent; font-size: 10px; font-weight: 700;"
            f" color: {color}; letter-spacing: 0.08em;"
        )
        cl.addWidget(lbl)
        cl.addStretch()
        rl.addWidget(cell, 1)
        if i == 0:
            div = QWidget()
            div.setFixedWidth(1)
            div.setAttribute(Qt.WA_StyledBackground, True)
            div.setStyleSheet(f"background: {COLORS['border']};")
            rl.addWidget(div)
    return w


def _render_hunks(hunks: list, layout: QVBoxLayout, limit: int = 100):
    if not hunks:
        return
    layout.addWidget(_side_header())
    rendered = 0
    total = sum(max(len(h["removed"]), len(h["added"])) for h in hunks)
    for i, hunk in enumerate(hunks):
        if rendered >= limit:
            break
        if i > 0:
            layout.addWidget(_side_gap())
        removed, added = hunk["removed"], hunk["added"]
        for j in range(max(len(removed), len(added))):
            if rendered >= limit:
                break
            layout.addWidget(_side_row(
                removed[j] if j < len(removed) else None,
                added[j]   if j < len(added)   else None,
            ))
            rendered += 1
    if total > limit:
        more = QLabel(f"  … {total - limit} more lines")
        more.setStyleSheet(
            f"background: transparent; font-size: 11px;"
            f" color: {COLORS['text_muted']}; padding: 6px 16px;"
        )
        layout.addWidget(more)


def _scrollbar_style(colors) -> str:
    b, m = colors["border"], colors["text_muted"]
    return f"""
        QScrollArea {{ background: transparent; border: none; }}
        QScrollBar:vertical {{
            background: transparent; width: 8px; margin: 0;
        }}
        QScrollBar::handle:vertical {{
            background: {b}; border-radius: 4px; min-height: 32px;
        }}
        QScrollBar::handle:vertical:hover {{ background: {m}; }}
        QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
        QScrollBar::add-page:vertical,  QScrollBar::sub-page:vertical  {{ background: transparent; }}
        QScrollBar:horizontal {{
            background: transparent; height: 8px; margin: 0;
        }}
        QScrollBar::handle:horizontal {{
            background: {b}; border-radius: 4px; min-width: 32px;
        }}
        QScrollBar::handle:horizontal:hover {{ background: {m}; }}
        QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{ width: 0; }}
        QScrollBar::add-page:horizontal, QScrollBar::sub-page:horizontal {{ background: transparent; }}
    """

def _close_btn_style(colors) -> str:
    return f"""
        QPushButton {{
            background: transparent; border: 1px solid {colors['border']};
            border-radius: 8px; color: {colors['text_muted']}; font-size: 13px;
        }}
        QPushButton:hover {{
            background: {colors['bg_hover']}; color: {colors['text_primary']};
        }}
    """


class _Row(QWidget):
    """Label + value pair."""

    def __init__(self, label: str, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(3)

        lbl = QLabel(label.upper())
        lbl.setStyleSheet(
            f"background: transparent; font-size: 10px; font-weight: 600; color: {COLORS['text_muted']}; letter-spacing: 0.07em;"
        )
        layout.addWidget(lbl)

        self._value = QLabel("—")
        self._value.setWordWrap(True)
        self._value.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self._value.setStyleSheet(f"background: transparent; font-size: 13px; color: {COLORS['text_primary']};")
        layout.addWidget(self._value)

    def set(self, text: str, color: str = None, mono: bool = False):
        col = color or COLORS["text_primary"]
        mono_css = "font-family: Consolas, 'Courier New', monospace;" if mono else ""
        self._value.setStyleSheet(f"background: transparent; font-size: 13px; color: {col}; {mono_css}")
        self._value.setText(text)


_STATUS_COLOR = {
    "added":    "#22c55e",
    "deleted":  "#ef4444",
    "modified": "#6366f1",
    "renamed":  "#f59e0b",
}

_STATUS_LABEL = {
    "added":    "Added",
    "deleted":  "Deleted",
    "modified": "Edited",
    "renamed":  "Renamed",
}


class _MiniBar(QWidget):
    """5-block visual bar — green blocks = additions, red = deletions."""

    def __init__(self, ins: int, dels: int, parent=None):
        super().__init__(parent)
        self.setFixedSize(40, 8)
        total = max(ins + dels, 1)
        self._green = round(ins / total * 5)
        self._red   = 5 - self._green

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setPen(Qt.NoPen)
        block_w, gap = 6, 2
        for i in range(5):
            x = i * (block_w + gap)
            color = "#22c55e" if i < self._green else "#ef4444"
            p.setBrush(QBrush(QColor(color)))
            p.drawRoundedRect(x, 0, block_w, 8, 2, 2)
        p.end()


class _DiffLine(QWidget):
    """Single line in the expanded diff view."""

    _BG     = {"added": "rgba(34,197,94,0.10)", "removed": "rgba(239,68,68,0.10)"}
    _NUM_BG = {"added": "rgba(34,197,94,0.06)", "removed": "rgba(239,68,68,0.06)"}

    def __init__(self, kind: str, text: str, line_num: int = None, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setStyleSheet(f"background: {self._BG.get(kind, 'transparent')};")

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 2, 12, 2)
        layout.setSpacing(0)

        if line_num is not None:
            num_lbl = QLabel(str(line_num))
            num_lbl.setFixedWidth(42)
            num_lbl.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
            num_lbl.setStyleSheet(
                f"background: {self._NUM_BG.get(kind, 'transparent')};"
                f" font-family: Consolas, monospace; font-size: 10px;"
                f" color: {COLORS['text_muted']}; padding-right: 8px;"
            )
            layout.addWidget(num_lbl)

        lbl = QLabel(text[:140] or " ")
        lbl.setTextInteractionFlags(Qt.TextSelectableByMouse)
        fg = COLORS["text_primary"] if kind in ("added", "removed") else COLORS["text_muted"]
        lbl.setStyleSheet(
            f"background: transparent; font-family: Consolas, monospace;"
            f" font-size: 11px; color: {fg}; padding-left: 10px;"
        )
        layout.addWidget(lbl)


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

        name_lbl = QLabel(info["name"])
        name_lbl.setStyleSheet(
            f"background: transparent; font-size: 12px; font-weight: 600;"
            f" color: {COLORS['text_primary']};"
        )
        nb.addWidget(name_lbl)

        parts = info["path"].split("/")
        if len(parts) > 1:
            dir_lbl = QLabel("/".join(parts[:-1]))
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
        if not self._selected:
            self.setStyleSheet("background: rgba(255,255,255,6); border-radius: 6px;")

    def leaveEvent(self, _):
        self.setStyleSheet("background: transparent; border-radius: 6px;")


def _divider() -> QFrame:
    f = QFrame()
    f.setFrameShape(QFrame.HLine)
    f.setStyleSheet(f"background: {COLORS['border']}; max-height: 1px;")
    return f


class ChangesPanel(QWidget):
    """
    Slides in from behind the detail panel to show a file's diff.
    Hidden position: x = parent.width() - PANEL_W  (tucked behind detail panel)
    Shown  position: x = parent.width() - PANEL_W - CHANGES_W
    """

    panel_toggled = pyqtSignal(bool)

    def __init__(self, parent: QWidget):
        super().__init__(parent)
        self.setFixedWidth(CHANGES_W)
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setStyleSheet(f"""
            ChangesPanel {{
                background: {COLORS['bg_secondary']};
                border-left: 1px solid {COLORS['border']};
            }}
        """)

        self._anim = QPropertyAnimation(self, b"geometry")
        self._anim.setDuration(200)
        self._anim.setEasingCurve(QEasingCurve.OutCubic)

        self._visible      = False
        self._current_path: str | None = None
        self._setup_ui()
        self._place(visible=False, animate=False)

    def _setup_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        hdr = QWidget()
        hdr.setObjectName("chgHdr")
        hdr.setFixedHeight(64)
        hdr.setStyleSheet(f"""
            #chgHdr {{
                background: {COLORS['bg_card']};
                border-bottom: 1px solid {COLORS['border']};
            }}
        """)
        hl = QHBoxLayout(hdr)
        hl.setContentsMargins(16, 0, 12, 0)
        hl.setSpacing(10)

        info_block = QVBoxLayout()
        info_block.setSpacing(3)
        info_block.setAlignment(Qt.AlignVCenter)

        self._title = QLabel("—")
        self._title.setStyleSheet(
            f"background: transparent; font-size: 13px; font-weight: 600;"
            f" color: {COLORS['text_primary']};"
        )
        self._subtitle = QLabel("")
        self._subtitle.setStyleSheet(
            f"background: transparent; font-size: 10px; color: {COLORS['text_muted']};"
        )
        info_block.addWidget(self._title)
        info_block.addWidget(self._subtitle)
        hl.addLayout(info_block)
        hl.addStretch()

        close_btn = QPushButton("✕")
        close_btn.setFixedSize(40, 40)
        close_btn.setCursor(Qt.PointingHandCursor)
        close_btn.setStyleSheet(_close_btn_style(COLORS))
        close_btn.clicked.connect(self.hide_panel)
        hl.addWidget(close_btn)
        root.addWidget(hdr)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setStyleSheet(_scrollbar_style(COLORS))

        self._content = QWidget()
        self._content.setStyleSheet("background: transparent;")
        self._content_layout = QVBoxLayout(self._content)
        self._content_layout.setContentsMargins(0, 8, 0, 8)
        self._content_layout.setSpacing(0)

        scroll.setWidget(self._content)
        scroll.viewport().setStyleSheet("background: transparent;")
        root.addWidget(scroll)

    def show_file(self, info: dict):
        self._current_path = info["path"]
        self._title.setText(info["name"])
        color = _STATUS_COLOR.get(info["status"], COLORS["accent"])
        label = _STATUS_LABEL.get(info["status"], "")
        path  = info["path"]
        self._subtitle.setText(
            f'<span style="color:{color};">{label}</span>'
            + (f"  ·  {path}" if "/" in path else "")
        )
        self._subtitle.setTextFormat(Qt.RichText)

        while self._content_layout.count():
            item = self._content_layout.takeAt(0)
            w = item.widget()
            if w:
                w.setParent(None)

        if info["is_binary"]:
            lbl = QLabel("Binary file — no preview available")
            lbl.setStyleSheet(
                f"background: transparent; font-size: 12px;"
                f" color: {COLORS['text_muted']}; padding: 20px;"
            )
            lbl.setAlignment(Qt.AlignCenter)
            self._content_layout.addWidget(lbl)
        elif not info["lines"]:
            lbl = QLabel("No changes to show")
            lbl.setStyleSheet(
                f"background: transparent; font-size: 12px;"
                f" color: {COLORS['text_muted']}; padding: 20px;"
            )
            lbl.setAlignment(Qt.AlignCenter)
            self._content_layout.addWidget(lbl)
        else:
            for i, hunk in enumerate(_compute_hunks(info["lines"])):
                if i > 0:
                    gap = QLabel("· · ·")
                    gap.setAlignment(Qt.AlignCenter)
                    gap.setStyleSheet(
                        f"background: transparent; color: {COLORS['text_muted']};"
                        f" font-size: 11px; padding: 6px 0;"
                    )
                    self._content_layout.addWidget(gap)
                self._add_hunk(hunk)

        self._content_layout.addStretch()

        if not self._visible:
            self._place(visible=True, animate=True)

    def _add_section(self, title: str, lines: list, kind: str):
        """lines: list of (line_num, text)"""
        if not lines:
            return
        color = "#22c55e" if kind == "added" else "#ef4444"

        hdr = QWidget()
        hdr.setAttribute(Qt.WA_StyledBackground, True)
        hdr.setStyleSheet(
            f"background: {'rgba(34,197,94,0.08)' if kind == 'added' else 'rgba(239,68,68,0.08)'};"
        )
        hdr.setFixedHeight(28)
        hl = QHBoxLayout(hdr)
        hl.setContentsMargins(12, 0, 12, 0)
        lbl = QLabel(title)
        lbl.setStyleSheet(
            f"background: transparent; font-size: 10px; font-weight: 700;"
            f" color: {color}; letter-spacing: 0.08em;"
        )
        hl.addWidget(lbl)
        hl.addStretch()
        count_lbl = QLabel(f"{len(lines)} line{'s' if len(lines) != 1 else ''}")
        count_lbl.setStyleSheet(
            f"background: transparent; font-size: 10px; color: {color};"
        )
        hl.addWidget(count_lbl)
        self._content_layout.addWidget(hdr)

        limit  = 80
        chunks = _chunk_lines(lines[:limit])
        for i, chunk in enumerate(chunks):
            if i > 0:
                gap = QLabel("· · ·")
                gap.setAlignment(Qt.AlignCenter)
                gap.setStyleSheet(
                    f"background: transparent; color: {COLORS['text_muted']};"
                    f" font-size: 11px; padding: 4px 0;"
                )
                self._content_layout.addWidget(gap)
            for line_num, text in chunk:
                self._content_layout.addWidget(_DiffLine(kind, text, line_num))

        if len(lines) > limit:
            more = QLabel(f"  … {len(lines) - limit} more lines")
            more.setStyleSheet(
                f"background: transparent; font-size: 11px;"
                f" color: {COLORS['text_muted']}; padding: 4px 12px;"
            )
            self._content_layout.addWidget(more)

    def _add_hunk(self, hunk: dict):
        removed, added = _filter_unchanged(hunk["removed"], hunk["added"])
        if not removed and not added:
            return
        if removed and added:
            self._add_section("Previous", removed, "removed")
            div = QFrame()
            div.setFrameShape(QFrame.HLine)
            div.setStyleSheet(f"background: {COLORS['border']}; max-height: 1px;")
            self._content_layout.addWidget(div)
            self._add_section("Changed", added, "added")
        elif removed:
            self._add_section("Deleted", removed, "removed")
        elif added:
            self._add_section("Added", added, "added")

    def hide_panel(self):
        if self._visible:
            self._current_path = None
            self._place(visible=False, animate=True)

    def reposition(self):
        self._place(self._visible, animate=False)

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
        h        = p.height()
        x_shown  = p.width() - PANEL_W - CHANGES_W
        x_hidden = p.width()
        target   = QRect(x_shown if visible else x_hidden, 0, CHANGES_W, h)
        if animate:
            self._anim.stop()
            self._anim.setStartValue(self.geometry())
            self._anim.setEndValue(target)
            self._anim.start()
        else:
            self.setGeometry(target)


class AllChangesPopup(QWidget):
    """Full-screen overlay showing every file's before/after changes."""

    def __init__(self, files: list[dict], commit_label: str, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setObjectName("allChangesOverlay")
        if parent:
            self.setGeometry(parent.rect())
        self.raise_()
        self._build(files, commit_label)

    def _build(self, files: list[dict], commit_label: str):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(80, 60, 80, 60)
        outer.setSpacing(0)

        card = QWidget()
        card.setAttribute(Qt.WA_StyledBackground, True)
        card.setObjectName("acCard")
        card.setStyleSheet(f"""
            #acCard {{
                background: {COLORS['bg_secondary']};
                border-radius: 12px;
            }}
        """)
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(0, 0, 0, 0)
        card_layout.setSpacing(0)

        # Header
        hdr = QWidget()
        hdr.setObjectName("acHdr")
        hdr.setFixedHeight(64)
        hdr.setStyleSheet(f"""
            #acHdr {{
                background: {COLORS['bg_card']};
                border-bottom: 1px solid {COLORS['border']};
                border-radius: 12px 12px 0 0;
            }}
        """)
        hl = QHBoxLayout(hdr)
        hl.setContentsMargins(24, 0, 16, 0)
        hl.setSpacing(12)

        title = QLabel("All Changes")
        title.setStyleSheet(
            f"background: transparent; font-size: 15px; font-weight: 700;"
            f" color: {COLORS['text_primary']};"
        )
        hl.addWidget(title)

        sub = QLabel(commit_label)
        sub.setStyleSheet(
            f"background: transparent; font-size: 12px; color: {COLORS['text_muted']};"
        )
        hl.addWidget(sub)
        hl.addStretch()

        n = len(files)
        count = QLabel(f"{n} file{'s' if n != 1 else ''}")
        count.setStyleSheet(
            f"background: transparent; font-size: 12px; color: {COLORS['text_muted']};"
        )
        hl.addWidget(count)

        close_btn = QPushButton("✕")
        close_btn.setFixedSize(40, 40)
        close_btn.setCursor(Qt.PointingHandCursor)
        close_btn.setStyleSheet(_close_btn_style(COLORS))
        close_btn.clicked.connect(self.close)
        hl.addWidget(close_btn)
        card_layout.addWidget(hdr)

        # Scrollable file sections
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setStyleSheet(_scrollbar_style(COLORS))

        content = QWidget()
        content.setStyleSheet("background: transparent;")
        cl = QVBoxLayout(content)
        cl.setContentsMargins(24, 16, 24, 24)
        cl.setSpacing(0)

        for i, info in enumerate(files):
            if i > 0:
                sep = QFrame()
                sep.setFrameShape(QFrame.HLine)
                sep.setStyleSheet(
                    f"background: {COLORS['border']}; max-height: 1px; margin: 0;"
                )
                cl.addWidget(sep)
            cl.addWidget(self._file_section(info))

        cl.addStretch()
        scroll.setWidget(content)
        scroll.viewport().setStyleSheet("background: transparent;")
        card_layout.addWidget(scroll)

        outer.addWidget(card)

    def _file_section(self, info: dict) -> QWidget:
        section = QWidget()
        section.setAttribute(Qt.WA_StyledBackground, True)
        section.setStyleSheet("background: transparent;")
        sl = QVBoxLayout(section)
        sl.setContentsMargins(0, 0, 0, 0)
        sl.setSpacing(0)

        # File header
        fhdr = QWidget()
        fhdr.setFixedHeight(52)
        fhdr.setAttribute(Qt.WA_StyledBackground, True)
        fhdr.setStyleSheet(f"background: transparent;")
        fhl = QHBoxLayout(fhdr)
        fhl.setContentsMargins(0, 0, 0, 0)
        fhl.setSpacing(8)

        color = _STATUS_COLOR.get(info["status"], COLORS["accent"])
        dot = QLabel("●")
        dot.setStyleSheet(f"background: transparent; font-size: 9px; color: {color};")
        fhl.addWidget(dot)

        name = QLabel(info["name"])
        name.setStyleSheet(
            f"background: transparent; font-size: 13px; font-weight: 600;"
            f" color: {COLORS['text_primary']};"
        )
        fhl.addWidget(name)

        if "/" in info["path"]:
            path_parts = "/".join(info["path"].split("/")[:-1])
            path_lbl = QLabel(f"  {path_parts}")
            path_lbl.setStyleSheet(
                f"background: transparent; font-size: 11px; color: {COLORS['text_muted']};"
            )
            fhl.addWidget(path_lbl)

        fhl.addStretch()

        if not info["is_binary"]:
            counts = QLabel(f"+{info['insertions']}  −{info['deletions']}")
            counts.setStyleSheet(
                f"background: transparent; font-size: 11px;"
                f" color: {COLORS['text_muted']}; font-family: monospace;"
            )
            fhl.addWidget(counts)
            fhl.addWidget(_MiniBar(info["insertions"], info["deletions"]))
        sl.addWidget(fhdr)

        # Before / After
        if info["is_binary"]:
            lbl = QLabel("Binary file")
            lbl.setStyleSheet(
                f"background: transparent; font-size: 12px;"
                f" color: {COLORS['text_muted']}; padding: 12px 16px;"
            )
            sl.addWidget(lbl)
        else:
            for i, hunk in enumerate(_compute_hunks(info["lines"])):
                if i > 0:
                    gap = QLabel("· · ·")
                    gap.setAlignment(Qt.AlignCenter)
                    gap.setStyleSheet(
                        f"background: transparent; color: {COLORS['text_muted']};"
                        f" font-size: 11px; padding: 6px 0;"
                    )
                    sl.addWidget(gap)
                removed, added = hunk["removed"], hunk["added"]
                if removed and added:
                    sl.addWidget(self._diff_block("Previous", removed, "removed"))
                    div = QFrame()
                    div.setFrameShape(QFrame.HLine)
                    div.setStyleSheet(f"background: {COLORS['border']}; max-height: 1px;")
                    sl.addWidget(div)
                    sl.addWidget(self._diff_block("Changed", added, "added"))
                elif removed:
                    sl.addWidget(self._diff_block("Deleted", removed, "removed"))
                elif added:
                    sl.addWidget(self._diff_block("Added", added, "added"))

        return section

    def _diff_block(self, title: str, lines: list, kind: str) -> QWidget:
        color = "#22c55e" if kind == "added" else "#ef4444"
        bg    = "rgba(34,197,94,0.06)" if kind == "added" else "rgba(239,68,68,0.06)"
        block = QWidget()
        block.setAttribute(Qt.WA_StyledBackground, True)
        block.setStyleSheet("background: transparent;")
        bl = QVBoxLayout(block)
        bl.setContentsMargins(0, 0, 0, 0)
        bl.setSpacing(0)

        hdr = QWidget()
        hdr.setAttribute(Qt.WA_StyledBackground, True)
        hdr.setStyleSheet(f"background: {bg};")
        hdr.setFixedHeight(32)
        hhl = QHBoxLayout(hdr)
        hhl.setContentsMargins(16, 0, 16, 0)
        lbl = QLabel(title)
        lbl.setStyleSheet(
            f"background: transparent; font-size: 10px; font-weight: 700;"
            f" color: {color}; letter-spacing: 0.08em;"
        )
        hhl.addWidget(lbl)
        hhl.addStretch()
        c_lbl = QLabel(f"{len(lines)} line{'s' if len(lines) != 1 else ''}")
        c_lbl.setStyleSheet(f"background: transparent; font-size: 10px; color: {color};")
        hhl.addWidget(c_lbl)
        bl.addWidget(hdr)

        limit  = 80
        chunks = _chunk_lines(lines[:limit])
        for i, chunk in enumerate(chunks):
            if i > 0:
                gap = QLabel("· · ·")
                gap.setAlignment(Qt.AlignCenter)
                gap.setStyleSheet(
                    f"background: transparent; color: {COLORS['text_muted']};"
                    f" font-size: 11px; padding: 4px 0;"
                )
                bl.addWidget(gap)
            for line_num, text in chunk:
                bl.addWidget(_DiffLine(kind, text, line_num))

        if len(lines) > limit:
            more = QLabel(f"  … {len(lines) - limit} more lines")
            more.setStyleSheet(
                f"background: transparent; font-size: 11px;"
                f" color: {COLORS['text_muted']}; padding: 6px 16px;"
            )
            bl.addWidget(more)

        return block

    def _diff_block(self, title: str, lines: list, kind: str) -> QWidget:
        """lines: list of (line_num, text)"""
        color  = "#22c55e" if kind == "added" else "#ef4444"
        bg     = "rgba(34,197,94,0.06)" if kind == "added" else "rgba(239,68,68,0.06)"
        block  = QWidget()
        block.setAttribute(Qt.WA_StyledBackground, True)
        block.setStyleSheet("background: transparent;")
        bl = QVBoxLayout(block)
        bl.setContentsMargins(0, 0, 0, 0)
        bl.setSpacing(0)

        hdr = QWidget()
        hdr.setAttribute(Qt.WA_StyledBackground, True)
        hdr.setStyleSheet(f"background: {bg};")
        hdr.setFixedHeight(32)
        hhl = QHBoxLayout(hdr)
        hhl.setContentsMargins(16, 0, 16, 0)
        lbl = QLabel(title)
        lbl.setStyleSheet(
            f"background: transparent; font-size: 10px; font-weight: 700;"
            f" color: {color}; letter-spacing: 0.08em;"
        )
        hhl.addWidget(lbl)
        hhl.addStretch()
        c_lbl = QLabel(f"{len(lines)} line{'s' if len(lines) != 1 else ''}")
        c_lbl.setStyleSheet(f"background: transparent; font-size: 10px; color: {color};")
        hhl.addWidget(c_lbl)
        bl.addWidget(hdr)

        limit   = 120
        capped  = lines[:limit]
        chunks  = _chunk_lines(capped)
        for i, chunk in enumerate(chunks):
            if i > 0:
                gap = QLabel("· · ·")
                gap.setAlignment(Qt.AlignCenter)
                gap.setStyleSheet(
                    f"background: transparent; color: {COLORS['text_muted']};"
                    f" font-size: 11px; padding: 4px 0;"
                )
                bl.addWidget(gap)
            for line_num, text in chunk:
                bl.addWidget(_DiffLine(kind, text, line_num))

        if len(lines) > limit:
            more = QLabel(f"  … {len(lines) - limit} more lines")
            more.setStyleSheet(
                f"background: transparent; font-size: 11px;"
                f" color: {COLORS['text_muted']}; padding: 6px 16px;"
            )
            bl.addWidget(more)

        return block

    def paintEvent(self, _):
        p = QPainter(self)
        p.fillRect(self.rect(), QColor(0, 0, 0, 170))
        p.end()

    def mousePressEvent(self, event):
        card = self.findChild(QWidget, "acCard")
        if card and not card.geometry().contains(event.pos()):
            self.close()
        super().mousePressEvent(event)

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Escape:
            self.close()
        super().keyPressEvent(event)


class DetailPanel(QWidget):
    """
    Slides in from the right edge of its parent when show_commit() is called.
    Parent must call reposition() whenever its size changes.
    """
    panel_toggled = pyqtSignal(bool)    # True = opening, False = closing
    file_selected = pyqtSignal(dict)   # file info dict when a card is clicked

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
        self._setup_ui()

        # Start off-screen to the right
        self._place(visible=False, animate=False)

    # ── UI ────────────────────────────────────────────────────────────────────

    def _setup_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # Header bar
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
            f"background: transparent; font-size: 14px; font-weight: 600; color: {COLORS['text_primary']};"
        )
        self._header_branch = QLabel("—")
        self._header_branch.setStyleSheet(
            f"background: transparent; font-size: 11px; color: {COLORS['text_muted']}; letter-spacing: 0.02em;"
        )
        name_block.addWidget(self._header_name)
        name_block.addWidget(self._header_branch)
        header_layout.addLayout(name_block)
        header_layout.addStretch()

        close_btn = QPushButton("✕")
        close_btn.setFixedSize(40, 40)
        close_btn.setCursor(Qt.PointingHandCursor)
        close_btn.setStyleSheet(_close_btn_style(COLORS))
        close_btn.clicked.connect(self.hide_panel)
        header_layout.addWidget(close_btn)
        root.addWidget(header)

        # Scrollable content
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setStyleSheet(_scrollbar_style(COLORS))

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
            f"background: transparent; font-size: 10px; font-weight: 600; color: {COLORS['text_muted']}; letter-spacing: 0.07em;"
        )
        content_layout.addWidget(msg_label)

        self._message = QLabel("—")
        self._message.setWordWrap(True)
        self._message.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self._message.setStyleSheet(f"background: transparent; font-size: 13px; color: {COLORS['text_primary']}; line-height: 1.5;")
        content_layout.addWidget(self._message)

        content_layout.addWidget(_divider())

        files_hdr = QWidget()
        files_hdr.setStyleSheet("background: transparent;")
        fhl = QHBoxLayout(files_hdr)
        fhl.setContentsMargins(0, 0, 0, 0)
        fhl.setSpacing(0)

        self._files_label = QLabel("CHANGES")
        self._files_label.setStyleSheet(
            f"background: transparent; font-size: 10px; font-weight: 600;"
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
        for card in self._file_cards:
            card.set_selected(card._info is info)
        self._selected_card = next((c for c in self._file_cards if c._info is info), None)
        self.file_selected.emit(info)

    def deselect_files(self):
        for card in getattr(self, "_file_cards", []):
            card.set_selected(False)
        self._selected_card = None

    def show_commit(self, commit, detail: dict, avatar_url: str = "",
                    display_author: str = None, files: list = None):
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

    def hide_panel(self):
        if self._visible:
            self.deselect_files()
            self._place(visible=False, animate=True)

    def reposition(self):
        """Call this from the parent's resizeEvent."""
        self._place(visible=self._visible, animate=False)

    def mousePressEvent(self, event):
        self._swipe_start: QPoint = event.pos()
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event):
        if hasattr(self, "_swipe_start"):
            if event.pos().x() - self._swipe_start.x() > SWIPE_THRESHOLD:
                self.hide_panel()
        super().mouseReleaseEvent(event)

    # ── Internal ─────────────────────────────────────────────────────────────

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

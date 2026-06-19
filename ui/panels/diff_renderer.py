"""Shared diff-rendering utilities, small widgets, and style helpers.

Used by ChangesPanel, AllChangesPopup, and DetailPanel.
"""
from __future__ import annotations

import re
from difflib import SequenceMatcher

from PyQt5.QtCore import Qt, QPropertyAnimation, QEasingCurve
from PyQt5.QtGui import QPainter, QColor, QBrush, QPen
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QScrollArea,
    QFrame, QSizePolicy, QGraphicsOpacityEffect,
)

from styles.theme import COLORS, scrollbar_style

# ── Panel size constants ──────────────────────────────────────────────────────
PANEL_W         = 320
CHANGES_W       = 460
SWIPE_THRESHOLD = 70   # px rightward drag to dismiss a panel

# ── Status colours / labels ───────────────────────────────────────────────────
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


# ── Scroll area ───────────────────────────────────────────────────────────────

class _VScrollArea(QScrollArea):
    """QScrollArea that clamps content to viewport width and blocks horizontal scrolling."""

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


# ── Text helpers ──────────────────────────────────────────────────────────────

def _trunc(text: str, n: int) -> str:
    return text if len(text) <= n else text[:n - 1] + "…"


# ── Style helpers ─────────────────────────────────────────────────────────────

def _scrollbar_style(_colors=None) -> str:
    """Thin wrapper kept for backward compatibility — delegates to theme.scrollbar_style()."""
    return "QScrollArea { background: transparent; border: none; }\n" + scrollbar_style()


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


# ── Diff parsing ──────────────────────────────────────────────────────────────

def _filter_unchanged(removed: list, added: list) -> tuple[list, list]:
    """Drop lines that are positionally paired and content-identical — they only moved."""
    if not removed or not added:
        return removed, added
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


# ── Side-by-side diff widgets ─────────────────────────────────────────────────

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
            f"background: transparent; font-size: 10px; font-weight: 700; font-family: 'Tilt Warp';"
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


# ── Small reusable widgets ────────────────────────────────────────────────────

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


class _Row(QWidget):
    """Label + value pair."""

    def __init__(self, label: str, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(3)

        lbl = QLabel(label.upper())
        lbl.setStyleSheet(
            f"background: transparent; font-size: 10px; font-weight: 600; font-family: 'Tilt Warp';"
            f" color: {COLORS['text_muted']}; letter-spacing: 0.07em;"
        )
        layout.addWidget(lbl)

        self._value = QLabel("—")
        self._value.setWordWrap(True)
        self._value.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self._value.setStyleSheet(
            f"background: transparent; font-size: 13px; color: {COLORS['text_primary']};"
        )
        layout.addWidget(self._value)

    def set(self, text: str, color: str = None, mono: bool = False):
        col = color or COLORS["text_primary"]
        mono_css = "font-family: Consolas, 'Courier New', monospace;" if mono else ""
        self._value.setStyleSheet(
            f"background: transparent; font-size: 13px; color: {col}; {mono_css}"
        )
        self._value.setText(text)


# ── Animation helpers ─────────────────────────────────────────────────────────

def _fade_in(widget: QWidget, duration: int = 300):
    effect = QGraphicsOpacityEffect(widget)
    widget.setGraphicsEffect(effect)
    anim = QPropertyAnimation(effect, b"opacity", widget)
    anim.setDuration(duration)
    anim.setStartValue(0.0)
    anim.setEndValue(1.0)
    anim.setEasingCurve(QEasingCurve.OutCubic)
    anim.start()
    widget._fade_anim = anim


def _fade_out_and_remove(widget: QWidget, layout, duration: int = 250):
    effect = QGraphicsOpacityEffect(widget)
    widget.setGraphicsEffect(effect)
    anim = QPropertyAnimation(effect, b"opacity", widget)
    anim.setDuration(duration)
    anim.setStartValue(1.0)
    anim.setEndValue(0.0)
    anim.setEasingCurve(QEasingCurve.InCubic)
    def _remove():
        layout.removeWidget(widget)
        widget.setParent(None)
    anim.finished.connect(_remove)
    anim.start()
    widget._fade_anim = anim


def _divider() -> QFrame:
    f = QFrame()
    f.setFrameShape(QFrame.HLine)
    f.setStyleSheet(f"background: {COLORS['border']}; max-height: 1px;")
    return f

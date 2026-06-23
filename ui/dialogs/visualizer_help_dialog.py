"""Help dialog explaining the visual elements and actions on the visualizer."""
from __future__ import annotations

from PyQt5.QtCore import Qt, QPointF
from PyQt5.QtGui import (
    QPainter, QColor, QPen, QBrush,
    QPolygonF,
)
from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QWidget,
    QScrollArea, QStackedWidget,
)
from styles.theme import COLORS, card_shadow, scrollbar_style

_ACCENT = QColor(COLORS["accent"])
_DANGER = QColor(COLORS["danger"])
_WARNING = QColor(COLORS["warning"])
_BLUE = QColor("#3b82f6")
_RED = QColor("#ef4444")
_AMBER = QColor("#d69e2e")
_INDIGO = QColor("#7c83db")
_WHITE_EDGE = QColor(255, 255, 255, 140)

NODE_R = 10
START_R = 14


# ── Small illustration strips ────────────────────────────────────────────────

class _Strip(QWidget):
    """Base for a small illustration drawn with QPainter."""

    def __init__(self, h: int = 44, parent=None):
        super().__init__(parent)
        self.setFixedSize(60, h)
        self.setStyleSheet("background: transparent;")

    def paintEvent(self, _ev):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        self._draw(p)
        p.end()

    def _draw(self, p: QPainter):
        pass

    # shared helpers matching graphics_items.py exactly
    def _node(self, p: QPainter, cx: float, cy: float, color: QColor,
              r: float = NODE_R, filled: bool = True):
        if filled:
            p.setBrush(QBrush(color))
            p.setPen(QPen(QColor(255, 255, 255, 120), 1.5))
        else:
            p.setBrush(Qt.NoBrush)
            p.setPen(QPen(color, 2.5))
        p.drawEllipse(QPointF(cx, cy), r, r)

    def _edge_line(self, p: QPainter, x1, y1, x2, y2, dashed=False):
        pen = QPen(_WHITE_EDGE, 1.5)
        if dashed:
            pen.setStyle(Qt.DashLine)
        pen.setCapStyle(Qt.RoundCap)
        p.setPen(pen)
        p.drawLine(QPointF(x1, y1), QPointF(x2, y2))


class _CommitStrip(_Strip):
    def _draw(self, p):
        self._node(p, 30, 22, _ACCENT)


class _UnpushedStrip(_Strip):
    def _draw(self, p):
        self._node(p, 30, 22, _ACCENT, filled=False)


class _HeadStrip(_Strip):
    def _draw(self, p):
        self._node(p, 30, 22, _ACCENT)
        p.setBrush(Qt.NoBrush)
        p.setPen(QPen(_DANGER, 2.5))
        p.drawEllipse(QPointF(30, 22), NODE_R + 5, NODE_R + 5)


class _FlagStrip(_Strip):
    def __init__(self, parent=None):
        super().__init__(h=52, parent=parent)

    def _draw(self, p):
        cy = 32
        r = START_R
        self._node(p, 30, cy, _ACCENT, r=r)
        pole_top = QPointF(30, cy - r - 20)
        pole_bot = QPointF(30, cy - r - 2)
        p.setPen(QPen(_ACCENT, 2))
        p.drawLine(pole_bot, pole_top)
        flag = QPolygonF([
            pole_top,
            QPointF(39, cy - r - 12),
            QPointF(30, cy - r - 5),
        ])
        p.setBrush(QBrush(_ACCENT))
        p.setPen(Qt.NoPen)
        p.drawPolygon(flag)


class _StashStrip(_Strip):
    def _draw(self, p):
        self._node(p, 30, 18, _ACCENT)
        p.setPen(Qt.NoPen)
        p.setBrush(QBrush(_AMBER))
        p.drawEllipse(QPointF(30, 18 + NODE_R + 5), 3.5, 3.5)


class _LocalTipStrip(_Strip):
    def _draw(self, p):
        self._node(p, 26, 22, _ACCENT)
        p.setPen(Qt.NoPen)
        p.setBrush(QBrush(_BLUE))
        p.drawEllipse(QPointF(26 + NODE_R + 6, 22), 4, 4)


class _RemoteTipStrip(_Strip):
    def _draw(self, p):
        self._node(p, 26, 22, _ACCENT)
        p.setPen(Qt.NoPen)
        p.setBrush(QBrush(_RED))
        p.drawEllipse(QPointF(26 + NODE_R + 6, 22), 4, 4)


class _BothTipsStrip(_Strip):
    def _draw(self, p):
        self._node(p, 22, 22, _ACCENT)
        p.setPen(Qt.NoPen)
        p.setBrush(QBrush(_BLUE))
        p.drawEllipse(QPointF(22 + NODE_R + 4, 22), 4, 4)
        p.setBrush(QBrush(_RED))
        p.drawEllipse(QPointF(22 + NODE_R + 11, 22), 4, 4)


class _SolidEdgeStrip(_Strip):
    def _draw(self, p):
        self._node(p, 14, 22, _ACCENT)
        self._node(p, 46, 22, _INDIGO)
        self._edge_line(p, 14 + NODE_R + 2, 22, 46 - NODE_R - 2, 22)


class _DashedEdgeStrip(_Strip):
    def _draw(self, p):
        self._node(p, 14, 22, _ACCENT)
        self._node(p, 46, 22, _INDIGO)
        self._edge_line(p, 14 + NODE_R + 2, 22, 46 - NODE_R - 2, 22, dashed=True)



# ── Dialog ────────────────────────────────────────────────────────────────────

_GRAPH_ITEMS = [
    (_CommitStrip, "Snapshot", "A saved snapshot of your code"),
    (_UnpushedStrip, "Unpushed snapshot", "A snapshot that hasn't been uploaded yet"),
    (_HeadStrip, "Current location", "Where you are right now"),
    (_FlagStrip, "Branch start", "The first snapshot on this branch"),
    (_StashStrip, "Unsaved changes", "This snapshot has unsaved work"),
    (_LocalTipStrip, "Local tip", "The latest snapshot on your computer"),
    (_RemoteTipStrip, "Remote tip", "The latest snapshot on GitHub"),
    (_BothTipsStrip, "Both tips", "Your latest and GitHub's latest are here"),
    (_SolidEdgeStrip, "Connection", "These snapshots are connected in order"),
    (_DashedEdgeStrip, "Branch / merge link", "Where a branch was created or merged"),
]

_ACTION_ITEMS = [
    ("Go to snapshot", "Switch your code to this point in history", None),
    ("Create branch", "Start a new line of work from this snapshot", None),
    ("Upload", "Send your local snapshots to GitHub", None),
    ("Pull latest", "Download new snapshots from GitHub", None),
    ("Sync with remote", "Combine your work with GitHub's when they've diverged", None),
    ("Hard Revert", "Permanently undo the latest snapshot", "warning"),
    ("Soft Revert", "Undo the latest snapshot but keep the changes", None),
    ("Merge into", "Combine this branch's work into another branch", None),
    ("Save Changes", "Turn your unsaved work into a new snapshot", None),
    ("Clear Changes", "Throw away all unsaved work", "danger"),
    ("Delete Branch", "Remove this branch from your project", "danger"),
]


class VisualizerHelpDialog(QDialog):

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowFlags(Qt.Dialog | Qt.FramelessWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setFixedSize(480, 580)
        self._build()

    def _build(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)

        card = QWidget()
        card.setStyleSheet(f"background: {COLORS['bg_card']}; border-radius: 12px;")
        card_shadow(card)
        outer = QVBoxLayout(card)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        # ── Title bar + close ─────────────────────────────────────────
        title_bar = QWidget()
        title_bar.setStyleSheet("background: transparent;")
        tb = QHBoxLayout(title_bar)
        tb.setContentsMargins(24, 18, 18, 10)

        title = QLabel("Visualizer Guide")
        title.setStyleSheet(
            f"font-size: 15px; font-weight: 700; color: {COLORS['text_primary']};"
            f" background: transparent;"
        )
        tb.addWidget(title)
        tb.addStretch()

        close_btn = QPushButton("✕")
        close_btn.setFixedSize(28, 28)
        close_btn.setCursor(Qt.PointingHandCursor)
        close_btn.setStyleSheet(f"""
            QPushButton {{
                background: transparent; border: none; border-radius: 14px;
                font-size: 13px; color: {COLORS['text_muted']};
            }}
            QPushButton:hover {{ background: {COLORS['bg_hover']}; color: {COLORS['text_primary']}; }}
        """)
        close_btn.clicked.connect(self.reject)
        tb.addWidget(close_btn)
        outer.addWidget(title_bar)

        # ── Tab switcher ──────────────────────────────────────────────
        self._tab_btns: dict[str, QPushButton] = {}
        tab_row = QWidget()
        tab_row.setStyleSheet("background: transparent;")
        tl = QHBoxLayout(tab_row)
        tl.setContentsMargins(24, 0, 24, 0)
        tl.setSpacing(4)

        for key, label in [("graph", "Graph"), ("actions", "Actions")]:
            btn = QPushButton(label)
            btn.setCursor(Qt.PointingHandCursor)
            btn.setFixedHeight(30)
            btn.setCheckable(True)
            btn.setChecked(key == "graph")
            btn.setStyleSheet(self._tab_style(key == "graph"))
            btn.clicked.connect(lambda _, k=key: self._switch_tab(k))
            tl.addWidget(btn)
            self._tab_btns[key] = btn

        tl.addStretch()
        outer.addWidget(tab_row)

        # ── Stacked pages ─────────────────────────────────────────────
        self._stack = QStackedWidget()
        self._stack.setStyleSheet("background: transparent;")

        self._stack.addWidget(self._build_graph_page())
        self._stack.addWidget(self._build_actions_page())

        outer.addWidget(self._stack)
        root.addWidget(card)

    # ── Tab helpers ───────────────────────────────────────────────────

    def _tab_style(self, active: bool) -> str:
        if active:
            return (
                f"QPushButton {{ background: {COLORS['accent_dim']};"
                f" border: 1px solid {COLORS['accent']}; border-radius: 6px;"
                f" font-size: 12px; font-weight: 600; color: {COLORS['accent']};"
                f" padding: 0 14px; }}"
            )
        return (
            f"QPushButton {{ background: transparent;"
            f" border: 1px solid {COLORS['border']}; border-radius: 6px;"
            f" font-size: 12px; font-weight: 500; color: {COLORS['text_muted']};"
            f" padding: 0 14px; }}"
            f"QPushButton:hover {{ border-color: {COLORS['text_muted']};"
            f" color: {COLORS['text_primary']}; }}"
        )

    def _switch_tab(self, key: str):
        idx = 0 if key == "graph" else 1
        self._stack.setCurrentIndex(idx)
        for k, btn in self._tab_btns.items():
            btn.setChecked(k == key)
            btn.setStyleSheet(self._tab_style(k == key))

    # ── Page builders ─────────────────────────────────────────────────

    def _build_graph_page(self) -> QScrollArea:
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.NoFrame)
        scroll.setStyleSheet(f"QScrollArea {{ background: transparent; border: none; }} {scrollbar_style()}")

        body = QWidget()
        body.setStyleSheet("background: transparent;")
        vl = QVBoxLayout(body)
        vl.setContentsMargins(24, 12, 24, 24)
        vl.setSpacing(6)

        for strip_cls, label, desc in _GRAPH_ITEMS:
            vl.addWidget(self._graph_row(strip_cls, label, desc))

        vl.addStretch()
        scroll.setWidget(body)
        return scroll

    def _build_actions_page(self) -> QScrollArea:
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.NoFrame)
        scroll.setStyleSheet(f"QScrollArea {{ background: transparent; border: none; }} {scrollbar_style()}")

        body = QWidget()
        body.setStyleSheet("background: transparent;")
        vl = QVBoxLayout(body)
        vl.setContentsMargins(24, 12, 24, 24)
        vl.setSpacing(6)

        for name, desc, color_key in _ACTION_ITEMS:
            vl.addWidget(self._action_row(name, desc, color_key))

        vl.addStretch()
        scroll.setWidget(body)
        return scroll

    # ── Row builders ─────────────────────────────────────────────────

    @staticmethod
    def _graph_row(strip_cls, label: str, desc: str) -> QWidget:
        row = QWidget()
        row.setStyleSheet("background: transparent;")
        hl = QHBoxLayout(row)
        hl.setContentsMargins(0, 0, 0, 0)
        hl.setSpacing(10)

        strip = strip_cls()
        hl.addWidget(strip, 0, Qt.AlignVCenter)

        text_block = QVBoxLayout()
        text_block.setSpacing(1)

        name_lbl = QLabel(label)
        name_lbl.setStyleSheet(
            f"background: transparent; font-size: 12px; font-weight: 600;"
            f" color: {COLORS['text_primary']};"
        )
        text_block.addWidget(name_lbl)

        desc_lbl = QLabel(desc)
        desc_lbl.setStyleSheet(
            f"background: transparent; font-size: 11px; color: {COLORS['text_muted']};"
        )
        desc_lbl.setWordWrap(True)
        text_block.addWidget(desc_lbl)

        hl.addLayout(text_block, 1)
        return row

    @staticmethod
    def _action_row(name: str, desc: str, color_key: str | None) -> QWidget:
        row = QWidget()
        row.setStyleSheet("background: transparent;")
        hl = QHBoxLayout(row)
        hl.setContentsMargins(0, 4, 0, 4)
        hl.setSpacing(10)

        if color_key == "danger":
            name_color = COLORS["danger"]
        elif color_key == "warning":
            name_color = COLORS["warning"]
        else:
            name_color = COLORS["text_primary"]

        badge = QLabel(name)
        badge.setStyleSheet(
            f"background: transparent; font-size: 12px; font-weight: 600;"
            f" color: {name_color};"
        )
        badge.setFixedWidth(120)
        hl.addWidget(badge, 0, Qt.AlignTop)

        desc_lbl = QLabel(desc)
        desc_lbl.setStyleSheet(
            f"background: transparent; font-size: 11px; color: {COLORS['text_muted']};"
        )
        desc_lbl.setWordWrap(True)
        hl.addWidget(desc_lbl, 1)

        return row

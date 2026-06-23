"""Help dialog explaining pull request concepts and actions."""
from __future__ import annotations

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QWidget,
    QScrollArea, QStackedWidget,
)
from styles.theme import COLORS, card_shadow, scrollbar_style

_GREEN = "#3ecf8e"
_PURPLE = "#8b5cf6"

_OVERVIEW_ITEMS = [
    (
        "What is a Pull Request?",
        "A request to merge your branch's changes into another branch. "
        "It lets you and others review changes before combining them.",
        None,
    ),
    ("Open", "The pull request is still active — changes haven't been merged yet.", _GREEN),
    ("Closed", "The pull request was closed without merging. The changes were not combined.", COLORS["text_muted"]),
    ("Merged", "The changes were successfully combined into the target branch.", _PURPLE),
]

_ACTION_ITEMS = [
    ("Open Pull Request", "Create a new pull request to propose merging your branch into another branch.", None),
    ("Approve", "Mark a pull request as reviewed and ready to merge.", COLORS["accent"]),
    ("Merge", "Combine the pull request's changes into the target branch.", _GREEN),
    ("Close", "Close the pull request without merging the changes.", COLORS["text_muted"]),
    ("Has conflicts", "The branches have overlapping changes that need to be resolved before merging.", COLORS["danger"]),
    ("No conflicts", "The branches can be merged cleanly without any issues.", _GREEN),
]


class PRHelpDialog(QDialog):

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowFlags(Qt.Dialog | Qt.FramelessWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setFixedSize(460, 480)
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

        # ── Title bar ─────────────────────────────────────────────────
        title_bar = QWidget()
        title_bar.setStyleSheet("background: transparent;")
        tb = QHBoxLayout(title_bar)
        tb.setContentsMargins(24, 18, 18, 10)

        title = QLabel("Pull Requests Guide")
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

        for key, label in [("overview", "Overview"), ("actions", "Actions")]:
            btn = QPushButton(label)
            btn.setCursor(Qt.PointingHandCursor)
            btn.setFixedHeight(30)
            btn.setCheckable(True)
            btn.setChecked(key == "overview")
            btn.setStyleSheet(self._tab_style(key == "overview"))
            btn.clicked.connect(lambda _, k=key: self._switch_tab(k))
            tl.addWidget(btn)
            self._tab_btns[key] = btn

        tl.addStretch()
        outer.addWidget(tab_row)

        # ── Stacked pages ─────────────────────────────────────────────
        self._stack = QStackedWidget()
        self._stack.setStyleSheet("background: transparent;")
        self._stack.addWidget(self._build_overview_page())
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
        idx = 0 if key == "overview" else 1
        self._stack.setCurrentIndex(idx)
        for k, btn in self._tab_btns.items():
            btn.setChecked(k == key)
            btn.setStyleSheet(self._tab_style(k == key))

    # ── Page builders ─────────────────────────────────────────────────

    def _build_overview_page(self) -> QScrollArea:
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.NoFrame)
        scroll.setStyleSheet(f"QScrollArea {{ background: transparent; border: none; }} {scrollbar_style()}")

        body = QWidget()
        body.setStyleSheet("background: transparent;")
        vl = QVBoxLayout(body)
        vl.setContentsMargins(24, 12, 24, 24)
        vl.setSpacing(10)

        for name, desc, dot_color in _OVERVIEW_ITEMS:
            vl.addWidget(self._overview_row(name, desc, dot_color))

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

        for name, desc, color in _ACTION_ITEMS:
            vl.addWidget(self._action_row(name, desc, color))

        vl.addStretch()
        scroll.setWidget(body)
        return scroll

    # ── Row builders ──────────────────────────────────────────────────

    @staticmethod
    def _overview_row(name: str, desc: str, dot_color: str | None) -> QWidget:
        row = QWidget()
        row.setStyleSheet("background: transparent;")
        vl = QVBoxLayout(row)
        vl.setContentsMargins(0, 0, 0, 0)
        vl.setSpacing(3)

        header = QHBoxLayout()
        header.setSpacing(8)

        if dot_color:
            dot = QLabel("●")
            dot.setStyleSheet(f"background: transparent; font-size: 10px; color: {dot_color};")
            dot.setFixedWidth(14)
            header.addWidget(dot)

        name_lbl = QLabel(name)
        name_lbl.setStyleSheet(
            f"background: transparent; font-size: 13px; font-weight: 600;"
            f" color: {COLORS['text_primary']};"
        )
        header.addWidget(name_lbl)
        header.addStretch()
        vl.addLayout(header)

        desc_lbl = QLabel(desc)
        desc_lbl.setStyleSheet(
            f"background: transparent; font-size: 11px; color: {COLORS['text_muted']};"
        )
        desc_lbl.setWordWrap(True)
        if dot_color:
            desc_lbl.setContentsMargins(22, 0, 0, 0)
        vl.addWidget(desc_lbl)

        return row

    @staticmethod
    def _action_row(name: str, desc: str, color: str | None) -> QWidget:
        row = QWidget()
        row.setStyleSheet("background: transparent;")
        hl = QHBoxLayout(row)
        hl.setContentsMargins(0, 4, 0, 4)
        hl.setSpacing(10)

        name_color = color or COLORS["text_primary"]
        badge = QLabel(name)
        badge.setStyleSheet(
            f"background: transparent; font-size: 12px; font-weight: 600;"
            f" color: {name_color};"
        )
        badge.setFixedWidth(130)
        hl.addWidget(badge, 0, Qt.AlignTop)

        desc_lbl = QLabel(desc)
        desc_lbl.setStyleSheet(
            f"background: transparent; font-size: 11px; color: {COLORS['text_muted']};"
        )
        desc_lbl.setWordWrap(True)
        hl.addWidget(desc_lbl, 1)

        return row

"""Self-contained widget classes used by CommitViewPage.

These are small, presentation-only QWidget subclasses that depend on nothing
from CommitViewPage (only Qt, the theme COLORS, the canvas ORIENT_* constants,
and the shared _VScrollArea). Extracted from ui/commit_view.py to keep that
module focused on page orchestration. No behavior change.
"""
from __future__ import annotations

from PyQt5.QtCore import (
    Qt, QRect, QTimer, QPropertyAnimation, QEasingCurve, pyqtSignal,
)
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QFrame, QLineEdit, QCheckBox, QSizePolicy,
)

from styles.theme import COLORS
from ui.canvas import ORIENT_TB, ORIENT_BT, ORIENT_LR, ORIENT_RL
from ui.panels import _VScrollArea


# ── Filter panel ──────────────────────────────────────────────────────────────
class _FilterPanel(QWidget):
    filter_changed = pyqtSignal()

    PANEL_W = 220
    _CB_STYLE = f"""
        QCheckBox {{
            background: transparent; font-size: 12px;
            color: {COLORS['text_primary']}; spacing: 6px;
        }}
        QCheckBox::indicator {{
            width: 14px; height: 14px;
            border: 1px solid {COLORS['border']};
            border-radius: 3px; background: transparent;
        }}
        QCheckBox::indicator:checked {{
            background: {COLORS['accent']}; border-color: {COLORS['accent']};
        }}
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedWidth(self.PANEL_W)
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setObjectName("filterPanel")
        self.setStyleSheet(f"""
            #filterPanel {{
                background: {COLORS['bg_card']};
                border: 1px solid {COLORS['border']};
                border-radius: 10px;
            }}
        """)
        self.hide()

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        hdr = QWidget()
        hdr.setObjectName("fpHdr")
        hdr.setFixedHeight(38)
        hdr.setStyleSheet(f"""
            #fpHdr {{
                background: {COLORS['bg_secondary']};
                border-bottom: 1px solid {COLORS['border']};
                border-radius: 10px 10px 0 0;
            }}
        """)
        hl = QHBoxLayout(hdr)
        hl.setContentsMargins(14, 0, 8, 0)
        title_lbl = QLabel("Filters")
        title_lbl.setStyleSheet(
            f"background: transparent; font-size: 12px; font-weight: 600; font-family: 'Tilt Warp';"
            f" color: {COLORS['text_muted']};"
        )
        hl.addWidget(title_lbl)
        hl.addStretch()
        reset_btn = QPushButton("Reset")
        reset_btn.setCursor(Qt.PointingHandCursor)
        reset_btn.setStyleSheet(f"""
            QPushButton {{ background: transparent; border: none;
                font-size: 11px; color: {COLORS['accent']}; }}
            QPushButton:hover {{ color: {COLORS['text_primary']}; }}
        """)
        reset_btn.clicked.connect(self._reset)
        hl.addWidget(reset_btn)
        root.addWidget(hdr)

        _scroll_style = f"""
            QScrollArea {{ background: transparent; border: none; }}
            QScrollBar:vertical {{
                background: transparent; width: 4px; margin: 0;
            }}
            QScrollBar::handle:vertical {{
                background: {COLORS['border']}; border-radius: 2px; min-height: 20px;
            }}
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
        """

        body = QVBoxLayout()
        body.setContentsMargins(12, 8, 12, 12)
        body.setSpacing(4)

        bl = QLabel("BRANCHES")
        bl.setStyleSheet(
            f"background: transparent; font-size: 10px; font-weight: 700; font-family: 'Tilt Warp';"
            f" color: {COLORS['text_muted']}; letter-spacing: 0.06em;"
        )
        body.addWidget(bl)

        self._branch_container = QWidget()
        self._branch_container.setStyleSheet("background: transparent;")
        self._branch_layout = QVBoxLayout(self._branch_container)
        self._branch_layout.setContentsMargins(0, 0, 0, 0)
        self._branch_layout.setSpacing(2)

        branch_scroll = _VScrollArea()
        branch_scroll.setWidgetResizable(True)
        branch_scroll.setFrameShape(QFrame.NoFrame)
        branch_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        branch_scroll.setStyleSheet(_scroll_style)
        branch_scroll.setMaximumHeight(160)
        branch_scroll.setWidget(self._branch_container)
        branch_scroll.viewport().setStyleSheet("background: transparent;")
        body.addWidget(branch_scroll)

        div = QFrame()
        div.setFrameShape(QFrame.HLine)
        div.setStyleSheet(f"background: {COLORS['border']}; max-height: 1px; margin: 4px 0;")
        body.addWidget(div)

        al = QLabel("COLLABORATORS")
        al.setStyleSheet(
            f"background: transparent; font-size: 10px; font-weight: 700; font-family: 'Tilt Warp';"
            f" color: {COLORS['text_muted']}; letter-spacing: 0.06em;"
        )
        body.addWidget(al)

        self._collab_loading = QLabel("Loading…")
        self._collab_loading.setStyleSheet(
            f"background: transparent; font-size: 12px; color: {COLORS['text_muted']}; padding: 6px 0;"
        )
        body.addWidget(self._collab_loading)

        self._author_container = QWidget()
        self._author_container.setStyleSheet("background: transparent;")
        self._author_layout = QVBoxLayout(self._author_container)
        self._author_layout.setContentsMargins(0, 0, 0, 0)
        self._author_layout.setSpacing(2)

        author_scroll = _VScrollArea()
        author_scroll.setWidgetResizable(True)
        author_scroll.setFrameShape(QFrame.NoFrame)
        author_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        author_scroll.setStyleSheet(_scroll_style)
        author_scroll.setMaximumHeight(260)
        author_scroll.setWidget(self._author_container)
        author_scroll.viewport().setStyleSheet("background: transparent;")
        author_scroll.hide()
        self._author_scroll = author_scroll
        body.addWidget(author_scroll)

        body_widget = QWidget()
        body_widget.setStyleSheet("background: transparent;")
        body_widget.setLayout(body)
        root.addWidget(body_widget)

        self._branch_checks: dict[str, QCheckBox] = {}
        self._author_checks: dict[str, QCheckBox] = {}

    def _make_cb(self, name: str, layout: QVBoxLayout, store: dict):
        cb = QCheckBox(name)
        cb.setChecked(True)
        cb.setStyleSheet(self._CB_STYLE)
        cb.stateChanged.connect(lambda _: self.filter_changed.emit())
        layout.addWidget(cb)
        store[name] = cb

    def _clear_layout(self, layout: QVBoxLayout, store: dict):
        while layout.count():
            w = layout.takeAt(0).widget()
            if w:
                w.setParent(None)
        store.clear()

    def set_branches(self, names: list[str]):
        self._clear_layout(self._branch_layout, self._branch_checks)
        for n in names:
            self._make_cb(n, self._branch_layout, self._branch_checks)

    def set_authors(self, names: list[str]):
        self._clear_layout(self._author_layout, self._author_checks)
        for n in names:
            self._make_cb(n, self._author_layout, self._author_checks)
        self._collab_loading.hide()
        self._author_scroll.show()

    def show_collaborators_loading(self):
        self._clear_layout(self._author_layout, self._author_checks)
        self._author_scroll.hide()
        self._collab_loading.show()

    def active_branches(self) -> set[str]:
        return {n for n, cb in self._branch_checks.items() if cb.isChecked()}

    def active_authors(self) -> set[str]:
        return {n for n, cb in self._author_checks.items() if cb.isChecked()}

    def _all_branches(self) -> set[str]:
        return set(self._branch_checks.keys())

    def _all_authors(self) -> set[str]:
        return set(self._author_checks.keys())

    def _reset(self):
        for cb in list(self._branch_checks.values()) + list(self._author_checks.values()):
            cb.setChecked(True)


class _OrientBar(QWidget):
    orientation_changed = pyqtSignal(str)

    _BUTTONS = [
        (ORIENT_BT, "↓", "Top to bottom — oldest to newest"),
        (ORIENT_TB, "↑", "Bottom to top — newest to oldest"),
        (ORIENT_LR, "→", "Left to right — oldest to newest"),
        (ORIENT_RL, "←", "Right to left — newest to oldest"),
    ]
    _ACTIVE = f"""
        QPushButton {{
            background: {COLORS['accent']}; border: none; border-radius: 6px;
            color: white; font-size: 14px; font-weight: 600; font-family: 'Tilt Warp';
        }}
    """
    _INACTIVE = f"""
        QPushButton {{
            background: transparent; border: none; border-radius: 6px;
            color: {COLORS['text_muted']}; font-size: 14px;
        }}
        QPushButton:hover {{ color: {COLORS['text_primary']}; }}
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("orientBar")
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setStyleSheet(f"""
            #orientBar {{
                background: {COLORS['bg_card']};
                border: 1px solid {COLORS['border']};
                border-radius: 8px;
            }}
        """)
        self.setFixedHeight(34)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(4, 0, 4, 0)
        layout.setSpacing(0)

        self._btns: dict[str, QPushButton] = {}
        for orient, icon, tip in self._BUTTONS:
            btn = QPushButton(icon)
            btn.setFixedSize(34, 34)
            btn.setCursor(Qt.PointingHandCursor)
            btn.setToolTip(tip)
            btn.clicked.connect(lambda _, o=orient: self.orientation_changed.emit(o))
            layout.addWidget(btn)
            self._btns[orient] = btn

        self._set_active(ORIENT_LR)

    def set_orientation(self, orient: str):
        self._set_active(orient)

    def _set_active(self, orient: str):
        for o, btn in self._btns.items():
            btn.setStyleSheet(self._ACTIVE if o == orient else self._INACTIVE)


class _TabBar(QWidget):
    tab_changed = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet("background: transparent;")
        self._active = "schema"
        self._buttons: dict[str, QPushButton] = {}

        hl = QHBoxLayout(self)
        hl.setContentsMargins(16, 0, 16, 0)
        hl.setSpacing(0)
        for key, label in [("schema", "Schema"), ("settings", "Settings"), ("collaboration", "Collaboration")]:
            btn = QPushButton(label)
            btn.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Expanding)
            btn.setCursor(Qt.PointingHandCursor)
            btn.setCheckable(True)
            btn.setChecked(key == "schema")
            btn.setStyleSheet(self._btn_style(key == "schema"))
            btn.clicked.connect(lambda _, k=key: self._select(k))
            hl.addWidget(btn)
            self._buttons[key] = btn
        hl.addStretch()

        self._indicator = QWidget(self)
        self._indicator.setFixedHeight(2)
        self._indicator.setStyleSheet(f"background: {COLORS['accent']};")
        self._ind_anim = QPropertyAnimation(self._indicator, b"geometry")
        self._ind_anim.setDuration(200)
        self._ind_anim.setEasingCurve(QEasingCurve.OutCubic)
        QTimer.singleShot(0, self._place_indicator)

    def _btn_style(self, active: bool) -> str:
        color  = COLORS["text_primary"] if active else COLORS["text_muted"]
        weight = "600" if active else "400"
        return (f"QPushButton {{ background: transparent; border: none;"
                f" font-size: 13px; font-weight: {weight}; color: {color};"
                f" padding: 0 20px; }}"
                f"QPushButton:hover {{ color: {COLORS['text_primary']}; }}")

    def _select(self, key: str):
        if key == self._active:
            return
        self._active = key
        for k, btn in self._buttons.items():
            btn.setChecked(k == key)
            btn.setStyleSheet(self._btn_style(k == key))
        self._place_indicator(animate=True)
        self.tab_changed.emit(key)

    def _place_indicator(self, animate: bool = False):
        btn = self._buttons.get(self._active)
        if not btn:
            return
        g = btn.geometry()
        target = QRect(g.x(), self.height() - 2, g.width(), 2)
        if animate:
            self._ind_anim.stop()
            self._ind_anim.setStartValue(self._indicator.geometry())
            self._ind_anim.setEndValue(target)
            self._ind_anim.start()
        else:
            self._indicator.setGeometry(target)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._place_indicator()

    def select(self, key: str):
        self._select(key)

    def set_viewer_mode(self, is_viewer: bool):
        for key, btn in self._buttons.items():
            if key != "schema":
                btn.setVisible(not is_viewer)
        if is_viewer and self._active != "schema":
            self._select("schema")


class _CreateRemoteDialog(QWidget):
    """Overlay dialog shown when a repo has no remote or its remote was deleted."""
    create_requested = pyqtSignal(str, bool)   # name, is_private
    cancelled        = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setStyleSheet(f"background: {COLORS['bg_primary']};")
        self.setAttribute(Qt.WA_TransparentForMouseEvents, False)

        outer = QVBoxLayout(self)
        outer.setAlignment(Qt.AlignCenter)
        outer.setContentsMargins(0, 0, 0, 0)

        card = QWidget()
        card.setFixedWidth(420)
        card.setObjectName("createRemoteCard")
        card.setAttribute(Qt.WA_StyledBackground, True)
        card.setStyleSheet(f"""
            QWidget#createRemoteCard {{
                background: {COLORS['bg_secondary']};
                border: 1px solid {COLORS['border']};
                border-radius: 12px;
            }}
        """)
        outer.addWidget(card)

        inner = QVBoxLayout(card)
        inner.setContentsMargins(28, 28, 28, 24)
        inner.setSpacing(12)

        self._title_lbl = QLabel()
        self._title_lbl.setStyleSheet(
            f"background: transparent; border: none; font-size: 15px; font-weight: 700;"
            f" font-family: 'Tilt Warp'; color: {COLORS['text_primary']};"
        )
        self._title_lbl.setWordWrap(True)
        inner.addWidget(self._title_lbl)

        self._subtitle_lbl = QLabel()
        self._subtitle_lbl.setStyleSheet(
            f"background: transparent; border: none; font-size: 13px;"
            f" color: {COLORS['text_secondary']};"
        )
        self._subtitle_lbl.setWordWrap(True)
        inner.addWidget(self._subtitle_lbl)

        inner.addSpacing(4)

        name_lbl = QLabel("Repository name")
        name_lbl.setStyleSheet(
            f"background: transparent; border: none; font-size: 12px;"
            f" font-weight: 600; color: {COLORS['text_muted']};"
        )
        inner.addWidget(name_lbl)

        self._name_edit = QLineEdit()
        self._name_edit.setFixedHeight(34)
        self._name_edit.setStyleSheet(f"""
            QLineEdit {{
                background: {COLORS['bg_primary']}; border: 1px solid {COLORS['border']};
                border-radius: 6px; color: {COLORS['text_primary']};
                font-size: 13px; padding: 0 10px;
            }}
            QLineEdit:focus {{ border-color: {COLORS['accent']}; }}
        """)
        inner.addWidget(self._name_edit)

        toggle_row = QHBoxLayout()
        toggle_row.setSpacing(8)

        self._pub_btn  = QPushButton("Public")
        self._priv_btn = QPushButton("Private")
        for btn in (self._pub_btn, self._priv_btn):
            btn.setFixedHeight(30)
            btn.setCheckable(True)
            btn.setCursor(Qt.PointingHandCursor)
        self._pub_btn.setChecked(False)
        self._priv_btn.setChecked(True)
        self._pub_btn.clicked.connect(lambda: self._set_privacy(False))
        self._priv_btn.clicked.connect(lambda: self._set_privacy(True))
        self._apply_toggle_style()
        toggle_row.addWidget(self._pub_btn)
        toggle_row.addWidget(self._priv_btn)
        toggle_row.addStretch()
        inner.addLayout(toggle_row)

        self._status_lbl = QLabel("")
        self._status_lbl.setStyleSheet(
            f"background: transparent; border: none; font-size: 12px; color: #ef4444;"
        )
        self._status_lbl.setWordWrap(True)
        self._status_lbl.hide()
        inner.addWidget(self._status_lbl)

        btn_row = QHBoxLayout()
        btn_row.setSpacing(8)

        self._cancel_btn = QPushButton("Cancel")
        self._cancel_btn.setFixedHeight(34)
        self._cancel_btn.setCursor(Qt.PointingHandCursor)
        self._cancel_btn.setStyleSheet(f"""
            QPushButton {{
                background: transparent; border: 1px solid {COLORS['border']};
                border-radius: 6px; color: {COLORS['text_muted']};
                font-size: 13px; padding: 0 16px;
            }}
            QPushButton:hover {{ border-color: {COLORS['text_muted']}; color: {COLORS['text_primary']}; }}
        """)
        self._cancel_btn.clicked.connect(self.cancelled)

        self._create_btn = QPushButton("Create Repository")
        self._create_btn.setFixedHeight(34)
        self._create_btn.setCursor(Qt.PointingHandCursor)
        self._create_btn.setStyleSheet(f"""
            QPushButton {{
                background: {COLORS['accent']}; border: none;
                border-radius: 6px; color: #fff;
                font-size: 13px; font-weight: 600; font-family: 'Tilt Warp'; padding: 0 16px;
            }}
            QPushButton:hover {{ background: {COLORS['accent_hover']}; }}
            QPushButton:disabled {{ background: {COLORS['border']}; color: {COLORS['text_muted']}; }}
        """)
        self._create_btn.clicked.connect(self._on_create_clicked)

        btn_row.addWidget(self._cancel_btn)
        btn_row.addStretch()
        btn_row.addWidget(self._create_btn)
        inner.addLayout(btn_row)

        self._is_private = True

    def setup(self, title: str, subtitle: str, repo_name: str):
        self._title_lbl.setText(title)
        self._subtitle_lbl.setText(subtitle)
        self._name_edit.setText(repo_name)
        self._status_lbl.hide()
        self._status_lbl.setText("")
        self._create_btn.setEnabled(True)
        self._create_btn.setText("Create Repository")
        self._set_privacy(True)

    def _set_privacy(self, is_private: bool):
        self._is_private = is_private
        self._pub_btn.setChecked(not is_private)
        self._priv_btn.setChecked(is_private)
        self._apply_toggle_style()

    def _apply_toggle_style(self):
        active   = f"background: {COLORS['accent']}; border: none; border-radius: 6px; color: #fff; font-size: 12px; font-weight: 600; font-family: 'Tilt Warp';"
        inactive = f"background: transparent; border: 1px solid {COLORS['border']}; border-radius: 6px; color: {COLORS['text_muted']}; font-size: 12px;"
        self._priv_btn.setStyleSheet(f"QPushButton {{ {active if self._is_private else inactive} }}")
        self._pub_btn.setStyleSheet(f"QPushButton {{ {inactive if self._is_private else active} }}")

    def _on_create_clicked(self):
        name = self._name_edit.text().strip()
        if not name:
            self._show_status("Please enter a repository name.")
            return
        self.create_requested.emit(name, self._is_private)

    def set_creating(self, active: bool):
        self._create_btn.setEnabled(not active)
        self._create_btn.setText("Creating…" if active else "Create Repository")
        self._cancel_btn.setEnabled(not active)
        if active:
            self._status_lbl.hide()

    def set_error(self, msg: str):
        self._create_btn.setEnabled(True)
        self._create_btn.setText("Create Repository")
        self._cancel_btn.setEnabled(True)
        self._show_status(msg)

    def _show_status(self, msg: str):
        self._status_lbl.setText(msg)
        self._status_lbl.show()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if self.parent():
            self.setGeometry(self.parent().rect())

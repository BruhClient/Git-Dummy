"""Slide-in panel showing a single file's diff."""
from __future__ import annotations

import qtawesome as qta

from PyQt5.QtCore import Qt, QSize, QPropertyAnimation, QEasingCurve, QRect, QPoint, pyqtSignal
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QFrame,
)

from styles.theme import COLORS
from .diff_renderer import (
    _VScrollArea, _trunc, _scrollbar_style, _close_btn_style,
    _STATUS_COLOR, _STATUS_LABEL,
    _compute_hunks, _chunk_lines, _filter_unchanged, _DiffLine,
    PANEL_W, CHANGES_W, SWIPE_THRESHOLD,
)


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
            f"background: transparent; font-size: 13px; font-weight: 600; font-family: 'Tilt Warp';"
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

        self._source_badge = QLabel("")
        self._source_badge.setFixedHeight(20)
        self._source_badge.setAlignment(Qt.AlignCenter)
        self._source_badge.hide()
        hl.addWidget(self._source_badge)

        close_btn = QPushButton()
        close_btn.setIcon(qta.icon("fa5s.times", color=COLORS["text_muted"]))
        close_btn.setIconSize(QSize(12, 12))
        close_btn.setFixedSize(40, 40)
        close_btn.setCursor(Qt.PointingHandCursor)
        close_btn.setStyleSheet(_close_btn_style(COLORS))
        close_btn.clicked.connect(self.hide_panel)
        hl.addWidget(close_btn)
        root.addWidget(hdr)

        scroll = _VScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setStyleSheet(_scrollbar_style(COLORS))

        self._content = QWidget()
        self._content.setStyleSheet("background: transparent;")
        self._content_layout = QVBoxLayout(self._content)
        self._content_layout.setContentsMargins(0, 8, 0, 8)
        self._content_layout.setSpacing(0)

        scroll.setWidget(self._content)
        scroll.viewport().setStyleSheet("background: transparent;")
        root.addWidget(scroll)

    def show_file(self, info: dict, source: str = "change"):
        self._current_path = info["path"]
        self._title.setText(_trunc(info["name"], 30))
        self._title.setToolTip(info["name"])

        is_stash = source == "stash"
        badge_text  = "UNSAVED" if is_stash else "CHANGE"
        badge_color = COLORS["warning"] if is_stash else COLORS["accent"]
        badge_bg    = "rgba(214,158,46,0.12)" if is_stash else COLORS["accent_dim"]
        self._source_badge.setText(badge_text)
        self._source_badge.setStyleSheet(
            f"background: {badge_bg}; color: {badge_color};"
            f" font-size: 9px; font-weight: 700; font-family: 'Tilt Warp'; letter-spacing: 0.08em;"
            f" border-radius: 4px; padding: 0 7px;"
        )
        self._source_badge.show()

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
            f"background: transparent; font-size: 10px; font-weight: 700; font-family: 'Tilt Warp';"
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
        from PyQt5.QtCore import QRect
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

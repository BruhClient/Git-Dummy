"""Full-screen overlay showing every file's before/after changes."""
from __future__ import annotations

from PyQt5.QtCore import Qt
from PyQt5.QtGui import QPainter, QColor
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QFrame,
)

from styles.theme import COLORS
from .diff_renderer import (
    _VScrollArea, _trunc, _scrollbar_style, _close_btn_style,
    _STATUS_COLOR, _MiniBar, _DiffLine,
    _compute_hunks, _chunk_lines,
)


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
        scroll = _VScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
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

        name = QLabel(_trunc(info["name"], 36))
        name.setToolTip(info["name"])
        name.setStyleSheet(
            f"background: transparent; font-size: 13px; font-weight: 600;"
            f" color: {COLORS['text_primary']};"
        )
        fhl.addWidget(name)

        if "/" in info["path"]:
            path_parts = "/".join(info["path"].split("/")[:-1])
            path_lbl = QLabel("  " + _trunc(path_parts, 32))
            path_lbl.setToolTip(path_parts)
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

from __future__ import annotations

from PyQt5.QtCore import Qt, pyqtSignal, QRectF
from PyQt5.QtGui import QColor, QPainter, QPen, QBrush, QFont, QPainterPath
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QFrame,
)

from styles.theme import COLORS, THEMES, CURRENT_MODE, apply_theme, apply_mode
from core import settings_store


# ── Mode card ─────────────────────────────────────────────────────────────────

# Fixed palettes so each card always shows its own colours regardless of
# which mode is currently active.
_MODE_PALETTE = {
    "dark": {
        "bg":     "#1c1c1c",
        "bar":    "#111111",
        "line":   "#2a2a2a",
        "border": "#2e2e2e",
    },
    "light": {
        "bg":     "#ffffff",
        "bar":    "#f4f6f8",
        "line":   "#e2e8f0",
        "border": "#e2e8f0",
    },
}


class _ModeCard(QWidget):
    clicked = pyqtSignal(str)  # "dark" or "light"

    def __init__(self, mode: str, label: str, parent=None):
        super().__init__(parent)
        self._mode = mode
        self._label = label
        self._selected = False
        self.setFixedSize(130, 104)
        self.setCursor(Qt.PointingHandCursor)

    def set_selected(self, selected: bool):
        self._selected = selected
        self.update()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)

        pal = _MODE_PALETTE[self._mode]
        card_h = 80
        r = 8

        # Card border (accent when selected)
        border_color = COLORS["accent"] if self._selected else pal["border"]
        border_w = 2 if self._selected else 1
        p.setPen(QPen(QColor(border_color), border_w))
        p.setBrush(QBrush(QColor(pal["bg"])))
        p.drawRoundedRect(1, 1, self.width() - 2, card_h - 2, r, r)

        # Top bar
        bar_path = QPainterPath()
        bar_path.moveTo(1, 14)
        bar_path.lineTo(1, r + 1)
        bar_path.quadTo(1, 1, r + 1, 1)
        bar_path.lineTo(self.width() - r - 1, 1)
        bar_path.quadTo(self.width() - 1, 1, self.width() - 1, r + 1)
        bar_path.lineTo(self.width() - 1, 14)
        bar_path.closeSubpath()
        p.setPen(Qt.NoPen)
        p.setBrush(QBrush(QColor(pal["bar"])))
        p.drawPath(bar_path)

        # Accent dot in top bar
        p.setBrush(QBrush(QColor(COLORS["accent"])))
        p.drawEllipse(self.width() - 16, 5, 8, 8)

        # Content lines
        p.setBrush(QBrush(QColor(pal["line"])))
        widths = [52, 36, 44]
        for i, w in enumerate(widths):
            p.drawRoundedRect(10, 22 + i * 16, w, 7, 3, 3)

        # Label below card
        text_color = COLORS["accent"] if self._selected else COLORS["text_secondary"]
        weight = QFont.DemiBold if self._selected else QFont.Normal
        p.setPen(QPen(QColor(text_color)))
        p.setFont(QFont("Inter", 11, weight))
        p.drawText(
            0, card_h + 6, self.width(), 18,
            Qt.AlignHCenter | Qt.AlignTop,
            self._label,
        )
        p.end()

    def mousePressEvent(self, _):
        self.clicked.emit(self._mode)


# ── Theme swatch ──────────────────────────────────────────────────────────────

class _ThemeSwatch(QWidget):
    clicked = pyqtSignal(str)

    def __init__(self, key: str, label: str, accent: str, parent=None):
        super().__init__(parent)
        self._key = key
        self._label = label
        self._accent = accent
        self._selected = False
        self.setFixedSize(88, 100)
        self.setCursor(Qt.PointingHandCursor)

    def set_selected(self, selected: bool):
        self._selected = selected
        self.update()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)

        cw = 56
        cx = (self.width() - cw) // 2
        cy = 6

        if self._selected:
            p.setPen(QPen(QColor(self._accent), 2.5))
            p.setBrush(Qt.NoBrush)
            p.drawEllipse(cx - 5, cy - 5, cw + 10, cw + 10)

        p.setPen(Qt.NoPen)
        p.setBrush(QBrush(QColor(COLORS["bg_card"])))
        p.drawEllipse(cx, cy, cw, cw)

        # Accent fills the bottom half of the circle
        clip = QPainterPath()
        clip.addEllipse(QRectF(cx, cy, cw, cw))
        p.setClipPath(clip)
        p.setBrush(QBrush(QColor(self._accent)))
        p.drawRect(cx, cy + cw // 2, cw, cw // 2)

        p.setClipping(False)
        p.setPen(QPen(QColor(COLORS["border"]), 1))
        p.setBrush(Qt.NoBrush)
        p.drawEllipse(cx, cy, cw, cw)

        text_color = self._accent if self._selected else COLORS["text_secondary"]
        p.setPen(QPen(QColor(text_color)))
        weight = QFont.DemiBold if self._selected else QFont.Normal
        p.setFont(QFont("Inter", 11, weight))
        p.drawText(
            0, cy + cw + 10, self.width(), 20,
            Qt.AlignHCenter | Qt.AlignTop,
            self._label,
        )
        p.end()

    def mousePressEvent(self, _):
        self.clicked.emit(self._key)


# ── Settings page ─────────────────────────────────────────────────────────────

class SettingsPage(QWidget):
    theme_changed = pyqtSignal(str)
    mode_changed  = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._swatches:    dict[str, _ThemeSwatch] = {}
        self._mode_cards:  dict[str, _ModeCard]    = {}
        self._build_ui()
        self._select_mode(settings_store.get("mode", "dark"))
        self._select_theme(settings_store.get("theme", "forest"))

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(56, 48, 56, 48)
        root.setSpacing(0)

        title = QLabel("Settings")
        title.setStyleSheet(
            f"font-size: 26px; font-weight: 700; color: {COLORS['text_primary']};"
        )
        root.addWidget(title)

        root.addSpacing(4)

        sub = QLabel("Customise Git Dummy to your liking.")
        sub.setStyleSheet(f"font-size: 14px; color: {COLORS['text_secondary']};")
        root.addWidget(sub)

        root.addSpacing(40)

        self._add_section_header(root, "Appearance")
        root.addSpacing(20)

        # ── Mode ──────────────────────────────────────────────────────────────
        mode_title = QLabel("Interface mode")
        mode_title.setStyleSheet(
            f"font-size: 15px; font-weight: 600; color: {COLORS['text_primary']};"
        )
        root.addWidget(mode_title)

        root.addSpacing(4)

        mode_desc = QLabel("Toggle between dark and light interface.")
        mode_desc.setStyleSheet(f"font-size: 13px; color: {COLORS['text_secondary']};")
        root.addWidget(mode_desc)

        root.addSpacing(16)

        mode_row = QHBoxLayout()
        mode_row.setSpacing(12)
        mode_row.setAlignment(Qt.AlignLeft)

        for mode, label in (("dark", "Dark"), ("light", "Light")):
            card = _ModeCard(mode, label)
            card.clicked.connect(self._on_mode_clicked)
            mode_row.addWidget(card)
            self._mode_cards[mode] = card

        root.addLayout(mode_row)

        root.addSpacing(28)

        # ── Theme ─────────────────────────────────────────────────────────────
        theme_title = QLabel("Accent theme")
        theme_title.setStyleSheet(
            f"font-size: 15px; font-weight: 600; color: {COLORS['text_primary']};"
        )
        root.addWidget(theme_title)

        root.addSpacing(4)

        theme_desc = QLabel("Sets the accent colour used across the interface and commit graph.")
        theme_desc.setStyleSheet(f"font-size: 13px; color: {COLORS['text_secondary']};")
        root.addWidget(theme_desc)

        root.addSpacing(16)

        swatch_row = QHBoxLayout()
        swatch_row.setSpacing(8)
        swatch_row.setAlignment(Qt.AlignLeft)

        for key, preset in THEMES.items():
            swatch = _ThemeSwatch(key, preset["label"], preset["accent"])
            swatch.clicked.connect(self._on_theme_clicked)
            swatch_row.addWidget(swatch)
            self._swatches[key] = swatch

        root.addLayout(swatch_row)
        root.addStretch()

    def _add_section_header(self, layout: QVBoxLayout, text: str):
        label = QLabel(text.upper())
        label.setStyleSheet(
            f"font-size: 11px; font-weight: 600; color: {COLORS['text_muted']}; "
            f"letter-spacing: 1px;"
        )
        layout.addWidget(label)
        layout.addSpacing(4)
        divider = QFrame()
        divider.setFixedHeight(1)
        divider.setStyleSheet(f"background: {COLORS['border']};")
        layout.addWidget(divider)

    def _on_mode_clicked(self, mode: str):
        apply_mode(mode)
        settings_store.save({"mode": mode})
        self._select_mode(mode)
        self.mode_changed.emit(mode)

    def _on_theme_clicked(self, key: str):
        apply_theme(key)
        settings_store.save({"theme": key})
        self._select_theme(key)
        self.theme_changed.emit(key)

    def _select_mode(self, mode: str):
        for k, card in self._mode_cards.items():
            card.set_selected(k == mode)

    def _select_theme(self, key: str):
        for k, swatch in self._swatches.items():
            swatch.set_selected(k == key)

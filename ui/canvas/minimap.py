"""Bird's-eye minimap widget for the commit graph canvas."""
from __future__ import annotations

from PyQt5.QtCore import Qt, QRectF, QPointF
from PyQt5.QtGui import QPainter, QColor, QPen, QBrush
from PyQt5.QtWidgets import QWidget

from styles.theme import COLORS


class MiniMap(QWidget):
    """
    Bird's-eye view of the commit graph.
    White box = current viewport. Click/drag to pan the canvas.
    """

    MAP_W    = 150
    MAP_H    = 160
    _PAD     = 10   # inner margin so dots aren't clipped at edges

    def __init__(self, canvas, parent=None):
        super().__init__(parent)
        self._canvas = canvas
        self._dot_color_cache: dict[str, QColor] = {}
        self.setFixedSize(self.MAP_W, self.MAP_H)
        self.setCursor(Qt.PointingHandCursor)
        canvas.viewport_changed.connect(self.update)

    def _dot_color(self, hex_str: str) -> QColor:
        color = self._dot_color_cache.get(hex_str)
        if color is None:
            color = QColor(hex_str)
            color.setAlpha(200)
            self._dot_color_cache[hex_str] = color
        return color

    # ── coordinate helpers ────────────────────────────────────────────────

    def _to_map(self, sx: float, sy: float) -> tuple[float, float]:
        r  = self._canvas._content_rect
        uw = self.MAP_W - 2 * self._PAD
        uh = self.MAP_H - 2 * self._PAD
        mx = self._PAD + (sx - r.x()) / max(r.width(),  1) * uw
        my = self._PAD + (sy - r.y()) / max(r.height(), 1) * uh
        return mx, my

    def _from_map(self, mx: float, my: float) -> tuple[float, float]:
        r  = self._canvas._content_rect
        uw = self.MAP_W - 2 * self._PAD
        uh = self.MAP_H - 2 * self._PAD
        sx = r.x() + (mx - self._PAD) / max(uw, 1) * r.width()
        sy = r.y() + (my - self._PAD) / max(uh, 1) * r.height()
        return sx, sy

    # ── paint ─────────────────────────────────────────────────────────────

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)

        bg = QColor(COLORS["bg_card"])
        bg.setAlpha(230)
        p.setBrush(QBrush(bg))
        p.setPen(QPen(QColor(COLORS["border"]), 1))
        p.drawRoundedRect(0, 0, self.MAP_W, self.MAP_H, 8, 8)

        canvas = self._canvas
        if not canvas._positions or not canvas._content_rect.isValid():
            p.end()
            return

        p.setPen(Qt.NoPen)
        dimmed = getattr(canvas, "_dimmed_shas", set())
        for sha, (sx, sy) in canvas._positions.items():
            if sha in dimmed:
                continue
            mx, my = self._to_map(sx, sy)
            color = self._dot_color(canvas._node_colors.get(sha, COLORS["accent"]))
            p.setBrush(QBrush(color))
            p.drawEllipse(QPointF(mx, my), 2.5, 2.5)

        vr = canvas.mapToScene(canvas.viewport().rect()).boundingRect()
        x1, y1 = self._to_map(vr.left(),  vr.top())
        x2, y2 = self._to_map(vr.right(), vr.bottom())
        box = QRectF(x1, y1, x2 - x1, y2 - y1).intersected(
            QRectF(1, 1, self.MAP_W - 2, self.MAP_H - 2)
        )
        fill = QColor("white")
        fill.setAlpha(18)
        p.setBrush(QBrush(fill))
        p.setPen(QPen(QColor("white"), 1))
        p.drawRect(box)

        p.end()

    # ── interaction ───────────────────────────────────────────────────────

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._navigate(event.pos())

    def mouseMoveEvent(self, event):
        if event.buttons() & Qt.LeftButton:
            self._navigate(event.pos())

    def _navigate(self, pos):
        sx, sy = self._from_map(pos.x(), pos.y())
        self._canvas.centerOn(sx, sy)
        self.update()

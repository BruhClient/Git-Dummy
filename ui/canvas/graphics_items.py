"""QGraphicsItem subclasses for the commit graph canvas."""
from __future__ import annotations

from typing import Optional

from PyQt5.QtCore import Qt, QRectF, QPointF, pyqtSignal
from PyQt5.QtGui import (
    QPainter, QColor, QPen, QBrush, QFont, QFontMetrics,
    QPainterPath, QPolygonF, QPixmap,
)
from PyQt5.QtWidgets import (
    QGraphicsObject, QGraphicsPathItem, QGraphicsItem,
)

from styles.theme import COLORS
from core.git_tracker import CommitInfo
from .constants import NODE_R, START_R, BADGE_R, ORIENT_LR, ORIENT_RL


class BranchLabel(QGraphicsItem):
    """
    Pill badge showing a branch name.
    Placed to the right of the branch-tip commit node.
    Origin = left-centre of the pill.
    """

    def __init__(self, name: str, color: str):
        super().__init__()
        self._full = name
        self._name = name if len(name) <= 22 else name[:19] + "…"
        self._color = QColor(color)

        self._font = QFont("Urbanist", 10)
        self._font.setWeight(QFont.Medium)
        fm = QFontMetrics(self._font)

        px, py = 10, 4
        self._tw = fm.horizontalAdvance(self._name)
        self._w  = self._tw + px * 2
        self._h  = fm.height() + py * 2
        self._px = px

        self.setToolTip(self._full)
        self.setAcceptedMouseButtons(Qt.NoButton)
        self.setZValue(3)

    @property
    def pill_height(self) -> float:
        return self._h

    def boundingRect(self) -> QRectF:
        return QRectF(0, -self._h / 2, self._w, self._h)

    def paint(self, painter: QPainter, _option, _widget):
        painter.setRenderHint(QPainter.Antialiasing)
        r = self._h / 2

        bg = QColor(self._color)
        bg.setAlpha(28)
        border = QColor(self._color)
        border.setAlpha(160)

        painter.setBrush(QBrush(bg))
        painter.setPen(QPen(border, 1))
        painter.drawRoundedRect(
            QRectF(0, -self._h / 2, self._w, self._h), r, r,
        )

        painter.setPen(QPen(QColor(self._color)))
        painter.setFont(self._font)
        painter.drawText(
            QRectF(self._px, -self._h / 2, self._tw, self._h),
            Qt.AlignCenter,
            self._name,
        )


class CommitNode(QGraphicsObject):
    """Coloured circle representing a single commit."""

    clicked = pyqtSignal(object)   # CommitInfo

    def __init__(self, commit: CommitInfo, color: str, is_start: bool = False,
                 is_local_only: bool = False, is_head: bool = False,
                 has_stash: bool = False,
                 is_local_tip: bool = False, is_remote_tip: bool = False,
                 is_action_head: bool = False):
        super().__init__()
        self._commit          = commit
        self._color           = QColor(color)
        self._is_start        = is_start
        self._is_local_only   = is_local_only
        self._is_head         = is_head
        self._has_stash       = has_stash
        self._is_local_tip    = is_local_tip
        self._is_remote_tip   = is_remote_tip
        self._is_action_head  = is_action_head
        self._r             = START_R if is_start else NODE_R
        self._hovered       = False
        self._selected      = False

        self.setAcceptHoverEvents(True)
        self.setCursor(Qt.PointingHandCursor)
        self.setZValue(2)

    def boundingRect(self) -> QRectF:
        r = self._r + 10
        extra_top = 14 if self._is_start else 0
        extra_bot = 10 if self._has_stash else 0
        top = -r - 8 - extra_top
        return QRectF(-r - 8, top, (r + 8) * 2, r * 2 + 16 + extra_top + extra_bot)

    def paint(self, painter: QPainter, _option, _widget):
        painter.setRenderHint(QPainter.Antialiasing)
        r = self._r
        c = self._color

        if self._hovered or self._selected:
            ring = QColor(c)
            ring.setAlpha(40)
            painter.setPen(QPen(ring, 2.5))
            painter.setBrush(Qt.NoBrush)
            painter.drawEllipse(QPointF(0, 0), r + 5, r + 5)

        if self._is_local_only:
            painter.setBrush(Qt.NoBrush)
            painter.setPen(QPen(c, 2.5))
        else:
            border = QColor("white")
            border.setAlpha(120)
            painter.setBrush(QBrush(c))
            painter.setPen(QPen(border, 1.5))
        painter.drawEllipse(QPointF(0, 0), r, r)

        if self._selected:
            painter.setBrush(Qt.NoBrush)
            painter.setPen(QPen(QColor("white"), 2))
            painter.drawEllipse(QPointF(0, 0), r + 4, r + 4)

        if self._is_head:
            painter.setBrush(Qt.NoBrush)
            painter.setPen(QPen(QColor(COLORS["danger"]), 2.5))
            painter.drawEllipse(QPointF(0, 0), r + 5, r + 5)

        if self._is_start:
            pole_top = QPointF(0, -r - 20)
            pole_bot = QPointF(0, -r - 2)
            painter.setPen(QPen(c, 2))
            painter.drawLine(pole_bot, pole_top)

            flag = QPolygonF([
                pole_top,
                QPointF(9, -r - 12),
                QPointF(0, -r - 5),
            ])
            painter.setBrush(QBrush(c))
            painter.setPen(Qt.NoPen)
            painter.drawPolygon(flag)

        if self._has_stash:
            amber = QColor("#d69e2e")
            painter.setPen(Qt.NoPen)
            painter.setBrush(QBrush(amber))
            painter.drawEllipse(QPointF(0, r + 5), 3.5, 3.5)

        _show_local  = self._is_action_head or self._is_local_tip
        _show_remote = self._is_remote_tip
        if _show_local and _show_remote:
            painter.setPen(Qt.NoPen)
            painter.setBrush(QBrush(QColor("#3b82f6")))
            painter.drawEllipse(QPointF(r + 4, 0), 4, 4)
            painter.setBrush(QBrush(QColor("#ef4444")))
            painter.drawEllipse(QPointF(r + 11, 0), 4, 4)
        elif _show_local:
            painter.setPen(Qt.NoPen)
            painter.setBrush(QBrush(QColor("#3b82f6")))
            painter.drawEllipse(QPointF(r + 6, 0), 4, 4)
        elif _show_remote:
            painter.setPen(Qt.NoPen)
            painter.setBrush(QBrush(QColor("#ef4444")))
            painter.drawEllipse(QPointF(r + 6, 0), 4, 4)

    def hoverEnterEvent(self, _e):
        self._hovered = True
        self.update()

    def hoverLeaveEvent(self, _e):
        self._hovered = False
        self.update()

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.clicked.emit(self._commit)
            event.accept()
        else:
            super().mousePressEvent(event)

    def set_selected(self, selected: bool):
        self._selected = selected
        self.update()

    def set_head(self, is_head: bool):
        self._is_head = is_head
        self.prepareGeometryChange()
        self.update()


class EdgeItem(QGraphicsPathItem):
    """Cross-lane connection line (L-elbow, solid or dashed)."""

    def __init__(
        self,
        cx: float, cy: float,
        px: float, py: float,
        color: str,
        dashed: bool = False,
        orientation: str = ORIENT_LR,
        diagonal: bool = False,
    ):
        path = QPainterPath()
        path.moveTo(cx, cy)
        if diagonal:
            path.lineTo(px, py)
        elif dashed and orientation in (ORIENT_LR, ORIENT_RL):
            path.lineTo(px, cy)
            path.lineTo(px, py)
        elif orientation in (ORIENT_LR, ORIENT_RL):
            path.lineTo(cx, py)
            path.lineTo(px, py)
        else:
            path.lineTo(px, cy)
            path.lineTo(px, py)
        super().__init__(path)

        white = QColor("white")
        white.setAlpha(140)
        style = Qt.DashLine if dashed else Qt.SolidLine
        self.setPen(QPen(white, 1.5, style, Qt.RoundCap, Qt.RoundJoin))
        self.setBrush(QBrush(Qt.NoBrush))
        self.setZValue(1)
        self.setAcceptedMouseButtons(Qt.NoButton)


class ContributorBadge(QGraphicsObject):
    """Circular avatar badge floating on a contributor's latest commit node."""

    clicked = pyqtSignal(str)   # login

    def __init__(self, login: str, color: str):
        super().__init__()
        self._login   = login
        self._color   = QColor(color)
        self._pixmap: Optional[QPixmap] = None
        self._hovered = False

        self.setAcceptHoverEvents(True)
        self.setCursor(Qt.PointingHandCursor)
        self.setZValue(5)
        self.setToolTip(login)

    def set_pixmap(self, pm: QPixmap):
        self._pixmap = pm.scaled(
            BADGE_R * 2, BADGE_R * 2,
            Qt.KeepAspectRatioByExpanding,
            Qt.SmoothTransformation,
        )
        self.update()

    def boundingRect(self) -> QRectF:
        r = BADGE_R + 6
        return QRectF(-r, -r, r * 2, r * 2)

    def paint(self, painter: QPainter, _option, _widget):
        painter.setRenderHint(QPainter.Antialiasing)
        r = BADGE_R
        c = self._color

        if self._hovered:
            ring = QColor(c)
            ring.setAlpha(50)
            painter.setPen(QPen(ring, 2))
            painter.setBrush(Qt.NoBrush)
            painter.drawEllipse(QPointF(0, 0), r + 4, r + 4)

        clip = QPainterPath()
        clip.addEllipse(QPointF(0, 0), r, r)
        painter.setClipPath(clip)

        if self._pixmap:
            painter.drawPixmap(-r, -r, self._pixmap)
        else:
            bg = QColor(c.red(), c.green(), c.blue(), 60)
            painter.setBrush(QBrush(bg))
            painter.setPen(Qt.NoPen)
            painter.drawEllipse(QPointF(0, 0), r, r)
            painter.setClipping(False)
            painter.setPen(QPen(c))
            font = QFont("Urbanist", max(6, r // 2), QFont.Bold)
            painter.setFont(font)
            painter.drawText(
                QRectF(-r, -r, r * 2, r * 2), Qt.AlignCenter,
                self._login[:2].upper(),
            )

        painter.setClipping(False)
        painter.setBrush(Qt.NoBrush)
        painter.setPen(QPen(c, 2))
        painter.drawEllipse(QPointF(0, 0), r, r)

    def hoverEnterEvent(self, _e):
        self._hovered = True
        self.update()

    def hoverLeaveEvent(self, _e):
        self._hovered = False
        self.update()

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.clicked.emit(self._login)
            event.accept()
        else:
            super().mousePressEvent(event)


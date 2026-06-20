"""Stepped instructions wizard with QPainter illustrations and animations."""
from __future__ import annotations

import math
from PyQt5.QtCore import (
    Qt, QPropertyAnimation, QEasingCurve, QPointF, QRectF, QTimer,
    pyqtProperty,
)
from PyQt5.QtGui import (
    QPainter, QColor, QPen, QBrush, QFont, QRadialGradient, QPainterPath,
    QPolygonF, QLinearGradient, QPixmap,
)
from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QWidget,
    QGraphicsOpacityEffect, QStackedWidget,
)
from styles.theme import COLORS

_ACCENT = QColor(COLORS["accent"])
_BG = QColor(COLORS["bg_primary"])
_CARD = QColor(COLORS["bg_card"])
_BORDER = QColor(COLORS["border"])
_TEXT = QColor(COLORS["text_primary"])
_TEXT2 = QColor(COLORS["text_secondary"])
_MUTED = QColor(COLORS["text_muted"])
_DANGER = QColor(COLORS["danger"])
_WARNING = QColor(COLORS["warning"])
_INFO = QColor(COLORS["info"])

_INDIGO = QColor("#6366f1")
_AMBER = QColor("#f59e0b")
_CYAN = QColor("#06b6d4")
_PINK = QColor("#ec4899")
_TEAL = QColor("#14b8a6")
_GREEN = QColor("#22c55e")

NODE_R = 10
START_R = 14

import os as _os
_LOGO_PATH = _os.path.join(_os.path.dirname(_os.path.abspath(__file__)), "..", "..", "logo", "optimised_logo1-removebg.png")


# ── Base illustration widget ──────────────────────────────────────────────────

class _Illust(QWidget):
    """Base class for animated illustrations. Subclasses override _draw(p, progress)."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._p = 0.0
        self._anim = QPropertyAnimation(self, b"prog")
        self._anim.setDuration(900)
        self._anim.setEasingCurve(QEasingCurve.OutCubic)
        self.setFixedHeight(200)
        self.setStyleSheet("background: transparent;")

    @pyqtProperty(float)
    def prog(self):
        return self._p

    @prog.setter
    def prog(self, v):
        self._p = v
        self.update()

    def animate(self):
        self._anim.stop()
        self._p = 0.0
        self._anim.setStartValue(0.0)
        self._anim.setEndValue(1.0)
        self._anim.start()

    def paintEvent(self, ev):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        self._draw(p, self._p)
        p.end()

    def _draw(self, p: QPainter, t: float):
        pass

    # ── Shared drawing helpers ────────────────────────────────────────────

    def _node(self, p: QPainter, cx: float, cy: float, color: QColor,
              r: float = NODE_R, alpha: int = 255, glow: bool = False,
              filled: bool = True):
        if glow:
            g = QRadialGradient(QPointF(cx, cy), r + 10)
            gc = QColor(color)
            gc.setAlpha(60)
            g.setColorAt(0, gc)
            g.setColorAt(1, QColor(0, 0, 0, 0))
            p.setBrush(QBrush(g))
            p.setPen(Qt.NoPen)
            p.drawEllipse(QPointF(cx, cy), r + 10, r + 10)
        c = QColor(color)
        c.setAlpha(alpha)
        if filled:
            p.setBrush(QBrush(c))
            p.setPen(QPen(QColor(255, 255, 255, 120), 1.5))
        else:
            p.setBrush(Qt.NoBrush)
            p.setPen(QPen(c, 2.5))
        p.drawEllipse(QPointF(cx, cy), r, r)

    def _edge(self, p: QPainter, x1, y1, x2, y2, color=None, alpha=140,
              dashed=False, width=1.5):
        c = QColor(color) if color else QColor(255, 255, 255)
        c.setAlpha(alpha)
        pen = QPen(c, width)
        if dashed:
            pen.setStyle(Qt.DashLine)
        pen.setCapStyle(Qt.RoundCap)
        pen.setJoinStyle(Qt.RoundJoin)
        p.setPen(pen)
        p.drawLine(QPointF(x1, y1), QPointF(x2, y2))

    def _label(self, p: QPainter, cx: float, cy: float, text: str, color: QColor):
        font = QFont("Inter", 9)
        font.setWeight(QFont.Medium)
        p.setFont(font)
        fm = p.fontMetrics()
        tw = fm.horizontalAdvance(text)
        th = fm.height()
        pw, ph = tw + 16, th + 6
        rx, ry = cx - pw / 2, cy - ph / 2
        bg = QColor(color)
        bg.setAlpha(28)
        p.setBrush(QBrush(bg))
        bc = QColor(color)
        bc.setAlpha(160)
        p.setPen(QPen(bc, 1))
        p.drawRoundedRect(QRectF(rx, ry, pw, ph), ph / 2, ph / 2)
        p.setPen(QPen(color))
        p.drawText(QRectF(rx, ry, pw, ph), Qt.AlignCenter, text)

    def _flag(self, p: QPainter, cx: float, cy: float, color: QColor, r: float = NODE_R):
        p.setPen(QPen(QColor(color), 2))
        p.drawLine(QPointF(cx, cy - r - 2), QPointF(cx, cy - r - 20))
        flag = QPolygonF([
            QPointF(cx, cy - r - 20),
            QPointF(cx + 9, cy - r - 12),
            QPointF(cx, cy - r - 5),
        ])
        p.setBrush(QBrush(color))
        p.setPen(Qt.NoPen)
        p.drawPolygon(flag)

    def _arrow(self, p: QPainter, x1, y1, x2, y2, color: QColor, size=6):
        c = QColor(color)
        c.setAlpha(200)
        p.setPen(QPen(c, 2, Qt.SolidLine, Qt.RoundCap))
        p.drawLine(QPointF(x1, y1), QPointF(x2, y2))
        angle = math.atan2(y2 - y1, x2 - x1)
        ax = x2 - size * math.cos(angle - 0.4)
        ay = y2 - size * math.sin(angle - 0.4)
        bx = x2 - size * math.cos(angle + 0.4)
        by = y2 - size * math.sin(angle + 0.4)
        tri = QPolygonF([QPointF(x2, y2), QPointF(ax, ay), QPointF(bx, by)])
        p.setBrush(QBrush(c))
        p.setPen(Qt.NoPen)
        p.drawPolygon(tri)

    def _text(self, p: QPainter, x: float, y: float, text: str,
              color: QColor = None, size: int = 10, bold: bool = False, center: bool = False):
        c = color or _TEXT2
        font = QFont("Inter", size)
        if bold:
            font.setWeight(QFont.Bold)
        p.setFont(font)
        p.setPen(QPen(c))
        if center:
            fm = p.fontMetrics()
            tw = fm.horizontalAdvance(text)
            p.drawText(QPointF(x - tw / 2, y), text)
        else:
            p.drawText(QPointF(x, y), text)

    def _spine(self, p: QPainter, x1, y1, x2, y2, color=None, alpha=160):
        """Lane spine — 2px, matches actual canvas."""
        self._edge(p, x1, y1, x2, y2, color=color, alpha=alpha, width=2)

    def _stash_dot(self, p: QPainter, cx: float, cy: float, r: float = NODE_R):
        p.setBrush(QBrush(_WARNING))
        p.setPen(Qt.NoPen)
        p.drawEllipse(QPointF(cx, cy + r + 5), 3.5, 3.5)

    def _btn_pill(self, p: QPainter, cx: float, cy: float, text: str,
                  bg: QColor, fg: QColor = None):
        fg = fg or QColor(255, 255, 255)
        font = QFont("Inter", 8)
        font.setWeight(QFont.Bold)
        p.setFont(font)
        fm = p.fontMetrics()
        tw = fm.horizontalAdvance(text)
        pw, ph = tw + 16, fm.height() + 8
        rx, ry = cx - pw / 2, cy - ph / 2
        p.setBrush(QBrush(bg))
        p.setPen(Qt.NoPen)
        p.drawRoundedRect(QRectF(rx, ry, pw, ph), 4, 4)
        p.setPen(QPen(fg))
        p.drawText(QRectF(rx, ry, pw, ph), Qt.AlignCenter, text)

    def _elbow(self, p: QPainter, x1, y1, x2, y2, color=None, alpha=140,
               dashed=False, horiz_first=True):
        """L-shaped elbow: two perpendicular segments."""
        c = QColor(color) if color else QColor(255, 255, 255)
        c.setAlpha(alpha)
        pen = QPen(c, 1.5)
        if dashed:
            pen.setStyle(Qt.DashLine)
        pen.setCapStyle(Qt.RoundCap)
        pen.setJoinStyle(Qt.RoundJoin)
        p.setPen(pen)
        path = QPainterPath(QPointF(x1, y1))
        if horiz_first:
            path.lineTo(x2, y1)
            path.lineTo(x2, y2)
        else:
            path.lineTo(x1, y2)
            path.lineTo(x2, y2)
        p.setBrush(Qt.NoBrush)
        p.drawPath(path)

    def _elbow_arrow(self, p: QPainter, x1, y1, x2, y2, color=None, alpha=140,
                     horiz_first=True, arr_size=7):
        """L-elbow with arrow head at (x2, y2)."""
        self._elbow(p, x1, y1, x2, y2, color=color, alpha=alpha, horiz_first=horiz_first)
        c = QColor(color) if color else QColor(255, 255, 255)
        c.setAlpha(alpha)
        if horiz_first:
            d = 1 if y2 > y1 else -1
            tri = QPolygonF([
                QPointF(x2, y2),
                QPointF(x2 - arr_size / 2, y2 - d * arr_size),
                QPointF(x2 + arr_size / 2, y2 - d * arr_size),
            ])
        else:
            d = 1 if x2 > x1 else -1
            tri = QPolygonF([
                QPointF(x2, y2),
                QPointF(x2 - d * arr_size, y2 - arr_size / 2),
                QPointF(x2 - d * arr_size, y2 + arr_size / 2),
            ])
        p.setBrush(QBrush(c))
        p.setPen(Qt.NoPen)
        p.drawPolygon(tri)


# ── Stage illustrations (LR orientation: oldest left, newest right) ───────────

class _WelcomeIllust(_Illust):
    _logo_pm = None

    def _draw(self, p, t):
        w = self.width()
        cx = w / 2

        if _WelcomeIllust._logo_pm is None:
            _WelcomeIllust._logo_pm = QPixmap(_LOGO_PATH)

        # Logo — fade in, centered, 72px
        if t > 0.1:
            a = min(1.0, (t - 0.1) / 0.35)
            logo_size = 72
            pm = _WelcomeIllust._logo_pm.scaled(
                logo_size, logo_size, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            p.setOpacity(a)
            p.drawPixmap(int(cx - pm.width() / 2), 15, pm)
            p.setOpacity(1.0)

        # "Evo Git" big text
        if t > 0.3:
            a = min(1.0, (t - 0.3) / 0.3)
            font = QFont("Tilt Warp", 22)
            font.setWeight(QFont.Bold)
            p.setFont(font)
            p.setPen(QPen(QColor(255, 255, 255, int(a * 240))))
            fm = p.fontMetrics()
            tw = fm.horizontalAdvance("Evo Git")
            p.drawText(QPointF(cx - tw / 2, 115), "Evo Git")

        # Tagline
        if t > 0.55:
            a = min(1.0, (t - 0.55) / 0.35)
            self._text(p, cx, 150, "Your project's story, visualized.",
                       QColor(255, 255, 255, int(a * 160)), size=11, center=True)


class _TrackProjectIllust(_Illust):
    def _draw(self, p, t):
        w = self.width()
        cx = w / 2
        if t > 0.1:
            a = min(1.0, (t - 0.1) / 0.3)
            self._btn_pill(p, cx, 35, "Track a Project",
                           QColor(_BORDER.red(), _BORDER.green(), _BORDER.blue(), int(a * 220)),
                           QColor(255, 255, 255, int(a * 200)))
        opts = [
            (w * 0.2, "Clone", "from GitHub"),
            (w * 0.5, "Open", "local folder"),
            (w * 0.8, "Init", "new repo"),
        ]
        for i, (ox, title, sub) in enumerate(opts):
            st = 0.35 + i * 0.15
            if t > st:
                a = min(1.0, (t - st) / 0.25)
                rc = QColor(COLORS["bg_secondary"])
                rc.setAlpha(int(a * 255))
                p.setBrush(QBrush(rc))
                bc = QColor(_BORDER)
                bc.setAlpha(int(a * 180))
                p.setPen(QPen(bc, 1))
                p.drawRoundedRect(QRectF(ox - 50, 70, 100, 55), 6, 6)
                self._text(p, ox, 98, title,
                           QColor(255, 255, 255, int(a * 220)), size=10, bold=True, center=True)
                self._text(p, ox, 114, sub,
                           QColor(255, 255, 255, int(a * 100)), size=8, center=True)
        if t > 0.8:
            a = min(1.0, (t - 0.8) / 0.2)
            self._text(p, cx, 160, "start by connecting a project to Evo Git",
                       QColor(255, 255, 255, int(a * 130)), size=9, center=True)


class _CommitsIllust(_Illust):
    def _draw(self, p, t):
        w = self.width()
        cy = 80
        xs = [w * 0.15, w * 0.35, w * 0.55, w * 0.75]
        for i, x in enumerate(xs):
            if t < (i + 1) * 0.2:
                break
            highlight = (i == 2)
            self._node(p, x, cy, _ACCENT, glow=highlight and t > 0.6)
            if i > 0:
                self._edge(p, xs[i - 1], cy, x, cy)
        if t > 0.5:
            a = min(1.0, (t - 0.5) / 0.3)
            self._text(p, w * 0.03, cy + 4, "older",
                       QColor(255, 255, 255, int(a * 100)), size=8)
            self._arrow(p, w * 0.82, cy, w * 0.9, cy,
                        QColor(255, 255, 255, int(a * 80)), size=5)
            self._text(p, w * 0.92, cy + 4, "newer",
                       QColor(255, 255, 255, int(a * 100)), size=8)
        if t > 0.6:
            a = min(1.0, (t - 0.6) / 0.3)
            self._text(p, xs[2], cy + 28, "↑ a snapshot of your code",
                       QColor(255, 255, 255, int(a * 180)), size=9, center=True)


class _GraphIllust(_Illust):
    def _draw(self, p, t):
        w = self.width()
        cy = 80
        xs = [w * 0.05, w * 0.25, w * 0.45, w * 0.65, w * 0.85]
        n = len(xs)
        drawn = int(t * n * 1.5)
        for i in range(min(drawn, n)):
            self._node(p, xs[i], cy, _ACCENT)
            if i > 0:
                frac = min(1.0, (t * n * 1.5 - i) / 1.0)
                mid_x = xs[i - 1] + (xs[i] - xs[i - 1]) * frac
                self._edge(p, xs[i - 1], cy, mid_x, cy)
        if t > 0.7:
            a = min(1.0, (t - 0.7) / 0.25)
            self._text(p, w / 2, cy + 35, "time flows  →",
                       QColor(255, 255, 255, int(a * 160)), size=10, center=True)


class _BranchesIllust(_Illust):
    def _draw(self, p, t):
        w = self.width()
        my = 100
        by = 55
        main_x = [w * 0.05, w * 0.25, w * 0.45, w * 0.65, w * 0.85]
        branch_x = [w * 0.45, w * 0.65]

        for i, x in enumerate(main_x):
            if t < i * 0.15:
                break
            self._node(p, x, my, _ACCENT)
            if i > 0:
                self._edge(p, main_x[i - 1], my, x, my)

        if t > 0.4:
            bt = min(1.0, (t - 0.4) / 0.3)
            self._elbow(p, main_x[1], my, branch_x[0], by,
                        color=_INDIGO, alpha=int(bt * 140), dashed=True, horiz_first=True)
            if bt > 0.3:
                self._node(p, branch_x[0], by, _INDIGO)
            if bt > 0.7:
                self._edge(p, branch_x[0], by, branch_x[1], by,
                           color=_INDIGO, alpha=int(bt * 140))
                self._node(p, branch_x[1], by, _INDIGO)

        if t > 0.7:
            a = min(1.0, (t - 0.7) / 0.25)
            self._label(p, main_x[-1], my + 25, "main",
                        QColor(_ACCENT.red(), _ACCENT.green(), _ACCENT.blue(), int(a * 255)))
            self._label(p, branch_x[-1], by - 22, "feature",
                        QColor(_INDIGO.red(), _INDIGO.green(), _INDIGO.blue(), int(a * 255)))


class _TipsIllust(_Illust):
    def _draw(self, p, t):
        w = self.width()
        cy = 80
        # LR: oldest on left, newest on right
        xs = [w * 0.15, w * 0.35, w * 0.55, w * 0.75]

        for i, x in enumerate(xs):
            if t < i * 0.15:
                break
            is_start = (i == 0)
            is_tip = (i == len(xs) - 1)
            r = START_R if is_start else NODE_R
            self._node(p, x, cy, _ACCENT, r=r, glow=is_tip)
            if i > 0:
                self._edge(p, xs[i - 1], cy, x, cy)

        if t > 0.5:
            a = min(1.0, (t - 0.5) / 0.3)
            self._flag(p, xs[0], cy, QColor(_ACCENT.red(), _ACCENT.green(), _ACCENT.blue(), int(a * 255)))
            self._text(p, xs[0], cy + 28, "branch start",
                       QColor(255, 255, 255, int(a * 160)), size=9, center=True)
        if t > 0.65:
            a = min(1.0, (t - 0.65) / 0.3)
            self._text(p, xs[-1], cy + 28, "latest (tip)",
                       QColor(255, 255, 255, int(a * 160)), size=9, center=True)


class _RemoteIllust(_Illust):
    def _draw(self, p, t):
        w = self.width()
        cy = 80
        nodes = [
            (w * 0.10, 255), (w * 0.27, 255), (w * 0.44, 255),
            (w * 0.61, 102), (w * 0.78, 102),
        ]
        for i, (x, alpha) in enumerate(nodes):
            if t < i * 0.15:
                break
            self._node(p, x, cy, _ACCENT, alpha=alpha)
            if i > 0:
                px, pa = nodes[i - 1]
                ea = min(alpha, pa)
                self._edge(p, px, cy, x, cy, alpha=ea)

        if t > 0.6:
            a = min(1.0, (t - 0.6) / 0.3)
            self._text(p, w * 0.27, cy + 28, "your commits",
                       QColor(255, 255, 255, int(a * 160)), size=9, center=True)
            self._text(p, w * 0.70, cy + 28, "remote only (dimmed)",
                       QColor(255, 255, 255, int(a * 100)), size=9, center=True)


class _DetailPanelIllust(_Illust):
    def _draw(self, p, t):
        w = self.width()
        cx = w / 2

        if t > 0.1:
            self._node(p, cx - 60, 60, _ACCENT, glow=True)
            self._node(p, cx - 60, 100, _ACCENT)
            self._edge(p, cx - 60, 60, cx - 60, 100)

        if t > 0.3:
            a = min(1.0, (t - 0.3) / 0.3)
            # panel outline
            pc = QColor(255, 255, 255, int(a * 40))
            p.setBrush(QBrush(QColor(COLORS["bg_secondary"])))
            bc = QColor(_BORDER)
            bc.setAlpha(int(a * 180))
            p.setPen(QPen(bc, 1))
            p.drawRoundedRect(QRectF(cx - 10, 20, 150, 170), 8, 8)

            if t > 0.5:
                ba = min(1.0, (t - 0.5) / 0.3)
                self._text(p, cx + 10, 50, "fix: update login",
                           QColor(255, 255, 255, int(ba * 200)), size=10, bold=True)
                self._text(p, cx + 10, 68, "by you · 2 min ago",
                           QColor(255, 255, 255, int(ba * 100)), size=8)

                self._text(p, cx + 10, 95, "ACTIONS",
                           QColor(255, 255, 255, int(ba * 80)), size=7, bold=True)

                btns = ["Create Branch", "Merge", "Revert"]
                for j, txt in enumerate(btns):
                    by = 108 + j * 26
                    self._btn_pill(p, cx + 65, by, txt,
                                   QColor(_ACCENT.red(), _ACCENT.green(), _ACCENT.blue(), int(ba * 180)))


class _MergeIllust(_Illust):
    def _draw(self, p, t):
        w = self.width()
        my = 110
        by = 55
        main_x = [w * 0.05, w * 0.25, w * 0.45, w * 0.65, w * 0.85]
        branch_x = [w * 0.25, w * 0.45]

        for i, x in enumerate(main_x):
            if t < i * 0.12:
                break
            self._node(p, x, my, _ACCENT)
            if i > 0:
                self._edge(p, main_x[i - 1], my, x, my)

        if t > 0.3:
            bt = min(1.0, (t - 0.3) / 0.25)
            self._elbow(p, main_x[1], my, branch_x[0], by,
                        color=_INDIGO, alpha=int(bt * 140), dashed=True, horiz_first=True)
            self._node(p, branch_x[0], by, _INDIGO)
            if bt > 0.5:
                self._edge(p, branch_x[0], by, branch_x[1], by,
                           color=_INDIGO, alpha=int(bt * 140))
                self._node(p, branch_x[1], by, _INDIGO)

        if t > 0.65:
            mt = min(1.0, (t - 0.65) / 0.3)
            self._elbow_arrow(p, branch_x[1], by, main_x[3], my,
                              color=_INDIGO, alpha=int(mt * 180), horiz_first=False)
            if mt > 0.5:
                self._text(p, main_x[3], my + 25, "merge commit ↑",
                           QColor(255, 255, 255, int(mt * 160)), size=9, center=True)


class _PushPullIllust(_Illust):
    def _draw(self, p, t):
        w = self.width()
        lx = w * 0.3
        rx = w * 0.7
        cy = 55

        self._text(p, lx, 25, "LOCAL", _MUTED, size=8, bold=True, center=True)
        self._text(p, rx, 25, "REMOTE", _MUTED, size=8, bold=True, center=True)

        for i, x in enumerate([lx + 40, lx, lx - 40]):
            if t > i * 0.12:
                self._node(p, x, cy, _ACCENT)
                if i > 0:
                    px = [lx + 40, lx, lx - 40][i - 1]
                    self._edge(p, px, cy, x, cy)
        for i, x in enumerate([rx + 20, rx - 20]):
            if t > i * 0.12:
                self._node(p, x, cy, _ACCENT, alpha=120)
                if i > 0:
                    self._edge(p, rx + 20, cy, x, cy, alpha=80)

        if t > 0.4:
            a = min(1.0, (t - 0.4) / 0.25)
            self._arrow(p, lx + 50, 110, rx - 30, 110,
                        QColor(_GREEN.red(), _GREEN.green(), _GREEN.blue(), int(a * 200)))
            self._text(p, w / 2, 105, "upload (push)",
                       QColor(_GREEN.red(), _GREEN.green(), _GREEN.blue(), int(a * 160)),
                       size=9, center=True)

        if t > 0.65:
            a = min(1.0, (t - 0.65) / 0.3)
            self._arrow(p, rx - 30, 150, lx + 50, 150,
                        QColor(_CYAN.red(), _CYAN.green(), _CYAN.blue(), int(a * 200)))
            self._text(p, w / 2, 145, "pull (download)",
                       QColor(_CYAN.red(), _CYAN.green(), _CYAN.blue(), int(a * 160)),
                       size=9, center=True)


class _StashIllust(_Illust):
    def _draw(self, p, t):
        w = self.width()
        cy = 70
        xs = [w * 0.15, w * 0.35, w * 0.55, w * 0.75]

        for i, x in enumerate(xs):
            if t < i * 0.15:
                break
            self._node(p, x, cy, _ACCENT)
            if i > 0:
                self._edge(p, xs[i - 1], cy, x, cy)

        if t > 0.5:
            a = min(1.0, (t - 0.5) / 0.3)
            self._stash_dot(p, xs[2], cy)
            self._text(p, xs[2], cy + 35, "unsaved changes ↑",
                       QColor(_WARNING.red(), _WARNING.green(), _WARNING.blue(), int(a * 200)),
                       size=9, center=True)
        if t > 0.7:
            a = min(1.0, (t - 0.7) / 0.25)
            self._text(p, w / 2, 150, '"Save Changes" keeps your work safe',
                       QColor(255, 255, 255, int(a * 140)), size=9, center=True)


class _EdgeTypesIllust(_Illust):
    def _draw(self, p, t):
        w = self.width()
        cols = [w * 0.18, w * 0.5, w * 0.82]
        sy = 65

        # Column 1: solid spine (horizontal)
        if t > 0.05:
            a = min(1.0, (t - 0.05) / 0.25)
            self._node(p, cols[0] + 25, sy, _ACCENT, alpha=int(a * 255))
            self._node(p, cols[0] - 25, sy, _ACCENT, alpha=int(a * 255))
            self._edge(p, cols[0] + 25, sy, cols[0] - 25, sy, alpha=int(a * 140))
            self._text(p, cols[0], sy + 30, "parent → child",
                       QColor(255, 255, 255, int(a * 160)), size=8, center=True)
            self._text(p, cols[0], sy + 43, "(solid line)",
                       QColor(255, 255, 255, int(a * 100)), size=7, center=True)

        # Column 2: dashed L-elbow (branch creation)
        if t > 0.3:
            a = min(1.0, (t - 0.3) / 0.25)
            self._node(p, cols[1] + 20, sy + 15, _ACCENT, alpha=int(a * 255))
            self._node(p, cols[1] - 20, sy - 20, _INDIGO, alpha=int(a * 255))
            self._elbow(p, cols[1] + 20, sy + 15, cols[1] - 20, sy - 20,
                        color=_INDIGO, alpha=int(a * 140), dashed=True, horiz_first=True)
            self._text(p, cols[1], sy + 30, "branch created",
                       QColor(255, 255, 255, int(a * 160)), size=8, center=True)
            self._text(p, cols[1], sy + 43, "(dashed L-elbow)",
                       QColor(255, 255, 255, int(a * 100)), size=7, center=True)

        # Column 3: merge L-elbow with arrow
        if t > 0.55:
            a = min(1.0, (t - 0.55) / 0.25)
            self._node(p, cols[2] + 20, sy - 20, _INDIGO, alpha=int(a * 255))
            self._node(p, cols[2] - 20, sy + 15, _ACCENT, alpha=int(a * 255))
            self._elbow_arrow(p, cols[2] + 20, sy - 20, cols[2] - 20, sy + 15,
                              color=_INDIGO, alpha=int(a * 180), horiz_first=False)
            self._text(p, cols[2], sy + 30, "merge",
                       QColor(255, 255, 255, int(a * 160)), size=8, center=True)
            self._text(p, cols[2], sy + 43, "(L-elbow + arrow)",
                       QColor(255, 255, 255, int(a * 100)), size=7, center=True)

        if t > 0.85:
            a = min(1.0, (t - 0.85) / 0.15)
            self._text(p, w / 2, 175, "lines tell the story of how code flows",
                       QColor(255, 255, 255, int(a * 120)), size=9, center=True)


class _CommitTypesIllust(_Illust):
    def _draw(self, p, t):
        w = self.width()
        cols = [w * 0.12, w * 0.31, w * 0.5, w * 0.69, w * 0.88]
        y = 55

        # 1. Local-only (unpushed) = hollow outline
        if t > 0.05:
            a = min(1.0, (t - 0.05) / 0.15)
            self._node(p, cols[0], y, _ACCENT, alpha=int(a * 255), filled=False)
            self._text(p, cols[0], y + 28, "local",
                       QColor(255, 255, 255, int(a * 160)), size=8, center=True)
            self._text(p, cols[0], y + 41, "(unpushed)",
                       QColor(255, 255, 255, int(a * 100)), size=7, center=True)

        # 2. Pushed = filled (exists on remote)
        if t > 0.2:
            a = min(1.0, (t - 0.2) / 0.15)
            self._node(p, cols[1], y, _ACCENT, alpha=int(a * 255))
            self._text(p, cols[1], y + 28, "pushed",
                       QColor(255, 255, 255, int(a * 160)), size=8, center=True)
            self._text(p, cols[1], y + 41, "(on remote)",
                       QColor(255, 255, 255, int(a * 100)), size=7, center=True)

        # 3. Remote-only = filled but dimmed (40% opacity)
        if t > 0.35:
            self._node(p, cols[2], y, _ACCENT, alpha=102)
            self._text(p, cols[2], y + 28, "remote only",
                       QColor(255, 255, 255, 160), size=8, center=True)
            self._text(p, cols[2], y + 41, "(not pulled)",
                       QColor(255, 255, 255, 100), size=7, center=True)

        # 4. HEAD = filled node + red danger ring
        if t > 0.5:
            a = min(1.0, (t - 0.5) / 0.15)
            self._node(p, cols[3], y, _ACCENT, alpha=int(a * 255))
            rc = QColor(_DANGER)
            rc.setAlpha(int(a * 255))
            p.setBrush(Qt.NoBrush)
            p.setPen(QPen(rc, 2.5))
            p.drawEllipse(QPointF(cols[3], y), NODE_R + 5, NODE_R + 5)
            self._text(p, cols[3], y + 28, "HEAD",
                       QColor(255, 255, 255, int(a * 160)), size=8, center=True)
            self._text(p, cols[3], y + 41, "(you are here)",
                       QColor(255, 255, 255, int(a * 100)), size=7, center=True)

        # 5. Stash dot — amber dot below node
        if t > 0.65:
            a = min(1.0, (t - 0.65) / 0.15)
            self._node(p, cols[4], y, _ACCENT, alpha=int(a * 255))
            self._stash_dot(p, cols[4], y)
            self._text(p, cols[4], y + 35, "unsaved",
                       QColor(255, 255, 255, int(a * 160)), size=8, center=True)
            self._text(p, cols[4], y + 48, "(amber dot ↑)",
                       QColor(255, 255, 255, int(a * 100)), size=7, center=True)

        if t > 0.85:
            a = min(1.0, (t - 0.85) / 0.15)
            self._text(p, w / 2, 155, "each style tells you the commit's status at a glance",
                       QColor(255, 255, 255, int(a * 120)), size=9, center=True)


class _ConflictUIIllust(_Illust):
    """Mockup of the merge conflict resolution dialog."""

    def _draw(self, p, t):
        w = self.width()
        cx = w / 2

        if t < 0.1:
            return

        a = min(1.0, (t - 0.1) / 0.25)

        # Dialog card
        card_w, card_h = 380, 180
        card_x = cx - card_w / 2
        card_y = 8
        bg = QColor(COLORS["bg_secondary"])
        bg.setAlpha(int(a * 255))
        p.setBrush(QBrush(bg))
        bc = QColor(_BORDER)
        bc.setAlpha(int(a * 180))
        p.setPen(QPen(bc, 1))
        p.drawRoundedRect(QRectF(card_x, card_y, card_w, card_h), 8, 8)

        if t < 0.25:
            return
        ia = min(1.0, (t - 0.25) / 0.3)

        # Badge
        self._text(p, card_x + 12, card_y + 20, "MERGE CONFLICT",
                   QColor(_WARNING.red(), _WARNING.green(), _WARNING.blue(), int(ia * 255)),
                   size=7, bold=True)

        # Progress
        self._text(p, card_x + card_w - 80, card_y + 20, "1 of 2 resolved",
                   QColor(255, 255, 255, int(ia * 100)), size=7)

        # Branch names
        self._text(p, card_x + 12, card_y + 38, "main  ↔  feature",
                   QColor(255, 255, 255, int(ia * 200)), size=9, bold=True)

        # Divider
        dc = QColor(_BORDER)
        dc.setAlpha(int(ia * 150))
        p.setPen(QPen(dc, 1))
        p.drawLine(QPointF(card_x + 10, card_y + 46),
                   QPointF(card_x + card_w - 10, card_y + 46))

        # File name
        self._text(p, card_x + 12, card_y + 62, "shared.txt",
                   QColor(255, 255, 255, int(ia * 180)), size=8, bold=True)

        # Two code panels
        panel_w = (card_w - 36) / 2
        panel_h = 55
        ly = card_y + 68
        lx = card_x + 10
        rx = card_x + 10 + panel_w + 8

        # Left panel header
        self._text(p, lx + 4, ly + 10, "Original",
                   QColor(255, 255, 255, int(ia * 80)), size=7)
        # Right panel header
        self._text(p, rx + 4, ly + 10, "Incoming",
                   QColor(_WARNING.red(), _WARNING.green(), _WARNING.blue(), int(ia * 180)), size=7)

        # Left code area
        lbg = QColor(COLORS["bg_primary"])
        lbg.setAlpha(int(ia * 200))
        p.setBrush(QBrush(lbg))
        p.setPen(Qt.NoPen)
        p.drawRoundedRect(QRectF(lx, ly + 14, panel_w, panel_h - 14), 4, 4)

        # Right code area
        p.drawRoundedRect(QRectF(rx, ly + 14, panel_w, panel_h - 14), 4, 4)

        # Code text
        code_font = QFont("Consolas", 7)
        p.setFont(code_font)
        p.setPen(QPen(QColor(255, 255, 255, int(ia * 140))))
        p.drawText(QPointF(lx + 6, ly + 28), "1  version one")
        p.drawText(QPointF(rx + 6, ly + 28), "1  version two")

        if t < 0.55:
            return
        ba = min(1.0, (t - 0.55) / 0.25)

        # Buttons row
        btn_y = card_y + 135
        # Accept Original (outline)
        self._btn_pill(p, cx - 55, btn_y, "Accept Original",
                       QColor(_BORDER.red(), _BORDER.green(), _BORDER.blue(), int(ba * 180)))
        # Accept Incoming (filled accent)
        self._btn_pill(p, cx + 55, btn_y, "Accept Incoming",
                       QColor(_ACCENT.red(), _ACCENT.green(), _ACCENT.blue(), int(ba * 220)))

        if t > 0.75:
            ca = min(1.0, (t - 0.75) / 0.2)
            # Confirm button
            self._btn_pill(p, cx, btn_y + 28, "Confirm Merge",
                           QColor(_ACCENT.red(), _ACCENT.green(), _ACCENT.blue(), int(ca * 100)),
                           QColor(255, 255, 255, int(ca * 80)))


class _ConflictTypesIllust(_Illust):
    """Three conflict scenarios — all horizontal RL."""

    def _draw(self, p, t):
        w = self.width()
        cols = [w * 0.17, w * 0.5, w * 0.83]
        cy = 45

        # 1. Merge conflict — two branches fork horizontally
        if t > 0.05:
            a = min(1.0, (t - 0.05) / 0.25)
            fx = cols[0] + 20
            self._node(p, fx, cy, _ACCENT, r=7, alpha=int(a * 255))
            self._node(p, cols[0] - 10, cy - 18, _ACCENT, r=7, alpha=int(a * 255))
            self._node(p, cols[0] - 10, cy + 18, _INDIGO, r=7, alpha=int(a * 255))
            self._edge(p, fx, cy, cols[0] - 10, cy - 18, alpha=int(a * 120))
            self._edge(p, fx, cy, cols[0] - 10, cy + 18, alpha=int(a * 120))
            wc = QColor(_WARNING)
            wc.setAlpha(int(a * 200))
            p.setBrush(Qt.NoBrush)
            p.setPen(QPen(wc, 1.5))
            p.drawEllipse(QPointF(cols[0] - 30, cy), 8, 8)
            self._text(p, cols[0] - 30, cy + 4, "!", _WARNING, size=8, bold=True, center=True)

            self._text(p, cols[0], cy + 48, "Merge",
                       QColor(255, 255, 255, int(a * 180)), size=8, center=True)
            self._text(p, cols[0], cy + 61, "two branches",
                       QColor(255, 255, 255, int(a * 100)), size=7, center=True)
            self._text(p, cols[0], cy + 72, "edit same file",
                       QColor(255, 255, 255, int(a * 100)), size=7, center=True)

        # 2. Save conflict — horizontal with stash
        if t > 0.35:
            a = min(1.0, (t - 0.35) / 0.25)
            sxs = [cols[1] + 25, cols[1], cols[1] - 25]
            for i, sx in enumerate(sxs):
                self._node(p, sx, cy, _ACCENT, r=7, alpha=int(a * 255))
                if i > 0:
                    self._edge(p, sxs[i - 1], cy, sx, cy, alpha=int(a * 120))
            self._stash_dot(p, cols[1], cy)

            self._text(p, cols[1], cy + 48, "Save",
                       QColor(255, 255, 255, int(a * 180)), size=8, center=True)
            self._text(p, cols[1], cy + 61, "stash clashes",
                       QColor(255, 255, 255, int(a * 100)), size=7, center=True)
            self._text(p, cols[1], cy + 72, "with newer code",
                       QColor(255, 255, 255, int(a * 100)), size=7, center=True)

        # 3. Sync conflict — local/remote diverged horizontally
        if t > 0.6:
            a = min(1.0, (t - 0.6) / 0.25)
            fx = cols[2] + 20
            self._node(p, fx, cy, _ACCENT, r=7, alpha=int(a * 255))
            self._node(p, cols[2] - 10, cy - 18, _ACCENT, r=7, alpha=int(a * 255))
            self._node(p, cols[2] - 10, cy + 18, _ACCENT, r=7, alpha=int(a * 102))
            self._edge(p, fx, cy, cols[2] - 10, cy - 18, alpha=int(a * 120))
            self._edge(p, fx, cy, cols[2] - 10, cy + 18, alpha=int(a * 80))
            self._text(p, cols[2] - 28, cy - 18, "L",
                       QColor(255, 255, 255, int(a * 100)), size=7, center=True)
            self._text(p, cols[2] - 28, cy + 22, "R",
                       QColor(255, 255, 255, int(a * 100)), size=7, center=True)

            self._text(p, cols[2], cy + 48, "Sync",
                       QColor(255, 255, 255, int(a * 180)), size=8, center=True)
            self._text(p, cols[2], cy + 61, "local & remote",
                       QColor(255, 255, 255, int(a * 100)), size=7, center=True)
            self._text(p, cols[2], cy + 72, "have diverged",
                       QColor(255, 255, 255, int(a * 100)), size=7, center=True)


class _ReadyIllust(_Illust):
    def _draw(self, p, t):
        w = self.width()
        cx = w / 2
        if t > 0.2:
            a = min(1.0, (t - 0.2) / 0.4)
            r = 28
            gc = QColor(_GREEN)
            gc.setAlpha(int(a * 60))
            g = QRadialGradient(QPointF(cx, 80), r + 20)
            g.setColorAt(0, gc)
            g.setColorAt(1, QColor(0, 0, 0, 0))
            p.setBrush(QBrush(g))
            p.setPen(Qt.NoPen)
            p.drawEllipse(QPointF(cx, 80), r + 20, r + 20)

            cc = QColor(_GREEN)
            cc.setAlpha(int(a * 255))
            p.setBrush(QBrush(cc))
            p.setPen(QPen(QColor(255, 255, 255, int(a * 120)), 2))
            p.drawEllipse(QPointF(cx, 80), r, r)

            if a > 0.5:
                ca = min(1.0, (a - 0.5) / 0.5)
                p.setPen(QPen(QColor(255, 255, 255, int(ca * 255)), 3, Qt.SolidLine, Qt.RoundCap))
                p.drawLine(QPointF(cx - 10, 80), QPointF(cx - 2, 90))
                p.drawLine(QPointF(cx - 2, 90), QPointF(cx + 12, 68))

        if t > 0.6:
            a = min(1.0, (t - 0.6) / 0.3)
            self._text(p, cx, 135, "You're all set!",
                       QColor(255, 255, 255, int(a * 220)), size=12, bold=True, center=True)
            self._text(p, cx, 158, "Click any commit to get started.",
                       QColor(255, 255, 255, int(a * 130)), size=10, center=True)


# ── Stage definitions ─────────────────────────────────────────────────────────

_STAGES = [
    {
        "title": "Welcome to Evo Git",
        "body": "A visual Git client that turns your project's history into an interactive graph you can see and touch.",
        "illust": _WelcomeIllust,
    },
    {
        "title": "Getting Started",
        "body": "Click 'Track a Project' to connect a repo. You can clone from GitHub, open a local folder, or create a new repo.",
        "illust": _TrackProjectIllust,
    },
    {
        "title": "Commits",
        "body": "Each dot is a commit — a saved snapshot of your entire project at one moment. Think of it as a checkpoint you can always go back to.",
        "illust": _CommitsIllust,
    },
    {
        "title": "The Graph",
        "body": "Commits connect to form a timeline. The oldest commit is on the left, newest on the right. Lines show how one commit leads to the next.",
        "illust": _GraphIllust,
    },
    {
        "title": "What the Lines Mean",
        "body": "Different line styles tell you different things about how commits relate to each other.",
        "illust": _EdgeTypesIllust,
    },
    {
        "title": "Branches",
        "body": "A branch is a parallel line of work. You can create one to build a feature without touching the main code, then bring it back when it's ready.",
        "illust": _BranchesIllust,
    },
    {
        "title": "Tips & Flags",
        "body": "The flag on the left marks where the branch was created. The glowing dot on the right is the tip — the latest commit.",
        "illust": _TipsIllust,
    },
    {
        "title": "Commit Styles",
        "body": "Each commit's appearance tells you its status — whether it's local, pushed, remote-only, or has unsaved work.",
        "illust": _CommitTypesIllust,
    },
    {
        "title": "The Detail Panel",
        "body": "Click any commit to open a side panel showing who made it, when, and what changed. Action buttons let you do things with that commit.",
        "illust": _DetailPanelIllust,
    },
    {
        "title": "Branch & Merge",
        "body": "Create a branch to work separately, then merge it back. A merge commit ties the two lines together, combining all the changes.",
        "illust": _MergeIllust,
    },
    {
        "title": "Upload & Pull",
        "body": "Upload (push) sends your local commits to the remote so others can see them. Pull downloads new remote commits to your machine.",
        "illust": _PushPullIllust,
    },
    {
        "title": "Save Changes",
        "body": "If you have uncommitted work, 'Save Changes' stashes it as a commit so nothing is lost. The amber dot shows where unsaved changes live.",
        "illust": _StashIllust,
    },
    {
        "title": "Resolving Conflicts",
        "body": "When files clash, this dialog shows both versions side by side. Pick which to keep for each file, then confirm.",
        "illust": _ConflictUIIllust,
    },
    {
        "title": "Types of Conflicts",
        "body": "Conflicts can happen in three situations — merging branches, saving stashed changes, or syncing with remote.",
        "illust": _ConflictTypesIllust,
    },
    {
        "title": "You're Ready",
        "body": "",
        "illust": _ReadyIllust,
    },
]


# ── Dialog ────────────────────────────────────────────────────────────────────

class InstructionsDialog(QDialog):

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowFlags(Qt.Dialog | Qt.FramelessWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setFixedSize(500, 540)
        self._idx = 0
        self._illusts: list[_Illust] = []
        self._setup_ui()

    def _setup_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)

        self._card = QWidget()
        self._card.setStyleSheet(f"background: {COLORS['bg_card']}; border-radius: 12px;")
        vl = QVBoxLayout(self._card)
        vl.setContentsMargins(28, 24, 28, 24)
        vl.setSpacing(12)

        # close button
        close_row = QHBoxLayout()
        close_row.addStretch()
        close_btn = QPushButton("✕")
        close_btn.setFixedSize(28, 28)
        close_btn.setCursor(Qt.PointingHandCursor)
        close_btn.setStyleSheet(f"""
            QPushButton {{
                background: transparent; border: none;
                color: {COLORS['text_muted']}; font-size: 16px;
            }}
            QPushButton:hover {{ color: {COLORS['text_primary']}; }}
        """)
        close_btn.clicked.connect(self.reject)
        close_row.addWidget(close_btn)
        vl.addLayout(close_row)

        # header: logo + title
        header_wrap = QWidget()
        header_wrap.setMinimumHeight(35)
        header_wrap.setStyleSheet("background: transparent;")
        header_row = QHBoxLayout(header_wrap)
        header_row.setContentsMargins(0, 0, 0, 0)
        header_row.setAlignment(Qt.AlignCenter)
        header_row.setSpacing(10)
        self._header_logo = QLabel()
        pm = QPixmap(_LOGO_PATH).scaled(42, 42, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        self._header_logo.setPixmap(pm)
        self._header_logo.setFixedSize(42, 42)
        self._header_logo.setStyleSheet("background: transparent;")
        header_row.addWidget(self._header_logo)
        self._title_lbl = QLabel()
        self._title_lbl.setStyleSheet(
            f"font-size: 20px; font-weight: 700; font-family: 'Tilt Warp';"
            f" color: {COLORS['text_primary']}; background: transparent;"
        )
        header_row.addWidget(self._title_lbl)
        vl.addWidget(header_wrap)

        self._body_lbl = QLabel()
        self._body_lbl.setWordWrap(True)
        self._body_lbl.setAlignment(Qt.AlignCenter)
        self._body_lbl.setStyleSheet(
            f"font-size: 12px; color: {COLORS['text_secondary']}; background: transparent;"
        )
        self._body_lbl.setFixedHeight(50)
        vl.addWidget(self._body_lbl)

        # illustration stack
        self._stack = QStackedWidget()
        self._stack.setFixedHeight(200)
        self._stack.setStyleSheet("background: transparent;")
        for stage in _STAGES:
            illust = stage["illust"](self._stack)
            self._illusts.append(illust)
            self._stack.addWidget(illust)
        vl.addWidget(self._stack)

        vl.addSpacing(4)

        # dots
        dots_row = QHBoxLayout()
        dots_row.setAlignment(Qt.AlignCenter)
        dots_row.setSpacing(6)
        self._dots: list[QLabel] = []
        for _ in _STAGES:
            dot = QLabel()
            dot.setFixedSize(8, 8)
            self._dots.append(dot)
            dots_row.addWidget(dot)
        vl.addLayout(dots_row)

        vl.addSpacing(4)

        # buttons
        btn_row = QHBoxLayout()
        btn_row.setSpacing(8)

        self._back_btn = QPushButton("Back")
        self._back_btn.setFixedHeight(38)
        self._back_btn.setMinimumWidth(80)
        self._back_btn.setCursor(Qt.PointingHandCursor)
        self._back_btn.setStyleSheet(f"""
            QPushButton {{
                background: transparent; border: 1px solid {COLORS['border']};
                border-radius: 8px; color: {COLORS['text_secondary']};
                font-size: 13px; font-weight: 600; font-family: 'Tilt Warp'; padding: 0 16px;
            }}
            QPushButton:hover {{ border-color: {COLORS['text_secondary']}; }}
        """)
        self._back_btn.clicked.connect(self._go_back)
        btn_row.addWidget(self._back_btn)

        btn_row.addStretch()

        self._step_lbl = QLabel()
        self._step_lbl.setStyleSheet(
            f"font-size: 11px; color: {COLORS['text_muted']}; background: transparent;"
            f" font-family: 'Tilt Warp';"
        )
        btn_row.addWidget(self._step_lbl)

        btn_row.addStretch()

        self._next_btn = QPushButton("Next")
        self._next_btn.setFixedHeight(38)
        self._next_btn.setMinimumWidth(80)
        self._next_btn.setCursor(Qt.PointingHandCursor)
        self._next_btn.setStyleSheet(f"""
            QPushButton {{
                background: {COLORS['accent']}; border: none;
                border-radius: 8px; color: {COLORS['text_on_accent']};
                font-size: 13px; font-weight: 700; font-family: 'Tilt Warp'; padding: 0 16px;
            }}
            QPushButton:hover {{ background: {COLORS['accent_hover']}; }}
        """)
        self._next_btn.clicked.connect(self._go_next)
        btn_row.addWidget(self._next_btn)

        vl.addLayout(btn_row)
        root.addWidget(self._card)

    def _show_stage(self, idx: int):
        self._idx = idx
        stage = _STAGES[idx]
        self._title_lbl.setText(stage["title"])
        self._body_lbl.setText(stage["body"])
        self._back_btn.setVisible(idx > 0)
        self._next_btn.setText("Close" if idx == len(_STAGES) - 1 else "Next")
        self._step_lbl.setText(f"{idx + 1} / {len(_STAGES)}")
        self._stack.setCurrentIndex(idx)
        for i, dot in enumerate(self._dots):
            c = COLORS['accent'] if i == idx else COLORS['border']
            dot.setStyleSheet(f"background: {c}; border-radius: 4px;")
        self._illusts[idx].animate()

    def _go_back(self):
        if self._idx > 0:
            self._show_stage(self._idx - 1)

    def _go_next(self):
        if self._idx < len(_STAGES) - 1:
            self._show_stage(self._idx + 1)
        else:
            self.accept()

    def showEvent(self, ev):
        super().showEvent(ev)
        self._show_stage(0)

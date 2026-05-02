from __future__ import annotations

import math
import threading
from typing import Optional

from PyQt5.QtCore import Qt, QRectF, QPointF, QEvent, pyqtSignal
from PyQt5.QtGui import (
    QPainter, QColor, QPen, QBrush, QFont, QFontMetrics,
    QPainterPath, QRadialGradient, QPolygonF, QPixmap,
)
from PyQt5.QtWidgets import (
    QGraphicsView, QGraphicsScene, QGraphicsObject,
    QGraphicsPathItem, QGraphicsItem, QGraphicsSimpleTextItem,
    QGraphicsPolygonItem, QWidget,
)

from core.git_tracker import CommitInfo
from styles.theme import COLORS

# ── Layout ────────────────────────────────────────────────────────────────────
NODE_R   = 10
START_R  = 14
BADGE_R  = 9        # contributor avatar badge radius
LANE_W   = 100      # wider — leaves room for branch label pills
ROW_H    = 72
H_PAD    = 80
V_PAD    = 60
CANVAS_PAD = 800    # pan boundary — how far past the content edge the user can scroll

ZOOM_MIN  = 0.5
ZOOM_MAX  = 1.5
ZOOM_STEP = 1.10

# ── Branch colours ─────────────────────────────────────────────────────────────
MAIN_COLOR = COLORS["accent"]   # updated by apply_theme(); read via _lane_color()

PALETTE = [
    "#6366f1",  # indigo
    "#f59e0b",  # amber
    "#ef4444",  # red
    "#8b5cf6",  # violet
    "#06b6d4",  # cyan
    "#f97316",  # orange
    "#ec4899",  # pink
    "#14b8a6",  # teal
    "#84cc16",  # lime
    "#a78bfa",  # purple
]


def _lane_color(lane_idx: int) -> str:
    return COLORS["accent"] if lane_idx == 0 else PALETTE[(lane_idx - 1) % len(PALETTE)]


# ── Lane algorithm ─────────────────────────────────────────────────────────────

def _compute_lanes(
    commits: list[CommitInfo],
    branch_tip_map: dict[str, list[str]],
) -> tuple[dict[str, int], dict[int, str]]:
    """
    Classic streaming lane algorithm — the same approach used by git log --graph.

    Requires commits to be in TOPOLOGICAL ORDER (children before parents),
    which graph_commits() guarantees via --topo-order.

    How it works
    ------------
    • We maintain a list of "open lanes".  Each slot holds the SHA that lane
      is currently waiting to see (its next expected commit).
    • For each commit we find which lane is expecting it, assign it there,
      then update that lane to expect the commit's first parent.
    • Merge commits open extra lanes for their additional parents.
    • When multiple lanes converge on the same SHA (a branch was merged),
      we free the stale duplicates so their slots can be reused.
    • Lane 0 is pre-seeded with the primary (main/master) tip so it
      always gets the green accent colour.
    """
    if not commits:
        return {}, {}

    # ── Identify primary branch ───────────────────────────────────────────
    primary = next(
        (n for names in branch_tip_map.values() for n in names if n in ("main", "master")),
        None,
    )

    primary_tip = next(
        (sha for sha, names in branch_tip_map.items() if primary and primary in names),
        None,
    )

    # ── Pre-seed ALL branch tips into dedicated lanes ─────────────────────
    # This is the key fix: if only the primary is pre-seeded, feature commits
    # that appear after a merge point (no lane waiting for them) get thrown
    # into a fresh lane — different from where the pre-merge feature commits
    # landed — so the same branch visually splits in two.
    # By pre-seeding every branch tip upfront each branch owns one lane for
    # the entire traversal.
    seen_tips: set[str] = set()
    ordered_tips: list[str] = []

    if primary_tip:
        ordered_tips.append(primary_tip)
        seen_tips.add(primary_tip)

    for sha in branch_tip_map:
        if sha not in seen_tips:
            ordered_tips.append(sha)
            seen_tips.add(sha)

    lanes: list[Optional[str]] = list(ordered_tips)   # lane i starts waiting for ordered_tips[i]

    assignment: dict[str, int] = {}

    for commit in commits:
        sha = commit.sha

        # Which lane is waiting for this commit?
        lane_idx = next((i for i, s in enumerate(lanes) if s == sha), None)

        if lane_idx is None:
            # Not expected — reuse first free slot or open a new lane
            free = next((i for i, s in enumerate(lanes) if s is None), None)
            if free is not None:
                lane_idx = free
            else:
                lane_idx = len(lanes)
                lanes.append(None)

        assignment[sha] = lane_idx

        # Free stale entries: when a branch merges into another, multiple
        # lanes can end up pointing at the same parent SHA — clean them up
        for i in range(len(lanes)):
            if i != lane_idx and lanes[i] == sha:
                lanes[i] = None

        parents = commit.parents
        if not parents:
            lanes[lane_idx] = None          # root commit — close this lane
        else:
            lanes[lane_idx] = parents[0]    # continue tracking first parent
            for p in parents[1:]:           # open extra lanes for merge parents
                if not any(s == p for s in lanes):
                    free = next((i for i, s in enumerate(lanes) if s is None), None)
                    if free is not None:
                        lanes[free] = p
                    else:
                        lanes.append(p)

    # ── Build lane_branch: lane_index -> display name ─────────────────────
    # Use ordered_tips (which mirrors the lane pre-seeding order) so lane 0
    # always maps to the primary branch regardless of where the tip ended up.
    lane_branch: dict[int, str] = {}
    for lane_idx, tip_sha in enumerate(ordered_tips):
        names = branch_tip_map.get(tip_sha, [])
        if names:
            preferred = next((n for n in names if n == primary), names[0])
            lane_branch[lane_idx] = preferred

    # Fallback for any dynamically-opened lanes beyond the pre-seeded set
    for sha, lane_idx in assignment.items():
        if lane_idx not in lane_branch:
            lane_branch[lane_idx] = branch_tip_map.get(sha, [""])[0] or f"branch-{lane_idx}"

    lane_branch.setdefault(0, primary or "main")

    return assignment, lane_branch


# ── Graphics items ─────────────────────────────────────────────────────────────

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

        self._font = QFont("Inter, Segoe UI", 10)
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

        # Semi-transparent fill
        bg = QColor(self._color)
        bg.setAlpha(28)
        border = QColor(self._color)
        border.setAlpha(160)

        painter.setBrush(QBrush(bg))
        painter.setPen(QPen(border, 1))
        painter.drawRoundedRect(
            QRectF(0, -self._h / 2, self._w, self._h), r, r,
        )

        # Branch name
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

    def __init__(self, commit: CommitInfo, color: str, is_start: bool = False, is_local_only: bool = False, is_head: bool = False):
        super().__init__()
        self._commit        = commit
        self._color         = QColor(color)
        self._is_start      = is_start
        self._is_local_only = is_local_only
        self._is_head       = is_head
        self._r             = START_R if is_start else NODE_R
        self._hovered       = False
        self._selected      = False

        self.setAcceptHoverEvents(True)
        self.setCursor(Qt.PointingHandCursor)
        self.setZValue(2)

    def boundingRect(self) -> QRectF:
        r = self._r + 10
        top = -r - (28 if self._is_head else 0)
        return QRectF(-r, top, r * 2, r * 2 + (28 if self._is_head else 0))

    def paint(self, painter: QPainter, _option, _widget):
        painter.setRenderHint(QPainter.Antialiasing)
        r = self._r
        c = self._color

        # Subtle glow on hover / select
        if self._hovered or self._selected:
            grad = QRadialGradient(QPointF(0, 0), r + 10)
            glow = QColor(c)
            glow.setAlpha(60)
            grad.setColorAt(0, glow)
            grad.setColorAt(1, QColor(0, 0, 0, 0))
            painter.setPen(Qt.NoPen)
            painter.setBrush(QBrush(grad))
            painter.drawEllipse(QPointF(0, 0), r + 10, r + 10)

        if self._is_local_only:
            # Hollow — colored border, no fill
            painter.setBrush(Qt.NoBrush)
            painter.setPen(QPen(c, 2.5))
        else:
            # Solid — colored fill, soft white border
            border = QColor("white")
            border.setAlpha(120)
            painter.setBrush(QBrush(c))
            painter.setPen(QPen(border, 1.5))
        painter.drawEllipse(QPointF(0, 0), r, r)

        # Selection ring
        if self._selected:
            painter.setBrush(Qt.NoBrush)
            painter.setPen(QPen(QColor("white"), 2))
            painter.drawEllipse(QPointF(0, 0), r + 4, r + 4)

        # HEAD pin
        if self._is_head:
            accent = QColor(COLORS["accent"])
            grad = QRadialGradient(QPointF(0, 0), r + 18)
            glow = QColor(accent); glow.setAlpha(80)
            grad.setColorAt(0, glow); grad.setColorAt(1, QColor(0, 0, 0, 0))
            painter.setPen(Qt.NoPen)
            painter.setBrush(QBrush(grad))
            painter.drawEllipse(QPointF(0, 0), r + 18, r + 18)
            painter.setBrush(Qt.NoBrush)
            painter.setPen(QPen(accent, 2.5))
            painter.drawEllipse(QPointF(0, 0), r + 6, r + 6)
            white = QColor("white"); white.setAlpha(200)
            painter.setPen(QPen(white, 1.5))
            painter.drawEllipse(QPointF(0, 0), r + 9, r + 9)
            pin_tip_y = -r - 4; pin_base_y = -r - 22
            painter.setPen(QPen(accent, 2))
            painter.drawLine(QPointF(0, pin_base_y + 10), QPointF(0, pin_tip_y))
            pin = QPolygonF([QPointF(-8, pin_base_y), QPointF(8, pin_base_y), QPointF(0, pin_base_y + 10)])
            painter.setBrush(QBrush(accent)); painter.setPen(Qt.NoPen)
            painter.drawPolygon(pin)

        # Start node — flag pole + triangle above in branch colour
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
    """
    Diagonal line for cross-lane connections.
    dashed=False  → solid   (merge)
    dashed=True   → dashed  (branch creation / divergence)
    """

    def __init__(
        self,
        cx: float, cy: float,
        px: float, py: float,
        color: str,
        dashed: bool = False,
    ):
        path = QPainterPath()
        path.moveTo(cx, cy)
        path.lineTo(px, py)
        super().__init__(path)

        white = QColor("white")
        white.setAlpha(140)
        style = Qt.SolidLine if dashed else Qt.DotLine
        self.setPen(QPen(white, 1.5, style, Qt.RoundCap, Qt.RoundJoin))
        self.setBrush(QBrush(Qt.NoBrush))
        self.setZValue(1)
        self.setAcceptedMouseButtons(Qt.NoButton)


class _ContributorBadge(QGraphicsObject):
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
            grad = QRadialGradient(QPointF(0, 0), r + 8)
            glow = QColor(c)
            glow.setAlpha(80)
            grad.setColorAt(0, glow)
            grad.setColorAt(1, QColor(0, 0, 0, 0))
            painter.setPen(Qt.NoPen)
            painter.setBrush(QBrush(grad))
            painter.drawEllipse(QPointF(0, 0), r + 8, r + 8)

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
            font = QFont("Inter", max(6, r // 2), QFont.Bold)
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


# ── Minimap ────────────────────────────────────────────────────────────────────

class MiniMap(QWidget):
    """
    Bird's-eye view of the commit graph.
    White box = current viewport. Click/drag to pan the canvas.
    """

    MAP_W    = 150
    MAP_H    = 160
    _PAD     = 10   # inner margin so dots aren't clipped at edges

    def __init__(self, canvas: "SpatialCanvas", parent=None):
        super().__init__(parent)
        self._canvas = canvas
        self.setFixedSize(self.MAP_W, self.MAP_H)
        self.setCursor(Qt.PointingHandCursor)
        canvas.viewport_changed.connect(self.update)

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

        # Background + border
        bg = QColor(COLORS["bg_card"])
        bg.setAlpha(230)
        p.setBrush(QBrush(bg))
        p.setPen(QPen(QColor(COLORS["border"]), 1))
        p.drawRoundedRect(0, 0, self.MAP_W, self.MAP_H, 8, 8)

        canvas = self._canvas
        if not canvas._positions or not canvas._content_rect.isValid():
            p.end()
            return

        # Commit dots
        p.setPen(Qt.NoPen)
        for sha, (sx, sy) in canvas._positions.items():
            mx, my = self._to_map(sx, sy)
            color = QColor(canvas._node_colors.get(sha, COLORS["accent"]))
            color.setAlpha(200)
            p.setBrush(QBrush(color))
            p.drawEllipse(QPointF(mx, my), 2.5, 2.5)

        # Viewport box
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


# ── Canvas view ────────────────────────────────────────────────────────────────

class SpatialCanvas(QGraphicsView):
    """
    Infinite panning + zoom canvas.

    Pan  — click-drag on the background.
    Zoom — scroll wheel (anchored to cursor).
    Select — click a commit node.
    """

    commit_clicked            = pyqtSignal(object)   # CommitInfo
    zoom_changed              = pyqtSignal(int)      # zoom percentage (100 = 1:1)
    contributor_badge_clicked = pyqtSignal(str)      # login
    viewport_changed          = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._scene = QGraphicsScene(self)
        self.setScene(self._scene)

        self._scene.setBackgroundBrush(self._make_grid_brush())
        self.setStyleSheet("border: none; background: transparent;")
        self.setRenderHint(QPainter.Antialiasing)
        self.setDragMode(QGraphicsView.NoDrag)
        self.setTransformationAnchor(QGraphicsView.AnchorUnderMouse)
        self.setResizeAnchor(QGraphicsView.AnchorViewCenter)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setFrameShape(self.NoFrame)

        self.viewport().setAttribute(Qt.WA_AcceptTouchEvents, True)
        self.grabGesture(Qt.PinchGesture)
        self.setFocusPolicy(Qt.StrongFocus)

        self._panning = False
        self._pan_origin = QPointF()
        self._gesture_active = False
        self._nodes: dict[str, CommitNode] = {}
        self._selected_sha: Optional[str] = None
        self._badges: list[_ContributorBadge] = []
        self._commits: list = []
        self._positions: dict[str, tuple[float, float]] = {}
        self._node_colors: dict[str, str] = {}
        self._content_rect: QRectF = QRectF()
        self._you_shas: set = set()
        self._author_items: dict[str, QGraphicsSimpleTextItem] = {}
        self._head_sha: str = ""

    # ── Helpers ───────────────────────────────────────────────────────────────

    @staticmethod
    def _make_grid_brush(cell: int = 40) -> QBrush:
        """Creates a tiled pixel-map with a subtle dot-grid pattern."""
        from PyQt5.QtGui import QPixmap
        pm = QPixmap(cell, cell)
        pm.fill(QColor(COLORS["bg_primary"]))
        p = QPainter(pm)
        line_color = QColor(COLORS["border"])
        line_color.setAlpha(80)
        p.setPen(QPen(line_color, 1))
        # Right edge (vertical line)
        p.drawLine(cell - 1, 0, cell - 1, cell - 1)
        # Bottom edge (horizontal line)
        p.drawLine(0, cell - 1, cell - 1, cell - 1)
        p.end()
        return QBrush(pm)

    # ── Public ────────────────────────────────────────────────────────────────

    def load_graph(
        self,
        commits: list[CommitInfo],
        branch_tip_map: dict[str, list[str]],
        you_shas: set = None,
        local_only_branches: set = None,
        unpushed_shas: set = None,
        head_sha: str = "",
    ):
        self._scene.clear()
        self._nodes.clear()
        self._badges.clear()   # scene.clear() already removes items
        self._positions.clear()
        self._node_colors.clear()
        self._author_items.clear()
        self._content_rect = QRectF()
        self._selected_sha = None
        self._commits = commits
        self._you_shas            = you_shas            or set()
        self._local_only_branches = local_only_branches or set()
        self._unpushed_shas       = unpushed_shas       or set()
        self._head_sha            = head_sha

        if not commits:
            return

        lane_map, lane_branch = _compute_lanes(commits, branch_tip_map)

        # Stamp each commit's branch field so the detail panel shows it correctly
        for commit in commits:
            commit.branch = lane_branch.get(lane_map.get(commit.sha, 0), "")

        # ── Positions ──────────────────────────────────────────────────────
        positions: dict[str, tuple[float, float]] = {}
        for i, commit in enumerate(commits):
            lane = lane_map.get(commit.sha, 0)
            x = H_PAD + lane * LANE_W
            y = V_PAD + i * ROW_H
            positions[commit.sha] = (x, y)
        self._positions = positions

        # Content rect for minimap
        if positions:
            xs = [x for x, y in positions.values()]
            ys = [y for x, y in positions.values()]
            self._content_rect = QRectF(
                min(xs) - 30, min(ys) - 30,
                max(xs) - min(xs) + 60, max(ys) - min(ys) + 60,
            )

        # start_shas built after lane_bottom is computed (see step 2)

        # ── 1. Lane spines ─────────────────────────────────────────────────
        lane_points: dict[int, list[tuple[float, float]]] = {}
        for commit in commits:
            lane = lane_map.get(commit.sha, 0)
            cx, cy = positions[commit.sha]
            lane_points.setdefault(lane, []).append((cx, cy))

        for lane, pts in lane_points.items():
            if len(pts) < 2:
                continue
            pts.sort(key=lambda p: p[1])
            path = QPainterPath()
            path.moveTo(pts[0][0], pts[0][1])
            for x, y in pts[1:]:
                path.lineTo(x, y)
            spine = QGraphicsPathItem(path)
            white = QColor("white")
            white.setAlpha(120)
            branch_name  = lane_branch.get(lane, "")
            is_local     = branch_name in self._local_only_branches
            raw_color    = _lane_color(lane) if is_local else "#6b7280"
            lane_color   = QColor(raw_color)
            lane_color.setAlpha(160)
            spine.setPen(QPen(lane_color, 2, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
            spine.setBrush(QBrush(Qt.NoBrush))
            spine.setZValue(1)
            spine.setAcceptedMouseButtons(Qt.NoButton)
            self._scene.addItem(spine)


        # ── 2. Cross-lane edges ────────────────────────────────────────────
        # Solid diagonal  → merge    (merge commit's extra parents)
        # Dashed diagonal → creation (exactly ONE per branch/lane — drawn only
        #                             from the bottommost commit of that lane,
        #                             i.e. the very first commit on the branch)

        # Find the bottommost (largest y = oldest) commit per lane
        lane_bottom: dict[int, CommitInfo] = {}
        for commit in commits:
            lane = lane_map.get(commit.sha, 0)
            _, cy = positions[commit.sha]
            existing = lane_bottom.get(lane)
            if existing is None or cy > positions[existing.sha][1]:
                lane_bottom[lane] = commit

        # Creation line: one per non-primary lane, from its bottommost commit.
        # If the parent is visible and cross-lane → draw to the parent.
        # If the parent is outside the fetched window → draw a short line
        # toward lane 0 at the next row, so the oldest node always has a line.
        lane_creation: dict[int, tuple[float, float, float, float]] = {}
        for lane, commit in lane_bottom.items():
            if lane == 0:        # primary branch has no creation line
                continue
            if not commit.parents:
                continue
            cx, cy = positions[commit.sha]
            p_sha = commit.parents[0]

            if p_sha in positions:
                parent_lane = lane_map.get(p_sha, 0)
                px, py = positions[p_sha]
                if parent_lane != lane:
                    lane_creation[lane] = (cx, cy, px, py)
            else:
                # Parent beyond visible range — point toward lane 0 one row below
                px = H_PAD          # lane 0 x-centre
                py = cy + ROW_H
                lane_creation[lane] = (cx, cy, px, py)

        # Pass B: draw merge edges (solid + arrowhead) + creation edges (dashed)
        for commit in commits:
            cx, cy = positions[commit.sha]
            commit_lane = lane_map.get(commit.sha, 0)
            for p_sha in commit.parents[1:]:
                if p_sha not in positions:
                    continue
                parent_lane = lane_map.get(p_sha, 0)
                if parent_lane != commit_lane:
                    px, py = positions[p_sha]
                    edge = EdgeItem(cx, cy, px, py, _lane_color(parent_lane), dashed=False)
                    self._scene.addItem(edge)

                    # Arrowhead at the merge-commit end, pointing from feature → main
                    dx, dy = cx - px, cy - py
                    length = math.hypot(dx, dy)
                    if length > 0:
                        ux, uy = dx / length, dy / length
                        # Tip just outside the merge commit node
                        tip_x = cx - ux * (NODE_R + 2)
                        tip_y = cy - uy * (NODE_R + 2)
                        sz = 7
                        l_x = tip_x - ux * sz - uy * (sz / 2)
                        l_y = tip_y - uy * sz + ux * (sz / 2)
                        r_x = tip_x - ux * sz + uy * (sz / 2)
                        r_y = tip_y - uy * sz - ux * (sz / 2)
                        poly = QPolygonF([
                            QPointF(tip_x, tip_y),
                            QPointF(l_x, l_y),
                            QPointF(r_x, r_y),
                        ])
                        arrow = QGraphicsPolygonItem(poly)
                        arrow.setBrush(QBrush(QColor(_lane_color(parent_lane))))
                        arrow.setPen(QPen(Qt.NoPen))
                        arrow.setZValue(3)
                        arrow.setAcceptedMouseButtons(Qt.NoButton)
                        self._scene.addItem(arrow)

        for lane, (cx, cy, px, py) in lane_creation.items():
            edge = EdgeItem(cx, cy, px, py, _lane_color(lane), dashed=True)
            self._scene.addItem(edge)

        # Oldest commit of each lane gets the start flag
        start_shas = {c.sha for c in lane_bottom.values()}

        # ── 3. Nodes ───────────────────────────────────────────────────────
        for commit in commits:
            cx, cy        = positions[commit.sha]
            lane          = lane_map.get(commit.sha, 0)
            branch_name   = lane_branch.get(lane, "")
            is_local      = (branch_name in self._local_only_branches
                             or commit.sha in self._unpushed_shas)
            color         = _lane_color(lane)
            self._node_colors[commit.sha] = color
            node  = CommitNode(commit, color,
                               is_start=commit.sha in start_shas,
                               is_local_only=is_local,
                               is_head=commit.sha == self._head_sha)
            node.setPos(cx, cy)
            node.clicked.connect(self._on_node_clicked)
            self._scene.addItem(node)
            self._nodes[commit.sha] = node

        # ── 4. Branch labels ───────────────────────────────────────────────
        # One label per lane, placed at the topmost (newest) commit in that
        # lane.  Using lane_branch / _lane_color directly avoids the
        # lane_map.get(sha, 0) fallback that caused wrong colours.
        lane_top: dict[int, tuple[float, float]] = {}
        for commit in commits:
            lane = lane_map.get(commit.sha, 0)
            cx, cy = positions[commit.sha]
            if lane not in lane_top or cy < lane_top[lane][1]:
                lane_top[lane] = (cx, cy)

        for lane, (cx, cy) in lane_top.items():
            name = lane_branch.get(lane, "")
            if not name:
                continue
            color = _lane_color(lane)
            label = BranchLabel(name, color)
            label.setPos(cx + NODE_R + 10, cy)
            self._scene.addItem(label)

        # ── 5. Commit info text (date + author) ────────────────────────────
        date_font   = QFont("Inter, Segoe UI", 8)
        author_font = QFont("Inter, Segoe UI", 8)
        date_color   = QBrush(QColor(COLORS["text_secondary"]))
        author_color = QBrush(QColor(COLORS["text_muted"]))

        for commit in commits:
            cx, cy = positions[commit.sha]
            text_x = cx + NODE_R + 14
            d = commit.date
            date_str = f"{d.day} {d.strftime('%b')} {d.year}  {d.strftime('%H:%M')}"

            date_item = QGraphicsSimpleTextItem(date_str)
            date_item.setFont(date_font)
            date_item.setBrush(date_color)
            date_item.setPos(text_x, cy - date_item.boundingRect().height() / 2 - 7)
            date_item.setAcceptedMouseButtons(Qt.NoButton)
            date_item.setZValue(2)
            self._scene.addItem(date_item)

            raw_author = "You" if commit.sha in self._you_shas else commit.author
            author = raw_author if len(raw_author) <= 22 else raw_author[:20] + "…"
            auth_item = QGraphicsSimpleTextItem(author)
            auth_item.setFont(author_font)
            auth_item.setBrush(author_color)
            auth_item.setPos(text_x, cy - auth_item.boundingRect().height() / 2 + 7)
            auth_item.setAcceptedMouseButtons(Qt.NoButton)
            auth_item.setZValue(2)
            self._scene.addItem(auth_item)
            self._author_items[commit.sha] = auth_item


        # ── Scene rect ─────────────────────────────────────────────────────
        max_lane = max(lane_map.values(), default=0)
        content_w = H_PAD * 2 + max_lane * LANE_W + 300
        content_h = V_PAD * 2 + len(commits) * ROW_H + 100
        self._scene.setSceneRect(
            -CANVAS_PAD, -CANVAS_PAD,
            content_w + CANVAS_PAD * 2,
            content_h + CANVAS_PAD * 2,
        )
        self.centerOn(H_PAD, V_PAD)

    def refresh_you_labels(self, you_shas: set):
        """Update author text labels to show 'You' for the given commit SHAs."""
        self._you_shas = you_shas
        for sha, item in self._author_items.items():
            commit = next((c for c in self._commits if c.sha == sha), None)
            if commit is None:
                continue
            raw = "You" if sha in you_shas else commit.author
            item.setText(raw if len(raw) <= 22 else raw[:20] + "…")

    def load_contributor_avatars(self, badge_data: list[dict]):
        """Place avatar badges for each contributor at their latest commit.

        badge_data: [{login, avatar_url, sha, color}, ...]
        """
        for badge in self._badges:
            self._scene.removeItem(badge)
        self._badges.clear()

        for entry in badge_data:
            sha        = entry.get("sha", "")
            login      = entry.get("login", "")
            avatar_url = entry.get("avatar_url", "")
            color      = entry.get("color", "#6366f1")

            if not sha or sha not in self._nodes:
                continue

            node  = self._nodes[sha]
            badge = _ContributorBadge(login, color)
            badge.setPos(node.x(), node.y() - NODE_R - 10 - BADGE_R)
            badge.clicked.connect(self.contributor_badge_clicked)
            self._scene.addItem(badge)
            self._badges.append(badge)

            if avatar_url:
                threading.Thread(
                    target=self._fetch_badge_avatar,
                    args=(badge, avatar_url),
                    daemon=True,
                ).start()

    def set_head_sha(self, sha: str):
        if sha == self._head_sha:
            return
        old = self._nodes.get(self._head_sha)
        if old:
            old.set_head(False)
        self._head_sha = sha
        new = self._nodes.get(sha)
        if new:
            new.set_head(True)

    def jump_to_commit(self, sha: str):
        """Select a commit node and scroll to it."""
        if sha not in self._nodes:
            return
        node = self._nodes[sha]
        if self._selected_sha and self._selected_sha in self._nodes:
            self._nodes[self._selected_sha].set_selected(False)
        self._selected_sha = sha
        node.set_selected(True)
        self.commit_clicked.emit(node._commit)
        self.centerOn(node.scenePos())

    def reset_zoom(self):
        self.resetTransform()
        self._emit_zoom()

    def zoom_in(self):
        self._apply_zoom(ZOOM_STEP)

    def zoom_out(self):
        self._apply_zoom(1.0 / ZOOM_STEP)

    @property
    def zoom_pct(self) -> int:
        return round(self.transform().m11() * 100)

    # ── Gesture (pinch) ───────────────────────────────────────────────────

    def event(self, event):
        if event.type() == QEvent.Gesture:
            pinch = event.gesture(Qt.PinchGesture)
            if pinch:
                state = pinch.state()
                self._gesture_active = (state != Qt.GestureFinished
                                        and state != Qt.GestureCanceled)
                factor = pinch.scaleFactor()
                if factor and factor != 1.0:
                    self._apply_zoom(factor, anchor=QGraphicsView.AnchorViewCenter)
            event.accept()
            return True
        return super().event(event)

    # ── Zoom ──────────────────────────────────────────────────────────────

    def wheelEvent(self, event):
        if event.angleDelta().y() == 0:
            return
        zoom_in = event.angleDelta().y() > 0
        self._apply_zoom(ZOOM_STEP if zoom_in else 1.0 / ZOOM_STEP)
        event.accept()

    def _apply_zoom(self, factor: float, anchor=QGraphicsView.AnchorUnderMouse):
        current = self.transform().m11()
        new_scale = current * factor
        if new_scale < ZOOM_MIN or new_scale > ZOOM_MAX:
            return
        prev_anchor = self.transformationAnchor()
        self.setTransformationAnchor(anchor)
        self.scale(factor, factor)
        self.setTransformationAnchor(prev_anchor)
        self._emit_zoom()

    def _emit_zoom(self):
        self.zoom_changed.emit(self.zoom_pct)
        self.viewport_changed.emit()

    def scrollContentsBy(self, dx: int, dy: int):
        super().scrollContentsBy(dx, dy)
        self.viewport_changed.emit()

    # ── Pan ───────────────────────────────────────────────────────────────

    def mousePressEvent(self, event):
        if self._gesture_active:
            event.ignore()
            return
        item = self.itemAt(event.pos())
        if isinstance(item, (CommitNode, _ContributorBadge)):
            super().mousePressEvent(event)
        elif event.button() == Qt.LeftButton:
            self._panning = True
            self._pan_origin = event.pos()
            self.setCursor(Qt.ClosedHandCursor)
            event.accept()
        else:
            super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._panning:
            delta = event.pos() - self._pan_origin
            self._pan_origin = event.pos()
            self.horizontalScrollBar().setValue(
                self.horizontalScrollBar().value() - delta.x()
            )
            self.verticalScrollBar().setValue(
                self.verticalScrollBar().value() - delta.y()
            )
            event.accept()
        else:
            super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if self._panning and event.button() == Qt.LeftButton:
            self._panning = False
            self.setCursor(Qt.ArrowCursor)
            event.accept()
        else:
            super().mouseReleaseEvent(event)

    # ── Internal ──────────────────────────────────────────────────────────

    @staticmethod
    def _fetch_badge_avatar(badge: _ContributorBadge, url: str):
        try:
            import requests
            resp = requests.get(url, timeout=10)
            if resp.status_code == 200:
                pm = QPixmap()
                pm.loadFromData(resp.content)
                if not pm.isNull():
                    badge.set_pixmap(pm)
        except Exception:
            pass

    def keyPressEvent(self, event):
        key = event.key()
        if key in (Qt.Key_Up, Qt.Key_Down) and self._commits:
            if self._selected_sha:
                idx = next((i for i, c in enumerate(self._commits) if c.sha == self._selected_sha), None)
            else:
                idx = None

            if idx is None:
                target = 0
            elif key == Qt.Key_Up:
                target = max(idx - 1, 0)
            else:
                target = min(idx + 1, len(self._commits) - 1)

            if idx != target:
                self.jump_to_commit(self._commits[target].sha)
            event.accept()
            return
        super().keyPressEvent(event)

    def _on_node_clicked(self, commit: CommitInfo):
        if self._selected_sha and self._selected_sha in self._nodes:
            self._nodes[self._selected_sha].set_selected(False)
        self._selected_sha = commit.sha
        self._nodes[commit.sha].set_selected(True)
        self.commit_clicked.emit(commit)

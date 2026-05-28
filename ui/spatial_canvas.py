from __future__ import annotations

import math
import threading
from typing import Optional

from PyQt5.QtCore import Qt, QRectF, QPointF, QEvent, pyqtSignal, QTimer
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

# ── Orientation ───────────────────────────────────────────────────────────────
ORIENT_TB = "TB"   # top → bottom  (newest at top)
ORIENT_BT = "BT"   # bottom → top  (oldest at top)
ORIENT_LR = "LR"   # left → right  (oldest at left)
ORIENT_RL = "RL"   # right → left  (newest at left)

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

def _branch_base(name: str) -> str:
    """Strip remote-tracking prefixes to get the logical branch name.

    e.g. "origin/Zen" → "Zen", "refs/remotes/origin/Zen" → "Zen"
    """
    for pfx in ("refs/remotes/origin/", "origin/", "refs/heads/"):
        name = name.removeprefix(pfx)
    return name


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

    # When multiple tips share the same branch name (local ahead of remote),
    # pick the topologically newest one (lowest index = child before parent).
    commit_index = {c.sha: i for i, c in enumerate(commits)}
    if primary:
        primary_candidates = [sha for sha, names in branch_tip_map.items()
                              if primary in names]
        primary_tip = min(primary_candidates,
                          key=lambda s: commit_index.get(s, 10**9),
                          default=None)
    else:
        primary_tip = None

    # ── Seed only lane 0 with the primary tip; allocate all others lazily ─
    # Branches get a lane only when first encountered — either as a merge
    # parent (parents[1:] loop below) or as an unmerged tip that appears
    # early in topo order and hits the "not expected" path.
    # This keeps lane indices compact so merge lines span only as many lanes
    # as there are concurrently active branches, not the total branch count.
    lanes: list[Optional[str]] = []
    if primary_tip:
        lanes.append(primary_tip)

    lane_branch: dict[int, str] = {}
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

        # Record branch name when a branch tip is first assigned to a lane
        if sha in branch_tip_map and lane_idx not in lane_branch:
            names = branch_tip_map[sha]
            preferred = next((n for n in names if n == primary), names[0])
            lane_branch[lane_idx] = preferred

        # Free stale entries: when a branch merges into another, multiple
        # lanes can end up pointing at the same parent SHA — clean them up
        for i in range(len(lanes)):
            if i != lane_idx and lanes[i] == sha:
                lanes[i] = None

        parents = commit.parents
        if not parents:
            lanes[lane_idx] = None
        else:
            parent0 = parents[0]
            # If the first parent is an unprocessed branch tip, don't let the
            # current lane inherit it — that would place two different branches
            # in the same lane.  Terminate this lane and open a fresh lane for
            # the parent tip so each branch keeps its own dedicated lane.
            if parent0 in branch_tip_map and parent0 not in assignment:
                p_names = branch_tip_map[parent0]
                current_branch = lane_branch.get(lane_idx, "")
                # If the parent tip is the remote-tracking copy of this lane's
                # branch (e.g. local "Zen" → "origin/Zen"), keep them in the
                # SAME lane.  Splitting them puts local and remote commits on
                # different lanes, causing the local tip to get a spurious
                # start flag.  Only split for genuinely different branches.
                if any(_branch_base(n) == _branch_base(current_branch) for n in p_names):
                    lanes[lane_idx] = parent0   # same logical branch — stay in lane
                else:
                    lanes[lane_idx] = None   # different branch — close this lane
                    if not any(s == parent0 for s in lanes):
                        new_lane_idx = len(lanes)
                        lanes.append(parent0)
                        p_pref = next((n for n in p_names if n == primary), p_names[0])
                        lane_branch[new_lane_idx] = p_pref
            else:
                lanes[lane_idx] = parent0
            for p in parents[1:]:           # open extra lanes for merge parents
                if not any(s == p for s in lanes):
                    free = next((i for i, s in enumerate(lanes) if s is None), None)
                    if free is not None:
                        new_lane_idx = free
                        lanes[free] = p
                    else:
                        new_lane_idx = len(lanes)
                        lanes.append(p)
                    # Record name if the merge parent happens to be a branch tip
                    if p in branch_tip_map and new_lane_idx not in lane_branch:
                        p_names = branch_tip_map[p]
                        p_pref = next((n for n in p_names if n == primary), p_names[0])
                        lane_branch[new_lane_idx] = p_pref

    # ── Build lane_branch: lane_index -> display name ─────────────────────
    # Names were recorded inline above for tip SHAs.
    # Fallback for any lanes that still lack a name.
    for sha, lane_idx in assignment.items():
        if lane_idx not in lane_branch:
            names = branch_tip_map.get(sha, [])
            lane_branch[lane_idx] = (names[0] if names else "") or f"branch-{lane_idx}"

    lane_branch.setdefault(0, primary or "main")

    # ── Re-order lanes by depth so nested branches sit further from main ──
    # Iterate in reverse topo order (oldest commit first) so each lane's
    # parent depth is already known when we compute that lane's depth.
    lane_depth: dict[int, int] = {0: 0}
    for commit in reversed(commits):
        lane = assignment.get(commit.sha, 0)
        if lane == 0 or not commit.parents or lane in lane_depth:
            continue
        parent_lane = assignment.get(commit.parents[0], 0)
        if parent_lane != lane:
            lane_depth[lane] = lane_depth.get(parent_lane, 0) + 1

    # Sort non-zero lanes: shallower branches (closer to main) get lower indices.
    non_main = sorted(
        {l for l in assignment.values() if l != 0},
        key=lambda l: (lane_depth.get(l, 0), l),
    )
    lane_remap: dict[int, int] = {0: 0}
    for new_idx, old_idx in enumerate(non_main, start=1):
        lane_remap[old_idx] = new_idx

    if any(k != v for k, v in lane_remap.items()):
        assignment  = {sha: lane_remap.get(l, l) for sha, l in assignment.items()}
        lane_branch = {lane_remap.get(l, l): name  for l, name in lane_branch.items()}

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
        # Flag pole tip sits at -self._r - 20; include it with margin
        extra_top = 14 if self._is_start else 0
        extra_bot = 10 if self._has_stash else 0
        top = -r - 8 - extra_top
        return QRectF(-r - 8, top, (r + 8) * 2, r * 2 + 16 + extra_top + extra_bot)

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
            painter.setBrush(Qt.NoBrush)
            painter.setPen(QPen(QColor(COLORS["danger"]), 2.5))
            painter.drawEllipse(QPointF(0, 0), r + 5, r + 5)

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

        # Stash indicator — small amber dot below the node
        if self._has_stash:
            amber = QColor("#d69e2e")
            painter.setPen(Qt.NoPen)
            painter.setBrush(QBrush(amber))
            painter.drawEllipse(QPointF(0, r + 5), 3.5, 3.5)

        # Debug: action-head indicator — small red dot to the right
        if self._is_action_head:
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
    """
    L-shaped (elbow) line for cross-lane connections.
    dashed=False  → solid   (merge)
    dashed=True   → dashed  (branch creation / divergence)
    """

    def __init__(
        self,
        cx: float, cy: float,
        px: float, py: float,
        color: str,
        dashed: bool = False,
        orientation: str = ORIENT_LR,
    ):
        path = QPainterPath()
        path.moveTo(cx, cy)
        # Elbow: go along the age axis first, then the lane axis.
        if orientation in (ORIENT_LR, ORIENT_RL):
            if dashed:
                # Creation edge: vertical-first — rise to the parent's lane at
                # this commit's own x-column, then move horizontally to the parent.
                # The vertical segment is always in-viewport (same x as the branch
                # commit), making the branch-to-main connection visible even when
                # the parent is just off the edge of the canvas.
                path.lineTo(cx, py)   # vertical to parent's y-level (at commit's x)
                path.lineTo(px, py)   # horizontal to parent
            else:
                # Merge edge: vertical-first (arrowhead drawn separately at commit).
                path.lineTo(cx, py)   # vertical to merged branch's y-level
                path.lineTo(px, py)   # horizontal to merged branch's x
        else:  # ORIENT_TB / ORIENT_BT
            path.lineTo(px, cy)   # horizontal segment to source's x-level
            path.lineTo(px, py)   # vertical segment to source
        super().__init__(path)

        white = QColor("white")
        white.setAlpha(140)
        style = Qt.DashLine if dashed else Qt.SolidLine
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
        self._known_authors: set = set()
        self._stash_shas: set = set()
        self._author_items: dict[str, QGraphicsSimpleTextItem] = {}
        self._head_sha: str = ""
        self._orientation: str = ORIENT_LR
        self._dimmed_shas: set[str] = set()

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
        stash_shas: set = None,
        orientation: str = ORIENT_LR,
        head_sha: str = "",
        is_initial: bool = False,
        local_tip_shas: set = None,
        remote_tip_shas: set = None,
        action_head_shas: set = None,
        default_branch: str = "",
    ):
        prev_centre = self.mapToScene(self.viewport().rect().center())

        old_scene = self._scene
        self._scene = QGraphicsScene(self)
        self._scene.setBackgroundBrush(self._make_grid_brush())
        self.setScene(self._scene)
        old_scene.deleteLater()

        self._orientation = orientation
        self._head_sha    = head_sha
        self._nodes.clear()
        self._badges.clear()
        self._positions.clear()
        self._node_colors.clear()
        self._author_items.clear()
        self._content_rect = QRectF()
        self._selected_sha = None
        self._dimmed_shas.clear()
        self._commits = commits
        self._you_shas            = you_shas            or set()
        self._local_only_branches = local_only_branches or set()
        self._unpushed_shas       = unpushed_shas       or set()
        self._stash_shas        = stash_shas      or set()
        self._local_tip_shas_c  = local_tip_shas    or set()
        self._remote_tip_shas_c = remote_tip_shas   or set()
        self._action_head_shas  = action_head_shas  or set()

        if not commits:
            return

        lane_map, lane_branch = _compute_lanes(commits, branch_tip_map)

        for commit in commits:
            commit.branch = lane_branch.get(lane_map.get(commit.sha, 0), "")

        # ── Positions ──────────────────────────────────────────────────────
        n = len(commits)
        positions: dict[str, tuple[float, float]] = {}
        for i, commit in enumerate(commits):
            lane = lane_map.get(commit.sha, 0)
            if orientation == ORIENT_LR:
                x = H_PAD + (n - 1 - i) * ROW_H
                y = V_PAD + lane * LANE_W
            elif orientation == ORIENT_RL:
                x = H_PAD + i * ROW_H
                y = V_PAD + lane * LANE_W
            elif orientation == ORIENT_BT:
                x = H_PAD + lane * LANE_W
                y = V_PAD + (n - 1 - i) * ROW_H
            else:  # ORIENT_TB
                x = H_PAD + lane * LANE_W
                y = V_PAD + i * ROW_H
            positions[commit.sha] = (x, y)
        self._positions = positions

        if positions:
            xs = [x for x, y in positions.values()]
            ys = [y for x, y in positions.values()]
            self._content_rect = QRectF(
                min(xs) - 30, min(ys) - 30,
                max(xs) - min(xs) + 60, max(ys) - min(ys) + 60,
            )

        # ── 1. Lane spines ─────────────────────────────────────────────────
        lane_points: dict[int, list[tuple[float, float]]] = {}
        for commit in commits:
            lane = lane_map.get(commit.sha, 0)
            cx, cy = positions[commit.sha]
            lane_points.setdefault(lane, []).append((cx, cy))

        sort_key = (lambda p: p[0]) if orientation in (ORIENT_LR, ORIENT_RL) else (lambda p: p[1])
        for lane, pts in lane_points.items():
            if len(pts) < 2:
                continue
            pts.sort(key=sort_key)
            path = QPainterPath()
            path.moveTo(pts[0][0], pts[0][1])
            for x, y in pts[1:]:
                path.lineTo(x, y)
            spine = QGraphicsPathItem(path)
            branch_name = lane_branch.get(lane, "")
            is_local    = branch_name in self._local_only_branches
            raw_color   = _lane_color(lane) if is_local else "#6b7280"
            lane_color  = QColor(raw_color)
            lane_color.setAlpha(160)
            spine.setPen(QPen(lane_color, 2, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
            spine.setBrush(QBrush(Qt.NoBrush))
            spine.setZValue(1)
            spine.setAcceptedMouseButtons(Qt.NoButton)
            self._scene.addItem(spine)

        # ── 2. Cross-lane edges ────────────────────────────────────────────

        for commit in commits:
            cx, cy = positions[commit.sha]
            commit_lane = lane_map.get(commit.sha, 0)
            for p_sha in commit.parents[1:]:
                if p_sha not in positions:
                    continue
                parent_lane = lane_map.get(p_sha, 0)
                if parent_lane != commit_lane:
                    px, py = positions[p_sha]
                    edge = EdgeItem(cx, cy, px, py, _lane_color(parent_lane),
                                    dashed=False, orientation=orientation)
                    self._scene.addItem(edge)
                    # Arrowhead points along the first elbow segment into M.
                    if orientation in (ORIENT_LR, ORIENT_RL):
                        ux, uy = 0.0, (1.0 if py < cy else -1.0)
                    else:
                        ux, uy = (1.0 if px < cx else -1.0), 0.0
                    if True:  # always compute tip (replaces old length > 0 guard)
                        tip_x = cx - ux * (NODE_R + 2)
                        tip_y = cy - uy * (NODE_R + 2)
                        sz = 7
                        poly = QPolygonF([
                            QPointF(tip_x, tip_y),
                            QPointF(tip_x - ux * sz - uy * (sz / 2),
                                    tip_y - uy * sz + ux * (sz / 2)),
                            QPointF(tip_x - ux * sz + uy * (sz / 2),
                                    tip_y - uy * sz - ux * (sz / 2)),
                        ])
                        arrow = QGraphicsPolygonItem(poly)
                        arrow.setBrush(QBrush(QColor(_lane_color(parent_lane))))
                        arrow.setPen(QPen(Qt.NoPen))
                        arrow.setZValue(3)
                        arrow.setAcceptedMouseButtons(Qt.NoButton)
                        self._scene.addItem(arrow)

        # ── 2b. Branch-creation edges (dashed) & start-flag markers ──────────
        # Three-pass approach to avoid spurious flags when local and remote tips
        # of the same branch land on different lanes (algorithm artefact).
        #
        # Issue: merge commits pre-allocate a lane for the remote tip (origin/Zen)
        # before the local tip (Zen) is processed. The local tip ends up on a
        # different lane, so its parent looks like a cross-lane hop → false flag.
        #
        # Fix: collect ALL candidates first, deduplicate per logical branch
        # (keeping only the oldest = true branch root), then draw.

        # Maps commit_sha → (cx, cy, px, py, lane, draw_edge)
        candidate_info: dict[str, tuple] = {}
        commit_idx_map = {c.sha: i for i, c in enumerate(commits)}

        # Pass 1a: main loop — commits whose first parent is on a different lane
        for commit in commits:
            lane = lane_map.get(commit.sha, 0)
            if lane == 0 or not commit.parents:
                continue
            p_sha = commit.parents[0]
            parent_lane = lane_map.get(p_sha, 0)
            if parent_lane == lane:
                continue  # same lane — normal spine segment, not a branch root
            if commit.sha not in positions:
                continue
            cx, cy = positions[commit.sha]
            if p_sha in positions:
                px, py = positions[p_sha]
            else:
                # Parent beyond visible range — synthetic off-screen anchor
                if orientation == ORIENT_LR:
                    px, py = cx - ROW_H, V_PAD
                elif orientation == ORIENT_RL:
                    px, py = cx + ROW_H, V_PAD
                elif orientation == ORIENT_BT:
                    px, py = H_PAD, cy - ROW_H
                else:
                    px, py = H_PAD, cy + ROW_H
            candidate_info[commit.sha] = (cx, cy, px, py, lane, True)

        # Pass 1b: fallback — branch tips whose first parent is outside visible range
        sha_set = {c.sha: c for c in commits}
        for tip_sha in branch_tip_map:
            if tip_sha not in positions or tip_sha in candidate_info:
                continue
            tip_lane = lane_map.get(tip_sha)
            if tip_lane is None or tip_lane == 0:
                continue
            tip_commit = sha_set.get(tip_sha)
            if not tip_commit:
                continue
            first_parent = tip_commit.parents[0] if tip_commit.parents else None
            if first_parent and first_parent in positions:
                continue
            cx, cy = positions[tip_sha]
            # No dashed edge for this case — just the start-flag marker on the node
            candidate_info[tip_sha] = (cx, cy, cx, cy, tip_lane, False)

        # Pass 2: deduplicate — per logical branch, keep only the oldest candidate
        # (highest index in commits = farthest back in topo order).
        # Local tip (newer, lower index) and branch root (older, higher index)
        # both resolve to the same branch key → root wins, local tip discarded.
        def _branch_key(sha: str) -> str:
            tip_names = branch_tip_map.get(sha)
            if tip_names:
                return _branch_base(tip_names[0])
            ln = lane_map.get(sha, 0)
            return _branch_base(lane_branch.get(ln, f"lane-{ln}"))

        by_branch: dict[str, list[str]] = {}
        for sha in candidate_info:
            key = _branch_key(sha)
            by_branch.setdefault(key, []).append(sha)

        start_shas: set[str] = set()
        for key, shas in by_branch.items():
            # Keep the oldest commit (highest index = farthest back in topo order)
            oldest = max(shas, key=lambda s: commit_idx_map.get(s, 0))
            start_shas.add(oldest)

        # Pass 3: draw dashed edges for the deduplicated start set only
        for sha, (cx, cy, px, py, lane, draw_edge) in candidate_info.items():
            if sha not in start_shas:
                continue
            if draw_edge:
                self._scene.addItem(EdgeItem(cx, cy, px, py, _lane_color(lane),
                                             dashed=True, orientation=orientation))

        # ── 3. Nodes ───────────────────────────────────────────────────────
        # Build branch-name → colour from lane_branch first (covers all lanes),
        # then from tip commits (lane 0 / primary is always first, setting the
        # authoritative colour before other lanes for the same branch name).
        branch_name_color: dict[str, str] = {}
        for ln in sorted(lane_branch):           # lane 0 first → primary wins
            bname = lane_branch[ln]
            if bname and bname not in branch_name_color:
                branch_name_color[bname] = _lane_color(ln)

        for commit in commits:
            cx, cy      = positions[commit.sha]
            lane        = lane_map.get(commit.sha, 0)
            branch_name = lane_branch.get(lane, "")
            is_local    = (branch_name in self._local_only_branches
                           or commit.sha in self._unpushed_shas)
            tip_names   = branch_tip_map.get(commit.sha, [])
            branch_key  = tip_names[0] if tip_names else branch_name
            color       = branch_name_color.get(branch_key, _lane_color(lane))
            self._node_colors[commit.sha] = color
            node = CommitNode(commit, color,
                              is_start=commit.sha in start_shas,
                              is_local_only=is_local,
                              is_head=commit.sha == head_sha,
                              has_stash=commit.sha in self._stash_shas,
                              is_local_tip=commit.sha in self._local_tip_shas_c,
                              is_remote_tip=commit.sha in self._remote_tip_shas_c,
                              is_action_head=commit.sha in self._action_head_shas)
            node.setPos(cx, cy)
            node.clicked.connect(self._on_node_clicked)
            self._scene.addItem(node)
            self._nodes[commit.sha] = node

        # ── 4. Branch labels — removed ────────────────────────────────────

        # ── 5. Commit info text (date + author) ────────────────────────────
        date_font   = QFont("Inter, Segoe UI", 8)
        author_font = QFont("Inter, Segoe UI", 8)
        date_color   = QBrush(QColor(COLORS["text_secondary"]))
        author_color = QBrush(QColor(COLORS["text_muted"]))

        for commit in commits:
            cx, cy = positions[commit.sha]
            d = commit.date
            date_str = f"{d.day} {d.strftime('%b')} {d.year}  {d.strftime('%H:%M')}"

            date_item = QGraphicsSimpleTextItem(date_str)
            date_item.setFont(date_font)
            date_item.setBrush(date_color)
            date_item.setAcceptedMouseButtons(Qt.NoButton)
            date_item.setZValue(2)

            auth_item = QGraphicsSimpleTextItem("")
            auth_item.setFont(author_font)
            auth_item.setBrush(author_color)
            auth_item.setAcceptedMouseButtons(Qt.NoButton)
            auth_item.setZValue(2)

            if orientation in (ORIENT_LR, ORIENT_RL):
                self._author_items[commit.sha] = auth_item
                self._update_author_item(auth_item, commit.sha, commit)
                auth_item.setPos(cx - auth_item.boundingRect().width() / 2, cy + NODE_R + 6)
                self._scene.addItem(auth_item)
            else:
                text_x = cx + NODE_R + 14
                dh = date_item.boundingRect().height()
                ah = auth_item.boundingRect().height()
                date_item.setPos(text_x, cy - dh / 2 - 7)
                auth_item.setPos(text_x, cy - ah / 2 + 7)
                self._scene.addItem(date_item)
                self._scene.addItem(auth_item)
                self._author_items[commit.sha] = auth_item
                self._update_author_item(auth_item, commit.sha, commit)

        # ── Scene rect ─────────────────────────────────────────────────────
        max_lane = max(lane_map.values(), default=0)
        if orientation in (ORIENT_LR, ORIENT_RL):
            content_w = H_PAD * 2 + n * ROW_H + 100
            content_h = V_PAD * 2 + max_lane * LANE_W + 300
        else:
            content_w = H_PAD * 2 + max_lane * LANE_W + 300
            content_h = V_PAD * 2 + n * ROW_H + 100
        self._scene.setSceneRect(
            -CANVAS_PAD, -CANVAS_PAD,
            content_w + CANVAS_PAD * 2,
            content_h + CANVAS_PAD * 2,
        )

        if not is_initial and (prev_centre.x() or prev_centre.y()):
            self.centerOn(prev_centre)
        elif head_sha and head_sha in self._nodes:
            self.centerOn(self._nodes[head_sha].scenePos())
        elif orientation == ORIENT_BT:
            self.centerOn(H_PAD, V_PAD + (n - 1) * ROW_H)
        elif orientation == ORIENT_LR:
            self.centerOn(H_PAD + (n - 1) * ROW_H, V_PAD)
        else:
            self.centerOn(H_PAD, V_PAD)

    def apply_commit_filter(self, dimmed_shas: set[str]):
        """Dim the given SHAs to 15% opacity; restore all others."""
        self._dimmed_shas = set(dimmed_shas)
        for commit in self._commits:
            dim     = commit.sha in dimmed_shas
            opacity = 0.15 if dim else 1.0
            if commit.sha in self._nodes:
                self._nodes[commit.sha].setOpacity(opacity)
            if commit.sha in self._author_items:
                self._author_items[commit.sha].setOpacity(0.0 if dim else 1.0)
        self.viewport_changed.emit()

    def set_pr_highlight(self, active_shas: set[str]):
        """PR hover: keep active_shas bright, dim everything else. Empty set restores filter."""
        if not active_shas:
            self.apply_commit_filter(self._dimmed_shas)
            return
        for commit in self._commits:
            keep    = commit.sha in active_shas
            opacity = 1.0 if keep else 0.08
            if commit.sha in self._nodes:
                self._nodes[commit.sha].setOpacity(opacity)
            if commit.sha in self._author_items:
                self._author_items[commit.sha].setOpacity(1.0 if keep else 0.0)
        self.viewport_changed.emit()

    def _update_author_item(self, item, sha: str, commit):
        is_you = sha in self._you_shas
        raw = "You" if is_you else commit.author
        item.setText(raw if len(raw) <= 8 else raw[:7] + "…")
        item.setVisible(True)
        if self._orientation in (ORIENT_LR, ORIENT_RL) and sha in self._positions:
            cx, cy = self._positions[sha]
            max_w = ROW_H - 8
            if item.boundingRect().width() > max_w:
                fm = QFontMetrics(item.font())
                item.setText(fm.elidedText(item.text(), Qt.ElideRight, int(max_w)))
            aw = item.boundingRect().width()
            item.setPos(cx - aw / 2, cy + NODE_R + 6)

    def refresh_you_labels(self, you_shas: set):
        """Update author text labels to show 'You' for the given commit SHAs."""
        self._you_shas = you_shas
        for sha, item in self._author_items.items():
            commit = next((c for c in self._commits if c.sha == sha), None)
            if commit is None:
                continue
            self._update_author_item(item, sha, commit)

    def set_known_authors(self, known: set[str]):
        """Dim author labels for commits whose author isn't a known collaborator."""
        self._known_authors = known
        muted = QColor(COLORS["text_muted"])
        primary = QColor(COLORS["text_primary"])
        for sha, item in self._author_items.items():
            commit = next((c for c in self._commits if c.sha == sha), None)
            if commit is None:
                continue
            if sha in self._you_shas or not known or commit.author in known:
                item.setBrush(QBrush(primary))
            else:
                item.setBrush(QBrush(muted))

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
        QTimer.singleShot(0, lambda: self.commit_clicked.emit(commit))

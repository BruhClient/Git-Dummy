"""Main canvas view — pan/zoom, graph loading, node selection."""
from __future__ import annotations

import threading
from typing import Optional

from PyQt5.QtCore import Qt, QRectF, QPointF, QEvent, pyqtSignal, QTimer
from PyQt5.QtGui import (
    QPainter, QColor, QPen, QBrush, QFont, QFontMetrics,
    QPainterPath, QPolygonF, QPixmap,
)
from PyQt5.QtWidgets import (
    QGraphicsView, QGraphicsScene,
    QGraphicsPathItem, QGraphicsPolygonItem, QGraphicsSimpleTextItem,
)

from core.git_tracker import CommitInfo
from styles.theme import COLORS
from .constants import (
    NODE_R, START_R, BADGE_R, LANE_W, ROW_H, H_PAD, V_PAD, CANVAS_PAD,
    ZOOM_MIN, ZOOM_MAX, ZOOM_STEP,
    ORIENT_TB, ORIENT_BT, ORIENT_LR, ORIENT_RL,
    _lane_color,
)
from .lane_algorithm import _compute_lanes, _branch_base
from .graphics_items import CommitNode, BranchLabel, EdgeItem, ContributorBadge


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
        self._badges: list[ContributorBadge] = []
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
        self._future_shas: set[str] = set()

    # ── Helpers ───────────────────────────────────────────────────────────────

    @staticmethod
    def _make_grid_brush(cell: int = 40) -> QBrush:
        """Creates a tiled pixel-map with a subtle dot-grid pattern."""
        pm = QPixmap(cell, cell)
        pm.fill(QColor(COLORS["bg_primary"]))
        p = QPainter(pm)
        line_color = QColor(COLORS["border"])
        line_color.setAlpha(80)
        p.setPen(QPen(line_color, 1))
        p.drawLine(cell - 1, 0, cell - 1, cell - 1)
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
        self._future_shas.clear()
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

        lane_map, lane_branch = _compute_lanes(commits, branch_tip_map,
                                               local_tip_shas=self._local_tip_shas_c)
        for commit in commits:
            commit.branch = lane_branch.get(lane_map.get(commit.sha, 0), "")

        # ── Identify future (remote-only) commits ────────────────────────────
        # Only dim commits on branches that are truly behind (local tip is an
        # ancestor of remote tip).  Skip diverged branches — both sides should
        # render at full opacity.
        _local_tip_set = local_tip_shas or set()
        _commit_order  = {c.sha: i for i, c in enumerate(commits)}
        _commit_by_sha = {c.sha: c for c in commits}
        _local_tip_for_branch: dict[str, tuple[str, int]] = {}
        for c in commits:
            if c.sha in _local_tip_set:
                _local_tip_for_branch[c.branch] = (c.sha, _commit_order.get(c.sha, 10**9))
        _behind_branches: set[str] = set()
        for sha, names in branch_tip_map.items():
            if sha in _local_tip_set:
                continue
            for name in names:
                if name not in _local_tip_for_branch:
                    continue
                local_sha, _local_order = _local_tip_for_branch[name]
                if _commit_order.get(sha, 10**9) >= _local_order:
                    continue
                # Verify local tip is reachable from remote tip (truly behind,
                # not diverged).
                _s, _v = sha, set()
                _reachable = False
                while _s and _s in _commit_by_sha and _s not in _v:
                    _v.add(_s)
                    if _s == local_sha:
                        _reachable = True
                        break
                    _c = _commit_by_sha[_s]
                    _s = _c.parents[0] if _c.parents else None
                if _reachable:
                    _behind_branches.add(name)
                break
        self._future_shas = {
            c.sha for c in commits
            if c.branch in _behind_branches
            and c.sha not in _local_tip_set
            and _commit_order.get(c.sha, 10**9) < _local_tip_for_branch[c.branch][1]
        }
        # ── Filter commits on anonymous lanes (deleted-branch ghosts) ──────
        unnamed_lanes = {lane for lane, name in lane_branch.items() if not name}
        if unnamed_lanes:
            commits = [c for c in commits if lane_map.get(c.sha, 0) not in unnamed_lanes]
            used_lanes  = sorted({lane_map.get(c.sha, 0) for c in commits})
            _lr         = {orig: new for new, orig in enumerate(used_lanes)}
            lane_map    = {sha: _lr[lane] for sha, lane in lane_map.items()
                           if lane not in unnamed_lanes}
            lane_branch = {_lr[orig]: name for orig, name in lane_branch.items()
                           if orig not in unnamed_lanes}

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

        self._draw_lane_spines(commits, positions, lane_map, lane_branch, orientation)
        self._draw_cross_lane_edges(commits, positions, lane_map, orientation)
        start_shas = self._draw_branch_creation_edges(
            commits, positions, lane_map, lane_branch, branch_tip_map, orientation)
        self._nodes = {}
        self._draw_nodes(commits, positions, lane_map, lane_branch, branch_tip_map,
                         start_shas, head_sha)
        for _sha in self._future_shas:
            if _sha in self._nodes:
                self._nodes[_sha].setOpacity(0.4)
            if _sha in self._author_items:
                self._author_items[_sha].setOpacity(0.4)
        self._draw_text_labels(commits, positions, orientation)

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

    # ── Graph drawing helpers ────────────────────────────────────────────────

    def _draw_lane_spines(self, commits, positions, lane_map, lane_branch, orientation):
        base_color: dict[str, str] = {}
        for ln in sorted(lane_branch):
            b = _branch_base(lane_branch[ln])
            if b and b not in base_color:
                base_color[b] = _lane_color(ln)

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
            bname = _branch_base(lane_branch.get(lane, ""))
            raw_color   = base_color.get(bname, _lane_color(lane))
            lane_color  = QColor(raw_color)
            lane_color.setAlpha(160)
            spine.setPen(QPen(lane_color, 2, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
            spine.setBrush(QBrush(Qt.NoBrush))
            spine.setZValue(1)
            spine.setAcceptedMouseButtons(Qt.NoButton)
            self._scene.addItem(spine)

    def _draw_cross_lane_edges(self, commits, positions, lane_map, orientation):
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
                    if orientation in (ORIENT_LR, ORIENT_RL):
                        ux, uy = 0.0, (1.0 if py < cy else -1.0)
                    else:
                        ux, uy = (1.0 if px < cx else -1.0), 0.0
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

    def _draw_branch_creation_edges(self, commits, positions, lane_map, lane_branch,
                                     branch_tip_map, orientation) -> set[str]:
        """Draw dashed edges for branch roots; return the set of start SHAs."""
        candidate_info: dict[str, tuple] = {}
        commit_idx_map = {c.sha: i for i, c in enumerate(commits)}

        for commit in commits:
            lane = lane_map.get(commit.sha, 0)
            if lane == 0:
                continue
            if not commit.parents:
                if commit.sha not in positions:
                    continue
                cx, cy = positions[commit.sha]
                if orientation == ORIENT_LR:
                    px, py = cx - ROW_H, V_PAD
                elif orientation == ORIENT_RL:
                    px, py = cx + ROW_H, V_PAD
                elif orientation == ORIENT_BT:
                    px, py = H_PAD, cy - ROW_H
                else:
                    px, py = H_PAD, cy + ROW_H
                candidate_info[commit.sha] = (cx, cy, px, py, lane, False, -1)
                continue
            p_sha = commit.parents[0]
            parent_lane = lane_map.get(p_sha, 0)
            if parent_lane == lane or commit.sha not in positions:
                continue
            cx, cy = positions[commit.sha]
            if p_sha in positions:
                px, py = positions[p_sha]
            else:
                if orientation == ORIENT_LR:
                    px, py = cx - ROW_H, V_PAD
                elif orientation == ORIENT_RL:
                    px, py = cx + ROW_H, V_PAD
                elif orientation == ORIENT_BT:
                    px, py = H_PAD, cy - ROW_H
                else:
                    px, py = H_PAD, cy + ROW_H
            candidate_info[commit.sha] = (cx, cy, px, py, lane, True, parent_lane)

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
            candidate_info[tip_sha] = (cx, cy, cx, cy, tip_lane, False, -1)

        _base_to_tips: dict[str, list[str]] = {}
        for tip_sha, names in branch_tip_map.items():
            for n in names:
                b = _branch_base(n)
                if b:
                    _base_to_tips.setdefault(b, []).append(tip_sha)
        diverged_tip_shas: set[str] = set()
        for b, tips in _base_to_tips.items():
            if len(tips) > 1:
                diverged_tip_shas.update(tips)

        _diverged_local_lanes: set[int] = set()
        for sha in diverged_tip_shas:
            if sha in self._local_tip_shas_c:
                dl = lane_map.get(sha)
                if dl is not None:
                    _diverged_local_lanes.add(dl)

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
            oldest = max(shas, key=lambda s: commit_idx_map.get(s, 0))
            start_shas.add(oldest)

        for sha, (cx, cy, px, py, lane, draw_edge, p_lane) in candidate_info.items():
            is_start = sha in start_shas
            is_diverged = sha in diverged_tip_shas
            if not is_start and not is_diverged and lane not in _diverged_local_lanes:
                continue
            if draw_edge:
                # Diagonal only for same-branch diverged tips (local tip → remote tip)
                same_branch = _branch_base(lane_branch.get(lane, "")) == _branch_base(lane_branch.get(p_lane, ""))
                _diagonal = same_branch and ((is_diverged and sha in self._local_tip_shas_c) or lane in _diverged_local_lanes)
                self._scene.addItem(EdgeItem(cx, cy, px, py, _lane_color(lane),
                                             dashed=True, orientation=orientation,
                                             diagonal=_diagonal))

        start_shas -= diverged_tip_shas
        return start_shas

    def _draw_nodes(self, commits, positions, lane_map, lane_branch, branch_tip_map,
                    start_shas, head_sha):
        branch_name_color: dict[str, str] = {}
        for ln in sorted(lane_branch):
            bname = _branch_base(lane_branch[ln])
            if bname and bname not in branch_name_color:
                branch_name_color[bname] = _lane_color(ln)
        self._branch_colors = branch_name_color

        for commit in commits:
            cx, cy      = positions[commit.sha]
            lane        = lane_map.get(commit.sha, 0)
            branch_name = lane_branch.get(lane, "")
            is_local    = (branch_name in self._local_only_branches
                           or commit.sha in self._unpushed_shas)
            tip_names   = branch_tip_map.get(commit.sha, [])
            branch_key  = _branch_base(tip_names[0]) if tip_names else _branch_base(branch_name)
            color       = branch_name_color.get(branch_key, _lane_color(lane))
            self._node_colors[commit.sha] = color
            # Only show remote-tip dot when the commit's lane matches one of its
            # branch_tip_map names. Prevents stale merged remote refs (e.g.
            # origin/zen after the PR was merged and local zen deleted) from
            # showing a dot on commits absorbed into main's lane.
            is_actual_remote_tip = (
                commit.sha in self._remote_tip_shas_c
                and branch_name in tip_names
            )
            node = CommitNode(commit, color,
                              is_start=commit.sha in start_shas,
                              is_local_only=is_local,
                              is_head=commit.sha == head_sha,
                              has_stash=commit.sha in self._stash_shas,
                              is_local_tip=commit.sha in self._local_tip_shas_c,
                              is_remote_tip=is_actual_remote_tip,
                              is_action_head=commit.sha in self._action_head_shas)
            node.setPos(cx, cy)
            node.clicked.connect(self._on_node_clicked)
            self._scene.addItem(node)
            self._nodes[commit.sha] = node


    def _draw_text_labels(self, commits, positions, orientation):
        author_font = QFont("Urbanist", 8)
        author_color = QBrush(QColor(COLORS["text_muted"]))

        for commit in commits:
            cx, cy = positions[commit.sha]

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
                ah = auth_item.boundingRect().height()
                auth_item.setPos(text_x, cy - ah / 2)
                self._scene.addItem(auth_item)
                self._author_items[commit.sha] = auth_item
                self._update_author_item(auth_item, commit.sha, commit)

    # ── Filter / highlight ───────────────────────────────────────────────────

    def apply_commit_filter(self, dimmed_shas: set[str]):
        """Dim the given SHAs to 15% opacity; restore all others."""
        self._dimmed_shas = set(dimmed_shas)
        for commit in self._commits:
            dim     = commit.sha in dimmed_shas
            is_future = commit.sha in self._future_shas
            opacity = 0.15 if dim else (0.4 if is_future else 1.0)
            if commit.sha in self._nodes:
                self._nodes[commit.sha].setOpacity(opacity)
            if commit.sha in self._author_items:
                self._author_items[commit.sha].setOpacity(0.0 if dim else (0.4 if is_future else 1.0))
        self.viewport_changed.emit()

    def scroll_to_sha(self, sha: str):
        node = self._nodes.get(sha)
        if node:
            self.centerOn(node)

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

    # ── Author labels ────────────────────────────────────────────────────────

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

    # ── Contributor avatars ──────────────────────────────────────────────────

    def load_contributor_avatars(self, badge_data: list[dict]):
        """Place avatar badges for each contributor at their latest commit."""
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
            badge = ContributorBadge(login, color)
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

    # ── Public state modifiers ───────────────────────────────────────────────

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

    # ── Gesture (pinch) ───────────────────────────────────────────────────────

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

    # ── Zoom ──────────────────────────────────────────────────────────────────

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

    # ── Pan ───────────────────────────────────────────────────────────────────

    def mousePressEvent(self, event):
        if self._gesture_active:
            event.ignore()
            return
        item = self.itemAt(event.pos())
        if isinstance(item, (CommitNode, ContributorBadge)):
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

    # ── Internal ──────────────────────────────────────────────────────────────

    @staticmethod
    def _fetch_badge_avatar(badge: ContributorBadge, url: str):
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

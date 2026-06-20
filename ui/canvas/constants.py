"""Layout constants and orientation flags shared across the canvas module."""

from styles.theme import COLORS

# ── Layout ────────────────────────────────────────────────────────────────────
NODE_R     = 10
START_R    = 14
BADGE_R    = 9        # contributor avatar badge radius
LANE_W     = 100      # wider — leaves room for branch label pills
ROW_H      = 72
H_PAD      = 80
V_PAD      = 60
CANVAS_PAD = 800      # pan boundary — how far past the content edge the user can scroll

ZOOM_MIN  = 0.2
ZOOM_MAX  = 1.5
ZOOM_STEP = 1.10

# ── Orientation ───────────────────────────────────────────────────────────────
ORIENT_TB = "TB"   # top → bottom  (newest at top)
ORIENT_BT = "BT"   # bottom → top  (oldest at top)
ORIENT_LR = "LR"   # left → right  (oldest at left)
ORIENT_RL = "RL"   # right → left  (newest at left)

# ── Branch colours ─────────────────────────────────────────────────────────────
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

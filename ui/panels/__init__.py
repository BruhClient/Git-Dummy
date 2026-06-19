"""ui.panels — re-exports the main panel classes and shared utilities."""
from ui.panels.detail_panel import DetailPanel  # noqa: F401
from ui.panels.changes_panel import ChangesPanel  # noqa: F401
from ui.panels.diff_renderer import (  # noqa: F401
    PANEL_W,
    CHANGES_W,
    SWIPE_THRESHOLD,
    _VScrollArea,
    _trunc,
    _close_btn_style,
    _STATUS_COLOR,
    _STATUS_LABEL,
    _filter_unchanged,
    _chunk_lines,
    _compute_hunks,
    _MiniBar,
    _DiffLine,
    _Row,
    _fade_in,
    _fade_out_and_remove,
    _divider,
)
from ui.panels.all_changes_popup import AllChangesPopup  # noqa: F401
from ui.panels.settings_panel import SettingsPanel  # noqa: F401
from ui.panels.position_panel import PositionPanel  # noqa: F401
from ui.panels.pr_panel import PullRequestsPanel  # noqa: F401

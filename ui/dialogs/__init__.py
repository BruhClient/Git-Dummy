"""ui.dialogs — re-exports all dialog classes and helpers."""
from ui.dialogs.confirm_dialog import (  # noqa: F401
    ConfirmDialog,
    AlertDialog,
    confirm,
    alert,
)
from ui.dialogs.message_dialog import CommitMessageDialog  # noqa: F401
from ui.dialogs.conflict_dialog import (  # noqa: F401
    _numbered,
    _ConflictDialog,
    _PullDirtyDialog,
    _NavigateDirtyDialog,
    _MergeConflictDialog,
)
from ui.dialogs.github_connect import _GitHubConnectDialog  # noqa: F401
from ui.dialogs.clone_dialog import CloneDialog, RepoRow  # noqa: F401
from ui.dialogs.init_dialog import InitDialog  # noqa: F401
from ui.dialogs.pr_open_wizard import PROpenWizard  # noqa: F401
from ui.dialogs.add_account_dialog import AddAccountDialog  # noqa: F401
from ui.dialogs.instructions_dialog import InstructionsDialog  # noqa: F401
from ui.dialogs.visualizer_help_dialog import VisualizerHelpDialog  # noqa: F401
from ui.dialogs.pr_help_dialog import PRHelpDialog  # noqa: F401

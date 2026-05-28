"""Re-export all git operations so `from core.ops import X` works directly."""

from .base_ops import (   # noqa: F401
    _run,
    has_uncommitted_changes,
    checkout_commit,
    checkout_branch,
    current_branch,
    reset_hard,
    get_conflict_files,
    get_conflict_content,
)
from .stash_ops import (   # noqa: F401
    get_stash_files,
    create_auto_stash,
    pop_auto_stash,
    apply_stash,
    drop_stash,
    get_stash_ref_for_commit,
    get_stash_commit_shas,
    get_stash_list_id,
    save_stash_as_commit,
)
from .diff_ops import (   # noqa: F401
    get_stash_diff_files,
    get_working_dir_diff_files,
)
from .merge_ops import (   # noqa: F401
    merge_branch,
    merge_with_decisions,
    merge_use_theirs,
    merge_use_ours,
    merge_abort,
    conflict_discard_local,
    conflict_keep_local,
    check_pr_conflicts,
    merge_pr_locally,
)
from .revert_ops import (   # noqa: F401
    discard_all_changes,
    hard_revert_to,
    soft_revert_to,
)
from .branch_ops import (   # noqa: F401
    get_default_branch,
    branch_for_commit,
    get_branch_unique_commits,
    branch_unique_commits,
    branch_unique_count,
    delete_branch_full,
    create_branch_with_commit,
)
from .github_ops import (   # noqa: F401
    create_github_repo,
    push_branch,
    push_to_github,
)
from .repo_ops import (   # noqa: F401
    init_repo,
    clone_repo,
    pull_ff,
    pull_stash_apply,
    pull_save_merge,
    pull_discard,
)

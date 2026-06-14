# `ui/commit_view.py` decomposition plan (Task #9)

**Owner:** code-quality-refactor
**Status:** in progress — 3 extraction steps landed (dead-file, widgets, PR mixin).

## Goal
Shrink `CommitViewPage` (`ui/commit_view.py`) into navigable modules **without
changing behavior**. No test suite exists, so each step must be landed as one
focused commit and verified by running `python main.py` and exercising the
moved functionality before starting the next step.

> **Sandbox caveat:** the refactor sessions so far ran in an environment with
> **no PyQt5 and no linter**, so the GUI could not be launched. Each step was
> instead verified statically: `py_compile` + package `compileall`, a grep that
> the moved `def`s are gone from `commit_view.py` and all call sites still
> reference them via `self.`, and an **AST free-variable analysis** of the new
> module confirming no undefined names (the only `NameError` failure mode a
> behavior-preserving mixin move can introduce). **A runtime smoke-test of each
> moved flow is still owed** and should be done by a teammate with a working
> PyQt5 environment.

## What already landed
1. **Deleted dead `ui/spatial_canvas.py`** (~1300 lines, zero imports; stale
   duplicate of the live `ui/canvas/spatial_canvas.py`). `ui/canvas/constants.py`
   is now the single source for `NODE_R`/`LANE_W`/`ROW_H`/`START_R`.
   Commit `56bd082`.
2. **Extracted self-contained widgets** → `ui/commit_view_widgets.py`
   (`_FilterPanel`, `_OrientBar`, `_TabBar`, `_CreateRemoteDialog`). Pure
   cut/paste; they depend only on Qt + `COLORS` + `ORIENT_*` + `_VScrollArea`.
   `commit_view.py`: 2872 → 2345 lines. Commit `49bd73c`.
3. **Extracted PR handlers** → `ui/commit_view_pr.py` `_PRMixin` (Step 4 below,
   done before Step 3). 11 methods, mixed in as `class CommitViewPage(_PRMixin,
   QWidget)`. Self-contained: needs **no module-level imports** (every dep is
   imported locally inside its method). `commit_view.py`: 2345 → 2149 lines.
   Commit `e472151`.

> **Ordering note:** the PR block (Step 4) was done first because it is a single
> **contiguous** range and fully self-contained, making it the lowest-risk first
> mixin. The action-handler block (Step 3) is **interspersed** with non-action
> methods (`_on_github_connect`, `_reload_after_init`), so it needs careful
> multi-range extraction — do it after the contiguous blocks.

## The remaining hard part
The bulk of `CommitViewPage` is **action handlers + threading orchestration +
canvas/collab glue**, and almost every method touches `self` state:
`self._tracker`, `self._repo_path`, `self._local_tip_shas`, `self._detail_panel`,
the 15 instance `pyqtSignal`s, the `_panel_op_active` flag (40 touch points),
`_navigating`, the `_xxx_thread`/`_xxx_worker` refs, etc.

These **cannot** become free functions in another module — they need `self`.
The only behavior-preserving decomposition is the **mixin pattern**: move
cohesive method groups into mixin classes (one file each), then compose:

```python
# ui/commit_view.py
class CommitViewPage(_ActionsMixin, _PollingMixin, _CanvasGlueMixin, QWidget):
    # ALL pyqtSignal declarations stay here (the metaclass must see them on the
    # QObject-derived class). __init__ / _setup_ui stay here too.
    _merge_done_sig = pyqtSignal(...)
    ...
```

Mixin methods reference `self._merge_done_sig`, `self._tracker`, etc.; these
resolve at runtime against the composed instance — identical binding, identical
behavior. **Rules:**
- Keep every `pyqtSignal` declaration on `CommitViewPage` itself.
- Keep `__init__`, `_setup_ui`, and the thread-ref attribute initialization on
  `CommitViewPage`.
- Mixins are plain classes (not `QWidget`/`QObject`) — they only hold methods.
- Put each mixin **before** `QWidget` in the MRO so its methods win; mixins must
  not define `__init__`.
- Do not reorder/rename methods or change signal signatures.

## Proposed modules & dependency order

Execute **top to bottom**; each is an independent commit + app-run verification.
Earlier steps are lower-risk; stop and reassess if any step needs to touch
`core/ops/*` or `ui/workers/commit_workers.py` (other agents own those — keep
changes there minimal and re-check `git status` before committing).

### Step 3 — `ui/commit_view_actions.py` → `_ActionsMixin` (highest value)
Move the git-action handlers. They share one shape: an inline
`def _run(): ... ; threading.Thread(target=_run, daemon=True).start()` plus a
result `pyqtSignal` slot, guarded by `_panel_op_active`. Group:
- **Stash:** `_on_clear_stash`, `_on_clear_stash_done`, `_on_save_stash`
- **Merge:** `_on_merge_branch`, `_on_merge_done`, `_on_merge_conflict_choice`,
  `_on_merge_resolve_done`
- **Pull:** `_on_pull_branch`, `_do_clean_pull`, `_on_pull_dirty_choice`,
  `_on_pull_done`
- **Push:** `_on_push_branch`, `_on_push_done`, `_on_conflict_choice`,
  `_on_conflict_done`
- **Revert/branch:** `_on_hard_revert`, `_on_soft_revert`, `_on_delete_branch`,
  `_run_branch_op`, `_on_branch_op_done`, `_on_branch_create`,
  `_on_branch_create_done`
- **Auto-pull:** `_trigger_auto_pull`, `_on_auto_pulled`

> ~25 methods, ~600 lines. Verify: do a stash save/clear, a branch merge
> (incl. a conflict), a pull (clean + dirty), a push (incl. rejected/non-ff),
> a hard & soft revert, a branch create & delete.

### Step 4 — `ui/commit_view_pr.py` → `_PRMixin`  ✅ DONE (commit `e472151`)
PR inbox + open-wizard flow:
`_load_pr_inbox`, `_on_pr_open_requested`, `_on_wizard_commit`,
`_on_wizard_discard`, `_on_wizard_push`, `_on_wizard_pr_submit`,
`_on_pr_merge_requested`, `_on_pr_conflict_check`, `_on_wizard_commit_done`,
`_on_wizard_push_done`, `_on_wizard_pr_done`.

> Verify: open the PR wizard, commit→push→submit a PR, and merge a PR
> (with and without conflicts).

### Step 5 — `ui/commit_view_remote.py` → `_RemoteSetupMixin`
GitHub-connect / create-remote / init flow:
`_on_connect_requested`, `_on_github_connect`, `_reload_after_init`,
`_start_create_repo`, `_on_create_done`, `_show_create_remote_dialog`,
`_on_create_remote_requested`, `_on_create_remote_cancelled`,
`_start_create_repo`'s QThread wiring. (Uses `_CreateRepoWorker`,
`_VisibilityWorker`.)

> Verify: open a repo with no remote, create the remote, confirm graph reloads.

### Step 6 — `ui/commit_view_polling.py` → `_PollingMixin`
Background polling + fs-watcher + uncommitted refresh:
`_poll_remote`, `_on_fetch_done`, `_on_branch_count_done`,
`_find_nearest_surviving_ancestor`, `_handle_remote_deleted_commit`,
`_setup_fs_watcher`, `_teardown_fs_watcher`, `_on_git_file_changed`,
`_on_git_dir_changed`, `_poll_uncommitted`, `_on_uncommitted_thread_done`,
`_on_uncommitted_done`, `_start_load`. (QThread workers `_FetchWorker`,
`_UncommittedRefreshWorker` — wiring follows the standard pattern; do **not**
introduce `deleteLater()` or cross-thread `QTimer.singleShot`.)

> Verify: leave the app idle 30s+ (fetch tick), make an external commit (fs
> watcher), edit a file (2s uncommitted poll), push from another clone
> (auto-ff).

### Step 7 — `ui/commit_view_navigate.py` → `_NavigateMixin`
Checkout/navigation (uses `_navigating` flag + `_NavigateWorker`):
`_on_navigate`, `_launch_navigate`, `_on_navigate_dirty_choice`,
`_on_navigate_done`, `_on_detail_thread_done`, `_on_commit_clicked`,
`_on_commit_detail_ready`.

> Verify: click commits (detail panel), checkout a commit/branch (clean +
> dirty working tree), confirm `_navigating` still gates the uncommitted poll.

### Step 8 — `ui/commit_view_collab.py` → `_CollabMixin`
Collaborator loading + attribution:
`_load_collaborators`, `_on_perm_check_done`, `_on_collabs_loaded`,
`_compute_you_shas`, `_find_latest_commit_for_login`, `_on_collaborator_clicked`,
`_place_contributor_badges`, `_avatar_url_for_author`.

> Verify: open Collaboration tab, confirm avatars/badges and "you" highlighting.

### Keep on `CommitViewPage` (do not extract)
`__init__`, `_setup_ui`, `set_user`, `reset`, `load_repo`, `_stop_all_threads`,
`_drop_inflight`, `_on_loaded`, `_update_position_panel`, `_apply_canvas_filter`,
`_set_orientation`, `_switch_tab`, `toggle_filter_panel`, `resizeEvent` and the
other geometry/`_reposition_*` helpers, plus **all `pyqtSignal` declarations**.
These are the page's structural core / canvas wiring and are tightly coupled to
layout; leaving them keeps the composed class coherent.

## On de-duplication (deliberately NOT doing yet)
The 16 inline `def _run(): … threading.Thread(target=_run).start()` blocks look
duplicated, but each body differs (different op, different result signal). Per
the project's "no premature abstraction" stance, do **not** extract a generic
`_run_in_thread` helper now — the closures aren't identical enough to share one.
Revisit only if, after Step 3, several handlers collapse to literally the same
shape. The QThread worker wiring (`moveToThread` + `started`/`finished` connects)
**is** repeated 2+ times verbatim; if a step would copy it again, extract a
small `_spawn_worker(thread_attr, worker)` helper on `CommitViewPage` instead of
duplicating — but only at that point, not preemptively.

## Verification checklist per step
1. `python3 -m py_compile` the touched files (syntax).
2. `python3 -m compileall ui core` (package-wide).
3. Grep the moved symbol names: only the import + call sites should remain in
   `commit_view.py`; no leftover `def`.
4. Trim imports the move orphaned from `commit_view.py` (and add them to the new
   module).
5. **Run `python main.py`** and exercise exactly the moved functionality.
6. One focused commit; `git status` first to avoid clobbering concurrent edits
   from other agents (e.g. `ui/canvas/lane_algorithm.py`, `core/ops/*`,
   `ui/workers/commit_workers.py`).

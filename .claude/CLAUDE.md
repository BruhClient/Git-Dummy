# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Running the app

```bash
# Activate the venv first
venv\Scripts\activate        # Windows
# source venv/bin/activate   # macOS/Linux

python main.py
```

## Installing dependencies

```bash
pip install -r requirements.txt
```

## Environment setup

Copy `.env` and populate with GitHub OAuth credentials:
```
GITHUB_CLIENT_ID=...
GITHUB_CLIENT_SECRET=...
```

OAuth callback listens on `http://localhost:9876/callback`. Token is persisted to `~/.gitdummy_token.json`. Repo list is persisted to `~/.gitdummy_repos.json`.

---

## Architecture

### Entry point
`main.py` creates a `QStackedWidget` (`App`) that holds two top-level pages: `AuthPage` and `MainWindow`. `MainWindow` itself holds a `RepoPage` and `CommitViewPage` in its own `QStackedWidget`.

### Layer separation

| Layer | Location | Responsibility |
|---|---|---|
| Git data | `core/git_ops.py` | All `subprocess` git commands. Returns `(bool, str)` or `(bool, str, list, dict)`. Never touches Qt. |
| Git state tracking | `core/git_tracker.py` | `GitTracker` wraps GitPython. `graph_commits()` returns `(commits, branch_tip_map, local_only)`. `CommitInfo` dataclass lives here. |
| Auth | `auth/github_auth.py` | GitHub OAuth flow via local HTTP server on port 9876. Emits `auth_success(user: dict)` / `auth_failed(str)`. |
| Persistence | `core/repo_store.py`, `core/settings_store.py` | JSON files in `~`. |
| Theme | `styles/theme.py` | Single `COLORS` dict + `make_global_style()`. All UI files import from here. |
| UI pages | `ui/` | PyQt5 widgets. All heavy work is on background threads. |

### Threading model — critical rules

**All git operations run on background QThreads or `threading.Thread`.** The pattern for QThread workers:

```python
thread = QThread()
worker = _SomeWorker(...)
worker.moveToThread(thread)
thread.started.connect(worker.run)
worker.finished.connect(some_slot)
worker.finished.connect(thread.quit)
thread.finished.connect(self._on_thread_done)  # sets self._thread_ref = None
self._thread_ref = thread
self._worker_ref = worker
thread.start()
```

**Never call `worker.deleteLater()` or `thread.deleteLater()` — this causes double-free crashes.** Let Python GC manage lifetime via the instance references. Clear the thread ref in `_on_thread_done` (connected to `thread.finished`) so `isRunning()` is never called on a dead object.

**Never use `QTimer.singleShot(0, callback)` from a background thread** — use a proper `pyqtSignal` instead.

### CommitViewPage (`ui/commit_view.py`) — the main page

This is the largest file (~4000 lines). Key internal state:

- `_panel_op_active: bool` — blocks concurrent actions across all buttons. Set True on action start, False in the done-handler.
- `_navigating: bool` — blocks uncommitted-changes poll during checkout operations.
- `_branch_head_shas` / `_local_tip_shas` / `_local_tip_branch` — computed in `_on_loaded` from local branch refs. **Local tip is always the authoritative head** for actions; remote tip is display-only.
- `_last_head_sha` — tracks git HEAD. Cleared to `""` on close-panel ops so `load_graph` re-reads it fresh.
- `_jump_to_head: bool` — set by `_on_branch_op_done(close_panel=True)`, consumed in `_on_loaded` to scroll the canvas to HEAD.

Background polling:
- `_poll_timer` (30 s) → `_poll_remote()` → `_FetchWorker` → `_on_fetch_done` → `_start_load()` if remote changed.
- `_uncommitted_timer` (2 s) → `_poll_uncommitted()` → `_UncommittedRefreshWorker` → `_on_uncommitted_done`.

Signal naming convention: `_foo_done_sig = pyqtSignal(...)` for cross-thread signals; always declare the full type signature so PyQt5 dispatches correctly.

### Canvas (`ui/spatial_canvas.py`)

`CommitNode` and `BranchLabel` are `QGraphicsItem` subclasses. **`boundingRect()` must fully contain everything painted**, including the flag pole above start nodes (pole extends `START_R + 20` px above centre).

Lane algorithm (`_compute_lanes`): streaming topological-order assignment. Pre-seeds all branch tips into dedicated lanes before traversal. Lane 0 = primary (main/master). `branch_tip_map` keys are tip SHAs, values are display name lists.

`load_graph` → `_compute_lanes` → position all commits → draw spines → draw cross-lane edges → create `CommitNode` objects → draw text labels.

### Detail panel (`ui/detail_panel.py`)

`lock_actions()` / `unlock_actions()` disable/enable action buttons during ops. **`_save_stash_btn` and `_clear_stash_btn` are excluded from `unlock_actions()`** — their visibility is managed exclusively by `update_uncommitted_files()` / `refresh_stash_section()`. `show_commit()` always hides them on entry; the 2-second poll re-shows them if the commit has unsaved changes.

### git_ops.py conventions

- All functions return `(bool, str)` or `(bool, str, list, dict)` — never raise.
- Use `git rev-parse --abbrev-ref HEAD` for current branch (not `git branch --show-current` which requires git 2.22+). Check for `"HEAD"` meaning detached.
- On any failure path, always abort in-progress merges (`git merge --abort`) and unstage staged files (`git reset HEAD`) before returning so the repo is left clean.
- `push_branch` checks both `r.stdout + r.stderr` (combined) for `"rejected"` / `"non-fast-forward"` because git writes the rejection table to stdout, not stderr.

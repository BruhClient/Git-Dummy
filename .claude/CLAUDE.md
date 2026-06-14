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

There is no test suite or lint config in this repo.

## Environment setup

`.env` (gitignored) holds GitHub OAuth app credentials:
```
GITHUB_CLIENT_ID=...
GITHUB_CLIENT_SECRET=...
```

OAuth callback listens on `http://localhost:9876/callback`.

---

## Architecture

### Entry point
`main.py` builds a `QStackedWidget` (`App`) holding `AuthPage` and `MainWindow`. `MainWindow` itself holds a `RepoPage` and `CommitViewPage` in its own `QStackedWidget`. `main.py` also applies a Windows-specific workaround: it resolves the Qt plugins path to an 8.3 short path via `GetShortPathNameW` before setting `QT_QPA_PLATFORM_PLUGIN_PATH`, because the project directory contains characters Qt can't encode through the ANSI codepage.

### Layer separation

| Layer | Location | Responsibility |
|---|---|---|
| Git data | `core/ops/` (8 domain files) | All `subprocess` git commands. Returns `(bool, str)` or `(bool, str, list, dict)`. Never touches Qt. |
| Git state tracking | `core/git_tracker.py` | `GitTracker` wraps GitPython. `graph_commits()` returns `(commits, branch_tip_map, local_only)`. `CommitInfo` dataclass lives here. |
| Auth | `auth/github_auth.py` | GitHub OAuth flow via a local HTTP server on port 9876. Single-account model — `auth_success`/`auth_failed` signals; `logout()` clears the saved session. |
| Persistence | `core/storage/repo_store.py`, `core/storage/settings_store.py` | JSON files under `~`. |
| Collab cache | `core/storage/collab_cache.py` | TTL-based (1 h) cache for collaborator lists, `~/.evogit_collab_cache.json`. `get(url)` returns `(data | None, is_stale)`. |
| Theme | `styles/theme.py` | Single `COLORS` dict + `make_global_style()`. All UI files import from here. |
| UI pages | `ui/` | PyQt5 widgets. All heavy work runs on background threads. |

### Package structure

```
core/
  ops/              # base_ops, stash_ops, diff_ops, merge_ops, revert_ops,
  │                 #   branch_ops, github_ops, repo_ops — re-exported via __init__.py
  storage/          # collab_cache, repo_store, settings_store
  git_tracker.py    # GitTracker + CommitInfo dataclass

ui/
  canvas/           # SpatialCanvas, MiniMap, CommitNode/BranchLabel/EdgeItem,
  │                 #   lane_algorithm, constants (ORIENT_*, NODE_R, …)
  panels/           # DetailPanel, ChangesPanel, AllChangesPopup, diff_renderer,
  │                 #   SettingsPanel, PositionPanel, PullRequestsPanel
  dialogs/          # ConfirmDialog, CommitMessageDialog, conflict dialogs,
  │                 #   GitHubConnectDialog, CloneDialog, InitDialog, PROpenWizard
  workers/          # commit_workers (QObject workers), repo_workers
  components/       # avatar cache, LoadingOverlay, HeaderBar, ZoomBar, Legend,
  │                 #   CollaboratorPanel, Toast, ExploreBanner, NoRemoteView
  commit_view.py    # CommitViewPage (~3300 lines) — main repo/graph page
  repo_page.py      # RepoPage — repo list / picker
  main_window.py    # MainWindow
  auth_page.py      # AuthPage

auth/
  github_auth.py    # single-account OAuth flow
styles/
  theme.py          # COLORS, make_global_style(), named style constants
```

> **Note:** `ui/spatial_canvas.py` (top-level, ~1300 lines) is a stale, unused duplicate.
> The live canvas is `ui/canvas/spatial_canvas.py`, exported via `ui/canvas/__init__.py`.

### Persisted files (under `~`)
- `.evogit_accounts.json` — saved OAuth session (legacy single-token file: `.evogit_token.json`)
- `.evogit_repos.json` — saved repo list
- `.evogit_settings.json` — per-repo settings (e.g. `repo_orientations`, `default_branch`)
- `.evogit_collab_cache.json` — collaborator TTL cache
- `.evogit_cache/avatars/` — avatar image cache (MD5-keyed PNGs)

### Threading model — critical rules

**All git operations run on background `QThread`s or `threading.Thread`.** The pattern for QThread workers (see `ui/workers/commit_workers.py` for the worker classes):

```python
thread = QThread()
worker = _SomeWorker(...)
worker.moveToThread(thread)
thread.started.connect(worker.run)
worker.finished.connect(some_slot)
worker.finished.connect(thread.quit)
thread.finished.connect(self._on_thread_done)  # clears self._thread_ref
self._thread_ref = thread
self._worker_ref = worker
thread.start()
```

- **Never call `worker.deleteLater()` or `thread.deleteLater()`** — let Python GC manage lifetime via the held references; clear the ref in the `thread.finished` handler so `isRunning()` is never called on a dead object.
- **Never use `QTimer.singleShot(0, callback)` from a background thread** — use a `pyqtSignal` instead.
- Before starting a new worker of a given kind, check `self._xxx_thread and self._xxx_thread.isRunning()` and skip/queue if one is already running.

### CommitViewPage (`ui/commit_view.py`)

The main page — loads a repo, builds the commit graph, and wires up all actions (checkout, branch, merge, stash, revert, push/pull, PRs, settings).

Key state:
- `_panel_op_active: bool` — blocks concurrent detail-panel actions; set `True` on action start, `False` in the done-handler.
- `_navigating: bool` — blocks the uncommitted-changes poll during checkout operations.
- `_branch_head_shas` / `_local_tip_shas` / `_local_tip_branch` — computed in `_on_loaded` from local branch refs (`git for-each-ref refs/heads/`, via subprocess — not GitPython, which caches stale tip SHAs after back-to-back merges). **Local tip is authoritative for actions; remote tip is display-only.**
- `_last_head_sha` — tracks git HEAD; cleared to `""` to force `load_graph` to re-read it fresh.

Background polling:
- `_poll_timer` (30 s) → `_poll_remote()` → `_FetchWorker` → `_on_fetch_done` → `_start_load()` if the remote changed. `_FetchWorker` only runs `git fetch` (via `GitTracker.fetch_with_author()`) and reports whether any remote ref moved plus a best-guess "who pushed" author — it does **not** merge or fast-forward the local branch. A reload shows the updated `origin/<branch>` tip on the graph, but the local branch stays where it was until the user explicitly pulls/merges.
- `_uncommitted_timer` (2 s) → `_poll_uncommitted()` → `_UncommittedRefreshWorker` → `_on_uncommitted_done`.
- `load_repo()` also calls `_poll_remote()` immediately on entry so a behind-remote branch syncs without waiting for the first 30 s tick.

Signal convention: declare full type signatures, e.g. `pyqtSignal(bool, str)`, so PyQt5 dispatches correctly across threads.

### Canvas (`ui/canvas/spatial_canvas.py`)

`CommitNode`, `BranchLabel`, and `EdgeItem` are `QGraphicsItem` subclasses in `ui/canvas/graphics_items.py`. `boundingRect()` must fully contain everything painted, including the flag pole above start nodes (extends `START_R + 20` px above centre).

Lane algorithm (`_compute_lanes` in `ui/canvas/lane_algorithm.py`): streaming topological-order assignment over commits in `--topo-order` (children before parents).
- `branch_tip_map`: `{tip_sha: [display_names]}`. When two tips share a name (e.g. local `main` and `origin/main` point to different commits), `primary_tip` selection walks the newest candidate's first-parent chain — if the oldest candidate is reachable, the relationship is linear ("local ahead/behind") and the newest wins; otherwise the branches have diverged and the oldest (established history) stays on lane 0.
- Lane 0 is reserved for the primary branch (`main`/`master`). Non-main branch tips are pre-seeded into their own lanes before the streaming pass. A second pass walks 2nd-parent (merge) chains to attribute PR commits back to their source branch (`commit_owner`), with a final consolidation pass moving misattributed commits into their owning branch's lane.

`load_graph()` → `_compute_lanes` → position commits → draw spines → draw cross-lane edges → create `CommitNode`s → draw labels. Four orientations: `ORIENT_TB` / `ORIENT_BT` / `ORIENT_LR` / `ORIENT_RL` (in `ui/canvas/constants.py`, re-exported via `ui/canvas/__init__.py`). `MiniMap` (`ui/canvas/minimap.py`) mirrors the scene viewport.

### Detail panel (`ui/panels/detail_panel.py`)

`lock_actions()` / `unlock_actions()` disable/enable action buttons during ops. `_save_stash_btn` / `_clear_stash_btn` are excluded from `unlock_actions()` — their visibility is managed only by `update_uncommitted_files()` / `refresh_stash_section()`.

Diff rendering helpers (`_DiffLine`, `_Row`, `_MiniBar`, `_VScrollArea`, fade animations) live in `ui/panels/diff_renderer.py`. The slide-in diff panel is `ChangesPanel` (`ui/panels/changes_panel.py`); the full-screen overlay is `AllChangesPopup` (`ui/panels/all_changes_popup.py`).

### Settings panel (`ui/panels/settings_panel.py`)

Exposes `_default_branch: str` (default `"main"`, seeded from `get_default_branch()` then refreshed from the GitHub API). `commit_view.py` reads it via `getattr(self._settings_panel, "_default_branch", "main")`.

### core/ops/ conventions

- All functions return `(bool, str)` or `(bool, str, list, dict)` — never raise.
- Use `git rev-parse --abbrev-ref HEAD` for current branch (works on git < 2.22, unlike `git branch --show-current`); a result of `"HEAD"` means detached.
- On any failure path, abort in-progress merges (`git merge --abort`) and unstage (`git reset HEAD`) before returning so the repo is left clean.
- `push_branch` (`core/ops/github_ops.py`) checks `stdout + stderr` combined for `"rejected"` / `"non-fast-forward"` — git writes the rejection table to stdout, not stderr.
- Domain split: `base_ops` (checkout, reset, conflict helpers), `stash_ops`, `diff_ops`, `merge_ops`, `revert_ops`, `branch_ops`, `github_ops`, `repo_ops`. `core/ops/__init__.py` re-exports everything.

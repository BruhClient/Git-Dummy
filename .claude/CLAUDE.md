# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Running the app

```bash
# Activate the venv first
venv\Scripts\activate        # Windows
# source venv/bin/activate   # macOS/Linux

python main.py
```

## Debugging — use print statements liberally

**Print statements are the primary diagnostic tool in this project.** There is no debugger attached, no test suite, and no logging framework — `print()` to stdout is the fastest way to understand what's happening, especially across threads.

Where to put them:
- **Worker `run()` methods** (`ui/workers/commit_workers.py`) — print the inputs and the result tuple `(ok, err)` from every `core/ops` call so you can see exactly what git returned.
- **Done-handlers in `commit_view.py`** — print the signal payload on arrival and the current value of `_panel_op_active` / `_navigating` to catch flag-reset bugs.
- **`core/ops/` functions** — print the exact subprocess command list and the raw `stdout` / `stderr` before the function returns, so you know what git actually said vs. what the caller received.
- **Canvas / lane algorithm** — print lane assignments and `branch_tip_map` inside `_compute_lanes` to diagnose mis-attributed commits.

When you add a print, be specific: include the function name and a short label so the output is scannable (`print(f"[push_branch] cmd={cmd} ok={ok} err={err[:120]}")`). Remove diagnostic prints before committing — they're a temporary tool, not permanent logging.

## Installing dependencies

```bash
pip install -r requirements.txt
```

There is no test suite or lint config in this repo.

## Environment setup

No `.env` file is required. Authentication uses GitHub Personal Access Tokens (see Auth section below).

---

## Architecture

### Entry point
`main.py` builds a `QStackedWidget` (`App`) holding `AuthPage` and `MainWindow`. `MainWindow` itself holds a `RepoPage` and `CommitViewPage` in its own `QStackedWidget`. `main.py` also applies a Windows-specific workaround: it resolves the Qt plugins path to an 8.3 short path via `GetShortPathNameW` before setting `QT_QPA_PLATFORM_PLUGIN_PATH`, because the project directory contains characters Qt can't encode through the ANSI codepage.

### Auth (`auth/github_auth.py`)

Authentication uses GitHub **Personal Access Tokens** (PATs) — no OAuth server, no browser redirect, no client_id/secret.

**Sign-in flow:**
1. User opens app → if saved token exists, validate it against `GET /api.github.com/user` → auto-login
2. If no saved token → show sign-in page with token input field
3. "Create a token on GitHub" link opens `https://github.com/settings/tokens/new?scopes=repo,read:user&description=Evo%20Git` with pre-selected scopes
4. User pastes token → `add_account(token)` validates on a background thread:
   - Calls `GET /user`, reads `X-OAuth-Scopes` response header
   - Checks `REQUIRED_SCOPES = {"repo", "read:user"}` — rejects tokens missing either scope
   - On success: saves account, emits `auth_success(user_dict)`

**Multi-account:** Storage supports multiple accounts in `~/.evogit_accounts.json`. TopNav popup lists all accounts with switch/add/sign-out actions. `switch_account(login)` re-validates the token and emits `auth_success`. `get_accounts()` returns the list (without tokens) for the UI.

**Token expiration:** `token_expired(str)` signal emitted when a saved token fails validation. Any 401 from the GitHub API during normal use surfaces as an error toast.

**Signals:** `auth_success(dict)`, `auth_failed(str)`, `token_expired(str)` — downstream code receives the same user dict as before (`access_token`, `login`, `name`, `avatar_url`).

### Layer separation

| Layer | Location | Responsibility |
|---|---|---|
| Git data | `core/ops/` (8 domain files) | All `subprocess` git commands. Returns `(bool, str)` or `(bool, str, list, dict)`. Never touches Qt. |
| Git state tracking | `core/git_tracker.py` | `GitTracker` wraps GitPython. `graph_commits()` returns `(commits, branch_tip_map, local_only)`. `CommitInfo` dataclass lives here. |
| Auth | `auth/github_auth.py` | GitHub PAT-based auth with multi-account support. `auth_success`/`auth_failed`/`token_expired` signals. |
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
  commit_view.py         # CommitViewPage (~2150 lines) — main repo/graph page
  commit_view_pr.py      # _PRMixin — PR inbox, wizard, merge handlers (extracted from commit_view.py)
  commit_view_widgets.py # Presentation-only QWidget subclasses (extracted from commit_view.py)
  repo_page.py           # RepoPage — repo list / picker
  main_window.py         # MainWindow
  auth_page.py           # AuthPage

auth/
  github_auth.py    # PAT-based auth, multi-account
styles/
  theme.py          # COLORS, make_global_style(), named style constants
```

### Persisted files (under `~`)
- `.evogit_accounts.json` — saved PAT accounts (multi-account: `{"active": "login", "accounts": {...}}`)
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

Background polling & auto-pull:
- `_poll_timer` (30 s) → `_poll_remote()` → `_FetchWorker` → `_on_fetch_done`. When remote refs changed, `_on_fetch_done` calls `_try_auto_pull()` which attempts to fast-forward the current branch if the working tree is clean. On success the graph reloads seamlessly. On failure (diverged, network error, dirty tree) an error toast is shown and the graph reloads with dimmed remote-only commits + Pull/Sync buttons available.
- `_uncommitted_timer` (2 s) → `_poll_uncommitted()` → `_UncommittedRefreshWorker` → `_on_uncommitted_done`.
- `load_repo()` also calls `_poll_remote()` immediately on entry so a behind-remote branch syncs without waiting for the first 30 s tick.

Signal convention: declare full type signatures, e.g. `pyqtSignal(bool, str)`, so PyQt5 dispatches correctly across threads.

### Canvas (`ui/canvas/spatial_canvas.py`)

`CommitNode`, `BranchLabel`, and `EdgeItem` are `QGraphicsItem` subclasses in `ui/canvas/graphics_items.py`. `boundingRect()` must fully contain everything painted, including the flag pole above start nodes (extends `START_R + 20` px above centre).

Lane algorithm (`_compute_lanes` in `ui/canvas/lane_algorithm.py`): streaming topological-order assignment over commits in `--topo-order` (children before parents).
- `branch_tip_map`: `{tip_sha: [display_names]}`. When two tips share a name (e.g. local `main` and `origin/main` point to different commits), `primary_tip` selection walks the newest candidate's first-parent chain — if the oldest candidate is reachable, the relationship is linear ("local ahead/behind") and the newest wins; otherwise the branches have diverged and the **remote tip** gets lane 0 (see diverged branch rules below).
- Lane 0 is reserved for the primary branch (`main`/`master`). Non-main branch tips are pre-seeded into their own lanes before the streaming pass (remote tips seeded before local tips). A second pass walks 2nd-parent (merge) chains to attribute PR commits back to their source branch (`commit_owner`), with a final consolidation pass moving misattributed commits into their owning branch's lane.
- **Sibling-depth normalization**: lanes sharing the same `_branch_base` name (e.g. local and remote tips of "feature-branch") are normalized to the same depth so they sort adjacent in the final remap. Remote-tip lanes sort before local-tip lanes at the same depth.

`load_graph()` → `_compute_lanes` → position commits → draw spines → draw cross-lane edges → create `CommitNode`s → draw labels. Four orientations: `ORIENT_TB` / `ORIENT_BT` / `ORIENT_LR` / `ORIENT_RL` (in `ui/canvas/constants.py`, re-exported via `ui/canvas/__init__.py`). `MiniMap` (`ui/canvas/minimap.py`) mirrors the scene viewport.

### Detail panel (`ui/panels/detail_panel.py`)

`lock_actions()` / `unlock_actions()` disable/enable action buttons during ops. `_save_stash_btn` / `_clear_stash_btn` are excluded from `unlock_actions()` — their visibility is managed only by `update_uncommitted_files()` / `refresh_stash_section()`.

Diff rendering helpers (`_DiffLine`, `_Row`, `_MiniBar`, `_VScrollArea`, fade animations) live in `ui/panels/diff_renderer.py`. The slide-in diff panel is `ChangesPanel` (`ui/panels/changes_panel.py`); the full-screen overlay is `AllChangesPopup` (`ui/panels/all_changes_popup.py`).

### Diverged branch handling

When a branch's local and remote tips point to different commits and neither is an ancestor of the other, the branch is **diverged**. The app handles this with specific visual and action rules.

**Visual rules:**
- **Remote tip goes straight** — keeps the branch's existing lane (lane 0 for main, branch lane for others). Pre-divergence commits stay on this lane connected by the spine.
- **Local tip branches off** — gets a new adjacent lane with a dashed creation edge back to the common ancestor. No flag on diverged tips (divergence ≠ new branch).
- **No dimming** for diverged commits — both sides render at full opacity. Dimming is reserved for the "behind" case only (remote has commits local hasn't pulled).
- `_draw_branch_creation_edges` in `spatial_canvas.py` identifies `diverged_tip_shas` (tips sharing a `_branch_base` name) and draws dashed edges for them while excluding them from `start_shas` (no flags).

**Action button matrix — Upload / Pull / Sync are mutually exclusive:**

| Scenario | Commit | Buttons |
|---|---|---|
| In sync | HEAD | Create branch, Hard/Soft Revert, Merge into |
| Ahead | HEAD (unpushed) | **Upload**, Create branch, Hard/Soft Revert, Merge into |
| Behind (auto-pull failed) | HEAD (stale) | **Pull latest**, Create branch, Hard/Soft Revert, Merge into |
| Diverged | Local tip | **Sync with remote**, Create branch, Hard/Soft Revert, Merge into |
| Diverged | Remote tip | *(read-only view, no special buttons)* |
| Behind | Remote-only (dimmed) | **Pull latest** only |
| Any | Historical commit | Go to snapshot, Create branch |
| Any | Other branch tip | Go to snapshot, Create branch, Merge into, Delete branch |

**Operation definitions:**
- **Upload** (`git push`) — sends local commits to remote. Only when ahead.
- **Pull latest** (`pull_ff` → `git fetch origin branch:branch`) — fast-forwards local to match remote. Only when behind. Undims remote commits, no merge commit.
- **Sync with remote** (`merge_branch(path, f"origin/{branch}")`) — merges remote into local, creates a merge commit. Only when diverged. Only shown on the local tip, not the remote tip.

**Divergence detection** in `_on_commit_detail_ready` uses first-parent reachability walks (not topo-order comparison) to correctly distinguish behind vs diverged. The `_future_shas` computation in `spatial_canvas.py` also uses reachability to skip diverged branches (no dimming for diverged).

**Stash migration**: both `pull_ff` and `_on_sync_branch` call `migrate_stash_after_pull(path, old_head)` after success, moving any stash from the old tip to the new HEAD.

### Settings panel (`ui/panels/settings_panel.py`)

Exposes `_default_branch: str` (default `"main"`, seeded from `get_default_branch()` then refreshed from the GitHub API). `commit_view.py` reads it via `getattr(self._settings_panel, "_default_branch", "main")`.

### core/ops/ conventions

- All functions return `(bool, str)` or `(bool, str, list, dict)` — never raise.
- Use `git rev-parse --abbrev-ref HEAD` for current branch (works on git < 2.22, unlike `git branch --show-current`); a result of `"HEAD"` means detached.
- On any failure path, abort in-progress merges (`git merge --abort`) and unstage (`git reset HEAD`) before returning so the repo is left clean.
- `push_branch` (`core/ops/github_ops.py`) checks `stdout + stderr` combined for `"rejected"` / `"non-fast-forward"` — git writes the rejection table to stdout, not stderr.
- Domain split: `base_ops` (checkout, reset, conflict helpers), `stash_ops`, `diff_ops`, `merge_ops`, `revert_ops`, `branch_ops`, `github_ops`, `repo_ops`. `core/ops/__init__.py` re-exports everything.

## Current development focus: evo-git-polish

The active improvement initiative for this codebase has three aims:

- **Polish** — visual/UX consistency, spacing, copy, interaction flows across `ui/panels/*`, `ui/dialogs/*`, `ui/components/*`.
- **Proactive bug-hunting** — find and fix bugs that haven't been reported yet, not just reactive fixes. The ranked backlog in `.claude/agents/action-catalog.md` (Part 2) is the starting checklist; there will be more.
- **Beginner/non-coder UX** — make the app approachable for people who don't know git: plain-language labels, tooltips explaining git concepts (commit, branch, merge, stash), simplified default views, friendlier error messages.

Agent team members most relevant to this initiative: `ui-ux-polish` (visual/UX), `git-actions-debugger` (bug-hunting from the action catalog backlog), and `code-quality-refactor` (structural cleanup that unblocks polish work).

## Test repository

A dedicated repo for staging git scenarios used during development/testing.

- **Remote:** https://github.com/BruhClient/test
- **Local path:** `C:/Users/travi/Desktop/Dev/test`

When the user requests a scenario (e.g. "set up a merge conflict", "show a diverged branch"), update this repo's git history/files to reflect that state, then push so the app can load it and demonstrate the scenario.

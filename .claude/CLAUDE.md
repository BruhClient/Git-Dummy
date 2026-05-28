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
`main.py` creates a `QStackedWidget` (`App`) that holds two top-level pages: `AuthPage` and `MainWindow`. `MainWindow` itself holds a `RepoPage` and `CommitViewPage` in its own `QStackedWidget`. `main.py` also applies a Windows-specific workaround to encode the Qt plugins path as an 8.3 short path before setting `QT_QPA_PLATFORM_PLUGIN_PATH`, needed because the project directory contains emoji.

### Layer separation

| Layer | Location | Responsibility |
|---|---|---|
| Git data | `core/ops/` (8 domain files) | All `subprocess` git commands. Returns `(bool, str)` or `(bool, str, list, dict)`. Never touches Qt. |
| Git state tracking | `core/git_tracker.py` | `GitTracker` wraps GitPython. `graph_commits()` returns `(commits, branch_tip_map, local_only)`. `CommitInfo` dataclass lives here. |
| Auth | `auth/github_auth.py` | GitHub OAuth flow via local HTTP server on port 9876. Emits `auth_success(user: dict)` / `auth_failed(str)`. |
| Persistence | `core/storage/repo_store.py`, `core/storage/settings_store.py` | JSON files in `~`. |
| Collab cache | `core/storage/collab_cache.py` | TTL-based (1 h) cache for collaborator lists, stored at `~/.gitdummy_collab_cache.json`. `get(url)` returns `(data | None, is_stale)`. |
| Theme | `styles/theme.py` | Single `COLORS` dict + `make_global_style()`. All UI files import from here. Named style constants (`BTN_PRIMARY`, `INPUT_STYLE`, etc.) live here too. |
| UI pages | `ui/` | PyQt5 widgets. All heavy work is on background threads. |

### Package structure

```
core/
  ops/              # 8 domain files: base_ops, stash_ops, diff_ops, merge_ops,
  │                 #   revert_ops, branch_ops, github_ops, repo_ops
  storage/          # collab_cache, repo_store, settings_store
  git_tracker.py    # GitTracker + CommitInfo dataclass

ui/
  canvas/           # SpatialCanvas, MiniMap, CommitNode/BranchLabel/EdgeItem,
  │                 #   lane_algorithm, constants (ORIENT_*, NODE_R, …)
  panels/           # DetailPanel, ChangesPanel, AllChangesPopup, diff_renderer
  │                 #   SettingsPanel, PositionPanel, PullRequestsPanel
  dialogs/          # ConfirmDialog, CommitMessageDialog, conflict dialogs,
  │                 #   _GitHubConnectDialog, CloneDialog, InitDialog, PROpenWizard
  workers/          # commit_workers (9 QObject workers), repo_workers
  components/       # avatar cache, LoadingOverlay, Header, ZoomBar, Legend,
  │                 #   CollaboratorPanel, Toast, ExploreBanner, NoRemoteView
  commit_view.py    # CommitViewPage (~2400 lines) — main page
  repo_page.py      # RepoPage
  main_window.py    # MainWindow
  auth_page.py      # AuthPage
  settings_page.py  # SettingsPage

auth/
  github_auth.py    # OAuth flow
styles/
  theme.py          # COLORS, make_global_style(), named style constants
```

### User-facing files at `~`
- `~/.gitdummy_token.json` — persisted OAuth token
- `~/.gitdummy_repos.json` — persisted repo list
- `~/.gitdummy_collab_cache.json` — collaborator TTL cache
- `~/.gitdummy_cache/avatars/` — avatar image cache (MD5-keyed PNGs)

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

This is the largest file (~2400 lines). Key internal state:

- `_panel_op_active: bool` — blocks concurrent actions across all buttons. Set True on action start, False in the done-handler.
- `_navigating: bool` — blocks uncommitted-changes poll during checkout operations.
- `_branch_head_shas` / `_local_tip_shas` / `_local_tip_branch` — computed in `_on_loaded` from local branch refs. **Local tip is always the authoritative head** for actions; remote tip is display-only.
- `_last_head_sha` — tracks git HEAD. Cleared to `""` on close-panel ops so `load_graph` re-reads it fresh.
- `_jump_to_head: bool` — set by `_on_branch_op_done(close_panel=True)`, consumed in `_on_loaded` to scroll the canvas to HEAD.

Background polling:
- `_poll_timer` (30 s) → `_poll_remote()` → `_FetchWorker` → `_on_fetch_done` → `_start_load()` if remote changed.
- `_uncommitted_timer` (2 s) → `_poll_uncommitted()` → `_UncommittedRefreshWorker` → `_on_uncommitted_done`.

Signal naming convention: `_foo_done_sig = pyqtSignal(...)` for cross-thread signals; always declare the full type signature so PyQt5 dispatches correctly.

Avatar data is loaded by `_AvatarWorker` and cached in the module-level `_AVATAR_CACHE` dict in `ui/components/avatar.py` (keyed by GitHub avatar URL). PNGs are written to `~/.gitdummy_cache/avatars/`. All workers live in `ui/workers/commit_workers.py`.

### Canvas (`ui/canvas/spatial_canvas.py`)

`CommitNode`, `BranchLabel`, and `EdgeItem` are `QGraphicsItem` subclasses defined in `ui/canvas/graphics_items.py`. **`boundingRect()` must fully contain everything painted**, including the flag pole above start nodes (pole extends `START_R + 20` px above centre).

Lane algorithm (`_compute_lanes` in `ui/canvas/lane_algorithm.py`): streaming topological-order assignment. Pre-seeds all branch tips into dedicated lanes before traversal. Lane 0 = primary (main/master). `branch_tip_map` keys are tip SHAs, values are display name lists.

`load_graph` → `_compute_lanes` → position all commits → draw spines → draw cross-lane edges → create `CommitNode` objects → draw text labels.

Four orientations are supported: `ORIENT_TB` / `ORIENT_BT` / `ORIENT_LR` / `ORIENT_RL` (defined in `ui/canvas/constants.py`, exported via `ui/canvas/__init__.py`). `MiniMap` is a small overlay widget in `ui/canvas/minimap.py` that mirrors the scene viewport. Node/lane sizing constants (`NODE_R`, `START_R`, `BADGE_R`, `LANE_W`, `ROW_H`) also live in `ui/canvas/constants.py`.

### Detail panel (`ui/panels/detail_panel.py`)

`lock_actions()` / `unlock_actions()` disable/enable action buttons during ops. **`_save_stash_btn` and `_clear_stash_btn` are excluded from `unlock_actions()`** — their visibility is managed exclusively by `update_uncommitted_files()` / `refresh_stash_section()`. `show_commit()` always hides them on entry; the 2-second poll re-shows them if the commit has unsaved changes.

Diff rendering utilities (constants, helpers, `_DiffLine`, `_Row`, `_MiniBar`, `_VScrollArea`, fade animations, dividers) live in `ui/panels/diff_renderer.py`. The slide-in diff panel is `ChangesPanel` in `ui/panels/changes_panel.py`. The full-screen overlay is `AllChangesPopup` in `ui/panels/all_changes_popup.py`.

### Settings panel (`ui/panels/settings_panel.py`)

Exposes `_default_branch: str` (defaults to `"main"`, seeded from `get_default_branch()` on load, refreshed from GitHub API). `commit_view.py` reads this attribute directly via `getattr(self._settings_panel, "_default_branch", "main")` wherever the default branch is needed.

### core/ops/ conventions

- All functions return `(bool, str)` or `(bool, str, list, dict)` — never raise.
- Use `git rev-parse --abbrev-ref HEAD` for current branch (not `git branch --show-current` which requires git 2.22+). Check for `"HEAD"` meaning detached.
- On any failure path, always abort in-progress merges (`git merge --abort`) and unstage staged files (`git reset HEAD`) before returning so the repo is left clean.
- `push_branch` (in `core/ops/github_ops.py`) checks both `r.stdout + r.stderr` (combined) for `"rejected"` / `"non-fast-forward"` because git writes the rejection table to stdout, not stderr.
- Domain split: `base_ops` (checkout, reset, conflict helpers), `stash_ops`, `diff_ops`, `merge_ops`, `revert_ops`, `branch_ops`, `github_ops`, `repo_ops`. `core/ops/__init__.py` re-exports everything.

---

## Working Preferences

These preferences apply to how Claude Code should work in this project.

### Print-first debugging protocol (highest priority)
Before proposing *any* fix — even a one-liner — reach for print statements as the primary diagnostic tool. The workflow:
1. **Draft a print plan**: identify the 1–3 key checkpoints that would confirm or refute the suspected cause.
2. **Tell the user exactly where to add the prints** (file, function, line) and what value to print.
3. **Tell the user how to trigger them** (which UI action, which repo state, what to do in the app).
4. **Wait for the pasted output before writing any fix.**

This bypasses all assumptions. One round of runtime data is worth more than any amount of code reading or speculation.

Apply this even for bugs that seem obvious. The cost of a wrong fix is always higher than one extra "paste the output" turn.

### User preferences
- **Ask clarifying questions early in plan mode** — before settling on an approach, use `AskUserQuestion` to confirm the actual goal. One question upfront saves multiple fix-and-revert cycles.
- **For data-display bugs, print the actual data before proposing any fix** — when the symptom is "wrong value shown" (wrong dot, wrong badge, wrong SHA), add a print at the render callsite *first*, before writing any fix code. One turn of runtime data beats four turns of speculation.
- **Two consecutive failed fixes → stop and reconsider the approach** — if the second attempt in the same strategy fails, don't try a third variant. Step back and ask whether the chosen tool or data source is fundamentally wrong.
- **Before fetching new data, check what's already in scope** — look at the current function's parameters and local variables before adding subprocess calls or new iterations. The answer is often already computed and passed in.
- **For wrong-set-membership bugs, print the source data that built the set** — when "item X is incorrectly in set S," print what caused X to be included (e.g. `branch_tip_map.get(sha)` for a `_remote_tip_shas` bug), not just `x in S`. Without knowing the inclusion cause, the fix targets the wrong entry point and fails for a different input case.
- **Before fixing a value-computation bug, enumerate all code paths that reach the fix site** — if a fix must work on every trigger, list every code path (e.g. full-reload vs. early-return) and verify the key variable's state on each before implementing. A fix that works on path A may silently break on path B if that path has stale or uninitialized data.

### Speed & focus
- **Skip Explore agents for targeted bugs** — if a file is already known (e.g. `ui/canvas/spatial_canvas.py` for a canvas bug), read the specific class or function directly instead of launching a broad agent sweep.
- **Skip Plan agents for small changes** — 1–5 line fixes don't need a Plan agent. Read the relevant section → fix → verify.
- **Use screenshots/images as the primary diagnostic tool** — map the visual symptom directly to rendering code rather than doing broad exploration first.

### Bug-fixing workflow (follow this order every time)
1. **Understand the problem** — ask clarifying questions before touching any code. Confirm what the user sees, what they expect, and which specific element/data is wrong.
2. **Add print statements — always, not just "if needed"** — before proposing any fix, draft a print plan (see *Print-first debugging protocol* above). Identify 1–3 checkpoints, specify the exact file/function/line, explain how to trigger, and wait for output. Runtime values reveal the cause in one turn; guessing costs many turns.
3. **Identify all root causes** — list every plausible cause before picking one. Don't commit to a fix until the cause list is complete.
4. **Test one fix at a time** — implement and test each candidate fix individually. If it doesn't work, move to the next cause on the list. Don't stack multiple speculative fixes.

### Debugging approach
- **Cross-reference sibling code first** — before analyzing a bug deeply, check if the same file already has a correct implementation for a related case (e.g. `ORIENT_TB` already had the right edge routing; `ORIENT_LR` just needed to match it).
- **For git command errors, reason about command semantics** — instead of theorising about all possible causes, ask "which command avoids this failure mode entirely?" (e.g. `git read-tree --reset -u` has no pathspec matching → no pathspec error).
- **Smallest viable fix first** — propose the minimal code change that addresses the root cause before considering larger refactors.

### Diagnostic shortcuts
- **Add print statements before any fix attempt, not as a last resort** — at the first
  sign of a bug, draft a print plan: name the exact file, function, and line; say what
  to print; and explain how to trigger it. E.g. "add
  `print('remote_tip_shas:', self._remote_tip_shas)` before `load_graph`, then open any
  repo and paste what appears in the terminal." Do this *before* reading more code or
  proposing a fix. Runtime values surface the cause in one turn; any other approach risks
  multiple wasted fix cycles. Remove the prints once the cause is confirmed.
- **Ask "which visual element?" before any rendering diagnosis** — "tip", "dot", "flag",
  "ring" are all distinct UI elements with separate code paths. One focused question
  eliminates large amounts of code reading.
- **"I see a random [X]" → ask what kind of [X] before searching for code** — when a
  user reports "random branches", the right first question is "what do they look like —
  a text label, a visual lane/column, a filter entry?" Each is a completely different
  code path. Jumping straight to "where does this text come from?" wastes cycles when
  the complaint is about a rendered structure, not a string.
- **Label vs. structure are separate code paths in the canvas** — a branch *label*
  (text/pill) and a branch *lane* (spine + commit nodes) are rendered independently.
  Fixing the label fallback (`f"branch-{lane_idx}"`) did not touch the lane rendering.
  Always confirm: "is the problem the text string, or the visual column itself?"
- **User names persist after the artifact changes** — if the user called something
  "branch-7" before a fix, they will keep calling it "branch-7" after. "I still see
  branch-7" does NOT mean the original text is still there; it may mean the underlying
  visual structure is still there under the same nickname. Ask "do you still see the
  *text* branch-7, or the column of commits you were calling branch-7?"
- **"Works in closed testing, not in real repo" → ask what's structurally different first**
  — the answer directly names the missing case (e.g. real repo has remote-only branches;
  test repo has only local ones). Do not trace hypothetical scenarios until the structural
  difference is known.
- **"It didn't work" → ask which specific symptom persists before re-analysing** — the
  user may be describing a different remaining symptom, not the original bug. One question:
  "is [the specific old symptom] still visible?"
- **For "field tracked but not rendered" bugs: grep the render method for the field name
  first** — e.g. `grep _is_remote_tip` in `CommitNode.paint` shows instantly whether it is
  drawn. Reading the full paint method line-by-line is always slower.
- **Lane algorithm bugs in real repos: add a one-line debug print instead of mental-tracing**
  — `print({s[:8]: l for s, l in assignment.items() if s in branch_tip_map})` after
  `_compute_lanes` immediately shows every branch-tip → lane assignment. Mental traces of
  4+ branch repos are error-prone.
- **When fixing a regression, ask "when should this NOT apply?"** — the v3 phantom fix
  correctly applied to branch-tip commits but was erroneously applied to all commits.
  Framing the question as "under what condition is this logic wrong?" pointed straight to
  `elif sha in branch_tip_map:`.

### Past failures (do not retry)
- **Fixing a label when the complaint was about a lane** — "random branch-7" was
  reported as a visual branch column. The first fix targeted the text fallback
  (`f"branch-{lane_idx}"`) instead of the lane rendering. This changed the label to
  blank but left the ghost column visible, requiring two extra turns to get to the
  real fix (filtering unnamed-lane commits from `load_graph`). The correct first move
  was to ask "is it the *text* or the *visual column* that bothers you?"
- **v2: pre-seeding alone** — fixes closed-testing A→B→C but not real repos. The phantom
  (`lanes[lane_idx] = parent0`) still creates harmful duplicates when `parent0` is already
  pre-seeded. Pre-seeding is necessary but not sufficient.
- **v3: phantom → None for all commits** — setting `lanes[lane_idx] = None` inside the
  `parent0 in branch_tip_map` block fires for ordinary main commits whose parent happens
  to be a pre-seeded branch tip (e.g. M6 → M5 where M5 is also a "hotfix" tip). This
  closes main's lane prematurely, pushing all subsequent main commits onto the wrong lane.
  The fix (v4) is `elif sha in branch_tip_map:` — only apply collision avoidance when the
  *current* commit is itself a branch tip.
- **Mental-tracing 4+ branch repos to find lane bugs** — traces of "asd from main" all
  look clean even when the real bug exists. Use `print({s[:8]: l for s, l in
  assignment.items() if s in branch_tip_map})` instead.
- **Re-opening root-cause analysis when user says "it didn't work"** — the remaining issue
  is almost always a *different* symptom, not the original bug. Ask which specific symptom
  persists first.
- **Reading paint() line-by-line to find a missing draw call** — grep the field name
  directly; reading the whole method is always slower.

### Planning
- **Plan mode is for genuine design decisions**, not for single-file line changes. If the change is obvious after reading the relevant code, go straight to ExitPlanMode with a concise plan and implement immediately after approval.

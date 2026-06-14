# Evo Git — Subagent Team

Four specialized subagents for working on this PyQt5 git visualizer. Claude Code auto-delegates to one of these based on the task description, or you can invoke explicitly: "use `<agent-name>` to ...".

| Agent | Model | Key tools | Scope |
|---|---|---|---|
| [`git-actions-debugger`](git-actions-debugger.md) | sonnet | Read, Edit, Write, Grep, Glob, Bash, PowerShell, TodoWrite | Bugs in git operations (`core/ops/*`, `git_tracker.py`) and the in-app action workflow — QThread orchestration, `_panel_op_active`/`_navigating` flags, dialogs in `commit_view.py`. |
| [`canvas-visualizer-debugger`](canvas-visualizer-debugger.md) | sonnet | Read, Edit, Write, Grep, Glob, Bash, PowerShell, TodoWrite | Bugs in the commit graph visualizer — `ui/canvas/*` (lane algorithm, graphics items, minimap, orientation), `GitTracker.graph_commits()`, `load_graph()`. |
| [`ui-ux-polish`](ui-ux-polish.md) | sonnet | Read, Edit, Write, Grep, Glob, Bash, PowerShell, TodoWrite | Visual/UX improvements — `ui/panels/*`, `ui/dialogs/*`, `ui/components/*`, `styles/theme.py`, top-level page layout. |
| [`code-quality-refactor`](code-quality-refactor.md) | opus | Read, Edit, Write, Grep, Glob, Bash, PowerShell, TodoWrite | Structural cleanup — decomposing `commit_view.py`, removing dead code, de-duplicating constants, enforcing `core/ops`/threading conventions. |

None of these have the `Agent`/`Task` tool (no cross-agent delegation) and none inherit the project's unrelated MCP tools (Canva, Gmail, Supabase, Scale Insights, Google Drive/Calendar) — each is scoped to local file I/O, code search, and running the app for verification.

## Reference docs

- [`action-catalog.md`](action-catalog.md) — full action → handler → worker → `core/ops` → git-command map for all 22 user-triggerable git actions, a ranked backlog of 6 known issues, and a UI design recommendation for surfacing action details on toasts without touching the existing conflict dialogs. `git-actions-debugger`'s primary reference and known-issues checklist.

## Overlapping areas

- **`git-actions-debugger` vs `canvas-visualizer-debugger`** — both can touch `commit_view.py`'s `load_graph()`/action-handling code. The former owns correctness of ops, threading, and state flags (e.g., an action that hangs or leaves stale state); the latter owns correctness of lane assignment and rendering (e.g., a graph that draws branches in the wrong place after that same action). A bug that spans both ("after pushing, the visualizer shows the wrong branch in the wrong lane") may need both.
- **`ui-ux-polish` vs `code-quality-refactor`** — both may edit the same UI files. `ui-ux-polish` changes are visual/UX only (spacing, color, copy, layout) and should not change behavior or structure. `code-quality-refactor` changes are structural (splitting files, removing dead code, de-duplication) and must preserve existing behavior/visuals exactly.

## Why opus for `code-quality-refactor`

Decomposing the ~2,900-line `commit_view.py` and reasoning across the project's layer boundaries (git ops never touching Qt, threading rules, etc.) without a test suite is the highest-stakes, most architectural job of the four. The other three stay on `sonnet` — a good balance for focused debugging and polish work.

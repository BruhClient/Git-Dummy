# Graph Report - .  (2026-07-08)

## Corpus Check
- 81 files · ~75,720 words
- Verdict: corpus is large enough that graph structure adds value.

## Summary
- 1399 nodes · 3012 edges · 79 communities (58 shown, 21 thin omitted)
- Extraction: 94% EXTRACTED · 6% INFERRED · 0% AMBIGUOUS · INFERRED: 170 edges (avg confidence: 0.65)
- Token cost: 0 input · 0 output

## Community Hubs (Navigation)
- [[_COMMUNITY_Canvas Painting & Instruction Dialogs|Canvas Painting & Instruction Dialogs]]
- [[_COMMUNITY_Clone Dialog & Repo Workers|Clone Dialog & Repo Workers]]
- [[_COMMUNITY_UI-UX Pro-Max Skill (BM25 + Design System)|UI-UX Pro-Max Skill (BM25 + Design System)]]
- [[_COMMUNITY_GitTracker & Background Workers|GitTracker & Background Workers]]
- [[_COMMUNITY_Core Git Operations|Core Git Operations]]
- [[_COMMUNITY_Pull Requests Panel|Pull Requests Panel]]
- [[_COMMUNITY_Commit View Strip Renderers|Commit View Strip Renderers]]
- [[_COMMUNITY_CICD Pipeline & Agent Skills|CI/CD Pipeline & Agent Skills]]
- [[_COMMUNITY_Settings Panel & Collaborator UI|Settings Panel & Collaborator UI]]
- [[_COMMUNITY_Repo Page Overlay (FilterTabRemote)|Repo Page Overlay (Filter/Tab/Remote)]]
- [[_COMMUNITY_SpatialCanvas (Graph View)|SpatialCanvas (Graph View)]]
- [[_COMMUNITY_Diff Renderer & Detail Panel|Diff Renderer & Detail Panel]]
- [[_COMMUNITY_Stash, Checkout & Diff Ops|Stash, Checkout & Diff Ops]]
- [[_COMMUNITY_GitHub Authentication|GitHub Authentication]]
- [[_COMMUNITY_Repo Page Path Handling|Repo Page Path Handling]]
- [[_COMMUNITY_Canvas Constants & Edge Items|Canvas Constants & Edge Items]]
- [[_COMMUNITY_CommitViewPage (Main Hub)|CommitViewPage (Main Hub)]]
- [[_COMMUNITY_Detail Panel Widgets|Detail Panel Widgets]]
- [[_COMMUNITY_GitHub Push & Fork Ops|GitHub Push & Fork Ops]]
- [[_COMMUNITY_Position Panel & Avatar|Position Panel & Avatar]]
- [[_COMMUNITY_PR Open Wizard|PR Open Wizard]]
- [[_COMMUNITY_Commit Node Graphics|Commit Node Graphics]]
- [[_COMMUNITY_Auth Page & Branding|Auth Page & Branding]]
- [[_COMMUNITY_App Entry Point|App Entry Point]]
- [[_COMMUNITY_Changes Panel (Slide-in Diff)|Changes Panel (Slide-in Diff)]]
- [[_COMMUNITY_Init Dialog Steps|Init Dialog Steps]]
- [[_COMMUNITY_Global Styles & TopNav|Global Styles & TopNav]]
- [[_COMMUNITY_Navigation Dirty Dialogs|Navigation Dirty Dialogs]]
- [[_COMMUNITY_Merge & Revert Ops|Merge & Revert Ops]]
- [[_COMMUNITY_Shared Widget Styles|Shared Widget Styles]]
- [[_COMMUNITY_No Remote View|No Remote View]]
- [[_COMMUNITY_Storage Layer (Persistence)|Storage Layer (Persistence)]]
- [[_COMMUNITY_Alert & Merge Dialogs|Alert & Merge Dialogs]]
- [[_COMMUNITY_PR Mixin (CommitView PR Logic)|PR Mixin (CommitView PR Logic)]]
- [[_COMMUNITY_Confirm Dialog|Confirm Dialog]]
- [[_COMMUNITY_Misc Widgets|Misc Widgets]]
- [[_COMMUNITY_CommitView Header|CommitView Header]]
- [[_COMMUNITY_Fetch & Visibility Ops|Fetch & Visibility Ops]]
- [[_COMMUNITY_Account Popup|Account Popup]]
- [[_COMMUNITY_Flow Layout|Flow Layout]]
- [[_COMMUNITY_Avatar & Collaborator Row|Avatar & Collaborator Row]]
- [[_COMMUNITY_Missing Repo Card|Missing Repo Card]]
- [[_COMMUNITY_Main Window|Main Window]]
- [[_COMMUNITY_Toast Notifications|Toast Notifications]]
- [[_COMMUNITY_Explore Banner & All Changes Popup|Explore Banner & All Changes Popup]]
- [[_COMMUNITY_GitHub Connect Dialog|GitHub Connect Dialog]]
- [[_COMMUNITY_Branch Actions|Branch Actions]]
- [[_COMMUNITY_Repo Card|Repo Card]]
- [[_COMMUNITY_MiniMap|MiniMap]]
- [[_COMMUNITY_Avatar Cache & Collab Panel|Avatar Cache & Collab Panel]]
- [[_COMMUNITY_CommitInfo & Graph Commits|CommitInfo & Graph Commits]]
- [[_COMMUNITY_Collaborator Panel|Collaborator Panel]]
- [[_COMMUNITY_Conflict Dialog|Conflict Dialog]]
- [[_COMMUNITY_Stash Operations|Stash Operations]]
- [[_COMMUNITY_Branch Label (Canvas)|Branch Label (Canvas)]]
- [[_COMMUNITY_Lane Algorithm|Lane Algorithm]]
- [[_COMMUNITY_Branch Depth & Ancestry|Branch Depth & Ancestry]]
- [[_COMMUNITY_Zoom Bar|Zoom Bar]]
- [[_COMMUNITY_Commit Workers|Commit Workers]]
- [[_COMMUNITY_PR Panel Actions|PR Panel Actions]]
- [[_COMMUNITY_Repo Ops|Repo Ops]]
- [[_COMMUNITY_Header Bar|Header Bar]]
- [[_COMMUNITY_Diff Ops|Diff Ops]]
- [[_COMMUNITY_Action Buttons|Action Buttons]]
- [[_COMMUNITY_Revert Ops|Revert Ops]]
- [[_COMMUNITY_Canvas Legend|Canvas Legend]]
- [[_COMMUNITY_Stash Panel|Stash Panel]]
- [[_COMMUNITY_Graph Loader|Graph Loader]]
- [[_COMMUNITY_Find-Skills Tool|Find-Skills Tool]]
- [[_COMMUNITY_Repo Store|Repo Store]]
- [[_COMMUNITY_Settings Store|Settings Store]]
- [[_COMMUNITY_Collab Cache|Collab Cache]]

## God Nodes (most connected - your core abstractions)
1. `CommitViewPage` - 106 edges
2. `DetailPanel` - 52 edges
3. `_run()` - 43 edges
4. `SpatialCanvas` - 43 edges
5. `GitTracker` - 42 edges
6. `_Illust` - 35 edges
7. `RepoPage` - 34 edges
8. `CloneDialog` - 33 edges
9. `scrollbar_style()` - 30 edges
10. `PullRequestsPanel` - 27 edges

## Surprising Connections (you probably didn't know these)
- `GitDummy Logo (Terracotta crash-test-dummy mascot icon)` --rationale_for--> `EvoGit / Git Dummy Application`  [INFERRED]
  logo/logo.png → .claude/CLAUDE.md
- `find-skills Skill (agents dir)` --semantically_similar_to--> `find-skills Skill (claude skills dir)`  [AMBIGUOUS] [semantically similar]
  .agents/skills/find-skills/SKILL.md → .claude/skills/find-skills/SKILL.md
- `App` --uses--> `GitHubAuth`  [INFERRED]
  main.py → auth/github_auth.py
- `BranchLabel` --uses--> `CommitInfo`  [INFERRED]
  ui/canvas/graphics_items.py → core/git_tracker.py
- `CommitNode` --uses--> `CommitInfo`  [INFERRED]
  ui/canvas/graphics_items.py → core/git_tracker.py

## Import Cycles
- None detected.

## Hyperedges (group relationships)
- **EvoGit Python dependency stack** — claude_claude_claude_md_evogit, requirements_txt_pyqt5, requirements_txt_gitpython, requirements_txt_requests, requirements_txt_qtawesome [EXTRACTED 1.00]
- **Canvas graphics item subclasses** — claude_claude_claude_md_spatialcanvas, claude_claude_claude_md_commitnode, claude_claude_claude_md_branchlabel, claude_claude_claude_md_edgeitem [EXTRACTED 1.00]
- **EvoGit specialized subagent team** — agent_team_txt_git_actions_debugger, agent_team_txt_canvas_visualizer_debugger, agent_team_txt_ui_ux_polish, agent_team_txt_code_quality_refactor, agent_team_txt_evo_git_polish_agent [EXTRACTED 1.00]
- **Release CI/CD pipeline jobs** — _github_workflows_release_yml_build_windows, _github_workflows_release_yml_build_macos, _github_workflows_release_yml_release_job [EXTRACTED 1.00]
- **Diff viewing UI components** — claude_claude_claude_md_changespanel, claude_claude_claude_md_allchangespopup, claude_claude_claude_md_diff_renderer [EXTRACTED 1.00]

## Communities (79 total, 21 thin omitted)

### Community 0 - "Canvas Painting & Instruction Dialogs"
Cohesion: 0.07
Nodes (30): QBrush, QRectF, QPainter, _BranchesIllust, _CommitsIllust, _CommitTypesIllust, _ConflictTypesIllust, _ConflictUIIllust (+22 more)

### Community 1 - "Clone Dialog & Repo Workers"
Cohesion: 0.05
Nodes (18): clone_repo(), Clone url into dest_parent/<repo-name>. Returns (ok, error, cloned_path)., QStackedWidget, CloneDialog, Dialog to clone a remote repo — shows the user's GitHub repos for quick access, Convert ISO 8601 timestamp to a human-readable relative string., Return the origin remote URL for a local repo, or '' if not found., Minimal clickable row for one GitHub repo. (+10 more)

### Community 2 - "UI-UX Pro-Max Skill (BM25 + Design System)"
Cohesion: 0.05
Nodes (42): BM25, detect_domain(), _load_csv(), Lowercase, split, remove punctuation, filter short words, Build BM25 index from documents, Score all documents against query, Load CSV and return list of dicts, Core search function using BM25 (+34 more)

### Community 3 - "GitTracker & Background Workers"
Cohesion: 0.07
Nodes (22): GitTracker, Fetch contributors for this repo from GitHub's API.         Returns a list of d, Thin wrapper around gitpython that reads commit history from a local repo., Return per-file diff info for a commit., Return extended info for a single commit (full message)., Return the name of any ongoing git operation, or '' if none., QObject, _BranchCountWorker (+14 more)

### Community 4 - "Core Git Operations"
Cohesion: 0.09
Nodes (42): checkout_branch(), current_branch(), get_conflict_content(), get_conflict_files(), parse_conflict_markers(), Parse `<<<<<<<` / `=======` / `>>>>>>>` conflict markers out of `lines`.     Ret, Parse conflict markers, return (original_lines, orig_start, incoming_lines, inc_, Run a git command with a timeout. Returns (ok, error_message). (+34 more)

### Community 5 - "Pull Requests Panel"
Cohesion: 0.07
Nodes (15): QScrollArea, _pill_style(), _pr_branch_shas(), _pr_state(), _PRRow, PullRequestsPanel, Pull Requests inbox — lives in the Collaboration tab., Full-page PR inbox shown in the Collaboration tab. (+7 more)

### Community 6 - "Commit View Strip Renderers"
Cohesion: 0.09
Nodes (17): _BothTipsStrip, _CommitStrip, _DashedEdgeStrip, _FlagStrip, _HeadStrip, _LocalTipStrip, QColor, QPainter (+9 more)

### Community 7 - "CI/CD Pipeline & Agent Skills"
Cohesion: 0.06
Nodes (42): reflect Skill (Conversation Self-Optimisation), ui-ux-pro-max Skill (Design Intelligence), build-macos CI Job, build-windows CI Job, NSIS (Windows Installer Compiler), PyInstaller (Build Tool), release CI Job, canvas-visualizer-debugger Agent (+34 more)

### Community 8 - "Settings Panel & Collaborator UI"
Cohesion: 0.09
Nodes (12): _Avatar, _divider(), _IconStat, QFrame, QLabel, QPixmap, Settings panel — repo info and collaborators., _SCollabRow (+4 more)

### Community 9 - "Repo Page Overlay (Filter/Tab/Remote)"
Cohesion: 0.10
Nodes (6): _CreateRemoteDialog, _FilterPanel, _OrientBar, QVBoxLayout, Overlay dialog shown when a repo has no remote or its remote was deleted., _TabBar

### Community 10 - "SpatialCanvas (Graph View)"
Cohesion: 0.08
Nodes (9): QGraphicsView, Infinite panning + zoom canvas.      Pan  — click-drag on the background., Dim the given SHAs to 15% opacity; restore all others., PR hover: keep active_shas bright, dim everything else. Empty set restores filte, Update author text labels to show 'You' for the given commit SHAs., Dim author labels for commits whose author isn't a known collaborator., Select a commit node and scroll to it., Creates a tiled pixel-map with a subtle dot-grid pattern. (+1 more)

### Community 11 - "Diff Renderer & Detail Panel"
Cohesion: 0.14
Nodes (22): Full-screen overlay showing every file's before/after changes., Main commit detail panel — slides in from the right., _close_btn_style(), _DiffLine, _divider(), _fade_in(), _fade_out_and_remove(), _MiniBar (+14 more)

### Community 12 - "Stash, Checkout & Diff Ops"
Cohesion: 0.11
Nodes (23): checkout_commit(), has_uncommitted_changes(), Reset index and working tree to HEAD, aborting any partial stash apply., reset_hard(), get_stash_diff_files(), get_working_dir_diff_files(), Return per-file diff info for a stash, in the same format as commit_files., Return per-file diff info for the current dirty working directory (staged + unst (+15 more)

### Community 13 - "GitHub Authentication"
Cohesion: 0.14
Nodes (11): GitHubAuth, Validate a new PAT and update an existing account. Runs on a background thread., Switch to a different saved account., Return list of saved accounts (without tokens)., Remove a specific account from storage., Clear the active session without removing the account from storage., Validate a token against the GitHub API. Returns (user_dict, scopes) or (None, s, Manages GitHub authentication via Personal Access Tokens.      Signals: (+3 more)

### Community 14 - "Repo Page Path Handling"
Cohesion: 0.15
Nodes (4): _norm_path(), Decide what to do with a dropped/browsed path., Let user point to the new location of a missing repo., RepoPage

### Community 15 - "Canvas Constants & Edge Items"
Cohesion: 0.16
Nodes (14): QGraphicsPathItem, _lane_color(), Layout constants and orientation flags shared across the canvas module., EdgeItem, QGraphicsItem subclasses for the commit graph canvas., Cross-lane connection line (L-elbow, solid or dashed)., Re-exports for the canvas package so `from ui.canvas import X` works., _branch_base() (+6 more)

### Community 18 - "GitHub Push & Fork Ops"
Cohesion: 0.12
Nodes (18): set_commit_author(), create_github_repo(), fork_repo(), push_branch(), push_to_github(), Fork the origin repo to the user's account and set push URL to the fork., Returns (success, error, clone_url)., Stages everything, makes an initial commit if needed, adds remote, pushes.     R (+10 more)

### Community 19 - "Position Panel & Avatar"
Cohesion: 0.15
Nodes (6): hash_color(), _Avatar, _Field, PositionPanel, QPixmap, Floating panel showing the commit currently checked out in the local repo.

### Community 20 - "PR Open Wizard"
Cohesion: 0.13
Nodes (10): _branch_to_title(), _divider(), PROpenWizard, QFrame, PR Open Wizard — 2-step modal overlay: Push → Open PR., Convert 'feature/add-login' → 'Add login'., Launch the wizard.         - branch: the feature branch being PR'd         - b, Call from commit_view after push completes. (+2 more)

### Community 21 - "Commit Node Graphics"
Cohesion: 0.10
Nodes (7): QGraphicsObject, CommitNode, ContributorBadge, QPixmap, Circular avatar badge floating on a contributor's latest commit node., Coloured circle representing a single commit., Place avatar badges for each contributor at their latest commit.

### Community 22 - "Auth Page & Branding"
Cohesion: 0.14
Nodes (5): AuthPage, LogoMark, Git Dummy branded logo mark., Shown briefly on launch while we try to restore a saved sign-in., Full-screen sign-in page — Personal Access Token entry.

### Community 23 - "App Entry Point"
Cohesion: 0.13
Nodes (6): App, _check_git_installed(), main(), Return the origin remote URL for a local repo, or '' if not found., _remote_url(), resource_path()

### Community 24 - "Changes Panel (Slide-in Diff)"
Cohesion: 0.16
Nodes (9): ChangesPanel, Slide-in panel showing a single file's diff., Slides in from behind the detail panel to show a file's diff.     Hidden positio, _chunk_lines(), _compute_hunks(), _filter_unchanged(), Split (line_num, text) pairs into consecutive groups., Group diff lines into hunks [{removed:[(n,t)…], added:[(n,t)…]}]. (+1 more)

### Community 25 - "Init Dialog Steps"
Cohesion: 0.20
Nodes (10): _divider(), _label(), QLabel, Step 1 — confirm git init., Step 2 — offer to push to GitHub., _StepDone, _StepGitHub, _StepInit (+2 more)

### Community 26 - "Global Styles & TopNav"
Cohesion: 0.20
Nodes (7): make_global_style(), _AvatarCircle, _download_avatar_async(), _LogoMark(), QPixmap, Slim top navigation bar — no sidebar., TopNav

### Community 27 - "Navigation Dirty Dialogs"
Cohesion: 0.17
Nodes (3): _NavigateDirtyDialog, _PullDirtyDialog, Prompt shown when the user tries to switch snapshots with unsaved changes.

### Community 29 - "Shared Widget Styles"
Cohesion: 0.17
Nodes (9): card_shadow(), Unified scrollbar stylesheet fragment — apply to any QScrollArea., scrollbar_style(), Self-contained widget classes used by CommitViewPage.  These are small, presenta, Banner shown when the user is exploring a past commit., CloneDialog and RepoRow — dialog for cloning a remote repo., Styled confirmation and alert dialogs, plus convenience helpers., Dark-themed single-line input dialog for commit messages, branch names, etc. (+1 more)

### Community 30 - "No Remote View"
Cohesion: 0.15
Nodes (4): _NoRemoteBanner, _NoRemoteView, No-remote placeholder view and compact banner., Switch banner to 'repo was deleted' warning state.

### Community 31 - "Storage Layer (Persistence)"
Cohesion: 0.22
Nodes (10): get(), _load_store(), Return (data, is_stale).  data is None on a full cache miss., save(), core.storage — persistence helpers., load(), save(), get() (+2 more)

### Community 32 - "Alert & Merge Dialogs"
Cohesion: 0.17
Nodes (5): QDialog, AlertDialog, MergeDialog, Styled alert dialog — title, body text, single OK button., Styled merge dialog — source branch, target selector, Merge/Cancel.

### Community 33 - "PR Mixin (CommitView PR Logic)"
Cohesion: 0.13
Nodes (6): _PRMixin, Load or refresh the PR inbox. Called when switching to Collaboration tab., User clicked 'Open Pull Request' on a branch head., Wizard Step 1: push branch., Wizard Step 2: call GitHub API to create the PR., User clicked Merge on a PR row. Check for conflicts first.

### Community 34 - "Confirm Dialog"
Cohesion: 0.16
Nodes (4): confirm(), ConfirmDialog, Show a styled confirmation dialog. Returns True if the user confirmed., Styled confirmation dialog — title, body text, Cancel + confirm button.

### Community 37 - "CommitView Header"
Cohesion: 0.16
Nodes (3): _Header, Top header bar for CommitViewPage., Resize the header to fit however many sub-rows are visible.

### Community 38 - "Fetch & Visibility Ops"
Cohesion: 0.17
Nodes (6): Fetch from origin. Returns True if refs changed., Fetch from origin.         Returns (changed, best_guess_author) where best_gues, Return commit SHAs reachable from local branches but not from any remote ref., Return (visibility, can_push). Visibility is 'private', 'public', 'not_found', o, Return the GitHub username that owns the remote repo, or ''., Return the GitHub HTTPS URL for origin, or empty string.

### Community 39 - "Account Popup"
Cohesion: 0.27
Nodes (4): QFrame, _AccountPopup, QPushButton, Floating popup showing saved accounts with switch / add / sign-out.

### Community 40 - "Flow Layout"
Cohesion: 0.21
Nodes (3): QLayout, _FlowLayout, Layout that wraps items to the next row when the width is exceeded.

### Community 41 - "Avatar & Collaborator Row"
Cohesion: 0.21
Nodes (4): _AvatarDot, _CollabRow, QPixmap, Circular avatar — starts with initials, upgrades to real photo.

### Community 42 - "Missing Repo Card"
Cohesion: 0.20
Nodes (4): QLabel, DropZone, MissingRepoCard, Card shown when a saved repo path no longer exists.

### Community 43 - "Main Window"
Cohesion: 0.18
Nodes (3): QMainWindow, QPoint, MainWindow

### Community 45 - "Explore Banner & All Changes Popup"
Cohesion: 0.26
Nodes (4): QWidget, _ExploreBanner, AllChangesPopup, Full-screen overlay showing every file's before/after changes.

### Community 46 - "GitHub Connect Dialog"
Cohesion: 0.24
Nodes (4): _GitHubConnectDialog, Full-screen overlay dialog for connecting a local repo to GitHub., Show the dialog centred over the parent., Full-screen overlay dialog for connecting a local repo to GitHub.

### Community 48 - "Repo Card"
Cohesion: 0.21
Nodes (5): Get the GitHub owner login by reading .git/config directly — no subprocess., Get the GitHub repo name from .git/config origin URL., _remote_owner(), _remote_repo(), RepoCard

### Community 49 - "MiniMap"
Cohesion: 0.25
Nodes (3): MiniMap, Bird's-eye minimap widget for the commit graph canvas., Bird's-eye view of the commit graph.     White box = current viewport. Click/dra

### Community 50 - "Avatar Cache & Collab Panel"
Cohesion: 0.36
Nodes (8): _avatar_disk_path(), _load_avatar(), QPixmap, Avatar disk + memory cache helpers., _save_avatar(), _person_color(), Collaborator panel — skeleton rows, avatar dots, rows, and the main panel., ui.components — re-exports all shared UI component classes.

### Community 51 - "CommitInfo & Graph Commits"
Cohesion: 0.20
Nodes (4): CommitInfo, Return up to max_count commits from the given branch/ref., Returns (commits, branch_tip_map, local_only) for the spatial canvas., Same as graph_commits but reads local branches only.

### Community 52 - "Collaborator Panel"
Cohesion: 0.24
Nodes (4): CollaboratorPanel, Floating panel showing repo contributors — always visible top-right., Grey placeholder row shown while collaborators are loading., _SkeletonRow

### Community 53 - "Conflict Dialog"
Cohesion: 0.27
Nodes (4): _ConflictDialog, _numbered(), Format lines with actual file line numbers as a left-justified gutter., ui.dialogs — re-exports all dialog classes and helpers.

### Community 55 - "Branch Label (Canvas)"
Cohesion: 0.22
Nodes (3): QGraphicsItem, BranchLabel, Pill badge showing a branch name.     Placed to the right of the branch-tip com

### Community 57 - "Branch Depth & Ancestry"
Cohesion: 0.22
Nodes (4): _compute_branch_depths(), Return branch_name → nesting depth (0 = default branch, 1 = off default, 2 = off, BFS up the old commit graph from deleted_sha, returning the first         ances, Called when the commit currently open in the detail panel no longer         exi

### Community 68 - "Canvas Legend"
Cohesion: 0.40
Nodes (3): _Legend, Canvas legend widget — explains the visual symbols., Small floating key explaining the visual symbols on the canvas.

### Community 72 - "Find-Skills Tool"
Cohesion: 1.00
Nodes (3): find-skills Skill (agents dir), Skills CLI (npx skills), find-skills Skill (claude skills dir)

## Ambiguous Edges - Review These
- `find-skills Skill (agents dir)` → `find-skills Skill (claude skills dir)`  [AMBIGUOUS]
  .agents/skills/find-skills/SKILL.md · relation: semantically_similar_to

## Knowledge Gaps
- **15 isolated node(s):** `AuthPage`, `RepoPage`, `CommitInfo (dataclass)`, `core/storage/ (Persistence Layer)`, `MiniMap` (+10 more)
  These have ≤1 connection - possible missing edges or undocumented components.
- **21 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **What is the exact relationship between `find-skills Skill (agents dir)` and `find-skills Skill (claude skills dir)`?**
  _Edge tagged AMBIGUOUS (relation: semantically_similar_to) - confidence is low._
- **Why does `CommitViewPage` connect `CommitViewPage (Main Hub)` to `Clone Dialog & Repo Workers`, `GitTracker & Background Workers`, `Pull Requests Panel`, `Commit View Strip Renderers`, `Settings Panel & Collaborator UI`, `GitHub Push & Fork Ops`, `Position Panel & Avatar`, `PR Open Wizard`, `App Entry Point`, `Navigation Dirty Dialogs`, `PR Mixin (CommitView PR Logic)`, `Commit Action Handlers`, `Toast Notifications`, `Explore Banner & All Changes Popup`, `CommitInfo & Graph Commits`, `Collaborator Panel`, `Lane Algorithm`, `Branch Depth & Ancestry`, `Commit Workers`, `Loading Overlay`, `Uncommitted Refresh`, `Revert Ops`, `Graph Loader`?**
  _High betweenness centrality (0.194) - this node is a cross-community bridge._
- **Why does `GitTracker` connect `GitTracker & Background Workers` to `Fetch & Visibility Ops`, `Toast Notifications`, `Stash, Checkout & Diff Ops`, `Canvas Constants & Edge Items`, `CommitViewPage (Main Hub)`, `GitHub Push & Fork Ops`, `CommitInfo & Graph Commits`?**
  _High betweenness centrality (0.058) - this node is a cross-community bridge._
- **Why does `DetailPanel` connect `Detail Panel Widgets` to `Alert & Merge Dialogs`, `Action Buttons`, `Confirm Dialog`, `Diff Renderer & Detail Panel`, `Stash, Checkout & Diff Ops`, `Explore Banner & All Changes Popup`, `Branch Actions`, `GitHub Push & Fork Ops`, `Navigation Dirty Dialogs`, `PR Panel Actions`?**
  _High betweenness centrality (0.046) - this node is a cross-community bridge._
- **Are the 11 inferred relationships involving `CommitViewPage` (e.g. with `App` and `CommitInfo`) actually correct?**
  _`CommitViewPage` has 11 INFERRED edges - model-reasoned connections that need verification._
- **Are the 4 inferred relationships involving `DetailPanel` (e.g. with `ConfirmDialog` and `MergeDialog`) actually correct?**
  _`DetailPanel` has 4 INFERRED edges - model-reasoned connections that need verification._
- **Are the 17 inferred relationships involving `_run()` (e.g. with `._do_clean_pull()` and `._on_branch_create()`) actually correct?**
  _`_run()` has 17 INFERRED edges - model-reasoned connections that need verification._
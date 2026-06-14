# Evo Git — Action Catalog & Audit

Reference doc for `git-actions-debugger` (and anyone else touching `core/ops/*` or
`ui/commit_view.py`). Part 1 maps every user-triggerable git action to its handler,
worker, ops function, and exact git command sequence. Part 2 is a ranked backlog of
known risk/inefficiency findings — pick one up as a self-contained task. Part 3 is a
UI design recommendation for surfacing action details without ever hiding conflict info.

---

## Part 1: Action catalog

### 1. Fetch (background poll)
- **UI**: none — `_poll_timer` (30s) in `commit_view.py`, plus an immediate call from `load_repo()`
- **Handler**: `_poll_remote()` → `_on_fetch_done()` (`ui/commit_view.py:1149`)
- **Worker**: `_FetchWorker` (`ui/workers/commit_workers.py:132`)
- **Ops**: `GitTracker.fetch_with_author()` (`core/git_tracker.py:264`) — uses GitPython, not `core/ops`
- **Git**: `git fetch origin` (via `remote.fetch()`)
- **Errors**: exceptions swallowed → `(False, "")`; on changed refs, triggers `_start_load()` to reload the graph. No merge of any kind happens here — see Finding 6.

### 2. Pull (fast-forward, clean tree)
- **UI**: `_pull_btn` (`ui/panels/detail_panel.py:403`, hidden when already on the branch)
- **Handler**: `_on_pull_branch()` → `_do_clean_pull()` (`ui/commit_view.py:1939`)
- **Worker**: inline `threading.Thread`
- **Ops**: `pull_ff()` (`core/ops/repo_ops.py:52`)
- **Git**: `git fetch origin {branch}:{branch}`
- **Errors**: toast on failure

### 3–5. Pull (dirty tree — stash/save/discard variants)
- **UI**: `_PullDirtyDialog` (shown when `pull_ff` would conflict with uncommitted changes)
- **Handler**: `_on_pull_dirty_choice()` (`ui/commit_view.py:1963`), dispatches on `choice`:
  - `"stash_pull"` → `pull_stash_apply()` (`core/ops/repo_ops.py:57`): `git stash` → `git fetch origin` → `git reset --hard origin/{branch}` → `git stash pop`
  - `"save_merge"` → `pull_save_merge()` (`core/ops/repo_ops.py:81`): `git add -A` → `git commit -m "saved changes before pull"` → `git fetch origin` → `git merge origin/{branch}`
  - `"discard_pull"` → `pull_discard()` (`core/ops/repo_ops.py:107`): `git reset --hard HEAD` → `git clean -fd` → `git fetch origin` → `git reset --hard origin/{branch}`
- **Worker**: inline `threading.Thread`
- **Errors**: `save_merge`/`stash_pull` show a merge-conflict dialog on conflict; otherwise toast

### 6. Push branch
- **Handler**: `_on_push_branch()` (`ui/commit_view.py:2023`) — used by the PR-open wizard and direct branch push
- **Worker**: inline `threading.Thread`
- **Ops**: `push_branch()` (`core/ops/github_ops.py:32`)
- **Git**: `git push -u origin {branch}`; on `[rejected]`/`non-fast-forward` → `git fetch origin` → `git merge origin/{branch}` → (on success) `git push -u origin {branch}` retry — see **Finding 5**
- **Errors**: merge conflict during the retry surfaces `_PushConflictDialog`-style data (conflict files + content); other failures → toast

### 7. Commit (PR wizard)
- **UI**: PR Open Wizard step 1
- **Handler**: `_on_wizard_commit()` (`ui/commit_view.py:2233`)
- **Worker**: inline `threading.Thread`
- **Ops**: inline subprocess (no `core/ops` wrapper)
- **Git**: `git add -A`, `git commit -m {message}`
- **Errors**: toast

### 8. Discard all changes
- **UI**: PR wizard "Discard & Start Over"
- **Handler**: `_on_wizard_discard()` (`ui/commit_view.py:2253`)
- **Ops**: `discard_all_changes()` (`core/ops/revert_ops.py:8`)
- **Git**: `git reset --hard HEAD`, `git clean -fd`
- **Errors**: toast

### 9. Save stash (as commit)
- **UI**: `_save_stash_btn` (`ui/panels/detail_panel.py:487`)
- **Handler**: `_on_save_stash()` (`ui/commit_view.py:1924`)
- **Ops**: `save_stash_as_commit()` (`core/ops/stash_ops.py:122`)
- **Git**: `git stash apply {stash_ref}` → optionally `git checkout -b {branch} origin/{branch}` → `git add -A` → `git commit -m ...` → `git merge --no-ff` → `git stash drop`
- **Errors**: merge-conflict dialog on the `--no-ff` merge step; otherwise toast

### 10. Clear stash
- **UI**: `_clear_stash_btn` (`ui/panels/detail_panel.py:494`)
- **Handler**: `_on_clear_stash()` (`ui/commit_view.py:1718`)
- **Ops**: `drop_stash()` (`core/ops/stash_ops.py:77`)
- **Git**: `git stash drop {stash_ref}`
- **Errors**: toast (success or error)

### 11. Hard revert
- **UI**: `_hard_revert_btn` (`ui/panels/detail_panel.py:501`)
- **Handler**: `_on_hard_revert()` → `_run_branch_op()` (`ui/commit_view.py:2097`)
- **Ops**: `hard_revert_to()` (`core/ops/revert_ops.py:16`)
- **Git**: `git checkout {branch}` (if needed) → `git reset --hard {target_sha}` → `git ls-remote --heads origin {branch}` → if it exists remotely, `git push --force origin {branch}`
- **Errors**: toast. **No check that `target_sha` is an ancestor of `origin/{branch}` before force-pushing — see Finding 1.**

### 12. Soft revert
- **UI**: `_soft_revert_btn` (`ui/panels/detail_panel.py:508`)
- **Handler**: `_on_soft_revert()` → `_run_branch_op()` (`ui/commit_view.py:2106`)
- **Ops**: `soft_revert_to()` (`core/ops/revert_ops.py:48`)
- **Git**: `git checkout {branch}` (if needed) → `git read-tree --reset -u {parent}` → `git add -A` → `git commit -m "reverted to {parent}"`
- **Errors**: on `read-tree` failure, runs `git reset HEAD` to clean the index before returning

### 13. Create branch from commit
- **UI**: `_branch_btn` (`ui/panels/detail_panel.py:366`)
- **Handler**: `_on_branch_create()` (`ui/commit_view.py:2158`)
- **Ops**: `create_branch_with_commit()` (`core/ops/branch_ops.py:174`)
- **Git**: `git checkout -b {branch_name} {from_sha}` → `git commit --allow-empty -m "created branch {branch_name}"`
- **Errors**: if the empty commit fails, deletes the just-created local branch

### 14. Delete branch (local + remote)
- **UI**: `_delete_branch_btn` (`ui/panels/detail_panel.py:553`)
- **Handler**: `_on_delete_branch()` → `_run_branch_op()` (`ui/commit_view.py:2114`)
- **Ops**: `delete_branch_full()` (`core/ops/branch_ops.py:94`)
- **Git**: if currently on the branch, checkout a fallback first → `git branch -D {branch}` → `git push origin --delete {branch}` (if it exists on origin)
- **Errors**: toast; special-cases "refusing to delete the current branch"

### 15. Merge branch
- **UI**: `_merge_btn` + `_merge_combo` (`ui/panels/detail_panel.py:520`, `:534`)
- **Handler**: `_on_merge_branch()` (`ui/commit_view.py:1840`)
- **Ops**: `merge_branch()` (`core/ops/merge_ops.py:8`)
- **Git**: `git checkout {target}` (if needed) → `git merge --no-ff {source}`
- **Errors**: merge-conflict dialog on conflict; otherwise toast

### 16. Resolve merge conflict (manual file decisions)
- **UI**: merge conflict dialog (`_MergeConflictDialog`)
- **Handler**: `_on_merge_conflict_choice()` (`ui/commit_view.py:1893`)
- **Ops**: `merge_with_decisions()` (`core/ops/merge_ops.py:34`)
- **Git**: `git merge --no-ff --no-commit {source}` → per file: `git checkout --ours|--theirs {file}` + `git add {file}` → `git commit --no-edit` (or `git merge --abort` if any file resolution fails)
- **Errors**: abort merge on any failure, leaving the repo clean

### 17. Navigate / checkout commit (with auto-stash)
- **UI**: click a commit on the canvas
- **Handler**: `_on_navigate()` (`ui/commit_view.py:2617`)
- **Worker**: `_NavigateWorker` (`ui/workers/commit_workers.py:187`)
- **Ops**: `create_auto_stash()` / `checkout_commit()` / `apply_stash()` (`core/ops/stash_ops.py`)
- **Git**: `git stash push --include-untracked -m {stash_id}` (if dirty) → `git checkout {sha}` → if a stash exists for the target commit, `git stash apply {stash_ref}`
- **Errors**: on stash-apply conflict, runs `git reset --hard HEAD` and emits `"stash-conflict"` — **the stash entry is never dropped, see Finding 3**

### 18. Init repository
- **UI**: Init dialog (`ui/dialogs/`)
- **Worker**: `_CreateRepoWorker` (`ui/workers/commit_workers.py:259`)
- **Ops**: `init_repo()` (`core/ops/repo_ops.py:9`)
- **Git**: `git init -b main` (fallback: `git init` + `git symbolic-ref HEAD refs/heads/main`) → `git config user.name/email` → `git add .` → `git commit --allow-empty -m "Initial commit"`
- **Errors**: `(ok, error_message)` tuple

### 19. Clone repository
- **UI**: Clone dialog (`ui/dialogs/`)
- **Worker**: `_CloneWorker` (`ui/workers/repo_workers.py:33`)
- **Ops**: `clone_repo()` (`core/ops/repo_ops.py:36`)
- **Git**: `git clone {url} {dest_path}`
- **Errors**: `(ok, error, path)` tuple

### 20. Create GitHub repo (from PR wizard)
- **Handler**: `_on_create_remote_requested()` (`ui/commit_view.py:1309`)
- **Ops**: `create_github_repo()` (`core/ops/github_ops.py:12`)
- **Git**: none — GitHub API `POST /user/repos`
- **Errors**: toast

### 21. Merge PR (locally)
- **UI**: PR inbox → Merge button on a PR row
- **Handler**: `_on_pr_merge_requested()` (`ui/commit_view.py:2319`)
- **Ops**: `merge_pr_locally()` (`core/ops/merge_ops.py:213`)
- **Git**: `git rev-parse --abbrev-ref HEAD` → `git checkout {target_branch}` (if needed) → `git pull --ff-only origin {target_branch}` → `git merge --no-ff --no-commit {feature_branch}` → per file: `git checkout --ours|--theirs` + `git add` → `git commit --no-edit` → `git push origin {target_branch}`
- **Errors**: on commit failure, `git merge --abort`. **Neither the `pull --ff-only` nor the `merge --no-commit` call's result is checked before proceeding — see Finding 2.**

### 22. GitHub connect / push initial commit to new remote
- **UI**: Settings panel / connect banner
- **Handler**: `_on_github_connect()` (`ui/commit_view.py:1809`)
- **Ops**: `push_to_github()` (`core/ops/github_ops.py:81`)
- **Git**: `git config user.name/email` → `git log --oneline -1` (check for existing commits) → `git commit --allow-empty -m "Initial commit"` (if none) → `git remote remove/add origin` → `git config http.{clone_url}.extraHeader ...` → `git push -u origin HEAD`
- **Errors**: toast (success or error)

---

## Part 2: Known issues / backlog (ranked by risk)

Each entry below is independent and self-contained — `git-actions-debugger` can pick
up any one of these without needing the others.

### 1. [HIGH] `hard_revert_to()` force-pushes without checking the remote relationship
- **File**: `core/ops/revert_ops.py:16-45` (push at lines 38-41)
- **Issue**: After `git reset --hard {target_sha}`, the function checks only whether `origin/{branch}` *exists* (`git ls-remote --heads`) — it never checks whether `target_sha` is an ancestor of the current `origin/{branch}` tip. If the remote has commits the local repo hasn't fetched, `git push --force` silently discards them.
- **Suggested direction**: before force-pushing, `git fetch origin {branch}` then `git merge-base --is-ancestor origin/{branch} {target_sha}` (or compare `origin/{branch}` against the new local tip); if `origin/{branch}` is *not* an ancestor of the reverted tip, surface a confirmation dialog (or fail with a clear message) instead of pushing silently.

### 2. [HIGH] `merge_pr_locally()` doesn't check `pull`/`merge` results before proceeding
- **File**: `core/ops/merge_ops.py:213-258` (lines 235 and 238)
- **Issue**: `_run(path, ["git", "pull", "--ff-only", "origin", target_branch], ...)` and the subsequent `_run(path, ["git", "merge", "--no-ff", "--no-commit", feature_branch], ...)` both discard their `(ok, err)` return values. If the `pull --ff-only` fails (e.g. target branch diverged from origin), the code proceeds to merge against a stale local tip anyway, then commits and pushes — possibly overwriting commits that were on `origin/{target_branch}`.
- **Suggested direction**: check the `pull --ff-only` result and abort with a clear error if it fails (don't silently merge against stale state); consider re-fetching immediately before the merge step too.

### 3. [MEDIUM] Stash entry leaks on apply-conflict during navigate
- **File**: `ui/workers/commit_workers.py:232-237` (`_NavigateWorker.run`), `core/ops/stash_ops.py:68` (`apply_stash`)
- **Issue**: When navigating to a commit that has an associated auto-stash, `apply_stash()` is called; if it fails (conflict), the worker runs `reset_hard()` and emits `"stash-conflict"`, but never calls `drop_stash()`. The stash entry remains in `git stash list` indefinitely, and the user's changes appear to have "disappeared" with no obvious link back to the leftover stash.
- **Suggested direction**: either retry `apply_stash` with `--index` / surface the conflicting files so the user can resolve them, or explicitly `drop_stash()` after the `reset_hard()` and inform the user their changes were discarded (matching the `"stash-conflict"` message's implication).

### 4. [MEDIUM] `check_pr_conflicts()` conflict detection relies on fragile `git merge-tree` string-matching
- **File**: `core/ops/merge_ops.py:141-210` (marker check at line 175, parsing at 184-205)
- **Issue**: Conflicts are detected via `"<<<<<<<" not in output` on raw `git merge-tree` text, then filenames are parsed by matching `+++ `/`--- ` line prefixes. `git merge-tree`'s plain-text output format isn't a stable, documented interface across git versions — a format change could cause conflicts to go undetected (returns `(False, [], {})` from the `except Exception` branch) or filenames to be misparsed (falls back to `["(unknown files — check manually)"]`).
- **Suggested direction**: prefer `git merge-tree --write-tree` / `-z` (machine-readable, available in modern git) if the project's minimum git version supports it; otherwise pin/document the git version this parsing was validated against and add a fallback path when `conflict_files` ends up empty but markers were found.

### 5. [LOW] `push_branch()` merges from origin without explicit user consent on rejection
- **File**: `core/ops/github_ops.py:32-78` (fetch+merge at lines 56-64)
- **Issue**: On a `[rejected]`/`non-fast-forward` push, the function automatically runs `git fetch origin` then `git merge origin/{branch}` (a real merge, not `--ff-only`) before retrying the push. If the merge succeeds cleanly, a merge commit is created and pushed without the user ever being told a merge happened. If it conflicts, conflict info is surfaced — so it's not silent in the failure case, only in the success case.
- **Suggested direction**: on the success path (merge succeeds, retry push succeeds), have the caller show an info toast like "origin had new commits — merged automatically before pushing" so the user isn't surprised by an unexpected merge commit in their history.

### 6. [LOW] CLAUDE.md documents an auto-fast-forward-on-fetch that doesn't exist in code
- **Files**: `.claude/CLAUDE.md` (background-polling section) vs. `ui/workers/commit_workers.py:132-149` (`_FetchWorker`) and `core/git_tracker.py:264` (`fetch_with_author`)
- **Issue**: Project docs describe `_FetchWorker` as "also attempt[ing] a silent `git merge --ff-only origin/<branch>` after fetching (only if the working tree is clean)". No such merge call exists anywhere in `_FetchWorker`, `_on_fetch_done`, or `fetch_with_author` — the fetch worker only fetches and triggers a graph reload if refs changed. Either the documented behavior was never implemented, or it existed and was removed without updating the docs.
- **Suggested direction**: decide which is true and reconcile — either implement the documented auto-ff-merge (with a clean-tree guard, matching `core/ops` conventions) so a branch that's behind its remote counterpart actually fast-forwards automatically, or correct `.claude/CLAUDE.md` to remove the claim. Worth resolving before relying on this doc for other action-flow reasoning.

---

## Part 3: UI design recommendation — surfacing action details without hiding conflict info

**Conflicts already get the right treatment and need no change.** `ui/dialogs/conflict_dialog.py`'s `_ConflictDialog`, `_MergeConflictDialog`, `_PullDirtyDialog`, and `_NavigateDirtyDialog` are modal, show the full list of affected files, and render side-by-side `QPlainTextEdit` diffs for each conflicting file. This is the right "never hide crucial info" surface for conflicts — don't fold conflict details into the toast system below.

**The gap is everything else** — the non-conflict success/error toasts fired by the 22 actions above. `ui/components/toast.py`'s `_Toast`:
- shows one line of text, truncated to ~120 chars by the caller in `commit_view.py` before the toast is even constructed,
- has `WA_TransparentForMouseEvents` set, so it currently can't be clicked/expanded at all.

**Recommendation**: add an optional expandable "Details" affordance to `_Toast`, used only when the caller has extra diagnostic text (the *untruncated* git command + stdout/stderr that's currently discarded at the 120-char truncation point):

- Default/common case is unchanged: a one-line toast, non-interactive, auto-dismisses — stays simple.
- When a toast is constructed with optional `details: str` text, render a small "Details ▾" affordance. Clicking it (removing `WA_TransparentForMouseEvents` only for toasts carrying details) expands the toast downward into a `QPlainTextEdit`, styled like `conflict_dialog.py`'s code-area styling (monospace, `COLORS['bg_secondary']`, rounded corners, thin custom scrollbar) — showing the full command + output.
- This is purely additive: no change to `_ConflictDialog`/`_MergeConflictDialog`/etc., no change to the default toast UX for the ~90% of actions that succeed with nothing more to say.
- Natural first candidates for `details=`: any toast fired from a `core/ops` failure tuple (`(False, err)`/`(False, err, files, content)`), where `err` is currently truncated — pass the full `err` as `details` instead of dropping it.

---

## Part 4: Additional findings from the app-wide sweep (`evo-git-polish`)

These were found doing a broad pass over `ui/`, `core/`, `styles/`, `auth/` rather than chasing a
specific report. Each names the specialist whose territory it falls in.

### A. [LOW] Dead `_NoRemoteBanner` / unused `_NoRemoteView` in `ui/components/no_remote_view.py`
- **Files**: `ui/components/no_remote_view.py` (191 lines), `ui/commit_view.py:42,131-133,485`
- **Issue**: `_NoRemoteBanner` is constructed in `CommitViewPage.__init__` (`commit_view.py:131`), immediately
  `.hide()`-ed with the comment "replaced by header status badge" (`:132`), added to the layout (`:133`),
  and hidden again later (`:485`) — it's never shown again anywhere in the file. `_NoRemoteView` is
  imported (`:42`) but never instantiated at all. Separately, `_NoRemoteBanner.set_error(msg)`
  (`no_remote_view.py:175-177`) silently discards its `msg` argument — harmless today since the widget
  is never shown, but would be a silent-failure bug if the banner were ever revived (e.g. for its
  `show_deleted()` "repo was deleted" state, which also looks unreferenced).
- **Suggested direction**: if the header status badge fully replaced this banner/view, remove
  `_NoRemoteBanner`/`_NoRemoteView` and the now-pointless `self._no_remote_banner` plumbing in
  `commit_view.py` (construction, the two `.hide()` calls, layout insertion, and the unused
  `_NoRemoteView` import). If there's a plan to revive it, fix `set_error()` to display `msg` first.
- **Owner**: `code-quality-refactor` (dead-code removal, likely natural fit alongside the
  `commit_view.py` decomposition already in progress).

"""Background QThread worker classes for CommitViewPage."""
from __future__ import annotations

import subprocess

from PyQt5.QtCore import QObject, pyqtSlot, pyqtSignal

from core.git_tracker import GitTracker


class _CollabLoader(QObject):
    """Fetches collaborators on a worker thread, emits list to main thread."""
    finished = pyqtSignal(list)

    def __init__(self, path: str, token: str):
        super().__init__()
        self._path  = path
        self._token = token

    @pyqtSlot()
    def run(self):
        t = GitTracker(self._path)
        try:
            t.open()
            result = t.get_collaborators(self._token)
        except Exception:
            result = []
        finally:
            t.close()
        self.finished.emit(result)


class _Loader(QObject):
    finished = pyqtSignal(list, dict, set, set, set, set)  # commits, branch_tip_map, local_only, unpushed, stash_shas, remote_tip_shas

    def __init__(self, path: str):
        super().__init__()
        self._path = path

    @pyqtSlot()
    def run(self):
        t = GitTracker(self._path)
        try:
            t.open()
            commits, branch_tip_map, local_only, remote_tip_shas = t.graph_commits()
            unpushed = t.get_unpushed_shas()
            from core.ops import get_stash_commit_shas, has_uncommitted_changes
            stash_shas = get_stash_commit_shas(self._path)
            if has_uncommitted_changes(self._path):
                head = t.head_sha()
                if head:
                    stash_shas = stash_shas | {head}
        except Exception:
            commits, branch_tip_map, local_only, unpushed, stash_shas, remote_tip_shas = [], {}, set(), set(), set(), set()
        finally:
            t.close()
        try:
            self.finished.emit(commits, branch_tip_map, local_only, unpushed, stash_shas, remote_tip_shas)
        except RuntimeError:
            pass


class _CommitDetailWorker(QObject):
    finished = pyqtSignal(object, dict, list, int)   # commit, detail, files, gen

    def __init__(self, path: str, commit, gen: int):
        super().__init__()
        self._path   = path
        self._commit = commit
        self._gen    = gen

    @pyqtSlot()
    def run(self):
        t = GitTracker(self._path)
        try:
            t.open()
            detail = t.commit_detail(self._commit.sha)
            files  = t.commit_files(self._commit.sha)
        except Exception:
            detail, files = {}, []
        finally:
            t.close()
        self.finished.emit(self._commit, detail, files, self._gen)


class _VisibilityWorker(QObject):
    finished = pyqtSignal(str, str, bool)   # url, visibility, can_push

    def __init__(self, path: str, token: str):
        super().__init__()
        self._path  = path
        self._token = token

    @pyqtSlot()
    def run(self):
        t = GitTracker(self._path)
        try:
            t.open()
            url = t.remote_url()
            vis, can_push = t.repo_visibility(self._token)
        except Exception:
            url, vis, can_push = "", "", False
        finally:
            t.close()
        self.finished.emit(url, vis, can_push)


class _FetchWorker(QObject):
    finished = pyqtSignal(bool, str)   # changed, best_guess_pusher

    def __init__(self, path: str):
        super().__init__()
        self._path = path

    @pyqtSlot()
    def run(self):
        t = GitTracker(self._path)
        try:
            t.open()
            changed, author = t.fetch_with_author()
        except Exception:
            changed, author = False, ""
        finally:
            t.close()
        self.finished.emit(changed, author)


class _BranchCountWorker(QObject):
    """Counts unique commits per branch not reachable from the default branch."""
    finished = pyqtSignal(dict)   # {branch_name: unique_count}

    def __init__(self, path: str, branches: list, default_branch: str):
        super().__init__()
        self._path     = path
        self._branches = branches
        self._default  = default_branch

    @pyqtSlot()
    def run(self):
        from core.ops import branch_unique_count
        counts = {b: branch_unique_count(self._path, b, self._default)
                  for b in self._branches}
        self.finished.emit(counts)


class _UncommittedRefreshWorker(QObject):
    """Lightweight background poll: dirty-state check + live diff + stash fingerprint."""
    finished = pyqtSignal(bool, list, str)   # dirty, files, stash_id

    def __init__(self, path: str):
        super().__init__()
        self._path = path

    @pyqtSlot()
    def run(self):
        from core.ops import has_uncommitted_changes, get_working_dir_diff_files, get_stash_list_id
        dirty = has_uncommitted_changes(self._path)
        files = get_working_dir_diff_files(self._path) if dirty else []
        stash_id = get_stash_list_id(self._path)
        self.finished.emit(dirty, files, stash_id)


class _NavigateWorker(QObject):
    """Runs stash-save / checkout / stash-restore on a background thread."""
    finished = pyqtSignal(bool, str)   # ok, error_message

    def __init__(self, path: str, sha: str, current_head: str, discard: bool = False):
        super().__init__()
        self._path         = path
        self._sha          = sha
        self._current_head = current_head
        self._discard      = discard

    @pyqtSlot()
    def run(self):
        from core.ops import (
            has_uncommitted_changes, get_stash_ref_for_commit,
            drop_stash, create_auto_stash, pop_auto_stash,
            checkout_commit, apply_stash, reset_hard,
            discard_all_changes,
        )
        path = self._path
        sha  = self._sha

        created_stash_id = None
        if self._discard:
            ok, err = discard_all_changes(path)
            if not ok:
                self.finished.emit(False, f"discard-failed: {err}")
                return
        elif has_uncommitted_changes(path):
            if self._current_head:
                old_ref = get_stash_ref_for_commit(path, self._current_head)
                if old_ref:
                    drop_stash(path, old_ref)
            stashed_files, created_stash_id = create_auto_stash(path)
            if not created_stash_id and has_uncommitted_changes(path):
                self.finished.emit(False, "auto-save-failed")
                return

        ok, err = checkout_commit(path, sha)
        if not ok:
            if created_stash_id:
                pop_auto_stash(path, created_stash_id)
            self.finished.emit(False, err)
            return

        target_ref = get_stash_ref_for_commit(path, sha)
        if target_ref:
            if not apply_stash(path, target_ref):
                reset_hard(path)
                # apply_stash left the working tree mid-conflict; reset_hard
                # discarded that attempt, so the stash itself is no longer
                # recoverable in any useful state — drop it so it doesn't sit
                # in `git stash list` forever (matches the "couldn't be
                # restored" message shown to the user).
                drop_stash(path, target_ref)
                self.finished.emit(True, "stash-conflict")
                return

        self.finished.emit(True, "")


class _FirstCommitWorker(QObject):
    finished = pyqtSignal(bool)

    def __init__(self, path: str):
        super().__init__()
        self._path = path

    @pyqtSlot()
    def run(self):
        subprocess.run(["git", "add", "."], cwd=self._path, capture_output=True)
        r = subprocess.run(
            ["git", "commit", "--allow-empty", "-m", "Initial commit"],
            cwd=self._path, capture_output=True,
        )
        self.finished.emit(r.returncode == 0)


class _CreateRepoWorker(QObject):
    finished = pyqtSignal(bool, str, str)   # success, error, clone_url

    def __init__(self, repo_path: str, repo_name: str, token: str, username: str,
                 private: bool = True, user_name: str = "", user_email: str = ""):
        super().__init__()
        self._path       = repo_path
        self._name       = repo_name
        self._token      = token
        self._username   = username
        self._private    = private
        self._user_name  = user_name
        self._user_email = user_email

    @pyqtSlot()
    def run(self):
        from core.ops import create_github_repo, push_to_github
        ok, err, clone_url = create_github_repo(self._name, self._private, self._token)
        if not ok:
            self.finished.emit(False, err, "")
            return
        ok, err = push_to_github(self._path, clone_url, self._username, self._token,
                                 self._user_name, self._user_email)
        self.finished.emit(ok, err, clone_url)

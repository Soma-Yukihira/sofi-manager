from __future__ import annotations

import subprocess
import threading
import unittest
from unittest.mock import patch

import updater


def _cp(returncode: int = 0, stdout: str = "", stderr: str = "") -> subprocess.CompletedProcess:
    return subprocess.CompletedProcess(args=["git"], returncode=returncode, stdout=stdout, stderr=stderr)


class GitGate(unittest.TestCase):
    """Behavior of the `.git/` presence gate on the low-level helpers."""

    def test_behind_count_returns_zero_without_git_dir(self):
        with patch.object(updater, "is_git_clone", return_value=False):
            self.assertEqual(updater.behind_count(), 0)

    def test_ahead_count_returns_zero_without_git_dir(self):
        with patch.object(updater, "is_git_clone", return_value=False):
            self.assertEqual(updater.ahead_count(), 0)

    def test_has_local_changes_returns_false_without_git_dir(self):
        with patch.object(updater, "is_git_clone", return_value=False):
            self.assertFalse(updater.has_local_changes())

    def test_fetch_returns_false_without_git_dir(self):
        with patch.object(updater, "is_git_clone", return_value=False):
            self.assertFalse(updater._fetch())


class IntParser(unittest.TestCase):
    def test_parses_trimmed_integer(self):
        self.assertEqual(updater._int(" 42 \n"), 42)

    def test_empty_string_is_zero(self):
        self.assertEqual(updater._int(""), 0)

    def test_none_is_zero(self):
        self.assertEqual(updater._int(None), 0)  # type: ignore[arg-type]

    def test_garbage_is_zero(self):
        self.assertEqual(updater._int("not-a-number"), 0)


class GitCommandHelpers(unittest.TestCase):
    """`behind_count`, `ahead_count`, etc. on top of a fake `_git`."""

    def test_behind_count_reads_rev_list_output(self):
        with patch.object(updater, "is_git_clone", return_value=True), \
             patch.object(updater, "_git", return_value=_cp(stdout="3\n")):
            self.assertEqual(updater.behind_count(), 3)

    def test_behind_count_returns_zero_on_git_failure(self):
        with patch.object(updater, "is_git_clone", return_value=True), \
             patch.object(updater, "_git", return_value=_cp(returncode=1, stdout="3\n")):
            self.assertEqual(updater.behind_count(), 0)

    def test_ahead_count_reads_rev_list_output(self):
        with patch.object(updater, "is_git_clone", return_value=True), \
             patch.object(updater, "_git", return_value=_cp(stdout="2\n")):
            self.assertEqual(updater.ahead_count(), 2)

    def test_behind_main_count_reads_rev_list_output(self):
        with patch.object(updater, "is_git_clone", return_value=True), \
             patch.object(updater, "_git", return_value=_cp(stdout="4\n")) as g:
            self.assertEqual(updater.behind_main_count(), 4)
            g.assert_called_with("rev-list", "--count", "main..origin/main")

    def test_behind_main_count_returns_zero_on_git_failure(self):
        with patch.object(updater, "is_git_clone", return_value=True), \
             patch.object(updater, "_git", return_value=_cp(returncode=128, stdout="")):
            self.assertEqual(updater.behind_main_count(), 0)

    def test_behind_main_count_returns_zero_without_git_dir(self):
        with patch.object(updater, "is_git_clone", return_value=False):
            self.assertEqual(updater.behind_main_count(), 0)

    def test_has_local_changes_true_when_porcelain_nonempty(self):
        with patch.object(updater, "is_git_clone", return_value=True), \
             patch.object(updater, "_git", return_value=_cp(stdout=" M file.py\n")):
            self.assertTrue(updater.has_local_changes())

    def test_has_local_changes_false_when_porcelain_empty(self):
        with patch.object(updater, "is_git_clone", return_value=True), \
             patch.object(updater, "_git", return_value=_cp(stdout="")):
            self.assertFalse(updater.has_local_changes())

    def test_current_branch_returns_stripped_name(self):
        with patch.object(updater, "_git", return_value=_cp(stdout="main\n")):
            self.assertEqual(updater.current_branch(), "main")

    def test_current_branch_empty_on_failure(self):
        with patch.object(updater, "_git", return_value=_cp(returncode=128, stdout="")):
            self.assertEqual(updater.current_branch(), "")


class FetchHelper(unittest.TestCase):
    def test_fetch_returns_true_on_success(self):
        with patch.object(updater, "is_git_clone", return_value=True), \
             patch.object(updater, "_git", return_value=_cp(returncode=0)):
            self.assertTrue(updater._fetch())

    def test_fetch_returns_false_on_nonzero(self):
        with patch.object(updater, "is_git_clone", return_value=True), \
             patch.object(updater, "_git", return_value=_cp(returncode=1)):
            self.assertFalse(updater._fetch())

    def test_fetch_returns_false_when_git_missing_from_path(self):
        with patch.object(updater, "is_git_clone", return_value=True), \
             patch.object(updater, "_git", side_effect=FileNotFoundError("git")):
            self.assertFalse(updater._fetch())

    def test_fetch_returns_false_on_oserror(self):
        with patch.object(updater, "is_git_clone", return_value=True), \
             patch.object(updater, "_git", side_effect=OSError("permission denied")):
            self.assertFalse(updater._fetch())


class SafeToPull(unittest.TestCase):
    def test_true_when_on_main_clean_and_not_ahead(self):
        with patch.object(updater, "is_git_clone", return_value=True), \
             patch.object(updater, "current_branch", return_value="main"), \
             patch.object(updater, "ahead_count", return_value=0), \
             patch.object(updater, "has_local_changes", return_value=False):
            self.assertTrue(updater._safe_to_pull())

    def test_false_when_not_git(self):
        with patch.object(updater, "is_git_clone", return_value=False):
            self.assertFalse(updater._safe_to_pull())

    def test_false_when_on_wrong_branch(self):
        with patch.object(updater, "is_git_clone", return_value=True), \
             patch.object(updater, "current_branch", return_value="feat/x"), \
             patch.object(updater, "ahead_count", return_value=0), \
             patch.object(updater, "has_local_changes", return_value=False):
            self.assertFalse(updater._safe_to_pull())

    def test_false_when_ahead(self):
        with patch.object(updater, "is_git_clone", return_value=True), \
             patch.object(updater, "current_branch", return_value="main"), \
             patch.object(updater, "ahead_count", return_value=1), \
             patch.object(updater, "has_local_changes", return_value=False):
            self.assertFalse(updater._safe_to_pull())

    def test_false_when_dirty(self):
        with patch.object(updater, "is_git_clone", return_value=True), \
             patch.object(updater, "current_branch", return_value="main"), \
             patch.object(updater, "ahead_count", return_value=0), \
             patch.object(updater, "has_local_changes", return_value=True):
            self.assertFalse(updater._safe_to_pull())


class PullHelper(unittest.TestCase):
    def test_pull_success(self):
        with patch.object(updater, "_git", return_value=_cp(returncode=0)):
            ok, msg = updater._pull()
        self.assertTrue(ok)
        self.assertEqual(msg, "OK")

    def test_pull_failure_returns_stderr(self):
        with patch.object(updater, "_git", return_value=_cp(returncode=1, stderr="diverged\n")):
            ok, msg = updater._pull()
        self.assertFalse(ok)
        self.assertEqual(msg, "diverged")

    def test_pull_failure_falls_back_to_stdout(self):
        with patch.object(updater, "_git", return_value=_cp(returncode=1, stdout="hint\n", stderr="")):
            ok, msg = updater._pull()
        self.assertFalse(ok)
        self.assertEqual(msg, "hint")


class ApplyPendingOnStartup(unittest.TestCase):
    def test_no_op_when_not_safe(self):
        with patch.object(updater, "_safe_to_pull", return_value=False), \
             patch.object(updater, "_restart") as mock_restart, \
             patch.object(updater, "_pull") as mock_pull:
            updater.apply_pending_on_startup()
        mock_restart.assert_not_called()
        mock_pull.assert_not_called()

    def test_no_op_when_not_behind(self):
        with patch.object(updater, "_safe_to_pull", return_value=True), \
             patch.object(updater, "behind_count", return_value=0), \
             patch.object(updater, "_restart") as mock_restart, \
             patch.object(updater, "_pull") as mock_pull:
            updater.apply_pending_on_startup()
        mock_restart.assert_not_called()
        mock_pull.assert_not_called()

    def test_restarts_after_successful_pull(self):
        with patch.object(updater, "_safe_to_pull", return_value=True), \
             patch.object(updater, "behind_count", return_value=2), \
             patch.object(updater, "_pull", return_value=(True, "OK")), \
             patch.object(updater, "_restart") as mock_restart:
            updater.apply_pending_on_startup()
        mock_restart.assert_called_once()

    def test_no_restart_when_pull_fails(self):
        with patch.object(updater, "_safe_to_pull", return_value=True), \
             patch.object(updater, "behind_count", return_value=2), \
             patch.object(updater, "_pull", return_value=(False, "diverged")), \
             patch.object(updater, "_restart") as mock_restart:
            updater.apply_pending_on_startup()
        mock_restart.assert_not_called()

    def test_swallows_pull_exception(self):
        with patch.object(updater, "_safe_to_pull", return_value=True), \
             patch.object(updater, "behind_count", return_value=1), \
             patch.object(updater, "_pull", side_effect=RuntimeError("boom")), \
             patch.object(updater, "_restart") as mock_restart:
            # Must not raise - the app must boot even if the updater explodes.
            updater.apply_pending_on_startup()
        mock_restart.assert_not_called()


class CheckInBackground(unittest.TestCase):
    def test_skipped_without_git_dir(self):
        callback_calls: list[int] = []
        with patch.object(updater, "is_git_clone", return_value=False), \
             patch.object(threading, "Thread") as mock_thread:
            updater.check_in_background(lambda n: callback_calls.append(n))
        mock_thread.assert_not_called()
        self.assertEqual(callback_calls, [])

    def _run_worker_synchronously(self):
        # Replace threading.Thread with a stub that runs the target inline,
        # so we can assert the callback synchronously.
        class _InlineThread:
            def __init__(self, target, name=None, daemon=None):
                self._target = target
            def start(self):
                self._target()
        return patch.object(threading, "Thread", _InlineThread)

    def test_fires_callback_when_fetch_finds_new_commits(self):
        seen: list[int] = []
        with patch.object(updater, "is_git_clone", return_value=True), \
             patch.object(updater, "_fetch", return_value=True), \
             patch.object(updater, "behind_count", return_value=3), \
             patch.object(updater, "_safe_to_pull", return_value=True), \
             self._run_worker_synchronously():
            updater.check_in_background(seen.append)
        self.assertEqual(seen, [3])

    def test_no_callback_when_fetch_fails(self):
        seen: list[int] = []
        with patch.object(updater, "is_git_clone", return_value=True), \
             patch.object(updater, "_fetch", return_value=False), \
             self._run_worker_synchronously():
            updater.check_in_background(seen.append)
        self.assertEqual(seen, [])

    def test_no_callback_when_uptodate(self):
        seen: list[int] = []
        with patch.object(updater, "is_git_clone", return_value=True), \
             patch.object(updater, "_fetch", return_value=True), \
             patch.object(updater, "behind_count", return_value=0), \
             self._run_worker_synchronously():
            updater.check_in_background(seen.append)
        self.assertEqual(seen, [])

    def test_no_callback_when_unsafe_to_pull(self):
        seen: list[int] = []
        with patch.object(updater, "is_git_clone", return_value=True), \
             patch.object(updater, "_fetch", return_value=True), \
             patch.object(updater, "behind_count", return_value=2), \
             patch.object(updater, "_safe_to_pull", return_value=False), \
             self._run_worker_synchronously():
            updater.check_in_background(seen.append)
        self.assertEqual(seen, [])

    def test_swallows_worker_exception(self):
        seen: list[int] = []
        with patch.object(updater, "is_git_clone", return_value=True), \
             patch.object(updater, "_fetch", side_effect=RuntimeError("boom")), \
             self._run_worker_synchronously():
            updater.check_in_background(seen.append)
        self.assertEqual(seen, [])


class FetchAndStatus(unittest.TestCase):
    """The seven states surfaced by the manual `Verifier les MAJ` button."""

    def test_not_git(self):
        with patch.object(updater, "is_git_clone", return_value=False):
            self.assertEqual(updater.fetch_and_status(), {"state": "not_git", "behind": 0})

    def test_fetch_failed(self):
        with patch.object(updater, "is_git_clone", return_value=True), \
             patch.object(updater, "_fetch", return_value=False):
            self.assertEqual(updater.fetch_and_status(), {"state": "fetch_failed", "behind": 0})

    def test_available_on_feature_branch_ignores_local_branch(self):
        # Dev working on a feature branch still wants to know when main moved.
        # dirty/ahead gates do not apply because the user is not on main and
        # therefore cannot trigger the inline fast-forward anyway.
        with patch.object(updater, "is_git_clone", return_value=True), \
             patch.object(updater, "_fetch", return_value=True), \
             patch.object(updater, "current_branch", return_value="feat/x"), \
             patch.object(updater, "has_local_changes", return_value=True), \
             patch.object(updater, "ahead_count", return_value=3), \
             patch.object(updater, "behind_main_count", return_value=4):
            self.assertEqual(updater.fetch_and_status(), {"state": "available", "behind": 4})

    def test_uptodate_on_feature_branch(self):
        with patch.object(updater, "is_git_clone", return_value=True), \
             patch.object(updater, "_fetch", return_value=True), \
             patch.object(updater, "current_branch", return_value="feat/x"), \
             patch.object(updater, "behind_main_count", return_value=0):
            self.assertEqual(updater.fetch_and_status(), {"state": "uptodate", "behind": 0})

    def test_dirty(self):
        with patch.object(updater, "is_git_clone", return_value=True), \
             patch.object(updater, "_fetch", return_value=True), \
             patch.object(updater, "behind_main_count", return_value=2), \
             patch.object(updater, "current_branch", return_value="main"), \
             patch.object(updater, "has_local_changes", return_value=True):
            self.assertEqual(updater.fetch_and_status(), {"state": "dirty", "behind": 2})

    def test_ahead(self):
        with patch.object(updater, "is_git_clone", return_value=True), \
             patch.object(updater, "_fetch", return_value=True), \
             patch.object(updater, "behind_main_count", return_value=2), \
             patch.object(updater, "current_branch", return_value="main"), \
             patch.object(updater, "has_local_changes", return_value=False), \
             patch.object(updater, "ahead_count", return_value=1):
            self.assertEqual(updater.fetch_and_status(), {"state": "ahead", "behind": 2})

    def test_uptodate(self):
        with patch.object(updater, "is_git_clone", return_value=True), \
             patch.object(updater, "_fetch", return_value=True), \
             patch.object(updater, "behind_main_count", return_value=0):
            self.assertEqual(updater.fetch_and_status(), {"state": "uptodate", "behind": 0})

    def test_available(self):
        with patch.object(updater, "is_git_clone", return_value=True), \
             patch.object(updater, "_fetch", return_value=True), \
             patch.object(updater, "behind_main_count", return_value=5), \
             patch.object(updater, "current_branch", return_value="main"), \
             patch.object(updater, "has_local_changes", return_value=False), \
             patch.object(updater, "ahead_count", return_value=0):
            self.assertEqual(updater.fetch_and_status(), {"state": "available", "behind": 5})


class ApplyAndRestart(unittest.TestCase):
    def test_refuses_when_not_safe(self):
        with patch.object(updater, "_safe_to_pull", return_value=False), \
             patch.object(updater, "_restart") as mock_restart, \
             patch.object(updater, "_pull") as mock_pull:
            ok, msg = updater.apply_and_restart()
        self.assertFalse(ok)
        self.assertIn("not safe", msg.lower())
        mock_pull.assert_not_called()
        mock_restart.assert_not_called()

    def test_returns_error_when_pull_fails(self):
        with patch.object(updater, "_safe_to_pull", return_value=True), \
             patch.object(updater, "_pull", return_value=(False, "diverged")), \
             patch.object(updater, "_restart") as mock_restart:
            ok, msg = updater.apply_and_restart()
        self.assertFalse(ok)
        self.assertEqual(msg, "diverged")
        mock_restart.assert_not_called()

    def test_restarts_on_success(self):
        with patch.object(updater, "_safe_to_pull", return_value=True), \
             patch.object(updater, "_pull", return_value=(True, "OK")), \
             patch.object(updater, "_restart") as mock_restart:
            updater.apply_and_restart()
        mock_restart.assert_called_once()


class GitInvocation(unittest.TestCase):
    """`_git` must shell out with the right cwd and (on Windows) the
    CREATE_NO_WINDOW flag, otherwise every git call flashes a cmd window
    under pythonw.exe."""

    def test_runs_git_in_repo_root_with_captured_output(self):
        captured: dict = {}

        def fake_run(cmd, **kwargs):
            captured["cmd"] = cmd
            captured["kwargs"] = kwargs
            return _cp(stdout="ok")

        with patch.object(subprocess, "run", side_effect=fake_run):
            updater._git("status", "--porcelain")

        self.assertEqual(captured["cmd"], ["git", "status", "--porcelain"])
        self.assertEqual(captured["kwargs"]["cwd"], str(updater.ROOT))
        self.assertTrue(captured["kwargs"]["capture_output"])
        self.assertTrue(captured["kwargs"]["text"])
        # creationflags must be present (0 on POSIX, CREATE_NO_WINDOW on Windows)
        self.assertIn("creationflags", captured["kwargs"])


if __name__ == "__main__":
    unittest.main()

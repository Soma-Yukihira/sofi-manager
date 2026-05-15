from __future__ import annotations

import io
import subprocess
import tempfile
import threading
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

import updater


def _cp(returncode: int = 0, stdout: str = "", stderr: str = "") -> subprocess.CompletedProcess:
    return subprocess.CompletedProcess(
        args=["git"], returncode=returncode, stdout=stdout, stderr=stderr
    )


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
        with (
            patch.object(updater, "is_git_clone", return_value=True),
            patch.object(updater, "_git", return_value=_cp(stdout="3\n")),
        ):
            self.assertEqual(updater.behind_count(), 3)

    def test_behind_count_returns_zero_on_git_failure(self):
        with (
            patch.object(updater, "is_git_clone", return_value=True),
            patch.object(updater, "_git", return_value=_cp(returncode=1, stdout="3\n")),
        ):
            self.assertEqual(updater.behind_count(), 0)

    def test_ahead_count_reads_rev_list_output(self):
        with (
            patch.object(updater, "is_git_clone", return_value=True),
            patch.object(updater, "_git", return_value=_cp(stdout="2\n")),
        ):
            self.assertEqual(updater.ahead_count(), 2)

    def test_behind_main_count_reads_rev_list_output(self):
        with (
            patch.object(updater, "is_git_clone", return_value=True),
            patch.object(updater, "_git", return_value=_cp(stdout="4\n")) as g,
        ):
            self.assertEqual(updater.behind_main_count(), 4)
            g.assert_called_with("rev-list", "--count", "main..origin/main")

    def test_behind_main_count_returns_zero_on_git_failure(self):
        with (
            patch.object(updater, "is_git_clone", return_value=True),
            patch.object(updater, "_git", return_value=_cp(returncode=128, stdout="")),
        ):
            self.assertEqual(updater.behind_main_count(), 0)

    def test_behind_main_count_returns_zero_without_git_dir(self):
        with patch.object(updater, "is_git_clone", return_value=False):
            self.assertEqual(updater.behind_main_count(), 0)

    def test_has_local_changes_true_when_porcelain_nonempty(self):
        with (
            patch.object(updater, "is_git_clone", return_value=True),
            patch.object(updater, "_git", return_value=_cp(stdout=" M file.py\n")),
        ):
            self.assertTrue(updater.has_local_changes())

    def test_has_local_changes_false_when_porcelain_empty(self):
        with (
            patch.object(updater, "is_git_clone", return_value=True),
            patch.object(updater, "_git", return_value=_cp(stdout="")),
        ):
            self.assertFalse(updater.has_local_changes())

    def test_current_branch_returns_stripped_name(self):
        with patch.object(updater, "_git", return_value=_cp(stdout="main\n")):
            self.assertEqual(updater.current_branch(), "main")

    def test_current_branch_empty_on_failure(self):
        with patch.object(updater, "_git", return_value=_cp(returncode=128, stdout="")):
            self.assertEqual(updater.current_branch(), "")


class FetchHelper(unittest.TestCase):
    def test_fetch_returns_true_on_success(self):
        with (
            patch.object(updater, "is_git_clone", return_value=True),
            patch.object(updater, "_git", return_value=_cp(returncode=0)),
        ):
            self.assertTrue(updater._fetch())

    def test_fetch_returns_false_on_nonzero(self):
        with (
            patch.object(updater, "is_git_clone", return_value=True),
            patch.object(updater, "_git", return_value=_cp(returncode=1)),
        ):
            self.assertFalse(updater._fetch())

    def test_fetch_returns_false_when_git_missing_from_path(self):
        with (
            patch.object(updater, "is_git_clone", return_value=True),
            patch.object(updater, "_git", side_effect=FileNotFoundError("git")),
        ):
            self.assertFalse(updater._fetch())

    def test_fetch_returns_false_on_oserror(self):
        with (
            patch.object(updater, "is_git_clone", return_value=True),
            patch.object(updater, "_git", side_effect=OSError("permission denied")),
        ):
            self.assertFalse(updater._fetch())


class SafeToPull(unittest.TestCase):
    def test_true_when_on_main_clean_and_not_ahead(self):
        with (
            patch.object(updater, "is_git_clone", return_value=True),
            patch.object(updater, "current_branch", return_value="main"),
            patch.object(updater, "ahead_count", return_value=0),
            patch.object(updater, "has_local_changes", return_value=False),
        ):
            self.assertTrue(updater._safe_to_pull())

    def test_false_when_not_git(self):
        with patch.object(updater, "is_git_clone", return_value=False):
            self.assertFalse(updater._safe_to_pull())

    def test_false_when_on_wrong_branch(self):
        with (
            patch.object(updater, "is_git_clone", return_value=True),
            patch.object(updater, "current_branch", return_value="feat/x"),
            patch.object(updater, "ahead_count", return_value=0),
            patch.object(updater, "has_local_changes", return_value=False),
        ):
            self.assertFalse(updater._safe_to_pull())

    def test_false_when_ahead(self):
        with (
            patch.object(updater, "is_git_clone", return_value=True),
            patch.object(updater, "current_branch", return_value="main"),
            patch.object(updater, "ahead_count", return_value=1),
            patch.object(updater, "has_local_changes", return_value=False),
        ):
            self.assertFalse(updater._safe_to_pull())

    def test_false_when_dirty(self):
        with (
            patch.object(updater, "is_git_clone", return_value=True),
            patch.object(updater, "current_branch", return_value="main"),
            patch.object(updater, "ahead_count", return_value=0),
            patch.object(updater, "has_local_changes", return_value=True),
        ):
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
        with patch.object(
            updater, "_git", return_value=_cp(returncode=1, stdout="hint\n", stderr="")
        ):
            ok, msg = updater._pull()
        self.assertFalse(ok)
        self.assertEqual(msg, "hint")


class ApplyPendingOnStartup(unittest.TestCase):
    def test_no_op_when_not_safe(self):
        with (
            patch.object(updater, "_safe_to_pull", return_value=False),
            patch.object(updater, "_restart") as mock_restart,
            patch.object(updater, "_pull") as mock_pull,
        ):
            updater.apply_pending_on_startup()
        mock_restart.assert_not_called()
        mock_pull.assert_not_called()

    def test_no_op_when_not_behind(self):
        with (
            patch.object(updater, "_safe_to_pull", return_value=True),
            patch.object(updater, "behind_count", return_value=0),
            patch.object(updater, "_restart") as mock_restart,
            patch.object(updater, "_pull") as mock_pull,
        ):
            updater.apply_pending_on_startup()
        mock_restart.assert_not_called()
        mock_pull.assert_not_called()

    def test_restarts_after_successful_pull(self):
        with (
            patch.object(updater, "_safe_to_pull", return_value=True),
            patch.object(updater, "behind_count", return_value=2),
            patch.object(updater, "_pull", return_value=(True, "OK")),
            patch.object(updater, "_restart") as mock_restart,
        ):
            updater.apply_pending_on_startup()
        mock_restart.assert_called_once()

    def test_no_restart_when_pull_fails(self):
        with (
            patch.object(updater, "_safe_to_pull", return_value=True),
            patch.object(updater, "behind_count", return_value=2),
            patch.object(updater, "_pull", return_value=(False, "diverged")),
            patch.object(updater, "_restart") as mock_restart,
        ):
            updater.apply_pending_on_startup()
        mock_restart.assert_not_called()

    def test_swallows_pull_exception(self):
        with (
            patch.object(updater, "_safe_to_pull", return_value=True),
            patch.object(updater, "behind_count", return_value=1),
            patch.object(updater, "_pull", side_effect=RuntimeError("boom")),
            patch.object(updater, "_restart") as mock_restart,
        ):
            # Must not raise - the app must boot even if the updater explodes.
            updater.apply_pending_on_startup()
        mock_restart.assert_not_called()


class CheckInBackground(unittest.TestCase):
    def test_skipped_without_git_dir(self):
        callback_calls: list[int] = []
        with (
            patch.object(updater, "is_git_clone", return_value=False),
            patch.object(threading, "Thread") as mock_thread,
        ):
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
        with (
            patch.object(updater, "is_git_clone", return_value=True),
            patch.object(updater, "_fetch", return_value=True),
            patch.object(updater, "behind_count", return_value=3),
            patch.object(updater, "_safe_to_pull", return_value=True),
            self._run_worker_synchronously(),
        ):
            updater.check_in_background(seen.append)
        self.assertEqual(seen, [3])

    def test_no_callback_when_fetch_fails(self):
        seen: list[int] = []
        with (
            patch.object(updater, "is_git_clone", return_value=True),
            patch.object(updater, "_fetch", return_value=False),
            self._run_worker_synchronously(),
        ):
            updater.check_in_background(seen.append)
        self.assertEqual(seen, [])

    def test_no_callback_when_uptodate(self):
        seen: list[int] = []
        with (
            patch.object(updater, "is_git_clone", return_value=True),
            patch.object(updater, "_fetch", return_value=True),
            patch.object(updater, "behind_count", return_value=0),
            self._run_worker_synchronously(),
        ):
            updater.check_in_background(seen.append)
        self.assertEqual(seen, [])

    def test_no_callback_when_unsafe_to_pull(self):
        seen: list[int] = []
        with (
            patch.object(updater, "is_git_clone", return_value=True),
            patch.object(updater, "_fetch", return_value=True),
            patch.object(updater, "behind_count", return_value=2),
            patch.object(updater, "_safe_to_pull", return_value=False),
            self._run_worker_synchronously(),
        ):
            updater.check_in_background(seen.append)
        self.assertEqual(seen, [])

    def test_swallows_worker_exception(self):
        seen: list[int] = []
        with (
            patch.object(updater, "is_git_clone", return_value=True),
            patch.object(updater, "_fetch", side_effect=RuntimeError("boom")),
            self._run_worker_synchronously(),
        ):
            updater.check_in_background(seen.append)
        self.assertEqual(seen, [])


class FetchAndStatus(unittest.TestCase):
    """The seven states surfaced by the manual `Verifier les MAJ` button."""

    def test_not_git(self):
        with patch.object(updater, "is_git_clone", return_value=False):
            self.assertEqual(updater.fetch_and_status(), {"state": "not_git", "behind": 0})

    def test_fetch_failed(self):
        with (
            patch.object(updater, "is_git_clone", return_value=True),
            patch.object(updater, "_fetch", return_value=False),
        ):
            self.assertEqual(updater.fetch_and_status(), {"state": "fetch_failed", "behind": 0})

    def test_available_on_feature_branch_ignores_local_branch(self):
        # Dev working on a feature branch still wants to know when main moved.
        # dirty/ahead gates do not apply because the user is not on main and
        # therefore cannot trigger the inline fast-forward anyway.
        with (
            patch.object(updater, "is_git_clone", return_value=True),
            patch.object(updater, "_fetch", return_value=True),
            patch.object(updater, "current_branch", return_value="feat/x"),
            patch.object(updater, "has_local_changes", return_value=True),
            patch.object(updater, "ahead_count", return_value=3),
            patch.object(updater, "behind_main_count", return_value=4),
        ):
            self.assertEqual(updater.fetch_and_status(), {"state": "available", "behind": 4})

    def test_uptodate_on_feature_branch(self):
        with (
            patch.object(updater, "is_git_clone", return_value=True),
            patch.object(updater, "_fetch", return_value=True),
            patch.object(updater, "current_branch", return_value="feat/x"),
            patch.object(updater, "behind_main_count", return_value=0),
        ):
            self.assertEqual(updater.fetch_and_status(), {"state": "uptodate", "behind": 0})

    def test_dirty(self):
        with (
            patch.object(updater, "is_git_clone", return_value=True),
            patch.object(updater, "_fetch", return_value=True),
            patch.object(updater, "behind_main_count", return_value=2),
            patch.object(updater, "current_branch", return_value="main"),
            patch.object(updater, "has_local_changes", return_value=True),
        ):
            self.assertEqual(updater.fetch_and_status(), {"state": "dirty", "behind": 2})

    def test_ahead(self):
        with (
            patch.object(updater, "is_git_clone", return_value=True),
            patch.object(updater, "_fetch", return_value=True),
            patch.object(updater, "behind_main_count", return_value=2),
            patch.object(updater, "current_branch", return_value="main"),
            patch.object(updater, "has_local_changes", return_value=False),
            patch.object(updater, "ahead_count", return_value=1),
        ):
            self.assertEqual(updater.fetch_and_status(), {"state": "ahead", "behind": 2})

    def test_uptodate(self):
        with (
            patch.object(updater, "is_git_clone", return_value=True),
            patch.object(updater, "_fetch", return_value=True),
            patch.object(updater, "behind_main_count", return_value=0),
        ):
            self.assertEqual(updater.fetch_and_status(), {"state": "uptodate", "behind": 0})

    def test_available(self):
        with (
            patch.object(updater, "is_git_clone", return_value=True),
            patch.object(updater, "_fetch", return_value=True),
            patch.object(updater, "behind_main_count", return_value=5),
            patch.object(updater, "current_branch", return_value="main"),
            patch.object(updater, "has_local_changes", return_value=False),
            patch.object(updater, "ahead_count", return_value=0),
        ):
            self.assertEqual(updater.fetch_and_status(), {"state": "available", "behind": 5})


class SkipReason(unittest.TestCase):
    """Priority order of the five skip reasons surfaced by `skip_reason()`.

    The GUI uses this to passively explain why auto-updates are OFF.
    Frozen and no-git short-circuit ahead of any git-state probing because
    those installs can never auto-update at all - regardless of how the
    user's tree looks today, the updater is structurally disabled."""

    def test_returns_none_on_clean_main(self):
        with (
            patch.object(updater, "_is_frozen", return_value=False),
            patch.object(updater, "is_git_clone", return_value=True),
            patch.object(updater, "current_branch", return_value="main"),
            patch.object(updater, "has_local_changes", return_value=False),
            patch.object(updater, "ahead_count", return_value=0),
        ):
            self.assertIsNone(updater.skip_reason())

    def test_frozen_wins_over_everything(self):
        # A PyInstaller .exe is the dominant reason - even if a .git/ dir
        # happens to exist next to it, the running binary cannot pull.
        with (
            patch.object(updater, "_is_frozen", return_value=True),
            patch.object(updater, "is_git_clone", return_value=True),
            patch.object(updater, "current_branch", return_value="main"),
            patch.object(updater, "has_local_changes", return_value=True),
            patch.object(updater, "ahead_count", return_value=5),
        ):
            self.assertEqual(updater.skip_reason(), "frozen")

    def test_no_git_when_not_frozen_and_no_dot_git(self):
        with (
            patch.object(updater, "_is_frozen", return_value=False),
            patch.object(updater, "is_git_clone", return_value=False),
        ):
            self.assertEqual(updater.skip_reason(), "no-git")

    def test_off_main_on_feature_branch(self):
        with (
            patch.object(updater, "_is_frozen", return_value=False),
            patch.object(updater, "is_git_clone", return_value=True),
            patch.object(updater, "current_branch", return_value="feat/x"),
            patch.object(updater, "has_local_changes", return_value=False),
            patch.object(updater, "ahead_count", return_value=0),
        ):
            self.assertEqual(updater.skip_reason(), "off-main")

    def test_dirty_when_on_main_with_local_changes(self):
        with (
            patch.object(updater, "_is_frozen", return_value=False),
            patch.object(updater, "is_git_clone", return_value=True),
            patch.object(updater, "current_branch", return_value="main"),
            patch.object(updater, "has_local_changes", return_value=True),
            patch.object(updater, "ahead_count", return_value=0),
        ):
            self.assertEqual(updater.skip_reason(), "dirty")

    def test_ahead_when_on_main_clean_with_unpushed_commits(self):
        with (
            patch.object(updater, "_is_frozen", return_value=False),
            patch.object(updater, "is_git_clone", return_value=True),
            patch.object(updater, "current_branch", return_value="main"),
            patch.object(updater, "has_local_changes", return_value=False),
            patch.object(updater, "ahead_count", return_value=2),
        ):
            self.assertEqual(updater.skip_reason(), "ahead")

    def test_dirty_takes_precedence_over_ahead(self):
        # Both could be true at once; "dirty" is the more actionable reason
        # since unpushed commits alone don't block the user from working.
        with (
            patch.object(updater, "_is_frozen", return_value=False),
            patch.object(updater, "is_git_clone", return_value=True),
            patch.object(updater, "current_branch", return_value="main"),
            patch.object(updater, "has_local_changes", return_value=True),
            patch.object(updater, "ahead_count", return_value=3),
        ):
            self.assertEqual(updater.skip_reason(), "dirty")


class IsFrozen(unittest.TestCase):
    def test_returns_false_when_sys_frozen_absent(self):
        # `sys.frozen` is only set by PyInstaller; in dev it must be falsy
        # so the updater runs normally.
        with patch.object(updater.sys, "frozen", False, create=True):
            self.assertFalse(updater._is_frozen())

    def test_returns_true_when_sys_frozen_set(self):
        with patch.object(updater.sys, "frozen", True, create=True):
            self.assertTrue(updater._is_frozen())


class ApplyAndRestart(unittest.TestCase):
    def test_refuses_when_not_safe(self):
        with (
            patch.object(updater, "_safe_to_pull", return_value=False),
            patch.object(updater, "_restart") as mock_restart,
            patch.object(updater, "_pull") as mock_pull,
        ):
            ok, msg = updater.apply_and_restart()
        self.assertFalse(ok)
        self.assertIn("not safe", msg.lower())
        mock_pull.assert_not_called()
        mock_restart.assert_not_called()

    def test_returns_error_when_pull_fails(self):
        with (
            patch.object(updater, "_safe_to_pull", return_value=True),
            patch.object(updater, "_pull", return_value=(False, "diverged")),
            patch.object(updater, "_restart") as mock_restart,
        ):
            ok, msg = updater.apply_and_restart()
        self.assertFalse(ok)
        self.assertEqual(msg, "diverged")
        mock_restart.assert_not_called()

    def test_restarts_on_success(self):
        with (
            patch.object(updater, "_safe_to_pull", return_value=True),
            patch.object(updater, "_pull", return_value=(True, "OK")),
            patch.object(updater, "_restart") as mock_restart,
        ):
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


def _make_codeload_zip(
    sha: str = "deadbeef" * 5,
    files: dict[str, bytes] | None = None,
) -> bytes:
    """Build an in-memory ZIP mimicking the codeload layout.

    Real codeload zips wrap content in a single `<repo>-<full-sha>/` dir;
    `_apply_zip_bytes` is supposed to strip that prefix transparently.
    """
    if files is None:
        files = {"README.md": b"# new", "gui.py": b"print('new gui')\n"}
    buf = io.BytesIO()
    prefix = f"sofi-manager-{sha}/"
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr(prefix, b"")  # directory entry
        for name, content in files.items():
            zf.writestr(prefix + name, content)
    return buf.getvalue()


class ApplyZipBytes(unittest.TestCase):
    """Pure extract+overwrite helper. Network-free."""

    def test_strips_top_level_prefix_and_writes_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            dest = Path(tmp)
            ok, msg = updater._apply_zip_bytes(
                _make_codeload_zip(files={"a.py": b"A", "sub/b.py": b"B"}),
                dest,
            )
            self.assertTrue(ok, msg)
            # Files land directly in dest, NOT under sofi-manager-<sha>/ -
            # the wrapping directory is the codeload artifact, not part
            # of the repo, so the entire install would shift one level deep
            # if we forgot to strip it.
            self.assertEqual((dest / "a.py").read_bytes(), b"A")
            self.assertEqual((dest / "sub" / "b.py").read_bytes(), b"B")
            self.assertFalse(
                (dest / "sofi-manager-deadbeefdeadbeefdeadbeefdeadbeefdeadbeef").exists()
            )

    def test_overwrites_existing_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            dest = Path(tmp)
            (dest / "gui.py").write_bytes(b"OLD")
            updater._apply_zip_bytes(
                _make_codeload_zip(files={"gui.py": b"NEW"}),
                dest,
            )
            self.assertEqual((dest / "gui.py").read_bytes(), b"NEW")

    def test_preserves_unrelated_user_files(self):
        # User-data files (bots.json, settings.json) live under gitignore so
        # they are NEVER in a codeload zip. The applier must leave them alone.
        with tempfile.TemporaryDirectory() as tmp:
            dest = Path(tmp)
            (dest / "bots.json").write_bytes(b"USER_DATA")
            (dest / "settings.json").write_bytes(b"USER_SETTINGS")
            updater._apply_zip_bytes(
                _make_codeload_zip(files={"gui.py": b"NEW"}),
                dest,
            )
            self.assertEqual((dest / "bots.json").read_bytes(), b"USER_DATA")
            self.assertEqual((dest / "settings.json").read_bytes(), b"USER_SETTINGS")

    def test_creates_nested_directories(self):
        with tempfile.TemporaryDirectory() as tmp:
            dest = Path(tmp)
            updater._apply_zip_bytes(
                _make_codeload_zip(files={"tools/build.py": b"build", "tests/t.py": b"t"}),
                dest,
            )
            self.assertEqual((dest / "tools" / "build.py").read_bytes(), b"build")
            self.assertEqual((dest / "tests" / "t.py").read_bytes(), b"t")

    def test_rejects_zip_slip(self):
        # A malicious zip with a `..` path must not escape the dest dir.
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as zf:
            zf.writestr("sofi-manager-abc/", b"")
            zf.writestr("sofi-manager-abc/../escape.py", b"pwn")
        with tempfile.TemporaryDirectory() as tmp:
            ok, msg = updater._apply_zip_bytes(buf.getvalue(), Path(tmp))
        self.assertFalse(ok)
        self.assertIn("zip-slip", msg.lower())

    def test_rejects_empty_zip(self):
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w"):
            pass
        with tempfile.TemporaryDirectory() as tmp:
            ok, msg = updater._apply_zip_bytes(buf.getvalue(), Path(tmp))
        self.assertFalse(ok)
        self.assertEqual(msg, "empty zip")

    def test_rejects_unexpected_layout(self):
        # codeload always wraps in a single top-level dir. Multiple top-level
        # entries means we got something other than what we asked for.
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as zf:
            zf.writestr("dir1/file.py", b"a")
            zf.writestr("dir2/file.py", b"b")
        with tempfile.TemporaryDirectory() as tmp:
            ok, msg = updater._apply_zip_bytes(buf.getvalue(), Path(tmp))
        self.assertFalse(ok)
        self.assertEqual(msg, "unexpected zip layout")

    def test_rejects_bad_zip_bytes(self):
        with tempfile.TemporaryDirectory() as tmp:
            ok, _msg = updater._apply_zip_bytes(b"not a zip", Path(tmp))
        self.assertFalse(ok)


class FetchRemoteMainSha(unittest.TestCase):
    def test_returns_sha_from_api_json(self):
        with patch.object(updater, "_http_get_json", return_value={"sha": "a" * 40, "commit": {}}):
            self.assertEqual(updater.fetch_remote_main_sha(), "a" * 40)

    def test_returns_none_on_network_error(self):
        import urllib.error

        with patch.object(updater, "_http_get_json", side_effect=urllib.error.URLError("dns")):
            self.assertIsNone(updater.fetch_remote_main_sha())

    def test_returns_none_on_non_dict_payload(self):
        # GitHub returns an error object as a dict, but a defensive non-dict
        # (list / null / string) must not crash us.
        with patch.object(updater, "_http_get_json", return_value=["unexpected"]):
            self.assertIsNone(updater.fetch_remote_main_sha())

    def test_returns_none_on_missing_sha_field(self):
        with patch.object(updater, "_http_get_json", return_value={"message": "Not Found"}):
            self.assertIsNone(updater.fetch_remote_main_sha())

    def test_rejects_non_40_char_sha(self):
        with patch.object(updater, "_http_get_json", return_value={"sha": "abc123"}):
            self.assertIsNone(updater.fetch_remote_main_sha())

    def test_rejects_non_hex_sha(self):
        with patch.object(updater, "_http_get_json", return_value={"sha": "z" * 40}):
            self.assertIsNone(updater.fetch_remote_main_sha())


class ApplyZipUpdate(unittest.TestCase):
    def test_refuses_when_not_no_git_install(self):
        with patch.object(updater, "skip_reason", return_value=None):
            ok, msg, sha = updater.apply_zip_update()
        self.assertFalse(ok)
        self.assertIsNone(sha)
        self.assertIn("non-git", msg.lower())

    def test_returns_failure_when_sha_fetch_fails(self):
        with (
            patch.object(updater, "skip_reason", return_value="no-git"),
            patch.object(updater, "fetch_remote_main_sha", return_value=None),
        ):
            ok, _msg, sha = updater.apply_zip_update()
        self.assertFalse(ok)
        self.assertIsNone(sha)

    def test_returns_failure_when_download_fails(self):
        import urllib.error

        with (
            patch.object(updater, "skip_reason", return_value="no-git"),
            patch.object(updater, "fetch_remote_main_sha", return_value="a" * 40),
            patch.object(updater, "_http_get_bytes", side_effect=urllib.error.URLError("net")),
        ):
            ok, _msg, sha = updater.apply_zip_update()
        self.assertFalse(ok)
        self.assertIsNone(sha)

    def test_happy_path_returns_new_sha(self):
        with (
            patch.object(updater, "skip_reason", return_value="no-git"),
            patch.object(updater, "fetch_remote_main_sha", return_value="b" * 40),
            patch.object(updater, "_http_get_bytes", return_value=_make_codeload_zip()),
            patch.object(updater, "_apply_zip_bytes", return_value=(True, "OK")),
        ):
            ok, msg, sha = updater.apply_zip_update()
        self.assertTrue(ok)
        self.assertEqual(msg, "OK")
        self.assertEqual(sha, "b" * 40)


class CheckZipInBackground(unittest.TestCase):
    def _inline_thread(self):
        class _InlineThread:
            def __init__(self, target, name=None, daemon=None):
                self._t = target

            def start(self):
                self._t()

        return patch.object(threading, "Thread", _InlineThread)

    def test_noop_outside_no_git(self):
        # Git clones use the git fetch path, not this one.
        with (
            patch.object(updater, "skip_reason", return_value=None),
            patch.object(threading, "Thread") as mock_thread,
        ):
            updater.check_zip_in_background(None, lambda _s: None, lambda _s: None)
        mock_thread.assert_not_called()

    def test_calls_on_baseline_when_no_installed_sha(self):
        # First launch on a fresh ZIP install: no recorded SHA -> adopt
        # whatever upstream reports as the baseline, silently.
        seen: list[str] = []
        with (
            patch.object(updater, "skip_reason", return_value="no-git"),
            patch.object(updater, "fetch_remote_main_sha", return_value="c" * 40),
            self._inline_thread(),
        ):
            updater.check_zip_in_background(None, seen.append, lambda _s: None)
        self.assertEqual(seen, ["c" * 40])

    def test_calls_on_update_when_sha_differs(self):
        seen: list[str] = []
        with (
            patch.object(updater, "skip_reason", return_value="no-git"),
            patch.object(updater, "fetch_remote_main_sha", return_value="d" * 40),
            self._inline_thread(),
        ):
            updater.check_zip_in_background("e" * 40, lambda _s: None, seen.append)
        self.assertEqual(seen, ["d" * 40])

    def test_silent_when_sha_matches(self):
        baseline: list[str] = []
        available: list[str] = []
        with (
            patch.object(updater, "skip_reason", return_value="no-git"),
            patch.object(updater, "fetch_remote_main_sha", return_value="f" * 40),
            self._inline_thread(),
        ):
            updater.check_zip_in_background("f" * 40, baseline.append, available.append)
        self.assertEqual(baseline, [])
        self.assertEqual(available, [])

    def test_silent_when_sha_fetch_fails(self):
        baseline: list[str] = []
        available: list[str] = []
        with (
            patch.object(updater, "skip_reason", return_value="no-git"),
            patch.object(updater, "fetch_remote_main_sha", return_value=None),
            self._inline_thread(),
        ):
            updater.check_zip_in_background(None, baseline.append, available.append)
        self.assertEqual(baseline, [])
        self.assertEqual(available, [])


if __name__ == "__main__":
    unittest.main()

"""Pure-helper coverage for sofi_manager.version: formatters, URL
builders, the should-announce decision, and the resolution-order
dispatch in `get_version`. No Tk windows or real git invocations -
subprocess is patched throughout."""

from __future__ import annotations

import subprocess
from unittest.mock import patch

import pytest

from sofi_manager import version


def _cp(returncode: int = 0, stdout: str = "", stderr: str = "") -> subprocess.CompletedProcess:
    return subprocess.CompletedProcess(
        args=["git"], returncode=returncode, stdout=stdout, stderr=stderr
    )


# ---------------------------------------------------------------------------
# Formatters
# ---------------------------------------------------------------------------


def test_format_short_with_count() -> None:
    v = version.VersionInfo(count=143, sha="727b0af", date="2026-05-15", source="git")
    assert version.format_short(v) == "v143 · 727b0af"


def test_format_short_without_count() -> None:
    v = version.VersionInfo(count=None, sha="727b0af", date="", source="zip")
    assert version.format_short(v) == "727b0af"


def test_format_full_with_all_parts() -> None:
    v = version.VersionInfo(count=143, sha="727b0af", date="2026-05-15", source="git")
    assert version.format_full(v) == "v143 · 727b0af · 2026-05-15"


def test_format_full_omits_missing_parts() -> None:
    v = version.VersionInfo(count=None, sha="727b0af", date="", source="zip")
    assert version.format_full(v) == "727b0af"


def test_format_full_omits_count_only() -> None:
    v = version.VersionInfo(count=None, sha="727b0af", date="2026-05-15", source="frozen")
    assert version.format_full(v) == "727b0af · 2026-05-15"


# ---------------------------------------------------------------------------
# URL builders
# ---------------------------------------------------------------------------


def test_commit_url_uses_repo_constant() -> None:
    url = version.commit_url("727b0af")
    assert url == "https://github.com/Soma-Yukihira/sofi-manager/commit/727b0af"


def test_compare_url_uses_three_dot_diff() -> None:
    url = version.compare_url("abc1234", "def5678")
    assert url == "https://github.com/Soma-Yukihira/sofi-manager/compare/abc1234...def5678"


# ---------------------------------------------------------------------------
# should_announce_update — the post-update banner gate
# ---------------------------------------------------------------------------


def test_should_announce_when_sha_changed() -> None:
    assert version.should_announce_update("old1234", "new5678") is True


def test_should_not_announce_on_first_launch() -> None:
    # last_seen is None: silently adopt baseline, no fake "first update".
    assert version.should_announce_update(None, "abc1234") is False


def test_should_not_announce_when_sha_unchanged() -> None:
    assert version.should_announce_update("same1234", "same1234") is False


def test_should_not_announce_when_current_is_empty() -> None:
    # Defensive: if we couldn't identify the current build, don't claim
    # an "update" against the empty string.
    assert version.should_announce_update("old1234", "") is False


# ---------------------------------------------------------------------------
# _from_git — parses subprocess output
# ---------------------------------------------------------------------------


def test_from_git_parses_sha_date_and_count() -> None:
    def fake_git(*args: str) -> subprocess.CompletedProcess:
        if args[0] == "log":
            return _cp(stdout="727b0af|2026-05-15\n")
        if args[0] == "rev-list":
            return _cp(stdout="143\n")
        return _cp(returncode=1)

    with patch.object(version, "_git", side_effect=fake_git):
        v = version._from_git()
    assert v == version.VersionInfo(count=143, sha="727b0af", date="2026-05-15", source="git")


def test_from_git_returns_none_when_log_fails() -> None:
    with patch.object(version, "_git", return_value=_cp(returncode=1)):
        assert version._from_git() is None


def test_from_git_returns_none_on_malformed_output() -> None:
    # No `|` separator.
    with patch.object(version, "_git", return_value=_cp(stdout="not-pipe-separated\n")):
        assert version._from_git() is None


def test_from_git_tolerates_missing_count() -> None:
    # Log succeeds, rev-list fails: VersionInfo still returned with count=None.
    def fake_git(*args: str) -> subprocess.CompletedProcess:
        if args[0] == "log":
            return _cp(stdout="727b0af|2026-05-15\n")
        return _cp(returncode=1)  # rev-list

    with patch.object(version, "_git", side_effect=fake_git):
        v = version._from_git()
    assert v is not None
    assert v.count is None
    assert v.sha == "727b0af"


def test_from_git_handles_git_not_installed() -> None:
    with patch.object(version, "_git", side_effect=FileNotFoundError):
        assert version._from_git() is None


# ---------------------------------------------------------------------------
# _from_zip_sha
# ---------------------------------------------------------------------------


def test_from_zip_sha_truncates_to_seven_chars() -> None:
    v = version._from_zip_sha("abcdef0123456789abcdef0123456789abcdef01")
    assert v is not None
    assert v.sha == "abcdef0"
    assert v.source == "zip"
    assert v.count is None
    assert v.date == ""


def test_from_zip_sha_returns_none_on_empty() -> None:
    assert version._from_zip_sha(None) is None
    assert version._from_zip_sha("") is None


# ---------------------------------------------------------------------------
# get_version — resolution order
# ---------------------------------------------------------------------------


def test_get_version_prefers_git_when_not_frozen() -> None:
    expected = version.VersionInfo(count=143, sha="727b0af", date="2026-05-15", source="git")
    with (
        patch.object(version, "_is_frozen", return_value=False),
        patch.object(version, "_is_git_clone", return_value=True),
        patch.object(version, "_from_git", return_value=expected),
    ):
        assert version.get_version() == expected


def test_get_version_falls_back_to_zip_sha_when_no_git() -> None:
    with (
        patch.object(version, "_is_frozen", return_value=False),
        patch.object(version, "_is_git_clone", return_value=False),
    ):
        v = version.get_version(zip_sha="abc1234def5678")
    assert v.source == "zip"
    assert v.sha == "abc1234"


def test_get_version_returns_unknown_when_nothing_works() -> None:
    with (
        patch.object(version, "_is_frozen", return_value=False),
        patch.object(version, "_is_git_clone", return_value=False),
    ):
        v = version.get_version(zip_sha=None)
    assert v.source == "unknown"
    assert v.sha == "unknown"
    assert v.count is None


def test_get_version_prefers_frozen_when_sys_frozen() -> None:
    expected = version.VersionInfo(count=143, sha="727b0af", date="2026-05-15", source="frozen")
    with (
        patch.object(version, "_is_frozen", return_value=True),
        patch.object(version, "_from_frozen", return_value=expected),
    ):
        # Even with git available, frozen takes priority.
        assert version.get_version() == expected


def test_get_version_falls_through_when_frozen_build_info_missing() -> None:
    # `_is_frozen()` says we're frozen, but `_from_frozen()` returns None
    # (missing `_build_info.py`); we should fall through to git.
    expected_git = version.VersionInfo(count=10, sha="abc1234", date="2026-01-01", source="git")
    with (
        patch.object(version, "_is_frozen", return_value=True),
        patch.object(version, "_from_frozen", return_value=None),
        patch.object(version, "_is_git_clone", return_value=True),
        patch.object(version, "_from_git", return_value=expected_git),
    ):
        assert version.get_version() == expected_git


# ---------------------------------------------------------------------------
# VersionInfo dataclass shape — guard against accidental field renames
# ---------------------------------------------------------------------------


def test_version_info_is_frozen() -> None:
    v = version.VersionInfo(count=1, sha="a", date="b", source="git")
    # dataclass(frozen=True) raises FrozenInstanceError (subclass of
    # AttributeError) on assignment.
    with pytest.raises(AttributeError):
        v.sha = "tampered"  # type: ignore[misc]

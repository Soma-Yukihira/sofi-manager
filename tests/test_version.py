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
# _from_zip
# ---------------------------------------------------------------------------


def test_from_zip_truncates_to_seven_chars() -> None:
    v = version._from_zip("abcdef0123456789abcdef0123456789abcdef01")
    assert v is not None
    assert v.sha == "abcdef0"
    assert v.source == "zip"
    assert v.count is None
    assert v.date == ""


def test_from_zip_returns_none_on_empty() -> None:
    assert version._from_zip(None) is None
    assert version._from_zip("") is None


def test_from_zip_carries_count_and_date_when_provided() -> None:
    v = version._from_zip("abcdef0123", zip_count=58, zip_date="2026-05-15")
    assert v == version.VersionInfo(count=58, sha="abcdef0", date="2026-05-15", source="zip")


def test_from_zip_ignores_non_int_count_and_non_str_date() -> None:
    # Defensive: settings.json could be hand-edited with garbage types.
    v = version._from_zip("abcdef0123", zip_count="58", zip_date=None)  # type: ignore[arg-type]
    assert v is not None
    assert v.count is None
    assert v.date == ""


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


# ---------------------------------------------------------------------------
# Private predicates and `_git` helper.
# ---------------------------------------------------------------------------


def test_is_frozen_default_false() -> None:
    # Source checkouts never set sys.frozen.
    assert version._is_frozen() is False


def test_is_frozen_when_attribute_set(monkeypatch: pytest.MonkeyPatch) -> None:
    import sys

    monkeypatch.setattr(sys, "frozen", True, raising=False)
    assert version._is_frozen() is True


def test_is_git_clone_reflects_dot_git_presence() -> None:
    # In this repo we always have a .git directory at test time; covers the
    # truthy branch. (The False branch is implicitly exercised by frozen-mode
    # tests above that monkey-patch _is_git_clone.)
    assert isinstance(version._is_git_clone(), bool)


def test_git_helper_invokes_subprocess(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, object] = {}

    def fake_run(args, **kwargs):  # type: ignore[no-untyped-def]
        captured["args"] = args
        captured["kwargs"] = kwargs
        return _cp(stdout="ok\n")

    monkeypatch.setattr(version.subprocess, "run", fake_run)
    result = version._git("status")
    assert result.stdout == "ok\n"
    assert captured["args"] == ["git", "status"]
    assert captured["kwargs"]["cwd"] == str(version.ROOT)


# ---------------------------------------------------------------------------
# `_from_git` edge cases that the existing dispatch tests don't reach.
# ---------------------------------------------------------------------------


def test_from_git_returns_none_when_sha_empty() -> None:
    # `git log` succeeded but its stdout split to an empty sha — treat as
    # unknown rather than fabricating a VersionInfo with sha="".
    with patch.object(version, "_git", return_value=_cp(stdout="|2026-05-15\n")):
        assert version._from_git() is None


def test_from_git_count_recovers_from_exception() -> None:
    # First _git call (the log) succeeds, the second (rev-list) raises —
    # the count must fall back to None instead of propagating the error.
    log_cp = _cp(stdout="abc1234|2026-05-15\n")

    call_count = {"n": 0}

    def fake_git(*args: str) -> subprocess.CompletedProcess:
        call_count["n"] += 1
        if call_count["n"] == 1:
            return log_cp
        raise OSError("git binary vanished")

    with patch.object(version, "_git", side_effect=fake_git):
        info = version._from_git()

    assert info is not None
    assert info.sha == "abc1234"
    assert info.count is None


# ---------------------------------------------------------------------------
# `_from_frozen` — exercised by injecting a fake `_build_info` module.
# ---------------------------------------------------------------------------


def test_from_frozen_returns_none_when_build_info_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # No _build_info shipped — import should raise and the helper returns None.
    import sys as _sys

    monkeypatch.setitem(_sys.modules, "sofi_manager._build_info", None)
    assert version._from_frozen() is None


def test_from_frozen_reads_baked_triple(monkeypatch: pytest.MonkeyPatch) -> None:
    import sys as _sys
    import types as _types

    fake = _types.ModuleType("sofi_manager._build_info")
    fake.BUILD_SHA = "deadbee"  # type: ignore[attr-defined]
    fake.BUILD_COUNT = 200  # type: ignore[attr-defined]
    fake.BUILD_DATE = "2026-05-16"  # type: ignore[attr-defined]
    monkeypatch.setitem(_sys.modules, "sofi_manager._build_info", fake)

    info = version._from_frozen()
    assert info is not None
    assert info.sha == "deadbee"
    assert info.count == 200
    assert info.date == "2026-05-16"
    assert info.source == "frozen"


def test_from_frozen_rejects_empty_sha(monkeypatch: pytest.MonkeyPatch) -> None:
    import sys as _sys
    import types as _types

    fake = _types.ModuleType("sofi_manager._build_info")
    fake.BUILD_SHA = ""  # type: ignore[attr-defined]
    monkeypatch.setitem(_sys.modules, "sofi_manager._build_info", fake)
    assert version._from_frozen() is None


def test_from_frozen_rejects_non_string_sha(monkeypatch: pytest.MonkeyPatch) -> None:
    import sys as _sys
    import types as _types

    fake = _types.ModuleType("sofi_manager._build_info")
    fake.BUILD_SHA = 12345  # type: ignore[attr-defined]
    monkeypatch.setitem(_sys.modules, "sofi_manager._build_info", fake)
    assert version._from_frozen() is None


def test_from_frozen_normalises_invalid_date(monkeypatch: pytest.MonkeyPatch) -> None:
    import sys as _sys
    import types as _types

    fake = _types.ModuleType("sofi_manager._build_info")
    fake.BUILD_SHA = "abc"  # type: ignore[attr-defined]
    fake.BUILD_COUNT = "not-an-int"  # type: ignore[attr-defined]
    fake.BUILD_DATE = 42  # not a string  # type: ignore[attr-defined]
    monkeypatch.setitem(_sys.modules, "sofi_manager._build_info", fake)

    info = version._from_frozen()
    assert info is not None
    assert info.sha == "abc"
    assert info.count is None  # bad type → coerced to None
    assert info.date == ""  # bad type → empty string

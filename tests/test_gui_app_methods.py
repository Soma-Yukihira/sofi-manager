"""Display-free coverage for SelfbotManagerApp methods.

Instances are built via `App.__new__(App)` — no Tk, no widgets — and
widget attributes are stubbed with MagicMock so display-free logic
(banner state, settings round-trip, update-check dispatch, status
header routing, etc.) runs end-to-end without a real event loop."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from sofi_manager import gui
from sofi_manager.bot_core import SelfBot

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def app() -> gui.SelfbotManagerApp:
    a = gui.SelfbotManagerApp.__new__(gui.SelfbotManagerApp)
    a.settings = {}
    a.theme = gui.Theme()
    a.version_info = SimpleNamespace(source="git", sha="abc1234", count=143, date="2026-05-16")
    a.bots = {}
    a.selected_id = None
    # `after(delay, fn, *args)` runs synchronously in tests.
    a.after = lambda _delay, fn=None, *args: fn(*args) if fn else None
    # tk.Tk.__getattr__ recurses infinitely on missing attrs because we
    # skipped super().__init__() — pre-populate every attr the code looks
    # up via getattr() so `getattr(self, name, None)` returns None cleanly.
    for attr in (
        "changelog_link",
        "_changelog_tooltip",
        "version_box",
        "version_label",
        "check_updates_btn",
    ):
        setattr(a, attr, None)
    return a


@pytest.fixture
def sync_thread(monkeypatch: pytest.MonkeyPatch) -> None:
    """Replace gui.threading.Thread so .start() runs target synchronously."""

    class _SyncThread:
        def __init__(
            self,
            target=None,
            args=(),
            kwargs=None,
            daemon=None,
            name=None,
        ) -> None:
            self._target = target
            self._args = args
            self._kwargs = kwargs or {}

        def start(self) -> None:
            if self._target is not None:
                self._target(*self._args, **self._kwargs)

    monkeypatch.setattr(gui.threading, "Thread", _SyncThread)


# ---------------------------------------------------------------------------
# _format_top (staticmethod)
# ---------------------------------------------------------------------------


def test_format_top_empty_returns_dash() -> None:
    assert gui.SelfbotManagerApp._format_top([]) == "—"


def test_format_top_renders_lines() -> None:
    out = gui.SelfbotManagerApp._format_top([("Naruto", 12), ("One Piece", 3)])
    assert out == "Naruto · 12\nOne Piece · 3"


def test_format_top_truncates_long_name() -> None:
    name = "X" * 25
    out = gui.SelfbotManagerApp._format_top([(name, 1)])
    assert out.startswith("X" * 18 + "…")
    assert "· 1" in out


def test_format_top_keeps_19_char_name_intact() -> None:
    name = "X" * 19
    out = gui.SelfbotManagerApp._format_top([(name, 1)])
    assert out == f"{name} · 1"


# ---------------------------------------------------------------------------
# _current_bot_filter
# ---------------------------------------------------------------------------


def test_current_bot_filter_all_returns_none(app: gui.SelfbotManagerApp) -> None:
    app._stats_filter_all = "Tous"
    app.stats_bot_filter_var = SimpleNamespace(get=lambda: "Tous")
    assert app._current_bot_filter() is None


def test_current_bot_filter_specific_returns_label(app: gui.SelfbotManagerApp) -> None:
    app._stats_filter_all = "Tous"
    app.stats_bot_filter_var = SimpleNamespace(get=lambda: "alpha")
    assert app._current_bot_filter() == "alpha"


# ---------------------------------------------------------------------------
# _changelog_base_sha
# ---------------------------------------------------------------------------


def test_changelog_base_sha_returns_none_when_absent(app: gui.SelfbotManagerApp) -> None:
    assert app._changelog_base_sha() is None


def test_changelog_base_sha_returns_none_when_empty(app: gui.SelfbotManagerApp) -> None:
    app.settings["last_changelog_base_sha"] = ""
    assert app._changelog_base_sha() is None


def test_changelog_base_sha_returns_none_when_equal_current(
    app: gui.SelfbotManagerApp,
) -> None:
    app.settings["last_changelog_base_sha"] = app.version_info.sha
    assert app._changelog_base_sha() is None


def test_changelog_base_sha_returns_value(app: gui.SelfbotManagerApp) -> None:
    app.settings["last_changelog_base_sha"] = "deadbee"
    assert app._changelog_base_sha() == "deadbee"


def test_changelog_base_sha_returns_none_for_non_string(
    app: gui.SelfbotManagerApp,
) -> None:
    app.settings["last_changelog_base_sha"] = 123
    assert app._changelog_base_sha() is None


# ---------------------------------------------------------------------------
# _refresh_version_label
# ---------------------------------------------------------------------------


def test_refresh_version_label_noop_without_widgets(app: gui.SelfbotManagerApp) -> None:
    # No version_box / version_label set: must early-return without raising.
    app._refresh_version_label()


def test_refresh_version_label_hides_when_source_unknown(
    app: gui.SelfbotManagerApp,
) -> None:
    app.version_info = SimpleNamespace(source="unknown", sha="", count=0, date="")
    app.version_box = MagicMock()
    app.version_label = MagicMock()
    app._refresh_version_label()
    app.version_box.grid_remove.assert_called_once()
    app.version_label.configure.assert_not_called()


def test_refresh_version_label_writes_label_and_shows_box(
    app: gui.SelfbotManagerApp, monkeypatch: pytest.MonkeyPatch
) -> None:
    app.version_box = MagicMock()
    app.version_label = MagicMock()
    monkeypatch.setattr(gui.version, "format_short", lambda v: "v143 · abc1234 · 2026-05-16")
    app._refresh_version_label()
    app.version_label.configure.assert_called_once_with(text="v143 · abc1234 · 2026-05-16")
    app.version_box.grid.assert_called_once()


def test_refresh_version_label_swallows_widget_error(
    app: gui.SelfbotManagerApp, monkeypatch: pytest.MonkeyPatch
) -> None:
    app.version_box = MagicMock()
    app.version_label = MagicMock()
    app.version_label.configure.side_effect = RuntimeError("no tk")
    monkeypatch.setattr(gui.version, "format_short", lambda v: "x")
    # No raise.
    app._refresh_version_label()


# ---------------------------------------------------------------------------
# Update banner
# ---------------------------------------------------------------------------


def test_show_update_banner_plural(app: gui.SelfbotManagerApp) -> None:
    app.update_banner_label = MagicMock()
    app.update_banner = MagicMock()
    app._show_update_banner(3)
    assert app._update_mode == "git"
    assert app._pending_zip_sha is None
    text = app.update_banner_label.configure.call_args.kwargs["text"]
    assert "3 commits" in text
    app.update_banner.grid.assert_called_once()


def test_show_update_banner_singular(app: gui.SelfbotManagerApp) -> None:
    app.update_banner_label = MagicMock()
    app.update_banner = MagicMock()
    app._show_update_banner(1)
    text = app.update_banner_label.configure.call_args.kwargs["text"]
    assert "1 commit " in text


def test_show_update_banner_hides_skip_banner(app: gui.SelfbotManagerApp) -> None:
    app.update_banner_label = MagicMock()
    app.update_banner = MagicMock()
    app.skip_banner = MagicMock()
    app._show_update_banner(2)
    app.skip_banner.grid_remove.assert_called_once()


def test_show_update_banner_swallows_widget_error(app: gui.SelfbotManagerApp) -> None:
    app.update_banner_label = MagicMock()
    app.update_banner = MagicMock()
    app.update_banner_label.configure.side_effect = RuntimeError("no tk")
    # No raise.
    app._show_update_banner(1)


def test_show_zip_update_banner_sets_state(app: gui.SelfbotManagerApp) -> None:
    app.update_banner_label = MagicMock()
    app.update_banner = MagicMock()
    app._show_zip_update_banner("deadbee")
    assert app._update_mode == "zip"
    assert app._pending_zip_sha == "deadbee"
    app.update_banner.grid.assert_called_once()


def test_show_zip_update_banner_hides_skip_banner(app: gui.SelfbotManagerApp) -> None:
    app.update_banner_label = MagicMock()
    app.update_banner = MagicMock()
    app.skip_banner = MagicMock()
    app._show_zip_update_banner("deadbee")
    app.skip_banner.grid_remove.assert_called_once()


def test_dismiss_update_banner_calls_grid_remove(app: gui.SelfbotManagerApp) -> None:
    app.update_banner = MagicMock()
    app._dismiss_update_banner()
    app.update_banner.grid_remove.assert_called_once()


def test_dismiss_update_banner_swallows_exception(app: gui.SelfbotManagerApp) -> None:
    app.update_banner = MagicMock()
    app.update_banner.grid_remove.side_effect = RuntimeError("no tk")
    # No raise.
    app._dismiss_update_banner()


# ---------------------------------------------------------------------------
# ZIP persistence
# ---------------------------------------------------------------------------


def test_persist_zip_info_rejects_missing_or_invalid_sha(
    app: gui.SelfbotManagerApp,
) -> None:
    assert app._persist_zip_info({}) is False
    assert app._persist_zip_info({"sha": ""}) is False
    assert app._persist_zip_info({"sha": 123}) is False


def test_persist_zip_info_first_write_persists(
    app: gui.SelfbotManagerApp, monkeypatch: pytest.MonkeyPatch
) -> None:
    saved: list[dict] = []
    monkeypatch.setattr(gui, "save_settings", lambda s: saved.append(dict(s)))
    monkeypatch.setattr(
        gui.version,
        "get_version",
        lambda zip_sha=None, zip_count=None, zip_date=None: SimpleNamespace(
            source="zip", sha=zip_sha, count=zip_count, date=zip_date
        ),
    )
    app._refresh_version_label = MagicMock()
    info = {"sha": "deadbee", "count": 144, "date": "2026-05-17"}
    assert app._persist_zip_info(info) is True
    assert app.settings["zip_install_sha"] == "deadbee"
    assert app.settings["zip_install_count"] == 144
    assert app.settings["zip_install_date"] == "2026-05-17"
    assert saved
    app._refresh_version_label.assert_called_once()


def test_persist_zip_info_noop_when_unchanged(
    app: gui.SelfbotManagerApp, monkeypatch: pytest.MonkeyPatch
) -> None:
    app.settings.update(
        {
            "zip_install_sha": "deadbee",
            "zip_install_count": 144,
            "zip_install_date": "2026-05-17",
        }
    )
    saved: list = []
    monkeypatch.setattr(gui, "save_settings", lambda s: saved.append(s))
    monkeypatch.setattr(gui.version, "get_version", lambda **k: SimpleNamespace())
    app._refresh_version_label = MagicMock()
    info = {"sha": "deadbee", "count": 144, "date": "2026-05-17"}
    assert app._persist_zip_info(info) is False
    assert saved == []
    app._refresh_version_label.assert_not_called()


def test_persist_zip_info_skips_non_int_count(
    app: gui.SelfbotManagerApp, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(gui, "save_settings", lambda s: None)
    monkeypatch.setattr(gui.version, "get_version", lambda **k: SimpleNamespace())
    app._refresh_version_label = MagicMock()
    info = {"sha": "abc", "count": "nope", "date": "2026-05-17"}
    assert app._persist_zip_info(info) is True
    assert "zip_install_count" not in app.settings
    assert app.settings["zip_install_date"] == "2026-05-17"


def test_persist_zip_info_save_failure_is_swallowed(
    app: gui.SelfbotManagerApp, monkeypatch: pytest.MonkeyPatch
) -> None:
    def _boom(_s: object) -> None:
        raise OSError("disk full")

    monkeypatch.setattr(gui, "save_settings", _boom)
    monkeypatch.setattr(gui.version, "get_version", lambda **k: SimpleNamespace())
    app._refresh_version_label = MagicMock()
    # Should not raise.
    assert app._persist_zip_info({"sha": "abc"}) is True


def test_on_zip_baseline_established_persists(app: gui.SelfbotManagerApp) -> None:
    captured: list = []
    app._persist_zip_info = lambda info: captured.append(info) or True
    app._on_zip_baseline_established({"sha": "abc"})
    assert captured == [{"sha": "abc"}]


def test_on_zip_update_available_shows_banner(app: gui.SelfbotManagerApp) -> None:
    app._show_zip_update_banner = MagicMock()
    app._on_zip_update_available({"sha": "deadbee"})
    app._show_zip_update_banner.assert_called_once_with("deadbee")


def test_on_zip_update_available_skips_when_sha_not_string(
    app: gui.SelfbotManagerApp,
) -> None:
    app._show_zip_update_banner = MagicMock()
    app._on_zip_update_available({"sha": 123})
    app._show_zip_update_banner.assert_not_called()


# ---------------------------------------------------------------------------
# _check_updates_now
# ---------------------------------------------------------------------------


def test_check_updates_now_git_mode_dispatches_status(
    app: gui.SelfbotManagerApp,
    sync_thread: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(gui.updater, "skip_reason", lambda: None)
    monkeypatch.setattr(
        gui.updater, "fetch_and_status", lambda: {"state": "available", "behind": 4}
    )
    app._on_check_updates_result = MagicMock()
    app.check_updates_btn = MagicMock()
    app._check_updates_now()
    app.check_updates_btn.configure.assert_any_call(state="disabled", text="...")
    app._on_check_updates_result.assert_called_once_with({"state": "available", "behind": 4})


def test_check_updates_now_zip_no_drift(
    app: gui.SelfbotManagerApp,
    sync_thread: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(gui.updater, "skip_reason", lambda: "no-git")
    monkeypatch.setattr(
        gui.updater,
        "fetch_remote_main_info",
        lambda: {"sha": "same", "count": 1, "date": "2026"},
    )
    app.settings["zip_install_sha"] = "same"
    app._on_check_updates_result = MagicMock()
    app._check_updates_now()
    result = app._on_check_updates_result.call_args.args[0]
    assert result["state"] == "uptodate"
    assert result["info"]["sha"] == "same"


def test_check_updates_now_zip_baseline_missing_uptodate(
    app: gui.SelfbotManagerApp,
    sync_thread: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # `zip_install_sha` absent → installed_sha is None → uptodate branch.
    monkeypatch.setattr(gui.updater, "skip_reason", lambda: "no-git")
    monkeypatch.setattr(gui.updater, "fetch_remote_main_info", lambda: {"sha": "newish"})
    app._on_check_updates_result = MagicMock()
    app._check_updates_now()
    result = app._on_check_updates_result.call_args.args[0]
    assert result["state"] == "uptodate"


def test_check_updates_now_zip_drift_available(
    app: gui.SelfbotManagerApp,
    sync_thread: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(gui.updater, "skip_reason", lambda: "no-git")
    monkeypatch.setattr(gui.updater, "fetch_remote_main_info", lambda: {"sha": "newsha"})
    app.settings["zip_install_sha"] = "oldsha"
    app._on_check_updates_result = MagicMock()
    app._check_updates_now()
    result = app._on_check_updates_result.call_args.args[0]
    assert result["state"] == "available_zip"


def test_check_updates_now_zip_fetch_failure(
    app: gui.SelfbotManagerApp,
    sync_thread: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(gui.updater, "skip_reason", lambda: "no-git")
    monkeypatch.setattr(gui.updater, "fetch_remote_main_info", lambda: None)
    app._on_check_updates_result = MagicMock()
    app._check_updates_now()
    result = app._on_check_updates_result.call_args.args[0]
    assert result["state"] == "fetch_failed"


def test_check_updates_now_swallows_worker_exception(
    app: gui.SelfbotManagerApp,
    sync_thread: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(gui.updater, "skip_reason", lambda: None)

    def _boom() -> None:
        raise RuntimeError("net down")

    monkeypatch.setattr(gui.updater, "fetch_and_status", _boom)
    app._on_check_updates_result = MagicMock()
    app._check_updates_now()
    result = app._on_check_updates_result.call_args.args[0]
    assert result["state"] == "error"
    assert "net down" in result["err"]


def test_check_updates_now_without_button(
    app: gui.SelfbotManagerApp,
    sync_thread: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # `check_updates_btn` absent: getattr fallback must not raise.
    monkeypatch.setattr(gui.updater, "skip_reason", lambda: None)
    monkeypatch.setattr(gui.updater, "fetch_and_status", lambda: {"state": "uptodate", "behind": 0})
    app._on_check_updates_result = MagicMock()
    app._check_updates_now()
    app._on_check_updates_result.assert_called_once()


# ---------------------------------------------------------------------------
# _on_check_updates_result
# ---------------------------------------------------------------------------


@pytest.fixture
def banner_app(app: gui.SelfbotManagerApp) -> gui.SelfbotManagerApp:
    app.check_updates_btn = MagicMock()
    app._show_update_banner = MagicMock()
    app._show_zip_update_banner = MagicMock()
    return app


def test_on_check_updates_result_available_shows_gold_banner(
    banner_app: gui.SelfbotManagerApp,
) -> None:
    banner_app._on_check_updates_result({"state": "available", "behind": 5})
    banner_app._show_update_banner.assert_called_once_with(5)
    banner_app.check_updates_btn.configure.assert_any_call(state="normal", text="↻  MAJ")


def test_on_check_updates_result_available_zip_drift(
    banner_app: gui.SelfbotManagerApp,
) -> None:
    banner_app.settings["zip_install_sha"] = "old"
    banner_app._on_check_updates_result({"state": "available_zip", "info": {"sha": "new"}})
    banner_app._show_zip_update_banner.assert_called_once_with("new")


def test_on_check_updates_result_available_zip_first_baseline(
    banner_app: gui.SelfbotManagerApp,
) -> None:
    banner_app._persist_zip_info = MagicMock()
    with patch.object(gui.messagebox, "showinfo") as info_box:
        banner_app._on_check_updates_result({"state": "available_zip", "info": {"sha": "new"}})
    banner_app._persist_zip_info.assert_called_once_with({"sha": "new"})
    info_box.assert_called_once()
    banner_app._show_zip_update_banner.assert_not_called()


def test_on_check_updates_result_available_zip_missing_info_warns(
    banner_app: gui.SelfbotManagerApp,
) -> None:
    with patch.object(gui.messagebox, "showwarning") as box:
        banner_app._on_check_updates_result({"state": "available_zip"})
    box.assert_called_once()


def test_on_check_updates_result_uptodate_with_info_backfills(
    banner_app: gui.SelfbotManagerApp,
) -> None:
    banner_app._persist_zip_info = MagicMock()
    info = {"sha": "abc", "count": 10, "date": "2026-05-16"}
    with patch.object(gui.messagebox, "showinfo"):
        banner_app._on_check_updates_result({"state": "uptodate", "info": info})
    banner_app._persist_zip_info.assert_called_once_with(info)


@pytest.mark.parametrize(
    "state,box_attr",
    [
        ("uptodate", "showinfo"),
        ("not_git", "showwarning"),
        ("fetch_failed", "showerror"),
        ("dirty", "showwarning"),
        ("ahead", "showwarning"),
        ("error", "showerror"),
    ],
)
def test_on_check_updates_result_dispatches_messagebox(
    banner_app: gui.SelfbotManagerApp, state: str, box_attr: str
) -> None:
    with patch.object(gui.messagebox, box_attr) as box:
        banner_app._on_check_updates_result({"state": state})
    box.assert_called_once()


def test_on_check_updates_result_error_includes_err_string(
    banner_app: gui.SelfbotManagerApp,
) -> None:
    with patch.object(gui.messagebox, "showerror") as box:
        banner_app._on_check_updates_result({"state": "error", "err": "boom"})
    msg = box.call_args.args[1]
    assert "boom" in msg


def test_on_check_updates_result_without_button(
    app: gui.SelfbotManagerApp,
) -> None:
    # No check_updates_btn attribute: getattr fallback must not raise.
    app._show_update_banner = MagicMock()
    app._on_check_updates_result({"state": "available", "behind": 1})
    app._show_update_banner.assert_called_once_with(1)


# ---------------------------------------------------------------------------
# Skip-reason banner
# ---------------------------------------------------------------------------


def test_maybe_show_skip_reason_banner_swallows_skip_reason_exception(
    app: gui.SelfbotManagerApp, monkeypatch: pytest.MonkeyPatch
) -> None:
    def _raise() -> str:
        raise RuntimeError("git broken")

    monkeypatch.setattr(gui.updater, "skip_reason", _raise)
    # No raise.
    app._maybe_show_skip_reason_banner()


def test_maybe_show_skip_reason_banner_unknown_reason_noop(
    app: gui.SelfbotManagerApp, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(gui.updater, "skip_reason", lambda: "dirty")
    app.update_banner = MagicMock()
    app.skip_banner_label = MagicMock()
    app.skip_banner = MagicMock()
    app._maybe_show_skip_reason_banner()
    app.skip_banner.grid.assert_not_called()


def test_maybe_show_skip_reason_banner_defers_to_gold(
    app: gui.SelfbotManagerApp, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(gui.updater, "skip_reason", lambda: "frozen")
    app.update_banner = MagicMock()
    app.update_banner.winfo_ismapped.return_value = True
    app.skip_banner_label = MagicMock()
    app.skip_banner = MagicMock()
    app._maybe_show_skip_reason_banner()
    app.skip_banner.grid.assert_not_called()


def test_maybe_show_skip_reason_banner_shows_frozen(
    app: gui.SelfbotManagerApp, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(gui.updater, "skip_reason", lambda: "frozen")
    app.update_banner = MagicMock()
    app.update_banner.winfo_ismapped.return_value = False
    app.skip_banner_label = MagicMock()
    app.skip_banner = MagicMock()
    app._maybe_show_skip_reason_banner()
    app.skip_banner.grid.assert_called_once()
    text = app.skip_banner_label.configure.call_args.kwargs["text"]
    assert ".exe" in text


def test_maybe_show_skip_reason_banner_swallows_widget_error(
    app: gui.SelfbotManagerApp, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(gui.updater, "skip_reason", lambda: "frozen")
    app.update_banner = MagicMock()
    app.update_banner.winfo_ismapped.side_effect = RuntimeError("no tk")
    app.skip_banner_label = MagicMock()
    app.skip_banner = MagicMock()
    # No raise.
    app._maybe_show_skip_reason_banner()


def test_dismiss_skip_reason_banner(app: gui.SelfbotManagerApp) -> None:
    app.skip_banner = MagicMock()
    app._dismiss_skip_reason_banner()
    app.skip_banner.grid_remove.assert_called_once()


def test_dismiss_skip_reason_banner_swallows_exception(
    app: gui.SelfbotManagerApp,
) -> None:
    app.skip_banner = MagicMock()
    app.skip_banner.grid_remove.side_effect = RuntimeError("no tk")
    # No raise.
    app._dismiss_skip_reason_banner()


def test_on_skip_reason_help_opens_browser(
    app: gui.SelfbotManagerApp, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[tuple] = []
    monkeypatch.setattr(gui.webbrowser, "open", lambda url, new=0: calls.append((url, new)))
    app._on_skip_reason_help()
    assert calls and calls[0][0] == gui.WIKI_UPDATING_URL
    assert calls[0][1] == 2


def test_on_skip_reason_help_falls_back_to_messagebox(
    app: gui.SelfbotManagerApp, monkeypatch: pytest.MonkeyPatch
) -> None:
    def _boom(url: str, new: int = 0) -> None:
        raise RuntimeError()

    monkeypatch.setattr(gui.webbrowser, "open", _boom)
    with patch.object(gui.messagebox, "showinfo") as info:
        app._on_skip_reason_help()
    info.assert_called_once()


# ---------------------------------------------------------------------------
# DB migration banner
# ---------------------------------------------------------------------------


def test_maybe_migrate_db_returns_storage_result(
    app: gui.SelfbotManagerApp, monkeypatch: pytest.MonkeyPatch
) -> None:
    sentinel = object()
    monkeypatch.setattr(gui.storage, "legacy_db_path", lambda: "L")
    monkeypatch.setattr(gui.storage, "default_db_path", lambda: "D")
    monkeypatch.setattr(gui.storage, "migrate_db", lambda legacy, default: sentinel)
    assert app._maybe_migrate_db() is sentinel


def test_maybe_migrate_db_swallows_exception(
    app: gui.SelfbotManagerApp,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(gui.storage, "legacy_db_path", lambda: "L")
    monkeypatch.setattr(gui.storage, "default_db_path", lambda: "D")

    def _boom(_l: object, _d: object) -> None:
        raise OSError("perm denied")

    monkeypatch.setattr(gui.storage, "migrate_db", _boom)
    assert app._maybe_migrate_db() is None
    err = capsys.readouterr().err
    assert "migrate_db" in err


def test_show_db_migration_banner(app: gui.SelfbotManagerApp) -> None:
    app.db_migration_banner = MagicMock()
    app._show_db_migration_banner()
    app.db_migration_banner.grid.assert_called_once()


def test_show_db_migration_banner_swallows_exception(
    app: gui.SelfbotManagerApp,
) -> None:
    app.db_migration_banner = MagicMock()
    app.db_migration_banner.grid.side_effect = RuntimeError("no tk")
    # No raise.
    app._show_db_migration_banner()


def test_dismiss_db_migration_banner(app: gui.SelfbotManagerApp) -> None:
    app.db_migration_banner = MagicMock()
    app._dismiss_db_migration_banner()
    app.db_migration_banner.grid_remove.assert_called_once()


# ---------------------------------------------------------------------------
# Post-update banner
# ---------------------------------------------------------------------------


def test_show_post_update_banner_skips_when_no_old_sha(
    app: gui.SelfbotManagerApp,
) -> None:
    app._post_update_old_sha = None
    app.post_update_banner_label = MagicMock()
    app.post_update_banner = MagicMock()
    app._show_post_update_banner()
    app.post_update_banner.grid.assert_not_called()


def test_show_post_update_banner_renders_label(
    app: gui.SelfbotManagerApp, monkeypatch: pytest.MonkeyPatch
) -> None:
    app._post_update_old_sha = "old"
    app.post_update_banner_label = MagicMock()
    app.post_update_banner = MagicMock()
    monkeypatch.setattr(gui.version, "format_short", lambda v: "v143 · abc · d")
    app._show_post_update_banner()
    text = app.post_update_banner_label.configure.call_args.kwargs["text"]
    assert "v143 · abc · d" in text
    app.post_update_banner.grid.assert_called_once()


def test_show_post_update_banner_swallows_exception(
    app: gui.SelfbotManagerApp, monkeypatch: pytest.MonkeyPatch
) -> None:
    app._post_update_old_sha = "old"
    app.post_update_banner_label = MagicMock()
    app.post_update_banner = MagicMock()
    app.post_update_banner_label.configure.side_effect = RuntimeError("no tk")
    monkeypatch.setattr(gui.version, "format_short", lambda v: "x")
    # No raise.
    app._show_post_update_banner()


def test_dismiss_post_update_banner(app: gui.SelfbotManagerApp) -> None:
    app.post_update_banner = MagicMock()
    app._dismiss_post_update_banner()
    app.post_update_banner.grid_remove.assert_called_once()


# ---------------------------------------------------------------------------
# _safe_open_url
# ---------------------------------------------------------------------------


def test_safe_open_url_invokes_webbrowser(
    app: gui.SelfbotManagerApp, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[tuple] = []
    monkeypatch.setattr(gui.webbrowser, "open", lambda u, new=0: calls.append((u, new)))
    app._safe_open_url("https://example.test/")
    assert calls == [("https://example.test/", 2)]


def test_safe_open_url_swallows(
    app: gui.SelfbotManagerApp, monkeypatch: pytest.MonkeyPatch
) -> None:
    def _boom(u: str, new: int = 0) -> None:
        raise RuntimeError()

    monkeypatch.setattr(gui.webbrowser, "open", _boom)
    # No raise.
    app._safe_open_url("x")


# ---------------------------------------------------------------------------
# Status header / action buttons / empty state
# ---------------------------------------------------------------------------


def _wire_status_widgets(app: gui.SelfbotManagerApp) -> None:
    app.status_label = MagicMock()
    app.status_dot = MagicMock()
    app.status_dot_id = 42
    app.start_btn = MagicMock()
    app.stop_btn = MagicMock()
    app.delete_btn = MagicMock()
    app.save_btn = MagicMock()


def test_show_empty_state_disables_buttons(app: gui.SelfbotManagerApp) -> None:
    _wire_status_widgets(app)
    app._show_empty_state()
    app.status_label.configure.assert_called_once()
    app.status_dot.itemconfig.assert_called_once_with(42, fill=app.theme["dot_off"])
    for btn in (app.start_btn, app.stop_btn, app.delete_btn, app.save_btn):
        btn.configure.assert_called_once_with(state="disabled")


@pytest.mark.parametrize(
    "status,expected_text",
    [
        ("running", "EN MARCHE"),
        ("starting", "CONNEXION"),
        ("error", "ERREUR"),
        ("stopped", "ARRÊTÉ"),
        ("unknown_status", "—"),
    ],
)
def test_update_status_header_routes_status(
    app: gui.SelfbotManagerApp, status: str, expected_text: str
) -> None:
    _wire_status_widgets(app)
    app._update_status_header(status)
    text = app.status_label.configure.call_args.kwargs["text"]
    assert expected_text in text
    app.status_dot.itemconfig.assert_called_once()


def test_refresh_action_buttons_empty_when_no_selection(
    app: gui.SelfbotManagerApp,
) -> None:
    _wire_status_widgets(app)
    app.selected_id = None
    app._refresh_action_buttons()
    # Falls into _show_empty_state.
    for btn in (app.start_btn, app.stop_btn, app.delete_btn, app.save_btn):
        btn.configure.assert_called_with(state="disabled")


def test_refresh_action_buttons_running_disables_start(
    app: gui.SelfbotManagerApp,
) -> None:
    _wire_status_widgets(app)
    instance = SimpleNamespace(status=SelfBot.STATUS_RUNNING)
    app.bots["bid"] = {"config": {}, "instance": instance}
    app.selected_id = "bid"
    app._refresh_action_buttons()
    app.start_btn.configure.assert_any_call(state="disabled")
    app.stop_btn.configure.assert_any_call(state="normal")


def test_refresh_action_buttons_stopped_enables_start(
    app: gui.SelfbotManagerApp,
) -> None:
    _wire_status_widgets(app)
    app.bots["bid"] = {"config": {}, "instance": None}
    app.selected_id = "bid"
    app._refresh_action_buttons()
    app.start_btn.configure.assert_any_call(state="normal")
    app.stop_btn.configure.assert_any_call(state="disabled")


def test_refresh_action_buttons_starting_disables_start(
    app: gui.SelfbotManagerApp,
) -> None:
    _wire_status_widgets(app)
    instance = SimpleNamespace(status=SelfBot.STATUS_STARTING)
    app.bots["bid"] = {"config": {}, "instance": instance}
    app.selected_id = "bid"
    app._refresh_action_buttons()
    app.start_btn.configure.assert_any_call(state="disabled")
    app.stop_btn.configure.assert_any_call(state="normal")


# ---------------------------------------------------------------------------
# Bot status callback
# ---------------------------------------------------------------------------


def test_on_bot_status_change_unknown_bot_noop(app: gui.SelfbotManagerApp) -> None:
    # No bots: must not raise.
    app._on_bot_status_change("nope", "running")


def test_on_bot_status_change_updates_entry(app: gui.SelfbotManagerApp) -> None:
    entry = MagicMock()
    app.bots["bid"] = {"entry": entry, "config": {}, "instance": None}
    app.selected_id = "other"
    app._on_bot_status_change("bid", "running")
    entry.set_status.assert_called_once_with("running")


def test_on_bot_status_change_refreshes_when_selected(
    app: gui.SelfbotManagerApp,
) -> None:
    entry = MagicMock()
    app.bots["bid"] = {"entry": entry, "config": {}, "instance": None}
    app.selected_id = "bid"
    app._refresh_action_buttons = MagicMock()
    app._on_bot_status_change("bid", "running")
    app._refresh_action_buttons.assert_called_once()


# ---------------------------------------------------------------------------
# Persistence
# ---------------------------------------------------------------------------


def test_persist_writes_bot_configs(
    app: gui.SelfbotManagerApp, monkeypatch: pytest.MonkeyPatch
) -> None:
    captured: list = []
    monkeypatch.setattr(gui, "save_bots", lambda bots: captured.append(bots))
    app.bots = {
        "a": {"config": {"name": "alpha"}, "instance": None},
        "b": {"config": {"name": "beta"}, "instance": None},
    }
    app._persist()
    assert captured == [[{"name": "alpha"}, {"name": "beta"}]]


def test_load_existing_bots_registers_and_sorts_wishlists(
    app: gui.SelfbotManagerApp, monkeypatch: pytest.MonkeyPatch
) -> None:
    loaded = [
        {
            "_id": "a",
            "name": "alpha",
            "wishlist": ["Zelda", "  ", "Aerith", "aerith"],
            "wishlist_series": ["Naruto", "naruto", "Bleach"],
        }
    ]
    monkeypatch.setattr(gui, "load_bots", lambda: loaded)
    app._register_bot = MagicMock()
    app._load_existing_bots()
    app._register_bot.assert_called_once()
    cfg = app._register_bot.call_args.args[0]
    # dedupe_sort: case-insensitive, first-seen casing wins.
    assert cfg["wishlist"] == ["Aerith", "Zelda"]
    assert cfg["wishlist_series"] == ["Bleach", "Naruto"]


# ---------------------------------------------------------------------------
# Stats filter / tab routing
# ---------------------------------------------------------------------------


def test_sync_bot_filter_values_preserves_selection(
    app: gui.SelfbotManagerApp, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(gui.storage, "distinct_bot_labels", lambda: ["alpha", "beta"])
    app._stats_filter_all = "Tous"
    app.stats_bot_filter = MagicMock()
    var = MagicMock()
    var.get.return_value = "alpha"  # already in new values
    app.stats_bot_filter_var = var
    app._sync_bot_filter_values()
    app.stats_bot_filter.configure.assert_called_once_with(values=["Tous", "alpha", "beta"])
    var.set.assert_not_called()


def test_sync_bot_filter_values_resets_when_stale(
    app: gui.SelfbotManagerApp, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(gui.storage, "distinct_bot_labels", lambda: ["alpha"])
    app._stats_filter_all = "Tous"
    app.stats_bot_filter = MagicMock()
    var = MagicMock()
    var.get.return_value = "deleted-bot"
    app.stats_bot_filter_var = var
    app._sync_bot_filter_values()
    var.set.assert_called_once_with("Tous")


def test_sync_bot_filter_values_swallows_db_error(
    app: gui.SelfbotManagerApp, monkeypatch: pytest.MonkeyPatch
) -> None:
    def _boom() -> list:
        raise RuntimeError("db down")

    monkeypatch.setattr(gui.storage, "distinct_bot_labels", _boom)
    app._stats_filter_all = "Tous"
    app.stats_bot_filter = MagicMock()
    var = MagicMock()
    var.get.return_value = "Tous"
    app.stats_bot_filter_var = var
    app._sync_bot_filter_values()
    app.stats_bot_filter.configure.assert_called_once_with(values=["Tous"])


def test_on_tab_changed_stats_triggers_refresh(app: gui.SelfbotManagerApp) -> None:
    app.tabs = MagicMock()
    app.tabs.get.return_value = "  Stats  "
    app._stats_refresh_after_id = None
    app._refresh_stats = MagicMock()
    app._schedule_stats_refresh = MagicMock()
    app._on_tab_changed()
    app._refresh_stats.assert_called_once()
    app._schedule_stats_refresh.assert_called_once()


def test_on_tab_changed_other_tab_cancels_pending(app: gui.SelfbotManagerApp) -> None:
    app.tabs = MagicMock()
    app.tabs.get.return_value = "Logs"
    app._stats_refresh_after_id = "after_id_42"
    app.after_cancel = MagicMock()
    app._on_tab_changed()
    app.after_cancel.assert_called_once_with("after_id_42")
    assert app._stats_refresh_after_id is None


def test_on_tab_changed_swallows_after_cancel_error(app: gui.SelfbotManagerApp) -> None:
    app.tabs = MagicMock()
    app.tabs.get.return_value = "Logs"
    app._stats_refresh_after_id = "id"
    app.after_cancel = MagicMock(side_effect=RuntimeError("no tk"))
    # No raise.
    app._on_tab_changed()
    assert app._stats_refresh_after_id is None


def test_schedule_stats_refresh_cancels_prior(app: gui.SelfbotManagerApp) -> None:
    app._stats_refresh_after_id = "old"
    app.after_cancel = MagicMock()
    app.after = MagicMock(return_value="new")
    app._schedule_stats_refresh()
    app.after_cancel.assert_called_once_with("old")
    assert app._stats_refresh_after_id == "new"


def test_schedule_stats_refresh_when_idle(app: gui.SelfbotManagerApp) -> None:
    app._stats_refresh_after_id = None
    app.after = MagicMock(return_value="id")
    app._schedule_stats_refresh()
    assert app._stats_refresh_after_id == "id"


def test_tick_stats_refresh_reschedules_when_on_stats(
    app: gui.SelfbotManagerApp,
) -> None:
    app._stats_refresh_after_id = "old"
    app.tabs = MagicMock()
    app.tabs.get.return_value = "Stats"
    app._refresh_stats = MagicMock()
    app._schedule_stats_refresh = MagicMock()
    app._tick_stats_refresh()
    app._refresh_stats.assert_called_once()
    app._schedule_stats_refresh.assert_called_once()


def test_tick_stats_refresh_idle_when_not_on_stats(
    app: gui.SelfbotManagerApp,
) -> None:
    app._stats_refresh_after_id = "old"
    app.tabs = MagicMock()
    app.tabs.get.return_value = "Logs"
    app._refresh_stats = MagicMock()
    app._schedule_stats_refresh = MagicMock()
    app._tick_stats_refresh()
    app._refresh_stats.assert_not_called()
    app._schedule_stats_refresh.assert_not_called()


# ---------------------------------------------------------------------------
# _refresh_stats
# ---------------------------------------------------------------------------


def _wire_stats_widgets(app: gui.SelfbotManagerApp) -> None:
    app._stats_filter_all = "Tous"
    app.stats_bot_filter = MagicMock()
    app.stats_bot_filter_var = MagicMock()
    app.stats_bot_filter_var.get.return_value = "Tous"
    app.stats_kpi_widgets = {
        "total": MagicMock(),
        "success_rate": MagicMock(),
        "top_series": MagicMock(),
        "top_rarities": MagicMock(),
    }
    app._redraw_stats_chart = MagicMock()


def test_refresh_stats_db_error(
    app: gui.SelfbotManagerApp, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(gui.storage, "distinct_bot_labels", list)

    def _boom(**_kw: object) -> list:
        raise RuntimeError("db gone")

    monkeypatch.setattr(gui.storage, "iter_grabs", _boom)
    _wire_stats_widgets(app)
    app._refresh_stats()
    assert app._stats_last is None
    app.stats_kpi_widgets["total"].configure.assert_called_with(text="—")
    # success_rate gets the exception class name in its text.
    rate_text = app.stats_kpi_widgets["success_rate"].configure.call_args.kwargs["text"]
    assert "RuntimeError" in rate_text
    app._redraw_stats_chart.assert_called_once()


def test_refresh_stats_empty_records(
    app: gui.SelfbotManagerApp, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(gui.storage, "distinct_bot_labels", list)
    monkeypatch.setattr(gui.storage, "iter_grabs", lambda **kw: iter([]))
    _wire_stats_widgets(app)
    app._refresh_stats()
    app.stats_kpi_widgets["total"].configure.assert_called_with(text="0")
    series_text = app.stats_kpi_widgets["top_series"].configure.call_args.kwargs["text"]
    assert "aucun grab" in series_text


def test_refresh_stats_with_data(
    app: gui.SelfbotManagerApp, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(gui.storage, "distinct_bot_labels", list)
    monkeypatch.setattr(gui.storage, "iter_grabs", lambda **kw: iter(["x"]))
    fake_stats = SimpleNamespace(
        total=10,
        success_rate=0.7,
        top_series=[("Naruto", 3)],
        top_rarities=[("SR", 2)],
        daily_counts=[(0, 0)],
    )
    monkeypatch.setattr(gui.storage, "compute_stats", lambda _records: fake_stats)
    _wire_stats_widgets(app)
    app._refresh_stats()
    assert app._stats_last is fake_stats
    app.stats_kpi_widgets["total"].configure.assert_called_with(text="10")
    app.stats_kpi_widgets["success_rate"].configure.assert_called_with(text="70%")


# ---------------------------------------------------------------------------
# Logs
# ---------------------------------------------------------------------------


def test_clear_current_logs_noop_without_selection(
    app: gui.SelfbotManagerApp,
) -> None:
    app.selected_id = None
    # Must not raise even though `self.bots` is empty.
    app._clear_current_logs()


def test_clear_current_logs_clears_buffer_and_widget(
    app: gui.SelfbotManagerApp,
) -> None:
    widget = MagicMock()
    app.bots["bid"] = {
        "log_buffer": [("info", "x"), ("info", "y")],
        "log_widget": widget,
    }
    app.selected_id = "bid"
    app._clear_current_logs()
    assert app.bots["bid"]["log_buffer"] == []
    widget.delete.assert_called_once_with("1.0", "end")
    # configure called twice: enable then disable
    assert widget.configure.call_count == 2


def test_clear_current_logs_without_widget(app: gui.SelfbotManagerApp) -> None:
    app.bots["bid"] = {"log_buffer": [("info", "x")], "log_widget": None}
    app.selected_id = "bid"
    app._clear_current_logs()
    assert app.bots["bid"]["log_buffer"] == []


def test_append_log_line_unknown_bot_noop(app: gui.SelfbotManagerApp) -> None:
    app._append_log_line("nope", "info", "hello")  # must not raise


def test_append_log_line_writes_to_widget(app: gui.SelfbotManagerApp) -> None:
    widget = MagicMock()
    app.bots["bid"] = {"log_buffer": [], "log_widget": widget}
    app._append_log_line("bid", "info", "line1")
    assert app.bots["bid"]["log_buffer"] == [("info", "line1")]
    widget.insert.assert_called_once_with("end", "line1\n", "info")
    widget.see.assert_called_once_with("end")


def test_append_log_line_trims_buffer_over_2000(app: gui.SelfbotManagerApp) -> None:
    widget = MagicMock()
    # 2000 already-buffered entries → append triggers the trim branch.
    buf = [("info", f"l{i}") for i in range(2000)]
    app.bots["bid"] = {"log_buffer": buf, "log_widget": widget}
    app._append_log_line("bid", "info", "final")
    # Trimmed to last 1500 of the pre-existing 2000, plus the new line
    # appended above before the trim, so the kept tail starts after the
    # cut and reflects the slice taken by the code.
    assert len(app.bots["bid"]["log_buffer"]) == 1500
    # Widget rewritten from scratch.
    widget.delete.assert_called_once_with("1.0", "end")


def test_append_log_line_without_widget(app: gui.SelfbotManagerApp) -> None:
    app.bots["bid"] = {"log_buffer": [], "log_widget": None}
    app._append_log_line("bid", "info", "x")
    assert app.bots["bid"]["log_buffer"] == [("info", "x")]


def test_drain_logs_pulls_from_queue(app: gui.SelfbotManagerApp) -> None:
    import queue as _q

    q = _q.Queue()
    q.put(("info", "line-a"))
    q.put(("error", "line-b"))
    instance = SimpleNamespace(log_queue=q)
    app.bots["bid"] = {"instance": instance, "log_buffer": [], "log_widget": None}
    # Block recursive re-schedule by replacing `after` with a MagicMock.
    app.after = MagicMock()
    app._drain_logs()
    assert app.bots["bid"]["log_buffer"] == [
        ("info", "line-a"),
        ("error", "line-b"),
    ]
    # Always reschedules itself.
    app.after.assert_called_once()
    delay = app.after.call_args.args[0]
    assert delay == 120


def test_drain_logs_skips_bots_without_instance(app: gui.SelfbotManagerApp) -> None:
    app.bots["bid"] = {"instance": None, "log_buffer": [], "log_widget": None}
    app.after = MagicMock()
    app._drain_logs()
    app.after.assert_called_once()


# ---------------------------------------------------------------------------
# _export_stats_csv
# ---------------------------------------------------------------------------


@pytest.fixture
def stats_app(app: gui.SelfbotManagerApp) -> gui.SelfbotManagerApp:
    """`app` plus the bits `_export_stats_csv` needs: a filter accessor + a
    stand-in for the modal parent (`self`)."""
    app._stats_filter_all = "Tous"
    app.stats_bot_filter_var = SimpleNamespace(get=lambda: "Tous")
    return app


def test_export_stats_csv_cancel_returns_early(
    stats_app: gui.SelfbotManagerApp, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(gui.filedialog, "asksaveasfilename", lambda **_: "")
    iter_grabs = MagicMock()
    monkeypatch.setattr(gui.storage, "iter_grabs", iter_grabs)
    stats_app._export_stats_csv()
    iter_grabs.assert_not_called()


def test_export_stats_csv_writes_file_and_reports_success(
    stats_app: gui.SelfbotManagerApp, tmp_path: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    out = tmp_path / "grabs.csv"
    monkeypatch.setattr(gui.filedialog, "asksaveasfilename", lambda **_: str(out))
    monkeypatch.setattr(gui.storage, "iter_grabs", lambda bot_label=None: iter([1, 2, 3]))
    monkeypatch.setattr(gui.storage, "export_csv", lambda records, f: sum(1 for _ in records))
    info = MagicMock()
    monkeypatch.setattr(gui.messagebox, "showinfo", info)
    stats_app._export_stats_csv()
    assert out.exists()
    # Success messagebox includes record count + scope hint.
    args = info.call_args.args
    assert "3 grabs" in args[1]
    assert "tous bots" in args[1]


def test_export_stats_csv_specific_bot_scope_passed_to_iter(
    stats_app: gui.SelfbotManagerApp, tmp_path: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    stats_app.stats_bot_filter_var = SimpleNamespace(get=lambda: "alpha")
    monkeypatch.setattr(gui.filedialog, "asksaveasfilename", lambda **_: str(tmp_path / "out.csv"))
    seen_scope: dict[str, Any] = {}

    def _iter(bot_label: Any = None) -> Any:
        seen_scope["scope"] = bot_label
        return iter([])

    monkeypatch.setattr(gui.storage, "iter_grabs", _iter)
    monkeypatch.setattr(gui.storage, "export_csv", lambda records, f: 0)
    monkeypatch.setattr(gui.messagebox, "showinfo", MagicMock())
    stats_app._export_stats_csv()
    assert seen_scope["scope"] == "alpha"


def test_export_stats_csv_db_read_failure_shows_error(
    stats_app: gui.SelfbotManagerApp, tmp_path: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(gui.filedialog, "asksaveasfilename", lambda **_: str(tmp_path / "x.csv"))

    def _boom(bot_label: Any = None) -> Any:
        raise RuntimeError("db down")

    monkeypatch.setattr(gui.storage, "iter_grabs", _boom)
    err = MagicMock()
    monkeypatch.setattr(gui.messagebox, "showerror", err)
    stats_app._export_stats_csv()
    err.assert_called_once()
    assert "RuntimeError" in err.call_args.args[1]


def test_export_stats_csv_oserror_during_write_shows_error(
    stats_app: gui.SelfbotManagerApp, tmp_path: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(gui.filedialog, "asksaveasfilename", lambda **_: str(tmp_path / "y.csv"))
    monkeypatch.setattr(gui.storage, "iter_grabs", lambda bot_label=None: iter([]))

    def _open_fails(*_a: Any, **_kw: Any) -> Any:
        raise OSError("disk full")

    monkeypatch.setattr("builtins.open", _open_fails)
    err = MagicMock()
    monkeypatch.setattr(gui.messagebox, "showerror", err)
    info = MagicMock()
    monkeypatch.setattr(gui.messagebox, "showinfo", info)
    stats_app._export_stats_csv()
    err.assert_called_once()
    info.assert_not_called()


# ---------------------------------------------------------------------------
# _register_bot
# ---------------------------------------------------------------------------


def _stub_bot_list_entry(monkeypatch: pytest.MonkeyPatch) -> MagicMock:
    """Replace BotListEntry with a MagicMock factory so _register_bot can run
    without instantiating Tk widgets."""
    factory = MagicMock(name="BotListEntry_factory")

    def _make(*a: Any, **kw: Any) -> Any:
        inst = MagicMock(name="BotListEntry_instance")
        factory(*a, **kw)
        return inst

    monkeypatch.setattr(gui, "BotListEntry", _make)
    return factory


def test_register_bot_assigns_uuid_when_absent(
    app: gui.SelfbotManagerApp, monkeypatch: pytest.MonkeyPatch
) -> None:
    _stub_bot_list_entry(monkeypatch)
    app.bot_list = MagicMock()
    cfg: dict[str, Any] = {"name": "alpha"}
    bot_id = app._register_bot(cfg)
    assert bot_id == cfg["_id"]
    assert bot_id  # non-empty
    assert app.bots[bot_id]["config"] is cfg


def test_register_bot_reuses_existing_id(
    app: gui.SelfbotManagerApp, monkeypatch: pytest.MonkeyPatch
) -> None:
    _stub_bot_list_entry(monkeypatch)
    app.bot_list = MagicMock()
    cfg = {"_id": "fixed-id", "name": "beta"}
    bot_id = app._register_bot(cfg)
    assert bot_id == "fixed-id"
    assert "fixed-id" in app.bots


def test_register_bot_default_buffer_when_none(
    app: gui.SelfbotManagerApp, monkeypatch: pytest.MonkeyPatch
) -> None:
    _stub_bot_list_entry(monkeypatch)
    app.bot_list = MagicMock()
    bot_id = app._register_bot({"name": "x"})
    assert app.bots[bot_id]["log_buffer"] == []


def test_register_bot_keeps_provided_buffer(
    app: gui.SelfbotManagerApp, monkeypatch: pytest.MonkeyPatch
) -> None:
    _stub_bot_list_entry(monkeypatch)
    app.bot_list = MagicMock()
    buf: list[tuple[str, str]] = [("info", "hi")]
    bot_id = app._register_bot({"name": "x"}, log_buffer=buf)
    # Same object, not a copy.
    assert app.bots[bot_id]["log_buffer"] is buf


def test_register_bot_wires_status_callback_when_instance_supplied(
    app: gui.SelfbotManagerApp, monkeypatch: pytest.MonkeyPatch
) -> None:
    _stub_bot_list_entry(monkeypatch)
    app.bot_list = MagicMock()
    instance = SimpleNamespace(status="running", status_callback=None)
    captured: list[tuple[str, str]] = []
    app._on_bot_status_change = lambda bid, s: captured.append((bid, s))
    bot_id = app._register_bot({"name": "y"}, instance=instance)
    assert app.bots[bot_id]["instance"] is instance
    # Firing the wired callback round-trips through `self.after(0, ...)` →
    # the `app` fixture runs `after` synchronously.
    instance.status_callback("error")
    assert captured == [(bot_id, "error")]


def test_register_bot_skips_status_callback_when_no_instance(
    app: gui.SelfbotManagerApp, monkeypatch: pytest.MonkeyPatch
) -> None:
    _stub_bot_list_entry(monkeypatch)
    app.bot_list = MagicMock()
    bot_id = app._register_bot({"name": "z"})
    # No instance recorded → no callback path to break.
    assert app.bots[bot_id]["instance"] is None


# ---------------------------------------------------------------------------
# _on_close
# ---------------------------------------------------------------------------


def test_on_close_persists_and_stops_all(
    app: gui.SelfbotManagerApp, monkeypatch: pytest.MonkeyPatch
) -> None:
    app._collect_form_into_config = MagicMock()
    app._persist = MagicMock()
    save_settings_mock = MagicMock()
    monkeypatch.setattr(gui, "save_settings", save_settings_mock)
    app._stats_refresh_after_id = None
    app.protocol = MagicMock()
    app._stop_all_async = MagicMock()
    app.destroy = MagicMock()
    app.selected_id = None

    app._on_close()

    app._collect_form_into_config.assert_not_called()  # no selection
    app._persist.assert_called_once()
    save_settings_mock.assert_called_once_with(app.settings)
    app._stop_all_async.assert_called_once_with(then=app.destroy)


def test_on_close_collects_selected_form(
    app: gui.SelfbotManagerApp, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(gui, "save_settings", MagicMock())
    app._collect_form_into_config = MagicMock()
    app._persist = MagicMock()
    app._stats_refresh_after_id = None
    app.protocol = MagicMock()
    app._stop_all_async = MagicMock()
    app.destroy = MagicMock()
    app.selected_id = "bid"

    app._on_close()
    app._collect_form_into_config.assert_called_once_with("bid")


def test_on_close_swallows_collect_error(
    app: gui.SelfbotManagerApp, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(gui, "save_settings", MagicMock())
    app._collect_form_into_config = MagicMock(side_effect=RuntimeError("boom"))
    app._persist = MagicMock()
    app._stats_refresh_after_id = None
    app.protocol = MagicMock()
    app._stop_all_async = MagicMock()
    app.destroy = MagicMock()
    app.selected_id = "bid"

    app._on_close()  # must not raise
    # Persist still runs even if form collection failed.
    app._persist.assert_called_once()


def test_on_close_cancels_pending_stats_refresh(
    app: gui.SelfbotManagerApp, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(gui, "save_settings", MagicMock())
    app._collect_form_into_config = MagicMock()
    app._persist = MagicMock()
    app._stats_refresh_after_id = "after#42"
    app.after_cancel = MagicMock()
    app.protocol = MagicMock()
    app._stop_all_async = MagicMock()
    app.destroy = MagicMock()
    app.selected_id = None

    app._on_close()
    app.after_cancel.assert_called_once_with("after#42")
    assert app._stats_refresh_after_id is None


def test_on_close_swallows_after_cancel_error(
    app: gui.SelfbotManagerApp, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(gui, "save_settings", MagicMock())
    app._collect_form_into_config = MagicMock()
    app._persist = MagicMock()
    app._stats_refresh_after_id = "after#42"
    app.after_cancel = MagicMock(side_effect=RuntimeError("no such id"))
    app.protocol = MagicMock()
    app._stop_all_async = MagicMock()
    app.destroy = MagicMock()
    app.selected_id = None

    app._on_close()
    # Cleared regardless.
    assert app._stats_refresh_after_id is None


def test_on_close_rebinds_protocol_to_noop(
    app: gui.SelfbotManagerApp, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(gui, "save_settings", MagicMock())
    app._collect_form_into_config = MagicMock()
    app._persist = MagicMock()
    app._stats_refresh_after_id = None
    proto_calls: list[tuple[str, Any]] = []
    app.protocol = lambda event, fn: proto_calls.append((event, fn))
    app._stop_all_async = MagicMock()
    app.destroy = MagicMock()
    app.selected_id = None

    app._on_close()
    assert proto_calls and proto_calls[-1][0] == "WM_DELETE_WINDOW"
    # Calling the no-op shouldn't raise.
    proto_calls[-1][1]()


def test_on_close_swallows_protocol_error(
    app: gui.SelfbotManagerApp, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(gui, "save_settings", MagicMock())
    app._collect_form_into_config = MagicMock()
    app._persist = MagicMock()
    app._stats_refresh_after_id = None
    app.protocol = MagicMock(side_effect=RuntimeError("late"))
    app._stop_all_async = MagicMock()
    app.destroy = MagicMock()
    app.selected_id = None

    app._on_close()  # must not raise
    app._stop_all_async.assert_called_once()


# ---------------------------------------------------------------------------
# _wire_changelog_link
# ---------------------------------------------------------------------------


def test_wire_changelog_link_noop_when_link_missing(
    app: gui.SelfbotManagerApp,
) -> None:
    app.changelog_link = None
    app._wire_changelog_link()  # must not raise


def test_wire_changelog_link_inactive_when_no_base_sha(
    app: gui.SelfbotManagerApp,
) -> None:
    app.changelog_link = MagicMock()
    # No `last_changelog_base_sha` in settings → inactive branch.
    app._wire_changelog_link()
    # Should NOT bind a click handler.
    bind_calls = app.changelog_link.bind.call_args_list
    sequences = [c.args[0] for c in bind_calls]
    assert "<Button-1>" not in sequences
    # Cursor cleared, hover wired to tooltip show/hide.
    assert "<Enter>" in sequences
    assert "<Leave>" in sequences


def test_wire_changelog_link_active_when_base_sha_present(
    app: gui.SelfbotManagerApp,
) -> None:
    app.changelog_link = MagicMock()
    app.settings["last_changelog_base_sha"] = "old1234"
    app._wire_changelog_link()
    sequences = [c.args[0] for c in app.changelog_link.bind.call_args_list]
    # Active branch: cursor=hand2 + Button-1 wired.
    assert "<Button-1>" in sequences
    # Cursor was set to hand2 at least once.
    cursor_calls = [
        c.kwargs.get("cursor")
        for c in app.changelog_link.configure.call_args_list
        if "cursor" in c.kwargs
    ]
    assert "hand2" in cursor_calls


def test_wire_changelog_link_swallows_unbind_error(
    app: gui.SelfbotManagerApp,
) -> None:
    link = MagicMock()
    link.unbind.side_effect = RuntimeError("never bound")
    app.changelog_link = link
    app._wire_changelog_link()  # no raise; bindings still applied


def test_wire_changelog_link_swallows_cursor_error_active(
    app: gui.SelfbotManagerApp,
) -> None:
    link = MagicMock()
    link.configure.side_effect = [None, RuntimeError("late"), None]
    app.changelog_link = link
    app.settings["last_changelog_base_sha"] = "old"
    app._wire_changelog_link()  # no raise


def test_wire_changelog_link_swallows_cursor_error_inactive(
    app: gui.SelfbotManagerApp,
) -> None:
    link = MagicMock()
    link.configure.side_effect = [None, RuntimeError("late")]
    app.changelog_link = link
    app._wire_changelog_link()  # no raise


# ---------------------------------------------------------------------------
# _show_changelog_tooltip / _hide_changelog_tooltip
# ---------------------------------------------------------------------------


def test_show_changelog_tooltip_noop_when_already_visible(
    app: gui.SelfbotManagerApp,
) -> None:
    sentinel = object()
    app._changelog_tooltip = sentinel
    app.changelog_link = MagicMock()
    app._show_changelog_tooltip()
    assert app._changelog_tooltip is sentinel


def test_show_changelog_tooltip_noop_when_link_missing(
    app: gui.SelfbotManagerApp,
) -> None:
    app._changelog_tooltip = None
    app.changelog_link = None
    app._show_changelog_tooltip()
    assert app._changelog_tooltip is None


def test_show_changelog_tooltip_creates_toplevel(
    app: gui.SelfbotManagerApp, monkeypatch: pytest.MonkeyPatch
) -> None:
    app._changelog_tooltip = None
    link = MagicMock()
    link.winfo_rootx.return_value = 100
    link.winfo_rooty.return_value = 200
    link.winfo_width.return_value = 80
    app.changelog_link = link

    tip_mock = MagicMock(name="tip")
    monkeypatch.setattr(gui.tk, "Toplevel", lambda *a, **kw: tip_mock)
    monkeypatch.setattr(gui.tk, "Label", lambda *a, **kw: MagicMock())

    app._show_changelog_tooltip()
    assert app._changelog_tooltip is tip_mock
    tip_mock.wm_overrideredirect.assert_called_once_with(True)
    tip_mock.wm_geometry.assert_called_once()


def test_show_changelog_tooltip_swallows_toplevel_error(
    app: gui.SelfbotManagerApp, monkeypatch: pytest.MonkeyPatch
) -> None:
    app._changelog_tooltip = None
    app.changelog_link = MagicMock()
    monkeypatch.setattr(gui.tk, "Toplevel", MagicMock(side_effect=RuntimeError("no root")))
    app._show_changelog_tooltip()
    assert app._changelog_tooltip is None


def test_hide_changelog_tooltip_noop_when_absent(
    app: gui.SelfbotManagerApp,
) -> None:
    app._changelog_tooltip = None
    app._hide_changelog_tooltip()  # no raise


def test_hide_changelog_tooltip_destroys_and_clears(
    app: gui.SelfbotManagerApp,
) -> None:
    tip = MagicMock()
    app._changelog_tooltip = tip
    app._hide_changelog_tooltip()
    tip.destroy.assert_called_once()
    assert app._changelog_tooltip is None


def test_hide_changelog_tooltip_swallows_destroy_error(
    app: gui.SelfbotManagerApp,
) -> None:
    tip = MagicMock()
    tip.destroy.side_effect = RuntimeError("gone")
    app._changelog_tooltip = tip
    app._hide_changelog_tooltip()
    assert app._changelog_tooltip is None


# ---------------------------------------------------------------------------
# _add_bot
# ---------------------------------------------------------------------------


def test_add_bot_registers_and_selects(
    app: gui.SelfbotManagerApp, monkeypatch: pytest.MonkeyPatch
) -> None:
    _stub_bot_list_entry(monkeypatch)
    app.bot_list = MagicMock()
    app._select_bot = MagicMock()
    app._persist = MagicMock()
    app._add_bot()
    assert app.bots  # at least one bot registered
    bot_id = next(iter(app.bots))
    app._select_bot.assert_called_once_with(bot_id)
    app._persist.assert_called_once()


# ---------------------------------------------------------------------------
# _stop_bot_async / _stop_all_async
# ---------------------------------------------------------------------------


def test_stop_bot_async_invokes_stop_and_done(
    app: gui.SelfbotManagerApp, sync_thread: None
) -> None:
    instance = MagicMock()
    done = MagicMock()
    app._stop_bot_async(instance, on_done=done)
    instance.stop.assert_called_once()
    done.assert_called_once()


def test_stop_bot_async_swallows_stop_error(app: gui.SelfbotManagerApp, sync_thread: None) -> None:
    instance = MagicMock()
    instance.stop.side_effect = RuntimeError("nope")
    done = MagicMock()
    app._stop_bot_async(instance, on_done=done)
    done.assert_called_once()  # still fired


def test_stop_bot_async_no_callback(app: gui.SelfbotManagerApp, sync_thread: None) -> None:
    instance = MagicMock()
    app._stop_bot_async(instance, on_done=None)
    instance.stop.assert_called_once()


def test_stop_bot_async_swallows_after_error(
    app: gui.SelfbotManagerApp,
    sync_thread: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    instance = MagicMock()
    done = MagicMock()
    # `after` raises when scheduling on_done → must be swallowed.
    app.after = MagicMock(side_effect=RuntimeError("destroyed"))
    app._stop_bot_async(instance, on_done=done)
    instance.stop.assert_called_once()


def test_stop_all_async_empty_calls_then_directly(
    app: gui.SelfbotManagerApp,
) -> None:
    app.bots = {}
    done = MagicMock()
    after_mock = MagicMock()
    app.after = after_mock
    app._stop_all_async(then=done)
    # Empty → fires `after(0, done)` exactly once.
    after_mock.assert_called_once_with(0, done)


def test_stop_all_async_empty_no_callback_returns(
    app: gui.SelfbotManagerApp,
) -> None:
    app.bots = {}
    app.after = MagicMock()
    app._stop_all_async(then=None)
    app.after.assert_not_called()


def test_stop_all_async_fires_then_after_all_stops(
    app: gui.SelfbotManagerApp, sync_thread: None
) -> None:
    inst_a = MagicMock()
    inst_b = MagicMock()
    app.bots = {
        "a": {"instance": inst_a},
        "b": {"instance": inst_b},
    }
    done = MagicMock()
    # `after` runs scheduled callables synchronously already.
    app._stop_all_async(then=done)
    inst_a.stop.assert_called_once()
    inst_b.stop.assert_called_once()
    done.assert_called_once()


def test_stop_all_async_only_fires_then_once(app: gui.SelfbotManagerApp, sync_thread: None) -> None:
    inst = MagicMock()
    app.bots = {"a": {"instance": inst}}
    fire_count = {"n": 0}

    def _then() -> None:
        fire_count["n"] += 1

    app._stop_all_async(then=_then)
    # _fire is scheduled both by the worker (lock-protected) and by the
    # max_wait safety ceiling — but the `fired` flag guarantees one call.
    assert fire_count["n"] == 1


def test_stop_all_async_swallows_stop_error(app: gui.SelfbotManagerApp, sync_thread: None) -> None:
    inst = MagicMock()
    inst.stop.side_effect = RuntimeError("nope")
    app.bots = {"a": {"instance": inst}}
    done = MagicMock()
    app._stop_all_async(then=done)
    done.assert_called_once()


# ---------------------------------------------------------------------------
# _stop_current
# ---------------------------------------------------------------------------


def test_stop_current_no_selection(app: gui.SelfbotManagerApp) -> None:
    app.selected_id = None
    app._stop_bot_async = MagicMock()
    app._stop_current()
    app._stop_bot_async.assert_not_called()


def test_stop_current_no_instance(app: gui.SelfbotManagerApp) -> None:
    app.selected_id = "bid"
    app.bots = {"bid": {"instance": None}}
    app._stop_bot_async = MagicMock()
    app._stop_current()
    app._stop_bot_async.assert_not_called()


def test_stop_current_dispatches_async_stop(app: gui.SelfbotManagerApp, sync_thread: None) -> None:
    inst = MagicMock()
    app.selected_id = "bid"
    app.bots = {"bid": {"instance": inst}}
    app.stop_btn = MagicMock()
    app._refresh_action_buttons = MagicMock()
    app._stop_current()
    # stop button is disabled while shutdown runs, then restored.
    states = [c.kwargs.get("state") for c in app.stop_btn.configure.call_args_list]
    assert "disabled" in states
    # `on_done` was invoked synchronously by sync_thread, which calls
    # `_refresh_action_buttons` when the bot is still selected.
    app._refresh_action_buttons.assert_called_once()


def test_stop_current_skips_refresh_when_selection_changed(
    app: gui.SelfbotManagerApp, sync_thread: None
) -> None:
    inst = MagicMock()
    app.selected_id = "bid"
    app.bots = {"bid": {"instance": inst}}
    app.stop_btn = MagicMock()
    app._refresh_action_buttons = MagicMock()

    real_after = app.after

    def _after_then_switch(delay: Any, fn: Any = None, *args: Any) -> Any:
        # Simulate the user switching bots mid-stop: the on_done callback
        # captures the original bid and now sees a mismatched selection.
        app.selected_id = "other"
        if fn is not None:
            return fn(*args)
        return None

    app.after = _after_then_switch
    app._stop_current()
    app._refresh_action_buttons.assert_not_called()
    # Restore for fixture cleanliness.
    app.after = real_after


# ---------------------------------------------------------------------------
# Small exception-swallow paths
# ---------------------------------------------------------------------------


def test_check_updates_now_swallows_btn_configure_error(
    app: gui.SelfbotManagerApp,
    sync_thread: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # btn.configure raises when toggling to "disabled" — must be swallowed
    # so the worker still dispatches.
    monkeypatch.setattr(gui.updater, "skip_reason", lambda: None)
    monkeypatch.setattr(gui.updater, "fetch_and_status", lambda: {"state": "uptodate", "behind": 0})
    btn = MagicMock()
    btn.configure.side_effect = RuntimeError("destroyed")
    app.check_updates_btn = btn
    app._on_check_updates_result = MagicMock()
    app._check_updates_now()
    app._on_check_updates_result.assert_called_once()


def test_on_check_updates_result_swallows_btn_configure_error(
    app: gui.SelfbotManagerApp,
) -> None:
    btn = MagicMock()
    btn.configure.side_effect = RuntimeError("destroyed")
    app.check_updates_btn = btn
    # Dispatched path: state uptodate with no info -> messagebox branch.
    with patch.object(gui.messagebox, "showinfo"):
        app._on_check_updates_result({"state": "uptodate", "behind": 0})


def test_dismiss_db_migration_banner_swallows_exception(
    app: gui.SelfbotManagerApp,
) -> None:
    app.db_migration_banner = MagicMock()
    app.db_migration_banner.grid_remove.side_effect = RuntimeError("gone")
    # No raise.
    app._dismiss_db_migration_banner()


def test_dismiss_post_update_banner_swallows_exception(
    app: gui.SelfbotManagerApp,
) -> None:
    app.post_update_banner = MagicMock()
    app.post_update_banner.grid_remove.side_effect = RuntimeError("gone")
    # No raise.
    app._dismiss_post_update_banner()


# ---------------------------------------------------------------------------
# _stop_all_async _fire swallows after() error
# ---------------------------------------------------------------------------


def test_stop_all_async_fire_swallows_after_error(
    app: gui.SelfbotManagerApp, sync_thread: None
) -> None:
    inst = MagicMock()
    app.bots = {"a": {"instance": inst}}
    done = MagicMock()

    # Only the inner `after(0, then)` inside `_fire` must raise; the outer
    # max_wait scheduling call still succeeds (otherwise the exception
    # escapes before `_fire` is even entered).
    def _after(delay: Any, fn: Any = None, *args: Any) -> Any:
        if delay == 0 and fn is done:
            raise RuntimeError("destroyed")
        # Outer ceiling call: run synchronously so `_fire` is exercised.
        if fn is not None:
            return fn(*args)
        return None

    app.after = _after
    # No raise.
    app._stop_all_async(then=done)
    inst.stop.assert_called_once()


# ---------------------------------------------------------------------------
# _on_stats_chart_click
# ---------------------------------------------------------------------------


def test_on_stats_chart_click_hits_bucket(app: gui.SelfbotManagerApp) -> None:
    app._stats_bar_hits = [
        (0.0, 10.0, 1_700_000_000),
        (10.0, 20.0, 1_700_086_400),
        (20.0, 30.0, 1_700_172_800),
    ]
    app._open_grabs_for_day = MagicMock()
    event = SimpleNamespace(x=15.0)
    app._on_stats_chart_click(event)
    app._open_grabs_for_day.assert_called_once_with(1_700_086_400)


def test_on_stats_chart_click_miss_returns_silently(
    app: gui.SelfbotManagerApp,
) -> None:
    app._stats_bar_hits = [(0.0, 10.0, 1_700_000_000)]
    app._open_grabs_for_day = MagicMock()
    event = SimpleNamespace(x=99.0)
    app._on_stats_chart_click(event)
    app._open_grabs_for_day.assert_not_called()


def test_on_stats_chart_click_empty_hits(app: gui.SelfbotManagerApp) -> None:
    app._stats_bar_hits = []
    app._open_grabs_for_day = MagicMock()
    event = SimpleNamespace(x=5.0)
    app._on_stats_chart_click(event)
    app._open_grabs_for_day.assert_not_called()


# ---------------------------------------------------------------------------
# _start_current
# ---------------------------------------------------------------------------


def test_start_current_noop_when_no_selection(
    app: gui.SelfbotManagerApp, monkeypatch: pytest.MonkeyPatch
) -> None:
    app.selected_id = None
    app._collect_form_into_config = MagicMock()
    app._persist = MagicMock()
    app._start_current()
    app._collect_form_into_config.assert_not_called()
    app._persist.assert_not_called()


def test_start_current_skips_when_already_running(
    app: gui.SelfbotManagerApp, monkeypatch: pytest.MonkeyPatch
) -> None:
    existing = SimpleNamespace(status=SelfBot.STATUS_RUNNING)
    app.selected_id = "bid"
    app.bots = {"bid": {"config": {"name": "alpha"}, "instance": existing}}
    app._collect_form_into_config = MagicMock()
    app._persist = MagicMock()
    # Don't patch gui.SelfBot — patching it would replace STATUS_RUNNING with
    # an auto-generated MagicMock attr that wouldn't match `existing.status`.
    # Instead, assert that `instance.start` was never called (proxy for the
    # skip branch).
    app._refresh_action_buttons = MagicMock()
    app.tabs = MagicMock()
    app._start_current()
    # Form collected + persisted (always), but no new SelfBot instantiation.
    app._collect_form_into_config.assert_called_once_with("bid")
    app._persist.assert_called_once()
    # The instance is still the same SimpleNamespace; no replacement made.
    assert app.bots["bid"]["instance"] is existing


def test_start_current_skips_when_already_starting(
    app: gui.SelfbotManagerApp, monkeypatch: pytest.MonkeyPatch
) -> None:
    existing = SimpleNamespace(status=SelfBot.STATUS_STARTING)
    app.selected_id = "bid"
    app.bots = {"bid": {"config": {"name": "alpha"}, "instance": existing}}
    app._collect_form_into_config = MagicMock()
    app._persist = MagicMock()
    app._refresh_action_buttons = MagicMock()
    app.tabs = MagicMock()
    app._start_current()
    assert app.bots["bid"]["instance"] is existing


def test_start_current_launches_new_instance(
    app: gui.SelfbotManagerApp, monkeypatch: pytest.MonkeyPatch
) -> None:
    cfg = {"name": "alpha"}
    app.selected_id = "bid"
    app.bots = {"bid": {"config": cfg, "instance": None}}
    app._collect_form_into_config = MagicMock()
    app._persist = MagicMock()
    app._refresh_action_buttons = MagicMock()
    app.tabs = MagicMock()
    app._on_bot_status_change = MagicMock()

    created = MagicMock(name="instance")
    factory = MagicMock(return_value=created)
    monkeypatch.setattr(gui, "SelfBot", factory)

    app._start_current()

    factory.assert_called_once_with(cfg)
    # status_callback wired and invokes _on_bot_status_change via after(0, ...).
    created.start.assert_called_once()
    assert app.bots["bid"]["instance"] is created
    app._refresh_action_buttons.assert_called_once()
    app.tabs.set.assert_called_once_with("  Logs  ")
    # The status_callback closes over bid + dispatches through after(0).
    created.status_callback("running")
    app._on_bot_status_change.assert_called_once_with("bid", "running")


def test_start_current_replaces_dead_instance(
    app: gui.SelfbotManagerApp, monkeypatch: pytest.MonkeyPatch
) -> None:
    # If the existing instance is in a stopped/error status, a fresh one is
    # constructed and replaces it.
    old = SimpleNamespace(status="stopped")
    app.selected_id = "bid"
    app.bots = {"bid": {"config": {"name": "alpha"}, "instance": old}}
    app._collect_form_into_config = MagicMock()
    app._persist = MagicMock()
    app._refresh_action_buttons = MagicMock()
    app.tabs = MagicMock()

    created = MagicMock(name="instance")
    factory = MagicMock(return_value=created)
    monkeypatch.setattr(gui, "SelfBot", factory)

    app._start_current()

    factory.assert_called_once()
    assert app.bots["bid"]["instance"] is created
    created.start.assert_called_once()


# ---------------------------------------------------------------------------
# Form-builder helpers: _add_field / _add_field_grid / _add_textarea
# ---------------------------------------------------------------------------


def _stub_frame(monkeypatch: pytest.MonkeyPatch) -> MagicMock:
    """Replace gui.ctk.CTkFrame so widget builders don't touch real Tk."""
    factory = MagicMock(name="CTkFrame_factory")
    monkeypatch.setattr(gui.ctk, "CTkFrame", factory)
    return factory


def test_add_field_registers_entry_in_cfg_widgets(
    app: gui.SelfbotManagerApp, monkeypatch: pytest.MonkeyPatch
) -> None:
    _stub_frame(monkeypatch)
    label = MagicMock()
    entry = MagicMock()
    app._mk_label = MagicMock(return_value=label)
    app._mk_entry = MagicMock(return_value=entry)
    app.cfg_widgets = {}

    parent = MagicMock()
    app._add_field(parent, "token", "Token", placeholder="ph", show="*", numeric=True)

    app._mk_label.assert_called_once()
    # `_mk_entry` is invoked with the same show/placeholder pass-through.
    kwargs = app._mk_entry.call_args.kwargs
    assert kwargs.get("show") == "*"
    assert kwargs.get("placeholder") == "ph"
    # entry is recorded under the given key, marked numeric.
    assert app.cfg_widgets["token"] is entry
    assert entry._numeric is True


def test_add_field_default_non_numeric(
    app: gui.SelfbotManagerApp, monkeypatch: pytest.MonkeyPatch
) -> None:
    _stub_frame(monkeypatch)
    app._mk_label = MagicMock()
    entry = MagicMock()
    app._mk_entry = MagicMock(return_value=entry)
    app.cfg_widgets = {}
    app._add_field(MagicMock(), "name", "Nom")
    assert app.cfg_widgets["name"] is entry
    assert entry._numeric is False


def test_add_field_grid_registers_entry(
    app: gui.SelfbotManagerApp, monkeypatch: pytest.MonkeyPatch
) -> None:
    _stub_frame(monkeypatch)
    app._mk_label = MagicMock()
    entry = MagicMock()
    app._mk_entry = MagicMock(return_value=entry)
    app.cfg_widgets = {}
    app._add_field_grid(MagicMock(), 0, "rarity_norm", "Norm", numeric=True)
    assert app.cfg_widgets["rarity_norm"] is entry
    assert entry._numeric is True


def test_add_field_grid_second_column_padding(
    app: gui.SelfbotManagerApp, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Second column (col=1) uses `padx=(8, 0)` — exercises the conditional.
    frame_factory = _stub_frame(monkeypatch)
    app._mk_label = MagicMock()
    app._mk_entry = MagicMock(return_value=MagicMock())
    app.cfg_widgets = {}
    app._add_field_grid(MagicMock(), 1, "k", "L")
    # The inner wrap.grid() call gets the (8, 0) padx tuple.
    wrap = frame_factory.return_value
    grid_kwargs = wrap.grid.call_args.kwargs
    assert grid_kwargs["padx"] == (8, 0)


def test_add_textarea_registers_textbox(
    app: gui.SelfbotManagerApp, monkeypatch: pytest.MonkeyPatch
) -> None:
    _stub_frame(monkeypatch)
    app._mk_label = MagicMock()
    tb = MagicMock()
    app._mk_textbox = MagicMock(return_value=tb)
    app.cfg_widgets = {}
    app._add_textarea(MagicMock(), "notes", "Notes", height=200)
    app._mk_textbox.assert_called_once()
    assert app._mk_textbox.call_args.kwargs.get("height") == 200
    assert app.cfg_widgets["notes"] is tb


# ---------------------------------------------------------------------------
# _make_log_widget — Tk Text + CTkScrollbar wiring
# ---------------------------------------------------------------------------


def test_make_log_widget_builds_text_and_scrollbar(
    app: gui.SelfbotManagerApp, monkeypatch: pytest.MonkeyPatch
) -> None:
    text_widget = MagicMock(name="tk.Text")
    text_factory = MagicMock(return_value=text_widget)
    scrollbar = MagicMock(name="CTkScrollbar")
    scrollbar_factory = MagicMock(return_value=scrollbar)
    monkeypatch.setattr(gui.tk, "Text", text_factory)
    monkeypatch.setattr(gui.ctk, "CTkScrollbar", scrollbar_factory)
    app.logs_holder = MagicMock()

    tb, sb = app._make_log_widget()

    assert tb is text_widget
    assert sb is scrollbar
    text_factory.assert_called_once()
    scrollbar_factory.assert_called_once()
    # Every LEVEL_KEYS entry yielded a tag_configure call.
    expected_levels = set(gui.LEVEL_KEYS.keys()) | {"system"}
    actual_levels = {c.args[0] for c in text_widget.tag_configure.call_args_list}
    assert expected_levels <= actual_levels
    # `system` tag is bolded.
    system_calls = [c for c in text_widget.tag_configure.call_args_list if c.args[0] == "system"]
    assert system_calls
    # `state="disabled"` is the final configure call so the widget is read-only
    # by default — the caller flips it back to "normal" while writing.
    text_widget.configure.assert_any_call(yscrollcommand=scrollbar.set, state="disabled")


def test_make_log_widget_scrollbar_yview_wired(
    app: gui.SelfbotManagerApp, monkeypatch: pytest.MonkeyPatch
) -> None:
    text_widget = MagicMock()
    monkeypatch.setattr(gui.tk, "Text", lambda *a, **kw: text_widget)
    scrollbar_factory = MagicMock(return_value=MagicMock())
    monkeypatch.setattr(gui.ctk, "CTkScrollbar", scrollbar_factory)
    app.logs_holder = MagicMock()

    app._make_log_widget()

    # Scrollbar `command` argument is the text widget's `yview` method.
    sb_kwargs = scrollbar_factory.call_args.kwargs
    assert sb_kwargs.get("command") is text_widget.yview


# ---------------------------------------------------------------------------
# _render_changelog_body — markdown-style block rendering
# ---------------------------------------------------------------------------


def _stub_widgets(
    monkeypatch: pytest.MonkeyPatch,
) -> tuple[MagicMock, MagicMock, MagicMock, list[MagicMock], list[MagicMock]]:
    """Replace ctk.CTkLabel/CTkFrame/CTkFont with factories that yield a
    fresh MagicMock per call (so per-widget interactions stay independent).
    Returns (label_factory, frame_factory, font_factory, label_instances,
    frame_instances) — instance lists are populated in call order."""
    label_instances: list[MagicMock] = []
    frame_instances: list[MagicMock] = []

    def _label(*_a: Any, **_kw: Any) -> MagicMock:
        m = MagicMock()
        label_instances.append(m)
        return m

    def _frame(*_a: Any, **_kw: Any) -> MagicMock:
        m = MagicMock()
        frame_instances.append(m)
        return m

    label_factory = MagicMock(name="CTkLabel", side_effect=_label)
    frame_factory = MagicMock(name="CTkFrame", side_effect=_frame)
    font_factory = MagicMock(name="CTkFont", side_effect=lambda *a, **kw: MagicMock())
    monkeypatch.setattr(gui.ctk, "CTkLabel", label_factory)
    monkeypatch.setattr(gui.ctk, "CTkFrame", frame_factory)
    monkeypatch.setattr(gui.ctk, "CTkFont", font_factory)
    return label_factory, frame_factory, font_factory, label_instances, frame_instances


def test_render_changelog_body_empty_renders_fallback(
    app: gui.SelfbotManagerApp, monkeypatch: pytest.MonkeyPatch
) -> None:
    label_factory, _frame_factory, _font_factory, _labels, _frames = _stub_widgets(monkeypatch)
    # `render_body` returns an empty tuple → fallback dim label.
    monkeypatch.setattr(gui.changelog, "render_body", lambda _b: ())
    app._render_changelog_body(MagicMock(), "raw fallback body")
    label_factory.assert_called_once()
    kwargs = label_factory.call_args.kwargs
    assert kwargs.get("text") == "raw fallback body"


def test_render_changelog_body_renders_all_block_kinds(
    app: gui.SelfbotManagerApp, monkeypatch: pytest.MonkeyPatch
) -> None:
    label_factory, frame_factory, _font_factory, _labels, _frames = _stub_widgets(monkeypatch)
    Block = gui.changelog.Block  # frozen dataclass
    blocks = (
        Block(kind="blank", text="", level=0),
        Block(kind="heading", text="Top-level", level=1),
        Block(kind="heading", text="Sub-heading", level=3),  # size 12 branch
        Block(kind="bullet", text="point-A", level=0),
        Block(kind="bullet", text="nested", level=2),
        Block(kind="paragraph", text="prose body", level=0),
    )
    monkeypatch.setattr(gui.changelog, "render_body", lambda _b: blocks)

    app._render_changelog_body(MagicMock(), "body-text")

    # Frames built: one for the blank spacer + one for each bullet row.
    assert frame_factory.call_count == 1 + 2  # 1 blank + 2 bullets
    # Labels built: 2 headings + (bullet glyph + bullet text) * 2 + 1 paragraph
    assert label_factory.call_count == 2 + 4 + 1
    # Heading text values present.
    texts = [c.kwargs.get("text") for c in label_factory.call_args_list]
    assert "Top-level" in texts
    assert "Sub-heading" in texts
    assert "point-A" in texts
    assert "nested" in texts
    assert "prose body" in texts


# ---------------------------------------------------------------------------
# _render_changelog_entry — caret/title row + optional collapsible body
# ---------------------------------------------------------------------------


def test_render_changelog_entry_no_body_skips_toggle(
    app: gui.SelfbotManagerApp, monkeypatch: pytest.MonkeyPatch
) -> None:
    label_factory, frame_factory, _font_factory, _labels, _frames = _stub_widgets(monkeypatch)
    entry = gui.changelog.ChangelogEntry(
        sha="abc1234",
        title="Short title",
        body="",
        html_url="https://example.test/c/abc1234",
    )
    app._render_changelog_entry(MagicMock(), entry)
    # Two frames (outer row + header), no body frame because body is empty.
    assert frame_factory.call_count == 2
    # Caret text uses the inert dim glyph when no body — first label built.
    caret_kwargs = label_factory.call_args_list[0].kwargs
    assert caret_kwargs.get("text") == "  "


def test_render_changelog_entry_with_body_toggle_open_and_close(
    app: gui.SelfbotManagerApp, monkeypatch: pytest.MonkeyPatch
) -> None:
    _label_factory, _frame_factory, _font_factory, labels, frames = _stub_widgets(monkeypatch)
    # `_render_changelog_body` is exercised separately — stub it out so the
    # toggle handler is what we test here.
    app._render_changelog_body = MagicMock()
    entry = gui.changelog.ChangelogEntry(
        sha="abc1234",
        title="With body",
        body="some body text",
        html_url="https://example.test/c/abc1234",
    )

    app._render_changelog_entry(MagicMock(), entry)

    # `caret` is the first CTkLabel built inside _render_changelog_entry.
    caret = labels[0]
    bind_call = [c for c in caret.bind.call_args_list if c.args[0] == "<Button-1>"]
    assert bind_call, "caret <Button-1> binding missing"
    toggle = bind_call[0].args[1]

    # First click: opens — body frame created and _render_changelog_body
    # invoked once. The body frame is the 3rd frame built (row, header, body).
    toggle()
    app._render_changelog_body.assert_called_once()
    body_frame = frames[2]
    body_frame.pack.assert_called()
    # Second click: closes — pack_forget on the body frame.
    toggle()
    body_frame.pack_forget.assert_called()
    # Third click: re-opens — frame already exists, no second body render.
    toggle()
    assert app._render_changelog_body.call_count == 1


def test_render_changelog_entry_title_click_opens_url(
    app: gui.SelfbotManagerApp, monkeypatch: pytest.MonkeyPatch
) -> None:
    _label_factory, _frame_factory, _font_factory, labels, _frames = _stub_widgets(monkeypatch)
    entry = gui.changelog.ChangelogEntry(
        sha="abc1234",
        title="T",
        body="",
        html_url="https://example.test/c/abc1234",
    )
    app._safe_open_url = MagicMock()

    app._render_changelog_entry(MagicMock(), entry)

    # The title label is the second CTkLabel built (caret, title, sha_label).
    title = labels[1]
    bind_calls = [c for c in title.bind.call_args_list if c.args[0] == "<Button-1>"]
    assert bind_calls
    # Trigger the handler.
    bind_calls[0].args[1](None)
    app._safe_open_url.assert_called_once_with("https://example.test/c/abc1234")


def test_render_changelog_entry_swallows_cursor_config_errors(
    app: gui.SelfbotManagerApp, monkeypatch: pytest.MonkeyPatch
) -> None:
    label_instances: list[MagicMock] = []

    def _label(*_a: Any, **_kw: Any) -> MagicMock:
        m = MagicMock()
        # Every label's `configure(cursor=...)` call raises so both
        # exception-swallow branches (title + caret) are exercised.
        m.configure.side_effect = RuntimeError("no cursor")
        label_instances.append(m)
        return m

    monkeypatch.setattr(gui.ctk, "CTkLabel", MagicMock(side_effect=_label))
    monkeypatch.setattr(gui.ctk, "CTkFrame", MagicMock(side_effect=lambda *a, **kw: MagicMock()))
    monkeypatch.setattr(gui.ctk, "CTkFont", MagicMock(side_effect=lambda *a, **kw: MagicMock()))

    entry = gui.changelog.ChangelogEntry(
        sha="abc1234",
        title="T",
        body="body",
        html_url="https://example.test/",
    )
    # No raise.
    app._render_changelog_entry(MagicMock(), entry)

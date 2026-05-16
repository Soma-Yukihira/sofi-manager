"""Display-free coverage for SelfbotManagerApp methods.

Instances are built via `App.__new__(App)` — no Tk, no widgets — and
widget attributes are stubbed with MagicMock so display-free logic
(banner state, settings round-trip, update-check dispatch, status
header routing, etc.) runs end-to-end without a real event loop."""

from __future__ import annotations

from types import SimpleNamespace
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

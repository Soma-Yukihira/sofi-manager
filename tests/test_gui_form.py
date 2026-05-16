"""Display-free coverage for SelfbotManagerApp form/selection methods.

Covers the bot-selection + form-round-trip surface:
`_populate_form`, `_collect_form_into_config`, `_save_current`,
`_select_bot`, `_switch_log_widget`, `_delete_current`, `_toggle_theme`.

Instances are built via `App.__new__(App)` — no Tk, no widgets — and
CTk widgets are replaced with trivial subclasses that bypass
`super().__init__()` so `isinstance(w, ctk.CTkSwitch)` /
`ctk.CTkTextbox` checks in `gui.py` still match."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import customtkinter as ctk
import pytest

from sofi_manager import gui

# ---------------------------------------------------------------------------
# Stub widgets — real subclasses so isinstance() matches, __init__ skipped.
# ---------------------------------------------------------------------------


class _StubSwitch(ctk.CTkSwitch):
    def __init__(self, value: bool = False) -> None:
        self._value = bool(value)

    def get(self) -> int:
        return 1 if self._value else 0

    def select(self) -> None:
        self._value = True

    def deselect(self) -> None:
        self._value = False


class _StubTextbox(ctk.CTkTextbox):
    def __init__(self, text: str = "") -> None:
        self._text = text

    def delete(self, _start: str, _end: str | None = None) -> None:
        self._text = ""

    def insert(self, _pos: str, text: str) -> None:
        self._text = (self._text or "") + text

    def get(self, _start: str = "1.0", _end: str = "end") -> str:
        return self._text


class _StubEntry(ctk.CTkEntry):
    def __init__(self, text: str = "", numeric: bool = False) -> None:
        self._text = text
        self._numeric = numeric

    def delete(self, _start: int, _end: str | None = None) -> None:
        self._text = ""

    def insert(self, _pos: int, text: str) -> None:
        self._text = (self._text or "") + str(text)

    def get(self) -> str:
        return self._text


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _make_widgets() -> dict[str, object]:
    """Build a representative cfg_widgets dict covering every isinstance arm:
    - one switch (`night_pause_enabled`)
    - one textbox for channel list (`all_channels`)
    - one textbox for free text (`token`)
    - one numeric entry mapped via the `drop_channel` int branch
    - one numeric entry mapped via the `cooldown_extra_min` int(float()) branch
    - one numeric entry mapped via the `pause_duration_min` h↔s branch
    - one numeric entry on the default float branch (`interval_min`)
    - one non-numeric entry (`name`)
    """
    return {
        "night_pause_enabled": _StubSwitch(),
        "all_channels": _StubTextbox(),
        "token": _StubTextbox(),
        "drop_channel": _StubEntry(numeric=True),
        "cooldown_extra_min": _StubEntry(numeric=True),
        "pause_duration_min": _StubEntry(numeric=True),
        "interval_min": _StubEntry(numeric=True),
        "name": _StubEntry(numeric=False),
    }


@pytest.fixture
def app() -> gui.SelfbotManagerApp:
    a = gui.SelfbotManagerApp.__new__(gui.SelfbotManagerApp)
    a.settings = {}
    a.theme = gui.Theme()
    a.version_info = SimpleNamespace(source="git", sha="abc1234", count=143, date="2026-05-16")
    a.bots = {}
    a.selected_id = None
    a.after = lambda _delay, fn=None, *args: fn(*args) if fn else None
    a.cfg_widgets = _make_widgets()
    a.wishlist_persos = _StubTextbox()
    a.wishlist_series = _StubTextbox()
    for attr in (
        "changelog_link",
        "_changelog_tooltip",
        "version_box",
        "version_label",
        "check_updates_btn",
    ):
        setattr(a, attr, None)
    return a


# ---------------------------------------------------------------------------
# _populate_form
# ---------------------------------------------------------------------------


def test_populate_form_switch_on_and_off(app: gui.SelfbotManagerApp) -> None:
    app._populate_form({"night_pause_enabled": True})
    assert app.cfg_widgets["night_pause_enabled"].get() == 1
    app._populate_form({"night_pause_enabled": False})
    assert app.cfg_widgets["night_pause_enabled"].get() == 0


def test_populate_form_all_channels_joins_with_newlines(app: gui.SelfbotManagerApp) -> None:
    app._populate_form({"all_channels": [123, 456, 789]})
    assert app.cfg_widgets["all_channels"].get() == "123\n456\n789"


def test_populate_form_all_channels_handles_none(app: gui.SelfbotManagerApp) -> None:
    app._populate_form({"all_channels": None})
    assert app.cfg_widgets["all_channels"].get() == ""


def test_populate_form_textbox_freeform(app: gui.SelfbotManagerApp) -> None:
    app._populate_form({"token": "secret-abc"})
    assert app.cfg_widgets["token"].get() == "secret-abc"


def test_populate_form_textbox_none_clears(app: gui.SelfbotManagerApp) -> None:
    app.cfg_widgets["token"]._text = "leftover"
    app._populate_form({"token": None})
    assert app.cfg_widgets["token"].get() == ""


def test_populate_form_entry_string(app: gui.SelfbotManagerApp) -> None:
    app._populate_form({"name": "alpha"})
    assert app.cfg_widgets["name"].get() == "alpha"


def test_populate_form_entry_skips_empty(app: gui.SelfbotManagerApp) -> None:
    app.cfg_widgets["name"]._text = "stale"
    app._populate_form({"name": ""})
    # delete clears; empty value skips re-insert.
    assert app.cfg_widgets["name"].get() == ""


def test_populate_form_pause_duration_converts_seconds_to_hours(
    app: gui.SelfbotManagerApp,
) -> None:
    # 3600s → 1.0h
    app._populate_form({"pause_duration_min": 3600})
    assert app.cfg_widgets["pause_duration_min"].get() == "1.0"


def test_populate_form_pause_duration_zero_skips_insert(
    app: gui.SelfbotManagerApp,
) -> None:
    app._populate_form({"pause_duration_min": 0})
    assert app.cfg_widgets["pause_duration_min"].get() == ""


def test_populate_form_renders_wishlists(app: gui.SelfbotManagerApp) -> None:
    app._populate_form({"wishlist": ["Aerith", "Zelda"], "wishlist_series": ["Bleach"]})
    assert app.wishlist_persos.get() == "Aerith\nZelda"
    assert app.wishlist_series.get() == "Bleach"


def test_populate_form_missing_key_uses_empty_default(app: gui.SelfbotManagerApp) -> None:
    # Empty cfg: every widget is reset, no crash on `cfg.get(key, "")`.
    app._populate_form({})
    assert app.cfg_widgets["night_pause_enabled"].get() == 0
    assert app.cfg_widgets["all_channels"].get() == ""
    assert app.cfg_widgets["name"].get() == ""


# ---------------------------------------------------------------------------
# _collect_form_into_config
# ---------------------------------------------------------------------------


@pytest.fixture
def app_with_bot(app: gui.SelfbotManagerApp) -> gui.SelfbotManagerApp:
    entry = MagicMock()
    app.bots["bid"] = {
        "config": {"name": "init"},
        "entry": entry,
        "instance": None,
        "log_widget": None,
        "log_scroll": None,
        "log_buffer": [],
    }
    return app


def test_collect_form_switch_writes_bool(app_with_bot: gui.SelfbotManagerApp) -> None:
    app_with_bot.cfg_widgets["night_pause_enabled"].select()
    app_with_bot._collect_form_into_config("bid")
    assert app_with_bot.bots["bid"]["config"]["night_pause_enabled"] is True


def test_collect_form_all_channels_parses_ints(app_with_bot: gui.SelfbotManagerApp) -> None:
    app_with_bot.cfg_widgets["all_channels"]._text = "10\n  20  \n\nnotanint\n30"
    app_with_bot._collect_form_into_config("bid")
    assert app_with_bot.bots["bid"]["config"]["all_channels"] == [10, 20, 30]


def test_collect_form_textbox_freeform_strips(app_with_bot: gui.SelfbotManagerApp) -> None:
    app_with_bot.cfg_widgets["token"]._text = "  hello  \n"
    app_with_bot._collect_form_into_config("bid")
    assert app_with_bot.bots["bid"]["config"]["token"] == "hello"


def test_collect_form_drop_channel_int(app_with_bot: gui.SelfbotManagerApp) -> None:
    app_with_bot.cfg_widgets["drop_channel"]._text = "12345"
    app_with_bot._collect_form_into_config("bid")
    assert app_with_bot.bots["bid"]["config"]["drop_channel"] == 12345


def test_collect_form_drop_channel_empty_zero(app_with_bot: gui.SelfbotManagerApp) -> None:
    app_with_bot.cfg_widgets["drop_channel"]._text = ""
    app_with_bot._collect_form_into_config("bid")
    assert app_with_bot.bots["bid"]["config"]["drop_channel"] == 0


def test_collect_form_cooldown_extra_int_of_float(
    app_with_bot: gui.SelfbotManagerApp,
) -> None:
    # `int(float(raw))` branch — accepts "5.7" and truncates to 5.
    app_with_bot.cfg_widgets["cooldown_extra_min"]._text = "5.7"
    app_with_bot._collect_form_into_config("bid")
    assert app_with_bot.bots["bid"]["config"]["cooldown_extra_min"] == 5


def test_collect_form_pause_duration_hours_to_seconds(
    app_with_bot: gui.SelfbotManagerApp,
) -> None:
    app_with_bot.cfg_widgets["pause_duration_min"]._text = "2"
    app_with_bot._collect_form_into_config("bid")
    assert app_with_bot.bots["bid"]["config"]["pause_duration_min"] == 7200.0


def test_collect_form_pause_duration_empty_zero(
    app_with_bot: gui.SelfbotManagerApp, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Bypass sanitize_config's clamp to assert the raw empty branch wrote 0.
    monkeypatch.setattr(gui, "sanitize_config", lambda c: c)
    app_with_bot.cfg_widgets["pause_duration_min"]._text = ""
    app_with_bot._collect_form_into_config("bid")
    assert app_with_bot.bots["bid"]["config"]["pause_duration_min"] == 0


def test_collect_form_default_numeric_float(
    app_with_bot: gui.SelfbotManagerApp, monkeypatch: pytest.MonkeyPatch
) -> None:
    # `interval_min` falls through the numeric chain into the default `float()`
    # branch. sanitize_config clamps to 30 — bypass it so we see the raw value.
    monkeypatch.setattr(gui, "sanitize_config", lambda c: c)
    app_with_bot.cfg_widgets["interval_min"]._text = "1.5"
    app_with_bot._collect_form_into_config("bid")
    assert app_with_bot.bots["bid"]["config"]["interval_min"] == 1.5


def test_collect_form_numeric_value_error_swallowed(
    app_with_bot: gui.SelfbotManagerApp,
) -> None:
    # Non-parseable numeric: `cfg[key]` is never written → original value preserved.
    app_with_bot.bots["bid"]["config"]["drop_channel"] = 999
    app_with_bot.cfg_widgets["drop_channel"]._text = "nope"
    app_with_bot._collect_form_into_config("bid")
    assert app_with_bot.bots["bid"]["config"]["drop_channel"] == 999


def test_collect_form_non_numeric_entry_keeps_string(
    app_with_bot: gui.SelfbotManagerApp,
) -> None:
    app_with_bot.cfg_widgets["name"]._text = "  alpha  "
    app_with_bot._collect_form_into_config("bid")
    assert app_with_bot.bots["bid"]["config"]["name"] == "alpha"


def test_collect_form_wishlists_dedupe_sorted(app_with_bot: gui.SelfbotManagerApp) -> None:
    app_with_bot.wishlist_persos._text = "Zelda\nAerith\naerith\n  \n"
    app_with_bot.wishlist_series._text = "Naruto\nBleach\nnaruto"
    app_with_bot._collect_form_into_config("bid")
    cfg = app_with_bot.bots["bid"]["config"]
    assert cfg["wishlist"] == ["Aerith", "Zelda"]
    assert cfg["wishlist_series"] == ["Bleach", "Naruto"]


def test_collect_form_updates_entry_name(app_with_bot: gui.SelfbotManagerApp) -> None:
    app_with_bot.cfg_widgets["name"]._text = "renamed"
    app_with_bot._collect_form_into_config("bid")
    app_with_bot.bots["bid"]["entry"].set_name.assert_called_once_with("renamed")


def test_collect_form_default_name_when_missing(app_with_bot: gui.SelfbotManagerApp) -> None:
    # Empty name → sanitize_config restores "Sans nom" → set_name called with that.
    app_with_bot.cfg_widgets["name"]._text = ""
    app_with_bot._collect_form_into_config("bid")
    args, _ = app_with_bot.bots["bid"]["entry"].set_name.call_args
    assert args[0]  # non-empty fallback label


# ---------------------------------------------------------------------------
# _save_current
# ---------------------------------------------------------------------------


def test_save_current_noop_when_no_selection(
    app: gui.SelfbotManagerApp, monkeypatch: pytest.MonkeyPatch
) -> None:
    saved: list = []
    monkeypatch.setattr(gui, "save_bots", lambda b: saved.append(b))
    app.selected_id = None
    app._save_current()
    assert saved == []


def test_save_current_writes_and_logs(
    app_with_bot: gui.SelfbotManagerApp, monkeypatch: pytest.MonkeyPatch
) -> None:
    saved: list = []
    monkeypatch.setattr(gui, "save_bots", lambda b: saved.append(b))
    app_with_bot.selected_id = "bid"
    app_with_bot.cfg_widgets["name"]._text = "alpha"
    app_with_bot.wishlist_persos._text = "Zelda\nAerith"
    app_with_bot.wishlist_series._text = "Bleach"
    app_with_bot._append_log_line = MagicMock()
    app_with_bot._save_current()
    # Persisted once.
    assert saved
    # Wishlists re-rendered sorted.
    assert app_with_bot.wishlist_persos.get() == "Aerith\nZelda"
    assert app_with_bot.wishlist_series.get() == "Bleach"
    # Log line written.
    app_with_bot._append_log_line.assert_called_once_with(
        "bid", "system", "Configuration sauvegardée"
    )


def test_save_current_pushes_config_into_live_instance(
    app_with_bot: gui.SelfbotManagerApp, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(gui, "save_bots", lambda b: None)
    app_with_bot.selected_id = "bid"
    instance = SimpleNamespace(config={"stale": True})
    app_with_bot.bots["bid"]["instance"] = instance
    app_with_bot._append_log_line = MagicMock()
    app_with_bot._save_current()
    assert instance.config is app_with_bot.bots["bid"]["config"]


# ---------------------------------------------------------------------------
# _select_bot
# ---------------------------------------------------------------------------


def test_select_bot_collects_previous_and_populates_new(
    app: gui.SelfbotManagerApp,
) -> None:
    old_entry = MagicMock()
    new_entry = MagicMock()
    app.bots = {
        "old": {
            "config": {"name": "old-name"},
            "entry": old_entry,
            "instance": None,
            "log_widget": None,
            "log_scroll": None,
            "log_buffer": [],
        },
        "new": {
            "config": {"name": "new-name", "night_pause_enabled": True},
            "entry": new_entry,
            "instance": None,
            "log_widget": None,
            "log_scroll": None,
            "log_buffer": [],
        },
    }
    app.selected_id = "old"
    # Pre-fill form widgets to simulate user input on the old bot.
    app.cfg_widgets["name"]._text = "renamed-old"
    app._switch_log_widget = MagicMock()
    app._refresh_action_buttons = MagicMock()

    app._select_bot("new")

    # Old bot's form was collected before the switch.
    assert app.bots["old"]["config"]["name"] == "renamed-old"
    old_entry.set_selected.assert_called_once_with(False)
    # New bot is now selected.
    assert app.selected_id == "new"
    new_entry.set_selected.assert_called_once_with(True)
    # New bot's config was populated into the form.
    assert app.cfg_widgets["name"].get() == "new-name"
    assert app.cfg_widgets["night_pause_enabled"].get() == 1
    app._switch_log_widget.assert_called_once_with("new")
    app._refresh_action_buttons.assert_called_once()


def test_select_bot_without_previous_selection(app: gui.SelfbotManagerApp) -> None:
    entry = MagicMock()
    app.bots["bid"] = {
        "config": {"name": "alpha"},
        "entry": entry,
        "instance": None,
        "log_widget": None,
        "log_scroll": None,
        "log_buffer": [],
    }
    app.selected_id = None
    app._switch_log_widget = MagicMock()
    app._refresh_action_buttons = MagicMock()

    app._select_bot("bid")

    assert app.selected_id == "bid"
    entry.set_selected.assert_called_once_with(True)


def test_select_bot_previous_id_missing_from_bots(app: gui.SelfbotManagerApp) -> None:
    # `selected_id` set but bot already deleted from `self.bots` — the early
    # collect branch must short-circuit on the `in self.bots` check.
    entry = MagicMock()
    app.bots["bid"] = {
        "config": {"name": "alpha"},
        "entry": entry,
        "instance": None,
        "log_widget": None,
        "log_scroll": None,
        "log_buffer": [],
    }
    app.selected_id = "ghost"  # not in bots
    app._switch_log_widget = MagicMock()
    app._refresh_action_buttons = MagicMock()
    app._collect_form_into_config = MagicMock()

    app._select_bot("bid")

    app._collect_form_into_config.assert_not_called()
    assert app.selected_id == "bid"


# ---------------------------------------------------------------------------
# _switch_log_widget
# ---------------------------------------------------------------------------


def test_switch_log_widget_creates_and_replays_buffer(
    app: gui.SelfbotManagerApp,
) -> None:
    child1 = MagicMock()
    child2 = MagicMock()
    app.logs_holder = MagicMock()
    app.logs_holder.winfo_children.return_value = [child1, child2]
    tb = MagicMock()
    sb = MagicMock()
    app._make_log_widget = MagicMock(return_value=(tb, sb))
    app.bots["bid"] = {
        "log_widget": None,
        "log_scroll": None,
        "log_buffer": [("info", "line-a"), ("error", "line-b")],
    }

    app._switch_log_widget("bid")

    # Existing children un-packed.
    child1.pack_forget.assert_called_once()
    child2.pack_forget.assert_called_once()
    # New widget created and persisted.
    app._make_log_widget.assert_called_once()
    assert app.bots["bid"]["log_widget"] is tb
    assert app.bots["bid"]["log_scroll"] is sb
    # Buffer replayed: configure(normal), insert each line, see end, configure(disabled).
    tb.configure.assert_any_call(state="normal")
    tb.configure.assert_any_call(state="disabled")
    tb.insert.assert_any_call("end", "line-a\n", "info")
    tb.insert.assert_any_call("end", "line-b\n", "error")
    tb.see.assert_called_once_with("end")
    # Final pack call wires the widget back.
    sb.pack.assert_called_once_with(side="right", fill="y")
    tb.pack.assert_called_once_with(side="left", fill="both", expand=True)


def test_switch_log_widget_reuses_existing_widget(app: gui.SelfbotManagerApp) -> None:
    app.logs_holder = MagicMock()
    app.logs_holder.winfo_children.return_value = []
    tb = MagicMock()
    sb = MagicMock()
    app._make_log_widget = MagicMock()
    app.bots["bid"] = {
        "log_widget": tb,
        "log_scroll": sb,
        "log_buffer": [("info", "ignored")],
    }

    app._switch_log_widget("bid")

    # Widget reused — no creation, no buffer replay.
    app._make_log_widget.assert_not_called()
    tb.insert.assert_not_called()
    # But it's re-packed for visibility.
    sb.pack.assert_called_once_with(side="right", fill="y")
    tb.pack.assert_called_once_with(side="left", fill="both", expand=True)


# ---------------------------------------------------------------------------
# _delete_current
# ---------------------------------------------------------------------------


def test_delete_current_noop_when_no_selection(app: gui.SelfbotManagerApp) -> None:
    app.selected_id = None
    # Must short-circuit before touching any widget.
    app._delete_current()


def test_delete_current_user_cancels(app: gui.SelfbotManagerApp) -> None:
    entry = MagicMock()
    app.bots["bid"] = {
        "config": {"name": "alpha"},
        "entry": entry,
        "instance": None,
        "log_widget": None,
        "log_scroll": None,
        "log_buffer": [],
    }
    app.selected_id = "bid"
    with patch.object(gui.messagebox, "askyesno", return_value=False):
        app._delete_current()
    # Bot still present.
    assert "bid" in app.bots
    entry.destroy.assert_not_called()


def test_delete_current_confirmed_with_running_instance(
    app: gui.SelfbotManagerApp, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(gui, "save_bots", lambda b: None)
    entry = MagicMock()
    instance = SimpleNamespace(status="running")
    app.bots["bid"] = {
        "config": {"name": "alpha"},
        "entry": entry,
        "instance": instance,
        "log_widget": None,
        "log_scroll": None,
        "log_buffer": [],
    }
    app.selected_id = "bid"
    app.logs_holder = MagicMock()
    child = MagicMock()
    app.logs_holder.winfo_children.return_value = [child]
    app.logs_placeholder = MagicMock()
    app._stop_bot_async = MagicMock()
    app._show_empty_state = MagicMock()
    # Pre-fill widgets to verify they're reset.
    app.cfg_widgets["night_pause_enabled"].select()
    app.cfg_widgets["all_channels"]._text = "123"
    app.cfg_widgets["name"]._text = "alpha"
    app.wishlist_persos._text = "Zelda"
    app.wishlist_series._text = "Naruto"

    with patch.object(gui.messagebox, "askyesno", return_value=True):
        app._delete_current()

    app._stop_bot_async.assert_called_once_with(instance)
    entry.destroy.assert_called_once()
    assert "bid" not in app.bots
    assert app.selected_id is None
    child.pack_forget.assert_called_once()
    app.logs_placeholder.pack.assert_called_once_with(expand=True)
    # Widgets reset.
    assert app.cfg_widgets["night_pause_enabled"].get() == 0
    assert app.cfg_widgets["all_channels"].get() == ""
    assert app.cfg_widgets["name"].get() == ""
    assert app.wishlist_persos.get() == ""
    assert app.wishlist_series.get() == ""
    app._show_empty_state.assert_called_once()


def test_delete_current_confirmed_without_instance(
    app: gui.SelfbotManagerApp, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(gui, "save_bots", lambda b: None)
    entry = MagicMock()
    app.bots["bid"] = {
        "config": {"name": "alpha"},
        "entry": entry,
        "instance": None,
        "log_widget": None,
        "log_scroll": None,
        "log_buffer": [],
    }
    app.selected_id = "bid"
    app.logs_holder = MagicMock()
    app.logs_holder.winfo_children.return_value = []
    app.logs_placeholder = MagicMock()
    app._stop_bot_async = MagicMock()
    app._show_empty_state = MagicMock()
    with patch.object(gui.messagebox, "askyesno", return_value=True):
        app._delete_current()
    # No instance → no stop call.
    app._stop_bot_async.assert_not_called()
    assert "bid" not in app.bots


# ---------------------------------------------------------------------------
# _toggle_theme
# ---------------------------------------------------------------------------


def test_toggle_theme_dark_to_light(
    app: gui.SelfbotManagerApp, monkeypatch: pytest.MonkeyPatch
) -> None:
    saved: list = []
    monkeypatch.setattr(gui, "save_settings", lambda s: saved.append(dict(s)))
    app.theme.mode = "dark"
    app.theme.overrides = {"bg": "#ff00ff"}
    app._rebuild_ui = MagicMock()
    app._toggle_theme()
    assert app.theme.mode == "light"
    assert app.theme.overrides == {}
    assert app.settings["theme"] == {"mode": "light", "overrides": {}}
    assert saved and saved[-1]["theme"] == {"mode": "light", "overrides": {}}
    app._rebuild_ui.assert_called_once()


def test_toggle_theme_light_to_dark(
    app: gui.SelfbotManagerApp, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(gui, "save_settings", lambda s: None)
    app.theme.mode = "light"
    app.theme.overrides = {"accent": "#abcdef"}
    app._rebuild_ui = MagicMock()
    app._toggle_theme()
    assert app.theme.mode == "dark"
    assert app.theme.overrides == {}
    app._rebuild_ui.assert_called_once()

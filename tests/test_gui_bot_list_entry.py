"""Display-free coverage for BotListEntry (sidebar bot row widget).

The class extends `ctk.CTkFrame` and pairs a `tk.Canvas` dot with a
`ctk.CTkLabel`. We can't construct one for real (Tk root required and
forbidden in tests), so we monkeypatch the three constructors plus
`bind`/`pack_propagate` to no-ops and assert on the resulting attrs +
method behavior."""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

import customtkinter as ctk
import pytest

from sofi_manager import gui


@pytest.fixture
def stub_tk(monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    """Stub out Tk-touching pieces of BotListEntry.__init__.

    Returns a dict capturing the Canvas + Label mocks plus a `bind_calls`
    list so individual tests can assert on what was bound and on which
    widget."""
    captured: dict[str, Any] = {"bind_calls": []}

    monkeypatch.setattr(ctk.CTkFrame, "__init__", lambda self, *a, **kw: None)
    monkeypatch.setattr(ctk.CTkFrame, "pack_propagate", lambda self, *a, **kw: None)

    def _frame_bind(self: Any, *a: Any, **kw: Any) -> None:
        captured["bind_calls"].append(("frame", a, kw))

    def _frame_configure(self: Any, **kw: Any) -> None:
        captured.setdefault("frame_configures", []).append(kw)

    monkeypatch.setattr(ctk.CTkFrame, "bind", _frame_bind, raising=False)
    monkeypatch.setattr(ctk.CTkFrame, "configure", _frame_configure, raising=False)

    canvas_mock = MagicMock(name="canvas")
    canvas_mock.create_oval.return_value = "oval-id"
    monkeypatch.setattr(gui.tk, "Canvas", lambda *a, **kw: canvas_mock)
    captured["canvas"] = canvas_mock

    label_mock = MagicMock(name="label")
    monkeypatch.setattr(gui.ctk, "CTkLabel", lambda *a, **kw: label_mock)
    captured["label"] = label_mock

    # CTkFont touches the default Tk root on instantiation — replace it
    # with a plain MagicMock factory so the kw stays a valid argument.
    monkeypatch.setattr(gui.ctk, "CTkFont", lambda *a, **kw: MagicMock(name="font"))
    return captured


def _make_entry(on_click: Any = None) -> gui.BotListEntry:
    theme = gui.Theme()
    cb = on_click or MagicMock()
    return gui.BotListEntry(master=None, theme=theme, bot_id="bid-1", on_click=cb)


# ---------------------------------------------------------------------------
# __init__
# ---------------------------------------------------------------------------


def test_init_stores_basic_attrs(stub_tk: dict[str, Any]) -> None:
    cb = MagicMock()
    entry = _make_entry(on_click=cb)
    assert entry.bot_id == "bid-1"
    assert entry.on_click is cb
    assert entry.selected is False
    assert isinstance(entry.theme, gui.Theme)


def test_init_dot_color_starts_off(stub_tk: dict[str, Any]) -> None:
    entry = _make_entry()
    assert entry._dot_color == entry.theme["dot_off"]


def test_init_creates_canvas_oval_and_stores_id(stub_tk: dict[str, Any]) -> None:
    entry = _make_entry()
    assert entry.dot is stub_tk["canvas"]
    assert entry.dot_id == "oval-id"
    stub_tk["canvas"].create_oval.assert_called_once()
    stub_tk["canvas"].pack.assert_called_once()


def test_init_creates_label_and_packs_it(stub_tk: dict[str, Any]) -> None:
    entry = _make_entry()
    assert entry.label is stub_tk["label"]
    stub_tk["label"].pack.assert_called_once()


def test_init_binds_three_events_on_each_widget(stub_tk: dict[str, Any]) -> None:
    _make_entry()
    # Frame gets 3 bindings (Button-1, Enter, Leave); the Canvas + Label
    # each get the same 3 via their respective .bind mocks.
    frame_binds = [c for c in stub_tk["bind_calls"] if c[0] == "frame"]
    assert {c[1][0] for c in frame_binds} == {"<Button-1>", "<Enter>", "<Leave>"}
    # Canvas + label each saw 3 .bind calls.
    assert stub_tk["canvas"].bind.call_count == 3
    assert stub_tk["label"].bind.call_count == 3


# ---------------------------------------------------------------------------
# _click / _enter / _leave / _set_bg
# ---------------------------------------------------------------------------


def test_click_invokes_on_click_with_bot_id(stub_tk: dict[str, Any]) -> None:
    cb = MagicMock()
    entry = _make_entry(on_click=cb)
    entry._click(None)
    cb.assert_called_once_with("bid-1")


def test_enter_changes_bg_when_not_selected(stub_tk: dict[str, Any]) -> None:
    entry = _make_entry()
    entry._enter(None)
    # The last configure on the frame should be panel_hover.
    last = stub_tk["frame_configures"][-1]
    assert last == {"fg_color": entry.theme["panel_hover"]}
    stub_tk["canvas"].configure.assert_called_with(bg=entry.theme["panel_hover"])


def test_enter_is_noop_when_selected(stub_tk: dict[str, Any]) -> None:
    entry = _make_entry()
    entry.selected = True
    before = list(stub_tk.get("frame_configures") or [])
    entry._enter(None)
    after = list(stub_tk.get("frame_configures") or [])
    assert before == after  # nothing new appended


def test_leave_restores_panel_when_not_selected(stub_tk: dict[str, Any]) -> None:
    entry = _make_entry()
    entry._leave(None)
    last = stub_tk["frame_configures"][-1]
    assert last == {"fg_color": entry.theme["panel"]}


def test_leave_is_noop_when_selected(stub_tk: dict[str, Any]) -> None:
    entry = _make_entry()
    entry.selected = True
    before = list(stub_tk.get("frame_configures") or [])
    entry._leave(None)
    after = list(stub_tk.get("frame_configures") or [])
    assert before == after


# ---------------------------------------------------------------------------
# set_selected
# ---------------------------------------------------------------------------


def test_set_selected_true_paints_selected_bg(stub_tk: dict[str, Any]) -> None:
    entry = _make_entry()
    entry.set_selected(True)
    assert entry.selected is True
    last = stub_tk["frame_configures"][-1]
    assert last == {"fg_color": entry.theme["panel_selected"]}


def test_set_selected_false_paints_default_panel_bg(stub_tk: dict[str, Any]) -> None:
    entry = _make_entry()
    entry.selected = True
    entry.set_selected(False)
    assert entry.selected is False
    last = stub_tk["frame_configures"][-1]
    assert last == {"fg_color": entry.theme["panel"]}


# ---------------------------------------------------------------------------
# set_name
# ---------------------------------------------------------------------------


def test_set_name_writes_value(stub_tk: dict[str, Any]) -> None:
    entry = _make_entry()
    entry.set_name("alpha")
    stub_tk["label"].configure.assert_called_with(text="alpha")


def test_set_name_falls_back_to_placeholder_when_empty(
    stub_tk: dict[str, Any],
) -> None:
    entry = _make_entry()
    entry.set_name("")
    stub_tk["label"].configure.assert_called_with(text="(sans nom)")


# ---------------------------------------------------------------------------
# set_status
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "status,color_key",
    [
        ("running", "success"),
        ("starting", "warn"),
        ("error", "error"),
        ("stopped", "dot_off"),
    ],
)
def test_set_status_maps_known_statuses(
    stub_tk: dict[str, Any], status: str, color_key: str
) -> None:
    entry = _make_entry()
    entry.set_status(status)
    assert entry._dot_color == entry.theme[color_key]
    stub_tk["canvas"].itemconfig.assert_called_with("oval-id", fill=entry.theme[color_key])


def test_set_status_unknown_falls_back_to_dot_off(stub_tk: dict[str, Any]) -> None:
    entry = _make_entry()
    entry.set_status("mystery")
    assert entry._dot_color == entry.theme["dot_off"]

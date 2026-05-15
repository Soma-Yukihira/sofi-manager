"""Pure-helper coverage for gui.py — atomic JSON IO, bot/settings
persistence, theme assembly, and the small string utilities. No Tk
windows are constructed; the helpers under test are display-free."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest
from cryptography.fernet import Fernet

from sofi_manager import crypto, gui


@pytest.fixture(autouse=True)
def _isolated_cipher() -> object:
    crypto.set_cipher_for_tests(Fernet(Fernet.generate_key()))
    yield
    crypto.set_cipher_for_tests(None)


# ---------------------------------------------------------------------------
# write_json_atomic
# ---------------------------------------------------------------------------


def test_write_json_atomic_round_trip(tmp_path: Path) -> None:
    target = tmp_path / "out.json"
    gui.write_json_atomic(target, {"k": "v", "n": 3})
    assert json.loads(target.read_text(encoding="utf-8")) == {"k": "v", "n": 3}


def test_write_json_atomic_cleans_tmp_file(tmp_path: Path) -> None:
    target = tmp_path / "out.json"
    gui.write_json_atomic(target, {"a": 1})
    assert not (tmp_path / "out.json.tmp").exists()


def test_write_json_atomic_overwrites_existing(tmp_path: Path) -> None:
    target = tmp_path / "out.json"
    target.write_text('{"old": true}', encoding="utf-8")
    gui.write_json_atomic(target, {"new": True})
    assert json.loads(target.read_text(encoding="utf-8")) == {"new": True}


def test_write_json_atomic_preserves_unicode(tmp_path: Path) -> None:
    target = tmp_path / "out.json"
    gui.write_json_atomic(target, {"name": "Café ⚜"})
    raw = target.read_text(encoding="utf-8")
    assert "Café ⚜" in raw  # ensure_ascii=False


# ---------------------------------------------------------------------------
# load_bots / save_bots
# ---------------------------------------------------------------------------


def test_load_bots_returns_empty_when_missing(tmp_path: Path) -> None:
    with patch.object(gui, "CONFIG_PATH", tmp_path / "absent.json"):
        assert gui.load_bots() == []


def test_load_bots_returns_empty_on_corrupted_json(tmp_path: Path) -> None:
    cfg = tmp_path / "bots.json"
    cfg.write_text("{not valid json", encoding="utf-8")
    with patch.object(gui, "CONFIG_PATH", cfg):
        assert gui.load_bots() == []


def test_save_then_load_bots_round_trip(tmp_path: Path) -> None:
    cfg = tmp_path / "bots.json"
    bots = [{"_id": "a", "name": "alpha", "token": "TOK_A"}]
    with patch.object(gui, "CONFIG_PATH", cfg):
        gui.save_bots(bots)
        reloaded = gui.load_bots()
    assert reloaded == bots


def test_save_bots_writes_ciphertext(tmp_path: Path) -> None:
    cfg = tmp_path / "bots.json"
    with patch.object(gui, "CONFIG_PATH", cfg):
        gui.save_bots([{"_id": "a", "name": "x", "token": "PLAINTEXT_TOKEN"}])
    raw = cfg.read_text(encoding="utf-8")
    assert "PLAINTEXT_TOKEN" not in raw
    assert "enc:v1:" in raw


def test_load_bots_accepts_legacy_plaintext_token(tmp_path: Path) -> None:
    cfg = tmp_path / "bots.json"
    payload = {"bots": [{"_id": "a", "name": "x", "token": "LEGACY"}]}
    cfg.write_text(json.dumps(payload), encoding="utf-8")
    with patch.object(gui, "CONFIG_PATH", cfg):
        bots = gui.load_bots()
    assert bots[0]["token"] == "LEGACY"


def test_save_bots_does_not_mutate_input(tmp_path: Path) -> None:
    cfg = tmp_path / "bots.json"
    bots = [{"_id": "a", "name": "x", "token": "SECRET"}]
    with patch.object(gui, "CONFIG_PATH", cfg):
        gui.save_bots(bots)
    # save_bots must not encrypt the caller's in-memory copy.
    assert bots[0]["token"] == "SECRET"


# ---------------------------------------------------------------------------
# load_settings / save_settings
# ---------------------------------------------------------------------------


def test_load_settings_defaults_when_missing(tmp_path: Path) -> None:
    with patch.object(gui, "SETTINGS_PATH", tmp_path / "absent.json"):
        assert gui.load_settings() == {"theme": {"mode": "dark", "overrides": {}}}


def test_load_settings_defaults_on_corrupted_json(tmp_path: Path) -> None:
    path = tmp_path / "settings.json"
    path.write_text("{not valid", encoding="utf-8")
    with patch.object(gui, "SETTINGS_PATH", path):
        assert gui.load_settings() == {"theme": {"mode": "dark", "overrides": {}}}


def test_load_settings_backfills_missing_keys(tmp_path: Path) -> None:
    path = tmp_path / "settings.json"
    path.write_text(json.dumps({"theme": {}}), encoding="utf-8")
    with patch.object(gui, "SETTINGS_PATH", path):
        s = gui.load_settings()
    assert s["theme"]["mode"] == "dark"
    assert s["theme"]["overrides"] == {}


def test_load_settings_preserves_user_values(tmp_path: Path) -> None:
    path = tmp_path / "settings.json"
    payload = {"theme": {"mode": "light", "overrides": {"bg": "#fff"}}}
    path.write_text(json.dumps(payload), encoding="utf-8")
    with patch.object(gui, "SETTINGS_PATH", path):
        s = gui.load_settings()
    assert s["theme"]["mode"] == "light"
    assert s["theme"]["overrides"] == {"bg": "#fff"}


def test_save_then_load_settings_round_trip(tmp_path: Path) -> None:
    path = tmp_path / "settings.json"
    payload = {"theme": {"mode": "light", "overrides": {"accent": "#d4af37"}}}
    with patch.object(gui, "SETTINGS_PATH", path):
        gui.save_settings(payload)
        assert gui.load_settings() == payload


# ---------------------------------------------------------------------------
# dedupe_sort
# ---------------------------------------------------------------------------


def test_dedupe_sort_sorts_alphabetically() -> None:
    assert gui.dedupe_sort(["charlie", "alpha", "bravo"]) == ["alpha", "bravo", "charlie"]


def test_dedupe_sort_is_case_insensitive_and_keeps_first_casing() -> None:
    # First-seen casing wins, but ordering is case-insensitive.
    assert gui.dedupe_sort(["Apple", "apple", "APPLE"]) == ["Apple"]
    assert gui.dedupe_sort(["banana", "Apple"]) == ["Apple", "banana"]


def test_dedupe_sort_strips_and_drops_empty() -> None:
    assert gui.dedupe_sort(["  alpha  ", "", "   ", "bravo"]) == ["alpha", "bravo"]


def test_dedupe_sort_empty_input() -> None:
    assert gui.dedupe_sort([]) == []


# ---------------------------------------------------------------------------
# contrast_text
# ---------------------------------------------------------------------------


def test_contrast_text_dark_background_returns_white() -> None:
    assert gui.contrast_text("#000000") == "#ffffff"
    assert gui.contrast_text("#1a1a1a") == "#ffffff"


def test_contrast_text_light_background_returns_black() -> None:
    assert gui.contrast_text("#ffffff") == "#000000"
    assert gui.contrast_text("#f4d03f") == "#000000"  # bright gold


def test_contrast_text_handles_missing_hash() -> None:
    assert gui.contrast_text("ffffff") == "#000000"


def test_contrast_text_falls_back_on_invalid_input() -> None:
    assert gui.contrast_text("not-a-color") == "#000000"
    assert gui.contrast_text("") == "#000000"


# ---------------------------------------------------------------------------
# Theme
# ---------------------------------------------------------------------------


def test_theme_default_mode_is_dark() -> None:
    t = gui.Theme()
    assert t.mode == "dark"
    assert t["bg"] == gui.DARK_THEME["bg"]


def test_theme_unknown_mode_falls_back_to_dark() -> None:
    t = gui.Theme(mode="solarized")
    assert t.mode == "dark"


def test_theme_light_mode_uses_light_preset() -> None:
    t = gui.Theme(mode="light")
    assert t["bg"] == gui.LIGHT_THEME["bg"]


def test_theme_overrides_mask_preset() -> None:
    t = gui.Theme(mode="dark", overrides={"accent": "#ff00ff"})
    assert t["accent"] == "#ff00ff"
    # Non-overridden slots still come from the preset.
    assert t["bg"] == gui.DARK_THEME["bg"]


def test_theme_overrides_are_isolated_from_caller_dict() -> None:
    overrides = {"accent": "#111111"}
    t = gui.Theme(overrides=overrides)
    overrides["accent"] = "#222222"
    assert t["accent"] == "#111111"


def test_theme_colors_returns_fresh_dict() -> None:
    t = gui.Theme()
    colors = t.colors
    colors["bg"] = "#mutated"
    # Mutating the returned dict must not affect subsequent reads.
    assert t["bg"] == gui.DARK_THEME["bg"]

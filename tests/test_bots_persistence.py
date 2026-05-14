"""Integration: tokens written to bots.json must be ciphertext, and a
legacy plaintext file must transparently round-trip + auto-migrate on
the first save."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest
from cryptography.fernet import Fernet

import cli
import crypto


@pytest.fixture(autouse=True)
def _isolated_cipher() -> object:
    crypto.set_cipher_for_tests(Fernet(Fernet.generate_key()))
    yield
    crypto.set_cipher_for_tests(None)


def _write_legacy_bots(path: Path, token: str) -> None:
    payload = {"bots": [{"_id": "abc", "name": "x", "token": token}]}
    path.write_text(json.dumps(payload), encoding="utf-8")


def test_token_on_disk_is_ciphertext(tmp_path: Path) -> None:
    cfg = tmp_path / "bots.json"
    with patch.object(cli, "CONFIG_PATH", cfg):
        cli.save_bots([{"_id": "abc", "name": "x", "token": "PLAINTEXT_TOKEN"}])
    raw = cfg.read_text(encoding="utf-8")
    assert "PLAINTEXT_TOKEN" not in raw
    assert "enc:v1:" in raw


def test_legacy_plaintext_loads_and_migrates_on_save(tmp_path: Path) -> None:
    cfg = tmp_path / "bots.json"
    _write_legacy_bots(cfg, "LEGACY_PLAIN")

    with patch.object(cli, "CONFIG_PATH", cfg):
        bots: list[dict[str, Any]] = cli.load_bots()
        assert bots[0]["token"] == "LEGACY_PLAIN"

        cli.save_bots(bots)
        raw = cfg.read_text(encoding="utf-8")
        assert "LEGACY_PLAIN" not in raw

        reloaded = cli.load_bots()
        assert reloaded[0]["token"] == "LEGACY_PLAIN"

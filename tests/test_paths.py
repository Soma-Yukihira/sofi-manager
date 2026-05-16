"""Unit tests for sofi_manager.paths — exercise both the PyInstaller-frozen
branch (sys.frozen=True / sys._MEIPASS) and the source-checkout branch."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

from sofi_manager import paths


def test_bundle_dir_in_source_returns_project_root() -> None:
    # In a normal source checkout, bundle_dir() points at the project root —
    # the grandparent of sofi_manager/paths.py.
    result = paths.bundle_dir()
    assert result == Path(paths.__file__).resolve().parent.parent


def test_bundle_dir_frozen_uses_meipass(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "_MEIPASS", str(tmp_path / "meipass"), raising=False)
    assert paths.bundle_dir() == Path(str(tmp_path / "meipass"))


def test_bundle_dir_frozen_without_meipass_falls_back_to_executable(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    # Pretend _MEIPASS is absent — PyInstaller --onedir mode does this.
    monkeypatch.delattr(sys, "_MEIPASS", raising=False)
    monkeypatch.setattr(sys, "executable", str(tmp_path / "app.exe"), raising=False)
    assert paths.bundle_dir() == tmp_path


def test_user_dir_in_source_returns_project_root() -> None:
    assert paths.user_dir() == Path(paths.__file__).resolve().parent.parent


def test_user_dir_frozen_returns_executable_parent(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    exe = tmp_path / "Selfbot Manager.exe"
    exe.write_bytes(b"")  # so .resolve() works without strict=True
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", str(exe), raising=False)
    assert paths.user_dir() == tmp_path.resolve()

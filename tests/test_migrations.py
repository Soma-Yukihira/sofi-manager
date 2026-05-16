"""Unit tests for sofi_manager._migrations.cleanup_legacy_root_files.

We monkey-patch the module-level ``__file__`` so the cleanup operates on
an isolated tmp_path instead of the real repo, which keeps the test from
ever touching the developer's working tree.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from sofi_manager import _migrations


@pytest.fixture
def fake_repo(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Build a tmp_path that mimics the runtime layout: a ``sofi_manager/``
    sub-package alongside the legacy root files we expect to remove."""
    pkg = tmp_path / "sofi_manager"
    pkg.mkdir()
    fake_module = pkg / "_migrations.py"
    fake_module.write_text("# placeholder so resolve() points here\n", encoding="utf-8")
    monkeypatch.setattr(_migrations, "__file__", str(fake_module))
    return tmp_path


def test_cleanup_removes_all_known_legacy_files(fake_repo: Path) -> None:
    for name in _migrations._LEGACY_ROOT_FILES:
        (fake_repo / name).write_text("# legacy orphan\n", encoding="utf-8")

    _migrations.cleanup_legacy_root_files()

    for name in _migrations._LEGACY_ROOT_FILES:
        assert not (fake_repo / name).exists(), f"{name} should have been removed"


def test_cleanup_is_idempotent_when_files_absent(fake_repo: Path) -> None:
    # No legacy files seeded — calling twice must not raise.
    _migrations.cleanup_legacy_root_files()
    _migrations.cleanup_legacy_root_files()


def test_cleanup_leaves_non_legacy_files_alone(fake_repo: Path) -> None:
    keeper = fake_repo / "main.py"
    keeper.write_text("print('kept')\n", encoding="utf-8")
    (fake_repo / "bot_core.py").write_text("# orphan\n", encoding="utf-8")

    _migrations.cleanup_legacy_root_files()

    assert keeper.exists()
    assert not (fake_repo / "bot_core.py").exists()


def test_cleanup_skips_when_package_dir_missing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Simulate __file__ pointing into a path whose parent does not exist on
    # disk — _migrations early-returns instead of walking a phantom root.
    ghost = tmp_path / "does_not_exist" / "_migrations.py"
    monkeypatch.setattr(_migrations, "__file__", str(ghost))
    _migrations.cleanup_legacy_root_files()


def test_cleanup_swallows_unlink_errors(fake_repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    (fake_repo / "bot_core.py").write_text("# locked\n", encoding="utf-8")
    original_unlink = Path.unlink

    def boom(self: Path, *args: object, **kwargs: object) -> None:
        if self.name == "bot_core.py":
            raise OSError("simulated lock")
        original_unlink(self, *args, **kwargs)

    monkeypatch.setattr(Path, "unlink", boom)

    # Must not propagate the OSError — cleanup is best-effort.
    _migrations.cleanup_legacy_root_files()

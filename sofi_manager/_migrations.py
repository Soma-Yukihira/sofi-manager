"""One-shot cleanup of pre-refactor flat-layout root .py files.

Before this refactor every runtime module sat at the project root.
Sources are now under `sofi_manager/`. The git-clone update path deletes
the old root files cleanly (git tracks the rename), but the ZIP codeload
fallback is overwrite-only — old root files linger as orphans.

`cleanup_legacy_root_files()` is invoked early from the root-level
`main.py` / `cli.py` shims to wipe those orphans. Explicit whitelist,
only runs when `sofi_manager/` is in place, idempotent.

Safe to delete this module once it has been live for a few releases.
"""

from __future__ import annotations

from pathlib import Path

_LEGACY_ROOT_FILES = (
    "bot_core.py",
    "crypto.py",
    "gui.py",
    "parsing.py",
    "paths.py",
    "scoring.py",
    "storage.py",
    "updater.py",
)


def cleanup_legacy_root_files() -> None:
    """Remove pre-refactor flat-layout modules orphaned at the project root
    after a ZIP-mode update (codeload never deletes files)."""
    pkg = Path(__file__).resolve().parent
    if not pkg.is_dir():
        return
    root = pkg.parent
    for name in _LEGACY_ROOT_FILES:
        try:
            (root / name).unlink(missing_ok=True)
        except OSError:
            pass

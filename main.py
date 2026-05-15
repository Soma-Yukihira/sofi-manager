"""
main.py - Selfbot Manager GUI entry point.

Thin shim over `sofi_manager.gui:run`. Kept at the project root so the
Windows shortcut and the PyInstaller spec (`Analysis(["main.py"])`)
keep working unchanged across the refactor.
"""

# One-shot: remove pre-refactor flat-layout root .py files that linger
# on ZIP-install upgrades. Idempotent, no-op on git-clone installs.
from sofi_manager._migrations import cleanup_legacy_root_files

cleanup_legacy_root_files()

# Apply any update fetched on the previous run BEFORE importing the GUI,
# so the new code is what gets loaded. No-op on non-git installs.
from sofi_manager.updater import apply_pending_on_startup

apply_pending_on_startup()

from sofi_manager.gui import run

if __name__ == "__main__":
    run()

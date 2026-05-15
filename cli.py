"""
cli.py - Selfbot Manager headless entry point.

Thin shim over `sofi_manager.cli:main`. Kept at the project root so
existing VPS systemd units that invoke `python cli.py` keep working
unchanged across the refactor.
"""

from __future__ import annotations

import sys

from sofi_manager._migrations import cleanup_legacy_root_files
from sofi_manager.cli import main

cleanup_legacy_root_files()

if __name__ == "__main__":
    sys.exit(main())

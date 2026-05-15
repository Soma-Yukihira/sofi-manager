"""
paths.py
PyInstaller-safe location helpers shared by gui / cli / storage.

Two distinct roots:
  - BUNDLE_DIR : read-only resources (assets/). Inside the PyInstaller
    bundle when frozen (sys._MEIPASS), otherwise next to the source.
  - USER_DIR   : mutable state (bots.json, settings.json, grabs.db).
    Always next to the exe / source so the user can edit / back up.

Kept import-light (stdlib only) so storage.py can pull `user_dir` at
startup without triggering the GUI stack.
"""

from __future__ import annotations

import sys
from pathlib import Path


def bundle_dir() -> Path:
    """Read-only resources root. Inside `_MEIPASS` when frozen."""
    if getattr(sys, "frozen", False):
        return Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
    # paths.py lives at sofi_manager/paths.py; the project root is its grandparent.
    return Path(__file__).resolve().parent.parent


def user_dir() -> Path:
    """Mutable user state root. Next to the exe (frozen) or source (dev)."""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent

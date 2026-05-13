"""
build.py — Selfbot Manager · one-command executable build.

Usage:
    python tools/build.py            # produces dist/SelfbotManager/  (recommended)
    python tools/build.py --onefile  # produces dist/SelfbotManager.exe (single-file)
    python tools/build.py --clean    # wipe build/ and dist/ first

The driver is the only public surface — `selfbot-manager.spec` is the
deterministic config it feeds to PyInstaller. End users never edit the
spec directly.

PyInstaller is a build-time-only dependency: installed on demand here,
NOT added to requirements.txt, to keep the runtime install lean.
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
SPEC = ROOT / "selfbot-manager.spec"


def _ensure_pyinstaller() -> None:
    try:
        import PyInstaller  # noqa: F401
        return
    except ImportError:
        pass
    print("[build] PyInstaller not found, installing...", flush=True)
    subprocess.check_call(
        [sys.executable, "-m", "pip", "install", "--quiet", "pyinstaller>=6.0"]
    )


def _clean() -> None:
    for d in ("build", "dist"):
        target = ROOT / d
        if target.exists():
            print(f"[build] removing {target.relative_to(ROOT)}/", flush=True)
            shutil.rmtree(target, ignore_errors=True)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Build the Selfbot Manager executable via PyInstaller.",
    )
    parser.add_argument(
        "--onefile",
        action="store_true",
        help="Bundle into a single .exe (slower startup, more AV noise).",
    )
    parser.add_argument(
        "--clean",
        action="store_true",
        help="Wipe build/ and dist/ before building.",
    )
    args = parser.parse_args(argv)

    if args.clean:
        _clean()

    _ensure_pyinstaller()

    env = os.environ.copy()
    env["SELFBOT_ONEFILE"] = "1" if args.onefile else "0"

    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--noconfirm",
        str(SPEC),
    ]
    print(f"[build] running: {' '.join(cmd)}", flush=True)
    result = subprocess.run(cmd, cwd=str(ROOT), env=env)
    if result.returncode != 0:
        return result.returncode

    if args.onefile:
        out = ROOT / "dist" / ("SelfbotManager.exe" if os.name == "nt" else "SelfbotManager")
    else:
        out = ROOT / "dist" / "SelfbotManager"
    print(f"\n[build] OK -> {out.relative_to(ROOT)}", flush=True)
    if not args.onefile:
        print("[build] Ship the entire dist/SelfbotManager/ folder to end users.", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())

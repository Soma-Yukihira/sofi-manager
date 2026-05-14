"""
create_shortcut.py — Windows · Selfbot Manager · taskbar shortcut.

Creates `Selfbot Manager.lnk` at the repo root pointing at either:

    1. dist/SelfbotManager/SelfbotManager.exe  (PyInstaller build), or
    2. <venv>/Scripts/pythonw.exe main.py      (source install)

…whichever is present. The .lnk is gitignored, so users regenerate it
locally — drag it onto the taskbar, or right-click → Pin to taskbar.

    python tools/create_shortcut.py

Windows-only (uses WScript.Shell via pywin32 if available, otherwise a
PowerShell one-liner — no extra runtime dependency).
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ICON = ROOT / "assets" / "app.ico"
LNK = ROOT / "Selfbot Manager.lnk"


def _find_target() -> tuple[str, str] | None:
    """Return (target_path, arguments) or None if nothing usable found."""
    exe_onedir = ROOT / "dist" / "SelfbotManager" / "SelfbotManager.exe"
    exe_onefile = ROOT / "dist" / "SelfbotManager.exe"
    for candidate in (exe_onedir, exe_onefile):
        if candidate.exists():
            return (str(candidate), "")

    for venv in ("env", "venv", ".venv"):
        pyw = ROOT / venv / "Scripts" / "pythonw.exe"
        if pyw.exists():
            return (str(pyw), '"main.py"')

    return None


def _create_via_powershell(target: str, args: str) -> None:
    ps = (
        "$s = (New-Object -ComObject WScript.Shell).CreateShortcut('{lnk}');"
        "$s.TargetPath='{target}';"
        "$s.Arguments='{args}';"
        "$s.WorkingDirectory='{root}';"
        "$s.IconLocation='{icon},0';"
        "$s.Description='Selfbot Manager';"
        "$s.WindowStyle=1;"
        "$s.Save()"
    ).format(
        lnk=str(LNK).replace("'", "''"),
        target=target.replace("'", "''"),
        args=args.replace("'", "''"),
        root=str(ROOT).replace("'", "''"),
        icon=str(ICON).replace("'", "''"),
    )
    subprocess.check_call(["powershell", "-NoProfile", "-NonInteractive", "-Command", ps])


def main() -> int:
    if os.name != "nt":
        print("[shortcut] This helper is Windows-only.", file=sys.stderr)
        return 1

    if not ICON.exists():
        print(f"[shortcut] Icon missing: {ICON}", file=sys.stderr)
        print("           Repo may be incomplete — pull again.", file=sys.stderr)
        return 1

    found = _find_target()
    if not found:
        print("[shortcut] Nothing to point at.", file=sys.stderr)
        print("           Either build the exe (python tools/build.py)", file=sys.stderr)
        print("           or create a venv with the dependencies installed.", file=sys.stderr)
        return 1

    target, args = found
    _create_via_powershell(target, args)

    print(f"[shortcut] OK -> {LNK}")
    print(f"           Target: {target} {args}".rstrip())
    print("           Drag onto taskbar, or right-click -> Pin to taskbar.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

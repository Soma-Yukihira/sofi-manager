# -*- mode: python ; coding: utf-8 -*-
#
# PyInstaller spec for Selfbot Manager (GUI).
# Driven by tools/build.py — `python tools/build.py [--onefile]`.
#
# Layout choices:
#   - `onedir` by default (faster startup, fewer AV false-positives).
#   - `--onefile` toggled via the SELFBOT_ONEFILE env var (build.py sets it).
#   - `windowed` build: no console window for the GUI.
#   - `assets/app.ico` bundled as a data file AND used as the exe icon.
#
# Runtime state (bots.json, settings.json) is resolved at runtime next to
# the exe by gui.py's USER_DIR helper. Do NOT bundle those — they are
# per-user and gitignored.

import os
from PyInstaller.utils.hooks import collect_data_files

ONEFILE = os.environ.get("SELFBOT_ONEFILE") == "1"

datas = [
    ("assets/app.ico", "assets"),
]
# customtkinter ships JSON themes that PyInstaller misses without help.
datas += collect_data_files("customtkinter")

block_cipher = None

a = Analysis(
    ["main.py"],
    pathex=[],
    binaries=[],
    datas=datas,
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)
pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

if ONEFILE:
    exe = EXE(
        pyz,
        a.scripts,
        a.binaries,
        a.zipfiles,
        a.datas,
        [],
        name="SelfbotManager",
        debug=False,
        bootloader_ignore_signals=False,
        strip=False,
        upx=False,
        runtime_tmpdir=None,
        console=False,
        disable_windowed_traceback=False,
        argv_emulation=False,
        target_arch=None,
        codesign_identity=None,
        entitlements_file=None,
        icon="assets/app.ico",
    )
else:
    exe = EXE(
        pyz,
        a.scripts,
        [],
        exclude_binaries=True,
        name="SelfbotManager",
        debug=False,
        bootloader_ignore_signals=False,
        strip=False,
        upx=False,
        console=False,
        disable_windowed_traceback=False,
        argv_emulation=False,
        target_arch=None,
        codesign_identity=None,
        entitlements_file=None,
        icon="assets/app.ico",
    )
    coll = COLLECT(
        exe,
        a.binaries,
        a.zipfiles,
        a.datas,
        strip=False,
        upx=False,
        upx_exclude=[],
        name="SelfbotManager",
    )

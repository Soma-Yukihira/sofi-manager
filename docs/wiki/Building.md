> 🇬🇧 English · [🇫🇷 Français](Building-fr)

# Building

Selfbot Manager ships from source, but a one-command build produces a
standalone Windows `.exe` for users who don't want to deal with Python.

## TL;DR

```bash
python tools/build.py
```

Output: `dist/SelfbotManager/SelfbotManager.exe` (plus its support
folder). Double-click the exe — no Python, no venv, no console window.

## What runs

`tools/build.py` is the only entry point. It:

1. Installs `pyinstaller>=6.0` on demand if missing (build-time-only
   dependency — not in `requirements.txt`).
2. Invokes PyInstaller against the checked-in spec
   [`selfbot-manager.spec`](https://github.com/Soma-Yukihira/sofi-manager/blob/main/selfbot-manager.spec).
3. Prints the output path on success.

The spec is the source of truth for build configuration. Don't pass
extra flags to PyInstaller directly — edit the spec.

## Output layout

### Default (`onedir`)

```
dist/
└── SelfbotManager/
    ├── SelfbotManager.exe        ← entry point
    ├── assets/app.ico
    └── _internal/                ← Python runtime + bundled libs
```

Ship the whole folder. Faster startup, fewer antivirus false-positives.

### Single-file (`--onefile`)

```bash
python tools/build.py --onefile
```

Produces `dist/SelfbotManager.exe`, a self-extracting bundle. Slower
first launch (extracts to a temp dir), more likely to get flagged by
overzealous AV heuristics — use only if you specifically need a single
file.

### Clean rebuild

```bash
python tools/build.py --clean
```

Wipes `build/` and `dist/` before running. Use after changing the spec,
an asset, or `requirements.txt`.

## Runtime paths

The frozen exe must read its bundled icon from one place and write its
runtime config to another. Two helpers in `gui.py` handle this:

| Helper       | Resolves to (frozen)              | Resolves to (source)         |
| ------------ | --------------------------------- | ---------------------------- |
| `BUNDLE_DIR` | `sys._MEIPASS` (read-only assets) | repo root (next to `gui.py`) |
| `USER_DIR`   | folder containing the .exe        | repo root                    |

- **Read-only assets** (`assets/app.ico`, customtkinter themes) live in
  `BUNDLE_DIR`. PyInstaller embeds them at build time.
- **Mutable state** (`bots.json`, `settings.json`) lives in `USER_DIR`.
  This means an end user can edit / back up these files alongside the
  exe, the same way they would with the source install.

`cli.py` applies the same rule for `bots.json`.

> [!NOTE]
> Never write to `BUNDLE_DIR` at runtime. In `--onefile` mode it points
> at a temp dir that disappears when the process exits.

## After the build · pin to taskbar

```bash
python tools/create_shortcut.py
```

This auto-detects the build at `dist/SelfbotManager/SelfbotManager.exe`
and creates `Selfbot Manager.lnk` pointing at it. Drag onto the taskbar
or right-click → *Pin to taskbar*.

If no build is present, the shortcut falls back to the venv `pythonw.exe`
+ `main.py` source install, exactly like before.

## Releasing

For now, releases are manual:

1. Bump version notes in the changelog (if you keep one).
2. `python tools/build.py --clean`
3. Zip `dist/SelfbotManager/` into `SelfbotManager-vX.Y.Z-win64.zip`.
4. Upload as a GitHub Release asset against the tag.

No installer, no auto-update. The point is full transparency about what
runs.

## Antivirus notes

PyInstaller-bundled apps are sometimes flagged by Windows Defender or
third-party AV — a known limitation of any self-extracting bootloader,
not a sign of malice in this repo. Mitigations applied here:

- `onedir` default (fewer heuristics tripped than `--onefile`).
- No UPX compression (UPX is a hard trigger for many AV vendors).
- Bundled icon = clear publisher signal.

If a scan still flags the build, submit `dist/SelfbotManager.exe` to
your AV vendor as a false positive, or build locally from source.

## Troubleshooting

| Symptom                                   | Cause / fix                                                                                |
| ----------------------------------------- | ------------------------------------------------------------------------------------------ |
| `ModuleNotFoundError` on first launch     | A new runtime import isn't in the spec. Add it to `hiddenimports` in `selfbot-manager.spec`. |
| Icon missing on the window / taskbar      | `assets/app.ico` wasn't bundled. Check `datas` in the spec.                                |
| `bots.json` not found next to the exe     | Working directory is wrong. Always launch via the .exe (or the shortcut), not the .lnk inside `_internal/`. |
| Build succeeds but exe exits immediately  | A console-only `print()` crashed without a console. Run the exe from a terminal to see the traceback. |
| First launch is slow (`--onefile` only)   | Expected — the bundle extracts to a temp dir on every cold start. Use the default `onedir`. |

## Next

- [Updating](Updating) — pulling new code into an existing source install.
- [Installation](Installation) — source install (the original path).

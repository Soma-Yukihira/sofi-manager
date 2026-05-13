# PROJECT_CONTEXT.md

Architectural and operational context for Selfbot Manager.

## What it is

A desktop application (GUI + CLI) that orchestrates multiple Discord
SOFI selfbots in parallel. Each bot runs in its own thread with its own
asyncio loop, sharing a common config file (`bots.json`) and theme
(`settings.json`).

- **GUI:** `main.py` → `gui.py` (CustomTkinter, black & gold theme,
  17-slot color customization, dark / light presets).
- **CLI:** `cli.py` for headless / VPS use; shares the same core as the
  GUI.
- **Core:** `bot_core.py` defines the `SelfBot` class — SOFI message
  parsing (FR + EN), rarity / popularity scoring, wishlist override,
  randomized night-pause window.
- **Updater:** `updater.py` checks GitHub Releases for new versions and
  surfaces results in the GUI top bar.

## Runtime layout

```
sofi-manager/
├── main.py / cli.py / gui.py / bot_core.py / updater.py
├── version.py            # __version__ + __repo__ (single SoT)
├── selfbot-manager.spec  # PyInstaller config, driven by tools/build.py
├── tools/
│   ├── build.py          # `python tools/build.py [--onefile] [--clean]`
│   ├── release.py        # `python tools/release.py [--dry-run] [--skip-tests]`
│   ├── update.py         # end-user `git pull` updater
│   ├── create_shortcut.py
│   └── install-systemd.sh
├── tests/                # pytest unit tests (core)
├── docs/
│   ├── wiki/             # EN + FR wiki sources
│   └── images/           # banner + screenshots
├── assets/app.ico        # gold ⚜ icon, bundled into the .exe
├── requirements.txt      # discord.py-self, customtkinter, curl_cffi
└── LICENSE               # MIT
```

Per-user state created at first launch (gitignored):

- `bots.json` — bot tokens + per-bot config
- `settings.json` — theme mode + 17-slot color customization
- `Selfbot Manager.lnk` — Windows taskbar shortcut

## Build system

[`tools/build.py`](tools/build.py) is the only public surface — it
auto-installs PyInstaller if missing, then drives
[`selfbot-manager.spec`](selfbot-manager.spec).

- Default mode is **onedir** → `dist/SelfbotManager/SelfbotManager.exe`
  + supporting files. Faster startup, fewer AV false-positives.
- `--onefile` produces `dist/SelfbotManager.exe`. Slower startup, more
  AV noise. Not used by the release pipeline.
- `--clean` wipes `build/` and `dist/` first.

The spec bundles `customtkinter` data, `curl_cffi` native libs, and
`_cffi_backend` as a hidden import — none of those are auto-detected by
PyInstaller's module graph.

## Version source of truth

[`version.py`](version.py) is the **only** place that stores the
version. Three consumers:

1. **GUI** — displayed in the top bar.
2. **In-app update check** (`updater.py`) — compared against the latest
   GitHub Release `tag_name` (leading `v` stripped).
3. **Release script** (`tools/release.py`) — derives the tag
   `v{__version__}`.

Bump it in a single commit. Do not store the version in any other
file, in setup metadata, or as a runtime constant elsewhere.

## Release pipeline

[`tools/release.py`](tools/release.py) — see
[docs/wiki/Updating.md](docs/wiki/Updating.md) for the full guide.

**Required tools:** Python 3.10+, Git, GitHub CLI (`gh`, authenticated).

**Commands:**

```bash
python tools/release.py --dry-run   # any branch, no side effects
python tools/release.py             # main only, tags + pushes + publishes
python tools/release.py --skip-tests
```

**Pipeline order:**

1. Read `__version__` + `__repo__` from `version.py`; validate strict
   SemVer `\d+\.\d+\.\d+`.
2. Branch check — must be `main` in live mode; warns only in
   `--dry-run`.
3. Clean tree check (`git status --porcelain` empty).
4. Tag-free check — `v{version}` must not exist locally or on origin.
5. (Live) `gh auth status` succeeds.
6. `pytest -q tests/` (skippable with `--skip-tests`).
7. `python tools/build.py --clean`.
8. Pack `dist/SelfbotManager/` →
   `dist/releases/SelfbotManager-v{version}-windows.zip` (deterministic:
   sorted entries, fixed 2020-01-01 mtime, 0o644 perms).
9. `git tag -a v{version} -m "Release {version}"` then
   `git push origin v{version}`.
10. `gh release create v{version} <archive> --repo {__repo__}` with
    auto-generated title and notes.

**Failure modes:**

- Tests fail → no build, no tag, no publish.
- Build fails or executable missing → no tag, no publish.
- Push fails after local tag → local tag is rolled back, retry-safe.
- `gh release create` fails after push → tag remains; rerun the `gh`
  command manually or `git push --delete origin v{version}` and retry.

## Update detection (consumer side)

`updater.py` calls
`GET https://api.github.com/repos/{__repo__}/releases/latest`:

- Reads `tag_name`, strips a leading `v`, compares against
  `version.py:__version__`.
- Reads `html_url` for the "Open the release" button (sends users to
  the GitHub release page; does not download the archive directly).
- Runs in a background thread — never blocks the UI.

Practical consequence: if a release is published without a matching
`v{version}` tag, or without a Windows zip asset attached, end users
either see the wrong update state or land on a page with no download.
The release script enforces both.

## Git hygiene

`.gitignore` blocks:

- Credentials: `bots.json`, `settings.json`, `*.token`, `*.secret`
- Build / release artifacts: `dist/`, `build/`, `dist/releases/`,
  `*.exe`, `*.zip`, `*.manifest`, `*.toc`, `*.pkg`
- Python cruft: `__pycache__/`, `*.py[cod]`, `*.egg-info/`, caches
- Virtualenvs: `env/`, `venv/`, `.venv/`, `ENV/`
- Tooling state: `.claude/`, `.claude/worktrees/`, `.vscode/`,
  `.idea/`
- Editor / OS junk: `*.swp`, `*.swo`, `.DS_Store`, `Thumbs.db`,
  `*.log`, `*.bak`, `*.tmp`

Run from a clean tree. The release script enforces this; respect it
even when working manually.

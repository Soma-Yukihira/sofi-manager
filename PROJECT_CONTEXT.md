# PROJECT_CONTEXT.md

Architectural and operational context for Selfbot Manager.

## What it is

A desktop application (GUI + CLI) that orchestrates multiple Discord
SOFI selfbots in parallel. Each bot runs in its own thread with its own
asyncio loop, sharing a common config file (`bots.json`) and theme
(`settings.json`).

- **GUI:** `main.py` (root shim) → `sofi_manager.gui` (CustomTkinter,
  black & gold theme, 17-slot color customization, dark / light presets).
- **CLI:** `cli.py` (root shim) → `sofi_manager.cli` for headless / VPS
  use; shares the same core as the GUI.
- **Core:** `sofi_manager.bot_core` defines the `SelfBot` class — SOFI
  message parsing (FR + EN), rarity / popularity scoring, wishlist
  override, randomized night-pause window.
- **Updater:** `sofi_manager.updater` ships continuous updates from
  `origin/main` via `git fetch` + `git pull --ff-only`, surfaced in the
  GUI as a non-blocking gold banner.

## Runtime layout

```
sofi-manager/
├── main.py / cli.py      # thin shims at the root (Windows shortcut, VPS systemd)
├── sofi_manager/         # runtime package — all the actual logic lives here
│   ├── gui.py            # CustomTkinter UI + theme system + banner
│   ├── cli.py            # CLI subcommands (list / show / add / rm / run)
│   ├── bot_core.py       # `SelfBot` class
│   ├── parsing.py        # SOFI message parsers (FR + EN, pure)
│   ├── scoring.py        # card scoring + wishlist override (pure)
│   ├── crypto.py         # Fernet token encryption (keyring + file fallback)
│   ├── paths.py          # `user_dir()` / `bundle_dir()` helpers
│   ├── storage.py        # SQLite grab history + legacy DB migration
│   ├── updater.py        # git-source + ZIP-codeload auto-updater
│   └── _migrations.py    # one-shot cleanup of pre-refactor root .py files
├── selfbot-manager.spec  # PyInstaller config, driven by tools/build.py
├── tools/
│   ├── build.py          # `python tools/build.py [--onefile] [--clean]`
│   ├── update.py         # CLI alternative to the in-app updater
│   ├── create_shortcut.py
│   └── install-systemd.sh
├── tests/                # pytest unit tests (core)
├── docs/
│   ├── wiki/             # EN + FR wiki sources (auto-synced to GitHub Wiki)
│   └── images/           # banner + screenshots
├── assets/app.ico        # gold ⚜ icon, bundled into the .exe
├── requirements.txt      # discord.py-self, customtkinter, curl_cffi
└── LICENSE               # MIT
```

Per-user state created at first launch (gitignored):

- `bots.json` — bot tokens + per-bot config (tokens are Fernet-encrypted
  with a key kept in the OS keyring; see [crypto.py](sofi_manager/crypto.py))
- `settings.json` — theme mode + 17-slot color customization
- `grabs.db` — SQLite history (WAL). Override with `SOFI_DB_PATH`.
- `Selfbot Manager.lnk` — Windows taskbar shortcut

The encryption key lives in the OS keyring under
`service="sofi-manager"`, falling back to `<USER_DATA>/key`
(`%APPDATA%/sofi-manager/` on Windows, `~/.config/sofi-manager/` on
POSIX). Pre-existing plaintext `bots.json` files keep working — the
first save after upgrade rewrites every token as ciphertext. Restoring
`bots.json` from a backup on a different machine without also restoring
the key will surface a clear error rather than silently corrupting
state.

## Build system

[`tools/build.py`](tools/build.py) drives
[`selfbot-manager.spec`](selfbot-manager.spec) — the spec is the
single source of truth. `customtkinter` data, `curl_cffi` native libs
and `_cffi_backend` are bundled there because PyInstaller's module
graph doesn't pick them up on its own.

Modes, output layout and antivirus notes: see
[Building](docs/wiki/Building.md).

## Update model

No release artifacts. Every commit on `main` is what users run, the
moment it lands.

### Why this design

- One source of truth (the git graph), zero manual steps between
  merging and shipping.
- No version-bump dance, no tag-vs-`__version__` drift to police.
- A fast-forward `git pull` plus a re-exec is atomic enough for a
  desktop side-project.

### Safety rails

The git-pull path **refuses to touch the tree** when:

- The current branch is not `main`.
- `git rev-list @{u}..HEAD` > 0 (local commits ahead — would force a
  merge).
- `git status --porcelain --untracked-files=no` is non-empty (local
  modifications to tracked files — risk of conflict).

The `.git/`-absent case is no longer a no-op: `apply_zip_update`
fetches `codeload.github.com/<repo>/zip/refs/heads/main`, validates it
(zip-slip guard, strict SHA baseline persisted as `zip_install_sha`
in `settings.json`), and overwrites tracked files in place. Because
codeload extraction is overwrite-only (it never deletes files removed
upstream), `sofi_manager._migrations.cleanup_legacy_root_files()` runs
on startup as a one-shot to wipe pre-refactor `.py` orphans at the
project root. Frozen `.exe` is the only structurally un-updatable case
— it surfaces an amber banner via `_maybe_show_skip_reason_banner`
pointing at a rebuild.

`bots.json`, `settings.json` and `grabs.db` are gitignored, so they
always survive.

User-facing flow (banner copy, restart sequence, codeload details,
`tools/update.py` CLI alternative): see
[Updating](docs/wiki/Updating.md).

## Git hygiene

`.gitignore` enforces the credentials, build-output, venv and cache
exclusions. The authoritative list of "never commit" patterns lives in
[CLAUDE.md](CLAUDE.md). Workflow: feature branch → PR → squash-merge
into `main`. Every push to `main` is auto-shipped to users.

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
- **Updater:** `updater.py` ships continuous updates from `origin/main`
  via `git fetch` + `git pull --ff-only`, surfaced in the GUI as a
  non-blocking gold banner.

## Runtime layout

```
sofi-manager/
├── main.py / cli.py / gui.py / bot_core.py / updater.py
├── selfbot-manager.spec  # PyInstaller config, driven by tools/build.py
├── tools/
│   ├── build.py          # `python tools/build.py [--onefile] [--clean]`
│   ├── update.py         # CLI alternative to the in-app updater
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

- `bots.json` — bot tokens + per-bot config (tokens are Fernet-encrypted
  with a key kept in the OS keyring; see [crypto.py](crypto.py))
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

[`tools/build.py`](tools/build.py) is the only public surface — it
auto-installs PyInstaller if missing, then drives
[`selfbot-manager.spec`](selfbot-manager.spec).

- Default mode is **onedir** → `dist/SelfbotManager/SelfbotManager.exe`
  + supporting files. Faster startup, fewer AV false-positives.
- `--onefile` produces `dist/SelfbotManager.exe`. Slower startup, more
  AV noise.
- `--clean` wipes `build/` and `dist/` first.

The spec bundles `customtkinter` data, `curl_cffi` native libs, and
`_cffi_backend` as a hidden import — none of those are auto-detected by
PyInstaller's module graph.

## Update model

No release artifacts. Every commit on `main` is what users run, the
moment it lands.

### Why this design

- One source of truth (the git graph), zero manual steps between
  merging and shipping.
- No version-bump dance, no tag-vs-`__version__` drift to police.
- A fast-forward `git pull` plus a re-exec is atomic enough for a
  desktop side-project.

### Flow

1. **Phase 1 — startup** (`updater.apply_pending_on_startup`, called
   from `main.py` *before* `from gui import run`):
   - Checks `.git/` exists, branch is `main`, no local commits ahead,
     working tree clean.
   - If `git rev-list --count HEAD..@{u}` > 0, runs
     `git pull --ff-only origin main` and `os.execv`s the current
     interpreter so the new code is what gets loaded.

2. **Phase 2 — background** (`updater.check_in_background`, called
   from `gui.SelfbotManagerApp.__init__`):
   - Daemon thread runs `git fetch origin main`.
   - If now behind, calls the callback on the Tk main thread (via
     `self.after`) which reveals the gold banner at the top of the
     window: *"Mise à jour disponible — N commit(s) en attente.
     Redémarrez pour appliquer."*

3. **User clicks Redémarrer** → `_on_update_restart` persists state,
   stops bots, calls `updater.apply_and_restart` → pull + re-exec.

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
in `settings.json`), and overwrites tracked files in place. Frozen
`.exe` is the only structurally un-updatable case — it surfaces an
amber banner via `_maybe_show_skip_reason_banner` pointing at a
rebuild.

`bots.json`, `settings.json` and `grabs.db` are gitignored, so they
always survive.

### CLI alternative

[`tools/update.py`](tools/update.py) does the same `git pull` from a
terminal, prints a verbose diff summary, and refreshes pip deps if
`requirements.txt` changed. Useful on a VPS or as a fallback when the
GUI cannot reach the network.

## Git hygiene

`.gitignore` blocks:

- Credentials: `bots.json`, `settings.json`, `*.token`, `*.secret`
- Build artifacts: `dist/`, `build/`, `*.exe`, `*.zip`, `*.manifest`,
  `*.toc`, `*.pkg`
- Python cruft: `__pycache__/`, `*.py[cod]`, `*.egg-info/`, caches
- Virtualenvs: `env/`, `venv/`, `.venv/`, `ENV/`
- Tooling state: `.claude/`, `.claude/worktrees/`, `.vscode/`,
  `.idea/`
- Editor / OS junk: `*.swp`, `*.swo`, `.DS_Store`, `Thumbs.db`,
  `*.log`, `*.bak`, `*.tmp`

Work only on `main`. Every push is a release.

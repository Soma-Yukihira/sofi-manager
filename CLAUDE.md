# CLAUDE.md

Instructions for Claude / AI assistants working in this repository.

## Project at a glance

Selfbot Manager — premium black & gold CustomTkinter GUI + CLI that
orchestrates multiple Discord SOFI selfbots in parallel. Local-first:
tokens and theme settings live in `bots.json` and `settings.json`,
both gitignored.

Read [PROJECT_CONTEXT.md](PROJECT_CONTEXT.md) for the architectural
overview.

## Update model

This project ships **continuously on `main`**, no release artifacts.
Every commit on `main` is what users run.

- **Consumer-side:** `updater.py` runs in the background when the GUI
  starts, does `git fetch origin main`, and if HEAD is behind, surfaces
  a gold banner. On the user's restart, `apply_pending_on_startup()`
  runs `git pull --ff-only` and re-execs the interpreter.
- **No release file, no SemVer tag, no `version.py`.** The git commit
  graph is the version.
- **`tools/update.py`** stays as a verbose CLI alternative (useful on a
  VPS or for debugging the same operation).

The auto-updater is intentionally conservative. Three install shapes:
git clone (fast-forward pull), ZIP (codeload fallback overwrites
tracked files), frozen `.exe` (amber banner, rebuild required). The
git path additionally skips on a non-`main` branch, local commits
ahead of `origin/main`, or uncommitted tracked-file modifications —
the on-demand check in the menu covers those developer cases.

## Hard rules — never commit

- `bots.json`, `settings.json`, `*.token`, `*.secret` (user data /
  credentials)
- `dist/`, `build/`, `*.exe`, `*.zip` (build outputs)
- `__pycache__/`, `*.py[cod]`, `*.egg-info/`
- `env/`, `venv/`, `.venv/`
- `.claude/`, `.claude/worktrees/**`
- `*.log`, `*.bak`, `*.tmp`, `*.swp`, `.DS_Store`, `Thumbs.db`

The `.gitignore` enforces all of these. Don't fight it — write outputs
under `dist/` so a clean checkout stays clean.

## Workflow rules

- **Use feature branches and PRs** — every push to `main` is shipped to
  users immediately by the auto-updater, so review-before-merge is the
  only safety rail. Squash-merge into `main`.
- **Don't push from a dirty tree** without thinking — the auto-updater
  fast-forwards users to your commit as soon as you push.
- **Don't bypass pre-commit hooks** (`--no-verify`) or signing flags
  unless the user explicitly asks for it.
- **Don't reintroduce a release pipeline** (`tools/release.py`,
  `version.py`, GitHub Releases poller) without an explicit request —
  the current owner has stated they don't want it.

## Code style

- Python 3.10+. Use `from __future__ import annotations` in modules with
  type hints, like existing files do.
- Match the existing terse comment style in `tools/*.py` — module
  docstring with usage, single-line comments only where the *why* is
  non-obvious.
- ANSI palette helpers live in `tools/update.py`; reuse the pattern when
  adding new CLI tools.
- Cross-platform: detect with `os.name == "nt"`, prefer `pathlib.Path`,
  avoid shell-specific syntax in subprocess calls.

## Where things live

Runtime modules live under the `sofi_manager/` package. `main.py` and
`cli.py` at the root are thin shims that delegate to it — they stay at
the root so the Windows shortcut, the PyInstaller spec, and existing
VPS systemd units (`python cli.py …`) keep working.

| Path                                     | Purpose                                  |
| ---------------------------------------- | ---------------------------------------- |
| `main.py`                                | GUI entry shim (pre-import update hook) → `sofi_manager.gui:run` |
| `cli.py`                                 | Headless / VPS entry shim → `sofi_manager.cli:main` |
| `sofi_manager/gui.py`                    | CustomTkinter UI + theme system + banner |
| `sofi_manager/cli.py`                    | CLI commands (list / show / add / rm / run) |
| `sofi_manager/bot_core.py`               | `SelfBot` class, SOFI parsing + scoring  |
| `sofi_manager/crypto.py`                 | Fernet token encryption (keyring + file) |
| `sofi_manager/paths.py`                  | `user_dir()` / `bundle_dir()` shared by gui/cli/storage |
| `sofi_manager/parsing.py`                | Pure SOFI message parsers (FR + EN)      |
| `sofi_manager/scoring.py`                | Card scoring + wishlist override         |
| `sofi_manager/storage.py`                | SQLite grab history + `migrate_db` legacy mover |
| `sofi_manager/updater.py`                | Git-source auto-updater (Discord-style)  |
| `sofi_manager/_migrations.py`            | One-shot cleanup of pre-refactor root .py files |
| `tools/build.py` + `selfbot-manager.spec`| PyInstaller build driver + spec          |
| `tools/update.py`                        | End-user `git pull` CLI updater          |
| `tools/create_shortcut.py`               | Windows taskbar shortcut generator       |
| `tests/`                                 | pytest unit tests for the core           |
| `docs/wiki/`                             | Wiki sources (EN + FR, mirrored to GH Wiki via `.github/workflows/wiki-sync.yml`) |

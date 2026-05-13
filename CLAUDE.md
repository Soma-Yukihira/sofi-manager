# CLAUDE.md

Instructions for Claude / AI assistants working in this repository.

## Project at a glance

Selfbot Manager — premium black & gold CustomTkinter GUI + CLI that
orchestrates multiple Discord SOFI selfbots in parallel. Local-first:
tokens and theme settings live in `bots.json` and `settings.json`,
both gitignored.

Read [PROJECT_CONTEXT.md](PROJECT_CONTEXT.md) for the architectural
overview.

## Versioning and releases

- **Single source of truth:** [`version.py`](version.py) — `__version__`
  and `__repo__`. Nothing else stores the version.
- **Tag format:** `vMAJOR.MINOR.PATCH` (strict SemVer, no pre-release
  suffixes). Tag must equal `v{__version__}` exactly — the in-app
  updater compares them directly.
- **Release tool:** [`tools/release.py`](tools/release.py). Always
  rehearse with `--dry-run` first (allowed on feature branches), then
  run live on `main` with a clean tree.
- **Update checker:** `updater.py` queries
  `GET /repos/{__repo__}/releases/latest` and compares `tag_name`
  against `__version__`. A release without a matching tag is invisible
  to users.

See [docs/wiki/Updating.md](docs/wiki/Updating.md) (EN) or
[docs/wiki/Updating-fr.md](docs/wiki/Updating-fr.md) (FR) for the full
maintainer workflow.

## Hard rules — never commit

- `bots.json`, `settings.json`, `*.token`, `*.secret` (user data /
  credentials)
- `dist/`, `build/`, `dist/releases/`, `*.exe`, `*.zip` (build / release
  outputs)
- `__pycache__/`, `*.py[cod]`, `*.egg-info/`
- `env/`, `venv/`, `.venv/`
- `.claude/`, `.claude/worktrees/**`
- `*.log`, `*.bak`, `*.tmp`, `*.swp`, `.DS_Store`, `Thumbs.db`

The `.gitignore` enforces all of these. Don't fight it — write outputs
under `dist/` so a clean checkout stays clean.

## Workflow rules

- Don't release from a dirty tree. `tools/release.py` will refuse, but
  also refuse it in your head.
- Don't release from a feature branch. The script enforces `main` for
  live mode; `--dry-run` is allowed elsewhere for testing.
- Don't release if `pytest` fails or the build fails — both gate the
  release.
- Don't tag manually. Use `tools/release.py`. If you must, the format is
  `vMAJOR.MINOR.PATCH` and the script's checks (clean tree, main branch,
  tag uniqueness) still apply.
- Don't bypass pre-commit hooks (`--no-verify`) or signing flags unless
  the user explicitly asks for it.

## Code style

- Python 3.10+. Use `from __future__ import annotations` in modules with
  type hints, like existing files do.
- Match the existing terse comment style in `tools/*.py` — module
  docstring with usage, single-line comments only where the *why* is
  non-obvious.
- ANSI palette helpers live in `tools/update.py` and `tools/release.py`;
  reuse the pattern when adding new CLI tools.
- Cross-platform: detect with `os.name == "nt"`, prefer `pathlib.Path`,
  avoid shell-specific syntax in subprocess calls.

## Where things live

| Path                                     | Purpose                                  |
| ---------------------------------------- | ---------------------------------------- |
| `main.py`                                | GUI entry point                          |
| `cli.py`                                 | Headless / VPS entry point               |
| `gui.py`                                 | CustomTkinter UI + theme system          |
| `bot_core.py`                            | `SelfBot` class, SOFI parsing + scoring  |
| `updater.py`                             | In-app GitHub Releases checker           |
| `version.py`                             | `__version__`, `__repo__` (single SoT)   |
| `tools/build.py` + `selfbot-manager.spec`| PyInstaller build driver + spec          |
| `tools/release.py`                       | Release automation (this file's topic)   |
| `tools/update.py`                        | End-user `git pull` updater              |
| `tools/create_shortcut.py`               | Windows taskbar shortcut generator       |
| `tests/`                                 | pytest unit tests for the core           |
| `docs/wiki/`                             | Wiki sources (EN + FR)                   |

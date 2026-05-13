> 🇬🇧 English · [🇫🇷 Français](Updating-fr)

# Updating

The project is a moving target — drops formats change, theme presets get
tweaked, dependencies bump. The good news: **your local config is never
touched** by an update.

## Check from the GUI

Click **`⟳  Mises à jour`** in the top bar. The app queries the latest
GitHub Release and shows:

- the installed version (`version.py:__version__`),
- the latest published tag,
- the release title and short notes,
- an **Open the release** button to download the new build.

The check runs in a background thread and never freezes the UI. If no
release has been published yet, you'll see *"Aucune release publiée pour le
moment."* — publish a release on GitHub for this feature to surface
something.

The button only **checks**; it does not download or replace files. Use
`python tools/update.py` (source install) or download the new `.exe` from
the release page (frozen build).

## TL;DR

```bash
python tools/update.py
```

That's it — same command on Windows, macOS, and Linux.

## What it actually runs

1. **Sanity check** — verifies the folder is a git clone (not a downloaded
   ZIP).
2. **`git fetch`** — checks if there's anything new on `main`.
3. **`git pull --ff-only`** — fast-forwards to the latest commit.
   - Refuses to merge if you have local commits diverging from `origin/main`
     (gives you a clear stash/commit hint).
4. **`pip install -r requirements.txt`** — only if `requirements.txt`
   actually changed in the pull. Skipped otherwise to save time.
5. **Summary** — old hash → new hash + number of files changed.

Output sample:

```
⚜  SELFBOT MANAGER  ·  UPDATER
------------------------------------------------------------
->  Checking remote...
->  Pulling latest changes (3 commit(s) behind)...
->  Installing updated dependencies (venv: env\)...
OK  Up to date

    6c1709e  ->  9aab1f4    (4 file(s) changed)

    Your bots.json + settings.json are untouched.
    Launch the app from the taskbar pin or:
      python main.py
```

## What is preserved

| File / folder              | Purpose                          | Touched by update? |
| -------------------------- | -------------------------------- | ------------------ |
| `bots.json`                | All your bots and tokens         | ❌ never           |
| `settings.json`            | Theme mode + custom colors       | ❌ never           |
| `Selfbot Manager.lnk`      | Your taskbar shortcut            | ❌ never           |
| `env/`                     | Your virtual environment         | ❌ never           |
| Project code & icon        | The codebase                     | ✅ overwritten     |

## When it refuses

### "Not a git repository"

You downloaded a ZIP instead of cloning. The script can't `git pull` from a
non-git folder. Fix:

```bash
git clone https://github.com/Soma-Yukihira/sofi-manager.git sofi-manager-new
# copy your config into the new folder
# (Windows: use `copy`; macOS/Linux: use `cp`)
```

Then delete the old folder. Future updates will work with
`python tools/update.py`.

### "git pull failed"

Almost always because you edited a tracked file (e.g. tweaked `gui.py`
locally). The script tells you to stash:

```bash
git stash
python tools/update.py
git stash pop
```

If `git stash pop` reports conflicts, resolve them in your editor.

### Internet error

Self-explanatory — check your connection and try again.

## When `requirements.txt` changes

If a new dependency is added (rare), the script auto-runs
`pip install -r requirements.txt` inside the venv it detects (`env/`,
`venv/`, or `.venv/`). You don't need to do anything manually.

## Format migrations

Today, `bots.json` and `settings.json` schemas are stable. If a future
release changes them in a breaking way, the changelog will mention it and
the GUI will print a clear migration message. No silent corruption.

---

# Publishing a release (maintainers only)

This section is for the project maintainer. End users do not need it.

## Prerequisites

- **Python 3.10+** with `pytest` and `pyinstaller` available (PyInstaller
  is auto-installed by `tools/build.py` if missing)
- **Git** with push rights on `origin`
- **GitHub CLI** (`gh`) — install from <https://cli.github.com/> and run
  `gh auth login` once

## Single source of truth

`version.py:__version__` is the **only** place to bump the version. The
GUI reads it for the "current version" line, the in-app update checker
compares it against GitHub's latest release tag, and `tools/release.py`
derives the tag from it.

Format is strict SemVer `MAJOR.MINOR.PATCH` (no pre-release suffixes).
The GitHub tag is always `v{__version__}` — e.g. `__version__ = "0.2.0"`
→ tag `v0.2.0`.

## Workflow

1. **Bump** `version.py:__version__` on a branch.
2. **Rehearse** the release without touching git or GitHub:
   ```bash
   python tools/release.py --dry-run
   ```
   Allowed from any branch — useful before merging the bump PR. Prints a
   warning if you're not on `main`, runs tests + build + archive, then
   stops.
3. **Merge** the bump PR into `main`.
4. **Switch** to `main` with a clean working tree:
   ```bash
   git checkout main
   git pull --ff-only
   ```
5. **Publish**:
   ```bash
   python tools/release.py
   ```

## What the live script does

1. Reads `__version__` / `__repo__` from `version.py` and validates strict
   SemVer.
2. Hard-fails if the branch is not `main`.
3. Hard-fails if the working tree is dirty (staged, unstaged, or
   untracked).
4. Hard-fails if tag `v{version}` already exists locally or on origin.
5. Verifies `gh` is installed and authenticated.
6. Runs `python -m pytest -q tests` (skip with `--skip-tests`).
7. Runs `python tools/build.py --clean` and verifies
   `dist/SelfbotManager/SelfbotManager.exe` exists.
8. Packs `dist/SelfbotManager/` into a deterministic zip:
   `dist/releases/SelfbotManager-v{version}-windows.zip`
   (sorted entries + fixed mtime → byte-stable across machines).
9. Creates annotated tag `v{version}` and pushes it to origin (rolls the
   local tag back if push fails).
10. `gh release create v{version} <archive> --repo {__repo__}` — creates
    the GitHub Release and uploads the zip as an asset.

## How the in-app update check sees it

`updater.py` queries
`GET https://api.github.com/repos/{__repo__}/releases/latest` and reads
`tag_name`. The GUI strips a leading `v` and compares against
`version.py:__version__`. The release tag **must** be `v{__version__}`
exactly, or the comparison will mismatch and users will see a wrong
"update available" / "up to date" state.

If you publish a release manually (without `tools/release.py`), make sure
the tag matches and that the Windows zip asset is attached to the
release — the download button in the GUI links to the release page, not
the zip directly.

## Flags

| Flag           | Effect                                                            |
| -------------- | ----------------------------------------------------------------- |
| `--dry-run`    | Plan + checks + tests + build + archive. No tag / push / publish. |
| `--skip-tests` | Skip pytest. Use only after running tests separately in CI.       |

## Build outputs and git hygiene

`dist/`, `build/`, `dist/releases/`, `*.exe`, `*.zip`, `__pycache__/`,
and `.claude/worktrees/` are all gitignored. Never commit any of them —
the release script writes everything to `dist/` on purpose so a clean
checkout stays clean.

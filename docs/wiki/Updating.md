# Updating

Selfbot Manager ships **continuously on `main`**. There are no release
artifacts: every commit on `main` is what users run, the moment it
lands. The in-app updater behaves like Discord — silent background
check, gold banner when ready, applied on restart.

## In-app auto-update (git clones)

When you start the GUI, a daemon thread runs `git fetch origin main`.
If the local clone is behind upstream, a gold banner appears at the top
of the window:

> Mise à jour disponible — N commit(s) en attente. Redémarrez pour appliquer.

Click **Redémarrer** and the app:

1. Saves your form / settings (same path as a normal close).
2. Stops any running bot.
3. Runs `git pull --ff-only origin main`.
4. Re-execs the Python interpreter with the same `argv`.

The `bots.json` and `settings.json` files are gitignored, so they are
never touched by the pull.

## Safety rails (git-pull path)

The git-pull path **refuses to touch the tree** when:

- The current branch is not `main`.
- You have local commits ahead of `origin/main`.
- Tracked files have uncommitted modifications.

In those cases no banner appears — they are developer states, and the
on-demand check in the menu surfaces them when needed. The
`.git/`-absent and frozen-`.exe` cases follow their own paths, below.

## CLI alternative

The same operation, verbose, from a terminal:

```bash
python tools/update.py
```

Refreshes pip dependencies if `requirements.txt` changed and prints a
clean diff summary. Useful on a VPS, in `tmux`, or as a fallback when
the GUI can't reach the network.

## ZIP installs (no `.git/`)

The updater falls back to a codeload path. It fetches the current
`main` SHA from `api.github.com`, downloads the matching ZIP from
`codeload.github.com`, and overwrites tracked files in place
(zip-slip guard, strict SHA baseline persisted as `zip_install_sha`
in `settings.json`). The gold banner and the restart flow are
identical to the git path. Gitignored files (`bots.json`,
`settings.json`, `grabs.db`) survive untouched.

## Frozen `.exe`

PyInstaller bundles can't atomically swap their own source files at
runtime, so the updater short-circuits with skip reason `frozen` and
the GUI shows a passive amber banner. Action: rebuild from a fresh
clone via `python tools/build.py`, or switch to a source install.

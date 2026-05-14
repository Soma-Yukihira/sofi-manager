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

## Safety rails

The updater **refuses to touch the tree** when any of the following
holds:

- `.git/` is absent (you installed from a ZIP or shipped `.exe`).
- The current branch is not `main`.
- You have local commits ahead of `origin/main`.
- Tracked files have uncommitted modifications.

In any of those cases the banner is simply not shown.

## CLI alternative

The same operation, verbose, from a terminal:

```bash
python tools/update.py
```

Refreshes pip dependencies if `requirements.txt` changed and prints a
clean diff summary. Useful on a VPS, in `tmux`, or as a fallback when
the GUI can't reach the network.

## ZIP / `.exe` users

These installs have no `.git/`, so the auto-updater is inert. To get
a newer build, re-download the source (or rebuild the executable from
a fresh clone via `python tools/build.py`).

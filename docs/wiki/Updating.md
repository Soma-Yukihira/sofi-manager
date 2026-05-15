# Updating

Selfbot Manager ships **continuously on `main`**. There are no release
artifacts: every commit on `main` is what users run, the moment it
lands. The in-app updater behaves like Discord — silent background
check, gold banner when ready, applied on restart.

## Which path applies to me?

Where the updater lands you depends on how Selfbot Manager was
installed. Find your row first; the sections below cover each path
in detail.

| Your install                                 | What you see                                                                                   | Action                                                                                     |
| -------------------------------------------- | ---------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------ |
| Git clone, on `main`, clean tree             | **Gold banner** + *Redémarrer* button                                                          | Click *Redémarrer* (or restart manually) — fast-forwards on next launch.                   |
| ZIP download (no `.git/`)                    | **Gold banner** via codeload — overwrites tracked files in place on restart                    | Same as above. `bots.json`, `settings.json`, `grabs.db` are gitignored and survive intact. |
| PyInstaller `.exe` (frozen build)            | **Amber banner**: *MAJ auto désactivées*                                                       | Rebuild from a fresh clone (`python tools/build.py`) or switch to a source install.        |
| Git clone, on a feature branch               | No banner. Manual check in the menu stays silent.                                              | `git checkout main` to re-enable updates. See [Troubleshooting › Updates](Troubleshooting#updates). |
| Git clone with uncommitted tracked changes   | No banner. Manual check: *Modifications locales en cours : commit ou stash requis*.            | Commit, stash, or discard. See [Troubleshooting › Updates](Troubleshooting#updates).       |
| Git clone with local commits ahead of `main` | No banner. Manual check: *Commits locaux en avance sur origin/main : push ou reset requis*.    | Push, rebase, or reset. See [Troubleshooting › Updates](Troubleshooting#updates).          |

The first three rows are end-user paths. The last three are developer
states — the updater intentionally stays silent there so it never
clobbers in-progress work.

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

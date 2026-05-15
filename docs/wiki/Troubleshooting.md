> 🇬🇧 English · [🇫🇷 Français](Troubleshooting-fr)

# Troubleshooting

The single most useful tool when something breaks: the **`📥 SOFI:`** log
lines. They show what SOFI actually sent, in the channel the bot is
watching. Most "the bot doesn't react" issues are visible there.

---

## Installation

### `python: command not found` / `'python' is not recognized`

Python isn't on PATH. Reinstall and tick *"Add Python to PATH"*, or call it
explicitly: `C:\Path\To\Python\python.exe`.

### `ModuleNotFoundError: No module named 'discord'`

The venv isn't activated, or `pip install -r requirements.txt` was not run
inside it. Re-activate (`.\env\Scripts\activate`) and install again.

### `ModuleNotFoundError: No module named 'customtkinter'`

Same cause as above. `pip install -r requirements.txt` inside the active venv.

---

## Authentication

### `Token invalide`

The token is empty, expired, or copied with extra whitespace. Re-grab it
(see [Installation › Getting a token](Installation#getting-a-token)) and
paste again.

### Account locked / 2FA prompt

Discord may flag a new login from your selfbot's IP. Log in once from a
browser on the same machine, complete any 2FA, then try again.

---

## Drop detection

### "Drop sent" appears but nothing happens after

Check for a `📥 SOFI:` line right after. If absent, SOFI didn't reply (rare)
or the message wasn't in a watched channel. Check the **Listened channels**
in the Configuration tab.

If `📥 SOFI:` is present but no `🎴 Drop détecté` follows: the message
didn't match `_DROP_TRIGGER_RE`. Open an issue with the `📥 SOFI:` line —
the regex may need extending for a new SOFI format.

### `Drop ignoré (pas le tien)`

Another user dropped in the same channel. Expected behavior.

### `Aucune carte parsée`

The drop format changed. The `📥 SOFI:` line above will show what came in —
copy it into an issue.

### `Boutons toujours disabled`

The bot waited 10× 0.5s for the buttons to activate but they never did.
This is rare and usually a Discord blip. The drop is forfeit for that
cycle. If it's chronic, increase the retry count in
[`bot_core.py`](../../blob/main/bot_core.py) (`for attempt in range(10)`).

---

## Updates

The auto-updater stays silent on three developer-only git states.
The manual check button in the menu (`↻ MAJ`) is what surfaces them.
For the end-user paths (gold / amber banners), see [Updating](Updating).

### Amber banner: *Installation .exe — MAJ auto désactivées*

You're running a PyInstaller `.exe` build. The updater can't atomically
swap the bundled executable's source files while it's running, so it
stays out of the way. To update: download a fresh source clone and
rebuild with `python tools/build.py`, then replace the old
`dist/SelfbotManager/` folder. Your `bots.json`, `settings.json`, and
`grabs.db` live in the same folder and aren't touched by the rebuild.

### Manual check stays silent (on a feature branch)

The updater refuses to touch a tree that isn't on `main`. Switch back:

```bash
git checkout main
git pull --ff-only
```

If you were doing work on the feature branch, push it first or stash it
(see the next two cases).

### `Modifications locales en cours : commit ou stash requis`

`git status --porcelain --untracked-files=no` reports modifications to
tracked files. A fast-forward could conflict, so the updater bails out.
Pick one:

```bash
git status            # see what's modified
git stash             # park the changes, update, then `git stash pop`
git restore <file>    # discard a file you don't want to keep
git commit -am "..."  # commit the work, then update
```

Untracked files are ignored — only changes to tracked files trip this.

### `Commits locaux en avance sur origin/main : push ou reset requis`

You have commits that aren't on `origin/main`. A fast-forward pull would
force a merge, so the updater bails out. Push the work:

```bash
git push origin main
```

Or, if those commits aren't worth keeping:

```bash
git reset --hard origin/main   # destructive — loses local commits
```

---

## GUI

### Theme toggle resets everything to grey

Likely a custom override that conflicted with the new preset. Open the
🎨 Couleurs modal and **Reset**.

### `bots.json` keeps growing or has duplicates

A crash mid-save may leave the file unclean. Stop the app, open
`bots.json`, deduplicate by `_id` field, save, restart.

### High CPU when many bots are running

Each bot is a thread + asyncio loop + Discord client. 5+ bots on a single
machine is fine; beyond that, consider moving to a small VPS with one
bot per process.

---

## Anything else

Open an [issue](../../issues/new) with:

- The exact message from the GUI (status bar + log lines).
- The `📥 SOFI:` lines around the failure.
- OS, Python version, package versions.

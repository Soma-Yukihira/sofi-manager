> 🇬🇧 English · [🇫🇷 Français](Updating-fr)

# Updating

The project is a moving target — drops formats change, theme presets get
tweaked, dependencies bump. The good news: **your local config is never
touched** by an update.

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

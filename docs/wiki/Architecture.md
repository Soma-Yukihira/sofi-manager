> 🇬🇧 English · [🇫🇷 Français](Architecture-fr)

# Architecture

A short tour for anyone forking or extending the project.

## Files

```
main.py        ← GUI entry. Runs apply_pending_on_startup() before
                  importing gui, then gui.run().
cli.py         ← Headless / VPS entry. Shares the same core.
gui.py         ← CustomTkinter UI: theme system, sidebar, tabs, logs,
                  modals, update banner.
bot_core.py    ← SelfBot class. SOFI parsing + scoring. Pure logic.
updater.py     ← Auto-updater: git fast-forward, ZIP codeload fallback,
                  skip_reason classifier (5 states).
crypto.py      ← Fernet token encryption. Key in the OS keyring with
                  a file fallback.
paths.py       ← bundle_dir() / user_dir() resolution. Source of truth
                  for source-vs-frozen path differences.
storage.py     ← SQLite grab history (WAL). Legacy DB migration.
```

The split is enforced by convention:

- `bot_core.py` does **not** import anything UI.
- `gui.py` does **not** import `discord`. It only knows about `SelfBot`,
  `default_config()`, and the parsing helpers used in tests.
- `cli.py` is the proof the core is UI-agnostic: it instantiates
  `SelfBot` directly with no Tk dependency.

## Threading model

Each bot runs in its **own OS thread** with its **own asyncio event loop**.

```
┌─────────────────────┐         ┌────────────────────────────┐
│  Tkinter main loop  │         │   Bot 1 thread             │
│  (UI thread)        │         │   ├── asyncio loop         │
│                     │         │   │   ├── drop_loop        │
│   ─ logs polling   ─┼────────►│   │   ├── cooldown_handler │
│   ─ status updates ─┼◄────────┤   │   └── night_pause      │
│                     │         │   └── discord.Client       │
└─────────────────────┘         └────────────────────────────┘
                                ┌────────────────────────────┐
                                │   Bot 2 thread (idem)      │
                                └────────────────────────────┘
```

Communication:

- **bot → UI** via `queue.Queue` (`SelfBot.log_queue`).
  The UI thread polls every 120 ms with `after()` and drains all queues.
- **bot → UI** for status changes via `status_callback` — it's called from
  the asyncio loop and wraps with `self.after(0, ...)` to bounce onto the
  Tk main thread.
- **UI → bot stop** via `asyncio.run_coroutine_threadsafe()` to schedule
  `client.close()` on the bot's loop.

## Theme system

Two presets (`DARK_THEME`, `LIGHT_THEME`) and a `Theme(mode, overrides)`
helper that merges them. All widget creation goes through `_mk_*` helpers
on the app that read from `self.theme[key]`.

When the user toggles theme or applies custom colors, the app calls
`_rebuild_ui()`:

1. Persists the current bot configs.
2. Detaches `status_callback` from running instances.
3. Destroys every child widget of `self`.
4. Calls `_apply_appearance()` and `_build_layout()`.
5. Re-registers each saved bot, keeping its `SelfBot` instance and log
   buffer alive.
6. Restores the previous selection.

Running threads are unaffected — they keep humming on their loop. Only the
view is rebuilt.

## Drop pipeline

```
on_message
  └── filter: from SOFI, in listened channels
  └── extract_full_text(message)        # content + every embed part
  └── if matches _COOLDOWN_RE → schedule cooldown handler
  └── if matches _DROP_TRIGGER_RE → continue
  └── mention check (covers <@id>, <@!id>, message.mentions)
  └── smart_parse_cards(full_text)      # G•/series/hearts regex
  └── choose_card(cards, cfg, log)      # initial pick (no hearts yet)
  └── fetch message → poll up to 10× for active buttons
  └── update card hearts from button labels
  └── choose_card(cards, cfg, log)      # final pick
  └── random delay, then click
```

`extract_full_text` is the bit that handles SOFI emitting drops as
embeds. `_DROP_TRIGGER_RE` matches both French (`drop des cartes`) and
English (`dropping cards`) variants — extend it if SOFI adds more
languages.

## Persistence

| File            | Owner                | Notes                                       |
| --------------- | -------------------- | ------------------------------------------- |
| `bots.json`     | `gui.py` / `cli.py`  | Bot configs. Tokens Fernet-encrypted via `crypto.py`. |
| `settings.json` | `gui.py`             | Theme prefs + updater state (`zip_install_sha`). |
| `grabs.db`      | `storage.py`         | SQLite history (WAL). `USER_DIR/grabs.db` by default, override with `SOFI_DB_PATH`. Legacy `%APPDATA%` / XDG paths migrated on first launch. |

All three are gitignored — they survive every update.

## Update flow

`updater.skip_reason()` classifies the install into one of five
buckets. The GUI branches off it:

```
                  ┌── None      → git path: git pull --ff-only,
                  │               re-exec on user "Redémarrer" click.
                  │
                  ├── no-git    → ZIP path: codeload fetch +
                  │               _apply_zip_bytes overwrite, same
   skip_reason() ─┤               banner, baseline persisted as
                  │               zip_install_sha in settings.json.
                  │
                  ├── frozen    → amber banner only. PyInstaller
                  │               bundles can't atomically swap their
                  │               own source files at runtime.
                  │
                  └── off-main  → silent. Dev states. The menu's
                      / dirty     on-demand check surfaces them when
                      / ahead     invoked.
```

`apply_pending_on_startup` (called from `main.py` *before* `import
gui`) only takes the git path — the ZIP and frozen cases are handled
later from the UI thread once Tk is running, via
`check_zip_in_background` and `_maybe_show_skip_reason_banner`.

## Packaging

The source tree runs as-is with `python main.py`. For end users, a
checked-in PyInstaller spec (`selfbot-manager.spec`) bundles the GUI
into a standalone Windows executable via `python tools/build.py`.

Two runtime path helpers in `paths.py` keep the source and frozen
builds in sync, and are imported by `gui.py`, `cli.py`, and
`storage.py`:

- `bundle_dir()` — read-only assets. Equals `sys._MEIPASS` when frozen,
  else the repo root.
- `user_dir()` — mutable state (`bots.json`, `settings.json`,
  `grabs.db`). Always resolves to the folder containing the .exe (or
  the source tree), so users can edit/back up these files alongside the
  binary. A one-shot migration moves any pre-existing `grabs.db` from
  the legacy `%APPDATA%` / XDG location into `USER_DIR` on first launch.

See the [Building](Building) wiki page for the full layout and the
PyInstaller-specific gotchas.

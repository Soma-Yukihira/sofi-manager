> 🇬🇧 English · [🇫🇷 Français](Architecture-fr)

# Architecture

A short tour for anyone forking or extending the project.

## Files

```
main.py        ← entry point, just calls gui.run()
gui.py         ← all UI: theme system, sidebar, tabs, logs, modal
bot_core.py    ← SelfBot class, parsing, scoring, no UI imports
```

The split is enforced by convention:

- `bot_core.py` does **not** import anything UI.
- `gui.py` does **not** import `discord`. It only knows about `SelfBot`,
  `default_config()`, and the parsing helpers used in tests.

This means you could ship a CLI variant by writing a `cli.py` that uses
`SelfBot` directly.

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

| File            | Owner    | Notes                                       |
| --------------- | -------- | ------------------------------------------- |
| `bots.json`     | `gui.py` | Array of bot configs. Created on first add. |
| `settings.json` | `gui.py` | UI prefs (theme mode + color overrides).    |

Both are gitignored.

> 🇬🇧 English · [🇫🇷 Français](Configuration-fr)

# Configuration

Every field of the **Configuration** tab, in order.

## Identity

| Field      | What it does                                                |
| ---------- | ----------------------------------------------------------- |
| **Name**   | Free label shown in the sidebar. No effect on behavior.     |
| **Token**  | Your Discord token. Stored locally in `bots.json`. Masked.  |

## Channels

| Field                | What it does                                                                                |
| -------------------- | ------------------------------------------------------------------------------------------- |
| **Drop channel ID**  | Where the bot sends `sd`. Right-click a channel in Discord → *Copy Channel ID*.             |
| **Listened channels**| One ID per line. SOFI messages in these channels are processed. The drop channel is always included automatically. |
| **Command sent**     | The text dropped on cycle. Default: `sd`.                                                   |

## Drop timing

The bot sleeps a random duration in `[interval_min, interval_max]` between
drops. Always set a range — a fixed interval is the easiest pattern to detect.

| Field                | Unit | Sensible default | What it does                                                       |
| -------------------- | ---- | ---------------- | ------------------------------------------------------------------ |
| Interval min         | s    | 510 (8m30s)      | Lower bound of the sleep between two `sd`.                         |
| Interval max         | s    | 600 (10m)        | Upper bound.                                                       |
| Cooldown extra min   | s    | 30               | Random delay added on top of SOFI's announced cooldown.            |
| Cooldown extra max   | s    | 145              | Upper bound of that extra delay.                                   |

## Night pause

Each day, the bot picks a random start between `22:00` and `01:00`, then
sleeps for a random duration.

| Field                | Unit  | Sensible default |
| -------------------- | ----- | ---------------- |
| Enable night pause   | bool  | on               |
| Pause duration min   | hours | 6.5              |
| Pause duration max   | hours | 9.0              |

## Scoring

Each card gets a score in `[0, 1]`. The bot picks the highest, **except** if
a wishlist match is good enough — see *Wishlist override* below.

```
score = rarity_weight · max(0, 1 − G/RARITY_NORM)
      + hearts_weight · min(1, hearts/HEARTS_NORM)
```

| Field                       | Range  | Default | Effect                                                        |
| --------------------------- | ------ | ------- | ------------------------------------------------------------- |
| Rarity weight               | 0–1    | 0.30    | Higher = prefer low G numbers.                                |
| Hearts weight               | 0–1    | 0.70    | Higher = prefer popular cards.                                |
| Rarity norm                 | int    | 2000    | G value treated as "common".                                  |
| Hearts norm                 | int    | 500     | hearts treated as "very popular".                             |
| Wishlist override threshold | float  | 1.40    | If best non-wishlist score ≥ wishlist score × this, take it.  |

> Weights should sum to 1.0.

### Wishlist override — how it works

If a wishlist card is in the drop, it usually wins. But if a non-wishlist
card scores **40%+ higher**, the bot takes it instead. Lower the threshold
to favor wishlists more aggressively, raise it to favor scores.

## Wishlist tab

Two text areas, one entry per line.

- **Characters** — matched against the card name, case-insensitive substring.
- **Series** — matched against the card series, same rules.

On save, both lists are **deduplicated** (case-insensitive) and **sorted
alphabetically**. Duplicate-with-different-case lines collapse to the first
casing seen.

## Logs tab

A live console of the selected bot. Color-coded:

- **gold** — system events (start, stop, drop detected, save).
- **green** — successes (login, click).
- **amber** — warnings (cooldown replaced, drop loop cancelled).
- **red** — errors.
- **gray** — info (drop sent, intervals, every SOFI message received).

`📥 SOFI:` lines show every SOFI message the bot saw in the listened
channels. Useful for diagnosing missed drops.

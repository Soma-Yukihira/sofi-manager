> 🇬🇧 English · [🇫🇷 Français](Stats-fr)

# Stats

The **Stats** tab is a read-only dashboard over `grabs.db`. Every
attempt the bot makes — success or failure — is recorded by
`storage.record_grab`; this tab is how you look at it.

For where the database lives and how it's structured, see
[Database](Database).

## Top bar

| Control          | What it does                                                                          |
| ---------------- | ------------------------------------------------------------------------------------- |
| **Bot filter**   | Dropdown of every `bot_label` seen in the DB. *Tous les bots* aggregates everything.  |
| **↻ Refresh**    | Re-reads the DB and rebuilds every panel. The tab also auto-refreshes after a grab.   |
| **↓ CSV**        | Exports the currently filtered grabs to a CSV file (see *Export* below).              |

## KPI cards

Four compact cards across the top, recomputed from the filtered set:

- **TOTAL GRABS** — every attempt, success or failure.
- **SUCCESS RATE** — `success / total`, rendered as a percentage.
- **TOP 3 SÉRIES** — the three series most often grabbed (successes only).
- **TOP 3 RARETÉS** — the three rarities most often grabbed (successes only).

The two TOP cards ignore failed attempts: a failed grab has no series
or rarity to count.

## Daily chart

A 14-day bar chart of grab counts (`GRABS / JOUR — 14 DERNIERS JOURS`).
The x-axis is `dd/mm` in local time. Empty days render as zero-height
bars, never gaps.

**Click any bar** to open the per-day drill-down modal:

- Header: `GRABS DU <date> · <bot filter scope>`
- Summary line: `<N> tentatives — <S> succès, <F> échecs`
- Table of every grab that day, most recent first:
  - Success rows: timestamp (HH:MM:SS), ✓, bot label, card name, series, rarity, hearts
  - Failure rows: timestamp (HH:MM:SS), ✗, bot label, error code

The bot filter from the top bar carries through — clicking a day with
*"Tous les bots"* selected shows every bot's grabs for that day.

## Export

The **↓ CSV** button writes every grab matching the current filter to
a file named `sofi-grabs-YYYYMMDD-HHMMSS.csv` in a folder you pick.

- Encoding: **UTF-8 with BOM** so Excel opens it without garbling
  accented card names.
- Header row included. Column order is chosen for readability in a
  spreadsheet: `ts, iso_ts, bot_label, channel_id, card_name, series,
  rarity, hearts, score, success, error_code`.
- `iso_ts` is the human-readable form of `ts` (local time, seconds
  precision); both are included so you can sort numerically and read
  visually.

The status bar reports `<N> grabs exportés` on success.

## Empty / error states

- **No DB yet** — the panels show `aucune donnée` until the first
  grab lands.
- **DB locked or unreadable** — the GUI surfaces `Erreur DB` and keeps
  the previous panel content. The DB is opened in WAL mode so a grab
  inserting while you're reading is normal and doesn't trip this.
- **CSV export fails** — usually a permission issue on the target
  folder. Pick a different location.

## Next

- [Database](Database) — file location, schema, `SOFI_DB_PATH` override,
  sqlite3 inspection.
- [Configuration](Configuration) — the rest of the tabs.

> 🇬🇧 English · [🇫🇷 Français](Database-fr)

# Database

Selfbot Manager stores every grab attempt in a local SQLite file —
`grabs.db`. This page covers where it lives, what's in it, and how to
inspect it from the outside.

For the in-app dashboard, see [Stats](Stats).

## Location

Resolved by `paths.user_dir()`, the same root as `bots.json` /
`settings.json`. That is:

- **Source install** — repo root, next to `main.py`.
- **Frozen `.exe`** — the folder containing the executable.

### Override with `SOFI_DB_PATH`

Set the environment variable to an absolute path to relocate the DB.
Useful on a VPS where you want the DB on a different volume, or for
running multiple instances against separate databases.

```bash
# POSIX
export SOFI_DB_PATH=/var/lib/sofi/grabs.db
# Windows (PowerShell)
$env:SOFI_DB_PATH = "D:\sofi\grabs.db"
```

The path's parent folder is created on demand. Both relative and
`~`-prefixed paths are expanded.

### Legacy locations (pre-PR-30)

Older versions kept the DB under the per-user data dir:

- Windows: `%APPDATA%\sofi-manager\grabs.db`
- POSIX: `$XDG_DATA_HOME/sofi-manager/grabs.db`
  (fallback `~/.local/share/sofi-manager/grabs.db`)

On first launch after upgrading, the GUI runs a one-shot migration:
the legacy file (plus its `-wal` / `-shm` sidecars) is moved into the
new location and a gold banner says *"Base de données déplacée vers
le dossier projet. Vos statistiques sont préservées."* The migration
is a no-op when the legacy file is absent, the target already exists,
or `SOFI_DB_PATH` happens to point at the legacy path.

## Schema

A single `grabs` table:

| Column        | Type     | Notes                                                                  |
| ------------- | -------- | ---------------------------------------------------------------------- |
| `id`          | INTEGER  | Primary key, autoincrement.                                            |
| `ts`          | INTEGER  | Unix epoch seconds. Not null.                                          |
| `bot_label`   | TEXT     | The bot's *Name* field at grab time. Not null.                         |
| `channel_id`  | INTEGER  | Discord channel ID where the drop happened. Nullable.                  |
| `card_name`   | TEXT     | Card title as parsed from SOFI. Nullable.                              |
| `series`      | TEXT     | Card series. Nullable.                                                 |
| `rarity`      | TEXT     | Rarity label (e.g. `SR`, `UR`). Nullable.                              |
| `hearts`      | INTEGER  | Heart count when known. Nullable.                                      |
| `score`       | REAL     | Internal scoring output in `[0, 1]`. Nullable.                         |
| `success`     | INTEGER  | `1` if the click went through, `0` otherwise. Not null.                |
| `error_code`  | TEXT     | Short tag on failure (e.g. `BUTTON_TIMEOUT`). Nullable.                |

Two indices: `(ts)` and `(bot_label, ts)` — they keep both the daily
chart and the per-bot filter responsive on long histories.

`success`-only rows still store `card_name` / `series` / `rarity`
when the parse succeeded; `success=0` rows generally only have the
`error_code` filled.

## WAL mode

`init_db` runs `PRAGMA journal_mode=WAL` at startup. That's why the
Stats tab can read while a grab is being inserted, and why you can
open the DB from a `sqlite3` CLI without locking the bot out.

WAL leaves two sidecar files next to the DB:

- `grabs.db-wal` — pending writes not yet checkpointed.
- `grabs.db-shm` — shared memory index.

Both are gitignored alongside `grabs.db` and are safe to delete when
no process is open against the DB. SQLite re-creates them on next open.

> [!WARNING]
> WAL mode does not play well with network shares (SMB, NFS, OneDrive,
> Dropbox, Google Drive). The lock semantics break and you can lose
> writes or corrupt the file. Keep `grabs.db` on a local disk, or
> point `SOFI_DB_PATH` at one.

## Inspection from the CLI

The schema is plain enough that you can answer most questions with a
`sqlite3` shell.

```bash
sqlite3 grabs.db
```

Useful queries:

```sql
-- How many grabs total, and what's the success rate?
SELECT COUNT(*) AS total,
       SUM(success) AS hits,
       ROUND(100.0 * SUM(success) / COUNT(*), 1) AS pct
FROM grabs;

-- Per-bot success rate, busiest first.
SELECT bot_label,
       COUNT(*) AS total,
       SUM(success) AS hits,
       ROUND(100.0 * SUM(success) / COUNT(*), 1) AS pct
FROM grabs
GROUP BY bot_label
ORDER BY total DESC;

-- Most common failure codes.
SELECT error_code, COUNT(*) AS n
FROM grabs
WHERE success = 0 AND error_code IS NOT NULL
GROUP BY error_code
ORDER BY n DESC;

-- Last 24 hours of grabs from one bot, newest first.
SELECT datetime(ts, 'unixepoch', 'localtime') AS when_local,
       success, card_name, series, rarity, hearts, error_code
FROM grabs
WHERE bot_label = 'main'
  AND ts >= strftime('%s', 'now', '-1 day')
ORDER BY ts DESC;
```

Open the DB **read-only** if the bot is running and you only need to
peek:

```bash
sqlite3 "file:grabs.db?mode=ro" -cmd ".uri on"
```

## Backup

`grabs.db` is gitignored, so nothing in the update flow ever touches
it. Back it up like any other SQLite file:

1. With the GUI **closed**: just copy `grabs.db`. (If the `-wal`
   sidecar is present and non-empty, copy it too.)
2. With the GUI **running**: use the SQLite online backup API or run
   `VACUUM INTO 'snapshot.db';` from a `sqlite3` shell — both produce
   a consistent snapshot without stopping the bot.

## Next

- [Stats](Stats) — the dashboard that reads this DB.
- [Architecture](Architecture) — how `sofi_manager.storage` fits in the
  rest of the project.

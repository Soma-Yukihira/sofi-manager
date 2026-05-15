"""
storage.py
Persistance locale des grabs SOFI dans un SQLite.

Indépendant de discord et de la GUI : se teste en isolation.
Le hook côté bot_core encapsule chaque appel dans un try/except,
un bug ici ne doit jamais casser un grab en vol.
"""

from __future__ import annotations

import csv
import os
import shutil
import sqlite3
import sys
import time
from collections import Counter
from collections.abc import Iterable, Iterator
from contextlib import closing
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import TextIO

from .paths import user_dir

_SCHEMA = """
CREATE TABLE IF NOT EXISTS grabs (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    ts          INTEGER NOT NULL,
    bot_label   TEXT    NOT NULL,
    channel_id  INTEGER,
    card_name   TEXT,
    series      TEXT,
    rarity      TEXT,
    hearts      INTEGER,
    score       REAL,
    success     INTEGER NOT NULL,
    error_code  TEXT
);
CREATE INDEX IF NOT EXISTS idx_grabs_ts ON grabs(ts);
CREATE INDEX IF NOT EXISTS idx_grabs_bot_ts ON grabs(bot_label, ts);
"""

_INSERT = (
    "INSERT INTO grabs "
    "(ts, bot_label, channel_id, card_name, series, rarity, hearts, score, success, error_code) "
    "VALUES (:ts, :bot_label, :channel_id, :card_name, :series, :rarity, :hearts, :score, "
    ":success, :error_code)"
)

_FIELDS = (
    "id",
    "ts",
    "bot_label",
    "channel_id",
    "card_name",
    "series",
    "rarity",
    "hearts",
    "score",
    "success",
    "error_code",
)

# Set of resolved DB paths already passed through init_db this process.
_initialized: set[str] = set()


@dataclass(slots=True)
class GrabRecord:
    """Une tentative de grab — succès ou échec."""

    ts: int = field(default_factory=lambda: int(time.time()))
    bot_label: str = ""
    channel_id: int | None = None
    card_name: str | None = None
    series: str | None = None
    rarity: str | None = None
    hearts: int | None = None
    score: float | None = None
    success: bool = False
    error_code: str | None = None
    id: int | None = None


def default_db_path() -> Path:
    """Résout le chemin par défaut de la DB.

    Aligned with bots.json / settings.json: lives next to the exe (frozen)
    or the source dir (dev). Override via SOFI_DB_PATH for VPS / multi-user
    setups where the DB must live elsewhere.
    """
    override = os.environ.get("SOFI_DB_PATH")
    if override:
        return Path(override).expanduser()
    return user_dir() / "grabs.db"


def legacy_db_path() -> Path:
    """Pre-PR-30 path. Used by `migrate_db` to find a pre-existing DB.

    Windows : %APPDATA%\\sofi-manager\\grabs.db
    POSIX   : $XDG_DATA_HOME/sofi-manager/grabs.db
              (fallback ~/.local/share/sofi-manager/grabs.db)
    """
    if sys.platform == "win32":
        base = os.environ.get("APPDATA") or str(Path.home() / "AppData" / "Roaming")
        return Path(base) / "sofi-manager" / "grabs.db"
    xdg = os.environ.get("XDG_DATA_HOME")
    base = Path(xdg).expanduser() if xdg else Path.home() / ".local" / "share"
    return base / "sofi-manager" / "grabs.db"


@dataclass(slots=True, frozen=True)
class MigrationResult:
    """Outcome of `migrate_db`. `moved=True` only on a successful relocation."""

    moved: bool
    reason: str  # "migrated" | "no_source" | "target_exists"
    files: tuple[Path, ...] = ()  # files actually moved to the new path


def migrate_db(old: Path, new: Path) -> MigrationResult:
    """Move grabs.db (+ wal/shm sidecars) from `old` to `new`.

    Idempotent — after a successful migration `old` no longer exists, so
    re-running is a no-op. Skips when `new` already exists to avoid
    clobbering whichever copy is canonical at the new location.

    Caller must ensure no SQLite connection is open against `old` — on
    Windows, an open handle blocks the rename.
    """
    same_path = old.resolve() == new.resolve() if old.exists() and new.exists() else old == new
    if same_path:
        # Caller already lives at the legacy path (e.g. SOFI_DB_PATH points
        # there). Nothing to do — and shutil.move would raise SameFileError.
        return MigrationResult(moved=False, reason="same_path")
    if not old.exists():
        return MigrationResult(moved=False, reason="no_source")
    if new.exists():
        return MigrationResult(moved=False, reason="target_exists")
    # Consolidate any pending WAL into the main file so the wal/shm
    # sidecars become disposable. Best-effort: a failure here just means
    # we'll also move the sidecars below.
    try:
        with closing(_connect(old)) as conn:
            conn.execute("PRAGMA wal_checkpoint(TRUNCATE);")
            conn.commit()
    except sqlite3.Error:
        pass
    new.parent.mkdir(parents=True, exist_ok=True)
    moved: list[Path] = []
    for suffix in ("", "-wal", "-shm"):
        src = Path(str(old) + suffix)
        if src.exists():
            dst = Path(str(new) + suffix)
            shutil.move(str(src), str(dst))
            moved.append(dst)
    return MigrationResult(moved=True, reason="migrated", files=tuple(moved))


def _connect(path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    return conn


def init_db(path: Path | None = None) -> Path:
    """Crée le schéma si nécessaire et active WAL pour lecture concurrente.

    Idempotent — peut être appelé à chaque démarrage sans risque.
    Retourne le chemin résolu, utile pour les logs et les tests.
    """
    resolved = path if path is not None else default_db_path()
    resolved.parent.mkdir(parents=True, exist_ok=True)
    with closing(_connect(resolved)) as conn:
        conn.executescript(_SCHEMA)
        # WAL pour que l'onglet stats puisse lire pendant qu'un grab insère.
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.commit()
    _initialized.add(str(resolved))
    return resolved


def record_grab(record: GrabRecord, path: Path | None = None) -> None:
    """Insère un grab. Auto-init la DB si nécessaire.

    Lève sqlite3.Error / OSError si la DB n'est pas accessible — l'appelant
    est censé encadrer d'un try/except (un bug DB ne doit pas casser un grab).
    """
    resolved = path if path is not None else default_db_path()
    if str(resolved) not in _initialized:
        init_db(resolved)
    payload = asdict(record)
    payload["success"] = 1 if record.success else 0
    payload.pop("id", None)
    with closing(_connect(resolved)) as conn, conn:
        conn.execute(_INSERT, payload)


def _row_to_record(row: sqlite3.Row) -> GrabRecord:
    data = {key: row[key] for key in _FIELDS}
    data["success"] = bool(data["success"])
    return GrabRecord(**data)


def iter_grabs(
    path: Path | None = None,
    *,
    bot_label: str | None = None,
    since_ts: int | None = None,
    until_ts: int | None = None,
    success: bool | None = None,
    limit: int | None = None,
) -> Iterator[GrabRecord]:
    """Itère sur les grabs, plus récent d'abord. Filtres optionnels."""
    resolved = path if path is not None else default_db_path()
    if not resolved.exists():
        return iter(())

    clauses: list[str] = []
    params: list[object] = []
    if bot_label is not None:
        clauses.append("bot_label = ?")
        params.append(bot_label)
    if since_ts is not None:
        clauses.append("ts >= ?")
        params.append(since_ts)
    if until_ts is not None:
        clauses.append("ts <= ?")
        params.append(until_ts)
    if success is not None:
        clauses.append("success = ?")
        params.append(1 if success else 0)

    where = (" WHERE " + " AND ".join(clauses)) if clauses else ""
    limit_sql = f" LIMIT {int(limit)}" if limit is not None else ""
    sql = f"SELECT * FROM grabs{where} ORDER BY ts DESC, id DESC{limit_sql}"

    with closing(_connect(resolved)) as conn:
        rows = conn.execute(sql, tuple(params)).fetchall()
    return iter([_row_to_record(r) for r in rows])


def distinct_bot_labels(path: Path | None = None) -> list[str]:
    """Liste triée des bot_label rencontrés. Vide si la DB n'existe pas encore."""
    resolved = path if path is not None else default_db_path()
    if not resolved.exists():
        return []
    with closing(_connect(resolved)) as conn:
        rows = conn.execute("SELECT DISTINCT bot_label FROM grabs ORDER BY bot_label").fetchall()
    return [str(r["bot_label"]) for r in rows]


# Order chosen to be readable when opened directly in Excel/LibreOffice.
_CSV_COLUMNS = (
    "ts",
    "iso_ts",
    "bot_label",
    "channel_id",
    "card_name",
    "series",
    "rarity",
    "hearts",
    "score",
    "success",
    "error_code",
)


def export_csv(records: Iterable[GrabRecord], out: TextIO) -> int:
    """Écrit les records dans `out` au format CSV (header inclus).

    Caller owns the file: open it with `newline=""` and `encoding="utf-8"`
    (or `utf-8-sig` for Excel compatibility). Returns the number of data
    rows written, so the GUI can show "Exporté N grabs".
    """
    writer = csv.DictWriter(out, fieldnames=_CSV_COLUMNS)
    writer.writeheader()
    count = 0
    for r in records:
        writer.writerow(
            {
                "ts": r.ts,
                "iso_ts": datetime.fromtimestamp(r.ts).isoformat(timespec="seconds"),
                "bot_label": r.bot_label,
                "channel_id": "" if r.channel_id is None else r.channel_id,
                "card_name": r.card_name or "",
                "series": r.series or "",
                "rarity": r.rarity or "",
                "hearts": "" if r.hearts is None else r.hearts,
                "score": "" if r.score is None else f"{r.score:.4f}",
                "success": 1 if r.success else 0,
                "error_code": r.error_code or "",
            }
        )
        count += 1
    return count


# ---------------------------------------------------------------------------
# Aggregations (pure functions over an iterable of GrabRecord)
# Kept here rather than in the GUI module so they're trivially unit-testable.
# ---------------------------------------------------------------------------


@dataclass(slots=True, frozen=True)
class Stats:
    total: int
    success: int
    success_rate: float  # 0.0 to 1.0; 0.0 for empty datasets
    top_series: list[tuple[str, int]]
    top_rarities: list[tuple[str, int]]
    daily_counts: list[tuple[int, int]]  # (day_start_unix, total_count); oldest first


def _day_bucket(ts: int) -> int:
    """Local-midnight unix timestamp of the day containing ts."""
    d = datetime.fromtimestamp(ts).replace(hour=0, minute=0, second=0, microsecond=0)
    return int(d.timestamp())


def compute_stats(
    records: Iterable[GrabRecord],
    *,
    top_n: int = 3,
    days: int = 14,
    now_ts: int | None = None,
) -> Stats:
    """Crunch a list of grabs into the dashboard summary.

    `daily_counts` always contains exactly `days` entries, oldest first,
    so the chart renderer can iterate without worrying about gaps.
    """
    items = list(records)
    total = len(items)
    success = sum(1 for r in items if r.success)
    rate = (success / total) if total else 0.0

    series = Counter(r.series for r in items if r.success and r.series)
    rarities = Counter(r.rarity for r in items if r.success and r.rarity)

    now = int(now_ts if now_ts is not None else time.time())
    today_start = _day_bucket(now)
    one_day = 86_400
    bucket_starts = [today_start - one_day * (days - 1 - i) for i in range(days)]
    by_bucket: Counter[int] = Counter()
    for r in items:
        bucket = _day_bucket(r.ts)
        if bucket >= bucket_starts[0]:
            by_bucket[bucket] += 1
    daily = [(b, by_bucket.get(b, 0)) for b in bucket_starts]

    return Stats(
        total=total,
        success=success,
        success_rate=rate,
        top_series=series.most_common(top_n),
        top_rarities=rarities.most_common(top_n),
        daily_counts=daily,
    )

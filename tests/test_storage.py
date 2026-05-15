"""Tests for the SQLite-backed grab history (storage.py)."""

from __future__ import annotations

import csv
import io
import os
import sqlite3
import time
import unittest
from contextlib import closing
from datetime import datetime
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

import storage
from storage import (
    GrabRecord,
    compute_stats,
    default_db_path,
    distinct_bot_labels,
    export_csv,
    init_db,
    iter_grabs,
    legacy_db_path,
    migrate_db,
    record_grab,
)


class _TmpDB(unittest.TestCase):
    """Each test gets a clean DB path under a tmp dir."""

    def setUp(self):
        self._tmp = TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.db_path = Path(self._tmp.name) / "grabs.db"
        # The init cache is process-global — flush it between tests so a stale
        # entry from a previous run can't mask a missing init.
        storage._initialized.clear()


class InitDbTests(_TmpDB):
    def test_creates_file_and_schema(self):
        path = init_db(self.db_path)
        self.assertEqual(path, self.db_path)
        self.assertTrue(self.db_path.exists())
        with closing(sqlite3.connect(str(self.db_path))) as conn:
            tables = {
                r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
            }
        self.assertIn("grabs", tables)

    def test_creates_parent_directory(self):
        nested = self.db_path.parent / "deep" / "nest" / "grabs.db"
        init_db(nested)
        self.assertTrue(nested.exists())

    def test_idempotent(self):
        init_db(self.db_path)
        # Insert a row, then call init_db again — row must survive.
        record_grab(GrabRecord(bot_label="bot[1]", success=True), path=self.db_path)
        init_db(self.db_path)
        rows = list(iter_grabs(self.db_path))
        self.assertEqual(len(rows), 1)

    def test_creates_useful_indexes(self):
        init_db(self.db_path)
        with closing(sqlite3.connect(str(self.db_path))) as conn:
            indexes = {
                r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='index'")
            }
        self.assertIn("idx_grabs_ts", indexes)
        self.assertIn("idx_grabs_bot_ts", indexes)

    def test_enables_wal_mode(self):
        init_db(self.db_path)
        with closing(sqlite3.connect(str(self.db_path))) as conn:
            mode = conn.execute("PRAGMA journal_mode;").fetchone()[0]
        self.assertEqual(mode.lower(), "wal")

    def test_marks_path_as_initialized(self):
        init_db(self.db_path)
        self.assertIn(str(self.db_path), storage._initialized)


class RecordGrabTests(_TmpDB):
    def test_round_trip_full_record(self):
        rec = GrabRecord(
            ts=1_700_000_000,
            bot_label="bot[2]",
            channel_id=1234567890,
            card_name="Hatsune Miku",
            series="Vocaloid",
            rarity="SR",
            hearts=512,
            score=0.873,
            success=True,
            error_code=None,
        )
        record_grab(rec, path=self.db_path)
        rows = list(iter_grabs(self.db_path))
        self.assertEqual(len(rows), 1)
        got = rows[0]
        self.assertEqual(got.bot_label, "bot[2]")
        self.assertEqual(got.channel_id, 1234567890)
        self.assertEqual(got.card_name, "Hatsune Miku")
        self.assertEqual(got.series, "Vocaloid")
        self.assertEqual(got.rarity, "SR")
        self.assertEqual(got.hearts, 512)
        self.assertAlmostEqual(got.score, 0.873)
        self.assertTrue(got.success)
        self.assertIsNone(got.error_code)
        self.assertEqual(got.ts, 1_700_000_000)
        self.assertIsNotNone(got.id)

    def test_default_ts_is_recent(self):
        before = int(time.time())
        record_grab(GrabRecord(bot_label="bot[1]"), path=self.db_path)
        after = int(time.time())
        rec = next(iter_grabs(self.db_path))
        self.assertGreaterEqual(rec.ts, before)
        self.assertLessEqual(rec.ts, after)

    def test_failure_is_persisted_with_error_code(self):
        record_grab(
            GrabRecord(bot_label="bot[1]", success=False, error_code="40060"),
            path=self.db_path,
        )
        rec = next(iter_grabs(self.db_path))
        self.assertFalse(rec.success)
        self.assertEqual(rec.error_code, "40060")

    def test_auto_init_on_first_record(self):
        # No explicit init_db call — record_grab must bootstrap the schema.
        self.assertFalse(self.db_path.exists())
        record_grab(GrabRecord(bot_label="bot[1]"), path=self.db_path)
        self.assertTrue(self.db_path.exists())
        self.assertEqual(len(list(iter_grabs(self.db_path))), 1)

    def test_id_autoincrements(self):
        for _ in range(3):
            record_grab(GrabRecord(bot_label="bot[1]"), path=self.db_path)
        ids = [r.id for r in iter_grabs(self.db_path)]
        self.assertEqual(len(ids), 3)
        self.assertEqual(len(set(ids)), 3)

    def test_nullable_card_fields_accepted(self):
        # A failed click before any card was scored — minimal record.
        record_grab(
            GrabRecord(bot_label="bot[1]", success=False, error_code="EmptyDrop"),
            path=self.db_path,
        )
        rec = next(iter_grabs(self.db_path))
        self.assertIsNone(rec.card_name)
        self.assertIsNone(rec.series)
        self.assertIsNone(rec.hearts)


class IterGrabsTests(_TmpDB):
    def setUp(self):
        super().setUp()
        # Seed: 3 bots, 2 records each, mixed success.
        seeds = [
            (1_700_000_100, "bot[1]", True, None),
            (1_700_000_200, "bot[1]", False, "10008"),
            (1_700_000_300, "bot[2]", True, None),
            (1_700_000_400, "bot[2]", False, "429"),
            (1_700_000_500, "bot[3]", True, None),
            (1_700_000_600, "bot[3]", True, None),
        ]
        for ts, label, ok, err in seeds:
            record_grab(
                GrabRecord(ts=ts, bot_label=label, success=ok, error_code=err),
                path=self.db_path,
            )

    def test_returns_empty_iter_when_db_missing(self):
        missing = self.db_path.parent / "nope.db"
        self.assertEqual(list(iter_grabs(missing)), [])

    def test_orders_newest_first(self):
        rows = list(iter_grabs(self.db_path))
        timestamps = [r.ts for r in rows]
        self.assertEqual(timestamps, sorted(timestamps, reverse=True))

    def test_filter_by_bot_label(self):
        rows = list(iter_grabs(self.db_path, bot_label="bot[2]"))
        self.assertEqual(len(rows), 2)
        self.assertTrue(all(r.bot_label == "bot[2]" for r in rows))

    def test_filter_by_success_true(self):
        rows = list(iter_grabs(self.db_path, success=True))
        self.assertEqual(len(rows), 4)
        self.assertTrue(all(r.success for r in rows))

    def test_filter_by_success_false(self):
        rows = list(iter_grabs(self.db_path, success=False))
        self.assertEqual(len(rows), 2)
        self.assertTrue(all(not r.success for r in rows))

    def test_filter_by_ts_range(self):
        rows = list(iter_grabs(self.db_path, since_ts=1_700_000_300, until_ts=1_700_000_500))
        self.assertEqual(len(rows), 3)
        for r in rows:
            self.assertGreaterEqual(r.ts, 1_700_000_300)
            self.assertLessEqual(r.ts, 1_700_000_500)

    def test_filter_combined(self):
        rows = list(
            iter_grabs(
                self.db_path,
                bot_label="bot[1]",
                success=False,
            )
        )
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0].error_code, "10008")

    def test_limit(self):
        rows = list(iter_grabs(self.db_path, limit=2))
        self.assertEqual(len(rows), 2)


class DefaultDbPathTests(unittest.TestCase):
    def test_env_override_wins(self):
        with patch.dict(os.environ, {"SOFI_DB_PATH": "/tmp/custom/grabs.db"}, clear=False):
            self.assertEqual(default_db_path(), Path("/tmp/custom/grabs.db"))

    def test_env_override_expands_user(self):
        with patch.dict(os.environ, {"SOFI_DB_PATH": "~/sofi.db"}, clear=False):
            self.assertEqual(default_db_path(), Path("~/sofi.db").expanduser())

    def test_returns_user_dir_grabs_db(self):
        fake = Path("/fake/project/dir")
        with (
            patch.dict(os.environ, {}, clear=True),
            patch.object(storage, "user_dir", lambda: fake),
        ):
            self.assertEqual(default_db_path(), fake / "grabs.db")


class LegacyDbPathTests(unittest.TestCase):
    def test_windows_uses_appdata(self):
        env = {"APPDATA": r"C:\Users\Test\AppData\Roaming"}
        with (
            patch.dict(os.environ, env, clear=True),
            patch.object(storage.sys, "platform", "win32"),
        ):
            path = legacy_db_path()
        self.assertEqual(
            path,
            Path(r"C:\Users\Test\AppData\Roaming") / "sofi-manager" / "grabs.db",
        )

    def test_posix_uses_local_share(self):
        with (
            patch.dict(os.environ, {}, clear=True),
            patch.object(storage.sys, "platform", "linux"),
            patch.object(Path, "home", staticmethod(lambda: Path("/home/test"))),
        ):
            path = legacy_db_path()
        self.assertEqual(path, Path("/home/test/.local/share/sofi-manager/grabs.db"))

    def test_posix_respects_xdg_data_home(self):
        env = {"XDG_DATA_HOME": "/custom/data"}
        with (
            patch.dict(os.environ, env, clear=True),
            patch.object(storage.sys, "platform", "linux"),
        ):
            path = legacy_db_path()
        self.assertEqual(path, Path("/custom/data/sofi-manager/grabs.db"))


class MigrateDbTests(_TmpDB):
    def setUp(self):
        super().setUp()
        self.old = Path(self._tmp.name) / "legacy" / "grabs.db"
        self.new = Path(self._tmp.name) / "project" / "grabs.db"

    def _seed_old(self, *, with_sidecars: bool = False) -> None:
        init_db(self.old)
        record_grab(GrabRecord(bot_label="bot[1]", success=True), path=self.old)
        # Force the init cache so iter/record on `new` later re-initialises.
        storage._initialized.clear()
        if with_sidecars:
            # Real WAL/SHM may have been truncated by the checkpoint inside
            # init_db; create empty stand-ins so we can assert they migrate
            # too even when present.
            Path(str(self.old) + "-wal").write_bytes(b"")
            Path(str(self.old) + "-shm").write_bytes(b"")

    def test_no_source_is_noop(self):
        result = migrate_db(self.old, self.new)
        self.assertFalse(result.moved)
        self.assertEqual(result.reason, "no_source")
        self.assertFalse(self.old.exists())
        self.assertFalse(self.new.exists())

    def test_target_exists_is_noop(self):
        self._seed_old()
        self.new.parent.mkdir(parents=True, exist_ok=True)
        self.new.write_bytes(b"existing")
        result = migrate_db(self.old, self.new)
        self.assertFalse(result.moved)
        self.assertEqual(result.reason, "target_exists")
        # Neither side touched.
        self.assertTrue(self.old.exists())
        self.assertEqual(self.new.read_bytes(), b"existing")

    def test_migrates_db_only(self):
        self._seed_old()
        result = migrate_db(self.old, self.new)
        self.assertTrue(result.moved)
        self.assertEqual(result.reason, "migrated")
        self.assertFalse(self.old.exists())
        self.assertTrue(self.new.exists())
        # Row survived the move.
        rows = list(iter_grabs(self.new))
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0].bot_label, "bot[1]")
        # Reported `files` contains the moved DB.
        self.assertIn(self.new, result.files)

    def test_checkpoint_clears_sidecars_on_happy_path(self):
        # WAL checkpoint(TRUNCATE) consolidates pending writes into the main
        # file and removes the sidecars. We assert the legacy directory is
        # fully empty after migration so the user sees nothing left behind.
        self._seed_old(with_sidecars=True)
        result = migrate_db(self.old, self.new)
        self.assertTrue(result.moved)
        for suffix in ("", "-wal", "-shm"):
            self.assertFalse(Path(str(self.old) + suffix).exists())
        # Main DB landed at the new location.
        self.assertTrue(self.new.exists())
        moved_names = {p.name for p in result.files}
        self.assertEqual(moved_names, {"grabs.db"})

    def test_moves_sidecars_when_checkpoint_fails(self):
        # If the WAL checkpoint can't run (e.g. the DB is unreadable as
        # SQLite for some reason), we must still move every sidecar that
        # happens to be lying around so the legacy dir is clean.
        self._seed_old(with_sidecars=True)
        # Patch _connect so the pragma path raises and we fall through to
        # the unconditional move loop.
        with patch.object(storage, "_connect", side_effect=sqlite3.Error("boom")):
            result = migrate_db(self.old, self.new)
        self.assertTrue(result.moved)
        for suffix in ("", "-wal", "-shm"):
            self.assertFalse(Path(str(self.old) + suffix).exists())
            self.assertTrue(Path(str(self.new) + suffix).exists())
        moved_names = {p.name for p in result.files}
        self.assertEqual(moved_names, {"grabs.db", "grabs.db-wal", "grabs.db-shm"})

    def test_idempotent_after_success(self):
        self._seed_old()
        first = migrate_db(self.old, self.new)
        self.assertTrue(first.moved)
        # Second call: old no longer exists → no_source, no error.
        second = migrate_db(self.old, self.new)
        self.assertFalse(second.moved)
        self.assertEqual(second.reason, "no_source")
        # New DB is untouched.
        self.assertEqual(len(list(iter_grabs(self.new))), 1)

    def test_same_path_is_noop(self):
        # Models the edge case where SOFI_DB_PATH points at the legacy path:
        # default_db_path() == legacy_db_path() and we must not self-move.
        self._seed_old()
        result = migrate_db(self.old, self.old)
        self.assertFalse(result.moved)
        self.assertEqual(result.reason, "same_path")
        self.assertTrue(self.old.exists())

    def test_creates_target_parent_directory(self):
        self._seed_old()
        deep = self.new.parent / "deep" / "nest" / "grabs.db"
        self.assertFalse(deep.parent.exists())
        result = migrate_db(self.old, deep)
        self.assertTrue(result.moved)
        self.assertTrue(deep.exists())


class FailureModeTests(_TmpDB):
    def test_record_grab_raises_on_unwritable_path(self):
        # A path whose parent is a regular file, not a directory.
        blocker = Path(self._tmp.name) / "notadir"
        blocker.write_text("x")
        bad = blocker / "grabs.db"
        with self.assertRaises((OSError, sqlite3.Error)):
            record_grab(GrabRecord(bot_label="bot[1]"), path=bad)

    def test_iter_grabs_does_not_init(self):
        # Reading a non-existent DB must not create the file.
        missing = self.db_path.parent / "phantom.db"
        list(iter_grabs(missing))
        self.assertFalse(missing.exists())


class ComputeStatsTests(unittest.TestCase):
    def test_empty_input_yields_zero_stats(self):
        stats = compute_stats([], days=14)
        self.assertEqual(stats.total, 0)
        self.assertEqual(stats.success, 0)
        self.assertEqual(stats.success_rate, 0.0)
        self.assertEqual(stats.top_series, [])
        self.assertEqual(stats.top_rarities, [])
        self.assertEqual(len(stats.daily_counts), 14)
        self.assertTrue(all(count == 0 for _, count in stats.daily_counts))

    def test_success_rate(self):
        records = [
            GrabRecord(success=True),
            GrabRecord(success=True),
            GrabRecord(success=True),
            GrabRecord(success=False, error_code="429"),
        ]
        stats = compute_stats(records)
        self.assertEqual(stats.total, 4)
        self.assertEqual(stats.success, 3)
        self.assertAlmostEqual(stats.success_rate, 0.75)

    def test_top_series_excludes_failures_and_nulls(self):
        records = [
            GrabRecord(success=True, series="Vocaloid"),
            GrabRecord(success=True, series="Vocaloid"),
            GrabRecord(success=True, series="Touhou"),
            GrabRecord(success=True, series="Vocaloid"),
            GrabRecord(success=False, series="Vocaloid"),  # failure: ignored
            GrabRecord(success=True, series=None),  # null series: ignored
            GrabRecord(success=True, series="Madoka"),
            GrabRecord(success=True, series="Touhou"),
        ]
        stats = compute_stats(records, top_n=3)
        self.assertEqual(stats.top_series, [("Vocaloid", 3), ("Touhou", 2), ("Madoka", 1)])

    def test_top_rarities_respects_top_n(self):
        records = [GrabRecord(success=True, rarity=r) for r in ["C", "C", "U", "R", "SR"]]
        stats = compute_stats(records, top_n=2)
        self.assertEqual(stats.top_rarities[0], ("C", 2))
        self.assertEqual(len(stats.top_rarities), 2)

    def test_daily_counts_buckets_are_in_chronological_order(self):
        # Pick a fixed "now" so the test is deterministic across timezones.
        now = int(datetime(2026, 5, 14, 12, 0, 0).timestamp())
        one_day = 86_400
        records = [
            GrabRecord(ts=now, success=True),  # today
            GrabRecord(ts=now - one_day, success=True),  # yesterday
            GrabRecord(
                ts=now - one_day, success=False
            ),  # yesterday (failure also counted in daily)
            GrabRecord(ts=now - 5 * one_day, success=True),  # 5 days ago
        ]
        stats = compute_stats(records, days=7, now_ts=now)
        self.assertEqual(len(stats.daily_counts), 7)
        # Oldest first.
        starts = [b for b, _ in stats.daily_counts]
        self.assertEqual(starts, sorted(starts))
        counts = [c for _, c in stats.daily_counts]
        # today=1, yesterday=2, day-5=1, the rest 0.
        self.assertEqual(counts[-1], 1)  # today
        self.assertEqual(counts[-2], 2)  # yesterday
        self.assertEqual(counts[-6], 1)  # 5 days ago
        self.assertEqual(sum(counts), 4)

    def test_daily_counts_drops_grabs_outside_window(self):
        now = int(datetime(2026, 5, 14, 12, 0, 0).timestamp())
        records = [
            GrabRecord(ts=now, success=True),
            GrabRecord(ts=now - 365 * 86_400, success=True),  # ancient, ignored by daily
        ]
        stats = compute_stats(records, days=14, now_ts=now)
        self.assertEqual(sum(c for _, c in stats.daily_counts), 1)
        # But total still reflects every record.
        self.assertEqual(stats.total, 2)


class DistinctBotLabelsTests(_TmpDB):
    def test_empty_when_db_missing(self):
        missing = self.db_path.parent / "absent.db"
        self.assertEqual(distinct_bot_labels(missing), [])

    def test_returns_sorted_unique_labels(self):
        for label in ["bot[2]", "bot[1]", "bot[2]", "bot[3]", "bot[1]"]:
            record_grab(GrabRecord(bot_label=label), path=self.db_path)
        self.assertEqual(
            distinct_bot_labels(self.db_path),
            ["bot[1]", "bot[2]", "bot[3]"],
        )

    def test_empty_when_db_present_but_no_rows(self):
        init_db(self.db_path)
        self.assertEqual(distinct_bot_labels(self.db_path), [])


class ExportCsvTests(unittest.TestCase):
    def _records(self) -> list[GrabRecord]:
        return [
            GrabRecord(
                ts=1_700_000_000,
                bot_label="bot[1]",
                channel_id=42,
                card_name="Hatsune Miku",
                series="Vocaloid",
                rarity="SR",
                hearts=512,
                score=0.873_456,
                success=True,
            ),
            GrabRecord(
                ts=1_700_000_100,
                bot_label="bot[2]",
                success=False,
                error_code="429",
            ),
        ]

    def test_writes_header_and_rows(self):
        out = io.StringIO()
        n = export_csv(self._records(), out)
        self.assertEqual(n, 2)
        out.seek(0)
        reader = csv.DictReader(out)
        rows = list(reader)
        self.assertEqual(reader.fieldnames[0], "ts")
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0]["bot_label"], "bot[1]")
        self.assertEqual(rows[0]["card_name"], "Hatsune Miku")
        self.assertEqual(rows[0]["hearts"], "512")
        self.assertEqual(rows[0]["score"], "0.8735")
        self.assertEqual(rows[0]["success"], "1")
        self.assertEqual(rows[1]["success"], "0")
        self.assertEqual(rows[1]["error_code"], "429")
        # Nullables become empty strings, never the literal "None".
        self.assertEqual(rows[1]["card_name"], "")
        self.assertEqual(rows[1]["hearts"], "")
        self.assertEqual(rows[1]["score"], "")

    def test_iso_ts_column_matches_ts(self):
        out = io.StringIO()
        export_csv(self._records(), out)
        out.seek(0)
        rows = list(csv.DictReader(out))
        self.assertEqual(
            rows[0]["iso_ts"],
            datetime.fromtimestamp(1_700_000_000).isoformat(timespec="seconds"),
        )

    def test_empty_input_writes_header_only(self):
        out = io.StringIO()
        n = export_csv([], out)
        self.assertEqual(n, 0)
        out.seek(0)
        content = out.read()
        self.assertTrue(content.startswith("ts,iso_ts,bot_label"))
        self.assertEqual(len(content.splitlines()), 1)


if __name__ == "__main__":
    unittest.main()

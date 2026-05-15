import asyncio
import threading
import time
import unittest
import unittest.mock
from unittest.mock import MagicMock

from sofi_manager.bot_core import (
    SelfBot,
    _drain_and_close_loop,
    default_config,
    sanitize_config,
)


class SanitizeConfigTests(unittest.TestCase):
    def test_sanitize_config_restores_safe_numeric_ranges(self):
        cfg = default_config()
        cfg.update(
            {
                "interval_min": 0,
                "interval_max": 10,
                "rarity_norm": 0,
                "hearts_norm": 0,
                "drop_channel": "123",
                "all_channels": ["456", "123", "bad", "456"],
            }
        )

        sanitize_config(cfg)

        self.assertGreaterEqual(cfg["interval_min"], 30)
        self.assertGreaterEqual(cfg["rarity_norm"], 1)
        self.assertGreaterEqual(cfg["hearts_norm"], 1)
        self.assertEqual(cfg["drop_channel"], 123)
        self.assertEqual(cfg["all_channels"], [123, 456])

    def test_sanitize_config_preserves_large_discord_ids(self):
        snowflake = 1018468157414985782
        cfg = default_config()
        cfg["drop_channel"] = str(snowflake)
        cfg["all_channels"] = [str(snowflake)]

        sanitize_config(cfg)

        self.assertEqual(cfg["drop_channel"], snowflake)
        self.assertEqual(cfg["all_channels"], [snowflake])

    def test_sanitize_config_parses_string_booleans(self):
        cfg = default_config()
        cfg["night_pause_enabled"] = "false"

        sanitize_config(cfg)

        self.assertFalse(cfg["night_pause_enabled"])


class SelfBotStopTests(unittest.TestCase):
    """The GUI used to freeze ~10s on stop because stop() blocks the calling
    thread up to 2*timeout seconds. These tests pin down the contract so
    future changes can't silently regress that ceiling."""

    def test_stop_is_noop_when_already_stopped(self):
        bot = SelfBot(default_config())
        # Fresh bot is already STATUS_STOPPED.
        started = time.monotonic()
        bot.stop()
        self.assertLess(time.monotonic() - started, 0.1)

    def test_stop_returns_immediately_without_loop(self):
        bot = SelfBot(default_config())
        bot.status = SelfBot.STATUS_RUNNING
        # _loop / _client never got assigned (e.g. start crashed pre-loop).
        started = time.monotonic()
        bot.stop()
        self.assertLess(time.monotonic() - started, 0.1)
        self.assertEqual(bot.status, SelfBot.STATUS_STOPPED)

    def test_stop_respects_timeout_when_close_hangs(self):
        """If _client.close() never resolves, stop(timeout=1) must return
        within ~timeout seconds, not block forever."""
        bot = SelfBot(default_config())
        bot.status = SelfBot.STATUS_RUNNING

        loop_ready = threading.Event()
        loop_box = {}

        def run_loop():
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            loop_box["loop"] = loop
            loop_ready.set()
            loop.run_forever()

        thr = threading.Thread(target=run_loop, daemon=True)
        thr.start()
        loop_ready.wait()
        loop = loop_box["loop"]

        async def never_returns():
            await asyncio.sleep(3600)

        client = MagicMock()
        client.close = never_returns

        bot._loop = loop
        bot._client = client
        # No worker thread → join branch is skipped.

        started = time.monotonic()
        bot.stop(timeout=1)
        elapsed = time.monotonic() - started

        try:
            self.assertLess(elapsed, 2.0, f"stop() blocked {elapsed:.2f}s with hanging close()")
        finally:
            loop.call_soon_threadsafe(loop.stop)
            thr.join(timeout=2)


class DrainAndCloseLoopTests(unittest.TestCase):
    """Pending tasks left in a closed loop trigger asyncio's "Task was
    destroyed but it is pending!" warning on interpreter shutdown."""

    def test_drain_cancels_pending_tasks_and_closes_loop(self):
        loop = asyncio.new_event_loop()

        async def long_running() -> None:
            await asyncio.sleep(3600)

        # Schedule the task on the loop without running it to completion.
        task = loop.create_task(long_running())
        # Step the loop briefly so the task starts and reaches the sleep.
        loop.run_until_complete(asyncio.sleep(0))
        self.assertFalse(task.done())

        _drain_and_close_loop(loop)

        self.assertTrue(loop.is_closed())
        self.assertTrue(task.done())
        self.assertTrue(task.cancelled())

    def test_drain_on_empty_loop_just_closes(self):
        loop = asyncio.new_event_loop()
        _drain_and_close_loop(loop)
        self.assertTrue(loop.is_closed())


class SdWatchdogTests(unittest.TestCase):
    def _run_on_loop(self, coro):
        loop = asyncio.new_event_loop()
        try:
            return loop.run_until_complete(coro)
        finally:
            loop.close()

    def test_watchdog_fires_after_timeout(self):
        bot = SelfBot(default_config())
        bot._sd_watchdog_timeout = 0.05
        channel = MagicMock()
        channel.id = 111
        channel.name = "drop-zone"

        async def scenario():
            bot._arm_sd_watchdog(channel)
            task = bot._sd_watchdogs[111]
            await asyncio.wait_for(task, timeout=1.0)

        self._run_on_loop(scenario())

        levels = [lvl for lvl, _ in list(bot.log_queue.queue)]
        self.assertIn("warn", levels)
        warn_msg = next(text for lvl, text in list(bot.log_queue.queue) if lvl == "warn")
        self.assertIn("drop-zone", warn_msg)
        self.assertNotIn(111, bot._sd_watchdogs)

    def test_watchdog_cancelled_before_timeout_stays_silent(self):
        bot = SelfBot(default_config())
        bot._sd_watchdog_timeout = 1.0  # long; we cancel well before
        channel = MagicMock()
        channel.id = 222
        channel.name = "ch"

        async def scenario():
            bot._arm_sd_watchdog(channel)
            await asyncio.sleep(0.01)
            bot._cancel_sd_watchdog(222)
            await asyncio.sleep(0.05)

        self._run_on_loop(scenario())

        levels = [lvl for lvl, _ in list(bot.log_queue.queue)]
        self.assertNotIn("warn", levels)
        self.assertNotIn(222, bot._sd_watchdogs)

    def test_arm_replaces_previous_watchdog(self):
        bot = SelfBot(default_config())
        bot._sd_watchdog_timeout = 1.0
        channel = MagicMock()
        channel.id = 333
        channel.name = "ch"

        async def scenario():
            bot._arm_sd_watchdog(channel)
            first = bot._sd_watchdogs[333]
            bot._arm_sd_watchdog(channel)
            second = bot._sd_watchdogs[333]
            await asyncio.sleep(0.01)
            self.assertIsNot(first, second)
            self.assertTrue(first.cancelled() or first.done())
            bot._cancel_sd_watchdog(333)

        self._run_on_loop(scenario())


class RecordGrabSafeTests(unittest.TestCase):
    """The bot persists every click attempt into storage, but a DB error
    must never cascade into the grab flow."""

    def _bot(self, name="bot[1]"):
        cfg = default_config()
        cfg["name"] = name
        return SelfBot(cfg)

    def test_calls_storage_with_card_fields(self):
        bot = self._bot("bot[1]")
        card = {"index": 0, "name": "Miku", "series": "Vocaloid", "rarity": 42, "hearts": 256}
        with unittest.mock.patch("sofi_manager.bot_core.storage.record_grab") as rec:
            bot._record_grab_safe(card, channel_id=98765, success=True, error_code=None)
        rec.assert_called_once()
        sent = rec.call_args.args[0]
        self.assertEqual(sent.bot_label, "bot[1]")
        self.assertEqual(sent.channel_id, 98765)
        self.assertEqual(sent.card_name, "Miku")
        self.assertEqual(sent.series, "Vocaloid")
        self.assertEqual(sent.rarity, "42")
        self.assertEqual(sent.hearts, 256)
        self.assertTrue(sent.success)
        self.assertIsNone(sent.error_code)
        self.assertIsInstance(sent.score, float)

    def test_persists_failure_with_error_code(self):
        bot = self._bot()
        card = {"index": 1, "name": "X", "series": "Y", "rarity": 100, "hearts": 50}
        with unittest.mock.patch("sofi_manager.bot_core.storage.record_grab") as rec:
            bot._record_grab_safe(card, channel_id=1, success=False, error_code="40060")
        sent = rec.call_args.args[0]
        self.assertFalse(sent.success)
        self.assertEqual(sent.error_code, "40060")

    def test_swallows_storage_error_and_logs_warning(self):
        bot = self._bot()
        card = {"index": 0, "name": "X", "series": "Y", "rarity": 100, "hearts": 0}
        with unittest.mock.patch(
            "sofi_manager.bot_core.storage.record_grab",
            side_effect=RuntimeError("disk full"),
        ):
            # Must not raise.
            bot._record_grab_safe(card, channel_id=1, success=True, error_code=None)
        levels = [lvl for lvl, _ in list(bot.log_queue.queue)]
        self.assertIn("warn", levels)
        warn_msg = next(text for lvl, text in list(bot.log_queue.queue) if lvl == "warn")
        self.assertIn("DB grabs", warn_msg)
        self.assertIn("RuntimeError", warn_msg)

    def test_handles_card_with_missing_rarity(self):
        # Defensive: a malformed card dict shouldn't crash the hook.
        bot = self._bot()
        with unittest.mock.patch("sofi_manager.bot_core.storage.record_grab") as rec:
            bot._record_grab_safe(
                {"name": "X", "series": "Y", "rarity": None, "hearts": None},
                channel_id=1,
                success=False,
                error_code="EmptyDrop",
            )
        sent = rec.call_args.args[0]
        self.assertIsNone(sent.rarity)
        self.assertIsNone(sent.hearts)


if __name__ == "__main__":
    unittest.main()

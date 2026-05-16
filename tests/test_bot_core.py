import asyncio
import threading
import time
import unittest
import unittest.mock
from datetime import datetime
from unittest.mock import MagicMock

from sofi_manager.bot_core import (
    SOFI_ID,
    SelfBot,
    _as_bool,
    _as_float,
    _as_int,
    _drain_and_close_loop,
    _seconds_until,
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


class CoercionHelperTests(unittest.TestCase):
    """The private `_as_*` helpers absorb arbitrary user input from the GUI
    config form (empty strings, bool-typed numerics, strings that look like
    floats, etc.) without crashing sanitize_config."""

    def test_as_float_returns_default_on_garbage(self):
        # Hits the TypeError/ValueError → default branch.
        self.assertEqual(_as_float("not-a-number", 7.5), 7.5)
        self.assertEqual(_as_float(None, 1.0), 1.0)

    def test_as_int_treats_bool_as_default(self):
        # bool is a subclass of int — explicit guard so True doesn't sneak
        # in as channel id 1.
        self.assertEqual(_as_int(True, 99), 99)
        self.assertEqual(_as_int(False, 99), 99)

    def test_as_int_passes_through_real_ints(self):
        self.assertEqual(_as_int(42, 0), 42)

    def test_as_int_handles_empty_string(self):
        self.assertEqual(_as_int("", 12), 12)
        self.assertEqual(_as_int("   ", 12), 12)

    def test_as_int_parses_numeric_string(self):
        self.assertEqual(_as_int("123", 0), 123)

    def test_as_int_falls_through_to_float_parse(self):
        # "1.5" fails int() but succeeds via float() → 1.
        self.assertEqual(_as_int("1.5", 0), 1)

    def test_as_int_returns_default_on_unparseable(self):
        self.assertEqual(_as_int("nope", 7), 7)
        self.assertEqual(_as_int(object(), 7), 7)

    def test_as_bool_accepts_truthy_strings(self):
        for value in ("1", "true", "TRUE", "yes", "on", "oui"):
            self.assertTrue(_as_bool(value, False), value)

    def test_as_bool_accepts_falsy_strings(self):
        for value in ("0", "false", "no", "off", "non"):
            self.assertFalse(_as_bool(value, True), value)

    def test_as_bool_returns_default_for_unknown_string(self):
        self.assertTrue(_as_bool("peut-être", True))
        self.assertFalse(_as_bool("peut-être", False))

    def test_as_bool_passes_through_real_bool(self):
        self.assertTrue(_as_bool(True))
        self.assertFalse(_as_bool(False))


class SanitizeConfigSwapTests(unittest.TestCase):
    """sanitize_config swaps min/max numeric ranges that are inverted in the
    saved config (e.g. user typed min=600, max=510)."""

    def test_interval_min_max_swap(self):
        cfg = default_config()
        cfg["interval_min"] = 600.0
        cfg["interval_max"] = 510.0
        sanitize_config(cfg)
        self.assertLessEqual(cfg["interval_min"], cfg["interval_max"])

    def test_cooldown_extra_min_max_swap(self):
        cfg = default_config()
        cfg["cooldown_extra_min"] = 200
        cfg["cooldown_extra_max"] = 50
        sanitize_config(cfg)
        self.assertLessEqual(cfg["cooldown_extra_min"], cfg["cooldown_extra_max"])

    def test_pause_duration_min_max_swap(self):
        cfg = default_config()
        cfg["pause_duration_min"] = 30000.0
        cfg["pause_duration_max"] = 100.0
        sanitize_config(cfg)
        self.assertLessEqual(cfg["pause_duration_min"], cfg["pause_duration_max"])


class SecondsUntilTests(unittest.TestCase):
    def test_future_hour_today(self):
        # If the target hour is later than now, _seconds_until returns a
        # positive duration capped at 24h.
        result = _seconds_until(23, 59)
        self.assertGreater(result, 0)
        self.assertLess(result, 24 * 3600 + 1)

    def test_past_hour_wraps_to_tomorrow(self):
        # If we ask for "00:00" and the wall clock is past midnight, the
        # function must add a day rather than returning a negative value.
        now = datetime.now()
        past_hour = (now.hour - 1) % 24
        result = _seconds_until(past_hour, 0)
        self.assertGreater(result, 0)


class DrainAndCloseLoopExceptionTests(unittest.TestCase):
    def test_drain_swallows_exceptions_during_gather(self):
        # Force `asyncio.all_tasks` to raise so we exercise the bare-except
        # branch that just lets us still hit loop.close().
        loop = asyncio.new_event_loop()
        with unittest.mock.patch(
            "sofi_manager.bot_core.asyncio.all_tasks",
            side_effect=RuntimeError("boom"),
        ):
            _drain_and_close_loop(loop)
        self.assertTrue(loop.is_closed())


class StartGuardTests(unittest.TestCase):
    """SelfBot.start() refuses to spin up a thread when the config can't
    possibly produce a working bot — these are user-facing error paths."""

    def test_start_refuses_when_already_running(self):
        bot = SelfBot(default_config())
        bot.status = SelfBot.STATUS_RUNNING
        self.assertFalse(bot.start())

    def test_start_refuses_when_starting(self):
        bot = SelfBot(default_config())
        bot.status = SelfBot.STATUS_STARTING
        self.assertFalse(bot.start())

    def test_start_refuses_without_token(self):
        cfg = default_config()
        cfg["token"] = ""
        cfg["drop_channel"] = 123
        bot = SelfBot(cfg)
        self.assertFalse(bot.start())
        levels = [lvl for lvl, _ in list(bot.log_queue.queue)]
        self.assertIn("error", levels)

    def test_start_refuses_without_drop_channel(self):
        cfg = default_config()
        cfg["token"] = "tok"
        cfg["drop_channel"] = 0
        bot = SelfBot(cfg)
        self.assertFalse(bot.start())
        msgs = [text for _, text in list(bot.log_queue.queue)]
        self.assertTrue(any("Drop channel" in m for m in msgs))

    def test_start_inserts_drop_channel_into_all_channels(self):
        # sanitize_config(__init__) already maintains this invariant; break
        # it manually post-init so start()'s defensive insert (lines 242-245)
        # is exercised — that block guards against config edits after init.
        cfg = default_config()
        cfg["token"] = "tok"
        cfg["drop_channel"] = 12345
        bot = SelfBot(cfg)
        bot.config["all_channels"] = [99999]  # drop_channel removed by hand

        with unittest.mock.patch("sofi_manager.bot_core.threading.Thread") as Th:
            Th.return_value = MagicMock()
            self.assertTrue(bot.start())

        self.assertEqual(bot.config["all_channels"][0], 12345)
        self.assertIn(99999, bot.config["all_channels"])


class SetStatusCallbackTests(unittest.TestCase):
    def test_callback_invoked_with_new_status(self):
        bot = SelfBot(default_config())
        captured: list[str] = []
        bot.status_callback = captured.append
        bot._set_status(SelfBot.STATUS_RUNNING)
        self.assertEqual(captured, [SelfBot.STATUS_RUNNING])
        self.assertEqual(bot.status, SelfBot.STATUS_RUNNING)

    def test_callback_exception_is_swallowed(self):
        # A buggy GUI hook must never tear down the bot thread.
        bot = SelfBot(default_config())

        def boom(_status: str) -> None:
            raise RuntimeError("buggy listener")

        bot.status_callback = boom
        # Must not raise, status must still update.
        bot._set_status(SelfBot.STATUS_RUNNING)
        self.assertEqual(bot.status, SelfBot.STATUS_RUNNING)


class StopErrorPathsTests(unittest.TestCase):
    """Two narrow stop() branches: the inner `except Exception: pass` that
    swallows a faulty client.close(), and the outer `except Exception` that
    logs when asyncio.run_coroutine_threadsafe itself blows up."""

    def _spin_loop(self):
        loop_box: dict[str, asyncio.AbstractEventLoop] = {}
        ready = threading.Event()

        def run():
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            loop_box["loop"] = loop
            ready.set()
            loop.run_forever()

        thr = threading.Thread(target=run, daemon=True)
        thr.start()
        ready.wait()
        return loop_box["loop"], thr

    def test_stop_swallows_client_close_exception(self):
        bot = SelfBot(default_config())
        bot.status = SelfBot.STATUS_RUNNING
        loop, thr = self._spin_loop()

        async def boom() -> None:
            raise RuntimeError("client.close exploded")

        client = MagicMock()
        client.close = boom
        bot._loop = loop
        bot._client = client

        # Must not raise — the inner try/except eats the close error.
        bot.stop(timeout=2)

        loop.call_soon_threadsafe(loop.stop)
        thr.join(timeout=2)
        if not loop.is_closed():
            loop.close()

    def test_stop_logs_when_run_coroutine_threadsafe_raises(self):
        bot = SelfBot(default_config())
        bot.status = SelfBot.STATUS_RUNNING
        loop, thr = self._spin_loop()
        bot._loop = loop
        bot._client = MagicMock()

        with unittest.mock.patch(
            "sofi_manager.bot_core.asyncio.run_coroutine_threadsafe",
            side_effect=RuntimeError("scheduling blew up"),
        ):
            bot.stop(timeout=1)

        msgs = [text for lvl, text in list(bot.log_queue.queue) if lvl == "error"]
        self.assertTrue(any("Erreur arrêt" in m for m in msgs))

        loop.call_soon_threadsafe(loop.stop)
        thr.join(timeout=2)
        if not loop.is_closed():
            loop.close()

    def test_stop_joins_worker_thread_when_alive(self):
        # When the caller is *not* the worker thread and _thread.is_alive(),
        # stop() joins it (line 287). We use a mock Thread so we can assert
        # the join call without standing up a real worker.
        bot = SelfBot(default_config())
        bot.status = SelfBot.STATUS_RUNNING
        loop, thr = self._spin_loop()

        async def close_ok() -> None:
            return None

        client = MagicMock()
        client.close = close_ok
        bot._loop = loop
        bot._client = client

        fake_thread = MagicMock()
        fake_thread.is_alive.return_value = True
        bot._thread = fake_thread

        bot.stop(timeout=1)

        fake_thread.join.assert_called_once_with(timeout=1)

        loop.call_soon_threadsafe(loop.stop)
        thr.join(timeout=2)
        if not loop.is_closed():
            loop.close()


class StopWithCancellableWorkTests(unittest.TestCase):
    """Verify stop() walks _drop_task, _cooldown_task, _night_task and the
    _sd_watchdogs dict, cancelling each before awaiting client.close()."""

    def test_stop_cancels_all_task_handles(self):
        bot = SelfBot(default_config())
        bot.status = SelfBot.STATUS_RUNNING

        loop_box: dict[str, asyncio.AbstractEventLoop] = {}
        ready = threading.Event()

        def run():
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            loop_box["loop"] = loop
            ready.set()
            loop.run_forever()

        thr = threading.Thread(target=run, daemon=True)
        thr.start()
        ready.wait()
        loop = loop_box["loop"]

        # Schedule three long-running coroutines on the worker loop and
        # capture their Task objects. asyncio.run_coroutine_threadsafe
        # returns a concurrent.futures.Future, but the underlying Task is
        # what we need bot.stop() to cancel.
        async def get_tasks():
            async def long() -> None:
                await asyncio.sleep(3600)

            t1 = asyncio.ensure_future(long())
            t2 = asyncio.ensure_future(long())
            t3 = asyncio.ensure_future(long())
            wd = asyncio.ensure_future(long())
            return t1, t2, t3, wd

        fut = asyncio.run_coroutine_threadsafe(get_tasks(), loop)
        drop_t, cd_t, night_t, wd_t = fut.result(timeout=1)

        client = MagicMock()
        # client.close returns a coroutine; the stop() helper awaits it.
        async def close_ok() -> None:
            return None

        client.close = close_ok
        bot._loop = loop
        bot._client = client
        bot._drop_task = drop_t
        bot._cooldown_task = cd_t
        bot._night_task = night_t
        bot._sd_watchdogs = {1: wd_t}

        bot.stop(timeout=2)

        # All four tasks must be done (cancelled).
        for t in (drop_t, cd_t, night_t, wd_t):
            self.assertTrue(t.done(), f"task {t} should be done after stop()")
        self.assertEqual(bot._sd_watchdogs, {})

        loop.call_soon_threadsafe(loop.stop)
        thr.join(timeout=2)
        if not loop.is_closed():
            loop.close()


class AsyncLoopTests(unittest.TestCase):
    """Async helpers (`_drop_loop`, `_handle_cooldown`, `_night_pause_loop`)
    are exercised by patching asyncio.sleep to a fast no-op so the test
    completes in milliseconds, then cancelling the task to break out of the
    while-True body."""

    def _run(self, coro):
        loop = asyncio.new_event_loop()
        try:
            return loop.run_until_complete(coro)
        finally:
            loop.close()

    def test_handle_cooldown_restarts_drop_loop_after_wait(self):
        bot = SelfBot(default_config())
        called: list[bool] = []
        bot._restart_drop_loop = lambda: called.append(True)  # type: ignore[assignment]

        sleep_args: list[float] = []

        async def fake_sleep(seconds: float) -> None:
            sleep_args.append(seconds)

        with (
            unittest.mock.patch("sofi_manager.bot_core.asyncio.sleep", fake_sleep),
            # Force the random extra cooldown to a stable value so the assertion
            # below isn't flaky.
            unittest.mock.patch(
                "sofi_manager.bot_core.random.uniform", return_value=10.0
            ),
        ):
            self._run(bot._handle_cooldown(30))

        self.assertTrue(called, "_handle_cooldown should call _restart_drop_loop")
        self.assertEqual(sleep_args, [40.0])  # 30s wait + 10s extra

    def test_handle_cooldown_swallows_cancellation(self):
        bot = SelfBot(default_config())
        bot._restart_drop_loop = lambda: None  # type: ignore[assignment]

        async def cancelled_sleep(seconds: float) -> None:
            raise asyncio.CancelledError

        with unittest.mock.patch(
            "sofi_manager.bot_core.asyncio.sleep", cancelled_sleep
        ), unittest.mock.patch(
            "sofi_manager.bot_core.random.uniform", return_value=5.0
        ):
            # Must not raise — CancelledError is caught by the helper.
            self._run(bot._handle_cooldown(30))

    def test_restart_drop_loop_cancels_existing_task(self):
        bot = SelfBot(default_config())

        async def scenario():
            old = asyncio.ensure_future(asyncio.sleep(3600))
            bot._drop_task = old
            # Patch _drop_loop to return a quick coroutine so create_task
            # doesn't kick off the real network loop.
            bot._drop_loop = lambda: asyncio.sleep(0)  # type: ignore[assignment]
            bot._restart_drop_loop()
            await asyncio.sleep(0)
            self.assertTrue(old.cancelled() or old.done())
            self.assertIsNotNone(bot._drop_task)
            self.assertIsNot(bot._drop_task, old)
            # Drain the new task to keep the loop clean.
            assert bot._drop_task is not None
            await bot._drop_task

        self._run(scenario())

    def test_drop_loop_logs_on_channel_missing(self):
        bot = SelfBot(default_config())
        bot.config["drop_channel"] = 42
        bot._client = MagicMock()
        bot._client.get_channel.return_value = None

        self._run(bot._drop_loop())

        msgs = [text for _, text in list(bot.log_queue.queue)]
        self.assertTrue(any("DROP_CHANNEL introuvable" in m for m in msgs))

    def test_drop_loop_sends_message_then_cancels(self):
        bot = SelfBot(default_config())
        bot.config["drop_channel"] = 42
        bot.config["interval_min"] = 60.0
        bot.config["interval_max"] = 60.0
        bot._client = MagicMock()
        channel = MagicMock()
        channel.name = "drop-zone"
        channel.id = 42

        async def send_ok(_message: str) -> None:
            return None

        channel.send = send_ok
        bot._client.get_channel.return_value = channel

        # Patch _arm_sd_watchdog so the test doesn't leak a real watchdog.
        bot._arm_sd_watchdog = lambda _ch: None  # type: ignore[assignment]

        async def fake_sleep(_seconds: float) -> None:
            # First iteration's post-send sleep — cancel ourselves to exit.
            raise asyncio.CancelledError

        with unittest.mock.patch(
            "sofi_manager.bot_core.asyncio.sleep", fake_sleep
        ), self.assertRaises(asyncio.CancelledError):
            self._run(bot._drop_loop())

        msgs = [text for _, text in list(bot.log_queue.queue)]
        self.assertTrue(any("Drop envoyé" in m for m in msgs))

    def test_drop_loop_recovers_from_send_error(self):
        bot = SelfBot(default_config())
        bot.config["drop_channel"] = 42
        bot._client = MagicMock()
        channel = MagicMock()
        channel.name = "drop-zone"
        channel.id = 42

        async def send_raises(_message: str) -> None:
            raise RuntimeError("rate limited")

        channel.send = send_raises
        bot._client.get_channel.return_value = channel

        sleeps: list[float] = []

        async def fake_sleep(seconds: float) -> None:
            sleeps.append(seconds)
            if len(sleeps) >= 1:
                # Break out of the while-True on the second iteration.
                raise asyncio.CancelledError

        with unittest.mock.patch(
            "sofi_manager.bot_core.asyncio.sleep", fake_sleep
        ), self.assertRaises(asyncio.CancelledError):
            self._run(bot._drop_loop())

        msgs = [text for _, text in list(bot.log_queue.queue)]
        self.assertTrue(any("Erreur drop" in m for m in msgs))
        self.assertEqual(sleeps[0], 30)  # the fixed 30s recovery wait

    def test_night_pause_loop_full_cycle_then_cancel(self):
        # Drive the loop through start_wait → pause_duration → resume log →
        # _restart_drop_loop, then cancel during the next iteration's first
        # sleep. This pins down lines 447-448 (resume + restart).
        bot = SelfBot(default_config())
        restart_calls: list[bool] = []
        bot._restart_drop_loop = lambda: restart_calls.append(True)  # type: ignore[assignment]

        sleep_count = {"n": 0}

        async def fake_sleep(_seconds: float) -> None:
            sleep_count["n"] += 1
            # 1st sleep: wait until 22h.        → return
            # 2nd sleep: pause duration.       → return
            # 3rd sleep (next iteration):      → cancel
            if sleep_count["n"] >= 3:
                raise asyncio.CancelledError

        with unittest.mock.patch(
            "sofi_manager.bot_core.asyncio.sleep", fake_sleep
        ), unittest.mock.patch(
            "sofi_manager.bot_core._seconds_until", return_value=10.0
        ), unittest.mock.patch(
            "sofi_manager.bot_core.random.randint", return_value=0
        ), unittest.mock.patch(
            "sofi_manager.bot_core.random.uniform", return_value=100.0
        ), self.assertRaises(asyncio.CancelledError):
            self._run(bot._night_pause_loop())

        msgs = [text for _, text in list(bot.log_queue.queue)]
        self.assertTrue(any("Reprise après pause" in m for m in msgs))
        self.assertEqual(len(restart_calls), 1)

    def test_night_pause_loop_logs_and_cancels(self):
        bot = SelfBot(default_config())
        bot.config["pause_duration_min"] = 100.0
        bot.config["pause_duration_max"] = 100.0
        bot._restart_drop_loop = lambda: None  # type: ignore[assignment]

        sleep_count = {"n": 0}

        async def fake_sleep(_seconds: float) -> None:
            sleep_count["n"] += 1
            # Let the first wait return (pretend "we slept until 22:xx"),
            # then cancel during the pause-duration sleep to break out.
            if sleep_count["n"] >= 2:
                raise asyncio.CancelledError

        with (
            unittest.mock.patch("sofi_manager.bot_core.asyncio.sleep", fake_sleep),
            # _seconds_until returns a 24h+ value on a freshly-faked clock
            # only rarely; pin the wait to a small positive number.
            unittest.mock.patch(
                "sofi_manager.bot_core._seconds_until", return_value=10.0
            ),
            unittest.mock.patch(
                "sofi_manager.bot_core.random.randint", return_value=0
            ),
            unittest.mock.patch(
                "sofi_manager.bot_core.random.uniform", return_value=100.0
            ),
            self.assertRaises(asyncio.CancelledError),
        ):
            self._run(bot._night_pause_loop())

        msgs = [text for _, text in list(bot.log_queue.queue)]
        self.assertTrue(any("Pause nocturne prévue" in m for m in msgs))
        self.assertTrue(any("Pause nocturne :" in m for m in msgs))

    def test_night_pause_loop_clamps_24h_overflow(self):
        # When the computed wait would exceed 24h (because _seconds_until
        # already added a day and we sum more on top), the helper subtracts
        # 24h to stay within a single day's worth of waiting. Force that
        # branch by returning a value > 24h.
        bot = SelfBot(default_config())
        bot._restart_drop_loop = lambda: None  # type: ignore[assignment]

        async def fake_sleep(_seconds: float) -> None:
            raise asyncio.CancelledError

        with unittest.mock.patch(
            "sofi_manager.bot_core.asyncio.sleep", fake_sleep
        ), unittest.mock.patch(
            "sofi_manager.bot_core._seconds_until",
            return_value=25 * 3600.0,
        ), unittest.mock.patch(
            "sofi_manager.bot_core.random.randint", return_value=0
        ), self.assertRaises(asyncio.CancelledError):
            self._run(bot._night_pause_loop())

        msgs = [text for _, text in list(bot.log_queue.queue)]
        # Sanity: even with the clamp, we still announced the night pause.
        self.assertTrue(any("Pause nocturne prévue" in m for m in msgs))

    def test_night_pause_cancels_active_tasks_before_pause(self):
        # Use MagicMock-backed task stand-ins so we can directly assert
        # that .cancel() was invoked without needing the cancellation to
        # actually propagate through the event loop (asyncio.sleep is
        # mocked, so a real Task can't be scheduled past .cancel()).
        bot = SelfBot(default_config())
        bot._restart_drop_loop = lambda: None  # type: ignore[assignment]

        drop = MagicMock()
        drop.done.return_value = False
        cooldown = MagicMock()
        cooldown.done.return_value = False
        bot._drop_task = drop
        bot._cooldown_task = cooldown

        sleep_count = {"n": 0}

        async def fake_sleep(_seconds: float) -> None:
            sleep_count["n"] += 1
            if sleep_count["n"] == 1:
                return
            raise asyncio.CancelledError

        with unittest.mock.patch(
            "sofi_manager.bot_core.asyncio.sleep", fake_sleep
        ), unittest.mock.patch(
            "sofi_manager.bot_core._seconds_until", return_value=10.0
        ), unittest.mock.patch(
            "sofi_manager.bot_core.random.randint", return_value=0
        ), unittest.mock.patch(
            "sofi_manager.bot_core.random.uniform", return_value=100.0
        ), self.assertRaises(asyncio.CancelledError):
            self._run(bot._night_pause_loop())

        drop.cancel.assert_called_once()
        cooldown.cancel.assert_called_once()


class SetupEventsTests(unittest.TestCase):
    """`_setup_events` wires two discord.Client callbacks. We capture the
    registered coroutines and drive them by hand so the on_ready body
    (channel listing, status flip, drop-loop start) is exercised without a
    real Discord connection."""

    def _make_bot_with_fake_client(self):
        cfg = default_config()
        cfg["all_channels"] = [111, 222]
        cfg["drop_channel"] = 111
        cfg["night_pause_enabled"] = False
        bot = SelfBot(cfg)

        registered: dict[str, object] = {}

        class FakeClient:
            user = MagicMock()

            def event(self, coro):
                registered[coro.__name__] = coro
                return coro

            def get_channel(self, cid):
                if cid == 111:
                    ch = MagicMock()
                    ch.name = "drop-zone"
                    return ch
                return None

        bot._client = FakeClient()  # type: ignore[assignment]
        return bot, registered

    def test_setup_events_registers_on_ready_and_on_message(self):
        bot, registered = self._make_bot_with_fake_client()
        bot._setup_events()
        self.assertIn("on_ready", registered)
        self.assertIn("on_message", registered)

    def test_on_ready_logs_channels_and_starts_drop_loop(self):
        bot, registered = self._make_bot_with_fake_client()
        # Make _restart_drop_loop a no-op so we don't need an event loop.
        bot._restart_drop_loop = lambda: None  # type: ignore[assignment]
        bot._setup_events()

        on_ready = registered["on_ready"]

        async def driver():
            await on_ready()  # type: ignore[misc]

        loop = asyncio.new_event_loop()
        try:
            loop.run_until_complete(driver())
        finally:
            loop.close()

        self.assertEqual(bot.status, SelfBot.STATUS_RUNNING)
        msgs = [text for _, text in list(bot.log_queue.queue)]
        self.assertTrue(any("Connecté" in m for m in msgs))
        self.assertTrue(any("Salon écouté" in m for m in msgs))
        # 222 has no matching channel in our fake client → warn branch.
        self.assertTrue(any("Salon introuvable" in m for m in msgs))

    def test_on_ready_starts_night_pause_when_enabled(self):
        bot, registered = self._make_bot_with_fake_client()
        bot.config["night_pause_enabled"] = True
        bot._restart_drop_loop = lambda: None  # type: ignore[assignment]
        # Make _night_pause_loop a quick no-op coroutine.
        bot._night_pause_loop = lambda: asyncio.sleep(0)  # type: ignore[assignment]
        bot._setup_events()

        loop = asyncio.new_event_loop()
        try:
            loop.run_until_complete(registered["on_ready"]())  # type: ignore[misc]
            # Drain the scheduled night task.
            loop.run_until_complete(asyncio.sleep(0))
        finally:
            loop.close()

        self.assertIsNotNone(bot._night_task)

    def test_on_message_delegates_to_internal_handler(self):
        bot, registered = self._make_bot_with_fake_client()
        bot._setup_events()

        received: list[object] = []

        async def fake_handler(msg):  # type: ignore[no-untyped-def]
            received.append(msg)

        bot._on_message = fake_handler  # type: ignore[assignment]

        sentinel = MagicMock()
        loop = asyncio.new_event_loop()
        try:
            loop.run_until_complete(registered["on_message"](sentinel))  # type: ignore[misc]
        finally:
            loop.close()

        self.assertEqual(received, [sentinel])


class ConstantsTests(unittest.TestCase):
    def test_sofi_id_matches_default_config(self):
        # Guard against accidental drift between the module-level constant
        # and the default config value.
        self.assertEqual(default_config()["sofi_id"], SOFI_ID)


if __name__ == "__main__":
    unittest.main()

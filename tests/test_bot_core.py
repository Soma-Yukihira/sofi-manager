import asyncio
import threading
import time
import unittest
from unittest.mock import MagicMock

from bot_core import (
    SelfBot,
    choose_card,
    default_config,
    iter_component_children,
    sanitize_config,
    score_card,
)


class FakeChild:
    def __init__(self, label):
        self.label = label


class FakeRow:
    def __init__(self, children):
        self.children = children


class BotCoreTests(unittest.TestCase):
    def test_score_card_survives_zero_norms(self):
        cfg = default_config()
        cfg["rarity_norm"] = 0
        cfg["hearts_norm"] = 0

        score = score_card({"rarity": 10, "hearts": 20}, cfg)

        self.assertIsInstance(score, float)

    def test_sanitize_config_restores_safe_numeric_ranges(self):
        cfg = default_config()
        cfg.update({
            "interval_min": 0,
            "interval_max": 10,
            "rarity_norm": 0,
            "hearts_norm": 0,
            "drop_channel": "123",
            "all_channels": ["456", "123", "bad", "456"],
        })

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

    def test_choose_card_uses_best_personal_wishlist_match(self):
        cfg = default_config()
        cfg["wishlist"] = ["A", "B"]
        cards = [
            {"index": 0, "name": "A", "series": "S", "rarity": 400, "hearts": 400},
            {"index": 1, "name": "B", "series": "S", "rarity": 100, "hearts": 430},
        ]

        selected = choose_card(cards, cfg, lambda *_: None)

        self.assertEqual(selected, 1)

    def test_component_children_are_flattened_across_rows(self):
        rows = [
            FakeRow([FakeChild("1"), FakeChild("2")]),
            FakeRow([FakeChild("3")]),
        ]

        labels = [child.label for child in iter_component_children(rows)]

        self.assertEqual(labels, ["1", "2", "3"])


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
            self.assertLess(
                elapsed, 2.0,
                f"stop() blocked {elapsed:.2f}s with hanging close()"
            )
        finally:
            loop.call_soon_threadsafe(loop.stop)
            thr.join(timeout=2)


if __name__ == "__main__":
    unittest.main()

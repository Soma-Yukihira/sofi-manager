"""Coverage for SelfBot._on_message — the longest coroutine in bot_core.

The handler routes every Discord message through six branches: wrong
author → drop, wrong channel → drop, cooldown → schedule wait, drop
trigger but not for us → log, drop for us → parse cards, fetch components,
click. We drive each branch by patching the parsing helpers at the
bot_core module level rather than crafting valid SOFI text, so the test
matrix stays focused on _on_message itself.
"""

from __future__ import annotations

import asyncio
import unittest.mock
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import discord
import pytest

from sofi_manager import bot_core
from sofi_manager.bot_core import SOFI_ID, SelfBot, default_config

# =====================================================================
# Helpers
# =====================================================================


def _run(coro: Any) -> Any:
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


def _make_bot(*, our_id: int = 99999, channel_id: int = 111) -> SelfBot:
    cfg = default_config()
    cfg["drop_channel"] = channel_id
    cfg["all_channels"] = [channel_id]
    bot = SelfBot(cfg)
    client = MagicMock()
    client.user = MagicMock()
    client.user.id = our_id
    # Default: we are NOT mentioned. Tests override per case.
    client.user.mentioned_in = MagicMock(return_value=False)
    bot._client = client
    return bot


def _make_message(
    *,
    author_id: int = SOFI_ID,
    channel_id: int = 111,
    content: str = "",
    message_id: int = 1234,
) -> MagicMock:
    msg = MagicMock(spec=discord.Message)
    msg.author = MagicMock()
    msg.author.id = author_id
    msg.channel = MagicMock()
    msg.channel.id = channel_id
    msg.channel.name = "drop-zone"
    msg.id = message_id
    msg.content = content
    msg.embeds = []
    msg.components = []
    return msg


class _FakeHTTP(discord.HTTPException):
    """A discord.HTTPException stand-in that bypasses the real __init__
    (which requires a response object) but still satisfies the
    `except discord.HTTPException` clause in _on_message."""

    def __init__(self, code: int = 40060, status: int = 400, text: str = "boom") -> None:
        Exception.__init__(self, text)
        self.code = code
        self.status = status
        self.text = text


def _patch_parsing(
    monkeypatch: pytest.MonkeyPatch,
    *,
    text: str = "",
    is_cooldown: bool = False,
    cooldown_seconds: int = 0,
    is_drop: bool = False,
    drop_recipients: str = "",
    cards: list[dict[str, Any]] | None = None,
) -> None:
    """One-shot patching of every parser the handler delegates to."""
    monkeypatch.setattr(bot_core, "extract_full_text", lambda _msg: text)
    monkeypatch.setattr(bot_core, "is_cooldown_message", lambda _t: is_cooldown)
    monkeypatch.setattr(bot_core, "parse_cooldown_seconds", lambda _t: cooldown_seconds)
    monkeypatch.setattr(bot_core, "is_drop_trigger", lambda _t: is_drop)
    monkeypatch.setattr(bot_core, "format_drop_recipients", lambda _m, _i: drop_recipients)
    monkeypatch.setattr(bot_core, "smart_parse_cards", lambda _t: list(cards or []))


# =====================================================================
# Early-return guards
# =====================================================================


class TestEarlyReturns:
    def test_ignores_non_sofi_author(self) -> None:
        bot = _make_bot()
        msg = _make_message(author_id=12345)  # not SOFI

        _run(bot._on_message(msg))

        # No logs emitted because we bail before extract_full_text.
        assert list(bot.log_queue.queue) == []

    def test_ignores_message_in_unlistened_channel(self) -> None:
        bot = _make_bot(channel_id=111)
        msg = _make_message(channel_id=999)  # not in all_channels

        _run(bot._on_message(msg))

        assert list(bot.log_queue.queue) == []

    def test_logs_sofi_preview_for_listened_channel(self, monkeypatch: pytest.MonkeyPatch) -> None:
        bot = _make_bot()
        _patch_parsing(monkeypatch, text="some sofi prose")
        msg = _make_message()

        _run(bot._on_message(msg))

        msgs = [text for _, text in list(bot.log_queue.queue)]
        assert any("📥 SOFI:" in m and "some sofi prose" in m for m in msgs)

    def test_empty_message_logs_vide(self, monkeypatch: pytest.MonkeyPatch) -> None:
        bot = _make_bot()
        _patch_parsing(monkeypatch, text="")
        msg = _make_message()

        _run(bot._on_message(msg))

        msgs = [t for _, t in list(bot.log_queue.queue)]
        assert any("(vide)" in m for m in msgs)


# =====================================================================
# Cooldown branch
# =====================================================================


class TestCooldown:
    def test_cooldown_message_cancels_drop_and_schedules_wait(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        bot = _make_bot()
        _patch_parsing(
            monkeypatch,
            text="cooldown bla",
            is_cooldown=True,
            cooldown_seconds=42,
        )

        drop = MagicMock()
        drop.done.return_value = False
        old_cd = MagicMock()
        old_cd.done.return_value = False
        bot._drop_task = drop
        bot._cooldown_task = old_cd

        # Replace _handle_cooldown with a no-op coroutine so create_task
        # gets a coroutine it can legitimately schedule — no "coroutine
        # was never awaited" warning at GC time.
        async def fake_handle_cooldown(_wait: int) -> None:
            return None

        bot._handle_cooldown = fake_handle_cooldown  # type: ignore[assignment]

        async def driver() -> None:
            created = MagicMock()
            with unittest.mock.patch(
                "sofi_manager.bot_core.asyncio.create_task",
                return_value=created,
            ) as ct:
                await bot._on_message(_make_message())
                ct.assert_called_once()
                # The coroutine handed to create_task must be the one we
                # patched in (so we can close it cleanly here).
                coro = ct.call_args.args[0]
                coro.close()
            assert bot._cooldown_task is created

        _run(driver())

        drop.cancel.assert_called_once()
        old_cd.cancel.assert_called_once()
        msgs = [t for _, t in list(bot.log_queue.queue)]
        assert any("drop_loop annulé" in m for m in msgs)
        assert any("Cooldown précédent remplacé" in m for m in msgs)

    def test_cooldown_with_zero_seconds_is_noop(self, monkeypatch: pytest.MonkeyPatch) -> None:
        # parse_cooldown_seconds returned 0 → handler returns without
        # creating a cooldown task.
        bot = _make_bot()
        _patch_parsing(
            monkeypatch,
            text="cooldown bla",
            is_cooldown=True,
            cooldown_seconds=0,
        )

        with unittest.mock.patch("sofi_manager.bot_core.asyncio.create_task") as ct:
            _run(bot._on_message(_make_message()))
            ct.assert_not_called()


# =====================================================================
# Drop-trigger branch
# =====================================================================


class TestDropNotForUs:
    def test_drop_with_other_recipients_logs_their_names(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        bot = _make_bot()
        _patch_parsing(
            monkeypatch,
            text="drop drop drop",
            is_drop=True,
            drop_recipients="@Alice, @Bob",
        )

        _run(bot._on_message(_make_message()))

        msgs = [t for _, t in list(bot.log_queue.queue)]
        assert any("Drop pour @Alice, @Bob" in m for m in msgs)

    def test_drop_with_no_recipients_logs_ignore(self, monkeypatch: pytest.MonkeyPatch) -> None:
        bot = _make_bot()
        _patch_parsing(
            monkeypatch,
            text="drop drop drop",
            is_drop=True,
            drop_recipients="",
        )

        _run(bot._on_message(_make_message()))

        msgs = [t for _, t in list(bot.log_queue.queue)]
        assert any("Drop ignoré" in m for m in msgs)

    def test_mention_via_raw_content_cancels_watchdog(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # client.user.mentioned_in returns False, but the raw content has
        # the <@id> token — handler must still treat it as a mention.
        bot = _make_bot(our_id=42)
        _patch_parsing(monkeypatch, text="hi <@42>", is_drop=False)
        msg = _make_message(content="hi <@42>")

        cancel_calls: list[int] = []
        bot._cancel_sd_watchdog = cancel_calls.append  # type: ignore[assignment]

        _run(bot._on_message(msg))
        assert cancel_calls == [msg.channel.id]


# =====================================================================
# Drop for us — full pipeline
# =====================================================================


def _make_button(label: str, *, disabled: bool = False, click: Any = None) -> MagicMock:
    btn = MagicMock()
    btn.label = label
    btn.disabled = disabled
    if click is not None:
        btn.click = click
    else:

        async def _ok() -> None:
            return None

        btn.click = _ok
    return btn


def _make_components(buttons: list[MagicMock]) -> list[Any]:
    # iter_component_children is patched to return our buttons directly,
    # so we just need the message.components to be truthy.
    return [object()]


class TestDropForUs:
    def _drop_setup(self, monkeypatch: pytest.MonkeyPatch) -> SelfBot:
        bot = _make_bot()
        # We ARE mentioned (so we proceed past the recipient check).
        bot._client.user.mentioned_in = MagicMock(return_value=True)
        _patch_parsing(
            monkeypatch,
            text="🎴 drop drop drop",
            is_drop=True,
            cards=[
                {"index": 0, "name": "Miku", "series": "Vocaloid", "rarity": 1000, "hearts": 0},
                {"index": 1, "name": "Luka", "series": "Vocaloid", "rarity": 500, "hearts": 0},
                {"index": 2, "name": "Rin", "series": "Vocaloid", "rarity": 750, "hearts": 0},
            ],
        )
        # Stub the parsers/sleepers used during the click pipeline.
        monkeypatch.setattr(bot_core, "parse_button_hearts", lambda label: int(label))
        monkeypatch.setattr(bot_core, "choose_card", lambda _c, _cfg, _log: 1)
        monkeypatch.setattr(bot_core.asyncio, "sleep", AsyncMock())
        monkeypatch.setattr(bot_core.random, "uniform", lambda _a, _b: 0)
        # Don't actually touch SQLite.
        monkeypatch.setattr(bot_core.storage, "record_grab", MagicMock())
        return bot

    def test_no_cards_parsed_logs_error(self, monkeypatch: pytest.MonkeyPatch) -> None:
        bot = _make_bot()
        bot._client.user.mentioned_in = MagicMock(return_value=True)
        _patch_parsing(
            monkeypatch,
            text="drop drop",
            is_drop=True,
            cards=[],  # parsing returned nothing
        )
        _run(bot._on_message(_make_message()))

        msgs = [t for lvl, t in list(bot.log_queue.queue) if lvl == "error"]
        assert any("Aucune carte parsée" in m for m in msgs)

    def test_fetch_message_raises_then_buttons_never_appear(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        bot = self._drop_setup(monkeypatch)
        msg = _make_message()

        async def boom(_id: int) -> Any:
            raise RuntimeError("network glitch")

        msg.channel.fetch_message = boom

        _run(bot._on_message(msg))

        msgs = [t for lvl, t in list(bot.log_queue.queue) if lvl == "error"]
        assert any("Erreur fetch" in m for m in msgs)
        assert any("Boutons toujours disabled" in m for m in msgs)

    def test_buttons_remain_disabled_logs_failure(self, monkeypatch: pytest.MonkeyPatch) -> None:
        bot = self._drop_setup(monkeypatch)
        msg = _make_message()
        fetched = MagicMock()
        fetched.components = _make_components([])  # truthy
        msg.channel.fetch_message = AsyncMock(return_value=fetched)
        # Return a fixed pair of disabled buttons every retry.
        disabled_btns = [_make_button("1", disabled=True), _make_button("2", disabled=True)]
        monkeypatch.setattr(bot_core, "iter_component_children", lambda _c: list(disabled_btns))

        _run(bot._on_message(msg))

        msgs = [t for lvl, t in list(bot.log_queue.queue) if lvl == "error"]
        assert any("Boutons toujours disabled" in m for m in msgs)

    def test_fetch_returns_no_components_loops_until_failure(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        bot = self._drop_setup(monkeypatch)
        msg = _make_message()
        # target_message.components is falsy → handler continues retrying.
        fetched = MagicMock()
        fetched.components = []
        msg.channel.fetch_message = AsyncMock(return_value=fetched)

        _run(bot._on_message(msg))

        msgs = [t for lvl, t in list(bot.log_queue.queue) if lvl == "error"]
        assert any("Boutons toujours disabled" in m for m in msgs)

    def test_click_success_records_grab(self, monkeypatch: pytest.MonkeyPatch) -> None:
        bot = self._drop_setup(monkeypatch)
        msg = _make_message()
        fetched = MagicMock()
        fetched.components = _make_components([])
        msg.channel.fetch_message = AsyncMock(return_value=fetched)

        clicked = MagicMock()
        clicked.click = AsyncMock(return_value=None)
        clicked.label = "5"
        clicked.disabled = False

        btns = [
            _make_button("3"),
            clicked,
            _make_button("7"),
        ]
        monkeypatch.setattr(bot_core, "iter_component_children", lambda _c: list(btns))

        _run(bot._on_message(msg))

        clicked.click.assert_awaited_once()
        msgs = [t for lvl, t in list(bot.log_queue.queue) if lvl == "success"]
        assert any("Cliqué bouton 2" in m for m in msgs)
        # storage.record_grab called with success=True
        bot_core.storage.record_grab.assert_called_once()  # type: ignore[attr-defined]
        sent = bot_core.storage.record_grab.call_args.args[0]  # type: ignore[attr-defined]
        assert sent.success is True
        assert sent.error_code is None

    def test_click_http_exception_records_error_code(self, monkeypatch: pytest.MonkeyPatch) -> None:
        bot = self._drop_setup(monkeypatch)
        msg = _make_message()
        fetched = MagicMock()
        fetched.components = _make_components([])
        msg.channel.fetch_message = AsyncMock(return_value=fetched)

        async def click_raises() -> None:
            raise _FakeHTTP(code=40060, status=400, text="already acked")

        btns = [
            _make_button("1"),
            _make_button("2", click=click_raises),
            _make_button("3"),
        ]
        monkeypatch.setattr(bot_core, "iter_component_children", lambda _c: list(btns))

        _run(bot._on_message(msg))

        msgs = [t for lvl, t in list(bot.log_queue.queue) if lvl == "error"]
        assert any("Erreur clic HTTP" in m and "40060" in m for m in msgs)
        sent = bot_core.storage.record_grab.call_args.args[0]  # type: ignore[attr-defined]
        assert sent.success is False
        assert sent.error_code == "40060"

    def test_click_generic_exception_records_type_name(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        bot = self._drop_setup(monkeypatch)
        msg = _make_message()
        fetched = MagicMock()
        fetched.components = _make_components([])
        msg.channel.fetch_message = AsyncMock(return_value=fetched)

        async def click_raises() -> None:
            raise ValueError("network derp")

        btns = [
            _make_button("1"),
            _make_button("2", click=click_raises),
            _make_button("3"),
        ]
        monkeypatch.setattr(bot_core, "iter_component_children", lambda _c: list(btns))

        _run(bot._on_message(msg))

        sent = bot_core.storage.record_grab.call_args.args[0]  # type: ignore[attr-defined]
        assert sent.success is False
        assert sent.error_code == "ValueError"

    def test_button_index_out_of_range_logs_error(self, monkeypatch: pytest.MonkeyPatch) -> None:
        bot = self._drop_setup(monkeypatch)
        # Second choose_card pick is 5, but we only return 2 buttons.
        monkeypatch.setattr(bot_core, "choose_card", lambda _c, _cfg, _log: 5)
        msg = _make_message()
        fetched = MagicMock()
        fetched.components = _make_components([])
        msg.channel.fetch_message = AsyncMock(return_value=fetched)
        monkeypatch.setattr(
            bot_core,
            "iter_component_children",
            lambda _c: [_make_button("1"), _make_button("2")],
        )

        _run(bot._on_message(msg))

        msgs = [t for lvl, t in list(bot.log_queue.queue) if lvl == "error"]
        assert any("Bouton 6 introuvable" in m for m in msgs)
        bot_core.storage.record_grab.assert_not_called()  # type: ignore[attr-defined]

    def test_chosen_button_becomes_disabled_logs_error(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # The retry loop accepts buttons when none are disabled, but the
        # chosen one can still flip disabled between detection and click
        # (no real concurrency in test — we force it via the same mock).
        bot = self._drop_setup(monkeypatch)
        msg = _make_message()
        fetched = MagicMock()
        fetched.components = _make_components([])
        msg.channel.fetch_message = AsyncMock(return_value=fetched)

        # Track call count: first iter_component_children call (during
        # retry loop) returns all-enabled buttons; second (after the loop)
        # would be irrelevant. The handler reuses the heart_buttons list,
        # so flip disabled on the chosen one in-place after construction.
        chosen = _make_button("2", disabled=False)
        btns = [_make_button("1"), chosen, _make_button("3")]
        monkeypatch.setattr(bot_core, "iter_component_children", lambda _c: list(btns))

        # Flip the chosen button's `disabled` flag mid-flight, *after*
        # the retry loop has accepted the all-enabled state but before
        # the final click — driven by a parse_button_hearts side effect.
        seen = {"n": 0}

        def fake_phearts(label: str) -> int | None:
            seen["n"] += 1
            # 3 buttons * 1 retry = 3 calls during retry-accept check,
            # then 3 more during the per-card label assignment. After
            # those we know we've left the retry loop — flip disabled.
            if seen["n"] >= 6:
                chosen.disabled = True
            return int(label)

        monkeypatch.setattr(bot_core, "parse_button_hearts", fake_phearts)

        _run(bot._on_message(msg))

        msgs = [t for lvl, t in list(bot.log_queue.queue) if lvl == "error"]
        assert any("encore désactivé" in m for m in msgs)
        bot_core.storage.record_grab.assert_not_called()  # type: ignore[attr-defined]

"""Property-based tests for parsing.py.

Complement the example-based tests in test_parsing.py by asserting
invariants that should hold for arbitrary inputs:

* round-tripping integers / cooldowns through their serialised form
  recovers the original value,
* parsers never raise on adversarial input — they return ``None`` or
  an empty list instead.

The ``infk`` OverflowError bug in ``parse_button_hearts`` was found by
the float-strategy test below.
"""

from __future__ import annotations

from hypothesis import given
from hypothesis import strategies as st

from parsing import (
    is_cooldown_message,
    is_drop_trigger,
    parse_button_hearts,
    parse_cooldown_seconds,
    smart_parse_cards,
)

# parse_button_hearts ---------------------------------------------------


@given(st.integers(min_value=0, max_value=2**31 - 1))
def test_button_hearts_plain_int_roundtrip(n: int) -> None:
    assert parse_button_hearts(str(n)) == n


@given(st.integers(min_value=0, max_value=10**12))
def test_button_hearts_k_suffix_int_roundtrip(n: int) -> None:
    assert parse_button_hearts(f"{n}k") == n * 1000


@given(st.integers(min_value=0, max_value=10**9))
def test_button_hearts_k_case_insensitive(n: int) -> None:
    assert parse_button_hearts(f"{n}k") == parse_button_hearts(f"{n}K")


@given(st.text())
def test_button_hearts_never_raises_on_text(label: str) -> None:
    result = parse_button_hearts(label)
    assert result is None or isinstance(result, int)


@given(st.floats(allow_nan=True, allow_infinity=True))
def test_button_hearts_never_raises_on_float_strings(f: float) -> None:
    # Regression: parse_button_hearts('infk') used to raise OverflowError.
    result = parse_button_hearts(f"{f}k")
    assert result is None or isinstance(result, int)


# parse_cooldown_seconds ------------------------------------------------


@given(
    st.integers(min_value=0, max_value=10**6),
    st.integers(min_value=0, max_value=10**6),
)
def test_cooldown_fr_roundtrip(minutes: int, seconds: int) -> None:
    text = f"prêt dans {minutes}m {seconds}s"
    assert parse_cooldown_seconds(text) == minutes * 60 + seconds


@given(
    st.integers(min_value=0, max_value=10**6),
    st.integers(min_value=0, max_value=10**6),
)
def test_cooldown_en_roundtrip(minutes: int, seconds: int) -> None:
    text = f"ready in {minutes}m {seconds}s"
    assert parse_cooldown_seconds(text) == minutes * 60 + seconds


@given(st.integers(min_value=0, max_value=10**6))
def test_cooldown_seconds_only_roundtrip(seconds: int) -> None:
    assert parse_cooldown_seconds(f"prêt dans {seconds}s") == seconds


@given(st.text())
def test_cooldown_never_raises(text: str) -> None:
    result = parse_cooldown_seconds(text)
    assert result is None or isinstance(result, int)


# smart_parse_cards -----------------------------------------------------


@given(st.text())
def test_smart_parse_cards_never_raises(content: str) -> None:
    cards = smart_parse_cards(content)
    assert isinstance(cards, list)
    for i, card in enumerate(cards):
        assert {"index", "name", "series", "rarity", "hearts"} <= card.keys()
        assert isinstance(card["rarity"], int)
        assert isinstance(card["hearts"], int)
        assert card["index"] == i


# trigger detection -----------------------------------------------------


@given(st.text())
def test_is_drop_trigger_returns_bool(text: str) -> None:
    assert isinstance(is_drop_trigger(text), bool)


@given(st.text())
def test_is_cooldown_message_returns_bool(text: str) -> None:
    assert isinstance(is_cooldown_message(text), bool)

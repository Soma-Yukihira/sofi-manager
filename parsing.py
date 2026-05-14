"""
parsing.py
SOFI message parsing — pure helpers, no Discord client, no asyncio.

Everything here takes a string (or a discord Message-like object that just
has the attributes the helper touches) and returns plain Python data, so
each function is trivially unit-testable in isolation.
"""

from __future__ import annotations

import re
from collections.abc import Iterator
from typing import Any

# Multilingual SOFI triggers (FR + EN).
_DROP_TRIGGER_RE = re.compile(
    r"drop\s+des\s+cartes|dropping\s+cards?|drops?\s+cards?",
    re.IGNORECASE,
)
_COOLDOWN_RE = re.compile(
    r"pr[êe]t\s+dans|ready\s+in",
    re.IGNORECASE,
)


def parse_cards(content: str) -> list[dict[str, Any]]:
    cards: list[dict[str, Any]] = []
    pattern = r'G•`?\s*(\d+)\s*`?\s*\|\s*(.+?)\s*•\s*(.+?)(?=\s*`\d|$)'
    for i, m in enumerate(re.finditer(pattern, content)):
        cards.append({
            "index": i,
            "name": m.group(2).strip(),
            "series": m.group(3).strip(),
            "rarity": int(m.group(1)),
            "hearts": 0,
        })
    return cards


def parse_cards_with_hearts(content: str) -> list[dict[str, Any]]:
    cards: list[dict[str, Any]] = []
    pattern = r'G•`?\s*(\d+)\s*`?\s*\|\s*(.+?)\s*•\s*(.+?)\s*•\s*(\d+)'
    for i, m in enumerate(re.finditer(pattern, content)):
        cards.append({
            "index": i,
            "name": m.group(2).strip(),
            "series": m.group(3).strip(),
            "rarity": int(m.group(1)),
            "hearts": int(m.group(4)),
        })
    return cards


def smart_parse_cards(content: str) -> list[dict[str, Any]]:
    return parse_cards_with_hearts(content) or parse_cards(content)


def parse_button_hearts(label: Any) -> int | None:
    """'43' → 43, '1.2k' → 1200, '1k' → 1000. None si invalide."""
    label = str(label).strip().lower()
    if label.endswith("k"):
        try:
            return int(float(label[:-1]) * 1000)
        except (ValueError, OverflowError):
            # OverflowError covers 'infk' and the like — float() accepts 'inf'
            # but int(inf) blows up.
            return None
    try:
        return int(label)
    except ValueError:
        return None


def parse_cooldown_seconds(content: str) -> int | None:
    m = re.search(
        r'(?:pr[êe]t\s+dans|ready\s+in)\s*:?\s*(?:(\d+)\s*m\s*)?(\d+)\s*s',
        content, re.IGNORECASE,
    )
    if m:
        minutes = int(m.group(1)) if m.group(1) else 0
        seconds = int(m.group(2))
        return minutes * 60 + seconds
    return None


def extract_full_text(message: Any) -> str:
    """Combine message.content + tous les embeds en un seul string.
    SOFI met parfois les cartes dans un embed plutôt qu'en texte brut."""
    parts = [message.content or ""]
    for emb in message.embeds:
        if emb.title:
            parts.append(emb.title)
        if emb.description:
            parts.append(emb.description)
        author = getattr(emb, "author", None)
        if author and getattr(author, "name", None):
            parts.append(author.name)
        for field in getattr(emb, "fields", []):
            if field.name:
                parts.append(field.name)
            if field.value:
                parts.append(field.value)
        footer = getattr(emb, "footer", None)
        if footer and getattr(footer, "text", None):
            parts.append(footer.text)
    return "\n".join(p for p in parts if p)


def iter_component_children(components: Any) -> Iterator[Any]:
    """Yield every child component, no matter how many action rows Discord uses."""
    for row in components or []:
        yield from getattr(row, "children", []) or []


def format_drop_recipients(message: Any, exclude_id: int | None) -> str:
    """Return '@name' or '@a, @b' for users mentioned in the drop, excluding self.

    Returns empty string if nobody else is mentioned (drop format we don't
    recognise)."""
    names: list[str] = []
    for user in getattr(message, "mentions", None) or []:
        uid = getattr(user, "id", None)
        if uid == exclude_id:
            continue
        name = getattr(user, "display_name", None) or getattr(user, "name", None)
        if name:
            names.append(f"@{name}")
    return ", ".join(names)


def is_drop_trigger(text: str) -> bool:
    return bool(_DROP_TRIGGER_RE.search(text))


def is_cooldown_message(text: str) -> bool:
    return bool(_COOLDOWN_RE.search(text))

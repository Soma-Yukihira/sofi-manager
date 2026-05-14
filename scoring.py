"""
scoring.py
Card scoring + selection — pure functions over a card dict and a config dict.

The scoring logic is intentionally separate from any Discord / GUI concern so
it can be evolved (and unit-tested) without touching the bot orchestrator.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

# Default-config knobs the scorer needs as fallbacks.
_DEFAULT_RARITY_NORM = 2000.0
_DEFAULT_HEARTS_NORM = 500.0
_DEFAULT_RARITY_WEIGHT = 0.30
_DEFAULT_HEARTS_WEIGHT = 0.70

LogFn = Callable[[str, str], None]


def _as_float(value: Any, default: float) -> float:
    # Local copy of bot_core's coercion helper — duplicating ~6 lines is
    # cheaper than introducing a circular import via a shared utils module.
    try:
        return float(value)
    except (TypeError, ValueError):
        return float(default)


def score_card(card: dict[str, Any], cfg: dict[str, Any]) -> float:
    rarity_norm = max(1.0, _as_float(cfg.get("rarity_norm"), _DEFAULT_RARITY_NORM))
    hearts_norm = max(1.0, _as_float(cfg.get("hearts_norm"), _DEFAULT_HEARTS_NORM))
    rarity_weight = max(0.0, _as_float(cfg.get("score_rarity_weight"), _DEFAULT_RARITY_WEIGHT))
    hearts_weight = max(0.0, _as_float(cfg.get("score_hearts_weight"), _DEFAULT_HEARTS_WEIGHT))

    rarity_score = max(0.0, 1.0 - _as_float(card.get("rarity"), 0) / rarity_norm)
    hearts_score = min(1.0, max(0.0, _as_float(card.get("hearts"), 0) / hearts_norm))
    return round(
        rarity_weight * rarity_score
        + hearts_weight * hearts_score,
        3,
    )


def choose_card(cards: list[dict[str, Any]], cfg: dict[str, Any], log: LogFn) -> int:
    """Retourne l'index de la carte à cliquer, en logguant le raisonnement."""
    scored = [(c, score_card(c, cfg)) for c in cards]
    best_card, best_score = max(scored, key=lambda x: x[1])

    wishlist_card: dict[str, Any] | None = None
    wishlist_score = 0.0
    wishlist_label = ""

    for card, score in scored:
        for wish in cfg.get("wishlist", []):
            if wish.lower() in card["name"].lower():
                if wishlist_card is None or score > wishlist_score:
                    wishlist_card, wishlist_score = card, score
                    wishlist_label = "🌟 Wishlist perso"

    if wishlist_card is None:
        for card, score in scored:
            for series in cfg.get("wishlist_series", []):
                if series.lower() in card["series"].lower():
                    if wishlist_card is None or score > wishlist_score:
                        wishlist_card, wishlist_score = card, score
                        wishlist_label = "📺 Wishlist série"

    if wishlist_card is not None:
        for card, score in scored:
            log("info", f"  {card['name']} • {card['series']} → score {score} (G•{card['rarity']} | {card['hearts']}❤️)")
        if best_score >= wishlist_score * cfg["wishlist_override_threshold"] and best_card != wishlist_card:
            log("warn", f"⚡ {wishlist_label} ignoré : {wishlist_card['name']} (score {wishlist_score}) "
                        f"< {best_card['name']} (score {best_score})")
            log("success", f"💡 Meilleur score retenu : {best_card['name']} • {best_card['series']}")
            return best_card["index"]
        log("success", f"{wishlist_label} : {wishlist_card['name']} • {wishlist_card['series']} "
                      f"(G•{wishlist_card['rarity']} | {wishlist_card['hearts']}❤️ | score {wishlist_score})")
        return wishlist_card["index"]

    for card, score in scored:
        log("info", f"  {card['name']} • {card['series']} → score {score} (G•{card['rarity']} | {card['hearts']}❤️)")
    log("success", f"💡 Meilleur score : {best_card['name']} • {best_card['series']} (score {best_score})")
    return best_card["index"]

import unittest

from sofi_manager.bot_core import default_config
from sofi_manager.scoring import choose_card, score_card


class ScoreCardTests(unittest.TestCase):
    def test_survives_zero_norms(self):
        cfg = default_config()
        cfg["rarity_norm"] = 0
        cfg["hearts_norm"] = 0

        score = score_card({"rarity": 10, "hearts": 20}, cfg)

        self.assertIsInstance(score, float)

    def test_higher_hearts_yields_higher_score(self):
        cfg = default_config()
        low = score_card({"rarity": 100, "hearts": 0}, cfg)
        high = score_card({"rarity": 100, "hearts": 400}, cfg)
        self.assertGreater(high, low)

    def test_lower_rarity_yields_higher_score(self):
        cfg = default_config()
        rare = score_card({"rarity": 10, "hearts": 100}, cfg)
        common = score_card({"rarity": 1500, "hearts": 100}, cfg)
        self.assertGreater(rare, common)

    def test_score_is_bounded(self):
        cfg = default_config()
        score = score_card({"rarity": 100, "hearts": 99999}, cfg)
        self.assertLessEqual(score, 1.0)
        self.assertGreaterEqual(score, 0.0)


class ChooseCardTests(unittest.TestCase):
    def test_uses_best_personal_wishlist_match(self):
        cfg = default_config()
        cfg["wishlist"] = ["A", "B"]
        cards = [
            {"index": 0, "name": "A", "series": "S", "rarity": 400, "hearts": 400},
            {"index": 1, "name": "B", "series": "S", "rarity": 100, "hearts": 430},
        ]

        selected = choose_card(cards, cfg, lambda *_: None)

        self.assertEqual(selected, 1)

    def test_falls_back_to_best_score_when_no_wishlist_hit(self):
        cfg = default_config()
        cfg["wishlist"] = []
        cfg["wishlist_series"] = []
        cards = [
            {"index": 0, "name": "X", "series": "S", "rarity": 1500, "hearts": 10},
            {"index": 1, "name": "Y", "series": "S", "rarity": 50, "hearts": 400},
        ]

        selected = choose_card(cards, cfg, lambda *_: None)

        self.assertEqual(selected, 1)

    def test_series_wishlist_when_no_personal_match(self):
        cfg = default_config()
        cfg["wishlist"] = []
        cfg["wishlist_series"] = ["Vocaloid"]
        cards = [
            {"index": 0, "name": "A", "series": "Random", "rarity": 50, "hearts": 400},
            {"index": 1, "name": "B", "series": "Vocaloid", "rarity": 100, "hearts": 200},
        ]

        # threshold high so best score doesn't override the series pick
        cfg["wishlist_override_threshold"] = 5.0

        selected = choose_card(cards, cfg, lambda *_: None)

        self.assertEqual(selected, 1)

    def test_wishlist_overridden_by_far_better_score(self):
        # The wishlist match is much weaker than the best non-wishlist card,
        # and the override threshold is low (1.0) so the best score wins.
        # This pins down the "override warning" branch.
        cfg = default_config()
        cfg["wishlist"] = ["WishMatch"]
        cfg["wishlist_series"] = []
        cfg["wishlist_override_threshold"] = 1.0  # any improvement triggers override
        cards = [
            # WishMatch: high rarity (low score), few hearts → low score.
            {"index": 0, "name": "WishMatch", "series": "S", "rarity": 1800, "hearts": 10},
            # Top: low rarity (high score), many hearts → much higher score.
            {"index": 1, "name": "Top", "series": "S", "rarity": 10, "hearts": 500},
        ]

        captured: list[tuple[str, str]] = []
        selected = choose_card(cards, cfg, lambda lvl, msg: captured.append((lvl, msg)))

        self.assertEqual(selected, 1)
        # The override path logs a warning that names the ignored wishlist card.
        warn_msgs = [m for lvl, m in captured if lvl == "warn"]
        self.assertTrue(any("WishMatch" in m for m in warn_msgs))


if __name__ == "__main__":
    unittest.main()

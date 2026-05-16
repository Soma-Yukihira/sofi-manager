import unittest
from types import SimpleNamespace

from sofi_manager.parsing import (
    extract_full_text,
    format_drop_recipients,
    is_cooldown_message,
    is_drop_trigger,
    iter_component_children,
    parse_button_hearts,
    parse_cooldown_seconds,
    smart_parse_cards,
)


class FakeChild:
    def __init__(self, label):
        self.label = label


class FakeRow:
    def __init__(self, children):
        self.children = children


class FakeMentionedUser:
    def __init__(self, uid, name=None, display_name=None):
        self.id = uid
        self.name = name
        self.display_name = display_name


class FakeMessage:
    def __init__(self, mentions):
        self.mentions = mentions


class IterComponentChildrenTests(unittest.TestCase):
    def test_component_children_are_flattened_across_rows(self):
        rows = [
            FakeRow([FakeChild("1"), FakeChild("2")]),
            FakeRow([FakeChild("3")]),
        ]

        labels = [child.label for child in iter_component_children(rows)]

        self.assertEqual(labels, ["1", "2", "3"])

    def test_handles_none_components(self):
        self.assertEqual(list(iter_component_children(None)), [])

    def test_handles_row_without_children(self):
        class Empty:
            pass

        self.assertEqual(list(iter_component_children([Empty()])), [])


class FormatDropRecipientsTests(unittest.TestCase):
    def test_empty_when_no_mentions(self):
        self.assertEqual(format_drop_recipients(FakeMessage([]), 42), "")

    def test_excludes_self(self):
        msg = FakeMessage([FakeMentionedUser(42, display_name="me")])
        self.assertEqual(format_drop_recipients(msg, 42), "")

    def test_prefers_display_name(self):
        msg = FakeMessage([FakeMentionedUser(7, name="raw", display_name="Pretty")])
        self.assertEqual(format_drop_recipients(msg, 42), "@Pretty")

    def test_falls_back_to_name(self):
        msg = FakeMessage([FakeMentionedUser(7, name="raw", display_name=None)])
        self.assertEqual(format_drop_recipients(msg, 42), "@raw")

    def test_joins_multiple(self):
        msg = FakeMessage(
            [
                FakeMentionedUser(1, display_name="a"),
                FakeMentionedUser(42, display_name="me"),
                FakeMentionedUser(2, display_name="b"),
            ]
        )
        self.assertEqual(format_drop_recipients(msg, 42), "@a, @b")


class ParseButtonHeartsTests(unittest.TestCase):
    def test_plain_integer(self):
        self.assertEqual(parse_button_hearts("43"), 43)

    def test_k_suffix_integer(self):
        self.assertEqual(parse_button_hearts("1k"), 1000)

    def test_k_suffix_float(self):
        self.assertEqual(parse_button_hearts("1.2k"), 1200)

    def test_uppercase_k(self):
        self.assertEqual(parse_button_hearts("5K"), 5000)

    def test_invalid_returns_none(self):
        self.assertIsNone(parse_button_hearts("oops"))

    def test_invalid_k_returns_none(self):
        self.assertIsNone(parse_button_hearts("abck"))


class ParseCooldownSecondsTests(unittest.TestCase):
    def test_seconds_only(self):
        self.assertEqual(parse_cooldown_seconds("prêt dans 45s"), 45)

    def test_minutes_and_seconds(self):
        self.assertEqual(parse_cooldown_seconds("prêt dans 2m 30s"), 150)

    def test_english_phrase(self):
        self.assertEqual(parse_cooldown_seconds("ready in 1m 0s"), 60)

    def test_no_match_returns_none(self):
        self.assertIsNone(parse_cooldown_seconds("nothing here"))


class SmartParseCardsTests(unittest.TestCase):
    def test_parses_cards_with_hearts(self):
        content = "G•`120` | Miku • Vocaloid • 256\nG•`80` | Rin • Vocaloid • 64"
        cards = smart_parse_cards(content)
        self.assertEqual(len(cards), 2)
        self.assertEqual(cards[0]["name"], "Miku")
        self.assertEqual(cards[0]["series"], "Vocaloid")
        self.assertEqual(cards[0]["rarity"], 120)
        self.assertEqual(cards[0]["hearts"], 256)
        self.assertEqual(cards[1]["hearts"], 64)

    def test_falls_back_to_no_hearts(self):
        content = "G•`120` | Miku • Vocaloid"
        cards = smart_parse_cards(content)
        self.assertEqual(len(cards), 1)
        self.assertEqual(cards[0]["hearts"], 0)

    def test_empty_when_no_match(self):
        self.assertEqual(smart_parse_cards("no cards here"), [])


class TriggerDetectionTests(unittest.TestCase):
    def test_drop_trigger_french(self):
        self.assertTrue(is_drop_trigger("drop des cartes"))

    def test_drop_trigger_english(self):
        self.assertTrue(is_drop_trigger("dropping cards"))

    def test_drop_trigger_negative(self):
        self.assertFalse(is_drop_trigger("nothing here"))

    def test_cooldown_french(self):
        self.assertTrue(is_cooldown_message("prêt dans 30s"))

    def test_cooldown_english(self):
        self.assertTrue(is_cooldown_message("ready in 1m"))

    def test_cooldown_negative(self):
        self.assertFalse(is_cooldown_message("dropping cards"))


class ExtractFullTextTests(unittest.TestCase):
    """Cover the embed-walk in parsing.extract_full_text.

    SOFI sometimes wraps the card list in an embed (title / description /
    fields / footer); extract_full_text flattens content + every embed into
    a single string the regex parsers can chew on. We build SimpleNamespace
    stand-ins for discord.Message + discord.Embed so the test is fully
    in-process and doesn't import the discord-py library at runtime.
    """

    @staticmethod
    def _embed(**kwargs):
        # discord.Embed has explicit attrs for title / description / author /
        # fields / footer; the parser only reads what's present, so a flexible
        # SimpleNamespace is enough.
        kwargs.setdefault("title", None)
        kwargs.setdefault("description", None)
        kwargs.setdefault("author", None)
        kwargs.setdefault("fields", [])
        kwargs.setdefault("footer", None)
        return SimpleNamespace(**kwargs)

    @staticmethod
    def _message(content="", embeds=None):
        return SimpleNamespace(content=content, embeds=embeds or [])

    def test_returns_content_when_no_embeds(self):
        msg = self._message(content="hello world")
        self.assertEqual(extract_full_text(msg), "hello world")

    def test_handles_none_content(self):
        # discord can give us content=None when the message is embeds-only.
        msg = self._message(content=None)
        self.assertEqual(extract_full_text(msg), "")

    def test_concatenates_embed_title_and_description(self):
        embed = self._embed(title="Drop", description="Pick one")
        msg = self._message(content="hey", embeds=[embed])
        self.assertEqual(extract_full_text(msg), "hey\nDrop\nPick one")

    def test_includes_embed_author_name(self):
        author = SimpleNamespace(name="SOFI")
        embed = self._embed(author=author)
        msg = self._message(embeds=[embed])
        self.assertIn("SOFI", extract_full_text(msg))

    def test_skips_author_without_name(self):
        # Some embeds carry an author proxy with no name; must not crash.
        author = SimpleNamespace(name=None)
        embed = self._embed(author=author)
        msg = self._message(content="x", embeds=[embed])
        self.assertEqual(extract_full_text(msg), "x")

    def test_includes_embed_fields(self):
        fields = [
            SimpleNamespace(name="Card 1", value="Miku"),
            SimpleNamespace(name="", value=""),  # empty field — must skip cleanly
        ]
        embed = self._embed(fields=fields)
        msg = self._message(embeds=[embed])
        text = extract_full_text(msg)
        self.assertIn("Card 1", text)
        self.assertIn("Miku", text)

    def test_includes_embed_footer_text(self):
        footer = SimpleNamespace(text="page 1/3")
        embed = self._embed(footer=footer)
        msg = self._message(embeds=[embed])
        self.assertIn("page 1/3", extract_full_text(msg))

    def test_skips_footer_without_text(self):
        footer = SimpleNamespace(text=None)
        embed = self._embed(footer=footer, title="t")
        msg = self._message(embeds=[embed])
        self.assertEqual(extract_full_text(msg), "t")

    def test_walks_multiple_embeds(self):
        msg = self._message(
            content="prefix",
            embeds=[
                self._embed(title="A"),
                self._embed(title="B", description="B-desc"),
            ],
        )
        self.assertEqual(extract_full_text(msg), "prefix\nA\nB\nB-desc")


if __name__ == "__main__":
    unittest.main()

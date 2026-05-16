from __future__ import annotations

import unittest
import urllib.error

from sofi_manager import changelog


class SplitCommitMessage(unittest.TestCase):
    def test_subject_only(self):
        self.assertEqual(
            changelog.split_commit_message("feat: add thing (#1)"),
            ("feat: add thing (#1)", ""),
        )

    def test_subject_with_body(self):
        msg = "feat: add thing (#1)\n\n## Summary\nDoes the thing.\n"
        title, body = changelog.split_commit_message(msg)
        self.assertEqual(title, "feat: add thing (#1)")
        self.assertEqual(body, "## Summary\nDoes the thing.")

    def test_empty_message(self):
        self.assertEqual(changelog.split_commit_message(""), ("", ""))

    def test_strips_trailing_whitespace_from_body(self):
        msg = "x\n\nbody\n\n\n"
        _, body = changelog.split_commit_message(msg)
        self.assertEqual(body, "body")

    def test_handles_multiple_leading_blank_lines(self):
        msg = "\n\nfix: thing\n\nbody"
        title, body = changelog.split_commit_message(msg)
        self.assertEqual(title, "fix: thing")
        self.assertEqual(body, "body")


class ParseComparePayload(unittest.TestCase):
    def _commit(self, sha: str, message: str, html_url: str = "") -> dict:
        return {
            "sha": sha,
            "html_url": html_url or f"https://github.com/x/y/commit/{sha}",
            "commit": {"message": message},
        }

    def test_extracts_entries_in_order(self):
        payload = {
            "commits": [
                self._commit("a" * 40, "feat: one (#1)\n\nbody one"),
                self._commit("b" * 40, "fix: two (#2)"),
            ]
        }
        entries = changelog.parse_compare_payload(payload)
        self.assertEqual(len(entries), 2)
        self.assertEqual(entries[0].sha, "a" * 7)
        self.assertEqual(entries[0].title, "feat: one (#1)")
        self.assertEqual(entries[0].body, "body one")
        self.assertEqual(entries[1].sha, "b" * 7)
        self.assertEqual(entries[1].body, "")

    def test_returns_empty_on_non_dict(self):
        self.assertEqual(changelog.parse_compare_payload(None), ())
        self.assertEqual(changelog.parse_compare_payload([]), ())
        self.assertEqual(changelog.parse_compare_payload("nope"), ())

    def test_returns_empty_when_commits_missing(self):
        self.assertEqual(changelog.parse_compare_payload({}), ())

    def test_returns_empty_when_commits_not_a_list(self):
        self.assertEqual(changelog.parse_compare_payload({"commits": "x"}), ())

    def test_skips_entries_with_missing_sha(self):
        payload = {
            "commits": [
                {"commit": {"message": "no sha here"}},
                self._commit("c" * 40, "ok (#3)"),
            ]
        }
        entries = changelog.parse_compare_payload(payload)
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0].sha, "c" * 7)

    def test_skips_entries_with_empty_title(self):
        payload = {"commits": [self._commit("d" * 40, "")]}
        self.assertEqual(changelog.parse_compare_payload(payload), ())

    def test_falls_back_to_commit_url_when_html_url_missing(self):
        payload = {
            "commits": [
                {"sha": "e" * 40, "commit": {"message": "feat: x"}},
            ]
        }
        entries = changelog.parse_compare_payload(payload)
        self.assertEqual(len(entries), 1)
        self.assertIn("e" * 40, entries[0].html_url)

    def test_skips_non_dict_commit_items(self):
        payload = {"commits": ["nope", self._commit("f" * 40, "fix: ok")]}
        entries = changelog.parse_compare_payload(payload)
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0].sha, "f" * 7)


class FetchChangelog(unittest.TestCase):
    def test_success_returns_entries_and_compare_url(self):
        payload = {
            "commits": [
                {
                    "sha": "a" * 40,
                    "html_url": "https://github.com/x/y/commit/aaa",
                    "commit": {"message": "feat: one (#1)"},
                }
            ]
        }
        result = changelog.fetch_changelog("old", "new", get_json=lambda _url: payload)
        self.assertTrue(result.ok)
        self.assertEqual(len(result.entries), 1)
        self.assertEqual(result.error, "")
        self.assertIn("old...new", result.compare_url)

    def test_empty_sha_returns_error_without_calling_api(self):
        calls: list[str] = []

        def boom(url: str) -> object:
            calls.append(url)
            return {}

        result = changelog.fetch_changelog("", "new", get_json=boom)
        self.assertFalse(result.ok)
        self.assertEqual(result.error, "SHA manquant.")
        self.assertEqual(calls, [])

    def test_network_error_returns_fr_message(self):
        def raise_urlerror(_url: str) -> object:
            raise urllib.error.URLError("offline")

        result = changelog.fetch_changelog("a", "b", get_json=raise_urlerror)
        self.assertFalse(result.ok)
        self.assertIn("API GitHub", result.error)
        self.assertEqual(result.entries, ())
        self.assertIn("a...b", result.compare_url)

    def test_oserror_returns_fr_message(self):
        def raise_oserror(_url: str) -> object:
            raise OSError("dns")

        result = changelog.fetch_changelog("a", "b", get_json=raise_oserror)
        self.assertFalse(result.ok)
        self.assertIn("API GitHub", result.error)

    def test_value_error_returns_fr_message(self):
        def raise_valueerror(_url: str) -> object:
            raise ValueError("bad json")

        result = changelog.fetch_changelog("a", "b", get_json=raise_valueerror)
        self.assertFalse(result.ok)

    def test_unexpected_exception_returns_generic_message(self):
        def raise_runtime(_url: str) -> object:
            raise RuntimeError("???")

        result = changelog.fetch_changelog("a", "b", get_json=raise_runtime)
        self.assertFalse(result.ok)
        self.assertIn("inattendue", result.error)

    def test_url_is_built_from_template(self):
        captured: list[str] = []

        def capture(url: str) -> object:
            captured.append(url)
            return {"commits": []}

        changelog.fetch_changelog("OLD", "NEW", get_json=capture)
        self.assertEqual(len(captured), 1)
        self.assertIn("/compare/OLD...NEW", captured[0])

    def test_success_with_empty_commits_still_ok(self):
        result = changelog.fetch_changelog("a", "b", get_json=lambda _u: {"commits": []})
        self.assertTrue(result.ok)
        self.assertEqual(result.entries, ())


class RenderBody(unittest.TestCase):
    def test_empty_returns_empty_tuple(self):
        self.assertEqual(changelog.render_body(""), ())

    def test_single_paragraph(self):
        blocks = changelog.render_body("just one line")
        self.assertEqual(blocks, (changelog.Block("paragraph", "just one line", 0),))

    def test_paragraph_collapses_soft_wraps(self):
        blocks = changelog.render_body("line one\nline two\nline three")
        self.assertEqual(
            blocks,
            (changelog.Block("paragraph", "line one line two line three", 0),),
        )

    def test_blank_line_separates_paragraphs(self):
        blocks = changelog.render_body("para one\n\npara two")
        self.assertEqual(
            blocks,
            (
                changelog.Block("paragraph", "para one", 0),
                changelog.Block("blank", "", 0),
                changelog.Block("paragraph", "para two", 0),
            ),
        )

    def test_consecutive_blanks_collapse(self):
        blocks = changelog.render_body("a\n\n\n\nb")
        kinds = [b.kind for b in blocks]
        self.assertEqual(kinds, ["paragraph", "blank", "paragraph"])

    def test_trailing_blanks_trimmed(self):
        blocks = changelog.render_body("a\n\n\n")
        self.assertEqual(blocks, (changelog.Block("paragraph", "a", 0),))

    def test_h2_heading(self):
        blocks = changelog.render_body("## Summary")
        self.assertEqual(blocks, (changelog.Block("heading", "Summary", 1),))

    def test_h3_heading(self):
        blocks = changelog.render_body("### Detail")
        self.assertEqual(blocks, (changelog.Block("heading", "Detail", 2),))

    def test_h1_heading(self):
        blocks = changelog.render_body("# Top")
        self.assertEqual(blocks, (changelog.Block("heading", "Top", 0),))

    def test_dash_bullets(self):
        body = "- alpha\n- beta\n- gamma"
        blocks = changelog.render_body(body)
        self.assertEqual(
            blocks,
            (
                changelog.Block("bullet", "alpha", 0),
                changelog.Block("bullet", "beta", 0),
                changelog.Block("bullet", "gamma", 0),
            ),
        )

    def test_star_bullets_treated_like_dash(self):
        blocks = changelog.render_body("* one\n* two")
        kinds = [b.kind for b in blocks]
        texts = [b.text for b in blocks]
        self.assertEqual(kinds, ["bullet", "bullet"])
        self.assertEqual(texts, ["one", "two"])

    def test_nested_bullets_get_level(self):
        blocks = changelog.render_body("- top\n  - nested\n    - deeper")
        levels = [b.level for b in blocks]
        self.assertEqual(levels, [0, 1, 2])

    def test_task_list_marker_stripped(self):
        blocks = changelog.render_body("- [ ] todo\n- [x] done")
        self.assertEqual(
            blocks,
            (
                changelog.Block("bullet", "todo", 0),
                changelog.Block("bullet", "done", 0),
            ),
        )

    def test_inline_bold_stripped(self):
        blocks = changelog.render_body("- adds **important** thing")
        self.assertEqual(blocks[0].text, "adds important thing")

    def test_inline_code_stripped(self):
        blocks = changelog.render_body("- updates `helper()`")
        self.assertEqual(blocks[0].text, "updates helper()")

    def test_inline_italic_stripped(self):
        blocks = changelog.render_body("see *the docs* later")
        self.assertEqual(blocks[0].text, "see the docs later")

    def test_realistic_pr_body(self):
        body = (
            "## Summary\n"
            "- adds X\n"
            "- fixes Y\n"
            "\n"
            "## Test plan\n"
            "- [ ] manual smoke\n"
            "- [x] pytest green\n"
        )
        kinds = [b.kind for b in changelog.render_body(body)]
        self.assertEqual(
            kinds,
            [
                "heading",
                "bullet",
                "bullet",
                "blank",
                "heading",
                "bullet",
                "bullet",
            ],
        )

    def test_paragraph_then_bullets_no_implicit_blank(self):
        blocks = changelog.render_body("intro line\n- a\n- b")
        kinds = [b.kind for b in blocks]
        self.assertEqual(kinds, ["paragraph", "bullet", "bullet"])


if __name__ == "__main__":
    unittest.main()

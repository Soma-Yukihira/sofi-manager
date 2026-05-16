"""
changelog.py - Fetch + parse the commit list between two SHAs.

Drives the post-update "what's new" modal in `gui.py`. The GitHub
Compare endpoint
(`GET /repos/{owner}/{repo}/compare/{base}...{head}`) returns the
commits reachable from `head` but not from `base`, with title + body
+ `html_url`. With squash-merge that maps one entry to one PR.

Pure helpers (parsing, formatting) live here so they can be tested
without a network round-trip; the actual HTTP call delegates to
`updater._http_get_json` and can be injected for tests.
"""

from __future__ import annotations

import re
import urllib.error
from collections.abc import Callable
from dataclasses import dataclass
from typing import Literal

from . import updater, version

_OWNER_REPO = "Soma-Yukihira/sofi-manager"
_COMPARE_API_TEMPLATE = f"https://api.github.com/repos/{_OWNER_REPO}/compare/{{base}}...{{head}}"


@dataclass(frozen=True)
class ChangelogEntry:
    """One commit in the compare range.

    `sha` is the 7-char short form (the API returns full 40, we trim
    at parse time so the modal renders compactly). `body` is the
    commit message body with the title line stripped; empty when the
    commit has only a subject line.
    """

    sha: str
    title: str
    body: str
    html_url: str


@dataclass(frozen=True)
class ChangelogResult:
    """Outcome of a `fetch_changelog` call.

    `ok` is True when the API call succeeded and parsed cleanly. On
    failure, `entries` is empty and `error` carries a short FR string
    suitable for display. `compare_url` is always set (computed from
    the input SHAs) so the modal can render the GitHub fallback link
    even on API error.
    """

    ok: bool
    entries: tuple[ChangelogEntry, ...]
    compare_url: str
    error: str


def split_commit_message(message: str) -> tuple[str, str]:
    """Split a commit message into `(title, body)`.

    The title is the first non-empty line; the body is everything
    after the first blank line, stripped of trailing whitespace.
    Conventional-commit squash-merge messages have the form
    `type(scope): subject (#NN)\\n\\n<PR body>` — this returns the
    subject and the body separately.
    """
    if not message:
        return "", ""
    lines = message.splitlines()
    title = ""
    body_start = 0
    for i, line in enumerate(lines):
        if line.strip():
            title = line.strip()
            body_start = i + 1
            break
    # Skip the blank line separating subject and body, if any.
    while body_start < len(lines) and not lines[body_start].strip():
        body_start += 1
    body = "\n".join(lines[body_start:]).rstrip()
    return title, body


def parse_compare_payload(data: object) -> tuple[ChangelogEntry, ...]:
    """Extract ChangelogEntry tuples from a parsed compare-API JSON.

    Defensive: any malformed entry is skipped rather than raising,
    because GitHub occasionally returns commits with missing fields
    (e.g. force-pushed history). An empty tuple on a structurally
    invalid payload is the caller's signal to surface "Aucun
    changement".
    """
    if not isinstance(data, dict):
        return ()
    commits = data.get("commits")
    if not isinstance(commits, list):
        return ()
    out: list[ChangelogEntry] = []
    for c in commits:
        if not isinstance(c, dict):
            continue
        sha = c.get("sha")
        if not isinstance(sha, str) or not sha:
            continue
        commit_blob = c.get("commit")
        message = ""
        if isinstance(commit_blob, dict):
            raw = commit_blob.get("message")
            if isinstance(raw, str):
                message = raw
        title, body = split_commit_message(message)
        if not title:
            continue
        html_url = c.get("html_url")
        if not isinstance(html_url, str) or not html_url:
            html_url = version.commit_url(sha)
        out.append(ChangelogEntry(sha=sha[:7], title=title, body=body, html_url=html_url))
    return tuple(out)


def compare_api_url(old_sha: str, new_sha: str) -> str:
    return _COMPARE_API_TEMPLATE.format(base=old_sha, head=new_sha)


BlockKind = Literal["heading", "bullet", "paragraph", "blank"]


@dataclass(frozen=True)
class Block:
    """One block of rendered commit-body markdown.

    `level` carries the heading depth (`## ` → 1, `### ` → 2, `# ` → 0)
    or the bullet indent depth (top-level bullet → 0, nested → 1+).
    Always 0 for paragraph and blank blocks.
    """

    kind: BlockKind
    text: str
    level: int = 0


_BOLD_RE = re.compile(r"\*\*(.+?)\*\*")
_ITALIC_RE = re.compile(r"(?<![*\w])\*(?!\s)([^*\n]+?)(?<!\s)\*(?!\w)")
_CODE_RE = re.compile(r"`([^`\n]+)`")
_BULLET_RE = re.compile(r"^[-*]\s+(.*)$")
_HEADING_RE = re.compile(r"^(#{1,6})\s+(.*)$")
_TASK_RE = re.compile(r"^\[[ xX]\]\s+")


def _strip_inline(s: str) -> str:
    """Drop GitHub-flavored inline marks while keeping the inner text.

    Bold (`**x**`), italic (`*x*`), and code (`` `x` ``) collapse to
    their inner text. Inline rendering would require per-run widget
    layout in CTk, which fights wrapping; the modal compensates with
    per-block typography (heading font, bullet glyph) instead.
    """
    s = _BOLD_RE.sub(r"\1", s)
    s = _ITALIC_RE.sub(r"\1", s)
    s = _CODE_RE.sub(r"\1", s)
    return s


def render_body(text: str) -> tuple[Block, ...]:
    """Parse a commit-message body into renderable blocks.

    Handles `## Headings`, `- bullets` (or `*`), GitHub task lists
    (`- [ ]` / `- [x]`), and paragraphs (lines collapsed with a single
    space, like GFM). Inline marks are stripped — see `_strip_inline`.
    Consecutive blank lines collapse to a single blank block; trailing
    blanks are trimmed.
    """
    if not text:
        return ()
    blocks: list[Block] = []
    paragraph_buf: list[str] = []

    def flush_paragraph() -> None:
        if paragraph_buf:
            joined = " ".join(paragraph_buf).strip()
            if joined:
                blocks.append(Block("paragraph", joined, 0))
            paragraph_buf.clear()

    def push_blank() -> None:
        if blocks and blocks[-1].kind != "blank":
            blocks.append(Block("blank", "", 0))

    for raw in text.splitlines():
        stripped = raw.strip()
        if not stripped:
            flush_paragraph()
            push_blank()
            continue
        heading_match = _HEADING_RE.match(stripped)
        if heading_match:
            flush_paragraph()
            level = max(0, len(heading_match.group(1)) - 1)
            blocks.append(Block("heading", _strip_inline(heading_match.group(2)), level))
            continue
        # Bullet detection uses the raw line so leading indent maps to nesting.
        bullet_match = _BULLET_RE.match(raw.lstrip())
        if bullet_match:
            flush_paragraph()
            indent = len(raw) - len(raw.lstrip())
            level = indent // 2
            inner = _TASK_RE.sub("", bullet_match.group(1).strip())
            blocks.append(Block("bullet", _strip_inline(inner), level))
            continue
        paragraph_buf.append(_strip_inline(stripped))
    flush_paragraph()
    while blocks and blocks[-1].kind == "blank":
        blocks.pop()
    return tuple(blocks)


def fetch_changelog(
    old_sha: str,
    new_sha: str,
    *,
    get_json: Callable[[str], object] | None = None,
) -> ChangelogResult:
    """Fetch the commit range `old_sha..new_sha` from the compare API.

    `get_json` defaults to `updater._http_get_json` and is injectable
    so tests can stub out the network. On any failure (network, HTTP,
    JSON, schema), `ok=False` with a FR error message; the caller is
    expected to show the message inside the modal and surface the
    `compare_url` button as a fallback.
    """
    cmp_url = version.compare_url(old_sha, new_sha)
    if not old_sha or not new_sha:
        return ChangelogResult(ok=False, entries=(), compare_url=cmp_url, error="SHA manquant.")
    fetch = get_json if get_json is not None else updater._http_get_json
    try:
        data = fetch(compare_api_url(old_sha, new_sha))
    except (urllib.error.URLError, OSError, ValueError):
        return ChangelogResult(
            ok=False,
            entries=(),
            compare_url=cmp_url,
            error="Impossible de joindre l'API GitHub.",
        )
    except Exception:
        return ChangelogResult(
            ok=False,
            entries=(),
            compare_url=cmp_url,
            error="Erreur inattendue lors de la récupération.",
        )
    entries = parse_compare_payload(data)
    return ChangelogResult(ok=True, entries=entries, compare_url=cmp_url, error="")

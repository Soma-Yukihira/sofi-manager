"""GitHub Releases update check.

Pure stdlib (urllib + json). Returns an :class:`UpdateResult` describing the
outcome; never raises. The GUI calls :func:`check_for_update` from a worker
thread and marshals the result back to the Tk main thread.

Version comparison is strict SemVer (`MAJOR.MINOR.PATCH`); the leading `v` of
a tag is tolerated, anything else (e.g. `1.2`, `1.2.3-rc1`) is treated as
malformed and surfaced as an error rather than a silent miscompare.
"""

from __future__ import annotations

import json
import re
import urllib.error
import urllib.request
from dataclasses import dataclass

from version import __repo__, __version__

API_URL = f"https://api.github.com/repos/{__repo__}/releases/latest"
USER_AGENT = f"sofi-manager-updater/{__version__}"
TIMEOUT_SECONDS = 8

_SEMVER_RE = re.compile(r"^v?(\d+)\.(\d+)\.(\d+)$")
_NOTES_MAX_CHARS = 1200


@dataclass(frozen=True)
class UpdateResult:
    current_version: str
    latest_version: str | None = None
    update_available: bool = False
    release_url: str | None = None
    release_name: str | None = None
    release_notes: str | None = None
    error: str | None = None


def _parse_semver(tag: str) -> tuple[int, int, int] | None:
    m = _SEMVER_RE.match(tag.strip())
    if not m:
        return None
    return int(m.group(1)), int(m.group(2)), int(m.group(3))


def _truncate(text: str, limit: int = _NOTES_MAX_CHARS) -> str:
    text = text.strip()
    if len(text) <= limit:
        return text
    return text[: limit - 1].rstrip() + "…"


def check_for_update(timeout: float = TIMEOUT_SECONDS) -> UpdateResult:
    current = __version__
    req = urllib.request.Request(
        API_URL,
        headers={"User-Agent": USER_AGENT, "Accept": "application/vnd.github+json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return UpdateResult(
                current_version=current,
                error="Aucune release publiée pour le moment.",
            )
        if e.code == 403:
            return UpdateResult(
                current_version=current,
                error="Limite GitHub atteinte. Réessayez plus tard.",
            )
        return UpdateResult(
            current_version=current,
            error=f"Erreur GitHub (HTTP {e.code}).",
        )
    except urllib.error.URLError:
        return UpdateResult(
            current_version=current,
            error="Pas de connexion réseau ou GitHub indisponible.",
        )
    except (TimeoutError, OSError):
        return UpdateResult(
            current_version=current,
            error="Délai dépassé en contactant GitHub.",
        )
    except (ValueError, json.JSONDecodeError):
        return UpdateResult(
            current_version=current,
            error="Réponse GitHub invalide.",
        )

    tag = (payload.get("tag_name") or "").strip()
    release_url = payload.get("html_url") or f"https://github.com/{__repo__}/releases"
    release_name = (payload.get("name") or "").strip() or None
    notes = payload.get("body") or ""
    notes_short = _truncate(notes) if notes else None

    latest_parsed = _parse_semver(tag) if tag else None
    current_parsed = _parse_semver(current)

    if not tag:
        return UpdateResult(
            current_version=current,
            release_url=release_url,
            error="Release GitHub sans tag.",
        )
    if latest_parsed is None or current_parsed is None:
        return UpdateResult(
            current_version=current,
            latest_version=tag or None,
            release_url=release_url,
            release_name=release_name,
            release_notes=notes_short,
            error="Version malformée — comparaison impossible.",
        )

    return UpdateResult(
        current_version=current,
        latest_version=tag,
        update_available=latest_parsed > current_parsed,
        release_url=release_url,
        release_name=release_name,
        release_notes=notes_short,
    )

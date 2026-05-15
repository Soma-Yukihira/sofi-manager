"""
version.py - Identify which build of Selfbot Manager is running.

Git is the source of truth: at runtime we shell out to read commit
count, short SHA and commit date from HEAD. No `__version__` constant
to bump manually.

Two fallbacks for the cases where `.git/` is absent at runtime:

  - Frozen .exe builds bake the same triple into `_build_info.py` at
    build time (see `tools/build.py`).
  - ZIP installs (no .git/, no _build_info) only know the SHA they were
    last installed at, persisted in settings.json as `zip_install_sha`.
    Count and date are unavailable without an extra API call we
    deliberately don't make on the GUI launch path.

See PROJECT_CONTEXT.md "Update model -> Version identification".
"""

from __future__ import annotations

import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

VersionSource = Literal["git", "zip", "frozen", "unknown"]

ROOT = Path(__file__).resolve().parent.parent

_OWNER_REPO = "Soma-Yukihira/sofi-manager"

# Suppress flashing cmd windows when invoked from pythonw.exe / a frozen
# GUI (mirrors the same constant in updater.py).
_CREATE_NO_WINDOW = 0x08000000 if os.name == "nt" else 0


@dataclass(frozen=True)
class VersionInfo:
    """Identification triple for the running build.

    `count` is the number of commits on HEAD's history (humans read
    "v143"); None when unavailable (ZIP install, missing git). `sha` is
    always set - at minimum a 7-char short hash. `date` is the commit
    date as `YYYY-MM-DD`, empty when unknown.
    """

    count: int | None
    sha: str
    date: str
    source: VersionSource


def _git(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        creationflags=_CREATE_NO_WINDOW,
    )


def _is_frozen() -> bool:
    return bool(getattr(sys, "frozen", False))


def _is_git_clone() -> bool:
    return (ROOT / ".git").exists()


def _from_git() -> VersionInfo | None:
    """Read sha + date + count from the local clone, or None on any failure."""
    try:
        log_r = _git("log", "-1", "--format=%h|%cs")
    except (FileNotFoundError, OSError):
        return None
    if log_r.returncode != 0:
        return None
    out = (log_r.stdout or "").strip()
    if "|" not in out:
        return None
    sha, date = out.split("|", 1)
    if not sha:
        return None
    count: int | None = None
    try:
        count_r = _git("rev-list", "--count", "HEAD")
        if count_r.returncode == 0:
            raw = (count_r.stdout or "").strip()
            if raw:
                count = int(raw)
    except (FileNotFoundError, OSError, ValueError):
        count = None
    return VersionInfo(count=count, sha=sha, date=date, source="git")


def _from_frozen() -> VersionInfo | None:
    """Read the triple baked into `_build_info.py` at build time."""
    try:
        from . import _build_info  # type: ignore[attr-defined]
    except ImportError:
        return None
    sha = getattr(_build_info, "BUILD_SHA", "")
    if not isinstance(sha, str) or not sha:
        return None
    raw_count = getattr(_build_info, "BUILD_COUNT", None)
    count = raw_count if isinstance(raw_count, int) else None
    date = getattr(_build_info, "BUILD_DATE", "")
    if not isinstance(date, str):
        date = ""
    return VersionInfo(count=count, sha=sha, date=date, source="frozen")


def _from_zip_sha(zip_sha: str | None) -> VersionInfo | None:
    if not isinstance(zip_sha, str) or not zip_sha:
        return None
    return VersionInfo(count=None, sha=zip_sha[:7], date="", source="zip")


def get_version(zip_sha: str | None = None) -> VersionInfo:
    """Best-effort identification of the running build.

    Resolution order: frozen build -> git clone -> ZIP-install SHA from
    settings.json -> unknown placeholder. Callers running from the GUI
    pass `settings.get("zip_install_sha")` for the ZIP fallback.
    """
    if _is_frozen():
        v = _from_frozen()
        if v is not None:
            return v
    if _is_git_clone():
        v = _from_git()
        if v is not None:
            return v
    v = _from_zip_sha(zip_sha)
    if v is not None:
        return v
    return VersionInfo(count=None, sha="unknown", date="", source="unknown")


def format_short(v: VersionInfo) -> str:
    """`v143 - 727b0af` when count is known, else `727b0af`."""
    if v.count is not None:
        return f"v{v.count} · {v.sha}"
    return v.sha


def format_full(v: VersionInfo) -> str:
    """`v143 - 727b0af - 2026-05-15` (parts omitted when absent)."""
    parts: list[str] = []
    if v.count is not None:
        parts.append(f"v{v.count}")
    parts.append(v.sha)
    if v.date:
        parts.append(v.date)
    return " · ".join(parts)


def commit_url(sha: str) -> str:
    return f"https://github.com/{_OWNER_REPO}/commit/{sha}"


def compare_url(old_sha: str, new_sha: str) -> str:
    return f"https://github.com/{_OWNER_REPO}/compare/{old_sha}...{new_sha}"


def should_announce_update(last_seen: str | None, current: str) -> bool:
    """True iff the post-update banner should be shown.

    Returns False on first launch (no last_seen) so we silently adopt
    the baseline instead of fake-announcing a "first update". Returns
    False when the SHAs match (no actual change). The boolean is
    extracted from the GUI so it can be tested without Tk.
    """
    return last_seen is not None and bool(current) and last_seen != current

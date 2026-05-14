"""
updater.py - Discord-style auto-update.

Two-phase flow, sources-only (no GitHub Release artifact):

  Phase 1 - startup (`apply_pending_on_startup`):
      If the local clone is already behind upstream main from a previous
      `git fetch`, apply with `git pull --ff-only` and re-exec Python so
      the new code is in effect for this run. Equivalent to Discord
      applying a previously-downloaded patch on launch.

  Phase 2 - background (`check_in_background`):
      Run `git fetch` once the GUI is up. If new commits arrived, call
      the provided callback on the Tk main thread so it can surface a
      non-blocking banner.

Only active for git-clone installs. ZIP/exe installs (no `.git/`) skip
silently - they are expected to re-clone or rebuild.

Why no `release file`: this project ships continuously on `main`; users
follow HEAD. Pinning to a release would add a manual step (tagging)
without buying safety the fast-forward + dirty-tree checks below don't
already provide.
"""

from __future__ import annotations

import os
import subprocess
import sys
import threading
from collections.abc import Callable
from pathlib import Path

ROOT = Path(__file__).resolve().parent

# Suppress console windows on Windows when git is invoked from the GUI
# (which runs under pythonw.exe / a windowed exe). Without this flag,
# every `git` call flashes a black cmd window.
_CREATE_NO_WINDOW = 0x08000000 if os.name == "nt" else 0


def _git(*args: str, capture: bool = True) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", *args],
        cwd=str(ROOT),
        capture_output=capture,
        text=True,
        creationflags=_CREATE_NO_WINDOW,
    )


def is_git_clone() -> bool:
    return (ROOT / ".git").exists()


def _int(s: str) -> int:
    try:
        return int((s or "0").strip())
    except ValueError:
        return 0


def behind_count() -> int:
    """Upstream commits not yet in HEAD. 0 if up to date / unknown."""
    if not is_git_clone():
        return 0
    r = _git("rev-list", "--count", "HEAD..@{u}")
    return _int(r.stdout) if r.returncode == 0 else 0


def behind_main_count() -> int:
    """Commits on `origin/main` not yet in the local `main` branch.

    Used by the manual update check so it reports `available` based on what
    end-users will be fast-forwarded to, regardless of whether the dev is
    currently on a feature branch. Returns 0 if local `main` is missing or
    the rev-list call fails."""
    if not is_git_clone():
        return 0
    r = _git("rev-list", "--count", "main..origin/main")
    return _int(r.stdout) if r.returncode == 0 else 0


def ahead_count() -> int:
    if not is_git_clone():
        return 0
    r = _git("rev-list", "--count", "@{u}..HEAD")
    return _int(r.stdout) if r.returncode == 0 else 0


def has_local_changes() -> bool:
    """True if working tree has uncommitted modifications to tracked files."""
    if not is_git_clone():
        return False
    r = _git("status", "--porcelain", "--untracked-files=no")
    return bool((r.stdout or "").strip())


def current_branch() -> str:
    r = _git("rev-parse", "--abbrev-ref", "HEAD")
    return (r.stdout or "").strip() if r.returncode == 0 else ""


def _safe_to_pull() -> bool:
    # Refuse to touch the tree if anything looks unusual - avoids surprising
    # the user who has local work in progress.
    return (
        is_git_clone()
        and current_branch() == "main"
        and ahead_count() == 0
        and not has_local_changes()
    )


def _fetch() -> bool:
    if not is_git_clone():
        return False
    try:
        r = _git("fetch", "--quiet", "origin", "main")
    except (FileNotFoundError, OSError):
        return False
    return r.returncode == 0


def _pull() -> tuple[bool, str]:
    r = _git("pull", "--ff-only", "--quiet", "origin", "main")
    if r.returncode != 0:
        return False, (r.stderr or r.stdout or "git pull failed").strip()
    return True, "OK"


def _restart() -> None:
    """Re-exec the current Python interpreter with the same argv."""
    os.execv(sys.executable, [sys.executable, *sys.argv])


def apply_pending_on_startup() -> None:
    """
    Apply any update already fetched on the previous session, then re-exec.
    Silent on any failure - the app must always boot.
    """
    if not _safe_to_pull():
        return
    if behind_count() == 0:
        return
    try:
        ok, _msg = _pull()
    except Exception:
        return
    if ok:
        _restart()


def check_in_background(on_update_available: Callable[[int], None]) -> None:
    """
    Fire-and-forget. Fetches in a daemon thread; if behind, schedules
    `on_update_available(commit_count)` on the caller's thread.

    The caller is responsible for marshalling the callback onto the Tk main
    thread - typically by wrapping it in `root.after(0, ...)`.
    """
    if not is_git_clone():
        return

    def _worker() -> None:
        try:
            if not _fetch():
                return
            n = behind_count()
            if n > 0 and _safe_to_pull():
                on_update_available(n)
        except Exception:
            # Never let the updater crash the app.
            pass

    t = threading.Thread(target=_worker, name="updater", daemon=True)
    t.start()


def fetch_and_status() -> dict:
    """
    For the manual `Verifier les MAJ` button: fetch then describe what
    the updater would do. The check tracks `origin/main` regardless of the
    branch the user is currently on — devs working in feature branches
    still want to know when main has moved. The dirty / ahead gates only
    matter when the user is actually on main (i.e. eligible for the
    inline `Restart now` fast-forward).

    Returns a dict with `state` in:
        available, uptodate, not_git, fetch_failed, dirty, ahead
    and `behind` (int, only meaningful for `available`).
    """
    if not is_git_clone():
        return {"state": "not_git", "behind": 0}
    if not _fetch():
        return {"state": "fetch_failed", "behind": 0}
    n = behind_main_count()
    if n == 0:
        return {"state": "uptodate", "behind": 0}
    if current_branch() == "main":
        if has_local_changes():
            return {"state": "dirty", "behind": n}
        if ahead_count() > 0:
            return {"state": "ahead", "behind": n}
    return {"state": "available", "behind": n}


def apply_and_restart() -> tuple[bool, str]:
    """Called when the user clicks `Restart now`. Pulls then re-execs."""
    if not _safe_to_pull():
        return False, "Working tree not safe to fast-forward."
    ok, msg = _pull()
    if not ok:
        return False, msg
    _restart()
    return True, "Restarting..."  # unreachable

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

import io
import json as _json
import os
import shutil
import subprocess
import sys
import threading
import urllib.error
import urllib.request
import zipfile
from collections.abc import Callable
from pathlib import Path
from typing import Literal

SkipReason = Literal["frozen", "no-git", "off-main", "dirty", "ahead"]

_OWNER_REPO = "Soma-Yukihira/sofi-manager"
_GITHUB_API_LATEST_SHA = f"https://api.github.com/repos/{_OWNER_REPO}/commits/main"
_CODELOAD_ZIP_URL = f"https://codeload.github.com/{_OWNER_REPO}/zip/refs/heads/main"
_USER_AGENT = "sofi-manager-updater"
_NETWORK_TIMEOUT = 30  # seconds

ROOT = Path(__file__).resolve().parent.parent

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


def _is_frozen() -> bool:
    """True when running from a PyInstaller bundle (`sys.frozen` is set)."""
    return bool(getattr(sys, "frozen", False))


def skip_reason() -> SkipReason | None:
    """
    Reason auto-updates are silently disabled, or None if the updater can
    fast-forward this install on the next restart.

    Priority order (first match wins):
        - "frozen"   : PyInstaller .exe build; user must rebuild/reinstall.
        - "no-git"   : no `.git/` directory (ZIP / source-only download).
        - "off-main" : on a feature branch; updater protects local work.
        - "dirty"    : tracked files have uncommitted modifications.
        - "ahead"    : local commits not yet pushed to origin/main.

    The GUI surfaces "frozen" / "no-git" so .exe and ZIP users learn why
    their install will never auto-update, instead of silently lagging
    behind. The dev cases ("off-main" / "dirty" / "ahead") are returned
    here for completeness (callers like UPD-ZIP can branch on them) but
    are already surfaced on-demand by `fetch_and_status` — no passive
    banner, since devs intentionally sit in those states.
    """
    if _is_frozen():
        return "frozen"
    if not is_git_clone():
        return "no-git"
    if current_branch() != "main":
        return "off-main"
    if has_local_changes():
        return "dirty"
    if ahead_count() > 0:
        return "ahead"
    return None


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


# ----------------------------------------------------------------------
# ZIP-fallback updater (UPD-ZIP)
# ----------------------------------------------------------------------
#
# Users who downloaded the source as a ZIP from GitHub have no `.git/` and
# would otherwise never auto-update. We bypass git entirely:
#   1. Poll the GitHub API for the current SHA of refs/heads/main.
#   2. Compare against the SHA we last installed (stored in settings.json).
#      First launch with no stored SHA = adopt remote as baseline, no banner.
#   3. On restart, download the codeload ZIP, overwrite tracked files in
#      place. User-data files (bots.json, settings.json, grabs.db, key)
#      are gitignored, therefore absent from the ZIP, therefore untouched.
#
# Overwrite-only: files removed upstream linger as orphans. Acceptable for
# rare renames; the live code path is what the new ZIP defines.
#
# Frozen (.exe) installs are deliberately NOT supported here - the running
# binary is locked on Windows and unpacking source over a PyInstaller
# install would not change what executes. They keep the amber banner.


def _http_get_json(url: str) -> object:
    req = urllib.request.Request(
        url,
        headers={"User-Agent": _USER_AGENT, "Accept": "application/vnd.github+json"},
    )
    with urllib.request.urlopen(req, timeout=_NETWORK_TIMEOUT) as resp:
        return _json.loads(resp.read().decode("utf-8"))


def _http_get_bytes(url: str) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": _USER_AGENT})
    with urllib.request.urlopen(req, timeout=_NETWORK_TIMEOUT) as resp:
        return bytes(resp.read())


def fetch_remote_main_sha() -> str | None:
    """GET the SHA of the latest commit on origin/main, or None on failure.

    Failures are silent on purpose: a flaky network or GitHub API rate limit
    must never crash the GUI launch path.
    """
    try:
        data = _http_get_json(_GITHUB_API_LATEST_SHA)
    except (urllib.error.URLError, OSError, ValueError):
        return None
    except Exception:
        return None
    if not isinstance(data, dict):
        return None
    sha = data.get("sha")
    if isinstance(sha, str) and len(sha) == 40 and all(c in "0123456789abcdef" for c in sha):
        return sha
    return None


def _apply_zip_bytes(zip_bytes: bytes, dest: Path) -> tuple[bool, str]:
    """Extract a codeload ZIP onto `dest`, stripping the top-level prefix.

    Pure helper, no network. Guards against zip-slip (entries that resolve
    outside `dest`) and unexpected layouts (mixed top-level dirs).
    """
    try:
        with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
            names = zf.namelist()
            if not names:
                return False, "empty zip"
            # codeload ZIPs always wrap content in a single `<repo>-<sha>/`
            # directory; strip it so files land directly in `dest`.
            prefix = names[0].split("/", 1)[0] + "/"
            for n in names:
                if not n.startswith(prefix):
                    return False, "unexpected zip layout"
            dest_resolved = dest.resolve()
            for info in zf.infolist():
                rel = info.filename[len(prefix) :]
                if not rel:
                    continue
                target = (dest / rel).resolve()
                try:
                    target.relative_to(dest_resolved)
                except ValueError:
                    return False, f"zip-slip blocked: {info.filename}"
                if info.is_dir():
                    target.mkdir(parents=True, exist_ok=True)
                    continue
                target.parent.mkdir(parents=True, exist_ok=True)
                with zf.open(info) as src, open(target, "wb") as out:
                    shutil.copyfileobj(src, out)
    except (zipfile.BadZipFile, OSError) as e:
        return False, str(e)
    return True, "OK"


def apply_zip_update() -> tuple[bool, str, str | None]:
    """Fetch + extract the latest main ZIP onto this install. Returns
    `(ok, message, new_sha)`. Callers are expected to persist `new_sha`
    before re-execing the interpreter so the next launch knows the
    baseline.
    """
    if skip_reason() != "no-git":
        return False, "ZIP update only applies to non-git installs.", None
    new_sha = fetch_remote_main_sha()
    if new_sha is None:
        return False, "Impossible de joindre l'API GitHub.", None
    try:
        zip_bytes = _http_get_bytes(_CODELOAD_ZIP_URL)
    except (urllib.error.URLError, OSError) as e:
        return False, f"Telechargement echoue: {e}", None
    ok, msg = _apply_zip_bytes(zip_bytes, ROOT)
    if not ok:
        return False, msg, None
    return True, "OK", new_sha


def check_zip_in_background(
    installed_sha: str | None,
    on_baseline: Callable[[str], None],
    on_update_available: Callable[[str], None],
) -> None:
    """Fire-and-forget ZIP-mode check. No-op outside the no-git case.

    Three outcomes:
      - installed_sha is None  -> `on_baseline(remote)` (first launch).
      - installed_sha == remote -> silent (up to date).
      - otherwise               -> `on_update_available(remote)`.

    Callbacks fire on the worker thread; the caller is responsible for
    marshalling to Tk via `root.after(0, ...)`.
    """
    if skip_reason() != "no-git":
        return

    def _worker() -> None:
        try:
            remote = fetch_remote_main_sha()
            if remote is None:
                return
            if installed_sha is None:
                on_baseline(remote)
            elif installed_sha != remote:
                on_update_available(remote)
        except Exception:
            pass

    t = threading.Thread(target=_worker, name="updater-zip", daemon=True)
    t.start()

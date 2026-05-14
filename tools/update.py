"""
update.py — Selfbot Manager · cross-platform updater.

    python tools/update.py

Pulls the latest code from GitHub, refreshes Python deps inside the
detected venv (env/, venv/, .venv/) only if requirements.txt changed,
and prints a clean summary. Runtime files (bots.json, settings.json,
dist/) are gitignored and untouched.

Replaces the previous PowerShell + Bash duo with one Python entry point
that works on Windows / macOS / Linux without code duplication.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
IS_TTY = sys.stdout.isatty()


# ANSI palette (degrades to plain text when not on a TTY)
def _c(code: str) -> str:
    return f"\x1b[{code}m" if IS_TTY else ""

GOLD   = _c("38;2;212;175;55")
GREEN  = _c("38;2;74;222;128")
RED    = _c("38;2;248;113;113")
YELLOW = _c("38;2;251;191;36")
GRAY   = _c("38;2;156;163;175")
RESET  = _c("0")


def step(msg: str) -> None: print(f"{GRAY}->  {msg}{RESET}")
def ok(msg: str)   -> None: print(f"{GREEN}OK  {msg}{RESET}")
def warn(msg: str) -> None: print(f"{YELLOW}!   {msg}{RESET}")
def err(msg: str)  -> None: print(f"{RED}X   {msg}{RESET}", file=sys.stderr)


def _git(*args: str, capture: bool = True) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", *args],
        cwd=str(ROOT),
        capture_output=capture,
        text=True,
    )


def _find_pip() -> Path | None:
    pip_name = "pip.exe" if os.name == "nt" else "pip"
    scripts  = "Scripts" if os.name == "nt" else "bin"
    for venv in ("env", "venv", ".venv"):
        candidate = ROOT / venv / scripts / pip_name
        if candidate.exists():
            return candidate
    return None


def main() -> int:
    print()
    print(f"{GOLD}*  SELFBOT MANAGER  ·  UPDATER{RESET}")
    print(f"{GRAY}{'-' * 60}{RESET}")

    if not (ROOT / ".git").exists():
        err("Not a git repository.")
        print("  This folder was probably downloaded as a ZIP.")
        print("  Re-clone with:")
        print("    git clone https://github.com/Soma-Yukihira/sofi-manager.git")
        return 1

    old_hash = _git("rev-parse", "--short", "HEAD").stdout.strip()

    step("Checking remote...")
    fetch = _git("fetch", "--quiet")
    if fetch.returncode != 0:
        err("Could not reach GitHub. Check your internet connection.")
        return 1

    behind = int(_git("rev-list", "--count", "HEAD..@{u}").stdout.strip() or "0")
    ahead  = int(_git("rev-list", "--count", "@{u}..HEAD").stdout.strip() or "0")

    if behind == 0 and ahead == 0:
        ok(f"Already up to date  (commit {old_hash})")
        return 0

    if ahead > 0:
        warn(f"You have {ahead} local commit(s) not pushed.")

    step(f"Pulling latest changes  ({behind} commit(s) behind)...")
    pull = _git("pull", "--ff-only", capture=False)
    if pull.returncode != 0:
        err("git pull failed.")
        print("  Most common cause: a tracked file is locally modified.")
        print("  Either stash or commit, then re-run:")
        print("    git stash")
        print("    python tools/update.py")
        print("    git stash pop")
        return 1

    new_hash = _git("rev-parse", "--short", "HEAD").stdout.strip()

    diff_out = _git("diff", "--name-only", f"{old_hash}..{new_hash}").stdout
    changed_files = [line for line in diff_out.splitlines() if line]
    req_changed = "requirements.txt" in changed_files

    pip = _find_pip()
    if pip and req_changed:
        step(f"Installing updated dependencies  (venv: {pip.parent.parent.name}/)...")
        rc = subprocess.call(
            [str(pip), "install", "--quiet", "-r", "requirements.txt"],
            cwd=str(ROOT),
        )
        if rc != 0:
            err("pip install failed.")
            return rc
        ok("Dependencies refreshed")
    elif pip:
        step("requirements.txt unchanged — skipping pip")
    else:
        warn("No virtualenv detected (env/, venv/, .venv/).")
        print("    If new dependencies are required:")
        print("      pip install -r requirements.txt")

    print()
    ok("Up to date")
    print(f"    {GRAY}{old_hash}  ->  {new_hash}    ({len(changed_files)} file(s) changed){RESET}")
    print(f"    {GRAY}Your bots.json + settings.json are untouched.{RESET}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

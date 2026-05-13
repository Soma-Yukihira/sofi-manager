"""
release.py - Selfbot Manager - GitHub Release automation.

    python tools/release.py            # full release
    python tools/release.py --dry-run  # plan only, no tag / push / upload
    python tools/release.py --skip-tests

Steps, in order, each one a hard gate:

    1. Read __version__ / __repo__ from version.py (strict SemVer).
    2. Verify current branch is `main`.
    3. Verify the working tree is clean (no staged / unstaged / untracked).
    4. Verify the tag `v{__version__}` does not already exist (local + remote).
    5. Run the test suite (skippable with --skip-tests).
    6. Run `python tools/build.py` to produce dist/SelfbotManager/.
    7. Pack dist/SelfbotManager/ into a deterministic ZIP archive.
    8. Create the annotated tag and push it to origin.
    9. Create the GitHub Release via `gh` and upload the archive.

The script never commits build outputs - dist/ and build/ are gitignored.
Designed to run identically from PowerShell, cmd, or bash.
"""

from __future__ import annotations

import argparse
import os
import re
import runpy
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
VERSION_FILE = ROOT / "version.py"
BUILD_SCRIPT = ROOT / "tools" / "build.py"
DIST_FOLDER = ROOT / "dist" / "SelfbotManager"
RELEASE_DIR = ROOT / "dist" / "releases"

SEMVER_RE = re.compile(r"^\d+\.\d+\.\d+$")
IS_TTY = sys.stdout.isatty()


def _c(code: str) -> str:
    return f"\x1b[{code}m" if IS_TTY else ""

GOLD   = _c("38;2;212;175;55")
GREEN  = _c("38;2;74;222;128")
RED    = _c("38;2;248;113;113")
YELLOW = _c("38;2;251;191;36")
GRAY   = _c("38;2;156;163;175")
RESET  = _c("0")


def step(msg: str) -> None: print(f"{GRAY}->  {msg}{RESET}", flush=True)
def ok(msg: str)   -> None: print(f"{GREEN}OK  {msg}{RESET}", flush=True)
def warn(msg: str) -> None: print(f"{YELLOW}!   {msg}{RESET}", flush=True)
def err(msg: str)  -> None: print(f"{RED}X   {msg}{RESET}", file=sys.stderr, flush=True)


class ReleaseError(RuntimeError):
    """Any precondition / step failure - caught in main() for a clean exit."""


def _run(cmd: list[str], **kwargs) -> subprocess.CompletedProcess:
    """Run a command, default cwd = repo root, default text=True."""
    kwargs.setdefault("cwd", str(ROOT))
    kwargs.setdefault("text", True)
    return subprocess.run(cmd, **kwargs)


def _git(*args: str, capture: bool = True) -> subprocess.CompletedProcess:
    return _run(
        ["git", *args],
        capture_output=capture,
    )


def _read_version() -> tuple[str, str]:
    if not VERSION_FILE.exists():
        raise ReleaseError(f"version.py not found at {VERSION_FILE}")
    ns = runpy.run_path(str(VERSION_FILE))
    version = ns.get("__version__")
    repo = ns.get("__repo__")
    if not isinstance(version, str) or not version:
        raise ReleaseError("version.py: __version__ is missing or empty")
    if not isinstance(repo, str) or "/" not in repo:
        raise ReleaseError("version.py: __repo__ must be 'owner/name'")
    if not SEMVER_RE.match(version):
        raise ReleaseError(
            f"__version__ = {version!r} is not strict SemVer (MAJOR.MINOR.PATCH)"
        )
    return version, repo


def _check_branch(dry_run: bool) -> None:
    res = _git("rev-parse", "--abbrev-ref", "HEAD")
    if res.returncode != 0:
        raise ReleaseError("not a git repository (git rev-parse failed)")
    branch = res.stdout.strip()
    if branch == "main":
        return
    if dry_run:
        warn(f"current branch is {branch!r} (not 'main') - allowed in --dry-run only")
        warn("a real release will refuse this branch; re-run on 'main' after merging")
        return
    raise ReleaseError(f"current branch is {branch!r}, releases must come from 'main'")


def _check_clean_tree() -> None:
    res = _git("status", "--porcelain")
    if res.returncode != 0:
        raise ReleaseError("git status failed")
    if res.stdout.strip():
        listing = "\n    ".join(res.stdout.strip().splitlines())
        raise ReleaseError(
            "working tree is not clean - commit or stash first:\n    " + listing
        )


def _check_tag_free(tag: str) -> None:
    local = _git("rev-parse", "-q", "--verify", f"refs/tags/{tag}")
    if local.returncode == 0:
        raise ReleaseError(f"tag {tag} already exists locally")
    remote = _git("ls-remote", "--tags", "origin", tag)
    if remote.returncode != 0:
        raise ReleaseError("could not query origin for existing tags (git ls-remote failed)")
    if remote.stdout.strip():
        raise ReleaseError(f"tag {tag} already exists on origin")


def _check_gh_ready() -> None:
    if shutil.which("gh") is None:
        raise ReleaseError("GitHub CLI 'gh' not found in PATH - install from https://cli.github.com/")
    auth = _run(["gh", "auth", "status"], capture_output=True)
    if auth.returncode != 0:
        raise ReleaseError("gh is not authenticated - run `gh auth login` first")


def _run_tests() -> None:
    tests_dir = ROOT / "tests"
    if not tests_dir.exists():
        warn("no tests/ directory - skipping test step")
        return
    step("running tests (python -m pytest tests/)")
    res = _run([sys.executable, "-m", "pytest", "-q", "tests"])
    if res.returncode != 0:
        raise ReleaseError("tests failed - release aborted")
    ok("tests passed")


def _run_build() -> None:
    step("running build (python tools/build.py --clean)")
    res = _run([sys.executable, str(BUILD_SCRIPT), "--clean"])
    if res.returncode != 0:
        raise ReleaseError("build failed - release aborted")
    if not DIST_FOLDER.exists() or not DIST_FOLDER.is_dir():
        raise ReleaseError(f"expected build output not found: {DIST_FOLDER}")
    exe = DIST_FOLDER / ("SelfbotManager.exe" if os.name == "nt" else "SelfbotManager")
    if not exe.exists():
        raise ReleaseError(f"built executable missing: {exe}")
    ok(f"build produced {DIST_FOLDER.relative_to(ROOT)}/")


# Fixed timestamp for deterministic archives: 2020-01-01 00:00:00 (local).
# ZIP can't store anything before 1980 anyway.
_ZIP_EPOCH = (2020, 1, 1, 0, 0, 0)


def _pack_archive(version: str) -> Path:
    RELEASE_DIR.mkdir(parents=True, exist_ok=True)
    archive_name = f"SelfbotManager-v{version}-windows.zip"
    archive_path = RELEASE_DIR / archive_name
    if archive_path.exists():
        archive_path.unlink()

    step(f"packing deterministic archive -> {archive_path.relative_to(ROOT)}")

    # Sorted walk + fixed mtime + fixed external attrs => byte-stable output.
    files: list[Path] = sorted(
        (p for p in DIST_FOLDER.rglob("*") if p.is_file()),
        key=lambda p: p.relative_to(DIST_FOLDER).as_posix(),
    )
    if not files:
        raise ReleaseError(f"{DIST_FOLDER} is empty - nothing to pack")

    with zipfile.ZipFile(
        archive_path,
        mode="w",
        compression=zipfile.ZIP_DEFLATED,
        compresslevel=9,
    ) as zf:
        for f in files:
            arcname = f"SelfbotManager/{f.relative_to(DIST_FOLDER).as_posix()}"
            info = zipfile.ZipInfo(filename=arcname, date_time=_ZIP_EPOCH)
            info.compress_type = zipfile.ZIP_DEFLATED
            # 0o644 for regular files, stored in the high 16 bits.
            info.external_attr = (0o644 & 0xFFFF) << 16
            info.create_system = 0  # MS-DOS / FAT - cross-platform stable
            with f.open("rb") as src:
                zf.writestr(info, src.read())

    size_mb = archive_path.stat().st_size / (1024 * 1024)
    ok(f"archive ready ({size_mb:.1f} MiB)")
    return archive_path


def _create_and_push_tag(tag: str, version: str) -> None:
    step(f"creating annotated tag {tag}")
    res = _git("tag", "-a", tag, "-m", f"Release {version}", capture=False)
    if res.returncode != 0:
        raise ReleaseError(f"git tag {tag} failed")

    step(f"pushing tag {tag} to origin")
    res = _git("push", "origin", tag, capture=False)
    if res.returncode != 0:
        # Roll back the local tag so a re-run is clean.
        _git("tag", "-d", tag)
        raise ReleaseError("git push failed - local tag rolled back")
    ok(f"tag {tag} pushed")


def _create_github_release(tag: str, version: str, archive: Path, repo: str) -> None:
    title = f"Selfbot Manager {tag}"
    notes = (
        f"Automated release for {tag}.\n\n"
        f"Download `{archive.name}`, unzip, and run `SelfbotManager.exe`.\n\n"
        f"See [CHANGELOG / commit history]"
        f"(https://github.com/{repo}/commits/{tag}) for details."
    )
    step(f"creating GitHub release {tag} on {repo}")
    res = _run(
        [
            "gh", "release", "create", tag,
            str(archive),
            "--repo", repo,
            "--title", title,
            "--notes", notes,
        ],
    )
    if res.returncode != 0:
        raise ReleaseError(
            "gh release create failed - the tag was pushed; "
            f"either re-run `gh release create {tag}` manually or delete the tag "
            f"with `git push --delete origin {tag}` before retrying."
        )
    ok(f"release {tag} published")


def _print_plan(version: str, tag: str, repo: str, dry_run: bool, skip_tests: bool) -> None:
    mode = "DRY RUN" if dry_run else "LIVE"
    print()
    print(f"{GOLD}*  SELFBOT MANAGER  *  RELEASE  ({mode}){RESET}")
    print(f"{GRAY}{'-' * 60}{RESET}")
    print(f"    repo     : {repo}")
    print(f"    version  : {version}")
    print(f"    tag      : {tag}")
    print(f"    tests    : {'SKIPPED' if skip_tests else 'pytest tests/'}")
    print(f"    build    : python tools/build.py --clean")
    print(f"    archive  : dist/releases/SelfbotManager-v{version}-windows.zip")
    print()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Build and publish a GitHub release for Selfbot Manager.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Run all preflight checks + build + pack archive, but do NOT tag, push, or publish.",
    )
    parser.add_argument(
        "--skip-tests",
        action="store_true",
        help="Skip the pytest step (use only when tests were just run in CI).",
    )
    args = parser.parse_args(argv)

    try:
        version, repo = _read_version()
        tag = f"v{version}"

        _print_plan(version, tag, repo, args.dry_run, args.skip_tests)

        step("verifying current branch is 'main'")
        _check_branch(args.dry_run)
        if not args.dry_run:
            ok("on main")

        step("verifying working tree is clean")
        _check_clean_tree()
        ok("tree clean")

        step(f"verifying tag {tag} does not exist")
        _check_tag_free(tag)
        ok(f"tag {tag} free")

        if not args.dry_run:
            step("verifying GitHub CLI 'gh' is installed and authenticated")
            _check_gh_ready()
            ok("gh ready")

        if args.skip_tests:
            warn("--skip-tests: not running pytest")
        else:
            _run_tests()

        _run_build()
        archive = _pack_archive(version)

        if args.dry_run:
            print()
            ok("DRY RUN complete - tag NOT created, release NOT published")
            print(f"    archive ready: {archive.relative_to(ROOT)}")
            return 0

        _create_and_push_tag(tag, version)
        _create_github_release(tag, version, archive, repo)

        print()
        ok(f"Release {tag} published successfully")
        print(f"    https://github.com/{repo}/releases/tag/{tag}")
        return 0

    except ReleaseError as e:
        err(str(e))
        return 1
    except KeyboardInterrupt:
        err("interrupted")
        return 130


if __name__ == "__main__":
    sys.exit(main())

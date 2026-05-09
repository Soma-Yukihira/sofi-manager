"""
cli.py — Selfbot Manager · headless / VPS-friendly entry point.

Usage:
    python cli.py list                        # list configured bots
    python cli.py show NAME                   # full config of one bot
    python cli.py add                         # interactive wizard
    python cli.py rm NAME                     # remove a bot
    python cli.py run                         # run all configured bots
    python cli.py run NAME [NAME ...]         # run one or more by name

Use --no-color to strip ANSI escapes (logs to file, dumb terminal).
Use --help on any command for details.
"""

from __future__ import annotations

import argparse
import json
import os
import signal
import sys
import time
import uuid
from pathlib import Path

# Allow `cli.py` to be run from anywhere
_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE))

from bot_core import SelfBot, default_config, sanitize_config  # noqa: E402


CONFIG_PATH = _HERE / "bots.json"


# =============================================
# ANSI palette (24-bit → graceful fallback)
# =============================================

class Color:
    RESET   = "\x1b[0m"
    BOLD    = "\x1b[1m"
    DIM     = "\x1b[2m"
    GOLD    = "\x1b[38;2;212;175;55m"
    GOLDBR  = "\x1b[38;2;244;208;63m"
    GREEN   = "\x1b[38;2;74;222;128m"
    RED     = "\x1b[38;2;248;113;113m"
    YELLOW  = "\x1b[38;2;251;191;36m"
    GRAY    = "\x1b[38;2;156;163;175m"
    DIMGRAY = "\x1b[38;2;107;114;128m"


LEVEL_COLOR = {
    "info":    Color.GRAY,
    "success": Color.GREEN,
    "error":   Color.RED,
    "warn":    Color.YELLOW,
    "system":  Color.GOLD,
}


def _enable_windows_vt():
    """Enable VT100 ANSI sequences on legacy Windows consoles."""
    if os.name != "nt":
        return
    try:
        import ctypes
        kernel32 = ctypes.windll.kernel32
        h = kernel32.GetStdHandle(-11)  # STD_OUTPUT_HANDLE
        # ENABLE_PROCESSED_OUTPUT | ENABLE_VIRTUAL_TERMINAL_PROCESSING
        kernel32.SetConsoleMode(h, 7)
    except Exception:
        pass


def _strip_colors():
    for attr in dir(Color):
        if not attr.startswith("_") and attr.isupper():
            setattr(Color, attr, "")


def cprint(text: str = "", end: str = "\n"):
    print(text, end=end, flush=True)


# =============================================
# Storage
# =============================================

def load_bots() -> list[dict]:
    if not CONFIG_PATH.exists():
        return []
    try:
        bots = json.loads(CONFIG_PATH.read_text(encoding="utf-8")).get("bots", [])
        return [sanitize_config(bot) for bot in bots]
    except Exception as e:
        cprint(f"{Color.RED}Failed to read {CONFIG_PATH}: {e}{Color.RESET}")
        return []


def save_bots(bots: list[dict]):
    tmp = CONFIG_PATH.with_name(CONFIG_PATH.name + ".tmp")
    tmp.write_text(
        json.dumps({"bots": bots}, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    tmp.replace(CONFIG_PATH)


def find_bot(bots, name_or_id: str):
    nl = name_or_id.lower()
    for b in bots:
        if b.get("_id") == name_or_id or (b.get("name") or "").lower() == nl:
            return b
    return None


def header(title: str):
    cprint()
    cprint(f"{Color.GOLD}⚜  {Color.BOLD}{title}{Color.RESET}")
    cprint(f"{Color.DIMGRAY}{'-' * 60}{Color.RESET}")


# =============================================
# Commands
# =============================================

def cmd_list(args):
    bots = load_bots()
    header(f"Configured bots  ({len(bots)})")
    if not bots:
        cprint(f"{Color.DIMGRAY}No bots yet. Add one with:{Color.RESET}  python cli.py add")
        return 0
    for b in bots:
        name = b.get("name") or "(no name)"
        token = b.get("token") or ""
        token_tag = f"…{token[-6:]}" if token else f"{Color.RED}MISSING{Color.RESET}"
        drop = b.get("drop_channel") or 0
        listen = len(b.get("all_channels") or [])
        wish = len(b.get("wishlist") or [])
        series = len(b.get("wishlist_series") or [])
        night = "on" if b.get("night_pause_enabled") else "off"
        cprint(f"  {Color.BOLD}{Color.GOLDBR}⚙  {name}{Color.RESET}")
        cprint(f"     {Color.DIMGRAY}token  {Color.RESET} {token_tag}")
        cprint(f"     {Color.DIMGRAY}drop   {Color.RESET} {drop}")
        cprint(f"     {Color.DIMGRAY}listen {Color.RESET} {listen} channel(s)")
        cprint(f"     {Color.DIMGRAY}wishlist{Color.RESET} {wish} chars · {series} series")
        cprint(f"     {Color.DIMGRAY}night  {Color.RESET} {night}")
        cprint()
    return 0


def cmd_show(args):
    bots = load_bots()
    bot = find_bot(bots, args.name)
    if not bot:
        cprint(f"{Color.RED}No bot named '{args.name}'.{Color.RESET}")
        return 1
    redacted = dict(bot)
    if redacted.get("token"):
        t = redacted["token"]
        redacted["token"] = f"{t[:6]}…{t[-6:]}"
    print(json.dumps(redacted, indent=2, ensure_ascii=False))
    return 0


def _ask(prompt: str, default: str | None = None, allow_empty: bool = False) -> str:
    suffix = f" {Color.DIMGRAY}[{default}]{Color.RESET}" if default else ""
    while True:
        raw = input(f"{Color.GOLD}? {Color.RESET}{prompt}{suffix}: ").strip()
        if raw:
            return raw
        if default is not None:
            return default
        if allow_empty:
            return ""
        cprint(f"  {Color.YELLOW}value required{Color.RESET}")


def _ask_int(prompt: str, default: int | None = None) -> int:
    while True:
        raw = _ask(prompt, str(default) if default is not None else None)
        try:
            return int(raw)
        except ValueError:
            cprint(f"  {Color.YELLOW}not a number{Color.RESET}")


def _ask_list(prompt: str) -> list[int]:
    cprint(f"{Color.GOLD}? {Color.RESET}{prompt}  {Color.DIMGRAY}(one ID per line, blank to finish){Color.RESET}")
    out = []
    while True:
        raw = input(f"  {Color.DIMGRAY}>{Color.RESET} ").strip()
        if not raw:
            return out
        try:
            out.append(int(raw))
        except ValueError:
            cprint(f"  {Color.YELLOW}skipping (not an int){Color.RESET}")


def cmd_add(args):
    header("New bot wizard")
    cprint(f"{Color.DIMGRAY}Press Ctrl+C to cancel.{Color.RESET}\n")

    bots = load_bots()
    cfg = default_config()
    try:
        cfg["name"] = _ask("Bot name")
        if find_bot(bots, cfg["name"]):
            cprint(f"{Color.RED}A bot with this name already exists. Aborting.{Color.RESET}")
            return 1
        cfg["token"] = _ask("Discord token")
        cfg["drop_channel"] = _ask_int("Drop channel ID")
        more = _ask_list("Additional channels to listen on")
        cfg["all_channels"] = list(dict.fromkeys([cfg["drop_channel"], *more]))

        # everything else: defaults are fine; keep wizard short
        cprint()
        cprint(f"{Color.DIMGRAY}Defaults will be used for timing, scoring, night pause and wishlist.{Color.RESET}")
        cprint(f"{Color.DIMGRAY}Edit bots.json or use the GUI for fine-tuning.{Color.RESET}")
    except (EOFError, KeyboardInterrupt):
        cprint(f"\n{Color.YELLOW}Cancelled.{Color.RESET}")
        return 130

    cfg["_id"] = str(uuid.uuid4())
    sanitize_config(cfg)
    bots.append(cfg)
    save_bots(bots)

    cprint()
    cprint(f"{Color.GREEN}OK{Color.RESET}  Bot '{cfg['name']}' saved.")
    cprint(f"   Run with:  {Color.BOLD}python cli.py run \"{cfg['name']}\"{Color.RESET}")
    return 0


def cmd_rm(args):
    bots = load_bots()
    bot = find_bot(bots, args.name)
    if not bot:
        cprint(f"{Color.RED}No bot named '{args.name}'.{Color.RESET}")
        return 1
    if not args.yes:
        confirm = input(
            f"{Color.YELLOW}Delete '{bot.get('name')}'? this cannot be undone. (y/N) {Color.RESET}"
        ).strip().lower()
        if confirm not in ("y", "yes"):
            cprint("aborted.")
            return 0
    bots = [b for b in bots if b is not bot]
    save_bots(bots)
    cprint(f"{Color.GREEN}OK{Color.RESET}  Deleted '{bot.get('name')}'.")
    return 0


def cmd_run(args):
    bots_cfg = load_bots()
    if not bots_cfg:
        cprint(f"{Color.RED}No bots configured. Run `python cli.py add` first.{Color.RESET}")
        return 1

    if args.names:
        wanted = {n.lower() for n in args.names}
        selected = [b for b in bots_cfg if (b.get("name") or "").lower() in wanted]
        missing = wanted - {(b.get("name") or "").lower() for b in selected}
        if missing:
            cprint(f"{Color.RED}Unknown bot(s): {', '.join(missing)}{Color.RESET}")
            return 1
    else:
        selected = bots_cfg

    header(f"Starting {len(selected)} bot(s)")
    instances: list[SelfBot] = []
    name_pad = max((len(b.get("name") or "") for b in selected), default=8)
    name_pad = min(max(name_pad, 8), 18)

    def _on_status(bot, status):
        tag = {
            "running":  f"{Color.GREEN}● running{Color.RESET}",
            "starting": f"{Color.YELLOW}● connecting{Color.RESET}",
            "stopped":  f"{Color.DIMGRAY}● stopped{Color.RESET}",
            "error":    f"{Color.RED}● error{Color.RESET}",
        }.get(status, status)
        prefix = f"{Color.BOLD}{Color.GOLD}{(bot.config.get('name') or '?'):>{name_pad}}{Color.RESET}"
        cprint(f"{prefix}  {tag}")

    for cfg in selected:
        bot = SelfBot(cfg)
        bot.status_callback = (lambda s, b=bot: _on_status(b, s))
        bot.start()
        instances.append(bot)

    cprint(f"{Color.DIMGRAY}Press Ctrl+C to stop. Logs are written below.{Color.RESET}")
    cprint()

    stop_requested = {"v": False}

    def _signal_handler(*_):
        stop_requested["v"] = True
    try:
        signal.signal(signal.SIGINT, _signal_handler)
        signal.signal(signal.SIGTERM, _signal_handler)
    except Exception:
        pass  # not all platforms have SIGTERM via signal module

    try:
        while not stop_requested["v"]:
            any_drained = False
            for bot in instances:
                drained = 0
                while drained < 100:
                    try:
                        level, line = bot.log_queue.get_nowait()
                    except Exception:
                        break
                    color = LEVEL_COLOR.get(level, "")
                    name = (bot.config.get("name") or "?")[:name_pad]
                    prefix = f"{Color.BOLD}{Color.GOLD}{name:>{name_pad}}{Color.RESET}"
                    cprint(f"{prefix}  {color}{line}{Color.RESET}")
                    drained += 1
                    any_drained = True
            if not any_drained:
                time.sleep(0.12)
    except KeyboardInterrupt:
        pass

    cprint()
    cprint(f"{Color.YELLOW}⚜  Stopping bots...{Color.RESET}")
    for bot in instances:
        try:
            bot.stop()
        except Exception:
            pass

    # drain remaining logs for ~3s
    deadline = time.time() + 3
    while time.time() < deadline:
        any_drained = False
        for bot in instances:
            try:
                while True:
                    level, line = bot.log_queue.get_nowait()
                    color = LEVEL_COLOR.get(level, "")
                    name = (bot.config.get("name") or "?")[:name_pad]
                    prefix = f"{Color.BOLD}{Color.GOLD}{name:>{name_pad}}{Color.RESET}"
                    cprint(f"{prefix}  {color}{line}{Color.RESET}")
                    any_drained = True
            except Exception:
                pass
        if not any_drained:
            break
        time.sleep(0.1)

    cprint(f"{Color.GOLD}⚜  Done.{Color.RESET}")
    return 0


# =============================================
# Argparse plumbing
# =============================================

def build_parser():
    p = argparse.ArgumentParser(
        prog="cli.py",
        description="Selfbot Manager · headless interface (VPS-friendly).",
    )
    p.add_argument("--no-color", action="store_true",
                    help="Disable ANSI colors (useful for log files / dumb TTYs).")
    sub = p.add_subparsers(dest="command", required=True, metavar="COMMAND")

    sub.add_parser("list", help="List all configured bots.")

    pshow = sub.add_parser("show", help="Show a bot's full config (token redacted).")
    pshow.add_argument("name", help="Bot name or _id.")

    sub.add_parser("add", help="Interactive wizard to add a new bot.")

    prm = sub.add_parser("rm", help="Remove a bot.")
    prm.add_argument("name", help="Bot name or _id.")
    prm.add_argument("-y", "--yes", action="store_true",
                      help="Skip confirmation prompt.")

    prun = sub.add_parser("run", help="Run one or more bots in the foreground.")
    prun.add_argument("names", nargs="*",
                       help="Bot names to run (default: all configured bots).")

    return p


def main(argv=None):
    # Force UTF-8 stdout so glyphs like ⚜ render on Windows (cp1252 default)
    # and don't crash when output is piped or redirected to a file.
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass

    parser = build_parser()
    args = parser.parse_args(argv)

    if args.no_color or not sys.stdout.isatty():
        _strip_colors()
    else:
        _enable_windows_vt()

    handlers = {
        "list":  cmd_list,
        "show":  cmd_show,
        "add":   cmd_add,
        "rm":    cmd_rm,
        "run":   cmd_run,
    }
    fn = handlers[args.command]
    try:
        return fn(args) or 0
    except KeyboardInterrupt:
        cprint(f"\n{Color.YELLOW}Interrupted.{Color.RESET}")
        return 130


if __name__ == "__main__":
    sys.exit(main())

<div align="center">

<img src="docs/images/banner.svg" alt="SOFI Manager" width="100%">

<p>
  <a href="README.md"><b>English</b></a> ·
  <a href="README.fr.md">Français</a>
</p>

<p><i>Premium black &amp; gold GUI to orchestrate multiple Discord SOFI selfbots in parallel.</i></p>

<p>
  <a href="https://github.com/Soma-Yukihira/sofi-manager/actions/workflows/ci.yml"><img src="https://img.shields.io/github/actions/workflow/status/Soma-Yukihira/sofi-manager/ci.yml?branch=main&style=flat-square&labelColor=0a0a0a&color=d4af37&label=CI" alt="CI"></a>
  <img src="https://img.shields.io/badge/python-3.10%2B-d4af37?style=flat-square&labelColor=0a0a0a" alt="Python 3.10+">
  <img src="https://img.shields.io/badge/license-MIT-d4af37?style=flat-square&labelColor=0a0a0a" alt="MIT License">
  <img src="https://img.shields.io/badge/platform-Windows%20%7C%20macOS%20%7C%20Linux-d4af37?style=flat-square&labelColor=0a0a0a" alt="Cross-platform">
  <img src="https://img.shields.io/badge/UI-CustomTkinter-d4af37?style=flat-square&labelColor=0a0a0a" alt="CustomTkinter">
</p>

</div>

> [!WARNING]
> **Selfbots violate the [Discord Terms of Service](https://discord.com/terms).**
> Running this on your account may result in suspension or permanent ban.
> This project is provided for educational purposes only — **use at your own risk**.

---

## ✨ Features

- 🪶 **Multi-bot** — manage any number of selfbots from a single window, each with its own thread, asyncio loop and config
- 🎴 **Smart card picking** — rarity + popularity scoring with wishlist override (characters & series)
- 🌙 **Night pause** — random sleep window between 22:00 and 01:00 to mimic human behavior
- 🌍 **Multilingual SOFI detection** — drop & cooldown messages parsed in **French and English**
- 🎨 **Premium theming** — dark and light presets + per-color customization (17 slots)
- 📜 **Live logs** — color-coded console per bot, with a diagnostic feed of every SOFI message received
- 💾 **Local-first** — config stays on disk in `bots.json`; tokens are Fernet-encrypted with a key kept in the OS keyring (file fallback under `%APPDATA%/sofi-manager/`)

---

## 📸 Screenshots

|                                 |                                |
| :-----------------------------: | :----------------------------: |
| ![Dark mode](docs/images/screenshot-dark.png) | ![Light mode](docs/images/screenshot-light.png) |
| _Dark preset_                   | _Light preset_                 |

---

## 🚀 Quick start

```bash
git clone https://github.com/Soma-Yukihira/sofi-manager.git
cd sofi-manager
python -m venv env
# Windows
.\env\Scripts\Activate.ps1
# macOS / Linux
# source env/bin/activate

pip install -r requirements.txt
python main.py
```

The GUI opens. Click **+ ADD BOT**, fill in your token + drop channel, **Save**, then **▶ Start**.

### Optional · Standalone Windows .exe

Skip Python entirely with a one-command build:

```bash
python tools/build.py
```

Produces `dist/SelfbotManager/SelfbotManager.exe` — double-click to run.
See the [Building](../../wiki/Building) wiki page for options
(`--onefile`, `--clean`) and runtime path strategy.

### Optional · Pin to taskbar (Windows)

```bash
python tools/create_shortcut.py
```

Generates `Selfbot Manager.lnk` with the gold ⚜ icon, auto-pointing at
the `.exe` if you built one, otherwise at the venv `pythonw.exe`. Drag
it onto your taskbar (or right-click → *Pin to taskbar*) — launches the
app without a console window.

### Updating

**Discord-style auto-update (git clones).** On startup the app checks
`origin/main` in a background thread. When new commits land, a gold
banner appears at the top of the window: *Mise à jour disponible —
Redémarrez pour appliquer*. Click **Redémarrer** and the app applies
`git pull --ff-only`, re-execs Python, and you are running the new
code. No release file, no manual step — every commit on `main` is a
release.

The auto-updater adapts to your install:
- **Git clone** — `git pull --ff-only origin main`, then re-exec.
- **ZIP download** (no `.git/`) — fetches `main` from
  `codeload.github.com` and overwrites tracked files in place. Same
  banner, same restart flow.
- **Frozen `.exe`** — skipped; a passive amber banner points at a
  rebuild from a fresh clone.
- Also skipped on a non-`main` branch, with local commits ahead, or
  with uncommitted tracked-file modifications.
- `bots.json`, `settings.json` and `grabs.db` are gitignored — they
  survive every update untouched.

**Manual update** (verbose CLI summary, also useful on a VPS):

```bash
python tools/update.py
```

Same command on Windows, macOS, and Linux. Refreshes Python deps if
`requirements.txt` changed and prints a clean diff summary.

### Headless / VPS

For servers without a display, a CLI shares the same `bots.json` and core:

```bash
python cli.py add                     # interactive bot wizard
python cli.py list                    # show configured bots
python cli.py run                     # run all in the foreground
sudo ./tools/install-systemd.sh       # one-shot systemd service installer
```

See the [VPS Deployment wiki page](../../wiki/VPS-Deployment) for the full
guide, including `tmux`, `systemd` hardening, and pushing config from the
GUI to the server.

📖 **Full documentation in the [Wiki](../../wiki).**

---

## 📂 Project structure

```
sofi-manager/
├── main.py              # GUI launch shim (pre-import update hook)
├── cli.py               # Headless / VPS launch shim
├── sofi_manager/        # Runtime package — every module the app actually loads
│   ├── gui.py           #   CustomTkinter UI + theme system + update banner
│   ├── cli.py           #   CLI subcommands (list / show / add / rm / run)
│   ├── bot_core.py      #   SelfBot class + orchestration
│   ├── parsing.py       #   SOFI message parsers (FR + EN, pure)
│   ├── scoring.py       #   card scoring + wishlist override (pure)
│   ├── crypto.py        #   Fernet token encryption (OS keyring)
│   ├── paths.py         #   bundle_dir() / user_dir() resolution
│   ├── storage.py       #   SQLite grab history + legacy DB migration
│   ├── updater.py       #   git + ZIP-codeload auto-updater
│   └── _migrations.py   #   one-shot cleanup of pre-refactor root .py files
├── selfbot-manager.spec # PyInstaller spec (driven by tools/build.py)
├── tools/               # build / update / shortcut / systemd installer
├── assets/app.ico       # gold ⚜ icon, bundled into the .exe
├── requirements.txt     # discord.py-self, customtkinter, curl_cffi
├── tests/               # pytest unit tests
├── docs/
│   ├── wiki/            # Wiki source pages (EN + FR, auto-synced to GitHub Wiki)
│   └── images/          # Banner + screenshots
└── LICENSE              # MIT
```

Runtime files `bots.json` (encrypted tokens + bot configs),
`settings.json` (theme prefs + updater state) and `grabs.db` (SQLite
grab history) are created on first use and gitignored.

---

## 📚 Documentation

The [Wiki](../../wiki) covers each topic in depth:

| Page | What's inside |
| ---- | ------------- |
| [Installation](../../wiki/Installation) | Python setup, venv, dependencies |
| [Building](../../wiki/Building) | One-command standalone Windows .exe |
| [Configuration](../../wiki/Configuration) | Every field of the GUI explained |
| [Theming](../../wiki/Theming) | Presets and 17-slot color customization |
| [Updating](../../wiki/Updating) | In-app updater, ZIP fallback, safety rails |
| [VPS Deployment](../../wiki/VPS-Deployment) | CLI, `tmux`, `systemd` hardening |
| [Architecture](../../wiki/Architecture) | How bots, threads and event loops are wired |
| [Troubleshooting](../../wiki/Troubleshooting) | Common errors + the `📥 SOFI:` debug log |
| [Discord ToS Notice](../../wiki/Discord-ToS) | Risks and what to expect |

---

## 🤝 Contributing

PRs are welcome. Read [CONTRIBUTING.md](CONTRIBUTING.md) before opening one.

For bugs, open an [issue](../../issues/new) with the `📥 SOFI:` log lines from
your run — they pinpoint format changes on SOFI's side instantly.

---

## 📄 License

[MIT](LICENSE) © Soma-Yukihira.

This software is provided "as is", without warranty of any kind. By using it,
you acknowledge the risks described in the warning above.

<div align="center">

<img src="docs/images/banner.svg" alt="SOFI Manager" width="100%">

<p>
  <a href="README.md"><b>English</b></a> ·
  <a href="README.fr.md">Français</a>
</p>

<p><i>Premium black &amp; gold GUI to orchestrate multiple Discord SOFI selfbots in parallel.</i></p>

<p>
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
- 💾 **Local-first** — config and tokens stay on disk in `bots.json`, never sent anywhere

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
.\env\Scripts\activate
# macOS / Linux
# source env/bin/activate

pip install -r requirements.txt
python main.py
```

The GUI opens. Click **+ ADD BOT**, fill in your token + drop channel, **Save**, then **▶ Start**.

### Optional · Pin to taskbar (Windows)

```powershell
.\tools\create-shortcut.ps1
```

This generates `Selfbot Manager.lnk` with the gold ⚜ icon. Drag it onto your
taskbar (or right-click → *Pin to taskbar*) — launches the app without a
console window.

📖 **Full documentation in the [Wiki](../../wiki).**

---

## 📂 Project structure

```
sofi-manager/
├── main.py              # GUI launcher
├── gui.py               # CustomTkinter interface + theme system
├── bot_core.py          # SelfBot class + parsing/scoring logic
├── requirements.txt     # discord.py-self, customtkinter
├── docs/
│   ├── wiki/            # Wiki source pages (EN + FR)
│   └── images/          # Banner + screenshots
└── LICENSE              # MIT
```

The runtime files `bots.json` (tokens) and `settings.json` (theme prefs) are
created on first use and gitignored.

---

## 📚 Documentation

The [Wiki](../../wiki) covers each topic in depth:

| Page | What's inside |
| ---- | ------------- |
| [Installation](../../wiki/Installation) | Python setup, venv, dependencies |
| [Configuration](../../wiki/Configuration) | Every field of the GUI explained |
| [Theming](../../wiki/Theming) | Presets and 17-slot color customization |
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

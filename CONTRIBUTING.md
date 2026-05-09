# Contributing

Thanks for considering a contribution. This is a small project — keep PRs
small and focused.

> [English] · [Français](CONTRIBUTING.fr.md)

---

## 🐛 Reporting bugs

Open an [issue](../../issues/new) with:

1. **What you did** — the action you performed in the GUI.
2. **What happened** — the actual behavior, including the **`📥 SOFI:` log
   lines** from the moment of failure. Those lines are the single most useful
   diagnostic — paste them verbatim.
3. **What you expected** — the intended behavior.
4. **Environment** — OS, Python version (`python --version`), package
   versions (`pip list | grep -E "discord|customtkinter"`).

Never paste your token. Redact it as `XXX.YYY.ZZZ` if it appears anywhere.

---

## 💡 Suggesting features

Open an issue describing the use case before writing code. A 3-line proposal
("today X is painful, I'd like Y") saves everyone time.

---

## 🛠 Development setup

```bash
git clone https://github.com/Soma-Yukihira/sofi-manager.git
cd sofi-manager
python -m venv env
.\env\Scripts\activate          # Windows
# source env/bin/activate       # macOS / Linux
pip install -r requirements.txt
python main.py
```

Run the lightweight core tests first:

```bash
python -m unittest
```

Then smoke-test UI changes manually:

- Start the GUI, add a bot, save, restart — config persists.
- Toggle dark/light theme, customize a color, restart — settings persist.
- Edit a wishlist with duplicates and mixed case — saving sorts and
  deduplicates.

---

## 🧱 Code style

- Stay close to the existing style. Prefer readability over cleverness.
- No new dependencies without discussion.
- Keep `bot_core.py` UI-agnostic: it must remain importable without a
  display.
- Keep `gui.py` Discord-agnostic: don't add network logic there.

---

## 📜 Pull requests

1. Fork, branch from `main`.
2. One concern per PR — small diffs review faster.
3. Write a clear description: what changed, why, and how you tested it.
4. By submitting a PR you agree that your contribution is licensed under the
   project's [MIT License](LICENSE).

---

## 🚫 Out of scope

- Anything that helps **evade Discord detection** (proxy rotation,
  fingerprint spoofing, bypassing rate limits). The project is open about
  what it does — the [warning](README.md#) is meant to be honest, not
  bypassed.
- Features that target Discord servers or users without consent (mass DM,
  scraping members, automated reporting, etc.).

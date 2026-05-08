> 🇬🇧 English · [🇫🇷 Français](Installation-fr)

# Installation

## Requirements

- **Python 3.10 or newer** — [download](https://www.python.org/downloads/).
  On Windows, tick *"Add Python to PATH"* in the installer.
- **pip** — bundled with Python.
- A Discord account and its token.

Verify in a terminal:

```bash
python --version
pip --version
```

## Step-by-step

### 1. Clone

```bash
git clone https://github.com/Soma-Yukihira/sofi-manager.git
cd sofi-manager
```

Or download the ZIP from the GitHub page and extract it.

### 2. Create a virtual environment

Strongly recommended — keeps dependencies isolated from the rest of your
system.

```bash
python -m venv env
```

Activate it:

| OS              | Command                  |
| --------------- | ------------------------ |
| Windows (CMD)   | `env\Scripts\activate`   |
| Windows (PS)    | `.\env\Scripts\activate` |
| macOS / Linux   | `source env/bin/activate` |

You should see `(env)` prefix your prompt.

### 3. Install dependencies

```bash
pip install -r requirements.txt
```

This installs:

- `discord.py-self` — Discord client (selfbot fork of `discord.py`)
- `customtkinter` — modern themed Tk widgets

### 4. Run

```bash
python main.py
```

The window opens. The first run creates no files — `bots.json` and
`settings.json` appear after you add a bot or change a setting.

## Getting a token

1. Open Discord in a browser. Log in.
2. Open DevTools → **Network** tab.
3. Send any message. Look for a request to `messages`.
4. In **Request Headers**, copy the value of `Authorization`. That's your token.

> [!CAUTION]
> Treat your token like a password. Anyone with it has full access to your
> account.

## Next

- [Configuration](Configuration) — the GUI fields explained.
- [Discord ToS Notice](Discord-ToS) — read this before running.

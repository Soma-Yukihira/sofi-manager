> 🇬🇧 English · [🇫🇷 Français](VPS-Deployment-fr)

# VPS Deployment

Run Selfbot Manager **headless** on a Linux server — no GUI required.

## Why CLI?

The repository ships two entry points sharing the same core
(`sofi_manager.bot_core`):

| Entry point | When to use                                          |
| ----------- | ---------------------------------------------------- |
| `main.py`   | Local desktop — full GUI, theming, multiple panes    |
| `cli.py`    | VPS, container, headless server — terminal logs only |

Both read the same `bots.json`, so you can add bots in the GUI on your
laptop, push the file to the VPS, and the CLI picks it up.

## CLI cheatsheet

```bash
python cli.py list                       # show configured bots
python cli.py show "Bot name"            # full config of one bot (token redacted)
python cli.py add                        # interactive wizard
python cli.py rm "Bot name"              # delete a bot
python cli.py run                        # run all bots in the foreground
python cli.py run "Bot A" "Bot B"        # run only those two
python cli.py --no-color run             # strip ANSI for log files
```

`Ctrl+C` stops cleanly: every running bot drains its remaining logs and
disconnects before exit.

## Quick deploy on a fresh VPS

Tested on Debian 12 / Ubuntu 22.04. Adapt for your distro.

```bash
# 1. system deps
sudo apt update
sudo apt install -y python3 python3-venv git

# 2. clone & venv
git clone https://github.com/Soma-Yukihira/sofi-manager.git
cd sofi-manager
python3 -m venv env
./env/bin/pip install --upgrade pip
./env/bin/pip install -r requirements.txt

# 3. configure
./env/bin/python cli.py add        # interactive — repeat for each bot
./env/bin/python cli.py list       # verify

# 4. test run
./env/bin/python cli.py run        # Ctrl+C when satisfied
```

## Run modes

### Foreground (testing)

```bash
./env/bin/python cli.py run
```

Logs print straight to the terminal. Closing the SSH session kills the bots.

### Persistent via `tmux` (interactive)

```bash
tmux new -s selfbot
./env/bin/python cli.py run
# Detach with: Ctrl+B then D
# Reattach later with: tmux attach -t selfbot
```

Survives SSH disconnects but dies on reboot.

### Persistent via `systemd` (production · recommended)

A one-shot installer is included:

```bash
sudo ./tools/install-systemd.sh
sudo systemctl start sofi-manager
journalctl -u sofi-manager -f         # tail live logs
```

The script generates `/etc/systemd/system/sofi-manager.service` configured
with your user, install path and venv. The service:

- starts at boot (`enable`d by the installer)
- restarts on failure (10 s backoff)
- drops privileges and isolates `/home`, `/etc`, `/var` (`ProtectSystem`,
  `PrivateTmp`, `NoNewPrivileges`)
- pipes stdout/stderr to the journal — no log files to rotate

Useful follow-ups:

```bash
sudo systemctl status sofi-manager
sudo systemctl restart sofi-manager
sudo systemctl stop sofi-manager
sudo systemctl disable --now sofi-manager      # full uninstall
```

## Configuring bots on the VPS

Three ways, pick one:

1. **Interactive on the VPS** — `python cli.py add`, walk through the wizard.
   Asks for name, token, drop channel, listened channels. Defaults are
   sensible for everything else.

2. **Edit `bots.json` directly** — same schema as the GUI version. See
   [Configuration](Configuration) for every field.

3. **Configure on your desktop, push to VPS** — open the GUI on your
   laptop, set up the bots fully (wishlist, theme prefs are irrelevant on
   the VPS), then:

   ```bash
   scp bots.json user@vps:/home/user/sofi-manager/bots.json
   sudo systemctl restart sofi-manager
   ```

## Updating

```bash
./env/bin/python tools/update.py
sudo systemctl restart sofi-manager   # if running as a service
```

The CLI `git pull`s, refreshes `pip` deps if `requirements.txt`
changed, and prints a clean diff summary. See [Updating](Updating)
for the full update model (in-app GUI updater + codeload fallback for
ZIP installs).

## Resource usage

Per bot: ~30–40 MB RAM, near-zero CPU (mostly sleeping between drops).
A 512 MB / 1 vCPU VPS comfortably runs 5+ bots.

Bandwidth is negligible — Discord WebSocket + a few REST calls per drop.

## Hardening tips

- **Fail-to-ban** SSH brute force: `sudo apt install fail2ban` (defaults are fine).
- **Non-root user** for the service: the installer already uses your sudo
  user, never root. Don't change that.
- **Token storage**: `bots.json` is `0644` by default. Tighten with
  `chmod 600 bots.json` if you don't trust other accounts on the box.
- **Discord 2FA on backup channel**: if Discord flags the IP, you may need
  to confirm 2FA from a browser before the bot can reconnect.

## Troubleshooting

See the dedicated [Troubleshooting](Troubleshooting) page. The CLI
prints the same `📥 SOFI:` diagnostic lines as the GUI — they're the
single best clue when a drop is missed.

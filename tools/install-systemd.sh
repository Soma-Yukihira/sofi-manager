#!/usr/bin/env bash
# =====================================================================
# install-systemd.sh — Register Selfbot Manager as a systemd service
# so it auto-starts at boot and restarts on failure.
#
# Run from the project root:
#   sudo ./tools/install-systemd.sh
#
# After install:
#   sudo systemctl start sofi-manager
#   systemctl status sofi-manager
#   journalctl -u sofi-manager -f         # tail logs
#   sudo systemctl restart sofi-manager
#   sudo systemctl disable --now sofi-manager
# =====================================================================
set -euo pipefail

if [[ "$(uname -s)" != "Linux" ]]; then
    echo "X  systemd is Linux-only. macOS users: use launchd or run via tmux."
    exit 1
fi

if [[ $EUID -ne 0 ]]; then
    echo "→  Re-running with sudo..."
    exec sudo --preserve-env=USER "$0" "$@"
fi

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SVC_USER="${SUDO_USER:-${USER}}"
PYTHON="$ROOT/env/bin/python"

if [[ ! -x "$PYTHON" ]]; then
    echo "X  Python venv not found at: $PYTHON"
    echo "   Create it first:"
    echo "     cd $ROOT"
    echo "     python3 -m venv env"
    echo "     ./env/bin/pip install -r requirements.txt"
    exit 1
fi

if [[ ! -f "$ROOT/bots.json" ]]; then
    echo "!  No bots.json found. The service will start with zero bots."
    echo "   Add a bot first with:"
    echo "     $PYTHON $ROOT/cli.py add"
    echo
fi

UNIT=/etc/systemd/system/sofi-manager.service
cat > "$UNIT" <<EOF
[Unit]
Description=Selfbot Manager · auto-dropper for SOFI
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=$SVC_USER
WorkingDirectory=$ROOT
Environment=PYTHONUNBUFFERED=1
ExecStart=$PYTHON $ROOT/cli.py --no-color run
Restart=on-failure
RestartSec=10
StandardOutput=journal
StandardError=journal

# Hardening
NoNewPrivileges=yes
PrivateTmp=yes
ProtectSystem=full
ProtectHome=read-only
ReadWritePaths=$ROOT

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable sofi-manager.service >/dev/null

echo
echo "✓  Service installed: $UNIT"
echo "   User       : $SVC_USER"
echo "   Working dir: $ROOT"
echo "   Python     : $PYTHON"
echo
echo "   Start now:"
echo "     sudo systemctl start sofi-manager"
echo
echo "   Tail logs:"
echo "     journalctl -u sofi-manager -f"
echo

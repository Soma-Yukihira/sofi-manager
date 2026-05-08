#!/usr/bin/env bash
# =====================================================================
# update.sh — Selfbot Manager · one-shot updater (Linux / macOS)
#
# Pulls the latest code, refreshes Python deps inside the local venv
# only if requirements.txt changed, prints a clean summary.
#
# Your local files (bots.json, settings.json, env/) are gitignored.
#
#   Usage :  ./tools/update.sh
# =====================================================================
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

# ANSI palette
if [[ -t 1 ]]; then
    GOLD=$'\033[38;2;212;175;55m'
    GREEN=$'\033[38;2;74;222;128m'
    RED=$'\033[38;2;248;113;113m'
    YELLOW=$'\033[38;2;251;191;36m'
    GRAY=$'\033[38;2;156;163;175m'
    DIM=$'\033[2m'
    RESET=$'\033[0m'
else
    GOLD=""; GREEN=""; RED=""; YELLOW=""; GRAY=""; DIM=""; RESET=""
fi

step()  { printf "%s->  %s%s\n" "$GRAY" "$1" "$RESET"; }
ok()    { printf "%sOK  %s%s\n" "$GREEN" "$1" "$RESET"; }
warn()  { printf "%s!   %s%s\n" "$YELLOW" "$1" "$RESET"; }
err()   { printf "%sX   %s%s\n" "$RED" "$1" "$RESET"; }

printf "\n%s⚜  SELFBOT MANAGER  ·  UPDATER%s\n" "$GOLD" "$RESET"
printf "%s------------------------------------------------------------%s\n" "$GRAY" "$RESET"

if [[ ! -d .git ]]; then
    err "Not a git repository."
    echo
    echo "  This folder was probably downloaded as a ZIP."
    echo "  Re-clone with:"
    echo
    echo "    git clone https://github.com/Soma-Yukihira/sofi-manager.git"
    echo
    exit 1
fi

oldHash=$(git rev-parse --short HEAD)

step "Checking remote..."
if ! git fetch --quiet 2>/dev/null; then
    err "Could not reach GitHub. Check your internet connection."
    exit 1
fi

behind=$(git rev-list --count 'HEAD..@{u}')
ahead=$(git rev-list --count '@{u}..HEAD')

if [[ "$behind" -eq 0 && "$ahead" -eq 0 ]]; then
    ok "Already up to date  (commit $oldHash)"
    echo
    exit 0
fi

if [[ "$ahead" -gt 0 ]]; then
    warn "You have $ahead local commit(s) not pushed."
fi

step "Pulling latest changes  ($behind commit(s) behind)..."
if ! git pull --ff-only; then
    err "git pull failed."
    echo
    echo "  Most common cause: you've edited a tracked file locally."
    echo "  Either stash your changes or commit them, then re-run:"
    echo
    echo "    git stash"
    echo "    ./tools/update.sh"
    echo "    git stash pop"
    echo
    exit 1
fi

newHash=$(git rev-parse --short HEAD)

# Detect venv
PIP=""
VENV=""
for name in env venv .venv; do
    if [[ -x "$ROOT/$name/bin/pip" ]]; then
        PIP="$ROOT/$name/bin/pip"
        VENV="$name"
        break
    fi
done

req_changed=false
if git diff --name-only "$oldHash..$newHash" | grep -q "^requirements\.txt$"; then
    req_changed=true
fi

if [[ -n "$PIP" && "$req_changed" == "true" ]]; then
    step "Installing updated dependencies  (venv: $VENV/)..."
    "$PIP" install --quiet -r requirements.txt
    ok "Dependencies refreshed"
elif [[ -n "$PIP" ]]; then
    step "requirements.txt unchanged — skipping pip"
else
    warn "No virtualenv detected (env/, venv/, .venv/)."
    echo "    If new dependencies are required:"
    echo "      pip install -r requirements.txt"
fi

nFiles=$(git diff --name-only "$oldHash..$newHash" | wc -l | tr -d ' ')

echo
ok "Up to date"
echo
printf "    %s%s  ->  %s    (%s file(s) changed)%s\n" "$GRAY" "$oldHash" "$newHash" "$nFiles" "$RESET"
echo
printf "    %sYour bots.json + settings.json are untouched.%s\n" "$GRAY" "$RESET"
if systemctl is-active --quiet sofi-manager 2>/dev/null; then
    printf "    %sRestart the service to pick up the changes:%s\n" "$GRAY" "$RESET"
    echo "      sudo systemctl restart sofi-manager"
fi
echo

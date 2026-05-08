# =====================================================================
# update.ps1 — Selfbot Manager · one-shot updater
#
# Pulls the latest code from GitHub, refreshes the Python dependencies
# inside the local venv, and prints a clean summary.
#
# Your local files (bots.json, settings.json, Selfbot Manager.lnk, env/)
# are never touched — they are gitignored.
#
#   Usage :  .\tools\update.ps1
# =====================================================================

$ErrorActionPreference = 'Stop'

# Force UTF-8 console output so ⚜ and accented chars render properly
# even on legacy Windows PowerShell with CP1252 default code page.
try {
    [Console]::OutputEncoding = [System.Text.Encoding]::UTF8
    $OutputEncoding           = [System.Text.Encoding]::UTF8
} catch {}

$root = (Resolve-Path "$PSScriptRoot\..").Path
Push-Location $root

function Write-Header($msg) {
    Write-Host ""
    Write-Host "⚜  $msg" -ForegroundColor Yellow
    Write-Host ('-' * 60) -ForegroundColor DarkGray
}

function Write-Step($msg) {
    Write-Host "->  $msg" -ForegroundColor Cyan
}

function Write-OK($msg) {
    Write-Host "OK  $msg" -ForegroundColor Green
}

function Write-Warn($msg) {
    Write-Host "!   $msg" -ForegroundColor Yellow
}

function Write-Err($msg) {
    Write-Host "X   $msg" -ForegroundColor Red
}

Write-Header "SELFBOT MANAGER  ·  UPDATER"

# 1) Sanity check : is this a git repo?
if (-not (Test-Path "$root\.git")) {
    Write-Err "Not a git repository."
    Write-Host ""
    Write-Host "  This folder was probably downloaded as a ZIP." -ForegroundColor Gray
    Write-Host "  To enable updates, re-clone the project:" -ForegroundColor Gray
    Write-Host ""
    Write-Host "    git clone https://github.com/Soma-Yukihira/sofi-manager.git" -ForegroundColor White
    Write-Host ""
    Write-Host "  Then copy your bots.json and settings.json into the new folder." -ForegroundColor Gray
    Write-Host ""
    Pop-Location
    exit 1
}

# 2) Capture state before
$oldHash = (git rev-parse --short HEAD 2>$null)

Write-Step "Checking remote..."
try {
    git fetch --quiet 2>&1 | Out-Null
} catch {
    Write-Err "Could not reach GitHub. Check your internet connection."
    Pop-Location
    exit 1
}

$behind = (git rev-list --count 'HEAD..@{u}' 2>$null)
$ahead  = (git rev-list --count '@{u}..HEAD' 2>$null)

if ([int]$behind -eq 0 -and [int]$ahead -eq 0) {
    Write-OK "Already up to date  (commit $oldHash)"
    Write-Host ""
    Pop-Location
    exit 0
}

if ([int]$ahead -gt 0) {
    Write-Warn "You have $ahead local commit(s) not pushed."
    Write-Host "    They will be preserved by the fast-forward pull." -ForegroundColor Gray
}

# 3) Pull
Write-Step "Pulling latest changes  ($behind commit(s) behind)..."
$pullOut = (git pull --ff-only 2>&1)
$pullExit = $LASTEXITCODE

if ($pullExit -ne 0) {
    Write-Err "git pull failed:"
    $pullOut | ForEach-Object { Write-Host "    $_" -ForegroundColor Gray }
    Write-Host ""
    Write-Host "  Most common cause: you've edited a tracked file locally." -ForegroundColor Gray
    Write-Host "  Either stash your changes or commit them, then re-run." -ForegroundColor Gray
    Write-Host ""
    Write-Host "    git stash               # set local edits aside" -ForegroundColor White
    Write-Host "    .\tools\update.ps1      # update" -ForegroundColor White
    Write-Host "    git stash pop           # bring them back" -ForegroundColor White
    Write-Host ""
    Pop-Location
    exit 1
}

$newHash = (git rev-parse --short HEAD)

# 4) Detect venv
$pip = $null
$venvName = $null
foreach ($name in @('env', 'venv', '.venv')) {
    $candidate = Join-Path $root "$name\Scripts\pip.exe"
    if (Test-Path $candidate) {
        $pip = $candidate
        $venvName = $name
        break
    }
}

# 5) Refresh dependencies (only if requirements.txt changed in the pull)
$reqChanged = $false
$diffOut = (git diff --name-only "$oldHash..$newHash" 2>$null)
if ($diffOut -match 'requirements\.txt') { $reqChanged = $true }

if ($pip -and $reqChanged) {
    Write-Step "Installing updated dependencies  (venv: $venvName\)..."
    & $pip install --quiet -r requirements.txt 2>&1 | ForEach-Object {
        if ($_ -match 'error|ERROR') {
            Write-Host "    $_" -ForegroundColor Red
        } else {
            Write-Host "    $_" -ForegroundColor DarkGray
        }
    }
    Write-OK "Dependencies refreshed"
} elseif ($pip) {
    Write-Step "requirements.txt unchanged - skipping pip"
} else {
    Write-Warn "No virtualenv detected (env/, venv/, .venv/)."
    Write-Host "    If new dependencies are required by this update, install them with:" -ForegroundColor Gray
    Write-Host "      pip install -r requirements.txt" -ForegroundColor White
}

# 6) Summary
$changedFiles = (git diff --name-only "$oldHash..$newHash" 2>$null)
$nFiles = if ($changedFiles) { ($changedFiles -split "`n").Count } else { 0 }

Write-Host ""
Write-OK "Up to date"
Write-Host ""
Write-Host "    $oldHash  ->  $newHash    ($nFiles file(s) changed)" -ForegroundColor Gray
Write-Host ""
Write-Host "    Your bots.json + settings.json are untouched." -ForegroundColor DarkGray
Write-Host "    Launch the app from the taskbar pin or:" -ForegroundColor DarkGray
Write-Host "      python main.py" -ForegroundColor White
Write-Host ""

Pop-Location

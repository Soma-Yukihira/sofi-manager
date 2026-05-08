# =====================================================================
# create-shortcut.ps1 — Windows · Selfbot Manager
# Génère un raccourci .lnk dans la racine du projet, configuré avec ton
# venv local. Lance ce script une fois après l'install des dépendances.
#
#   Usage :  .\tools\create-shortcut.ps1
# =====================================================================

$root = (Resolve-Path "$PSScriptRoot\..").Path
$icon = Join-Path $root "assets\app.ico"
$lnkPath = Join-Path $root "Selfbot Manager.lnk"

# Détecte le venv (env, venv, .venv)
$pyw = $null
foreach ($name in @('env', 'venv', '.venv')) {
    $candidate = Join-Path $root "$name\Scripts\pythonw.exe"
    if (Test-Path $candidate) {
        $pyw = $candidate
        break
    }
}

if (-not $pyw) {
    Write-Host ""
    Write-Host "X  No virtual environment found in the project root." -ForegroundColor Red
    Write-Host "   Looked for: env\, venv\, .venv\" -ForegroundColor Gray
    Write-Host ""
    Write-Host "   Create one first:" -ForegroundColor Yellow
    Write-Host "     python -m venv env"            -ForegroundColor Gray
    Write-Host "     .\env\Scripts\activate"         -ForegroundColor Gray
    Write-Host "     pip install -r requirements.txt" -ForegroundColor Gray
    Write-Host ""
    exit 1
}

if (-not (Test-Path $icon)) {
    Write-Host ""
    Write-Host "X  Icon not found: $icon" -ForegroundColor Red
    Write-Host "   The repository may be incomplete; pull again." -ForegroundColor Gray
    Write-Host ""
    exit 1
}

$shell = New-Object -ComObject WScript.Shell
$lnk = $shell.CreateShortcut($lnkPath)
$lnk.TargetPath       = $pyw
$lnk.Arguments        = '"main.py"'
$lnk.WorkingDirectory = $root
$lnk.IconLocation     = "$icon,0"
$lnk.Description      = 'Selfbot Manager'
$lnk.WindowStyle      = 1
$lnk.Save()

Write-Host ""
Write-Host "OK  Shortcut created" -ForegroundColor Green
Write-Host "    $lnkPath" -ForegroundColor Gray
Write-Host ""
Write-Host "    Target : $pyw `"main.py`"" -ForegroundColor DarkGray
Write-Host "    Icon   : $icon" -ForegroundColor DarkGray
Write-Host ""
Write-Host "Pin to taskbar:" -ForegroundColor Cyan
Write-Host "  - Drag-and-drop ``Selfbot Manager.lnk`` onto the taskbar, or" -ForegroundColor Gray
Write-Host "  - Right-click -> Show more options -> Pin to taskbar" -ForegroundColor Gray
Write-Host ""

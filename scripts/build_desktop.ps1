# Builds the native desktop app on Windows: compiles the frontend, copies it
# into backend/app/static (same layout the Docker image uses), then runs
# PyInstaller. Run directly in PowerShell -- no Git Bash / WSL needed.
#
# Usage: powershell -ExecutionPolicy Bypass -File scripts\build_desktop.ps1
# (or just right-click -> "Run with PowerShell" once your execution policy
# allows local scripts: Set-ExecutionPolicy -Scope CurrentUser RemoteSigned)

$ErrorActionPreference = 'Stop'

$repoRoot = Split-Path -Parent $PSScriptRoot

Write-Host "==> Building frontend"
Push-Location "$repoRoot\frontend"
npm ci
if ($LASTEXITCODE -ne 0) { throw "npm ci failed" }
npm run build
if ($LASTEXITCODE -ne 0) { throw "npm run build failed" }
Pop-Location

Write-Host "==> Copying frontend build into backend\app\static"
$staticDir = "$repoRoot\backend\app\static"
if (Test-Path $staticDir) { Remove-Item -Recurse -Force $staticDir }
New-Item -ItemType Directory -Path $staticDir | Out-Null
Copy-Item -Recurse "$repoRoot\frontend\dist\*" $staticDir

Write-Host "==> Installing backend + desktop dependencies (separate build venv, doesn't touch backend\.venv)"
Push-Location "$repoRoot\backend"
python -m venv .venv-desktop-build
if ($LASTEXITCODE -ne 0) { throw "venv creation failed -- is Python 3.12+ on PATH?" }
& .\.venv-desktop-build\Scripts\Activate.ps1
pip install -e ".[desktop]"
if ($LASTEXITCODE -ne 0) { throw "pip install failed" }

Write-Host "==> Running PyInstaller"
pyinstaller savr_desktop.spec --noconfirm
if ($LASTEXITCODE -ne 0) { throw "PyInstaller build failed" }
Pop-Location

Write-Host "==> Done: backend\dist\savr\savr.exe"

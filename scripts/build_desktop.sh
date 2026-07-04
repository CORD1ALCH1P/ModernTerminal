#!/usr/bin/env bash
# Builds the native desktop app: compiles the frontend, copies it into
# backend/app/static (same layout the Docker image uses), then runs
# PyInstaller. Must be run on the target OS -- this produces a build for
# whatever platform it's run on (Linux/macOS/Windows), not a cross-build.
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

echo "==> Building frontend"
cd "$repo_root/frontend"
npm ci
npm run build

echo "==> Copying frontend build into backend/app/static"
rm -rf "$repo_root/backend/app/static"
mkdir -p "$repo_root/backend/app/static"
cp -r "$repo_root/frontend/dist/." "$repo_root/backend/app/static/"

echo "==> Installing backend + desktop dependencies (separate build venv, doesn't touch backend/.venv)"
cd "$repo_root/backend"
python3 -m venv .venv-desktop-build
# Windows' venv module lays out Scripts/ instead of bin/ -- this also covers
# running this script under Git Bash on Windows, not just Linux/macOS.
if [ -f .venv-desktop-build/bin/activate ]; then
  source .venv-desktop-build/bin/activate
else
  source .venv-desktop-build/Scripts/activate
fi
pip install -e ".[desktop]"

echo "==> Running PyInstaller"
pyinstaller savr_desktop.spec --noconfirm

echo "==> Done: backend/dist/savr/"

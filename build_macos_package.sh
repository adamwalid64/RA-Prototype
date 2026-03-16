#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
FRONTEND_DIR="$PROJECT_ROOT/frontend/RA-Project"
BACKEND_DIR="$PROJECT_ROOT/backend"
VENV_DIR="$BACKEND_DIR/.venv-packager-mac"
FRONTEND_DIST="$FRONTEND_DIR/dist"
BACKEND_FRONTEND_DIST="$BACKEND_DIR/frontend_dist"
RELEASE_DIR="$PROJECT_ROOT/release-macos"
PYINSTALLER_DIST="$BACKEND_DIR/dist/RA Launcher.app"

run_step() {
  local label="$1"
  shift
  echo "$label"
  "$@"
}

echo "Building frontend..."
pushd "$FRONTEND_DIR" >/dev/null
if ! npm ci; then
  echo "npm ci failed; retrying with npm install..."
  npm install
fi
run_step "Running frontend build..." npm run build
popd >/dev/null

if [[ ! -d "$FRONTEND_DIST" ]]; then
  echo "Frontend build output not found at $FRONTEND_DIST"
  exit 1
fi

echo "Preparing backend static assets..."
rm -rf "$BACKEND_FRONTEND_DIST"
cp -R "$FRONTEND_DIST" "$BACKEND_FRONTEND_DIST"

if [[ ! -d "$VENV_DIR" ]]; then
  run_step "Creating Python venv..." python3 -m venv "$VENV_DIR"
fi

VENV_PYTHON="$VENV_DIR/bin/python"

run_step "Upgrading pip..." "$VENV_PYTHON" -m pip install --upgrade pip
run_step "Installing Python dependencies..." "$VENV_PYTHON" -m pip install -r "$BACKEND_DIR/requirements.txt" pyinstaller

echo "Building macOS app bundle..."
pushd "$BACKEND_DIR" >/dev/null
run_step "Running PyInstaller..." \
  "$VENV_PYTHON" -m PyInstaller \
  --noconfirm \
  --clean \
  --windowed \
  --name "RA Launcher" \
  --add-data "frontend_dist:frontend_dist" \
  launcher.py
popd >/dev/null

if [[ ! -d "$PYINSTALLER_DIST" ]]; then
  echo "PyInstaller output not found at $PYINSTALLER_DIST"
  exit 1
fi

echo "Preparing macOS release folder..."
rm -rf "$RELEASE_DIR"
mkdir -p "$RELEASE_DIR"
cp -R "$PYINSTALLER_DIST" "$RELEASE_DIR/"
cp "$PROJECT_ROOT/PACKAGE_GUIDE.md" "$RELEASE_DIR/PACKAGE_GUIDE.md"

echo "Creating distributable zip..."
ditto -c -k --sequesterRsrc --keepParent "$RELEASE_DIR/RA Launcher.app" "$RELEASE_DIR/RA-Launcher-macOS.zip"

echo ""
echo "Done. macOS distributable files are in:"
echo "  $RELEASE_DIR"
echo ""
echo "Share 'RA-Launcher-macOS.zip' with Mac users."

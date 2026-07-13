#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/../.."

PYTHON_BIN="${PYTHON_BIN:-python3.12}"
VENV_DIR="${VENV_DIR:-.venv-packaging-macos}"

if [ "$(uname -s)" != "Darwin" ]; then
  echo "macOS build must run on macOS."
  exit 1
fi

if ! command -v "$PYTHON_BIN" >/dev/null 2>&1; then
  echo "Python executable not found: $PYTHON_BIN"
  echo "Install Python 3.12 or run with PYTHON_BIN=/path/to/python."
  exit 1
fi

if [ ! -d "/Applications/VLC.app" ] && [ ! -d "$HOME/Applications/VLC.app" ]; then
  echo "Warning: VLC.app was not found."
  echo "Install it with: brew install --cask vlc"
fi

"$PYTHON_BIN" -m venv "$VENV_DIR"
source "$VENV_DIR/bin/activate"

python -m pip install --upgrade pip
python -m pip install -r requirements-packaging.txt

python packaging/macos/create_icns.py
python -m PyInstaller --clean --noconfirm packaging/macos/video-event-logger.spec

echo
echo "Build complete:"
echo "  dist/Video Event Logger.app"
echo
echo "Create release archive:"
echo "  bash packaging/macos/create_release_archive.sh"

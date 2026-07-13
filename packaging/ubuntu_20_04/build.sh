#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/../.."

PYTHON_BIN="${PYTHON_BIN:-python3.12}"
VENV_DIR="${VENV_DIR:-.venv-packaging}"

if ! command -v "$PYTHON_BIN" >/dev/null 2>&1; then
  echo "Python executable not found: $PYTHON_BIN"
  echo "Install Python 3.12 or run with PYTHON_BIN=/path/to/python."
  exit 1
fi

if ! command -v vlc >/dev/null 2>&1; then
  echo "Warning: vlc was not found. Install it with: sudo apt install vlc"
fi

"$PYTHON_BIN" -m venv "$VENV_DIR"
source "$VENV_DIR/bin/activate"

python -m pip install --upgrade pip
python -m pip install -r requirements-packaging.txt
python -m PyInstaller --clean --noconfirm packaging/ubuntu_20_04/video-event-logger.spec

echo
echo "Build complete:"
echo "  dist/video-event-logger/video-event-logger"
echo
echo "Install user launcher:"
echo "  bash packaging/ubuntu_20_04/install_user_shortcut.sh"

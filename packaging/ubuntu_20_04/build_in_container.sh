#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/../.."

if [ "${VIDEO_EVENT_LOGGER_CONTAINER_BUILD:-}" != "1" ]; then
  echo "This script must run inside the Ubuntu 20.04 packaging container." >&2
  exit 1
fi
if ! grep -q '^VERSION_ID="20.04"$' /etc/os-release; then
  echo "The container is not based on Ubuntu 20.04." >&2
  exit 1
fi
if [ "$(uname -m)" != "x86_64" ] || [ "$(dpkg --print-architecture)" != "amd64" ]; then
  echo "The container must run as linux/amd64 (x86_64/amd64)." >&2
  exit 1
fi

BUILD_MODE="${BUILD_MODE:-release}"
case "$BUILD_MODE" in
  debug|release) ;;
  *)
    echo "Unsupported BUILD_MODE: $BUILD_MODE (expected debug or release)" >&2
    exit 1
    ;;
esac

PYTHON_BIN="${PYTHON_BIN:-python3.12}"
VENV_DIR="${VENV_DIR:-/tmp/video-event-logger-packaging-venv}"
BUILD_INFO_PATH="${BUILD_INFO_PATH:-build/BUILD_INFO.txt}"
DEPENDENCY_INFO_PATH="${DEPENDENCY_INFO_PATH:-build/pip-freeze.txt}"

cleanup() {
  rm -rf "$VENV_DIR"
}
trap cleanup EXIT

rm -rf build dist "$VENV_DIR"
mkdir -p build release

"$PYTHON_BIN" -m venv "$VENV_DIR"
source "$VENV_DIR/bin/activate"
python -m pip install --upgrade \
  pip==24.2 \
  setuptools==75.1.0 \
  wheel==0.44.0
python -m pip install -r requirements-packaging.txt
python -m pip freeze | tee "$DEPENDENCY_INFO_PATH"

python -c "import PySide6; import vlc; print('PySide6', PySide6.__version__); print('libVLC', vlc.libvlc_get_version())"

BUILD_MODE="$BUILD_MODE" python -m PyInstaller \
  --clean \
  --noconfirm \
  packaging/ubuntu_20_04/video-event-logger.spec

APP_VERSION="$(sed -n 's/^APP_VERSION = "\(.*\)"/\1/p' video_event_logger/app_config.py)"
if [ -z "$APP_VERSION" ]; then
  echo "Could not read APP_VERSION from video_event_logger/app_config.py" >&2
  exit 1
fi

PYTHON_VERSION="$(python -c 'import platform; print(platform.python_version())')"
PYINSTALLER_VERSION="$(python -c 'import PyInstaller; print(PyInstaller.__version__)')"
PYSIDE_VERSION="$(python -c 'import PySide6; print(PySide6.__version__)')"
PYTHON_VLC_VERSION="$(python -c 'import importlib.metadata; print(importlib.metadata.version("python-vlc"))')"
SOURCE_DATE_EPOCH="${SOURCE_DATE_EPOCH:-$(date +%s)}"
if ! [[ "$SOURCE_DATE_EPOCH" =~ ^[0-9]+$ ]]; then
  echo "Invalid SOURCE_DATE_EPOCH: $SOURCE_DATE_EPOCH" >&2
  exit 1
fi
BUILD_DATE_UTC="${BUILD_DATE_UTC:-$(date -u '+%Y-%m-%dT%H:%M:%SZ')}"

{
  echo "Application: Video Event Logger"
  echo "Application version: $APP_VERSION"
  echo "Build mode: $BUILD_MODE"
  echo "Build date UTC: $BUILD_DATE_UTC"
  echo "Target platform: Ubuntu 20.04"
  echo "Target architecture: amd64 (x86_64)"
  echo "Ubuntu base version: 20.04"
  echo "Python version: $PYTHON_VERSION"
  echo "PyInstaller version: $PYINSTALLER_VERSION"
  echo "PySide6 version: $PYSIDE_VERSION"
  echo "python-vlc version: $PYTHON_VLC_VERSION"
  echo
  echo "Resolved Python dependencies:"
  sed 's/^/  /' "$DEPENDENCY_INFO_PATH"
} > "$BUILD_INFO_PATH"

DIST_DIR="dist/video-event-logger" \
BUILD_INFO_PATH="$BUILD_INFO_PATH" \
  bash packaging/ubuntu_20_04/validate_build.sh

BUILD_INFO_PATH="$BUILD_INFO_PATH" \
  bash packaging/ubuntu_20_04/create_release_archive.sh

if [ -n "${HOST_UID:-}" ] && [ -n "${HOST_GID:-}" ]; then
  chown "$HOST_UID:$HOST_GID" "release/${RELEASE_NAME}.tar.gz"
fi

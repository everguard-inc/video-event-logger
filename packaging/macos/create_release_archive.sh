#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/../.."

APP_VERSION="$(sed -n 's/^APP_VERSION = "\(.*\)"/\1/p' video_event_logger/app_config.py)"
if [ -z "$APP_VERSION" ]; then
  echo "Could not read APP_VERSION from video_event_logger/app_config.py"
  exit 1
fi

APP_BUNDLE="${APP_BUNDLE:-dist/Video Event Logger.app}"
RELEASE_NAME="${RELEASE_NAME:-video-event-logger-v$APP_VERSION-macos}"
RELEASE_DIR="${RELEASE_DIR:-release}"
WORK_DIR="$RELEASE_DIR/$RELEASE_NAME"
ARCHIVE_PATH="$RELEASE_DIR/$RELEASE_NAME.zip"

if [ "$(uname -s)" != "Darwin" ]; then
  echo "macOS release archive must be created on macOS."
  exit 1
fi

if [ ! -d "$APP_BUNDLE" ]; then
  echo "App bundle not found: $APP_BUNDLE"
  echo "Build it first: PYTHON_BIN=python3.12 bash packaging/macos/build.sh"
  exit 1
fi

if ! command -v ditto >/dev/null 2>&1; then
  echo "ditto was not found. This script must run on macOS."
  exit 1
fi

mkdir -p "$RELEASE_DIR"
rm -rf "$WORK_DIR"
mkdir -p "$WORK_DIR"
cp -R "$APP_BUNDLE" "$WORK_DIR/"
cp packaging/macos/release_README.txt "$WORK_DIR/README.txt"

ditto -c -k --keepParent "$WORK_DIR" "$ARCHIVE_PATH"

echo "Release archive created:"
echo "  $ARCHIVE_PATH"

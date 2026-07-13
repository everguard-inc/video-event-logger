#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/../.."

APP_NAME="video-event-logger"
APP_VERSION="$(sed -n 's/^APP_VERSION = "\(.*\)"/\1/p' video_event_logger/app_config.py)"
if [ -z "$APP_VERSION" ]; then
  echo "Could not read APP_VERSION from video_event_logger/app_config.py"
  exit 1
fi

DEFAULT_RELEASE_NAME="$APP_NAME-v$APP_VERSION-ubuntu20.04"
RELEASE_NAME="${RELEASE_NAME:-$DEFAULT_RELEASE_NAME}"
BUILD_DIR="${BUILD_DIR:-dist/$APP_NAME}"
RELEASE_DIR="${RELEASE_DIR:-release}"
WORK_DIR="$RELEASE_DIR/$RELEASE_NAME"
ARCHIVE_PATH="$RELEASE_DIR/$RELEASE_NAME.tar.gz"

if [ ! -x "$BUILD_DIR/$APP_NAME" ]; then
  echo "Packaged app not found: $BUILD_DIR/$APP_NAME"
  echo "Build it first: PYTHON_BIN=python3.12 bash packaging/ubuntu_20_04/build.sh"
  exit 1
fi

mkdir -p "$RELEASE_DIR"
rm -rf "$WORK_DIR"
mkdir -p "$WORK_DIR"

cp -R "$BUILD_DIR" "$WORK_DIR/$APP_NAME"
cp packaging/ubuntu_20_04/release_install.sh "$WORK_DIR/install.sh"
cp packaging/ubuntu_20_04/release_README.txt "$WORK_DIR/README.txt"
chmod +x "$WORK_DIR/install.sh"

tar -czf "$ARCHIVE_PATH" -C "$RELEASE_DIR" "$RELEASE_NAME"

echo "Release archive created:"
echo "  $ARCHIVE_PATH"
echo
echo "Send this archive to the user."

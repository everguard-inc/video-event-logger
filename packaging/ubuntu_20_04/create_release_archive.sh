#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/../.."

APP_NAME="video-event-logger"
APP_VERSION="$(sed -n 's/^APP_VERSION = "\(.*\)"/\1/p' video_event_logger/app_config.py)"
if [ -z "$APP_VERSION" ]; then
  echo "Could not read APP_VERSION from video_event_logger/app_config.py"
  exit 1
fi

DEFAULT_RELEASE_NAME="$APP_NAME-v$APP_VERSION-ubuntu20.04-amd64"
RELEASE_NAME="${RELEASE_NAME:-$DEFAULT_RELEASE_NAME}"
BUILD_DIR="${BUILD_DIR:-dist/$APP_NAME}"
RELEASE_DIR="${RELEASE_DIR:-release}"
ARCHIVE_PATH="$RELEASE_DIR/$RELEASE_NAME.tar.gz"
BUILD_INFO_PATH="${BUILD_INFO_PATH:-build/BUILD_INFO.txt}"
SOURCE_DATE_EPOCH="${SOURCE_DATE_EPOCH:-0}"

if [ ! -x "$BUILD_DIR/$APP_NAME" ]; then
  echo "Packaged app not found: $BUILD_DIR/$APP_NAME"
  echo "Build it first: bash packaging/ubuntu_20_04/build_release.sh"
  exit 1
fi
if [ ! -f "$BUILD_INFO_PATH" ]; then
  echo "Build metadata not found: $BUILD_INFO_PATH" >&2
  exit 1
fi
if ! [[ "$SOURCE_DATE_EPOCH" =~ ^[0-9]+$ ]]; then
  echo "Invalid SOURCE_DATE_EPOCH: $SOURCE_DATE_EPOCH" >&2
  exit 1
fi
if ! tar --version | grep -q 'GNU tar'; then
  echo "GNU tar is required to create the Ubuntu release archive." >&2
  exit 1
fi

DIST_DIR="$BUILD_DIR" BUILD_INFO_PATH="$BUILD_INFO_PATH" \
  bash packaging/ubuntu_20_04/validate_build.sh

mkdir -p "$RELEASE_DIR"
STAGING_PARENT="$(mktemp -d /tmp/video-event-logger-release.XXXXXX)"
WORK_DIR="$STAGING_PARENT/$RELEASE_NAME"
ARCHIVE_TEMP="$(mktemp "$RELEASE_DIR/.${RELEASE_NAME}.XXXXXX.tar.gz")"

cleanup() {
  rm -rf "$STAGING_PARENT"
  if [ -n "${ARCHIVE_TEMP:-}" ] && [ -f "$ARCHIVE_TEMP" ]; then
    rm -f "$ARCHIVE_TEMP"
  fi
}
trap cleanup EXIT

mkdir -p "$WORK_DIR"
cp -R "$BUILD_DIR" "$WORK_DIR/$APP_NAME"
cp packaging/ubuntu_20_04/install.sh "$WORK_DIR/install.sh"
cp packaging/ubuntu_20_04/uninstall.sh "$WORK_DIR/uninstall.sh"
cp packaging/ubuntu_20_04/fix.sh "$WORK_DIR/fix.sh"
cp packaging/ubuntu_20_04/video-event-logger-launcher "$WORK_DIR/video-event-logger-launcher"
cp packaging/ubuntu_20_04/release_README.md "$WORK_DIR/README.md"
cp "$BUILD_INFO_PATH" "$WORK_DIR/BUILD_INFO.txt"
chmod +x \
  "$WORK_DIR/install.sh" \
  "$WORK_DIR/uninstall.sh" \
  "$WORK_DIR/fix.sh" \
  "$WORK_DIR/video-event-logger-launcher"

tar \
  --sort=name \
  --mtime="@$SOURCE_DATE_EPOCH" \
  --owner=0 \
  --group=0 \
  --numeric-owner \
  -cf - \
  -C "$STAGING_PARENT" \
  "$RELEASE_NAME" | gzip -n -9 > "$ARCHIVE_TEMP"

mv "$ARCHIVE_TEMP" "$ARCHIVE_PATH"
ARCHIVE_TEMP=""

echo "Release archive created:"
echo "  $ARCHIVE_PATH"
echo
echo "Send this archive to the user."

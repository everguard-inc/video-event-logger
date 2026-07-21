#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/../.."

IMAGE_NAME="${IMAGE_NAME:-video-event-logger-ubuntu20.04-amd64-build}"
PIP_CACHE_VOLUME="${PIP_CACHE_VOLUME:-video-event-logger-pip-cache}"
PLATFORM="${PLATFORM:-linux/amd64}"
if [ "$#" -gt 1 ]; then
  echo "Usage: $0 [debug|release]" >&2
  exit 1
fi
BUILD_MODE="${1:-${BUILD_MODE:-release}}"

if [ "$PLATFORM" != "linux/amd64" ]; then
  echo "Unsupported PLATFORM: $PLATFORM" >&2
  echo "Ubuntu 20.04 packaging supports only linux/amd64." >&2
  exit 1
fi

case "$BUILD_MODE" in
  debug|release) ;;
  *)
    echo "Unsupported BUILD_MODE: $BUILD_MODE (expected debug or release)" >&2
    exit 1
    ;;
esac

if ! command -v docker >/dev/null 2>&1; then
  echo "Docker was not found. Install Docker with buildx support first." >&2
  exit 1
fi
if ! docker buildx version >/dev/null 2>&1; then
  echo "Docker buildx is required but is not available." >&2
  exit 1
fi

APP_VERSION="$(sed -n 's/^APP_VERSION = "\(.*\)"/\1/p' video_event_logger/app_config.py)"
if [ -z "$APP_VERSION" ]; then
  echo "Could not read APP_VERSION from video_event_logger/app_config.py" >&2
  exit 1
fi

RELEASE_NAME="${RELEASE_NAME:-video-event-logger-v$APP_VERSION-ubuntu20.04-amd64}"
BUILD_DATE_UTC="$(date -u '+%Y-%m-%dT%H:%M:%SZ')"
SOURCE_DATE_EPOCH="$(date +%s)"

mkdir -p release
rm -f "release/$RELEASE_NAME.tar.gz"

echo "Building Video Event Logger $APP_VERSION"
echo "  target: $PLATFORM"
echo "  mode:   $BUILD_MODE"
echo "  output: release/$RELEASE_NAME.tar.gz"

docker build \
  --platform "$PLATFORM" \
  -f packaging/ubuntu_20_04/Dockerfile \
  -t "$IMAGE_NAME" \
  .

docker run \
  --rm \
  --platform "$PLATFORM" \
  -e "BUILD_MODE=$BUILD_MODE" \
  -e "BUILD_DATE_UTC=$BUILD_DATE_UTC" \
  -e "HOST_UID=$(id -u)" \
  -e "HOST_GID=$(id -g)" \
  -e "RELEASE_NAME=$RELEASE_NAME" \
  -e "SOURCE_DATE_EPOCH=$SOURCE_DATE_EPOCH" \
  -v "$PWD/release:/app/release" \
  -v "$PIP_CACHE_VOLUME:/root/.cache/pip" \
  "$IMAGE_NAME"

ARCHIVE_PATH="release/$RELEASE_NAME.tar.gz"
if [ ! -f "$ARCHIVE_PATH" ]; then
  echo "Build finished without the expected archive: $ARCHIVE_PATH" >&2
  exit 1
fi

echo
echo "Validated release archive:"
echo "  $ARCHIVE_PATH"

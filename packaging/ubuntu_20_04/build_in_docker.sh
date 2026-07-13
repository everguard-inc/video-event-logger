#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/../.."

IMAGE_NAME="${IMAGE_NAME:-video-event-logger-ubuntu20.04-build}"
PLATFORM="${PLATFORM:-linux/amd64}"
APP_VERSION="$(sed -n 's/^APP_VERSION = "\(.*\)"/\1/p' video_event_logger/app_config.py)"
if [ -z "$APP_VERSION" ]; then
  echo "Could not read APP_VERSION from video_event_logger/app_config.py"
  exit 1
fi
RELEASE_NAME="${RELEASE_NAME:-video-event-logger-v$APP_VERSION-ubuntu20.04}"

mkdir -p release

docker build \
  --platform "$PLATFORM" \
  -f packaging/ubuntu_20_04/Dockerfile \
  -t "$IMAGE_NAME" \
  .

docker run \
  --rm \
  --platform "$PLATFORM" \
  -e "RELEASE_NAME=$RELEASE_NAME" \
  -v "$PWD/release:/app/release" \
  "$IMAGE_NAME"

echo
echo "Release archive:"
echo "  release/$RELEASE_NAME.tar.gz"

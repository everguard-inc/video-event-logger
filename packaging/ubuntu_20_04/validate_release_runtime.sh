#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/../.."

if [ "$#" -ne 1 ] || [ ! -f "$1" ]; then
  echo "Usage: $0 release/video-event-logger-v<VERSION>-ubuntu20.04-amd64.tar.gz" >&2
  exit 1
fi
archive="$(cd "$(dirname "$1")" && pwd)/$(basename "$1")"
image="video-event-logger-ubuntu24.04-runtime-test"
docker build --platform linux/amd64 \
  -f packaging/ubuntu_20_04/runtime_test.Dockerfile -t "$image" .
docker run --rm --platform linux/amd64 \
  -v "$archive:/input/release.tar.gz:ro" "$image"

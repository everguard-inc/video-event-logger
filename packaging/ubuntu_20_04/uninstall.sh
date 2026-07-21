#!/usr/bin/env bash
set -euo pipefail

fail() {
  echo "Uninstall failed: $*" >&2
  exit 1
}

if [ -z "${HOME:-}" ]; then
  fail "HOME is not set"
fi

INSTALL_DIR="${INSTALL_DIR:-$HOME/.local/opt/video-event-logger}"
DESKTOP_DIR="${XDG_DATA_HOME:-$HOME/.local/share}/applications"
DESKTOP_FILE="$DESKTOP_DIR/video-event-logger.desktop"
STATE_DIR="${XDG_STATE_HOME:-$HOME/.local/state}/video-event-logger"
USER_DATA_DIR="$HOME/VideoEventLogger"

case "$INSTALL_DIR" in
  "$HOME"/*) ;;
  *) fail "INSTALL_DIR must be an absolute path below HOME: $INSTALL_DIR" ;;
esac
case "$INSTALL_DIR" in
  "$HOME"|"$HOME/.local"|"$HOME/.local/opt"|"/")
    fail "refusing unsafe INSTALL_DIR: $INSTALL_DIR"
    ;;
esac
case "$STATE_DIR" in
  "$HOME"/*) ;;
  *) fail "state directory must be below HOME: $STATE_DIR" ;;
esac
case "$STATE_DIR" in
  "$HOME"|"$HOME/.local"|"$HOME/.local/state"|"/")
    fail "refusing unsafe state directory: $STATE_DIR"
    ;;
esac

rm -f "$DESKTOP_FILE"
rm -rf "$STATE_DIR"
rm -rf "$INSTALL_DIR"

if command -v update-desktop-database >/dev/null 2>&1 && [ -d "$DESKTOP_DIR" ]; then
  update-desktop-database "$DESKTOP_DIR" >/dev/null 2>&1 || true
fi

echo "Video Event Logger was removed."
echo "Annotation JSON files were preserved at:"
echo "  $USER_DATA_DIR"

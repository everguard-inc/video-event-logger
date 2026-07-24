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
VAAPI_RUNTIME_BASE="$HOME/.local/opt/video-event-logger-vaapi"
VAAPI_RUNTIME_DIR="$VAAPI_RUNTIME_BASE/24.1.0"
VAAPI_CONFIG_DIR="${XDG_CONFIG_HOME:-$HOME/.config}/video-event-logger"
VAAPI_RUNTIME_MARKER="$VAAPI_CONFIG_DIR/vaapi-runtime"

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
rm -f "$VAAPI_RUNTIME_MARKER"
if [ -d "$VAAPI_RUNTIME_DIR" ]; then
  rm -rf "$VAAPI_RUNTIME_DIR"
fi
rmdir "$VAAPI_RUNTIME_BASE" 2>/dev/null || true
rmdir "$VAAPI_CONFIG_DIR" 2>/dev/null || true

if command -v update-desktop-database >/dev/null 2>&1 && [ -d "$DESKTOP_DIR" ]; then
  update-desktop-database "$DESKTOP_DIR" >/dev/null 2>&1 || true
fi

echo "Video Event Logger was removed."
echo "Annotation JSON files were preserved at:"
echo "  $USER_DATA_DIR"
echo "The optional app-specific VA-API runtime was removed if it was installed."

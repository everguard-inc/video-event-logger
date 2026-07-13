#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")"

APP_NAME="video-event-logger"
APP_DIR="$PWD/$APP_NAME"
INSTALL_DIR="${INSTALL_DIR:-$HOME/.local/opt/video-event-logger}"
DESKTOP_DIR="${XDG_DATA_HOME:-$HOME/.local/share}/applications"
DESKTOP_FILE="$DESKTOP_DIR/video-event-logger.desktop"
LAUNCHER_FILE="$INSTALL_DIR/video-event-logger-launcher"
ICON_FILE="$INSTALL_DIR/video_event_logger/assets/app_icon.svg"

if [ ! -x "$APP_DIR/$APP_NAME" ]; then
  echo "App executable not found: $APP_DIR/$APP_NAME"
  exit 1
fi

if ! command -v vlc >/dev/null 2>&1; then
  echo "Warning: VLC was not found."
  echo "Install it first with: sudo apt install vlc"
fi

if [ -z "$INSTALL_DIR" ] || [ "$INSTALL_DIR" = "/" ]; then
  echo "Refusing to use unsafe INSTALL_DIR: $INSTALL_DIR"
  exit 1
fi

rm -rf "$INSTALL_DIR"
mkdir -p "$INSTALL_DIR" "$DESKTOP_DIR"
cp -R "$APP_DIR/." "$INSTALL_DIR/"

cat > "$LAUNCHER_FILE" <<'LAUNCHER'
#!/usr/bin/env bash
set -e

APP_DIR="$(cd "$(dirname "$0")" && pwd)"

for lib_dir in /usr/lib/x86_64-linux-gnu /usr/lib/aarch64-linux-gnu /usr/lib/arm-linux-gnueabihf; do
  if [ -d "$lib_dir" ]; then
    export LD_LIBRARY_PATH="$lib_dir:${LD_LIBRARY_PATH:-}"
    if [ -d "$lib_dir/vlc/plugins" ]; then
      export VLC_PLUGIN_PATH="$lib_dir/vlc/plugins${VLC_PLUGIN_PATH:+:$VLC_PLUGIN_PATH}"
      export PYTHON_VLC_MODULE_PATH="${PYTHON_VLC_MODULE_PATH:-$lib_dir/vlc/plugins}"
    fi
    if [ -f "$lib_dir/libvlc.so.5" ]; then
      export PYTHON_VLC_LIB_PATH="${PYTHON_VLC_LIB_PATH:-$lib_dir/libvlc.so.5}"
    fi
    break
  fi
done

exec "$APP_DIR/video-event-logger" "$@"
LAUNCHER

chmod +x "$LAUNCHER_FILE"

cat > "$DESKTOP_FILE" <<DESKTOP_ENTRY
[Desktop Entry]
Name=Video Event Logger
Comment=Log video event intervals and export JSON annotations
Exec=$LAUNCHER_FILE
Path=$INSTALL_DIR
Terminal=false
Type=Application
Icon=$ICON_FILE
Categories=AudioVideo;Video;Utility;
StartupNotify=true
DESKTOP_ENTRY

chmod +x "$DESKTOP_FILE"

if command -v update-desktop-database >/dev/null 2>&1; then
  update-desktop-database "$DESKTOP_DIR" >/dev/null 2>&1 || true
fi

echo "Video Event Logger installed."
echo "Open it from the Ubuntu application menu."

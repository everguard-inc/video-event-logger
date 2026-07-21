#!/usr/bin/env bash
set -euo pipefail

APP_NAME="video-event-logger"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

fail() {
  echo "Installation failed: $*" >&2
  exit 1
}

if [ -z "${HOME:-}" ]; then
  fail "HOME is not set"
fi

APP_DIR="${APP_DIR:-$SCRIPT_DIR/$APP_NAME}"
LAUNCHER_SOURCE="${LAUNCHER_SOURCE:-$SCRIPT_DIR/video-event-logger-launcher}"
UNINSTALL_SOURCE="${UNINSTALL_SOURCE:-$SCRIPT_DIR/uninstall.sh}"
BUILD_INFO_SOURCE="${BUILD_INFO_SOURCE:-$SCRIPT_DIR/BUILD_INFO.txt}"
INSTALL_DIR="${INSTALL_DIR:-$HOME/.local/opt/video-event-logger}"
DESKTOP_DIR="${XDG_DATA_HOME:-$HOME/.local/share}/applications"
DESKTOP_FILE="$DESKTOP_DIR/video-event-logger.desktop"
LAUNCHER_FILE="$INSTALL_DIR/video-event-logger-launcher"
ICON_RELATIVE_PATH="_internal/video_event_logger/assets/app_icon.svg"
ICON_FILE="$INSTALL_DIR/$ICON_RELATIVE_PATH"
STATE_DIR="${XDG_STATE_HOME:-$HOME/.local/state}/video-event-logger"
LOG_FILE="$STATE_DIR/application.log"
LIBVLC_PATH=""
VLC_PLUGIN_DIR=""
QXCB_PATH=""

find_libvlc_path() {
  local candidate detected
  for candidate in \
    /usr/lib/x86_64-linux-gnu/libvlc.so.5 \
    /lib/x86_64-linux-gnu/libvlc.so.5 \
    /usr/local/lib/libvlc.so.5; do
    if [ -r "$candidate" ]; then
      printf '%s\n' "$candidate"
      return 0
    fi
  done

  if command -v ldconfig >/dev/null 2>&1; then
    detected="$(ldconfig -p 2>/dev/null | awk '$1 == "libvlc.so.5" { print $NF; exit }')"
    if [ -n "$detected" ] && [ -r "$detected" ]; then
      printf '%s\n' "$detected"
      return 0
    fi
  fi
  return 1
}

find_vlc_plugin_dir() {
  local candidate detected libvlc_dir
  if [ -n "$LIBVLC_PATH" ]; then
    libvlc_dir="$(dirname "$LIBVLC_PATH")"
    if [ -d "$libvlc_dir/vlc/plugins" ]; then
      printf '%s\n' "$libvlc_dir/vlc/plugins"
      return 0
    fi
  else
    libvlc_dir=""
  fi

  for candidate in \
    /usr/lib/x86_64-linux-gnu/vlc/plugins \
    /usr/lib/vlc/plugins \
    /usr/local/lib/vlc/plugins; do
    if [ -n "$candidate" ] && [ -d "$candidate" ]; then
      printf '%s\n' "$candidate"
      return 0
    fi
  done

  detected="$(find /usr/lib /usr/local/lib -type d -path '*/vlc/plugins' -print -quit 2>/dev/null || true)"
  if [ -n "$detected" ]; then
    printf '%s\n' "$detected"
    return 0
  fi
  return 1
}

refresh_runtime_paths() {
  LIBVLC_PATH="$(find_libvlc_path || true)"
  VLC_PLUGIN_DIR="$(find_vlc_plugin_dir || true)"
}

print_runtime_diagnostics() {
  local qxcb_missing="not checked"
  if [ -n "$QXCB_PATH" ] && [ -f "$QXCB_PATH" ]; then
    qxcb_missing="$(ldd "$QXCB_PATH" 2>/dev/null | awk '/not found/ { printf "%s%s", separator, $1; separator=", " }')"
    qxcb_missing="${qxcb_missing:-none}"
  fi
  echo "Runtime dependency diagnostics:" >&2
  echo "  vlc command: $(command -v vlc 2>/dev/null || echo missing)" >&2
  echo "  file command: $(command -v file 2>/dev/null || echo missing)" >&2
  echo "  libVLC: ${LIBVLC_PATH:-missing}" >&2
  echo "  VLC plugins: ${VLC_PLUGIN_DIR:-not detected; system default will be used}" >&2
  echo "  Qt xcb plugin: ${QXCB_PATH:-missing}" >&2
  echo "  Qt xcb missing libraries: $qxcb_missing" >&2
}

qt_runtime_dependencies_ready() {
  local qxcb_ldd
  [ -n "$QXCB_PATH" ] && [ -f "$QXCB_PATH" ] || return 1
  qxcb_ldd="$(ldd "$QXCB_PATH" 2>&1)" || return 1
  ! grep -Fq "not found" <<< "$qxcb_ldd"
}

runtime_dependencies_ready() {
  refresh_runtime_paths
  command -v vlc >/dev/null 2>&1 \
    && command -v file >/dev/null 2>&1 \
    && [ -n "$LIBVLC_PATH" ] \
    && qt_runtime_dependencies_ready
}

install_runtime_dependencies() {
  if runtime_dependencies_ready; then
    echo "Ubuntu runtime dependencies are already installed."
    print_runtime_diagnostics
    return
  fi

  command -v apt >/dev/null 2>&1 || fail "the apt package manager is required"
  local gtk_package="libgtk-3-0"
  if ! apt-cache show "$gtk_package" >/dev/null 2>&1 \
    && apt-cache show libgtk-3-0t64 >/dev/null 2>&1; then
    gtk_package="libgtk-3-0t64"
  fi
  local packages=(vlc file libxcb-cursor0 "$gtk_package")
  echo "Installing required Ubuntu packages: ${packages[*]}"

  if [ "$(id -u)" -eq 0 ]; then
    apt update
    DEBIAN_FRONTEND=noninteractive apt install -y "${packages[@]}"
    ldconfig
  else
    if ! command -v sudo >/dev/null 2>&1; then
      echo "Administrator access is required to install system packages." >&2
      echo "Run these commands and start install.sh again:" >&2
      echo "  sudo apt update" >&2
      echo "  sudo apt install vlc file libxcb-cursor0 libgtk-3-0" >&2
      exit 1
    fi
    sudo apt update
    sudo apt install "${packages[@]}"
    sudo ldconfig
  fi

  if ! qt_runtime_dependencies_ready \
    && ldd "$QXCB_PATH" 2>/dev/null | grep -Fq "libxcb-cursor.so.0 => not found"; then
    echo "Repairing missing libxcb-cursor.so.0..."
    if [ "$(id -u)" -eq 0 ]; then
      DEBIAN_FRONTEND=noninteractive apt install -y --reinstall libxcb-cursor0
      ldconfig
    else
      sudo apt install --reinstall libxcb-cursor0
      sudo ldconfig
    fi
  fi

  if ! runtime_dependencies_ready; then
    print_runtime_diagnostics
    fail "required runtime components are still unavailable after package installation"
  fi
  print_runtime_diagnostics
}

if [ ! -x "$APP_DIR/$APP_NAME" ]; then
  fail "app executable is missing or not executable: $APP_DIR/$APP_NAME"
fi
if [ ! -f "$LAUNCHER_SOURCE" ]; then
  fail "launcher is missing: $LAUNCHER_SOURCE"
fi
if [ ! -f "$UNINSTALL_SOURCE" ]; then
  fail "uninstaller is missing: $UNINSTALL_SOURCE"
fi
if [ ! -f "$BUILD_INFO_SOURCE" ]; then
  fail "build metadata is missing: $BUILD_INFO_SOURCE"
fi

case "$INSTALL_DIR" in
  "$HOME"/*) ;;
  *) fail "INSTALL_DIR must be an absolute path below HOME: $INSTALL_DIR" ;;
esac
case "$INSTALL_DIR" in
  "$HOME"|"$HOME/.local"|"$HOME/.local/opt"|"/")
    fail "refusing unsafe INSTALL_DIR: $INSTALL_DIR"
    ;;
esac
case "$INSTALL_DIR" in
  *$'\n'*) fail "INSTALL_DIR must not contain a newline" ;;
esac

if [ "$(uname -m)" != "x86_64" ]; then
  fail "this package requires x86_64; detected $(uname -m)"
fi

QXCB_PATH="$(find "$APP_DIR" -type f -name 'libqxcb.so' -print -quit)"
if [ -z "$QXCB_PATH" ]; then
  fail "Qt xcb platform plugin is missing from the package"
fi

install_runtime_dependencies

EXECUTABLE_DESCRIPTION="$(file -b "$APP_DIR/$APP_NAME")"
case "$EXECUTABLE_DESCRIPTION" in
  *"ELF 64-bit"*"x86-64"*) ;;
  *) fail "packaged executable is not an x86-64 ELF: $EXECUTABLE_DESCRIPTION" ;;
esac

if ! qxcb_ldd="$(ldd "$QXCB_PATH" 2>&1)" || grep -Fq "not found" <<< "$qxcb_ldd"; then
  echo "$qxcb_ldd" >&2
  print_runtime_diagnostics
  fail "Qt xcb runtime dependencies are missing"
fi

if ! libvlc_ldd="$(ldd "$LIBVLC_PATH" 2>&1)" || grep -Fq "not found" <<< "$libvlc_ldd"; then
  echo "$libvlc_ldd" >&2
  fail "system libVLC has missing shared-library dependencies"
fi

export PYTHON_VLC_LIB_PATH="$LIBVLC_PATH"
if [ -n "$VLC_PLUGIN_DIR" ]; then
  export VLC_PLUGIN_PATH="$VLC_PLUGIN_DIR"
elif [ -n "${VLC_PLUGIN_PATH:-}" ] && [ ! -d "$VLC_PLUGIN_PATH" ]; then
  unset VLC_PLUGIN_PATH
fi

echo "Running packaged application smoke test before installation..."
if ! QT_QPA_PLATFORM=offscreen "$APP_DIR/$APP_NAME" --smoke-test; then
  print_runtime_diagnostics
  fail "packaged application smoke test failed; the application was not installed"
fi

INSTALL_PARENT="$(dirname "$INSTALL_DIR")"
mkdir -p "$INSTALL_PARENT" "$DESKTOP_DIR" "$STATE_DIR"
STAGING_DIR="$(mktemp -d "$INSTALL_PARENT/.video-event-logger.install.XXXXXX")"
BACKUP_DIR="$INSTALL_PARENT/.video-event-logger.backup.$$"
DESKTOP_TEMP=""

cleanup() {
  if [ -n "${STAGING_DIR:-}" ] && [ -d "$STAGING_DIR" ]; then
    rm -rf "$STAGING_DIR"
  fi
  if [ -n "${DESKTOP_TEMP:-}" ] && [ -f "$DESKTOP_TEMP" ]; then
    rm -f "$DESKTOP_TEMP"
  fi
}
trap cleanup EXIT

cp -R "$APP_DIR/." "$STAGING_DIR/"
cp "$LAUNCHER_SOURCE" "$STAGING_DIR/video-event-logger-launcher"
cp "$UNINSTALL_SOURCE" "$STAGING_DIR/uninstall.sh"
cp "$BUILD_INFO_SOURCE" "$STAGING_DIR/BUILD_INFO.txt"
chmod +x \
  "$STAGING_DIR/$APP_NAME" \
  "$STAGING_DIR/video-event-logger-launcher" \
  "$STAGING_DIR/uninstall.sh"

if [ ! -f "$STAGING_DIR/$ICON_RELATIVE_PATH" ]; then
  fail "application icon is missing from the package"
fi
if [ -e "$BACKUP_DIR" ]; then
  fail "temporary backup path already exists: $BACKUP_DIR"
fi
if [ -e "$INSTALL_DIR" ]; then
  mv "$INSTALL_DIR" "$BACKUP_DIR"
fi
if ! mv "$STAGING_DIR" "$INSTALL_DIR"; then
  if [ -d "$BACKUP_DIR" ]; then
    mv "$BACKUP_DIR" "$INSTALL_DIR"
  fi
  fail "could not activate the new installation"
fi
STAGING_DIR=""
if [ -d "$BACKUP_DIR" ]; then
  rm -rf "$BACKUP_DIR"
fi

DESKTOP_TEMP="$(mktemp "$DESKTOP_DIR/.video-event-logger.desktop.XXXXXX")"
cat > "$DESKTOP_TEMP" <<DESKTOP_ENTRY
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
chmod +x "$DESKTOP_TEMP"
mv "$DESKTOP_TEMP" "$DESKTOP_FILE"
DESKTOP_TEMP=""

if command -v update-desktop-database >/dev/null 2>&1; then
  update-desktop-database "$DESKTOP_DIR" >/dev/null 2>&1 || true
fi

echo
echo "Video Event Logger installed."
echo
echo "Launcher:"
echo "  $LAUNCHER_FILE"
echo
echo "Application log:"
echo "  $LOG_FILE"
echo
echo "Manual start:"
echo "  $LAUNCHER_FILE"
echo
echo "Uninstall:"
echo "  bash $INSTALL_DIR/uninstall.sh"

#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/../.."

DIST_DIR="${DIST_DIR:-dist/video-event-logger}"
APP_EXECUTABLE="$DIST_DIR/video-event-logger"
DIST_RUNTIME_DIR="$DIST_DIR/_internal"
BUILD_INFO_PATH="${BUILD_INFO_PATH:-build/BUILD_INFO.txt}"
MAX_GLIBC_VERSION="2.31"

fail() {
  echo "Validation failed: $*" >&2
  exit 1
}

for command_name in file ldd objdump find grep sort; do
  command -v "$command_name" >/dev/null 2>&1 || fail "missing command: $command_name"
done

[ "$(uname -m)" = "x86_64" ] || fail "builder architecture is $(uname -m), expected x86_64"
[ "$(dpkg --print-architecture)" = "amd64" ] || fail "dpkg architecture is not amd64"
[ -x "$APP_EXECUTABLE" ] || fail "main executable is missing: $APP_EXECUTABLE"
[ -d "$DIST_RUNTIME_DIR" ] || fail "PyInstaller runtime directory is missing: $DIST_RUNTIME_DIR"
[ -f "$BUILD_INFO_PATH" ] || fail "BUILD_INFO.txt is missing: $BUILD_INFO_PATH"

# PyInstaller adds _internal to the dynamic-loader path when the application
# starts. Mirror that environment while inspecting bundled ELF files so that
# sibling libraries (for example libssl.so.3 -> libcrypto.so.3) resolve here.
DIST_LD_LIBRARY_PATH="$DIST_RUNTIME_DIR${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"

MAIN_DESCRIPTION="$(file -b "$APP_EXECUTABLE")"
case "$MAIN_DESCRIPTION" in
  *"ELF 64-bit"*"x86-64"*) ;;
  *) fail "main executable is not an x86-64 ELF: $MAIN_DESCRIPTION" ;;
esac
echo "Main executable: $MAIN_DESCRIPTION"

mapfile -d '' ELF_FILES < <(find "$DIST_DIR" -type f -print0)
checked_elf_count=0
glibc_failure=0

for candidate in "${ELF_FILES[@]}"; do
  description="$(file -b "$candidate")"
  case "$description" in
    *ELF*executable*|*ELF*"shared object"*) ;;
    *) continue ;;
  esac

  checked_elf_count=$((checked_elf_count + 1))
  if ! ldd_output="$(LD_LIBRARY_PATH="$DIST_LD_LIBRARY_PATH" ldd "$candidate" 2>&1)"; then
    echo "$ldd_output" >&2
    fail "ldd could not inspect $candidate"
  fi
  if grep -Fq "not found" <<< "$ldd_output"; then
    echo "$ldd_output" >&2
    fail "missing shared-library dependency in $candidate"
  fi

  if ! symbol_table="$(objdump -T "$candidate" 2>&1)"; then
    echo "$symbol_table" >&2
    fail "objdump could not inspect $candidate"
  fi
  required_versions="$(sed -n 's/.*GLIBC_\([0-9][0-9.]*\).*/\1/p' <<< "$symbol_table" | sort -Vu)"
  for version in $required_versions; do
    highest="$(printf '%s\n%s\n' "$MAX_GLIBC_VERSION" "$version" | sort -V | tail -n 1)"
    if [ "$highest" = "$version" ] && [ "$version" != "$MAX_GLIBC_VERSION" ]; then
      echo "Unsupported GLIBC_$version required by: $candidate" >&2
      glibc_failure=1
    fi
  done
done

[ "$checked_elf_count" -gt 0 ] || fail "no ELF executables or shared objects found"
[ "$glibc_failure" -eq 0 ] || fail "one or more files require glibc newer than $MAX_GLIBC_VERSION"
echo "ELF files checked: $checked_elf_count"

vlc_files="$(find "$DIST_DIR" -type f \( -name 'libvlc.so' -o -name 'libvlc.so.*' -o -name 'libvlccore.so' -o -name 'libvlccore.so.*' \) -print)"
[ -z "$vlc_files" ] || fail "system VLC libraries were bundled:\n$vlc_files"
vlc_plugin_dirs="$(find "$DIST_DIR" -type d -path '*/vlc/plugins' -print)"
[ -z "$vlc_plugin_dirs" ] || fail "a VLC plugin directory was bundled:\n$vlc_plugin_dirs"

QXCB_PATH="$(find "$DIST_DIR" -type f -name 'libqxcb.so' -print -quit)"
[ -n "$QXCB_PATH" ] || fail "Qt xcb platform plugin libqxcb.so is missing"
if ! qxcb_ldd="$(LD_LIBRARY_PATH="$DIST_LD_LIBRARY_PATH" ldd "$QXCB_PATH" 2>&1)"; then
  echo "$qxcb_ldd" >&2
  fail "ldd could not inspect $QXCB_PATH"
fi
if grep -Fq "not found" <<< "$qxcb_ldd"; then
  echo "$qxcb_ldd" >&2
  fail "libqxcb.so has missing dependencies"
fi
echo "Qt xcb plugin: $QXCB_PATH"

PYTHON_RUNTIME="$(find "$DIST_DIR" -type f -name 'libpython3.12.so*' -print -quit)"
[ -n "$PYTHON_RUNTIME" ] || fail "bundled Python 3.12 runtime was not found"
echo "Python runtime: $PYTHON_RUNTIME"

LIBFFI_RUNTIME="$(find "$DIST_DIR" -type f -name 'libffi.so.7*' -print -quit)"
[ -n "$LIBFFI_RUNTIME" ] || fail "bundled libffi.so.7 compatibility runtime was not found"
echo "libffi compatibility runtime: $LIBFFI_RUNTIME"

OPENSSL_CRYPTO_RUNTIME="$(find "$DIST_DIR" -type f -name 'libcrypto.so.3' -print -quit)"
OPENSSL_SSL_RUNTIME="$(find "$DIST_DIR" -type f -name 'libssl.so.3' -print -quit)"
[ -n "$OPENSSL_CRYPTO_RUNTIME" ] || fail "bundled OpenSSL 3 libcrypto runtime was not found"
[ -n "$OPENSSL_SSL_RUNTIME" ] || fail "bundled OpenSSL 3 libssl runtime was not found"
echo "OpenSSL crypto runtime: $OPENSSL_CRYPTO_RUNTIME"
echo "OpenSSL TLS runtime: $OPENSSL_SSL_RUNTIME"

OPENSSL_LICENSE="$(find "$DIST_DIR" -type f -path '*/licenses/openssl/LICENSE.txt' -print -quit)"
[ -n "$OPENSSL_LICENSE" ] || fail "bundled OpenSSL license was not found"

APP_ICON="$(find "$DIST_DIR" -type f -path '*/video_event_logger/assets/app_icon.svg' -print -quit)"
[ -n "$APP_ICON" ] || fail "application icon is missing from the PyInstaller output"

for metadata_field in \
  "Application version:" \
  "Build mode:" \
  "Build date UTC:" \
  "Target platform:" \
  "Target architecture:" \
  "Ubuntu base version:" \
  "Python version:" \
  "PyInstaller version:" \
  "PySide6 version:" \
  "python-vlc version:"; do
  grep -q "^$metadata_field" "$BUILD_INFO_PATH" || fail "BUILD_INFO.txt lacks field: $metadata_field"
done
grep -q '^Bundled OpenSSL version: OpenSSL 3\.' "$BUILD_INFO_PATH" \
  || fail "BUILD_INFO.txt lacks the bundled OpenSSL 3 version"

if ! command -v vlc >/dev/null 2>&1 || [ ! -f /usr/lib/x86_64-linux-gnu/libvlc.so.5 ]; then
  fail "builder VLC/libVLC is unavailable for the packaged smoke test"
fi
VLC_XCB_X11_PLUGIN="/usr/lib/x86_64-linux-gnu/vlc/plugins/video_output/libxcb_x11_plugin.so"
[ -f "$VLC_XCB_X11_PLUGIN" ] \
  || fail "VLC xcb_x11 video-output plugin is unavailable: $VLC_XCB_X11_PLUGIN"
QT_QPA_PLATFORM=offscreen "$APP_EXECUTABLE" --smoke-test

echo "Ubuntu 20.04 package validation passed."

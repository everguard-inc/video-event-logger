#!/usr/bin/env bash
set -euo pipefail
export LC_ALL=C

# Optional, app-scoped workaround for the old Intel VA-API stack shipped by
# Ubuntu 20.04. Nothing is copied to /usr and no installed graphics package is
# replaced. The launcher opts into this runtime only when the marker written by
# this script exists.

STACK_VERSION="24.1.0"
LIBVA_COMMIT="907b2b5405ca1091b4360bf35060e143bd704b62"
LIBVA_SHA256="25776fd0f0d5ec87a7abe5392bc9951e117c448e7edc45dc23a737333e3b971b"
GMMLIB_COMMIT="92d702f885ae7bbfcd5b480c262db805ccc580bf"
GMMLIB_SHA256="70597c50e56df33aee72663cce404d0559dc4574feb4024715bb3a97e789e5b1"
MEDIA_DRIVER_COMMIT="8b608aef2aecfea2eb281e6a35b08203c427defa"
MEDIA_DRIVER_SHA256="1f978b7d2390996be5275b4da6316594227a90de6841e62f9010b7b04c249b58"

fail() {
  echo "Fix failed: $*" >&2
  exit 1
}

if [ -z "${HOME:-}" ]; then
  fail "HOME is not set"
fi

RUNTIME_BASE="$HOME/.local/opt/video-event-logger-vaapi"
RUNTIME_DIR="$RUNTIME_BASE/$STACK_VERSION"
CONFIG_DIR="${XDG_CONFIG_HOME:-$HOME/.config}/video-event-logger"
RUNTIME_MARKER="$CONFIG_DIR/vaapi-runtime"
JOBS="${VIDEO_EVENT_LOGGER_FIX_JOBS:-$(getconf _NPROCESSORS_ONLN 2>/dev/null || echo 2)}"
BUILD_ROOT=""

case "$RUNTIME_BASE" in
  "$HOME"/*) ;;
  *) fail "runtime directory must be below HOME: $RUNTIME_BASE" ;;
esac
case "$RUNTIME_DIR" in
  "$RUNTIME_BASE"/*) ;;
  *) fail "unsafe runtime directory: $RUNTIME_DIR" ;;
esac
case "$JOBS" in
  ''|*[!0-9]*) fail "VIDEO_EVENT_LOGGER_FIX_JOBS must be a positive integer" ;;
esac
if [ "$JOBS" -lt 1 ]; then
  fail "VIDEO_EVENT_LOGGER_FIX_JOBS must be a positive integer"
fi

cleanup() {
  if [ -n "$BUILD_ROOT" ] && [ -d "$BUILD_ROOT" ]; then
    case "$BUILD_ROOT" in
      "$RUNTIME_BASE"/.build.*) rm -rf "$BUILD_ROOT" ;;
      *) echo "Refusing to remove unexpected temporary directory: $BUILD_ROOT" >&2 ;;
    esac
  fi
}
trap cleanup EXIT

usage() {
  cat <<'EOF'
Optional Ubuntu 20.04 Intel Gen12 video workaround for Video Event Logger.

Usage:
  bash fix.sh diagnose
  bash fix.sh install
  bash fix.sh status
  bash fix.sh uninstall

diagnose   Print read-only OS, GPU, VA-API, VLC, and active-fix details.
install    Build a pinned Intel VA-API runtime under the current user's HOME
           and enable it only for Video Event Logger. Requires internet access,
           about 2 GB of free space while building, and sudo for build tools.
status     Show whether the private runtime is installed and enabled.
uninstall Disable and remove only the private runtime. System drivers and VLC
           are never removed or changed.
EOF
}

os_value() {
  local key="$1"
  [ -r /etc/os-release ] || return 0
  sed -n "s/^${key}=//p" /etc/os-release | head -n 1 | tr -d '"'
}

is_ubuntu_20_04() {
  [ "$(os_value ID)" = "ubuntu" ] && [ "$(os_value VERSION_ID)" = "20.04" ]
}

has_intel_gpu() {
  local vendor_file
  for vendor_file in /sys/class/drm/card*/device/vendor; do
    if [ -r "$vendor_file" ] && [ "$(tr '[:upper:]' '[:lower:]' < "$vendor_file")" = "0x8086" ]; then
      return 0
    fi
  done
  if command -v lspci >/dev/null 2>&1; then
    lspci -nn 2>/dev/null | grep -Eiq 'Intel Corporation.*(VGA|Display|Graphics)|((VGA|Display).*)Intel Corporation'
    return
  fi
  return 1
}

has_supported_intel_gpu() {
  local device_file device_id
  for device_file in /sys/class/drm/card*/device/device; do
    if [ -r "$device_file" ]; then
      device_id="$(tr '[:upper:]' '[:lower:]' < "$device_file")"
      case "$device_id" in
        0x9a??|0x4c??|0x46??) return 0 ;;
      esac
    fi
  done
  if command -v lspci >/dev/null 2>&1; then
    lspci -nn 2>/dev/null \
      | tr '[:upper:]' '[:lower:]' \
      | grep -Eq '\[8086:(9a|4c|46)[0-9a-f]{2}\]'
    return
  fi
  return 1
}

marker_runtime() {
  local configured=""
  if [ -f "$RUNTIME_MARKER" ]; then
    IFS= read -r configured < "$RUNTIME_MARKER" || true
  fi
  printf '%s\n' "$configured"
}

runtime_is_complete() {
  local root="$1"
  [ -f "$root/lib/libva.so.2" ] \
    && [ -f "$root/lib/libva-drm.so.2" ] \
    && [ -f "$root/lib/libva-x11.so.2" ] \
    && [ -f "$root/lib/libigdgmm.so.12" ] \
    && [ -f "$root/lib/dri/iHD_drv_video.so" ]
}

print_vainfo() {
  local root="${1:-}"
  local driver_dir=""
  local library_path="${LD_LIBRARY_PATH:-}"
  if ! command -v vainfo >/dev/null 2>&1; then
    echo "  vainfo: not installed"
    return 0
  fi
  if [ -n "$root" ]; then
    driver_dir="$root/lib/dri"
    library_path="$root/lib${library_path:+:$library_path}"
  fi

  local output=""
  if [ -r /dev/dri/renderD128 ]; then
    output="$(
      LIBVA_DRIVER_NAME=iHD \
      LIBVA_DRIVERS_PATH="${driver_dir:-/usr/lib/x86_64-linux-gnu/dri}" \
      LD_LIBRARY_PATH="$library_path" \
      vainfo --display drm --device /dev/dri/renderD128 2>&1 || true
    )"
  fi
  if [ -z "$output" ] || ! grep -Fq 'va_openDriver() returns 0' <<< "$output"; then
    output="$(
      LIBVA_DRIVER_NAME=iHD \
      LIBVA_DRIVERS_PATH="${driver_dir:-/usr/lib/x86_64-linux-gnu/dri}" \
      LD_LIBRARY_PATH="$library_path" \
      vainfo 2>&1 || true
    )"
  fi
  if [ -z "$output" ]; then
    echo "  vainfo: produced no output"
    return 0
  fi
  sed -n \
    -e '/VA-API version/p' \
    -e '/Driver version/p' \
    -e '/Trying to open/p' \
    -e '/va_openDriver()/p' \
    -e '/vaInitialize failed/p' \
    <<< "$output" | sed 's/^/  /'
}

diagnose() {
  local configured
  configured="$(marker_runtime)"
  echo "Video Event Logger Intel video diagnostics"
  echo "  OS: $(os_value PRETTY_NAME)"
  echo "  architecture: $(uname -m)"
  if has_intel_gpu; then
    echo "  Intel GPU: detected"
  else
    echo "  Intel GPU: not detected"
  fi
  if has_supported_intel_gpu; then
    echo "  supported Intel Gen12 GPU: detected"
  else
    echo "  supported Intel Gen12 GPU: not detected"
  fi
  echo "  VLC: $(vlc --version 2>/dev/null | head -n 1 || echo not installed)"
  echo "  system VA-API:"
  print_vainfo
  if [ -n "$configured" ]; then
    echo "  configured private runtime: $configured"
    if runtime_is_complete "$configured"; then
      echo "  private runtime files: complete"
      echo "  private VA-API:"
      print_vainfo "$configured"
    else
      echo "  private runtime files: incomplete"
    fi
  else
    echo "  configured private runtime: none"
  fi
}

status() {
  local configured
  configured="$(marker_runtime)"
  if [ -z "$configured" ]; then
    echo "The optional Intel VA-API fix is not enabled."
    return 1
  fi
  echo "Configured runtime: $configured"
  if [ "$configured" != "$RUNTIME_DIR" ]; then
    echo "The marker points to an unexpected runtime."
    return 1
  fi
  if ! runtime_is_complete "$configured"; then
    echo "The private runtime is incomplete. Run: bash fix.sh uninstall"
    return 1
  fi
  echo "The optional Intel VA-API fix is installed and enabled for Video Event Logger."
}

require_install_target() {
  if [ "${VIDEO_EVENT_LOGGER_FIX_ALLOW_UNSUPPORTED:-0}" = "1" ]; then
    return 0
  fi
  [ "$(id -u)" -ne 0 ] \
    || fail "run fix.sh as the normal desktop user, without sudo; it will request sudo only for build tools"
  [ "$(uname -s)" = "Linux" ] || fail "install is supported only on Linux"
  [ "$(uname -m)" = "x86_64" ] || fail "install requires x86_64"
  is_ubuntu_20_04 || fail "this workaround is only for Ubuntu 20.04"
  has_supported_intel_gpu \
    || fail "a supported Intel Gen12 GPU was not detected; this workaround does not apply"
}

require_build_space() {
  local available_kb
  available_kb="$(df -Pk "$RUNTIME_BASE" | awk 'NR == 2 { print $4 }')"
  case "$available_kb" in
    ''|*[!0-9]*) fail "could not determine free space below $RUNTIME_BASE" ;;
  esac
  if [ "$available_kb" -lt 2097152 ]; then
    fail "at least 2 GB of free space is required while building the private runtime"
  fi
}

install_dependencies() {
  command -v apt-get >/dev/null 2>&1 || fail "apt-get is required"
  local packages=(
    build-essential
    ca-certificates
    cmake
    curl
    libdrm-dev
    libpciaccess-dev
    libx11-dev
    libx11-xcb-dev
    libxcb-dri3-dev
    libxcb1-dev
    libxext-dev
    libxfixes-dev
    meson
    ninja-build
    pkg-config
    vainfo
  )
  echo "Installing build tools and headers (system graphics drivers are not changed)..."
  if [ "$(id -u)" -eq 0 ]; then
    apt-get update
    DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends "${packages[@]}"
  else
    command -v sudo >/dev/null 2>&1 || fail "sudo is required to install build dependencies"
    sudo apt-get update
    sudo apt-get install --no-install-recommends "${packages[@]}"
  fi
}

download_source() {
  local name="$1"
  local repository="$2"
  local commit="$3"
  local expected_sha="$4"
  local archive="$BUILD_ROOT/$name.tar.gz"
  echo "Downloading $name..."
  curl \
    --fail \
    --location \
    --proto '=https' \
    --retry 3 \
    --show-error \
    --silent \
    "https://github.com/intel/$repository/archive/$commit.tar.gz" \
    --output "$archive"
  printf '%s  %s\n' "$expected_sha" "$archive" | sha256sum --check --status \
    || fail "checksum verification failed for $name"
  mkdir -p "$BUILD_ROOT/src/$name"
  tar -xzf "$archive" -C "$BUILD_ROOT/src/$name" --strip-components=1
}

validate_built_runtime() {
  local root="$1"
  local driver="$root/lib/dri/iHD_drv_video.so"
  runtime_is_complete "$root" || fail "the built runtime is missing required files"
  local ldd_output
  ldd_output="$(LD_LIBRARY_PATH="$root/lib" ldd "$driver" 2>&1)" \
    || fail "could not inspect the built Intel driver"
  if grep -Fq 'not found' <<< "$ldd_output"; then
    echo "$ldd_output" >&2
    fail "the built Intel driver has unresolved libraries"
  fi
}

activate_runtime() {
  mkdir -p "$CONFIG_DIR"
  local marker_temp
  marker_temp="$(mktemp "$CONFIG_DIR/.vaapi-runtime.XXXXXX")"
  printf '%s\n' "$RUNTIME_DIR" > "$marker_temp"
  chmod 600 "$marker_temp"
  mv "$marker_temp" "$RUNTIME_MARKER"
}

install_fix() {
  require_install_target
  if runtime_is_complete "$RUNTIME_DIR"; then
    activate_runtime
    echo "The private Intel VA-API $STACK_VERSION runtime was already present and is now enabled."
    return 0
  fi
  if [ -e "$RUNTIME_DIR" ]; then
    fail "an incomplete runtime already exists at $RUNTIME_DIR; run uninstall first"
  fi

  install_dependencies
  for command_name in cmake curl meson ninja pkg-config sha256sum tar; do
    command -v "$command_name" >/dev/null 2>&1 || fail "missing build command: $command_name"
  done

  mkdir -p "$RUNTIME_BASE"
  require_build_space
  BUILD_ROOT="$(mktemp -d "$RUNTIME_BASE/.build.XXXXXX")"
  local stage="$BUILD_ROOT/runtime"
  mkdir -p "$stage"

  download_source libva libva "$LIBVA_COMMIT" "$LIBVA_SHA256"
  download_source gmmlib gmmlib "$GMMLIB_COMMIT" "$GMMLIB_SHA256"
  download_source media-driver media-driver "$MEDIA_DRIVER_COMMIT" "$MEDIA_DRIVER_SHA256"

  echo "Building libva 2.20.0..."
  meson setup "$BUILD_ROOT/build-libva" "$BUILD_ROOT/src/libva" \
    --prefix "$stage" \
    --libdir lib \
    --buildtype release \
    -Ddriverdir="$stage/lib/dri" \
    -Dwith_x11=yes \
    -Dwith_glx=no \
    -Dwith_wayland=no
  ninja -C "$BUILD_ROOT/build-libva" -j "$JOBS"
  meson install -C "$BUILD_ROOT/build-libva"

  echo "Building gmmlib 22.3.14..."
  cmake \
    -S "$BUILD_ROOT/src/gmmlib" \
    -B "$BUILD_ROOT/build-gmmlib" \
    -DCMAKE_BUILD_TYPE=Release \
    -DCMAKE_INSTALL_PREFIX="$stage" \
    -DCMAKE_INSTALL_LIBDIR=lib \
    -DRUN_TEST_SUITE=OFF
  cmake --build "$BUILD_ROOT/build-gmmlib" --parallel "$JOBS"
  cmake --install "$BUILD_ROOT/build-gmmlib"

  echo "Building Intel media-driver 24.1.0..."
  PKG_CONFIG_PATH="$stage/lib/pkgconfig" \
  CMAKE_PREFIX_PATH="$stage" \
  LD_LIBRARY_PATH="$stage/lib${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}" \
  cmake \
    -S "$BUILD_ROOT/src/media-driver" \
    -B "$BUILD_ROOT/build-media-driver" \
    -DCMAKE_BUILD_TYPE=Release \
    -DCMAKE_INSTALL_PREFIX="$stage" \
    -DCMAKE_INSTALL_LIBDIR=lib \
    -DLIBVA_DRIVERS_PATH="$stage/lib/dri" \
    -DBUILD_CMRTLIB=OFF \
    -DBUILD_KERNELS=OFF \
    -DENABLE_KERNELS=ON \
    -DENABLE_NONFREE_KERNELS=ON \
    -DGEN8=OFF \
    -DGEN9=OFF \
    -DGEN11=OFF \
    -DGEN12=ON \
    -DXe_M=OFF \
    -DMTL=OFF \
    -DARL=OFF \
    -DINSTALL_DRIVER_SYSCONF=OFF \
    -DMEDIA_RUN_TEST_SUITE=OFF
  cmake --build "$BUILD_ROOT/build-media-driver" --parallel "$JOBS"
  cmake --install "$BUILD_ROOT/build-media-driver"

  validate_built_runtime "$stage"
  mv "$stage" "$RUNTIME_DIR"
  activate_runtime

  echo
  echo "Private Intel VA-API $STACK_VERSION runtime installed."
  echo "It is enabled only for Video Event Logger. Restart the application and test the affected video."
  echo "Rollback: bash fix.sh uninstall"
}

uninstall_fix() {
  local configured
  configured="$(marker_runtime)"
  if [ -f "$RUNTIME_MARKER" ]; then
    rm -f "$RUNTIME_MARKER"
  fi
  if [ -d "$RUNTIME_DIR" ]; then
    case "$RUNTIME_DIR" in
      "$HOME/.local/opt/video-event-logger-vaapi/$STACK_VERSION") rm -rf "$RUNTIME_DIR" ;;
      *) fail "refusing to remove unexpected runtime path: $RUNTIME_DIR" ;;
    esac
  fi
  rmdir "$RUNTIME_BASE" 2>/dev/null || true
  rmdir "$CONFIG_DIR" 2>/dev/null || true
  echo "The optional Video Event Logger VA-API runtime was disabled and removed."
  if [ -n "$configured" ] && [ "$configured" != "$RUNTIME_DIR" ]; then
    echo "Note: the previous marker pointed elsewhere and that directory was not removed: $configured"
  fi
  echo "System graphics drivers and VLC were not changed. Build dependencies were left installed."
}

command_name="${1:-}"
case "$command_name" in
  diagnose) diagnose ;;
  install) install_fix ;;
  status) status ;;
  uninstall) uninstall_fix ;;
  -h|--help|help|'') usage ;;
  *) usage >&2; exit 2 ;;
esac

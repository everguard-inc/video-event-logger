# Ubuntu 20.04 x86_64 packaging

Build baseline: **Ubuntu 20.04 x86_64** (`linux/amd64`). The launcher also supports Wayland-based Ubuntu 24.04 sessions through XWayland because libVLC 3 requires an X11 window id for embedded playback; container validation still runs against the Ubuntu 20.04 baseline.

The build runs entirely inside an Ubuntu 20.04 Docker image, compiles Python 3.12.4 with a shared runtime, creates a PyInstaller `onedir` application, validates the result, and emits a release archive. The target machine does not need Python. VLC/libVLC must be installed on the target system and is deliberately not included in the archive. A current OpenSSL 3 runtime is built on Ubuntu 20.04 and bundled narrowly for Qt HTTPS support because the target OS provides only OpenSSL 1.1.

## Host prerequisites

- Docker with the `buildx` component;
- permission to run Docker containers;
- support for `linux/amd64` containers;
- approximately 12 GB of free disk space for the Docker image, Python compilation, PySide6, and PyInstaller output.

On Apple Silicon, Docker Desktop uses x86_64 emulation. The build command explicitly sets `linux/amd64`; compiling Python with profile-guided optimizations can therefore take considerably longer than on a native x86_64 host.

Downloaded Python wheels are retained in the Docker volume `video-event-logger-pip-cache`, so later source-only rebuilds do not need to download PySide6 again.

## Release build

Run from the repository root:

```bash
bash packaging/ubuntu_20_04/build_release.sh
```

The validated archive is written to:

```text
release/video-event-logger-v<version>-ubuntu20.04-amd64.tar.gz
```

## Debug build

```bash
BUILD_MODE=debug bash packaging/ubuntu_20_04/build_release.sh
```

Debug mode builds the same `onedir` layout with PyInstaller `console=True` and `debug=True`. The installed launcher leaves stdout and stderr attached to the invoking terminal. Release mode appends them to the persistent application log.

## What the build validates

Before any archive is created, `validate_build.sh` verifies:

- builder architecture is `x86_64`/`amd64`;
- the main executable is an x86-64 ELF;
- every ELF executable/shared object has no `ldd` dependency marked `not found`;
- no ELF file requires a GLIBC symbol newer than `GLIBC_2.31`;
- no `libvlc.so*`, `libvlccore.so*`, or VLC plugin directory is bundled;
- system VLC provides the plain X11 `libxcb_x11_plugin.so` video-output module used to embed video consistently on Xorg and XWayland;
- bundled Qt contains `libqxcb.so` and its dependencies resolve;
- the PyInstaller output contains the Python 3.12 runtime, the narrow `libffi.so.7` compatibility runtime, and application icon;
- the OpenSSL 3 `libcrypto`/`libssl` runtime and its license are bundled, and Qt reports working TLS support;
- `BUILD_INFO.txt` contains the required version/build metadata;
- the packaged `--smoke-test` initializes Qt, loads system libVLC, and creates a libVLC Instance plus MediaPlayer.

Useful manual diagnostics inside an Ubuntu 20.04 environment:

```bash
file dist/video-event-logger/video-event-logger
ldd dist/video-event-logger/video-event-logger
objdump -T dist/video-event-logger/video-event-logger | grep GLIBC_
find dist/video-event-logger -name libqxcb.so -exec ldd {} \;
```

## Install the release

On an Ubuntu 20.04 x86_64 target:

```bash
tar -xzf video-event-logger-v<version>-ubuntu20.04-amd64.tar.gz
cd video-event-logger-v<version>-ubuntu20.04-amd64
bash install.sh
```

If runtime packages are missing, `install.sh` asks for administrator access and runs:

```bash
sudo apt update
sudo apt install vlc vlc-plugin-base file libxcb-cursor0 libgtk-3-0
```

The application itself is installed without `sudo` at `~/.local/opt/video-event-logger`. The installer creates a desktop entry under `${XDG_DATA_HOME:-$HOME/.local/share}/applications` and places `uninstall.sh` plus the optional Ubuntu 20.04 Intel `fix.sh` inside the installed application directory.

The optional fix is deliberately separate from normal installation. On affected Intel Gen12 machines it builds a checksum-pinned libva 2.20/gmmlib 22.3.14/media-driver 24.1.0 stack under `~/.local/opt/video-event-logger-vaapi`; the launcher activates that stack only when `${XDG_CONFIG_HOME:-$HOME/.config}/video-event-logger/vaapi-runtime` exists and points to a complete private runtime. No system graphics library, VLC package, or PPA is changed. See `release_README.md` for the end-user commands.

Dependency validation is based on the actual `vlc` executable, `libvlc.so.5`, `ldd` results, and the packaged smoke test—not an exact Debian package-name match. This avoids false failures on systems where a compatible library is provided by a renamed package such as `libgtk-3-0t64`. The installer prints every detected VLC path before continuing.

Dependency readiness also includes `ldd` validation of bundled `libqxcb.so`. Missing Qt libraries therefore trigger package installation even when VLC is already present. A missing `libxcb-cursor.so.0` receives a targeted `libxcb-cursor0` reinstall attempt followed by `ldconfig`; diagnostics print every still-unresolved Qt library.

The package includes Ubuntu 20.04's `libffi.so.7` only because the bundled Python `_ctypes` module requires that ABI and newer Ubuntu releases may provide only `libffi.so.8`. This is a targeted compatibility exception; glibc, libVLC, and VLC plugins remain system-provided and are not bundled. Ubuntu 20.04 x86_64 remains the only officially supported target.

## Manual start and smoke test

```bash
~/.local/opt/video-event-logger/video-event-logger-launcher
~/.local/opt/video-event-logger/video-event-logger-launcher --smoke-test
```

The smoke test does not need a video, audio device, network, or user interaction. It verifies that Qt can load its HTTPS/TLS backend locally; it does not contact an external server.

## Logs and Qt diagnostics

Release logs are appended to:

```text
${XDG_STATE_HOME:-$HOME/.local/state}/video-event-logger/application.log
```

Enable Qt plugin diagnostics for one launch without editing the launcher:

```bash
QT_DEBUG_PLUGINS=1 ~/.local/opt/video-event-logger/video-event-logger-launcher
```

The diagnostic output is written to the same application log in release mode.

The supported entry point is `video-event-logger-launcher`, not the inner PyInstaller executable. The launcher discovers the installed `libvlc.so.5`, sets `PYTHON_VLC_LIB_PATH`, optionally sets a detected `VLC_PLUGIN_PATH`, activates a valid app-specific VA-API runtime marker when present, and uses Qt's `xcb` platform so libVLC can embed video consistently on both Xorg and Wayland-based Ubuntu sessions.

## Uninstall

```bash
bash ~/.local/opt/video-event-logger/uninstall.sh
```

The uninstaller removes the installed application, desktop entry, and XDG state log. It deliberately preserves annotation JSON files under `~/VideoEventLogger`.

## Mandatory manual release checks

Automated validation is not a substitute for a graphical target-system test. Before distribution, extract and install the archive in a clean Ubuntu 20.04 x86_64 VM, start it from both the terminal and application menu, run `--smoke-test`, open an H.264 MP4, test playback/seek/pause, reinstall the same archive, and verify the persistent log and desktop icon.

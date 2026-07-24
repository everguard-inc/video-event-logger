# Video Event Logger for Ubuntu x86_64

This package uses Ubuntu 20.04 as its minimum build/runtime baseline and runs Qt through X11/XWayland for embedded libVLC playback, including on Wayland-based Ubuntu 24.04 sessions. It contains a self-contained Python application runtime and the OpenSSL 3 libraries required by Qt for HTTPS annotation uploads. Python does not need to be installed on the target machine. VLC remains a required system dependency and is not bundled.

## Install

Run the installer as your normal desktop user:

```bash
bash install.sh
```

When required packages are missing, `install.sh` runs:

```bash
sudo apt update
sudo apt install vlc vlc-plugin-base file libxcb-cursor0 libgtk-3-0
```

The system-package step may ask for the user's password. The application itself is still installed without `sudo` in the current user's home directory.

The installer discovers the actual system `libvlc.so.5` path, checks its shared-library dependencies, and runs the packaged application smoke test before copying application files. VLC's plugin directory is used when detected; otherwise libVLC uses its compiled-in system default.

The installer adds the application for the current user under:

```text
~/.local/opt/video-event-logger
```

## Start manually

```bash
~/.local/opt/video-event-logger/video-event-logger-launcher
```

## Smoke test

```bash
~/.local/opt/video-event-logger/video-event-logger-launcher --smoke-test
```

## Logs

Release builds append stdout and stderr to:

```text
${XDG_STATE_HOME:-$HOME/.local/state}/video-event-logger/application.log
```

For Qt plugin diagnostics:

```bash
QT_DEBUG_PLUGINS=1 ~/.local/opt/video-event-logger/video-event-logger-launcher
```

Then inspect `application.log` in the directory above.

If installation fails, read the printed runtime diagnostics. They report the detected `vlc` command, libVLC path, and plugin directory. On Ubuntu releases where GTK uses a `t64` package name, the installer selects `libgtk-3-0t64` automatically when appropriate.

The same diagnostics list unresolved Qt xcb libraries. If an older package database says `libxcb-cursor0` is installed but `libxcb-cursor.so.0` is physically missing, the installer automatically attempts:

```bash
sudo apt install --reinstall libxcb-cursor0
sudo ldconfig
```

Do not use the inner `video-event-logger/video-event-logger` executable as the normal entry point. After installation, use the launcher shown above because it configures the detected system libVLC path and preserves startup errors in the log.

## Optional Ubuntu 20.04 Intel green-band fix

Ubuntu 20.04 ships an old Intel media driver that can corrupt the upper part of an H.264 frame on some Intel Gen12 (Tiger Lake/Rocket Lake/Alder Lake) systems. The package includes an optional app-specific workaround. Do not run it on machines where video is already correct.

First collect read-only diagnostics:

```bash
bash ~/.local/opt/video-event-logger/fix.sh diagnose
```

To install the workaround, close Video Event Logger and run the script as the normal desktop user, without `sudo`:

```bash
bash ~/.local/opt/video-event-logger/fix.sh install
```

The script asks for administrator access only to install compiler/header packages. It downloads checksum-pinned official Intel sources and builds libva 2.20, gmmlib 22.3.14, and Intel media-driver 24.1.0 under `~/.local/opt/video-event-logger-vaapi`. It does not replace files under `/usr`, add a PPA, or change VLC/VA-API behavior for other applications. Allow about 2 GB of temporary free space; the build can take several minutes.

Check or fully roll back the app-specific runtime with:

```bash
bash ~/.local/opt/video-event-logger/fix.sh status
bash ~/.local/opt/video-event-logger/fix.sh uninstall
```

`uninstall` removes the private runtime and activation marker, but leaves the compiler/header packages installed. Restart Video Event Logger after installing or removing the workaround.

## Uninstall

```bash
bash ~/.local/opt/video-event-logger/uninstall.sh
```

This removes the application, desktop entry, and application log. Annotation JSON files under `~/VideoEventLogger` are preserved.

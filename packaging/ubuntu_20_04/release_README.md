# Video Event Logger for Ubuntu 20.04 x86_64

This package contains a self-contained Python application runtime. Python does not need to be installed on the target machine. VLC remains a required system dependency and is not bundled.

## Install

Run the installer as your normal desktop user:

```bash
bash install.sh
```

When required packages are missing, `install.sh` runs:

```bash
sudo apt update
sudo apt install vlc file libxcb-cursor0 libgtk-3-0
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

## Uninstall

```bash
bash ~/.local/opt/video-event-logger/uninstall.sh
```

This removes the application, desktop entry, and application log. Annotation JSON files under `~/VideoEventLogger` are preserved.

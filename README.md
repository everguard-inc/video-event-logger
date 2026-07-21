# Video Event Logger

Video Event Logger is a local desktop application for reviewing video files, logging event intervals, and exporting JSON annotations. The current application version is `0.2.0` and the annotation schema version is `1.0`.

The application is built with PySide6 and uses VLC/libVLC through `python-vlc`. It currently accepts `.mp4` and `.mkv` files.

## Current capabilities

- Play, pause, scrub, and seek by 1 or 10 seconds.
- Change playback speed to x1, x2, x4, or x8. Resuming after a pause resets the speed to x1.
- Step approximately one frame backward or forward using VLC's reported FPS, with a 30 FPS fallback.
- Rotate the preview clockwise in 90-degree increments while playback is paused. Rotation changes only the preview and is not persisted.
- Log interval start/end timestamps with buttons or keyboard shortcuts.
- Show a persistent highlighted `INTERVAL ACTIVE` indicator with the exact Start timestamp until the interval is completed or cancelled.
- Automatically use the exact video duration as End when an active interval reaches the end of the video.
- Apply an `event_type` to new intervals and optionally confirm or change it in a popup that also accepts a comment.
- Play, edit, delete, and jump to saved intervals; show per-event counts.
- Keep both the shareable result JSON and the recovery autosave current after interval creation, editing, or deletion; update current state again when the application closes.
- Show separate `result JSON` and `autosave` status indicators, including partial-save failures.
- Continue existing work, start over, delete a project, and optionally resume the last playback position.
- Export final annotations without storing the full source-video path.
- Save JSON atomically so a failed write keeps the previous file intact and does not follow a destination symlink/hardlink into the source video.

## Run from source

Python 3.12 is the supported development runtime.

```bash
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python -m video_event_logger
```

VLC must also be installed on the system.

Ubuntu:

```bash
sudo apt update
sudo apt install vlc libvlc5 vlc-plugin-base
```

macOS:

```bash
brew install --cask vlc
```

Windows playback support exists in the `VideoPlayer` adapter, but there is currently no documented or tested Windows packaging flow.

## Annotation workflow

1. Select `Open Video` and choose an `.mp4` or `.mkv` file.
2. Set the `event_type` for new intervals. An empty value becomes `undefined`; the UI limits the value to 25 characters.
3. Press `A` or `Start` at the beginning of an event. The Start button and End button are highlighted, and the active indicator shows the exact timestamp. Pressing Start again replaces that timestamp.
4. Press `D` or `End` at the end of an event.
5. If `Show popup after each interval` is enabled, confirm the event type and optional comment. Cancelling the popup discards the pending interval.
6. Review intervals in the table. `Play` stops automatically at the interval end, `Edit` changes the event type/comment, and double-clicking a row jumps to its start.
7. After every completed, edited, or deleted interval, the application immediately updates both JSON files. The file in `results/` is therefore ready to copy while the application remains open.
8. Before delivery, optionally select `Validate & Save JSON Now` to validate the full document and explicitly rewrite both files. This is a verification/checkpoint action, not a prerequisite for current interval data to reach the result JSON.

### Keyboard shortcuts

| Key | Action |
| --- | --- |
| `Space` | Play or pause |
| `A` | Set interval start |
| `D` | Set interval end |
| `Esc` | Cancel a pending interval |
| `Delete` | Delete the selected interval |
| `Left` / `Right` | Seek backward/forward 1 second |
| `Shift+Left` / `Shift+Right` | Seek backward/forward 10 seconds |
| `,` / `.` | Step approximately one frame backward/forward |
| `1`, `2`, `4`, `8` | Set playback speed |

Playback shortcuts are ignored while a line-edit control has focus.

## Stored data

Application data is stored under the current user's home directory:

```text
~/VideoEventLogger/autosave/<video-stem>.autosave.json
~/VideoEventLogger/results/<video-stem>.annotations.json
```

Builds from before the rename stored data under the legacy `~/VideoEventMarker` directory. The new application does not delete or move that directory. If existing work must be retained, copy its `autosave/` and `results/` contents into `~/VideoEventLogger/` before opening those projects in the renamed build.

The two files have different roles:

- `results/<video-stem>.annotations.json` is the shareable result. It is updated immediately after every completed, edited, or deleted interval, so it can be copied without closing the application or pressing an extra save button.
- `autosave/<video-stem>.autosave.json` is the recovery copy used when continuing work. It is updated independently from the result file.

Both writes use a temporary file in the destination directory, flush it to disk, and atomically replace the JSON destination. If one write fails, the other is still attempted; the two labelled status lamps show which file is current or failed. A failed write leaves that file's previous valid version intact and removes the temporary file.

Projects are currently identified only by the video filename stem. Videos with the same stem in different directories, or files such as `sample.mp4` and `sample.mkv`, therefore share annotation paths. Avoid those collisions until project identity is made unique.

The JSON document contains:

- schema, application, autosave/final, and creation metadata;
- `video_name`, but no full `video_path`;
- current event type and last playback position;
- video metadata;
- intervals with seconds, formatted timestamps, event type, and comment.

Only video duration is currently populated at runtime. `fps`, `frame_count`, and `resolution` remain `null`; interval `start_frame`/`end_frame` remain `null` and `frame_source` is `unavailable`. Frame controls affect playback but do not add frame numbers to exported annotations.

## Tests and local verification

Run the unit test suite:

```bash
python -m unittest discover -s tests -v
```

Run a Python syntax/import compilation check:

```bash
python -m compileall -q video_event_logger tests packaging/macos/create_icns.py
```

The current 31-test suite covers annotation/project services, atomic persistence (including symlink/hardlink regression cases), live result/recovery checkpoints and partial failures, resumed-work synchronization, end-of-video interval completion, and UI feedback state. Real VLC video output and packaged binaries still require the manual release smoke test.

Before distributing any build, complete [RELEASE_SMOKE_CHECKLIST.md](RELEASE_SMOKE_CHECKLIST.md). The code-quality review and prioritized follow-up work are recorded in [CODE_QUALITY_AUDIT.md](CODE_QUALITY_AUDIT.md).

## Package for Ubuntu 20.04

PyInstaller does not cross-build a Linux application from macOS. The supported release flow always builds inside an `ubuntu:20.04` Docker image for `linux/amd64`; do not run PyInstaller directly on the host for an Ubuntu release.

### Docker release build

Install Docker with the Buildx plugin (Docker Desktop includes it), then run from the repository root:

```bash
bash packaging/ubuntu_20_04/build_release.sh
```

The build uses Ubuntu 20.04, Python 3.12.4, pinned Python dependencies, and `linux/amd64`. Python is compiled inside the image with a shared `libpython3.12`. The first build can take several minutes, especially under x86-64 emulation on Apple Silicon.

For a diagnostic build that keeps a console and PyInstaller debug output:

```bash
BUILD_MODE=debug bash packaging/ubuntu_20_04/build_release.sh
```

The expected output is:

```text
release/video-event-logger-v0.2.0-ubuntu20.04-amd64.tar.gz
```

Before the archive is created, the container automatically checks the ELF architecture, every bundled ELF dependency with `ldd`, the maximum required GLIBC version (`2.31`), the Qt `xcb` platform plugin, libVLC availability, required resources, `BUILD_INFO`, and the packaged `--smoke-test`, including creation of a libVLC Instance and MediaPlayer. Public `BUILD_INFO` contains only application/build/runtime versions and the resolved Python dependency list; it does not expose Git metadata. Archive creation is aborted on any failure. Detailed build, validation, and troubleshooting instructions are in [packaging/ubuntu_20_04/README.md](packaging/ubuntu_20_04/README.md).

### Install the Ubuntu release

On the target Ubuntu 20.04 machine:

```bash
tar -xzf video-event-logger-v0.2.0-ubuntu20.04-amd64.tar.gz
cd video-event-logger-v0.2.0-ubuntu20.04-amd64
bash install.sh
```

When dependencies are missing, `install.sh` requests administrator access and executes:

```bash
sudo apt update
sudo apt install vlc file libxcb-cursor0 libgtk-3-0
```

The application itself is installed without `sudo` under `~/.local/opt/video-event-logger`, and an application-menu entry named `Video Event Logger` is created. It is safe to run the installer again to update an existing installation. To verify an installed build without opening the full UI, run:

```bash
~/.local/opt/video-event-logger/video-event-logger-launcher --smoke-test
```

Release-mode launcher output is written to `~/.local/state/video-event-logger/application.log` (or the equivalent path below `$XDG_STATE_HOME`). The launcher does not modify global `LD_LIBRARY_PATH`; it only points `python-vlc` at the system libVLC installation.

`install.sh` validates the actual system libVLC file and runs the packaged smoke test before installing. It does not require an exact `dpkg` package-name match, so compatible renamed packages do not cause a false `required Ubuntu packages are unavailable` error. Use the installed launcher or application-menu entry for normal startup, not the inner PyInstaller executable.

The installer also checks the actual `ldd` result for Qt's `libqxcb.so`. If `libxcb-cursor.so.0` is missing despite package-manager state, it attempts `sudo apt install --reinstall libxcb-cursor0` and runs `sudo ldconfig` before validating again.

The release bundles the specific `libffi.so.7` runtime required by Python 3.12's `_ctypes` extension. This prevents `python-vlc could not be imported` on newer Ubuntu systems that have only `libffi.so.8`; system VLC and glibc are still not bundled.

To uninstall the application:

```bash
bash ~/.local/opt/video-event-logger/uninstall.sh
```

The uninstaller removes the application, desktop entry, and application log. Annotation JSON files in `~/VideoEventLogger` are intentionally preserved.

## Package for macOS

Build on macOS for the same CPU architecture as the target machine. Separate Apple Silicon and Intel builds are required if both architectures must be supported.

```bash
brew install --cask vlc
PYTHON_BIN=python3.12 bash packaging/macos/build.sh
bash packaging/macos/create_release_archive.sh
```

Outputs:

```text
dist/Video Event Logger.app
release/video-event-logger-v0.2.0-macos.zip
```

The target Mac also needs VLC installed. The current MVP is unsigned and not notarized, so the first launch may require right-clicking `Video Event Logger.app` and selecting `Open`.

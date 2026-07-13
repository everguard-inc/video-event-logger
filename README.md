# Video Event Logger

Video Event Logger is a local desktop application for reviewing video files, logging event intervals, and exporting JSON annotations. The current application version is `0.2.0` and the annotation schema version is `1.0`.

The application is built with PySide6 and uses VLC/libVLC through `python-vlc`. It currently accepts `.mp4` and `.mkv` files.

## Current capabilities

- Play, pause, scrub, and seek by 1 or 10 seconds.
- Change playback speed to x1, x2, x4, or x8. Resuming after a pause resets the speed to x1.
- Step approximately one frame backward or forward using VLC's reported FPS, with a 30 FPS fallback.
- Rotate the preview clockwise in 90-degree increments while playback is paused. Rotation changes only the preview and is not persisted.
- Log interval start/end timestamps with buttons or keyboard shortcuts.
- Apply an `event_type` to new intervals and optionally confirm or change it in a popup that also accepts a comment.
- Play, edit, delete, and jump to saved intervals; show per-event counts.
- Autosave after interval creation, editing, or deletion and when the application closes.
- Continue existing work, start over, delete a project, and optionally resume the last playback position.
- Export final annotations without storing the full source-video path.

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
3. Press `A` or `Start` at the beginning of an event.
4. Press `D` or `End` at the end of an event.
5. If `Show popup after each interval` is enabled, confirm the event type and optional comment. Cancelling the popup discards the pending interval.
6. Review intervals in the table. `Play` stops automatically at the interval end, `Edit` changes the event type/comment, and double-clicking a row jumps to its start.
7. Select `Finish & Save JSON` to create the final annotation file.

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

The current suite covers the core annotation and project services. Playback, Qt controller flows, persistence edge cases, and packaged binaries still require the manual release smoke test.

Before distributing any build, complete [RELEASE_SMOKE_CHECKLIST.md](RELEASE_SMOKE_CHECKLIST.md). The code-quality review and prioritized follow-up work are recorded in [CODE_QUALITY_AUDIT.md](CODE_QUALITY_AUDIT.md).

## Package for Ubuntu 20.04

PyInstaller does not cross-build a Linux application from macOS. Use the Docker flow or build natively on Ubuntu 20.04.

### Docker build from macOS

Install Docker Desktop, then run:

```bash
bash packaging/ubuntu_20_04/build_in_docker.sh
```

The default build uses Ubuntu 20.04, Python 3.12, and `linux/amd64`. Python 3.12 is compiled from the official Python source archive inside the image. The first build can take several minutes, especially under CPU emulation on Apple Silicon.

The expected output is:

```text
release/video-event-logger-v0.2.0-ubuntu20.04.tar.gz
```

Do not trust an artifact based only on its filename. Before release, verify that its executable is an x86-64 Linux `ELF` binary and that the archive contains no macOS `.dylib` files. The exact commands are in the release smoke checklist.

### Native Ubuntu build

Install the system dependencies and make Python 3.12 available, then run:

```bash
PYTHON_BIN=python3.12 bash packaging/ubuntu_20_04/build.sh
bash packaging/ubuntu_20_04/create_release_archive.sh
```

The unpackaged executable is located at:

```text
dist/video-event-logger/video-event-logger
```

To install that local build for the current user without creating an archive:

```bash
bash packaging/ubuntu_20_04/install_user_shortcut.sh
```

### Install the Ubuntu release

On the target Ubuntu 20.04 machine:

```bash
sudo apt update
sudo apt install vlc libvlc5 vlc-plugin-base
tar -xzf video-event-logger-v0.2.0-ubuntu20.04.tar.gz
cd video-event-logger-v0.2.0-ubuntu20.04
bash install.sh
```

The per-user installer places the application under `~/.local/opt/video-event-logger` and creates an application-menu entry named `Video Event Logger`.

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

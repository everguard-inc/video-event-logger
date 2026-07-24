# Video Event Logger

Video Event Logger is a local desktop application for reviewing video files, logging event intervals, and exporting JSON annotations. The current application version is `0.3.5` and the annotation schema version is `1.0`.

The application is built with PySide6 and uses VLC/libVLC through `python-vlc`. It currently accepts `.mp4` and `.mkv` files.

## Current capabilities

- Play, pause, scrub, and seek by 1 or 10 seconds.
- Change playback speed to x1, x2, x4, or x8. The active Play/Pause and speed buttons are highlighted; resuming after a pause resets the speed to x1.
- Show only the video in full screen from `View` → `Video Full Screen`, with `F11`, or by double-clicking the video. A compact HUD provides an interactive seek slider, current/duration time, playback state, speed, interval feedback, and save/error messages. The controls hide after 3 seconds of inactivity and return on mouse or playback/seek activity; hover and slider drag keep them visible. `Esc` only leaves video full screen; `Q` cancels a pending interval in either view.
- Switch between bright and dark appearance from `View` → `View mode` → `Bright/Dark`. The selected theme is retained between application launches.
- Step approximately one frame backward or forward using VLC's reported FPS, with a 30 FPS fallback.
- Select preview rotation at 0°, 90°, 180°, or 270° from the `View` menu while playback is paused. Rotation changes only the preview and is not persisted.
- Log interval start/end timestamps with buttons or keyboard shortcuts.
- Show a persistent highlighted `INTERVAL ACTIVE` indicator with the exact Start timestamp until the interval is completed or cancelled. Pressing Start/`A` again is ignored and never replaces that timestamp.
- Automatically use the exact video duration as End when an active interval reaches the end of the video.
- Apply an `event_type` to new intervals and optionally confirm or change it in a popup that also accepts a comment. The popup is controlled from `View` → `Show Interval Details Popup`, and the choice is retained between launches.
- Play, edit, delete, and jump to saved intervals; show per-event counts.
- Create the shareable annotation JSON immediately after a video is opened, even when it contains no intervals, and keep it current after every relevant change.
- Configure a persistent endpoint and local access token under `Connection` → `Settings…`, then upload the current JSON from `File` → `Upload Annotations…` with an asynchronous modal progress dialog. Successful, failed, cancelled, and duplicate (`409 Conflict`) uploads receive distinct feedback.
- Keep the previous valid annotation document as a hidden `.bak` recovery file.
- Show one global `Unsaved changes`, `Saving…`, `✓ Saved`, or persistent failure state in the status bar.
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

1. Select `File` → `Open Video…` (`Ctrl/Cmd+O`) and choose an `.mp4` or `.mkv` file. An empty annotation JSON is created immediately.
2. Set the `event_type` for new intervals. An empty value becomes `undefined`; the UI limits the value to 25 characters.
3. Press `A` or `Start` at the beginning of an event. The Start button and End button are highlighted, and the active indicator shows the exact timestamp. Pressing Start again is ignored until the interval is finished or cancelled.
4. Press `D` or `End` at the end of an event.
5. If `View` → `Show Interval Details Popup` is enabled, confirm the event type and optional comment. Cancelling the popup discards the pending interval.
6. Review intervals in the table. `Play` stops automatically at the interval end, `Edit` changes the event type/comment, and double-clicking a row jumps to its start.
7. After every completed, edited, or deleted interval, the application atomically updates the annotation JSON and keeps its previous valid version as `.bak`.
8. Before delivery, optionally select `File` → `Validate & Save Annotations` (`Ctrl/Cmd+S`) to validate and retry the save. Use `File` → `Show Annotation File in Folder` to locate the deliverable file.
9. To deliver through the API, configure the endpoint and token once under `Connection` → `Settings…`, then select `File` → `Upload Annotations…`.

### Keyboard shortcuts

| Key | Action |
| --- | --- |
| `Space` | Play or pause |
| `F11` | Enter or leave video-only full-screen mode |
| `A` | Set interval start |
| `D` | Set interval end |
| `Q` | Cancel a pending interval |
| `Esc` | Leave video full screen |
| `Delete` | Delete the selected interval |
| `Left` / `Right` | Seek backward/forward 1 second |
| `Shift+Left` / `Shift+Right` | Seek backward/forward 10 seconds |
| `,` / `.` | Step approximately one frame backward/forward |
| `1`, `2`, `4`, `8` | Set playback speed |

Playback shortcuts are ignored while a line-edit control has focus.

## Stored data

Application data is stored under the current user's home directory:

```text
~/VideoEventLogger/results/<video-stem>.annotations.json
~/VideoEventLogger/results/<video-stem>.annotations.json.bak
```

The `.annotations.json` file is the only current, shareable document. It is created as soon as a video opens successfully, including for a valid empty annotation result with `intervals: []`. The `.bak` file contains the previous valid JSON and appears starting with the second successful save. It is for automatic recovery and does not appear as a separate status in the UI.

Builds from before this storage change may have `~/VideoEventLogger/autosave/<video-stem>.autosave.json`. The application can load that legacy recovery file; after the canonical annotation JSON is saved successfully, the obsolete autosave is removed. Builds from before the application rename stored data under `~/VideoEventMarker`; that directory is not moved automatically.

Each save first copies the previous valid annotation document to `.bak`, then writes a temporary JSON in the results directory, flushes it to disk, and atomically replaces the canonical destination. A failed write leaves the previous valid JSON intact. The status bar shows unsaved `event_type` edits, saving, success, or failure; failures remain visible and can be retried with `Ctrl/Cmd+S`.

Projects are currently identified only by the video filename stem. Videos with the same stem in different directories, or files such as `sample.mp4` and `sample.mkv`, therefore share annotation paths. Avoid those collisions until project identity is made unique.

The JSON document contains:

- schema, application, compatibility, and creation metadata;
- `video_name`, but no full `video_path`;
- current event type and last playback position;
- video metadata;
- intervals with seconds, formatted timestamps, event type, and comment.

Only video duration is currently populated at runtime. `fps`, `frame_count`, and `resolution` remain `null`; interval `start_frame`/`end_frame` remain `null` and `frame_source` is `unavailable`. Frame controls affect playback but do not add frame numbers to exported annotations.

## Annotation upload API

The upload command sends `POST` to the exact configured endpoint URL with these headers:

```text
Authorization: TokenAuth <token>
Content-Type: application/json
Accept: application/json
```

The request body is the complete current `.annotations.json` document, without a wrapper object. Before sending, the application applies the current `event_type`, validates the document, saves it atomically, and rejects files containing more than 2,000 intervals. The request has a 30-second timeout and can be cancelled from its modal progress dialog.

Endpoint URL and token are stored in the platform's local `QSettings` store and reused between launches. The connection dialog provides a wide URL field supporting up to 2,048 characters and an eye control for showing or hiding the token. This intentionally simple storage is not encrypted; the token is never written into the annotation JSON. Use HTTPS for non-local endpoints.

Any HTTP `2xx` response is treated as success. The server should return `409 Conflict` for a duplicate submission, preferably with a JSON response such as `{"detail": "Annotation already uploaded"}`. A practical duplicate fingerprint is the authenticated user plus `video_name` plus a canonical representation of the intervals; volatile runtime fields such as `last_playback_position_seconds` should be ignored so a retry is rejected while genuinely changed annotations can still be accepted. Other JSON error responses may use `detail`, `message`, or `error`; the application displays that text to the user. Generic HTML error pages are hidden and replaced with concise status-specific guidance, including an endpoint URL hint for `404`.

## Tests and local verification

Run the unit test suite:

```bash
python -m unittest discover -s tests -v
```

Run a Python syntax/import compilation check:

```bash
python -m compileall -q video_event_logger tests packaging/macos/create_icns.py
```

The current 80-test suite covers annotation/project services, immediate empty-file creation, atomic persistence and `.bak` recovery (including symlink/hardlink regression cases), safe legacy autosave migration, save/unsaved states and failures, resumed-work synchronization, end-of-video interval completion, playback/video-full-screen HUD/theme/rotation controls, Linux VLC output configuration, persisted appearance/popup/API preferences, connection settings, API request/error/duplicate behavior, menu availability, and UI feedback state. Real VLC video output, live HTTP behavior, and packaged binaries still require the manual release smoke test.

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
release/video-event-logger-v0.3.5-ubuntu20.04-amd64.tar.gz
```

Before the archive is created, the container automatically checks the ELF architecture, every bundled ELF dependency with `ldd`, the maximum required GLIBC version (`2.31`), the Qt `xcb` platform plugin, libVLC availability, required resources, `BUILD_INFO`, and the packaged `--smoke-test`, including creation of a libVLC Instance and MediaPlayer. Public `BUILD_INFO` contains only application/build/runtime versions and the resolved Python dependency list; it does not expose Git metadata. Archive creation is aborted on any failure. Detailed build, validation, and troubleshooting instructions are in [packaging/ubuntu_20_04/README.md](packaging/ubuntu_20_04/README.md).

### Install the Ubuntu release

On the target Ubuntu x86_64 machine (Ubuntu 20.04 baseline; Ubuntu 24.04 uses XWayland compatibility for embedded video):

```bash
tar -xzf video-event-logger-v0.3.5-ubuntu20.04-amd64.tar.gz
cd video-event-logger-v0.3.5-ubuntu20.04-amd64
bash install.sh
```

When dependencies are missing, `install.sh` requests administrator access and executes:

```bash
sudo apt update
sudo apt install vlc vlc-plugin-base file libxcb-cursor0 libgtk-3-0
```

The application itself is installed without `sudo` under `~/.local/opt/video-event-logger`, and an application-menu entry named `Video Event Logger` is created. It is safe to run the installer again to update an existing installation. To verify an installed build without opening the full UI, run:

```bash
~/.local/opt/video-event-logger/video-event-logger-launcher --smoke-test
```

Release-mode launcher output is written to `~/.local/state/video-event-logger/application.log` (or the equivalent path below `$XDG_STATE_HOME`). By default the launcher only points `python-vlc` at the system libVLC installation. If the optional Ubuntu 20.04 Intel fix is explicitly installed, it prepends that private runtime to `LD_LIBRARY_PATH` for the Video Event Logger process only; the desktop session and other applications are unaffected.

`install.sh` validates the actual system libVLC file and runs the packaged smoke test before installing. It does not require an exact `dpkg` package-name match, so compatible renamed packages do not cause a false `required Ubuntu packages are unavailable` error. Use the installed launcher or application-menu entry for normal startup, not the inner PyInstaller executable.

The installer also checks the actual `ldd` result for Qt's `libqxcb.so`. If `libxcb-cursor.so.0` is missing despite package-manager state, it attempts `sudo apt install --reinstall libxcb-cursor0` and runs `sudo ldconfig` before validating again.

The release bundles the specific `libffi.so.7` runtime required by Python 3.12's `_ctypes` extension. It also bundles OpenSSL 3 narrowly for Qt HTTPS uploads because Ubuntu 20.04 provides only OpenSSL 1.1. The release smoke-test verifies that Qt can initialize this TLS backend without making an external request. System VLC and glibc are still not bundled.

On an affected Ubuntu 20.04 Intel Gen12 machine, an optional machine-local compatibility runtime can be diagnosed, installed, checked, or removed independently of normal installation:

```bash
bash ~/.local/opt/video-event-logger/fix.sh diagnose
bash ~/.local/opt/video-event-logger/fix.sh install
bash ~/.local/opt/video-event-logger/fix.sh status
bash ~/.local/opt/video-event-logger/fix.sh uninstall
```

Run `fix.sh` as the normal desktop user. It builds checksum-pinned official Intel libva 2.20/gmmlib 22.3.14/media-driver 24.1.0 sources below the user's home directory and never replaces system graphics libraries or VLC. This workaround is intended only for the green/corrupted upper video band on Ubuntu 20.04; do not enable it where playback is already correct.

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
release/video-event-logger-v0.3.5-macos.zip
```

The target Mac also needs VLC installed. The current MVP is unsigned and not notarized, so the first launch may require right-clicking `Video Event Logger.app` and selecting `Open`.

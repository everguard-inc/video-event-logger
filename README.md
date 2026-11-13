# Video Event Logger

Video Event Logger is a local desktop application for reviewing video files, logging event intervals, and exporting JSON annotations. The current application version is `0.3.10` and the annotation schema version is `1.0`.

The application is built with PySide6 and uses VLC/libVLC through `python-vlc`. It currently accepts `.mp4` and `.mkv` files.

Planned improvements are tracked in [BACKLOG.md](BACKLOG.md).

## Current capabilities

- Play, pause, scrub, and seek by 1 or 10 seconds.
- Change playback speed to x1, x2, x4, or x8. The active Play/Pause and speed buttons are highlighted; pausing and resuming preserve the selected speed. Press `1` or click x1 to return to normal speed.
- Show only the video in full screen from `View` → `Full Screen mode` → `Enable Full Screen`, with `F11`, or by double-clicking the video. The video fills the screen; a floating HUD offers Play/Pause, `-10s` / `-1s` / frame / `+1s` / `+10s`, speed, the current event type, Start/End/Cancel, an `Events` toggle, and a seek track that marks every interval and the interval being recorded. While an interval is recorded, a red `REC` pill shows its type, start and length and is never replaced by notifications. By default, the controls hide after 3 seconds without real pointer movement and return on mouse or playback/seek activity; hover, slider or edge drags and open menus keep them visible. Enable `View` → `Full Screen mode` → `Keep Controls Visible` to keep the bar visible; this preference is retained between launches. `Esc` only leaves video full screen; `Q` cancels a pending interval in either view.
- Switch between dark (default) and bright appearance from `View` → `Appearance` → `Dark/Bright`. The selected theme is retained between application launches.
- Step approximately one frame backward or forward using VLC's reported FPS, with a 30 FPS fallback.
- Select preview rotation at 0°, 90°, 180°, or 270° from the `View` menu while playback is paused. Rotation changes only the preview and is not persisted.
- Log interval start/end timestamps with buttons or keyboard shortcuts.
- Show a persistent highlighted `INTERVAL ACTIVE` indicator with the exact Start timestamp until the interval is completed or cancelled. Pressing Start/`A` again is ignored and never replaces that timestamp.
- Automatically use the exact video duration as End when an active interval reaches the end of the video.
- Apply an `event_type` to new intervals and optionally confirm or change it in a popup that also accepts a comment. The popup is controlled from `View` → `Show Interval Details Popup`, and the choice is retained between launches.
- Play, edit, delete, and jump to saved intervals; show per-event counts. Edit Start/End precisely in seconds, or drag either edge on the interval track. Overlapping intervals use separate lanes; colors identify event types. The track fits one to four lanes without vertical scrolling; additional overlaps use a slim scrollbar. Time zoom and horizontal scrolling help trim short intervals. `View` → `Events Bar` → `Show` (or `E`) toggles the track and remembers the choice. At Fit, the track and playback slider share the same time axis. Selecting an interval opens a details panel next to the table for exact Start/End (milliseconds, ±1 frame, `⌖ Now` takes the playhead), event type and comment. Ctrl/Cmd+Z undoes interval changes in the current video; pressed right after End, it returns to recording with the same Start instead of deleting the interval.
- Event type chips next to Start/End switch the type for new intervals with one click.
- Add multiple videos or a folder (direct MP4/MKV files only) to the right-hand playlist. Double-click a video or use Previous/Next. Automatic advancement is optional and off by default.
- Select an optional annotation JSON when opening videos, or use Open Annotations for the current video. Imported intervals appear immediately and remain editable; their source file is not modified automatically.
- Create the shareable annotation JSON immediately after a video is opened, even when it contains no intervals, and keep it current after every relevant change.
- Configure a persistent endpoint and local access token under `Connection` → `Settings…` (also the `Connection…` header button), then press `Submit…` in the header, `Ctrl/Cmd+Enter`, or `File` → `Submit Annotations…`. A review step summarises intervals, marked time, work time and types, and warns about `undefined` types. A video without events is submitted as `"intervals": []` after confirming “I watched the whole video and found no events”. The result screen always shows the server's text: `201` `export_queued` / `export_pending` / `no_events` are successes, `201` `unrecognized` and `409` are shown as needing attention, `400` shows the `error` with Back to editing, `401`/`403` offer Connection settings, and `5xx` or network failures offer Retry. The playlist remembers the last result per video.
- Keep the previous valid annotation document as a hidden `.bak` recovery file.
- Show one global `Unsaved changes`, `Saving…`, `✓ Saved`, or persistent failure state in the status bar.
- Automatically restore the current video’s working annotations and playback position when returning to it. Older filename-based annotations are offered for explicit migration.
- Export final annotations without storing the full source-video path.
- Save JSON atomically so a failed write keeps the previous file intact and does not follow a destination symlink/hardlink into the source video.

## Active work time

Annotation JSON files include `active_work_seconds`, the approximate total wall-clock time spent reviewing and annotating that video. For example, `900.0` means 15 minutes of work. Playback and editing share one counter, with no per-interval breakdown or double counting; playback speed does not multiply the time.

Visible, foreground playback counts as viewing even without keyboard or mouse input. While paused, input within the player's UI keeps the counter active; after 60 seconds without input it stops until activity resumes. This estimate includes the first 60 seconds of a paused idle period. Minimized/background windows, download management, and long timer gaps such as computer sleep are excluded. No keystrokes, mouse coordinates, or input history are stored.

The counter is saved to the working JSON every 30 seconds while it changes, and checkpointed on annotation saves, export, upload, video switch, and normal exit. It continues from the saved value on reopening; a crash can lose time since the last checkpoint. Older JSON files start at zero. The counter belongs to the annotation document, not a user account: imported totals are retained, and importing annotations for the current video keeps the larger of the existing and imported totals without adding them together.

## Download video from a link

Use **File → Download Video from Link…**, paste one complete HTTPS/S3 presigned GET link per line, and choose a download folder. Videos and **ZIP, TAR, or TAR.GZ** archives are queued in order. One file downloads at a time, with 8 parallel connections by default (configurable from 1 to 16). Existing filenames are preserved: duplicate names receive a numeric suffix. Only the download directory is saved in settings; signed URLs and the queue stay in memory and are not restored after restarting.

The Downloads window is non-modal. **In background**, Escape, or × hides it while transfers and extraction continue. Keep annotating the current video; completion never switches playback, and adds the file to the Playlist only when **Add to playlist when ready** is enabled (off by default). Pasted links are previewed as video, archive (unpacked automatically) or unknown type before queueing; each download is a card with Download › Unpack › Ready steps and its own actions. Reopen Downloads from the status-bar button, File menu, or **Ctrl/Cmd+Shift+J** (including fullscreen), then choose **Open video** or **Add to playlist** for a ready file. The status bar shows progress, queued files, and the number of failures. Select a job for byte counts, speed, extraction progress, cancellation, or retry. A failed job does not block subsequent jobs; expired links need a new URL. Completed/cancelled links are discarded; failed links remain in memory only for retry.

Minimizing does not cancel downloads. Closing the application asks whether to cancel the entire queue and exit or keep working. On confirmation, pending jobs are cancelled and the window remains alive until the active worker finishes cleanup. No blocking wait runs on the GUI thread. The queue and worker belong to the main window, independently of the Downloads dialog.

Archive detection uses the downloaded contents, including when the URL has no useful extension. An archive must contain exactly one regular `.mp4` or `.mkv` file; nested folders are supported and other files are ignored. The video is unpacked with progress and cancellation, and the temporary archive is removed. Only the video is retained. ZIP CRC and TAR.GZ integrity are checked; damaged, encrypted, unsafe, empty, or ambiguous archives are rejected without replacing an existing destination. Archive paths are never used as extraction destinations.

The chosen filename is retained, with its extension adjusted to the video inside the archive when necessary (for example, `trip.mp4` becomes `trip.mkv`). An existing file at that adjusted path is never overwritten automatically. Extraction needs enough space for both the temporary archive and the unpacked video until completion.

The downloader probes with a GET range request instead of HEAD so a GET-signed URL remains usable. It downloads disjoint byte ranges, validates their offsets, lengths, and ETag, and continues interrupted ranges from the last written byte. Lost network (laptop sleep, Wi-Fi or VPN changes) is waited out: the job shows **Waiting for network**, keeps downloaded data, retries with backoff up to 30 seconds and resumes immediately after wake or **Retry now**; it stops only after 30 minutes without progress while the computer is awake, keeping the data for **Retry**. While a download or extraction runs, the application prevents idle sleep (`caffeinate` on macOS, `systemd-inhibit` on Linux); closing the lid still sleeps the computer. Servers without range support or a strong ETag use one connection. Downloads stay in a temporary file in the destination folder until complete; cancellation, unrecoverable errors and exit remove incomplete data and preserve an existing destination. Confirmed exit during a download requests cancellation first. A stalled connection can take up to 15 seconds to time out.

Use a valid HTTPS link with permission to download the object. When a link expires or is revoked mid-download, the job shows **Link expired** and keeps the downloaded data; paste a new link to the same file to continue from where it stopped (size and ETag must match). Downloads are not resumed across application restarts. Parallel connections can improve throughput when individual connections are the bottleneck; they do not bypass server or network bandwidth limits. No AWS credentials or separate aria2 installation are required.

## Recent files and fullscreen Events Bar

File → Recent keeps the latest 20 videos, folders, and annotation imports in each category across launches. Paths distinguish files with the same name. Reopening a video uses its current working annotations; reopening an annotation entry imports that JSON with its associated video. Clear History only clears this list. The playlist is not restored on startup.

View → Playlist shows the sidebar; its close button hides it and remembers that choice. If enabled, the playlist stays hidden on entering fullscreen and appears over the video at the left screen edge. Moving away hides it after a short delay; menus and dialogs keep it open. Leaving fullscreen restores the regular sidebar.

View → Events Bar → Show in Fullscreen (or `E` / the HUD `Events` button in full screen) independently enables the editable interval timeline. In full screen it floats above the HUD controls and hides with them, so the video keeps the whole screen. Right-click an interval for Play/Edit/Delete, or double-click with the left button to edit. The mouse wheel over the track zooms around the cursor; Shift + wheel pans horizontally. Drag the top grip to resize the bar vertically in either view; the height is remembered between launches. This preference is saved separately from View → Events Bar → Show for the regular window.

## Run from source

Python 3.12 is the supported development runtime.

```bash
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python -m video_event_logger
```

VLC must also be installed on the system. Software decoding uses separate libavcodec frame buffers (`--no-avcodec-dr`) to avoid reproducible H.264 buffer failures during paused seeks; decoder threading and platform hardware policies are retained. This adds a frame copy for software decoding.

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

1. Select `File` → `Open Videos…` (`Ctrl/Cmd+O`) and choose one or more `.mp4`/`.mkv` files, or choose `Open Folder…`. In the next dialog, optionally choose a JSON for the first video. Leave it empty to restore default working annotations or start empty. Every opened video has a working JSON immediately; other playlist items load when activated.
2. Set the `event_type` for new intervals. An empty value becomes `undefined`; the UI limits the value to 25 characters.
3. Press `A` or `Start` at the beginning of an event. The Start button and End button are highlighted, and the active indicator shows the exact timestamp. Pressing Start again is ignored until the interval is finished or cancelled.
4. Press `D` or `End` at the end of an event.
5. If `View` → `Show Interval Details Popup` is enabled, confirm the event type and optional comment. Cancelling the popup discards the pending interval.
6. Review intervals in the table and colored track. `Play` pauses and seeks back to the exact interval end if polling overshoots it; the red line shows the current playback position; `Edit` changes Start/End (seconds, three decimal places), event type, and comment. Drag only an edge to change a boundary; dragging the body does not move the interval. Track and table selections stay synchronized. Double-click a table row to seek or a track interval to edit it. Use the wheel to zoom at the pointer, Shift + wheel to scroll horizontally, or Zoom/Fit and scrollbars for precision. Right-click an interval for Play/Edit/Delete. Drag the top grip to adjust the bar height; Escape cancels an uncommitted interval-edge drag.
7. After every completed, edited, or deleted interval, the application atomically updates the annotation JSON and keeps its previous valid version as `.bak`.
8. Before delivery, select `File` → `Save Annotations…` (`Ctrl/Cmd+S`). Every invocation asks where to save a JSON, including beside the video or in any chosen folder. The last export folder is remembered. This creates a snapshot; use Save Annotations again after further edits. `Show Annotation File in Folder` locates the most recent export for this video in the current session, or its working JSON if there is no export.
9. To deliver through the API, configure the endpoint and token once under `Connection` → `Settings…`, then press `Submit…` (`Ctrl/Cmd+Enter`). With no events in the video, confirm “No events” in the review step.

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
| `E` | Show or hide the events bar (window or full screen) |
| `Ctrl/Cmd+Z` | Undo the last interval change; right after End, keep recording |
| `Ctrl/Cmd+Enter` | Submit annotations |

Playback shortcuts are ignored while a text or numeric input has focus. `Ctrl/Cmd+Z` undoes interval additions, edits, and deletions for the current video (up to 50 changes); directly after End it reopens that interval as the active one with the same Start. With the interval details popup enabled, `Esc` there means **Keep recording** and **Discard interval** is a separate button. Switching videos or importing annotations starts a new undo history.

## Stored data

Working annotations remain under the current user's home directory:

```text
~/VideoEventLogger/results/<video-filename>.<path-id>.annotations.json
~/VideoEventLogger/results/<video-filename>.<path-id>.annotations.json.bak
```

The filename includes the original extension and a stable hash of the resolved local video path. Same-named videos in different folders and MP4/MKV files with the same stem therefore have separate working files. Moving a video changes its working identity; use Open Annotations to attach its previous JSON. Full source paths are never included in exported JSON.

The working JSON is created when a video is opened and updated after changes. Before switching videos, the current event type, playback position, and annotations are saved. A failed save blocks switching, and a pending interval must be completed or cancelled with Q. Closing also stops if saving fails.

Save Annotations always opens a destination picker and exports a validated snapshot without changing the working autosave location. Imported files are read without modifying or renaming them, including malformed JSON. Selecting the imported file as an export destination explicitly can overwrite it through the normal Save dialog.

Each write is atomic, and the previous valid document is retained as `.bak`. A failed write keeps the existing file. The status bar reports working autosave state; the sidebar identifies an exported snapshot and reminds the user to save again after editing.

Older `results/<video-stem>.annotations.json` and `autosave/<video-stem>.autosave.json` files are offered when no path-specific working file exists. Accepting loads them into a new working file; the legacy originals are retained. Older data under `~/VideoEventMarker` is not moved automatically. Corrupted working JSON can recover from its backup; manually imported malformed files remain untouched.

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

Any HTTP `2xx` response is treated as success; its JSON `status` (`export_queued`, `export_pending`, `no_events`, `unrecognized`) and `message` are shown on the result screen. The server should return `409 Conflict` for a duplicate submission, preferably with a JSON response such as `{"detail": "Annotation already uploaded"}`. A practical duplicate fingerprint is the authenticated user plus `video_name` plus a canonical representation of the intervals; volatile runtime fields such as `last_playback_position_seconds` should be ignored so a retry is rejected while genuinely changed annotations can still be accepted. Other JSON error responses may use `detail`, `message`, or `error`; the application displays that text to the user. Generic HTML error pages are hidden and replaced with concise status-specific guidance, including an endpoint URL hint for `404`.

## Tests and local verification

Run the unit test suite:

```bash
python -m unittest discover -s tests -v
```

Run a Python syntax/import compilation check:

```bash
python -m compileall -q video_event_logger tests packaging/macos/create_icns.py
```

The automated suite covers annotation/project services, immediate empty-file creation, atomic persistence and `.bak` recovery (including symlink/hardlink regression cases), safe legacy autosave migration, save/unsaved states and failures, resumed-work synchronization, end-of-video interval completion, playback speed retention, video-full-screen HUD seek buttons and always-on controls, file-manager selection/fallback, theme/rotation controls, Linux VLC output configuration, persisted appearance/popup/API preferences, connection settings, API request/error/duplicate behavior, menu availability, and UI feedback state. Additional tests cover playlist isolation/switch failures, explicit export/cancellation, non-destructive imports, legacy migration, invalid interval bounds, undo, edge dragging, overlap lanes, folder filtering, and optional automatic advancement. Real VLC video output, live HTTP behavior, and packaged binaries still require the manual release smoke test.

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
release/video-event-logger-v0.3.10-ubuntu20.04-amd64.tar.gz
```

Before the archive is created, the container automatically checks the ELF architecture, every bundled ELF dependency with `ldd`, the maximum required GLIBC version (`2.31`), the Qt `xcb` platform plugin, libVLC availability, required resources, `BUILD_INFO`, and the packaged `--smoke-test`, including creation of a libVLC Instance and MediaPlayer. Public `BUILD_INFO` contains only application/build/runtime versions and the resolved Python dependency list; it does not expose Git metadata. Archive creation is aborted on any failure. Detailed build, validation, and troubleshooting instructions are in [packaging/ubuntu_20_04/README.md](packaging/ubuntu_20_04/README.md).

### Install the Ubuntu release

On the target Ubuntu x86_64 machine (Ubuntu 20.04 baseline; Ubuntu 24.04 uses XWayland compatibility for embedded video):

```bash
tar -xzf video-event-logger-v0.3.10-ubuntu20.04-amd64.tar.gz
cd video-event-logger-v0.3.10-ubuntu20.04-amd64
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

The release bundles the specific `libffi.so.7` runtime required by Python 3.12's `_ctypes` extension. Python is compiled against the same bundled OpenSSL 3 runtime used by Qt, so downloads and uploads do not depend on system OpenSSL 1.1. The release smoke-test exercises Python TLS and Qt TLS without making an external request. The host build also tests the actual installer and installed launcher in a separate Ubuntu 24.04 container without OpenSSL 1.1. System VLC and glibc are still not bundled.

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
release/video-event-logger-v0.3.10-macos.zip
```

The target Mac also needs VLC installed. The current MVP is unsigned and not notarized, so the first launch may require right-clicking `Video Event Logger.app` and selecting `Open`.

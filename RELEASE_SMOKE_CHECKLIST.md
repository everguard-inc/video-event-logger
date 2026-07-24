# Release Smoke Checklist

Use this checklist before sending any packaged build to a user. Record failures with screenshots/logs and do not mark the release ready while a required item is failing.

Release: `Video Event Logger v0.3.5`

Annotation schema: `1.0`

## Release record

- [ ] Commit/revision: `____________________________`
- [ ] Build date: `____________________________`
- [ ] Builder OS and CPU: `____________________________`
- [ ] Test OS and CPU: `____________________________`
- [ ] VLC version: `____________________________`
- [ ] Tester: `____________________________`

## Source preflight

- [ ] Confirm the release version comes from `video_event_logger/app_config.py` and the window title is expected to be `Video Event Logger v0.3.5`.
- [ ] Confirm no unrelated or unreviewed files are being packaged.
- [ ] Run all unit tests; expect 80 passing tests:

```bash
.venv/bin/python -m unittest discover -s tests -v
```

- [ ] Compile all Python sources successfully:

```bash
.venv/bin/python -m compileall -q video_event_logger tests packaging/macos/create_icns.py
```

- [ ] Validate the shell scripts:

```bash
for file in packaging/ubuntu_20_04/*.sh packaging/macos/*.sh; do
  bash -n "$file"
done
```

- [ ] Review [CODE_QUALITY_AUDIT.md](CODE_QUALITY_AUDIT.md), and confirm any open P0/P1 finding is accepted for this release or fixed and retested.

## Ubuntu 20.04 artifact

- [ ] Build a fresh release using the Docker flow:

```bash
bash packaging/ubuntu_20_04/build_release.sh
```

- [ ] Confirm the build completed its mandatory ELF/GLIBC/`ldd`/Qt/libVLC/resource/metadata/smoke validation and produced the expected archive:

```text
release/video-event-logger-v0.3.5-ubuntu20.04-amd64.tar.gz
```

- [ ] Confirm the archive has the expected top-level folder, application, `install.sh`, `uninstall.sh`, optional `fix.sh`, launcher, README, and `BUILD_INFO`:

```bash
tar -tzf release/video-event-logger-v0.3.5-ubuntu20.04-amd64.tar.gz | head -30
```

- [ ] Confirm the packaged executable is `ELF 64-bit ... x86-64`, not Mach-O:

```bash
tar -xOzf release/video-event-logger-v0.3.5-ubuntu20.04-amd64.tar.gz \
  video-event-logger-v0.3.5-ubuntu20.04-amd64/video-event-logger/video-event-logger | file -
```

- [ ] Confirm the archive contains no `.dylib` files; this command must print nothing:

```bash
tar -tzf release/video-event-logger-v0.3.5-ubuntu20.04-amd64.tar.gz | grep '\.dylib$'
```

- [ ] Extract and review `BUILD_INFO`; confirm app version, build mode/date, Ubuntu/Python/PyInstaller/PySide6/python-vlc versions, and dependency freeze. Confirm it contains no Git commit, branch, repository path, or tree-state information.
- [ ] Confirm the archive does not bundle `libvlc.so*`, `libvlccore.so*`, or the VLC plugin tree.
- [ ] Confirm the package contains the intentional `libffi.so.7` compatibility runtime required by Python `_ctypes`; no broader system-library tree should be bundled.
- [ ] Confirm the package contains `libcrypto.so.3`, `libssl.so.3`, and the OpenSSL license; packaged `--smoke-test` must report working Qt TLS with an OpenSSL 3 runtime.

- [ ] Extract and test the archive on a clean Ubuntu 20.04 x86-64 machine, not only in the build container.
- [ ] On a clean target without the runtime packages, run `bash install.sh` as the normal desktop user and confirm it requests administrator access for these commands:

```bash
sudo apt update
sudo apt install vlc file libxcb-cursor0 libgtk-3-0
```

- [ ] Confirm `install.sh` stops clearly without creating a partial installation if package installation is rejected or fails.
- [ ] Confirm installer diagnostics print the detected `vlc` executable, `libvlc.so.5`, and VLC plugin directory (or explicitly say the system default will be used).
- [ ] Confirm installer diagnostics report the Qt xcb plugin and list every unresolved Qt shared library; a missing `libxcb-cursor.so.0` must trigger the targeted `libxcb-cursor0` repair path.
- [ ] Confirm the pre-install packaged `--smoke-test` succeeds before application files are activated.
- [ ] Confirm the application files themselves are installed as the normal desktop user, not owned by root.
- [ ] Run the installer a second time and confirm the per-user installation updates cleanly.
- [ ] Confirm installation under `~/.local/opt/video-event-logger`.
- [ ] Confirm the application-menu launcher appears as `Video Event Logger` and starts without a terminal.
- [ ] Confirm the installed launcher, rather than the inner PyInstaller executable, is used as the desktop entry `Exec` target.
- [ ] Run `QT_QPA_PLATFORM=offscreen ~/.local/opt/video-event-logger/video-event-logger-launcher --smoke-test`; confirm Qt, the application modules, icon, and system libVLC initialize successfully.
- [ ] Confirm release-mode stdout/stderr is appended to `~/.local/state/video-event-logger/application.log` (or `$XDG_STATE_HOME/video-event-logger/application.log`).
- [ ] Confirm neither the launcher nor the application modifies global `LD_LIBRARY_PATH`.
- [ ] Run `bash ~/.local/opt/video-event-logger/uninstall.sh`; confirm the application, desktop entry, and state log are removed.
- [ ] Confirm uninstall preserves annotation JSON files under `~/VideoEventLogger`.

## macOS artifact

- [ ] Install VLC on the build machine:

```bash
brew install --cask vlc
```

- [ ] Build the `.app` bundle on the target CPU architecture:

```bash
PYTHON_BIN=python3.12 bash packaging/macos/build.sh
```

- [ ] Confirm the executable is Mach-O and reports the intended architecture (`arm64` or `x86_64`):

```bash
file "dist/Video Event Logger.app/Contents/MacOS/Video Event Logger"
```

- [ ] Create the archive:

```bash
bash packaging/macos/create_release_archive.sh
```

- [ ] Confirm `release/video-event-logger-v0.3.5-macos.zip` exists and contains `Video Event Logger.app` plus `README.txt`.
- [ ] Unzip on a clean Mac with the same architecture, move the app to `Applications`, and install VLC.
- [ ] Start the unsigned app using right-click -> `Open` if Gatekeeper requires it.

## Common launch and playback checks

Repeat this section for every release platform.

- [ ] Confirm the window title is `Video Event Logger v0.3.5` and the application icon is visible.
- [ ] Confirm playback/annotation controls are disabled before a video is loaded.
- [ ] Open an `.mp4` video.
- [ ] Open an `.mkv` video in a separate pass.
- [ ] Confirm an unsupported extension is rejected.
- [ ] Confirm the first video frame appears shortly after opening, before manual playback.
- [ ] On Ubuntu, confirm the entire video frame has normal colours with no green or translucent band along its upper edge during open, play, pause, and seek.
- [ ] On a Wayland-based Ubuntu 24.04 session, confirm video remains embedded inside Video Event Logger and no separate VLC playback window opens.
- [ ] On the affected Ubuntu 20.04 Intel Gen12 machine, run `fix.sh diagnose`, then `fix.sh install` as the normal desktop user. Confirm the log says `Using app-specific Intel VA-API runtime`, `vainfo` reports Intel media-driver 24.1.0, and the green band is absent for every known failing video.
- [ ] Confirm `fix.sh status` reports the private runtime as enabled. Run `fix.sh uninstall`, restart the app, and confirm the marker/runtime are gone, the launcher falls back to system VA-API, and no `/usr` graphics/VLC file was changed.
- [ ] Confirm the current time, duration, and timeline are updated.
- [ ] Play and pause the video with both the button and `Space`.
- [ ] Confirm Play/Pause is highlighted only while playback is active.
- [ ] Drag the timeline slowly and quickly; confirm the preview seeks without freezing or flooding VLC.
- [ ] Test `-1s`, `+1s`, `-10s`, and `+10s` buttons.
- [ ] Test `Left`, `Right`, `Shift+Left`, and `Shift+Right` shortcuts.
- [ ] Test `Frame -`/`,` and `Frame +`/`.` while paused. These are FPS-based approximate steps; confirm sensible movement and no jump outside the video range.
- [ ] Test x1, x2, x4, and x8 using both buttons and numeric shortcuts.
- [ ] Confirm only the selected speed button is highlighted and no duplicate speed text appears beside duration.
- [ ] Pause at a speed above x1, resume, and confirm playback and the highlighted speed reset to x1.
- [ ] Enter video full screen using `View` → `Video Full Screen`, `F11`, and a double-click on the video; confirm no fullscreen button appears on the player panel and only the video fills the display while menus, timeline, table, and panels are hidden.
- [ ] With real VLC video rendering, confirm the native video surface does not cover the fullscreen HUD; verify current/duration time, PLAYING/PAUSED, and the selected speed, then drag the seek slider slowly and quickly and confirm preview/seek behavior remains responsive.
- [ ] Confirm the lower fullscreen HUD is compact, horizontally centered, and fully inside the display at both the native screen resolution and any scaled-display setting used by annotators.
- [ ] Stop moving the mouse and using playback/seek/speed controls; confirm the lower HUD hides after 3 seconds. Move the mouse or press Space/1/2/4/8/seek/frame shortcuts and confirm it returns.
- [ ] Hover the lower HUD and drag its slider for longer than 3 seconds; confirm it remains visible until hover/drag ends and the inactivity timeout elapses.
- [ ] Confirm Start/A shows one persistent `INTERVAL ACTIVE` badge in the upper status area in both popup modes, without a duplicate `Interval started` message.
- [ ] While an interval is active, seek to another timestamp and press Start/A again; confirm the original Start timestamp and active badge do not change. Finish it with End/D or cancel it with Q.
- [ ] Confirm successful End/D replaces that badge with a brief `Interval added` status, cancellation replaces it with `Interval canceled`, and no separate centered notification appears.
- [ ] With popup enabled, confirm the active interval badge remains visible until End or cancellation and the normal interval dialog appears.
- [ ] Change `View` → `Show Interval Details Popup`, restart the application, and confirm the checked state is retained.
- [ ] Simulate or provoke an annotation JSON failure and confirm the fullscreen error remains visible rather than disappearing automatically.
- [ ] Confirm annotation hotkeys remain active in video full screen and the normal layout is restored unchanged after exit.
- [ ] While full screen, press `Esc` and confirm it leaves full screen without cancelling a pending interval; press `Q` with an active interval and confirm fullscreen stays open while the upper status briefly shows `Interval canceled`.
- [ ] Use `View` → `View mode` to switch between Bright and Dark; confirm no theme switch is present on the player panel, text/tables/active controls/interval feedback remain readable, then restart and confirm the selected theme is retained.
- [ ] At the video end, press Play and confirm playback restarts.
- [ ] While paused, select 0°, 90°, 180°, and 270° through `View` → `Video rotation`; confirm no rotation control appears on the player panel and the preview reloads near the previous position.
- [ ] Confirm rotation is unavailable during playback and does not modify the source file or timestamps.

## Event type and interval checks

- [ ] Confirm `event_type` starts as `undefined` and is limited to 25 characters.
- [ ] Edit `event_type`; confirm the indicator and status bar become pending/`Unsaved changes`, then active/`✓ Saved` after Enter, focus loss, about 2 seconds, or explicit Validate & Save.
- [ ] Clear `event_type`; confirm `undefined` is applied.
- [ ] Keep focus in `event_type` and confirm playback/annotation letter and number shortcuts do not trigger while typing.
- [ ] Press `D`/`End` without a start and confirm the `Set interval start first` warning.
- [ ] Press `A`/`Start` and confirm a yellow `INTERVAL ACTIVE` indicator shows the exact Start timestamp, the Start button reads `Start set`, and the End button is highlighted.
- [ ] Press Start/A again at another position and confirm the original Start timestamp does not change.
- [ ] Press `A`/`Start`, seek backward, then press `D`/`End`; confirm an invalid interval is rejected.
- [ ] Press `A`, then `Q`; confirm the pending interval is cancelled and the indicator/buttons return to the ready state.
- [ ] With the popup enabled (the default), create an interval and confirm the video pauses and the popup shows start, end, event type, and comment.
- [ ] Cancel that popup and confirm no interval is added.
- [ ] Create and save an interval with an event type and a non-empty Unicode comment.
- [ ] Disable the popup and confirm a new interval is saved immediately with the active event type and an empty comment.
- [ ] With the popup disabled, set Start near the end and let playback finish; confirm the interval is created automatically with End equal to the exact video duration and the active indicator is cleared.
- [ ] Repeat with the popup enabled; confirm the popup opens automatically at video end and displays the exact duration as End.
- [ ] Confirm interval IDs are sequential and start/end timestamps match the logged positions.
- [ ] Use row `Play`; confirm playback begins at Start and pauses at End.
- [ ] Double-click a row and confirm playback jumps to the interval start.
- [ ] Use `Edit` to change the event type/comment and confirm the table and Event Counts update.
- [ ] Use row `Del`, then select a row and press `Delete`; confirm IDs and Event Counts update after each deletion.

## Live annotation JSON, backup, and project lifecycle

- [ ] Before opening a video, confirm `File` → `Validate & Save Annotations` and `Show Annotation File in Folder` are disabled while `Open Video…` remains enabled.
- [ ] Open a fresh video and confirm the status bar changes to `✓ Saved` and this file is created immediately, before any interval exists:

```text
~/VideoEventLogger/results/<video-stem>.annotations.json
```

- [ ] Parse that initial JSON and confirm `intervals` is an empty array; confirm `Show Annotation File in Folder` is now enabled.
- [ ] Apply an event type before creating an interval and confirm the same annotation JSON is updated.
- [ ] After another successful change, confirm the previous valid document exists as `results/<video-stem>.annotations.json.bak` while the canonical JSON contains the newest state.
- [ ] Without closing the app or using the explicit save action, copy/open the annotation JSON and confirm it already contains every completed interval.
- [ ] Edit and delete intervals; after each action confirm the canonical JSON and `✓ Saved` state reflect the latest table state.
- [ ] Close the app at a non-zero position and confirm the latest position is written to the annotation JSON.
- [ ] Reopen the same video, choose `Continue Existing Work`, and confirm intervals/event type are restored from the canonical JSON.
- [ ] Remove or corrupt a test copy of the canonical JSON while retaining its `.bak`; choose Continue and confirm the previous valid version is recovered without touching the video.
- [ ] Confirm `Continue from last position?` appears; test both Yes and No choices.
- [ ] For a copied legacy project containing `autosave/<video-stem>.autosave.json`, confirm Continue loads it, creates the canonical annotation JSON, and removes the legacy autosave only after the canonical save succeeds.
- [ ] Choose `Start Over`, reject the confirmation once, then accept it and confirm a new empty canonical JSON is saved while the previous version becomes `.bak`.
- [ ] Choose `Delete Project`, reject the confirmation once, then accept it; confirm the annotation JSON, `.bak`, and any legacy autosave are deleted but the video remains untouched.
- [ ] Verify the documented known limitation: videos with the same filename stem share project paths. Do not use colliding names in production annotation batches.

## Annotation JSON and explicit validation

- [ ] Confirm the lower Export action panel and top Open Video/popup/status controls are absent; only video and `event_type` remain in the compact metadata panel.
- [ ] Confirm `Open Video…`, `Validate & Save Annotations`, and `Show Annotation File in Folder` are present under `File`, with `Ctrl/Cmd+O` and `Ctrl/Cmd+S` working.
- [ ] Confirm `Show Interval Details Popup` is a checkable item directly under `View`, not under `View mode`.
- [ ] Create a document containing at least two intervals and confirm this file exists before using explicit validation:

```text
~/VideoEventLogger/results/<video-stem>.annotations.json
```

- [ ] Select `File` → `Validate & Save Annotations`; confirm validation succeeds, the canonical JSON is rewritten, its previous version is in `.bak`, and the status bar shows `✓ Saved`.
- [ ] Select `Show Annotation File in Folder` and confirm the results directory opens.
- [ ] Confirm the JSON is valid UTF-8 and parses successfully:

```bash
python3 -m json.tool "$HOME/VideoEventLogger/results/<video-stem>.annotations.json" >/dev/null
```

- [ ] Confirm top-level `schema_version` is `1.0`, `app_version` is `0.3.5`, and the compatibility field `is_autosave` is `false`.
- [ ] Confirm `video_name` contains only the filename and no `video_path` or full source path is present.
- [ ] Confirm `last_playback_position_seconds`, duration, interval seconds, formatted timestamps, event types, and comments are correct.
- [ ] Confirm the current implementation exports `fps`, `frame_count`, `resolution`, `start_frame`, and `end_frame` as `null`, with `frame_source` set to `unavailable`.

## Annotation API upload

- [ ] Before opening a video, confirm `Connection` → `Settings…` is enabled and `File` → `Upload Annotations…` is disabled; confirm there is no separate `API` menu.
- [ ] Enter an HTTP/HTTPS endpoint URL and token, restart the application, and confirm both values are retained; confirm the token is masked in the settings dialog and absent from the annotation JSON.
- [ ] Confirm the connection dialog and URL field are wide enough to review a long endpoint, URLs of at least 256 characters are accepted, and the eye icon toggles the token between hidden and visible states.
- [ ] Open a video and confirm `Upload Annotations…` becomes enabled only after its annotation JSON exists.
- [ ] Upload to a controlled test endpoint and confirm it receives `POST`, `Authorization: TokenAuth <token>`, `Content-Type: application/json`, and a body byte-for-byte equal to the saved annotation JSON.
- [ ] Confirm the modal progress dialog appears during the request, prevents conflicting interaction, and its Cancel button aborts the request with a clear cancellation message.
- [ ] Return a `2xx` response and confirm the success modal appears.
- [ ] Return `409` with `{"detail": "Already uploaded"}` and confirm the duplicate-specific modal appears.
- [ ] Return `401`, `403`, `500`, malformed/non-JSON error text, and simulate an unreachable/timeout endpoint; confirm each produces a clear failure modal without deleting or changing the saved annotation JSON.
- [ ] Confirm a document with more than 2,000 intervals is rejected locally before any request is sent.
- [ ] Start an interval and confirm upload is rejected until that interval is finished or cancelled.
- [ ] Confirm the packaged build includes QtNetwork and can make the same live upload request as the source build.

## Failure diagnostics and sign-off

- [ ] If VLC initialization fails, capture the full popup text, including attempted libVLC/plugin paths, before changing the machine.
- [ ] If packaging fails, keep the complete PyInstaller and Docker logs.
- [ ] Confirm no secrets, private source-video paths, or test videos are included in the release archive.
- [ ] Record the final archive size and SHA-256 checksum: `____________________________`.
- [ ] All required checks passed, or every accepted exception is linked to an issue/release note.
- [ ] Release approved by: `____________________________`.

# Release Smoke Checklist

Use this checklist before sending any packaged build to a user. Record failures with screenshots/logs and do not mark the release ready while a required item is failing.

Release: `Video Event Logger v0.3.10`

Annotation schema: `1.0`

## Release record

- [ ] Commit/revision: `____________________________`
- [ ] Build date: `____________________________`
- [ ] Builder OS and CPU: `____________________________`
- [ ] Test OS and CPU: `____________________________`
- [ ] VLC version: `____________________________`
- [ ] Tester: `____________________________`

## Source preflight

- [ ] Confirm the release version comes from `video_event_logger/app_config.py` and the window title is expected to be `Video Event Logger v0.3.10`.
- [ ] Confirm no unrelated or unreviewed files are being packaged.
- [ ] Run all unit tests; every test must pass:

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
release/video-event-logger-v0.3.10-ubuntu20.04-amd64.tar.gz
```

- [ ] Confirm the archive has the expected top-level folder, application, `install.sh`, `uninstall.sh`, optional `fix.sh`, launcher, README, and `BUILD_INFO`:

```bash
tar -tzf release/video-event-logger-v0.3.10-ubuntu20.04-amd64.tar.gz | head -30
```

- [ ] Confirm the packaged executable is `ELF 64-bit ... x86-64`, not Mach-O:

```bash
tar -xOzf release/video-event-logger-v0.3.10-ubuntu20.04-amd64.tar.gz \
  video-event-logger-v0.3.10-ubuntu20.04-amd64/video-event-logger/video-event-logger | file -
```

- [ ] Confirm the archive contains no `.dylib` files; this command must print nothing:

```bash
tar -tzf release/video-event-logger-v0.3.10-ubuntu20.04-amd64.tar.gz | grep '\.dylib$'
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

- [ ] Confirm `release/video-event-logger-v0.3.10-macos.zip` exists and contains `Video Event Logger.app` plus `README.txt`.
- [ ] Unzip on a clean Mac with the same architecture, move the app to `Applications`, and install VLC.
- [ ] Start the unsigned app using right-click -> `Open` if Gatekeeper requires it.

## Common launch and playback checks

Repeat this section for every release platform.

- [ ] Confirm the window title is `Video Event Logger v0.3.10` and the application icon is visible.
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
- [ ] At each of x2, x4, and x8, pause and resume using the button and `Space`; confirm playback, the highlighted speed button, and the fullscreen speed label retain the selected speed.
- [ ] Press `1` in both normal and fullscreen views, and click x1 in the normal view; confirm playback returns to normal speed and the speed indicators update.
- [ ] Enter video full screen using `View` → `Full Screen mode` → `Enable Full Screen`, `F11`, and a double-click on the video; confirm no fullscreen button appears on the player panel and only the video fills the display while menus, timeline, table, and panels are hidden.
- [ ] With real VLC video rendering, confirm the native video surface does not cover the fullscreen HUD; verify current/duration time, PLAYING/PAUSED, and the selected speed, then drag the seek slider slowly and quickly and confirm preview/seek behavior remains responsive.
- [ ] Click each fullscreen `-10s`, `-1s`, `+1s`, and `+10s` button while playing and paused; confirm the expected seek, clamping at the video boundaries, and continued keyboard-shortcut operation after clicking.
- [ ] Confirm the lower fullscreen HUD is compact, horizontally centered, and fully inside the display at both the native screen resolution and any scaled-display setting used by annotators.
- [ ] With `View` → `Full Screen mode` → `Keep Controls Visible` disabled (the default for a fresh settings profile), stop moving the mouse and using playback/seek/speed controls; confirm the lower HUD hides after 3 seconds. Move the mouse or press Space/1/2/4/8/seek/frame shortcuts and confirm it returns.
- [ ] Hover the lower HUD and drag its slider for longer than 3 seconds; confirm it remains visible until hover/drag ends and the inactivity timeout elapses.
- [ ] Enable `View` → `Full Screen mode` → `Keep Controls Visible`; confirm the HUD remains visible after more than 3 seconds of inactivity, hides on fullscreen exit, and remains visible after re-entry. Restart the application and confirm the preference is retained. Disable it again and confirm auto-hide returns.
- [ ] Confirm Start/A shows one persistent `INTERVAL ACTIVE` badge in the upper status area in both popup modes, without a duplicate `Interval started` message.
- [ ] While an interval is active, seek to another timestamp and press Start/A again; confirm the original Start timestamp and active badge do not change. Finish it with End/D or cancel it with Q.
- [ ] Confirm successful End/D replaces that badge with a brief `Interval added` status, cancellation replaces it with `Interval canceled`, and no separate centered notification appears.
- [ ] With popup enabled, confirm the active interval badge remains visible until End or cancellation and the normal interval dialog appears.
- [ ] Change `View` → `Show Interval Details Popup`, restart the application, and confirm the checked state is retained.
- [ ] Simulate or provoke an annotation JSON failure and confirm the fullscreen error remains visible rather than disappearing automatically.
- [ ] Confirm annotation hotkeys remain active in video full screen and the normal layout is restored unchanged after exit.
- [ ] While full screen, press `Esc` and confirm it leaves full screen without cancelling a pending interval; press `Q` with an active interval and confirm fullscreen stays open while the upper status briefly shows `Interval canceled`.
- [ ] Use `View` → `Appearance` to switch between Bright and Dark; confirm no theme switch is present on the player panel, text/tables/active controls/interval feedback remain readable, then restart and confirm the selected theme is retained.
- [ ] At the video end, press Play and confirm playback restarts.
- [ ] While paused, select 0°, 90°, 180°, and 270° through `View` → `Rotation`; confirm no rotation control appears on the player panel and the preview reloads near the previous position.
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
- [ ] Confirm `Show Interval Details Popup` is a checkable item directly under `View`, not under `Appearance`.
- [ ] Create a document containing at least two intervals and confirm this file exists before using explicit validation:

```text
~/VideoEventLogger/results/<video-stem>.annotations.json
```

- [ ] Select `File` → `Validate & Save Annotations`; confirm validation succeeds, the canonical JSON is rewritten, its previous version is in `.bak`, and the status bar shows `✓ Saved`.
- [ ] On Linux with a file manager supporting FileManager1 (such as Nautilus), select `Show Annotation File in Folder` and confirm the results directory opens with the current annotation JSON selected. Repeat with spaces and non-ASCII characters in the filename, including when the file manager is initially closed.
- [ ] Where FileManager1 is unavailable, confirm `Show Annotation File in Folder` still opens the results directory without an error.
- [ ] Confirm the JSON is valid UTF-8 and parses successfully:

```bash
python3 -m json.tool "$HOME/VideoEventLogger/results/<video-stem>.annotations.json" >/dev/null
```

- [ ] Confirm top-level `schema_version` is `1.0`, `app_version` is `0.3.10`, and the compatibility field `is_autosave` is `false`.
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

## Playlist, import/export, and interval track

- [ ] Open multiple MP4/MKV files and a folder; verify the right-hand playlist, duplicate prevention, direct-folder filtering, Previous/Next, and opt-in automatic advancement.
- [ ] Open same-named videos in different folders; add different intervals and return to each. Verify separate working JSONs and restored positions.
- [ ] Verify an active interval or failed save prevents switching without losing work.
- [ ] Open a received JSON during video opening and through Open Annotations. Verify immediate table/track display, mismatch warning, and unchanged source JSON after edits.
- [ ] Reject malformed JSON, non-finite/negative/reversed times, and times outside a known video duration without replacing current annotations.
- [ ] Use Save Annotations to export beside a video and into another folder; cancel a subsequent dialog. Verify the chosen snapshot, unchanged autosave location, and remembered export folder.
- [ ] Drag both interval edges, cancel with Escape, edit exact times, and undo. Verify table, working JSON, and interval playback end are synchronized.
- [ ] Verify overlapping lanes, colors/tooltips, selection synchronization, zoom/scroll/Fit, and that dragging an interval body does not move it.
- [ ] Verify the playlist and interval editor hide and return correctly around fullscreen playback.

- [ ] Toggle View → Events Bar → Show, restart the app, and enter/leave fullscreen. Confirm the preference survives and hidden tracks occupy no space.
- [ ] Verify no vertical scrollbar for 0–4 interval lanes at Fit or zoom; for more overlaps verify slim scrolling exposes all lanes. At Fit, the red playhead and seek handle must share the same horizontal position.
- [ ] Play an interval at x1 and x8. Confirm playback pauses on End and both bars show that exact time, without a visible overshoot gap.
- [ ] Repeatedly seek while paused/playing and switch H.264 MP4/MKV videos. Verify the reported get_buffer/thread_get_buffer/decode_slice_header/no frame failure sequence does not recur. Check high-resolution playback performance with indirect software buffers.

- [ ] Enable View → Events Bar → Show in Fullscreen independently of the regular Events Bar. Verify compact text/strokes, zoom, seeking, edge trimming, and the exact interval editor; exit fullscreen and restart to check both preferences.
- [ ] Open videos, a folder, and annotation JSONs; restart and reopen each through File → Recent. Confirm full paths disambiguate names, videos retain working edits, annotation entries use the associated video, and the playlist is not restored.
- [ ] Cancel opening and try a moved/deleted recent file. Confirm the active document is preserved. Clear History and verify source files and the current playlist remain intact.

- [ ] Close Playlist with its X, reopen via View → Playlist, and restart. Confirm visibility is remembered and the selected item survives hiding.
- [ ] Enter fullscreen with Playlist enabled: it starts hidden, opens over the video on the left edge, and hides 0.4 seconds after leaving. Check menus/dialogs, application switching, Escape/F11, and returning to the normal sidebar. With Playlist disabled, the edge must do nothing.
- [ ] Right-click each lane for Play/Edit/Delete; double-click with the left button for Edit. Verify playback stops at End and edits/deletions persist and can be undone.
- [ ] Wheel over the Events Bar at several positions and zoom levels; verify the time under the cursor stays anchored. Shift + wheel pans horizontally, scrollbar exposes overlapping lanes, and Fit shows the full duration.
- [ ] Drag the Events Bar's top grip up/down in both views, then restart. Confirm height is remembered, more lanes become visible, and enough video space remains in a small window.

## Presigned video downloads

- [ ] Paste several links (video, ZIP, TAR, TAR.GZ), choose a folder, and confirm sequential jobs with the requested parallel connections per file. Compare checksums and play the results.
- [ ] During transfer/extraction, hide Downloads with In background, Escape, and ×; reopen via status bar, menu, and Ctrl/Cmd+Shift+J, including fullscreen. Minimize/restore the application.
- [ ] Keep playing video A and create/edit/save intervals while B downloads. Verify playback/annotations survive and B never opens or enters Playlist automatically. Exercise Open video and Add to playlist explicitly.
- [ ] Cancel active and queued jobs individually. Failed jobs must not block the queue. Retry a network error; supply a new link for an expired URL.
- [ ] Quit during transfer and extraction: No keeps the queue alive; Yes cancels all pending jobs and waits for worker cleanup without freezing. No next job may start after confirmed exit.
- [ ] Duplicate names receive a numeric suffix; existing files and the currently playing video remain untouched. Reserved MP4/MKV outputs cannot be opened while queued/running.
- [ ] Test denied/expired links, interrupted connections, single-stream fallback, missing ETags, and changed server objects. Incomplete data must be removed.
- [ ] Confirm signed query parameters never appear in settings, Recent, error logs, or queue labels. Test HTTPS trust in packaged Linux and macOS builds. Queue is session-only.
- [ ] Verify archive detection without URL extensions, nested video extraction, matching checksum, actual MP4/MKV extension, and archive removal. Cancel extraction and verify cleanup.
- [ ] Reject corrupt, encrypted, empty/multiple-video archives, links, unsafe member paths, and insufficient disk space without overwriting existing files.
- [ ] Run `test_background_download_process.py`: separate Qt processes exercise real localhost HTTP downloads, archive extraction, GUI heartbeat, dialog destruction/recreation, annotation saves, and cancellation on exit. A crash or timeout fails the test.

## Active work time

- [ ] Review a video at ×1 and ×4; verify `active_work_seconds` reflects real elapsed foreground time and is included in saved/exported/uploaded JSON.
- [ ] Pause for over a minute: verify the counter stops after 60 seconds and resumes on mouse/keyboard activity without charging the rest of the idle period.
- [ ] Minimize, switch to another application, and suspend/resume the computer during playback. Verify time away is excluded; check normal and fullscreen modes and interval editing dialogs.
- [ ] Switch videos and reopen the application. Verify separate totals continue from each working JSON, including videos without any intervals. Load a legacy JSON and check it starts at zero.
- [ ] Import annotations for the current video twice; verify its accumulated total is not lost or added twice. Confirm time spent in the download dialog is excluded from the work counter.

## OpenSSL packaging regression (since 0.3.9)

- [ ] Confirm `BUILD_INFO.txt` reports both Python SSL and bundled OpenSSL as version 3.
- [ ] Confirm no bundled ELF depends on `libssl.so.1.1` or `libcrypto.so.1.1`; Python `_ssl` and `_hashlib` must resolve OpenSSL 3 from `_internal`.
- [ ] Run `bash packaging/ubuntu_20_04/validate_release_runtime.sh release/video-event-logger-v0.3.10-ubuntu20.04-amd64.tar.gz` and confirm both installation and installed launcher smoke-test pass on Ubuntu 24.04 without OpenSSL 1.1.

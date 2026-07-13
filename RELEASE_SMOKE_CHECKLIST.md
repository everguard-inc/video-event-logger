# Release Smoke Checklist

Use this checklist before sending any packaged build to a user. Record failures with screenshots/logs and do not mark the release ready while a required item is failing.

Release version: `Video Event Logger v0.2.0`  
Annotation schema: `1.0`

> **Known legacy artifact warning (audit 2026-07-13):** the pre-rename `release/video-event-marker-v0.2.0-ubuntu20.04.tar.gz` contains a macOS arm64 Mach-O executable and `.dylib` files. It is not an Ubuntu release and must not be distributed. Build a fresh `video-event-logger` archive with the Docker flow and repeat the artifact checks below.

## Release record

- [ ] Commit/revision: `____________________________`
- [ ] Build date: `____________________________`
- [ ] Builder OS and CPU: `____________________________`
- [ ] Test OS and CPU: `____________________________`
- [ ] VLC version: `____________________________`
- [ ] Tester: `____________________________`

## Source preflight

- [ ] Confirm the release version comes from `video_event_logger/app_config.py` and the window title is expected to be `Video Event Logger v0.2.0`.
- [ ] Confirm no unrelated or unreviewed files are being packaged.
- [ ] Run all unit tests; expect 13 passing tests:

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
bash packaging/ubuntu_20_04/build_in_docker.sh
```

- [ ] Confirm the expected archive exists and was produced by the current build:

```text
release/video-event-logger-v0.2.0-ubuntu20.04.tar.gz
```

- [ ] Confirm the archive has the expected top-level folder and installer:

```bash
tar -tzf release/video-event-logger-v0.2.0-ubuntu20.04.tar.gz | head -30
```

- [ ] Confirm the packaged executable is `ELF 64-bit ... x86-64`, not Mach-O:

```bash
tar -xOzf release/video-event-logger-v0.2.0-ubuntu20.04.tar.gz \
  video-event-logger-v0.2.0-ubuntu20.04/video-event-logger/video-event-logger | file -
```

- [ ] Confirm the archive contains no `.dylib` files; this command must print nothing:

```bash
tar -tzf release/video-event-logger-v0.2.0-ubuntu20.04.tar.gz | grep '\.dylib$'
```

- [ ] Extract and test the archive on a clean Ubuntu 20.04 x86-64 machine, not only in the build container.
- [ ] Install target dependencies:

```bash
sudo apt update
sudo apt install vlc libvlc5 vlc-plugin-base
```

- [ ] Run `bash install.sh` as the normal desktop user; do not run the application installer with `sudo`.
- [ ] Confirm installation under `~/.local/opt/video-event-logger`.
- [ ] Confirm the application-menu launcher appears as `Video Event Logger` and starts without a terminal.

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

- [ ] Confirm `release/video-event-logger-v0.2.0-macos.zip` exists and contains `Video Event Logger.app` plus `README.txt`.
- [ ] Unzip on a clean Mac with the same architecture, move the app to `Applications`, and install VLC.
- [ ] Start the unsigned app using right-click -> `Open` if Gatekeeper requires it.

## Common launch and playback checks

Repeat this section for every release platform.

- [ ] Confirm the window title is `Video Event Logger v0.2.0` and the application icon is visible.
- [ ] Confirm playback/annotation controls are disabled before a video is loaded.
- [ ] Open an `.mp4` video.
- [ ] Open an `.mkv` video in a separate pass.
- [ ] Confirm an unsupported extension is rejected.
- [ ] Confirm the first video frame appears shortly after opening, before manual playback.
- [ ] Confirm the current time, duration, and timeline are updated.
- [ ] Play and pause the video with both the button and `Space`.
- [ ] Drag the timeline slowly and quickly; confirm the preview seeks without freezing or flooding VLC.
- [ ] Test `-1s`, `+1s`, `-10s`, and `+10s` buttons.
- [ ] Test `Left`, `Right`, `Shift+Left`, and `Shift+Right` shortcuts.
- [ ] Test `Frame -`/`,` and `Frame +`/`.` while paused. These are FPS-based approximate steps; confirm sensible movement and no jump outside the video range.
- [ ] Test x1, x2, x4, and x8 using both buttons and numeric shortcuts.
- [ ] Pause at a speed above x1, resume, and confirm playback and the label reset to x1.
- [ ] At the video end, press Play and confirm playback restarts.
- [ ] While paused, rotate through 90, 180, 270, and 0 degrees; confirm the preview reloads near the previous position.
- [ ] Confirm rotation is unavailable during playback and does not modify the source file or timestamps.

## Event type and interval checks

- [ ] Confirm `event_type` starts as `undefined` and is limited to 25 characters.
- [ ] Edit `event_type`; confirm the indicator becomes pending, then active after Enter, focus loss, or about 2 seconds.
- [ ] Clear `event_type`; confirm `undefined` is applied.
- [ ] Keep focus in `event_type` and confirm playback/annotation letter and number shortcuts do not trigger while typing.
- [ ] Press `D`/`End` without a start and confirm the `Set interval start first` warning.
- [ ] Press `A`/`Start`, seek backward, then press `D`/`End`; confirm an invalid interval is rejected.
- [ ] Press `A`, then `Esc`; confirm the pending interval is cancelled.
- [ ] With the popup enabled (the default), create an interval and confirm the video pauses and the popup shows start, end, event type, and comment.
- [ ] Cancel that popup and confirm no interval is added.
- [ ] Create and save an interval with an event type and a non-empty Unicode comment.
- [ ] Disable the popup and confirm a new interval is saved immediately with the active event type and an empty comment.
- [ ] Confirm interval IDs are sequential and start/end timestamps match the logged positions.
- [ ] Use row `Play`; confirm playback begins at Start and pauses at End.
- [ ] Double-click a row and confirm playback jumps to the interval start.
- [ ] Use `Edit` to change the event type/comment and confirm the table and Event Counts update.
- [ ] Use row `Del`, then select a row and press `Delete`; confirm IDs and Event Counts update after each deletion.

## Autosave and project lifecycle

- [ ] After create/edit/delete, confirm the save lamp is green and this file exists:

```text
~/VideoEventLogger/autosave/<video-stem>.autosave.json
```

- [ ] Close the app at a non-zero position and confirm the latest position is written to autosave.
- [ ] Reopen the same video, choose `Continue Existing Work`, and confirm intervals/event type are restored.
- [ ] Confirm `Continue from last position?` appears; test both Yes and No choices.
- [ ] When both autosave and final JSON exist, confirm Continue loads the autosave version.
- [ ] Choose `Start Over`, reject the confirmation once, then accept it and confirm a new empty project is shown.
- [ ] Choose `Delete Project`, reject the confirmation once, then accept it; confirm autosave/final JSON files are deleted but the video remains untouched.
- [ ] Verify the documented known limitation: videos with the same filename stem share project paths. Do not use colliding names in production annotation batches.

## Final JSON export

- [ ] Select `Finish & Save JSON` with no intervals and confirm both No and Yes paths in the empty-file prompt.
- [ ] Save a document containing at least two intervals and confirm this file exists:

```text
~/VideoEventLogger/results/<video-stem>.annotations.json
```

- [ ] Select `Open result folder` and confirm the results directory opens.
- [ ] Confirm the JSON is valid UTF-8 and parses successfully:

```bash
python3 -m json.tool "$HOME/VideoEventLogger/results/<video-stem>.annotations.json" >/dev/null
```

- [ ] Confirm top-level `schema_version` is `1.0`, `app_version` is `0.2.0`, and `is_autosave` is `false`.
- [ ] Confirm `video_name` contains only the filename and no `video_path` or full source path is present.
- [ ] Confirm `last_playback_position_seconds`, duration, interval seconds, formatted timestamps, event types, and comments are correct.
- [ ] Confirm the current implementation exports `fps`, `frame_count`, `resolution`, `start_frame`, and `end_frame` as `null`, with `frame_source` set to `unavailable`.

## Failure diagnostics and sign-off

- [ ] If VLC initialization fails, capture the full popup text, including attempted libVLC/plugin paths, before changing the machine.
- [ ] If packaging fails, keep the complete PyInstaller and Docker logs.
- [ ] Confirm no secrets, private source-video paths, or test videos are included in the release archive.
- [ ] Record the final archive size and SHA-256 checksum: `____________________________`.
- [ ] All required checks passed, or every accepted exception is linked to an issue/release note.
- [ ] Release approved by: `____________________________`.

# Background download queue — validation

Date: 2026-11-02. Source changes after release 0.3.9; no new release archive built.

## Behavior

- Paste one HTTPS/S3 link per line and choose a folder. One queued file downloads at a time, using 1–16 connections; archives are extracted before the next job starts.
- Downloads is non-modal. In background, Escape, and × hide the view without stopping the queue. Reopen from the status bar, menu, or keyboard shortcut.
- Completion leaves the current video and annotations alone. Open video and Add to playlist are explicit actions.
- Failed jobs remain visible and do not block subsequent jobs. Retry uses the in-memory URL; an expired link requires a new URL. The queue is not persisted.
- Existing filenames receive a numeric suffix in the UI. Both possible archive output extensions are reserved while queued/running.
- Confirmed application exit cancels pending work and waits asynchronously for active cleanup. No active QThread belongs to the dialog or is deleted while running.

## Automated results

- macOS host, Python 3.12, Qt offscreen: **187 tests passed**.
- Ubuntu **20.04 amd64** container, Python 3.12.4 / PySide6 6.7.3: **187 tests passed**.
- Separate interpreter scenarios use actual localhost HTTP transfers and Qt threads. A native crash, timeout, QObject thread warning, destroyed-running-QThread warning, or QWaitCondition warning fails the process regression test.
- Verified sequential transfers, byte checksums, actual ZIP extraction to MKV, repeated hide/show and deletion/recreation of Downloads, annotation changes and saves during transfer, minimizing/restoring, and no automatic video switch.
- Verified rejecting exit keeps the queue alive; confirmed exit cancels active/pending jobs and leaves the actual QApplication event loop normally. Temporary files are removed.
- Additional runs decoded a generated 30-second MPEG-4 video through real libVLC with dummy video/audio outputs during downloads and annotation saves. Playback continued on macOS and Ubuntu 20.04. Maximum measured GUI heartbeat gap in the final Ubuntu run: **0.151 seconds** (test limit: 1.5 seconds).
- Existing downloader/archive tests cover range retries, single-stream fallback, HTTP denial, server changes, extraction cancellation, archive corruption, unsafe members, and disk-space failures.
- Python compileall and git diff --check passed.

## Lifetime and threading safeguards

`services/download_queue.py` owns the session queue and QThreads as a child of the main window. Certificate setup, HTTP transfers, file writes, and extraction run outside the GUI thread. Explicit queued connections deliver progress to QObject slots on the GUI thread. On completion, a timer checks that QThread.wait succeeds before releasing the worker or starting the next job.

The completion check uses QDeadlineTimer.current rather than a literal zero timeout: Qt 6.7's negative expired-deadline sentinel produced a pthread condition warning on Ubuntu. A real expired timestamp preserves nonblocking behavior without that warning.

The UI tests explicitly yield the Python GIL while pumping events with QTest.qWait; QApplication.exec is exercised separately by the exit process scenario.

## Limits

These are source-level automated/headless checks, including real HTTP, disk I/O and VLC decoding. They do not validate native desktop video rendering or a newly packaged release. Real S3 credentials/links were not used. The exact cause of the older reported crash cannot be established without its crash log; the new lifecycle is independently regression-tested.

"""Crash/hang regression scenario, run in a separate interpreter by unittest.

Optional VEL_TEST_VIDEO exercises actual libVLC decoding with a dummy video
output (no native desktop required). No network request leaves localhost.
"""
import gc
import hashlib
import io
import os
from pathlib import Path
import sys
import tempfile
import threading
import time
import zipfile
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtCore import QCoreApplication, QEvent, QTimer
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QMessageBox
from video_event_logger.ui.main_window import MainWindow
from video_event_logger.services.video_download import DownloadCancelled
from test_video_download import FixtureServer


def wait_for(predicate, timeout=15):
    deadline = time.monotonic() + timeout
    while not predicate() and time.monotonic() < deadline:
        QTest.qWait(10)
    assert predicate(), "Timed out waiting for background download"


def run(mode):
    app = QApplication([])
    app.setQuitOnLastWindowClosed(False)
    server = FixtureServer()
    server.payload *= 3
    serving = threading.Thread(target=server.serve_forever, daemon=True)
    serving.start()
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        settings = Mock()
        settings.value.side_effect = lambda key, default: default
        playback = os.environ.get("VEL_TEST_VIDEO")
        with patch("video_event_logger.ui.main_window.QSettings", return_value=settings), \
                patch("video_event_logger.services.path_utils.RESULTS_DIR", root / "annotations"), \
                patch("video_event_logger.services.path_utils.LEGACY_AUTOSAVE_DIR", root / "legacy"), \
                patch("video_event_logger.ui.video_player._vlc_initialization_attempts", return_value=[["--ignore-config", "--vout=dummy", "--aout=dummy", "--avcodec-hw=none"]]), \
                patch("video_event_logger.ui.video_player.VideoPlayer._attach_video_surface"):
            window = MainWindow()
            controller = window.controller
            controller._prepare_video_preview = Mock()
            player = controller.video_player
            if playback:
                current = Path(playback)
            else:
                current = root / "current.mp4"
                current.write_bytes(b"current video")
                player.load_video = Mock(return_value=True)
                player.get_duration_seconds = Mock(return_value=120.0)
                player.get_time_seconds = Mock(return_value=0.0)
            window.show()
            assert controller._open_video_path(current)
            if playback:
                player.play()
                wait_for(lambda: player.is_playing() and player.get_time_seconds() > 0)
            queue = controller.download_queue
            ticks = []
            pulse = QTimer(window)
            pulse.setInterval(10)
            pulse.timeout.connect(lambda: ticks.append(time.monotonic()))
            pulse.start()
            url = "http://127.0.0.1:%d/video?signature=background-test-secret" % server.server_port
            controller.download_video()
            first = queue.enqueue(url, root / "one.mp4", 2)
            second = queue.enqueue(url, root / "two.mp4", 2)
            try:
                wait_for(lambda: first.done > 0)
                if mode == "complete":
                    for _ in range(10):
                        controller.download_dialog.background_button.click()
                        controller.annotation_service.start_interval(1)
                        controller.annotation_service.end_interval(2, "event", "while downloading")
                        controller._refresh_table()
                        assert controller._save_checkpoint("Background test")
                        controller.download_video()
                        controller.download_dialog.close()
                        QTest.qWait(20)
                    window.showMinimized()
                    QTest.qWait(30)
                    window.showNormal()
                    # Delete only the view, including pending queued progress signals.
                    controller.download_dialog.deleteLater()
                    controller.download_dialog = None
                    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
                    gc.collect()
                    controller.download_video()
                    wait_for(lambda: not queue.busy)
                    assert first.state == second.state == "completed"
                    digest = hashlib.sha256(server.payload).digest()
                    assert all(hashlib.sha256(j.result_path.read_bytes()).digest() == digest for j in (first, second))
                    assert len(controller.document.intervals) == 10
                    assert controller.current_video_path == current.resolve()
                    assert (root / "one.mp4").resolve() not in window.workspace.playlist_panel.paths
                    # Real archive transfer and extraction, followed by another job.
                    video = server.payload
                    buffer = io.BytesIO()
                    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_STORED) as archive:
                        archive.writestr("nested/clip.mkv", video)
                    server.payload = buffer.getvalue()
                    archived = queue.enqueue(url, root / "archive.mp4", 4)
                    wait_for(lambda: not queue.busy)
                    assert archived.state == "completed"
                    assert archived.result_path.suffix == ".mkv"
                    assert hashlib.sha256(archived.result_path.read_bytes()).digest() == digest
                    if playback:
                        assert player.is_playing(), "Playback stopped during downloads"
                        assert player.get_time_seconds() > 1
                    assert len(ticks) > 20
                    gaps = [b - a for a, b in zip(ticks, ticks[1:])]
                    assert max(gaps) < 1.5, "GUI event loop stalled: %s" % max(gaps)
                    print("GUI heartbeat max gap: %.3fs; checksums, archive, annotations, playback state: PASS" % max(gaps), flush=True)
                    window.close()
                elif mode == "exit":
                    with patch("video_event_logger.tasks.event_logging.controller.QMessageBox.question", return_value=QMessageBox.StandardButton.No):
                        window.close()
                    assert window.isVisible() and queue.busy
                    app.setQuitOnLastWindowClosed(True)
                    watchdog = QTimer()
                    watchdog.setSingleShot(True)
                    watchdog.timeout.connect(lambda: app.exit(2))
                    watchdog.start(15000)
                    with patch("video_event_logger.tasks.event_logging.controller.QMessageBox.question", return_value=QMessageBox.StandardButton.Yes):
                        QTimer.singleShot(0, window.close)
                        exit_code = app.exec()
                    watchdog.stop()
                    assert exit_code == 0, "Application did not exit after cancelling downloads"
                    assert not queue.busy and not window.isVisible()
                    assert first.state == second.state == "cancelled"
                    assert not (root / "two.mp4").exists()
                assert not list(root.glob("*.part"))
                assert "background-test-secret" not in str(settings.setValue.call_args_list)
            finally:
                queue.cancel_all()
                wait_for(lambda: not queue.busy)
                player.pause()
                if player.media_player is not None:
                    player.media_player.stop()
                controller.timer.stop()
                controller.work_time_monitor.stop()
                window.deleteLater()
                QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        server.shutdown()
        server.server_close()
        serving.join()
    print("BACKGROUND_SCENARIO_PASS " + mode, flush=True)


if __name__ == "__main__":
    run(sys.argv[1])

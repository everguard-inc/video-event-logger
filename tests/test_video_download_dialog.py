import os
from pathlib import Path
import tempfile
import time
import threading
import unittest
from unittest.mock import Mock, patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtCore import QCoreApplication, QEvent, QObject
from PySide6.QtWidgets import QApplication
from PySide6.QtTest import QTest

from video_event_logger.services.download_queue import DownloadQueue
from video_event_logger.services.video_download import DownloadCancelled, DownloadError
from video_event_logger.ui.video_download_dialog import VideoDownloadDialog


class DownloadDialogTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.owner = QObject()
        self.queue = DownloadQueue(self.owner)
        self.settings = Mock()
        self.settings.value.side_effect = lambda key, default: default
        self.dialog = VideoDownloadDialog(self.settings, self.queue)
        self.dialog.path_input.setText(str(self.root))
        self.addCleanup(self.cleanup)

    def cleanup(self):
        self.queue.cancel_all()
        self.wait_for(lambda: not self.queue.busy)
        self.dialog.deleteLater()
        self.owner.deleteLater()
        QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)

    def wait_for(self, predicate):
        deadline = time.monotonic() + 5
        while not predicate() and time.monotonic() < deadline:
            QTest.qWait(10)
            # qWait pumps Qt from Python rather than running QApplication.exec().
            # Yield the GIL explicitly so QThread.run can enter Python reliably.
            time.sleep(0.001)
        if not predicate():
            import faulthandler
            faulthandler.dump_traceback()
        self.assertTrue(predicate(), repr([(j.path.name, j.state, j.status) for j in self.queue.jobs]) +
                        " worker=%s timer=%s" % (self.queue.worker, self.queue.reap_timer.isActive()))

    def add(self, name="video.mp4"):
        return self.queue.enqueue("https://example.org/" + name + "?signature=secret", self.root / name)

    def test_batch_uses_unique_names_and_never_persists_links(self):
        self.dialog.url_input.setPlainText("https://a/video.mp4?sig=one\nhttps://b/video.mp4?sig=two")
        self.dialog.start_download()
        self.assertEqual([j.path.name for j in self.queue.jobs], ["video.mp4", "video (2).mp4"])
        self.assertEqual(self.dialog.url_input.toPlainText(), "")
        self.settings.setValue.assert_called_once_with("downloads/directory", str(self.root))
        self.assertNotIn("secret", repr(self.queue.jobs))
        self.queue.cancel_all()  # Before the scheduled start: no network needed.

    def test_hide_close_and_destroy_view_do_not_cancel_worker(self):
        release = threading.Event()
        def transfer(downloader):
            release.wait(3)
            return downloader.destination
        with patch("video_event_logger.services.download_queue.VideoDownloader.run", transfer):
            job = self.add()
            self.wait_for(lambda: self.queue.worker is not None)
            worker = self.queue.worker
            try:
                self.dialog.show()
                self.assertFalse(self.dialog.isModal())
                self.dialog.background_button.click()
                self.assertFalse(self.dialog.isVisible())
                self.dialog.show()
                self.dialog.close()
                self.dialog.deleteLater()
                QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
                self.dialog = VideoDownloadDialog(self.settings, self.queue)
                self.dialog.show()
                self.assertIs(self.queue.worker, worker)
                self.assertFalse(worker.cancel_event.is_set())
            finally:
                release.set()
                self.wait_for(lambda: not self.queue.busy)
            self.assertEqual(job.state, "completed")
            self.assertEqual(job.url, "")
            self.assertTrue(self.dialog.card_for(job).open_button.isVisibleTo(self.dialog.card_for(job)))

    def test_queue_runs_in_order_and_error_does_not_block_next_file(self):
        order = []
        def transfer(downloader):
            order.append(downloader.destination.name)
            if downloader.destination.name == "bad.mp4":
                raise DownloadError("Link expired. Request a new link.")
            return downloader.destination
        with patch("video_event_logger.services.download_queue.VideoDownloader.run", transfer):
            jobs = [self.add(name) for name in ("one.mp4", "bad.mp4", "three.mp4")]
            self.wait_for(lambda: not self.queue.busy)
        self.assertEqual(order, ["one.mp4", "bad.mp4", "three.mp4"])
        self.assertEqual([j.state for j in jobs], ["completed", "failed", "completed"])
        self.assertIn("failed", self.queue.summary())
        with patch("video_event_logger.services.download_queue.VideoDownloader.run", lambda d: d.destination):
            retry = self.queue.retry(jobs[1])
            self.assertIs(retry, jobs[1])
            self.wait_for(lambda: not self.queue.busy)
        self.assertEqual(retry.state, "completed")
        self.assertEqual(jobs[1].url, "")

    def test_expired_link_keeps_partial_and_new_link_resumes_same_job(self):
        from video_event_logger.services.video_download import LinkExpiredError, ResumeState
        partial = self.root / ".video-download-x.part"
        partial.write_bytes(b"\0" * 100)
        state = ResumeState(partial, 100, '"etag"', [[0, 99, 40]])
        seen = []
        def expire(downloader):
            seen.append(downloader.resume)
            raise LinkExpiredError("The link expired.", state)
        with patch("video_event_logger.services.download_queue.VideoDownloader.run", expire):
            job = self.queue.enqueue("https://example.org/clip.zip?signature=secret", self.root / "clip.mp4")
            self.wait_for(lambda: not self.queue.busy)
        self.assertEqual((job.state, job.kind, job.kept_bytes), ("expired", "archive", 40))
        self.assertTrue(job.needs_new_link)
        self.assertIn("new link", self.queue.summary())
        with self.assertRaises(DownloadError):
            self.queue.retry(job)
        with patch("video_event_logger.services.download_queue.VideoDownloader.run",
                   lambda d: seen.append(d.resume) or d.destination):
            self.assertIs(self.queue.continue_with_link(job, "https://example.org/clip.zip?new=1"), job)
            self.wait_for(lambda: not self.queue.busy)
        self.assertEqual(job.state, "completed")
        self.assertEqual(seen, [None, state])
        self.queue.remove(job)
        self.assertNotIn(job, self.queue.jobs)

    def test_cancelling_a_stopped_download_deletes_kept_data(self):
        from video_event_logger.services.video_download import ResumableDownloadError, ResumeState
        partial = self.root / ".video-download-y.part"
        partial.write_bytes(b"data")
        state = ResumeState(partial, 10, '"etag"', [[0, 9, 4]])
        def stop(downloader):
            raise ResumableDownloadError("Connection lost for too long.", state)
        with patch("video_event_logger.services.download_queue.VideoDownloader.run", stop):
            job = self.add()
            self.wait_for(lambda: not self.queue.busy)
        self.assertTrue(job.can_retry)
        self.queue.cancel(job)
        self.assertEqual(job.state, "cancelled")
        self.assertFalse(partial.exists())

    def test_cancel_active_keeps_native_thread_until_cleanup_and_skips_cancelled_queued(self):
        entered, release = threading.Event(), threading.Event()
        def transfer(downloader):
            entered.set()
            downloader.cancel.wait(3)
            release.wait(3)
            raise DownloadCancelled()
        with patch("video_event_logger.services.download_queue.VideoDownloader.run", transfer):
            first, second = self.add(), self.add("second.mp4")
            self.wait_for(entered.is_set)
            self.queue.cancel(second)
            worker = self.queue.worker
            self.queue.cancel(first)
            QTest.qWait(30)
            self.assertIs(self.queue.worker, worker)
            self.assertTrue(self.queue.busy)
            self.assertTrue(worker.cancel_event.is_set())
            release.set()
            self.wait_for(lambda: not self.queue.busy)
        self.assertEqual([first.state, second.state], ["cancelled", "cancelled"])
        self.assertEqual(first.url + second.url, "")

    def test_large_progress_and_unpacking_are_delivered_on_gui_thread(self):
        from PySide6.QtCore import QThread
        entered, release = threading.Event(), threading.Event()
        def transfer(downloader):
            downloader.stage("Unpacking archive…")
            downloader.progress(5 * 1024**3, 10 * 1024**3, 0, 0)
            entered.set()
            release.wait(3)
            return downloader.destination
        threads = []
        self.queue.changed.connect(lambda: threads.append(QThread.currentThread()))
        with patch("video_event_logger.services.download_queue.VideoDownloader.run", transfer):
            self.add()
            self.wait_for(lambda: entered.is_set() and self.dialog.cards and self.dialog.cards[0].progress_bar.value() == 500)
            card = self.dialog.cards[0]
            self.assertIn("5.0 GiB / 10.0 GiB", card.status_label.text())
            self.assertIn("Unpacking", card.status_label.text())
            self.assertEqual(card.state_label.text(), "Unpacking")
            self.assertTrue(all(t is self.app.thread() for t in threads))
            release.set()
            self.wait_for(lambda: not self.queue.busy)

    def test_current_video_and_both_archive_extensions_are_reserved(self):
        path = self.root / "video.mkv"
        self.queue.current_video = lambda: path
        with self.assertRaises(DownloadError):
            self.add()
        self.queue.current_video = lambda: None
        self.add()
        self.assertTrue(self.queue.reserves_path(path))
        with self.assertRaises(DownloadError):
            self.add("video.mkv")
        self.queue.cancel_all()

    def test_file_changed_while_queued_is_never_replaced(self):
        path = self.root / "existing.mp4"
        path.write_bytes(b"original")
        job = self.queue.enqueue("https://example.org/video", path, overwrite=True)
        path.write_bytes(b"new content created after queueing")
        with patch("video_event_logger.services.download_queue.VideoDownloader.run") as run:
            self.wait_for(lambda: not self.queue.busy)
        run.assert_not_called()
        self.assertEqual(job.state, "failed")
        self.assertEqual(path.read_bytes(), b"new content created after queueing")

    @patch("video_event_logger.ui.video_download_dialog.QMessageBox.warning")
    def test_invalid_batch_enqueues_nothing(self, warning):
        self.dialog.url_input.setPlainText("https://a/video.mp4\ninvalid")
        self.dialog.start_download()
        self.assertEqual(self.queue.jobs, [])
        warning.assert_called_once()

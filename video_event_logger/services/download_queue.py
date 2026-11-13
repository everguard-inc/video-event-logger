"""Session-only sequential downloads, owned by the main window, not a dialog."""
from dataclasses import dataclass, field
from pathlib import Path
import ssl
import threading
import time

from PySide6.QtCore import QDeadlineTimer, QObject, QThread, QTimer, Qt, Signal, Slot
from PySide6.QtNetwork import QSslConfiguration

from video_event_logger.services.path_utils import is_supported_video
from video_event_logger.services.sleep_inhibitor import SleepInhibitor
from video_event_logger.services.video_download import (
    DownloadCancelled, DownloadError, LinkExpiredError, ResumableDownloadError,
    VideoDownloader, link_format, link_kind, validate_download_url,
)


def destination_stamp(path):
    try:
        info = path.lstat()
        return info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns
    except FileNotFoundError:
        return None


def destinations(path):
    # Archives can change the selected extension to the contained video's format.
    return {path.with_suffix(suffix).resolve() for suffix in (".mp4", ".mkv")} | {path.resolve()}


@dataclass
class DownloadJob:
    url: str = field(repr=False)
    path: Path
    connections: int
    stamp: object = field(repr=False)
    state: str = "queued"
    status: str = "Queued"
    done: int = 0
    total: object = None
    speed: float = 0
    active_connections: int = 0
    result_path: object = None
    kind: str = "unknown"  # "video", "archive" or "unknown" until the content is seen
    url_format: str = ""  # "MP4", "ZIP", "TAR.GZ"… from the link, for display
    stage: str = "download"  # "download" or "unpack" while running
    resume: object = field(default=None, repr=False)  # ResumeState with bytes kept on disk
    retry_at: float = 0.0  # monotonic time of the next automatic retry while waiting

    @property
    def kept_bytes(self):
        return self.resume.done if self.resume is not None else 0

    @property
    def can_retry(self):
        return self.state == "failed" and bool(self.url)

    @property
    def needs_new_link(self):
        return self.state == "expired"


class DownloadThread(QThread):
    progress = Signal(object, object, float, int)
    stage_changed = Signal(str)
    waiting = Signal(float)

    def __init__(self, job, parent):
        super().__init__(parent)
        self.job = job
        self.resume = job.resume
        self.cancel_event = threading.Event()
        self.retry_now_event = threading.Event()
        self.result_path = None
        self.error_message = None
        self.was_cancelled = False
        self.resume_state = None
        self.link_expired = False

    def run(self):
        try:
            # Trust-store discovery and downloader initialization can block too.
            # Keep them off the GUI thread, alongside network and disk operations.
            context = ssl.create_default_context()
            roots = QSslConfiguration.systemCaCertificates()
            if roots:
                context.load_verify_locations(cadata=b"".join(bytes(cert.toPem()) for cert in roots).decode("ascii"))
            downloader = VideoDownloader(self.job.url, self.job.path, self.job.connections,
                                         self.progress.emit, self.cancel_event, context,
                                         stage=self.stage_changed.emit, waiting=self.waiting.emit,
                                         resume=self.resume, retry_now=self.retry_now_event)
            if downloader.original_destination != self.job.stamp:
                raise DownloadError("The destination changed while queued. Choose another filename.")
            self.result_path = downloader.run()
        except DownloadCancelled:
            self.was_cancelled = True
        except ResumableDownloadError as exc:
            self.error_message = str(exc)
            self.resume_state = exc.state
            self.link_expired = isinstance(exc, LinkExpiredError)
        except DownloadError as exc:
            self.error_message = str(exc)
        except Exception:
            self.error_message = "The download could not be completed. Check the destination and try again."

    def cancel(self):
        self.cancel_event.set()


class DownloadQueue(QObject):
    changed = Signal()
    completed = Signal(object)
    idle = Signal()

    def __init__(self, parent=None, current_video=None):
        super().__init__(parent)
        self.current_video = current_video or (lambda: None)
        self.jobs = []
        self.worker = None
        self.active_job = None
        self.stopping = False
        self.reap_timer = QTimer(self)
        self.reap_timer.setInterval(10)
        self.reap_timer.timeout.connect(self._reap_worker)
        self.sleep_inhibitor = SleepInhibitor()
        self.changed.connect(self._update_sleep_inhibitor)

    @Slot()
    def _update_sleep_inhibitor(self):
        self.sleep_inhibitor.set_active(self.worker is not None)

    @property
    def keeps_awake(self):
        return self.sleep_inhibitor.active

    @property
    def busy(self):
        return self.worker is not None or any(job.state == "queued" for job in self.jobs)

    def reserves_path(self, path):
        return any(Path(path).resolve() in destinations(job.path) for job in self.jobs
                   if job.state in ("queued", "running", "cancelling"))

    def enqueue(self, url, path, connections=8, overwrite=False):
        if self.stopping:
            raise DownloadError("Downloads are stopping. Please wait.")
        url = validate_download_url(url)
        path = Path(path).expanduser().absolute()
        if not is_supported_video(path) or not path.parent.is_dir() or path.is_dir():
            raise DownloadError("Choose an existing folder and a filename ending in .mp4 or .mkv.")
        current = self.current_video()
        if current is not None and Path(current).resolve() in destinations(path):
            raise DownloadError("Choose a different filename from the video currently open in the player.")
        if any(self.reserves_path(candidate) for candidate in destinations(path)):
            raise DownloadError("This filename is already reserved by another download.")
        stamp = destination_stamp(path)
        if stamp is not None and not overwrite:
            raise DownloadError("This file already exists. Choose another filename or confirm replacement.")
        job = DownloadJob(url, path, max(1, min(16, int(connections))), stamp, kind=link_kind(url), url_format=link_format(url))
        self.jobs.append(job)
        self.changed.emit()
        QTimer.singleShot(0, self._start_next)
        return job

    @Slot()
    def _start_next(self):
        if self.worker is not None or self.stopping:
            return
        job = next((job for job in self.jobs if job.state == "queued"), None)
        if job is None:
            return
        current = self.current_video()
        if current is not None and Path(current).resolve() in destinations(job.path):
            job.state, job.status = "failed", "Destination is open in the player. Choose another filename."
            self.changed.emit()
            QTimer.singleShot(0, self._start_next)
            return
        self.active_job = job
        job.state, job.status, job.stage = "running", ("Resuming…" if job.resume else "Connecting…"), "download"
        worker = DownloadThread(job, self)
        self.worker = worker  # Strong ownership until the native thread has exited.
        worker.progress.connect(self._progress, Qt.ConnectionType.QueuedConnection)
        worker.stage_changed.connect(self._stage, Qt.ConnectionType.QueuedConnection)
        worker.waiting.connect(self._waiting, Qt.ConnectionType.QueuedConnection)
        worker.finished.connect(self._worker_finished, Qt.ConnectionType.QueuedConnection)
        worker.start()
        self.changed.emit()

    @Slot(object, object, float, int)
    def _progress(self, done, total, speed, connections):
        job = self.active_job
        if job is None or job.state not in ("running", "waiting"):
            return
        if job.state == "waiting" and done <= job.done and connections:
            return  # still no new bytes since the connection dropped
        job.state = "running"
        job.done, job.total, job.speed, job.active_connections = done, total, speed, connections
        job.status = "Unpacking video" if connections == 0 else "Downloading"
        self.changed.emit()

    @Slot(float)
    def _waiting(self, retry_in):
        job = self.active_job
        if job is None or job.state not in ("running", "waiting"):
            return
        job.state = "waiting"
        job.retry_at = time.monotonic() + retry_in
        job.status = "Connection lost. Downloaded data is kept; the download continues by itself when the network is back."
        self.changed.emit()

    def retry_now(self, job):
        if job is self.active_job and self.worker is not None and job.state == "waiting":
            self.worker.retry_now_event.set()

    @Slot(str)
    def _stage(self, text):
        if self.active_job is not None and self.active_job.state in ("running", "waiting"):
            self.active_job.state = "running"
            self.active_job.status = text
            if "Unpacking" in text:
                self.active_job.stage, self.active_job.kind = "unpack", "archive"
            self.active_job.done, self.active_job.total = 0, None
            self.changed.emit()

    @Slot()
    def _worker_finished(self):
        self.reap_timer.start()
        self._reap_worker()

    @Slot()
    def _reap_worker(self):
        worker = self.worker
        # finished() can precede native thread-local cleanup. Never block the UI
        # waiting for it, and never delete a QThread that hasn't fully exited.
        # A literal zero timeout uses a negative sentinel deadline in Qt 6.7,
        # which can produce EINVAL from pthread_cond_timedwait on Linux.
        # An already-expired, real timestamp is equally nonblocking and valid.
        if worker is None or not worker.wait(QDeadlineTimer.current(Qt.TimerType.PreciseTimer)):
            return
        self.reap_timer.stop()
        job = self.active_job
        if worker.result_path is not None:
            job.state, job.status = "completed", "Ready"
            job.result_path = worker.result_path
            job.url, job.resume = "", None
            if job.result_path.suffix.lower() != job.path.suffix.lower():
                job.kind = "archive"
        elif worker.was_cancelled:
            self._discard_partial(job)
            job.state, job.status, job.url = "cancelled", "Cancelled; incomplete data removed", ""
        elif worker.resume_state is not None:
            job.resume = worker.resume_state
            job.done, job.total = job.resume.done, job.resume.total
            job.state = "expired" if worker.link_expired else "failed"
            job.status = worker.error_message
            if worker.link_expired:
                job.url = ""
        else:
            # A failed resume attempt can leave a kept file that is no longer usable.
            if job.resume is not None and not job.resume.temp_path.exists():
                job.resume = None
            job.state, job.status = "failed", worker.error_message
        self.worker = self.active_job = None
        worker.deleteLater()
        self.changed.emit()
        if job.state == "completed":
            self.completed.emit(job.result_path)
        if not self.busy:
            self.stopping = False
            self.idle.emit()
        else:
            QTimer.singleShot(0, self._start_next)

    def _discard_partial(self, job):
        if job.resume is not None:
            try:
                job.resume.temp_path.unlink(missing_ok=True)
            except OSError:
                pass
            job.resume = None

    def cancel(self, job):
        if job.state == "queued":
            self._discard_partial(job)
            job.state, job.status, job.url = "cancelled", "Cancelled", ""
        elif job is self.active_job:
            job.state, job.status = "cancelling", "Cancelling… Waiting for the current operation to stop."
            self.worker.cancel()
        elif job.state in ("failed", "expired"):
            self._discard_partial(job)
            job.state, job.status, job.url = "cancelled", "Cancelled; incomplete data removed", ""
        self.changed.emit()

    def remove(self, job):
        """Forget a finished job (its file, if any, stays on disk)."""
        if job.state in ("completed", "cancelled", "failed", "expired"):
            self._discard_partial(job)
            self.jobs.remove(job)
            self.changed.emit()

    def _requeue(self, job):
        if self.stopping:
            raise DownloadError("Downloads are stopping. Please wait.")
        # Never silently renew overwrite approval for a file changed since enqueue.
        if destination_stamp(job.path) != job.stamp:
            raise DownloadError("The destination changed. Choose another filename.")
        if any(self.reserves_path(candidate) for candidate in destinations(job.path)):
            raise DownloadError("This filename is already reserved by another download.")
        job.state, job.status = "queued", "Queued"
        self.changed.emit()
        QTimer.singleShot(0, self._start_next)
        return job

    def retry(self, job):
        if job.state != "failed" or not job.url:
            raise DownloadError("Paste a new link to restart this download.")
        return self._requeue(job)

    def continue_with_link(self, job, url):
        """Continue a stopped download through a new link to the same file."""
        if job.state not in ("failed", "expired"):
            raise DownloadError("Only a stopped download can continue with a new link.")
        job.url = validate_download_url(url.strip())
        return self._requeue(job)

    def cancel_all(self):
        self.stopping = True
        for job in self.jobs:
            if job.state == "queued":
                self._discard_partial(job)
                job.state, job.status, job.url = "cancelled", "Cancelled", ""
            elif job.state in ("failed", "expired"):
                self._discard_partial(job)
                job.url = ""
        if self.active_job is not None:
            self.cancel(self.active_job)
        else:
            self.changed.emit()
            self.stopping = False
            self.idle.emit()

    def summary(self):
        queued = sum(job.state == "queued" for job in self.jobs)
        failed = sum(job.state == "failed" for job in self.jobs)
        if self.active_job is not None:
            job = self.active_job
            progress = " %d%%" % min(100, job.done * 100 // job.total) if job.total else ""
            if job.state == "waiting":
                return "Downloads: waiting for network%s · %d queued" % (progress, queued)
            return "Downloads: %s%s · %d queued" % (job.status.split("…")[0], progress, queued)
        if queued:
            return "Downloads: %d queued" % queued
        ready = sum(job.state == "completed" for job in self.jobs)
        expired = sum(job.state == "expired" for job in self.jobs)
        if expired:
            return "Downloads: %d ready · %d need a new link" % (ready, expired)
        return "Downloads: %d ready · %d failed" % (ready, failed)

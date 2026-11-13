"""Bounded parallel HTTP downloads. Signed URLs are kept in memory only."""
import concurrent.futures
import http.client
import math
import os
from pathlib import Path
import re
import ssl
import tempfile
import threading
import time
from dataclasses import dataclass
from typing import List, Optional
from urllib.error import HTTPError, URLError
from urllib.parse import unquote, urlsplit
from urllib.request import HTTPRedirectHandler, HTTPSHandler, Request, build_opener

from video_event_logger.services.video_archive import ArchiveError, archive_kind, extract_video


class DownloadError(Exception):
    """Only user-safe messages; never include a URL or server error body."""


class DownloadCancelled(DownloadError):
    pass


class RangeUnsupported(DownloadError):
    pass


class TransientDownloadError(Exception):
    pass


@dataclass
class ResumeState:
    """Bytes already on disk for a ranged download, kept for Retry or a new link."""
    temp_path: Path
    total: int
    etag: str
    parts: List[List[int]]  # [start, end, written]

    @property
    def done(self):
        return sum(part[2] for part in self.parts)


class ResumableDownloadError(DownloadError):
    """The transfer stopped but the partial file is kept and can be continued."""

    def __init__(self, message, state):
        super().__init__(message)
        self.state = state


class LinkExpiredError(ResumableDownloadError):
    """The signed link stopped working; a new link to the same file can continue."""


NETWORK_ERRORS = (TransientDownloadError, URLError, TimeoutError, ConnectionError,
                  http.client.HTTPException, ssl.SSLEOFError)


def validate_download_url(url):
    try:
        parsed = urlsplit(url)
        if (parsed.scheme not in ("https", "http") or not parsed.hostname
                or parsed.username is not None or parsed.password is not None
                or parsed.fragment or any(ch.isspace() or ord(ch) < 32 for ch in url)):
            raise ValueError()
        if parsed.scheme != "https" and parsed.hostname not in ("localhost", "127.0.0.1", "::1"):
            raise ValueError()
        parsed.port
    except ValueError:
        raise DownloadError("Paste a complete HTTPS download link, including its signed query parameters.") from None
    return url


ARCHIVE_SUFFIXES = (".tar.gz", ".tgz", ".zip", ".tar")


def link_kind(url):
    """Best guess from the link alone: "video", "archive" or "unknown"."""
    try:
        path = unquote(urlsplit(url).path).lower()
    except ValueError:
        return "unknown"
    if path.endswith(ARCHIVE_SUFFIXES):
        return "archive"
    if path.endswith((".mp4", ".mkv")):
        return "video"
    return "unknown"


def link_format(url):
    """Short label for the link's file type, e.g. "MP4", "ZIP", "TAR.GZ" or ""."""
    try:
        path = unquote(urlsplit(url).path).lower()
    except ValueError:
        return ""
    for suffix in (".tar.gz", ".tgz", ".zip", ".tar", ".mp4", ".mkv"):
        if path.endswith(suffix):
            return "TAR.GZ" if suffix == ".tgz" else suffix[1:].upper()
    return ""


def suggested_video_name(url):
    try:
        name = unquote(urlsplit(url).path.rsplit("/", 1)[-1])
    except ValueError:
        return "video.mp4"
    name = re.sub(r'[<>:"/\\|?*\x00-\x1f\x7f]', "_", name).strip(" .")
    for archive_suffix in (".tar.gz", ".tgz", ".zip", ".tar"):
        if name.lower().endswith(archive_suffix):
            name = name[:-len(archive_suffix)]
            if Path(name).suffix.lower() not in (".mp4", ".mkv"):
                name += ".mp4"
            break
    if Path(name).suffix.lower() not in (".mp4", ".mkv"):
        return "video.mp4"
    if len(name) > 180:
        name = name[:170] + Path(name).suffix
    if name.split(".", 1)[0].upper() in {"CON", "PRN", "AUX", "NUL", *("COM%d" % i for i in range(1, 10)), *("LPT%d" % i for i in range(1, 10))}:
        name = "_" + name
    return name


class SafeRedirects(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        validate_download_url(newurl)
        if urlsplit(req.full_url).scheme == "https" and urlsplit(newurl).scheme != "https":
            raise DownloadError("The server redirected the download to an insecure address.")
        return super().redirect_request(req, fp, code, msg, headers, newurl)


class VideoDownloader:
    BLOCK_SIZE = 256 * 1024
    MIN_PART_SIZE = 1024 * 1024
    TIMEOUT = 15
    # Network loss (sleep, Wi-Fi switch, VPN reconnect) is waited out instead of
    # failing: retries back off up to MAX_BACKOFF and give up only after
    # NETWORK_WAIT_LIMIT seconds without any progress while the computer is awake.
    BACKOFF_BASE = 1.0
    MAX_BACKOFF = 30.0
    NETWORK_WAIT_LIMIT = 30 * 60

    def __init__(self, url, destination, connections=8, progress=None, cancel=None, tls_context=None, stage=None,
                 waiting=None, resume=None, retry_now=None):
        self.url = validate_download_url(url)
        self.destination = Path(destination).absolute()
        self.connections = max(1, min(16, int(connections)))
        self.stage = stage or (lambda text: None)
        self.content_type = ""
        self.extracted_path = None
        self.progress = progress or (lambda done, total, speed, connections: None)
        self.cancel = cancel or threading.Event()
        self.abort = threading.Event()
        self.tls_context = tls_context or ssl.create_default_context()
        self.lock = threading.Lock()
        self.done = 0
        self.total = None
        self.active_connections = 1
        self.started = time.monotonic()
        self.last_report = 0
        self.etag = None
        self.temp_path = None
        self.parts = None  # type: Optional[List[List[int]]]
        self.keep_partial = False
        self.resume = resume
        self.waiting = waiting or (lambda retry_in: None)
        self.retry_now = retry_now or threading.Event()
        self.original_destination = self._destination_stamp()

    def _destination_stamp(self):
        try:
            info = self.destination.lstat()
            return info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns
        except FileNotFoundError:
            return None

    def _check_cancel(self):
        if self.cancel.is_set() or self.abort.is_set():
            raise DownloadCancelled("Download cancelled.")

    def _report(self, amount=0, force=False):
        with self.lock:
            self.done += amount
            now = time.monotonic()
            if force or now - self.last_report >= 0.1:
                self.last_report = now
                self.progress(self.done, self.total, self.done / max(0.1, now - self.started), self.active_connections)

    def _open(self, start=None, end=None):
        self._check_cancel()
        headers = {"Accept-Encoding": "identity", "User-Agent": "VideoEventLogger"}
        if start is not None:
            headers["Range"] = "bytes=%d-%d" % (start, end)
        if self.etag:
            headers["If-Match"] = self.etag
        opener = build_opener(SafeRedirects(), HTTPSHandler(context=self.tls_context))
        try:
            response = opener.open(Request(self.url, headers=headers, method="GET"), timeout=self.TIMEOUT)
        except HTTPError as exc:
            status = exc.code
            exc.close()
            if status in (408, 429, 500, 502, 503, 504):
                raise TransientDownloadError() from None
            if status in (401, 403):
                raise DownloadError("Access denied (HTTP %d). The link may have expired or require different signed headers. Request a new download link." % status) from None
            if status == 412:
                raise DownloadError("The video changed on the server. Request a new link and try again.") from None
            raise DownloadError("The server could not provide the video (HTTP %d)." % status) from None
        if response.headers.get("Content-Encoding", "identity").lower() not in ("identity", "gzip", "x-gzip"):
            response.close()
            raise DownloadError("The server returned an unsupported content encoding.")
        if self.etag and response.headers.get("ETag") != self.etag:
            response.close()
            raise DownloadError("The video changed on the server. The incomplete download was discarded.")
        content_type = response.headers.get("Content-Type", "").split(";", 1)[0].lower()
        self.content_type = content_type
        if content_type in ("text/html", "text/xml", "application/xml", "application/json"):
            response.close()
            raise DownloadError("The link returned a document or error page instead of a video or archive.")
        return response

    @staticmethod
    def _length(response):
        value = response.headers.get("Content-Length")
        if value is None:
            return None
        if not value.isdigit():
            raise DownloadError("The server returned an invalid file size.")
        return int(value)

    @staticmethod
    def _range(response):
        value = response.headers.get("Content-Range", "")
        match = re.fullmatch(r"bytes (\d+)-(\d+)/(\d+)", value)
        if not match:
            raise DownloadError("The server returned an invalid byte range.")
        return tuple(map(int, match.groups()))

    def _wait_before_retry(self, failures):
        """Sleep with backoff; returns early on cancel, Retry now, or wake from sleep."""
        delay = min(self.MAX_BACKOFF, self.BACKOFF_BASE * (2 ** max(0, failures - 1)))
        self.waiting(delay)
        wall_start, deadline = time.time(), time.monotonic() + delay
        while True:
            self._check_cancel()
            if self.retry_now.is_set():
                self.retry_now.clear()
                return
            remaining = deadline - time.monotonic()
            # Monotonic time stops while the computer sleeps; wall time does not.
            if remaining <= 0 or time.time() - wall_start > delay + 5:
                return
            self.cancel.wait(min(0.25, remaining))

    def _retrying(self, operation, progress_marker):
        """Run operation until it succeeds, waiting out network loss."""
        failures, stalled_since = 0, None
        while True:
            self._check_cancel()
            before = progress_marker()
            try:
                return operation()
            except NETWORK_ERRORS:
                if self.cancel.is_set() or self.abort.is_set():
                    raise DownloadCancelled("Download cancelled.") from None
                if progress_marker() > before:
                    failures, stalled_since = 0, None
                failures += 1
                now = time.monotonic()
                stalled_since = stalled_since or now
                if now - stalled_since > self.NETWORK_WAIT_LIMIT:
                    raise TransientDownloadError() from None
                self._wait_before_retry(failures)

    def _single(self, response):
        if response.status != 200:
            raise DownloadError("The server did not return a complete video.")
        self.total = self._length(response)
        self.active_connections = 1
        self.done = 0
        self.started = time.monotonic()
        self._report(force=True)
        with self.temp_path.open("wb") as output:
            while True:
                self._check_cancel()
                data = response.read(self.BLOCK_SIZE)
                if not data:
                    break
                if self.total is not None and self.done + len(data) > self.total:
                    raise DownloadError("The server sent more bytes than expected.")
                output.write(data)
                self._report(len(data))
            if self.total is not None and self.done != self.total:
                raise TransientDownloadError()
            if self.done == 0:
                raise DownloadError("The video is empty.")
            output.flush()
            os.fsync(output.fileno())
        self.total = self.done

    def _single_with_retries(self, initial=None):
        pending = [initial]

        def attempt():
            response = pending[0] if pending[0] is not None else self._open()
            pending[0] = None
            with response:
                self._single(response)

        self._retrying(attempt, lambda: self.done)

    def _part(self, part):
        start, end = part[0], part[1]

        def attempt():
            if part[2] == end - start + 1:
                return
            with self._open(start + part[2], end) as response:
                if response.status == 200:
                    raise RangeUnsupported("The server ignored a byte range.")
                if response.status != 206 or self._range(response) != (start + part[2], end, self.total):
                    raise DownloadError("A downloaded part has an unexpected byte range.")
                length = self._length(response)
                remaining = end - start + 1 - part[2]
                if length is not None and length != remaining:
                    raise DownloadError("A downloaded part has an unexpected size.")
                with self.temp_path.open("r+b") as output:
                    output.seek(start + part[2])
                    while remaining:
                        self._check_cancel()
                        data = response.read(min(self.BLOCK_SIZE, remaining))
                        if not data:
                            raise TransientDownloadError()
                        output.write(data)
                        part[2] += len(data)
                        remaining -= len(data)
                        self._report(len(data))
                    output.flush()
                    if response.read(1):
                        raise DownloadError("A downloaded part contains extra bytes.")

        self._retrying(attempt, lambda: part[2])

    def _split_parts(self):
        count = min(self.connections, max(1, math.ceil(self.total / self.MIN_PART_SIZE)))
        return [[i * self.total // count, (i + 1) * self.total // count - 1, 0] for i in range(count)]

    def _resume_state(self):
        if self.resume is not None and self.etag is None:
            return self.resume
        return ResumeState(self.temp_path, self.total, self.etag, self.parts)

    def _parallel(self, fresh=True):
        if fresh:
            self.parts = self._split_parts()
            with self.temp_path.open("wb") as output:
                output.truncate(self.total)
        pending = [part for part in self.parts if part[2] < part[1] - part[0] + 1]
        self.active_connections = max(1, len(pending))
        self.done = sum(part[2] for part in self.parts)
        self.started = time.monotonic()
        self._report(force=True)
        if pending:
            with concurrent.futures.ThreadPoolExecutor(max_workers=len(pending), thread_name_prefix="video-download") as pool:
                futures = [pool.submit(self._part, part) for part in pending]
                try:
                    for future in concurrent.futures.as_completed(futures):
                        future.result()
                except BaseException:
                    self.abort.set()
                    for future in futures:
                        future.cancel()
                    raise
        with self.temp_path.open("r+b") as output:
            os.fsync(output.fileno())

    def _prepare_video(self):
        self.stage("Checking downloaded file…")
        self._check_cancel()
        expected = urlsplit(self.url).path.lower().endswith((".zip", ".tar", ".tar.gz", ".tgz")) or self.content_type in (
            "application/zip", "application/x-zip-compressed", "application/x-tar", "application/gzip", "application/x-gzip",
        )
        try:
            kind = archive_kind(self.temp_path, expected)
            if kind is None:
                return self.temp_path
            self.stage("Unpacking archive…")
            fd, name = tempfile.mkstemp(prefix=".video-extract-", suffix=".part", dir=self.destination.parent)
            os.close(fd)
            self.extracted_path = Path(name)
            last_report = 0.0
            def extraction_progress(done, total):
                nonlocal last_report
                now = time.monotonic()
                if done in (0, total) or now - last_report >= 0.1:
                    last_report = now
                    self.progress(done, total, 0.0, 0)
            suffix = extract_video(kind, self.temp_path, self.extracted_path, self._check_cancel, extraction_progress)
            self._check_cancel()
            if self.destination.suffix.lower() != suffix:
                # Preserve the actual format, without extending overwrite approval
                # from the chosen filename to a different existing file.
                self.destination = self.destination.with_suffix(suffix)
                if self._destination_stamp() is not None:
                    raise DownloadError("A file with the extracted video's extension already exists. Choose another destination filename.")
                self.original_destination = None
            return self.extracted_path
        except ArchiveError as exc:
            raise DownloadError(str(exc)) from None

    def _probe(self):
        holder = []

        def attempt():
            holder.append(self._open(0, 0))

        self._retrying(attempt, lambda: 0)
        return holder[0]

    def _read_probe(self, response):
        with response:
            if response.status != 206:
                raise DownloadError("The server did not return downloadable video data.")
            start, end, total = self._range(response)
            if (start, end) != (0, 0) or total < 1:
                raise DownloadError("The server returned an invalid probe range.")
            if len(response.read(2)) != 1:
                raise DownloadError("The server returned an incomplete probe range.")
            tag = response.headers.get("ETag", "")
            return total, (tag if tag.startswith('"') and tag.endswith('"') else None)

    def _resume_from(self, state):
        """Continue a kept partial file, possibly through a new link to the same file."""
        if not state.temp_path.is_file():
            raise DownloadError("The partially downloaded data is gone. Start the download again.")
        self.temp_path = state.temp_path
        self.total, self.etag, self.parts = state.total, None, state.parts
        self.done = state.done
        response = self._probe()
        if response.status == 200:
            response.close()
            self._stop_resumable("This link cannot continue a partial download. Paste a direct link to the same file.", LinkExpiredError)
        total, etag = self._read_probe(response)
        if total != state.total or (etag and etag != state.etag):
            self.etag = state.etag
            self._stop_resumable("The new link points to a different file. Paste a link to the same video or archive.", LinkExpiredError)
        self.etag = state.etag
        self._parallel(fresh=False)

    def _transfer(self):
        if self.resume is not None:
            self._resume_from(self.resume)
            return
        fd, name = tempfile.mkstemp(prefix=".video-download-", suffix=".part", dir=self.destination.parent)
        os.close(fd)
        self.temp_path = Path(name)
        response = self._probe()
        if response.status == 200:
            self._single_with_retries(response)
            return
        self.total, self.etag = self._read_probe(response)
        if not self.etag:
            self._single_with_retries()
            return
        try:
            self._parallel()
        except RangeUnsupported:
            self.abort.clear()
            self.parts = None
            self._single_with_retries()

    def _can_resume(self):
        return self.parts is not None and self.temp_path is not None and self.done > 0

    def _stop_resumable(self, message, error_type=ResumableDownloadError):
        self.keep_partial = True
        raise error_type(message, self._resume_state()) from None

    def run(self):
        try:
            self._check_cancel()
            try:
                self._transfer()
            except NETWORK_ERRORS:
                if self._can_resume():
                    self._stop_resumable("The connection was lost for too long. Downloaded data is kept; press Retry when you are back online.")
                raise
            except DownloadError as exc:
                if (not isinstance(exc, (DownloadCancelled, ResumableDownloadError))
                        and str(exc).startswith("Access denied") and self._can_resume()):
                    self._stop_resumable(
                        "The link expired or was revoked. Downloaded data is kept: paste a new link to the same file to continue.",
                        LinkExpiredError,
                    )
                raise
            self._check_cancel()
            completed_path = self._prepare_video()
            self._check_cancel()
            if self._destination_stamp() != self.original_destination:
                raise DownloadError("The destination changed during the download. Choose another filename and try again.")
            if self.original_destination is None:
                # Atomically publish without replacing a file created in the meantime.
                os.link(completed_path, self.destination)
                completed_path.unlink()
            else:
                os.replace(completed_path, self.destination)
            if self.extracted_path is None:
                self._report(force=True)
            return self.destination
        except DownloadError:
            raise
        except NETWORK_ERRORS:
            raise DownloadError("The connection failed. Check your network and try again.") from None
        except OSError:
            raise DownloadError("Could not save the video. Check free disk space, folder permissions, and the destination filename.") from None
        finally:
            kept = self.temp_path if self.keep_partial else None
            for temporary in (self.temp_path, self.extracted_path):
                if temporary is not None and temporary != kept:
                    temporary.unlink(missing_ok=True)

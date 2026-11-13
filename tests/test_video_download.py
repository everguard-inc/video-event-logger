import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import re
import socket
import tempfile
import threading
import time
import unittest

from video_event_logger.services.video_download import (
    DownloadCancelled, DownloadError, LinkExpiredError, VideoDownloader,
    suggested_video_name, validate_download_url,
)


class FixtureServer(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self):
        super().__init__(("127.0.0.1", 0), FixtureHandler)
        self.payload = bytes(range(251)) * 25000  # About 6 MiB, nonuniform at range boundaries.
        self.requests = []
        self.lock = threading.Lock()
        self.active = 0
        self.maximum_active = 0
        self.dropped = False
        self.transient = False
        self.outage_until = 0.0
        self.outage_done = False
        self.expired = False
        self.streamed = 0


class FixtureHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, *args):
        pass

    def do_HEAD(self):
        self.send_error(405)

    def do_GET(self):
        server = self.server
        mode = self.path.split("?", 1)[0]
        requested = self.headers.get("Range")
        probe = requested == "bytes=0-0"
        with server.lock:
            server.requests.append((self.path, requested, self.headers.get("If-Match")))
            server.active += 1
            server.maximum_active = max(server.maximum_active, server.active)
        try:
            if mode == "/expired" or (mode == "/expire-mid" and server.expired):
                self.send_error(403, "secret-signature-must-not-appear")
                return
            if mode == "/outage" and time.monotonic() < server.outage_until:
                # Network gone, like right after the laptop wakes up.
                self.connection.shutdown(socket.SHUT_RDWR)
                self.close_connection = True
                return
            if mode == "/transient" and not server.transient:
                server.transient = True
                self.send_error(503)
                return
            if mode == "/redirect":
                self.send_response(307)
                self.send_header("Location", "/video?token=secret")
                self.send_header("Content-Length", "0")
                self.end_headers()
                return
            use_range = requested and mode not in ("/single", "/unknown", "/html") and not (mode == "/fallback" and not probe)
            start, end = (0, len(server.payload) - 1)
            if use_range:
                start, end = map(int, re.fullmatch(r"bytes=(\d+)-(\d+)", requested).groups())
            body = server.payload[start:end+1]
            self.send_response(206 if use_range else 200)
            self.send_header("Content-Type", "text/html" if mode == "/html" else "video/mp4")
            if mode != "/noetag":
                etag = '"other-file"' if mode == "/other" else '"fixture"'
                self.send_header("ETag", '"changed"' if mode == "/changed" and not probe else etag)
            if mode != "/unknown":
                self.send_header("Content-Length", str(len(body)))
            else:
                self.send_header("Connection", "close")
                self.close_connection = True
            if use_range:
                self.send_header("Content-Range", "bytes %d-%d/%d" % (start + (1 if mode == "/bad-range" and not probe else 0), end, len(server.payload)))
            self.end_headers()
            if probe:
                self.wfile.write(body)
                return
            with server.lock:
                drop = mode == "/drop" and not server.dropped
                if drop:
                    server.dropped = True
            limit = 512 * 1024 if drop else len(body)
            for offset in range(0, limit, 65536):
                self.wfile.write(body[offset:min(offset+65536, limit)])
                self.wfile.flush()
                time.sleep(0.008)
                if mode in ("/outage", "/expire-mid"):
                    with server.lock:
                        server.streamed += 65536
                        cut = server.streamed > 2 * 1024 * 1024 and not server.outage_done
                        if cut:
                            server.outage_done = True
                            if mode == "/outage":
                                server.outage_until = time.monotonic() + 1.5
                            else:
                                server.expired = True
                    if cut:
                        self.connection.shutdown(socket.SHUT_RDWR)
                        self.close_connection = True
                        return
            if drop:
                self.connection.shutdown(socket.SHUT_RDWR)
                self.connection.close()
                self.close_connection = True
        except (BrokenPipeError, ConnectionResetError, OSError):
            pass
        finally:
            with server.lock:
                server.active -= 1


class VideoDownloadTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = FixtureServer()
        cls.server_thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.server_thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.server_thread.join()

    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.target = self.root / "download.mp4"
        with self.server.lock:
            self.server.requests.clear()
            self.server.maximum_active = 0
            self.server.dropped = False
            self.server.transient = False
            self.server.outage_until = 0.0
            self.server.outage_done = False
            self.server.expired = False
            self.server.streamed = 0

    def downloader(self, mode="video", **kwargs):
        url = "http://127.0.0.1:%d/%s?X-Amz-Signature=secret%%2Bsignature&other=a%%2Fb" % (self.server.server_port, mode)
        return VideoDownloader(url, self.target, **kwargs)

    def assert_complete(self):
        self.assertEqual(hashlib.sha256(self.target.read_bytes()).digest(), hashlib.sha256(self.server.payload).digest())
        self.assertEqual(list(self.root.glob("*.part")), [])

    def test_parallel_ranges_match_source_and_keep_signed_query_unchanged(self):
        reports = []
        downloader = self.downloader(progress=lambda *args: reports.append(args))
        downloader.run()
        self.assert_complete()
        self.assertGreater(self.server.maximum_active, 1)
        parts = [request for request in self.server.requests if request[1] != "bytes=0-0"]
        self.assertTrue(all(request[2] == '"fixture"' for request in parts))
        self.assertTrue(all("X-Amz-Signature=secret%2Bsignature&other=a%2Fb" in request[0] for request in self.server.requests))
        self.assertEqual(reports[-1][0:2], (len(self.server.payload), len(self.server.payload)))
        self.assertLessEqual(reports[-1][3], 8)

    def test_single_stream_fallback_and_unknown_length(self):
        for mode in ("single", "unknown", "noetag", "fallback"):
            with self.subTest(mode=mode):
                downloader = self.downloader(mode)
                downloader.run()
                self.assert_complete()
                self.assertEqual(downloader.active_connections, 1)

    def test_retry_resumes_a_broken_range(self):
        downloader = self.downloader("drop")
        downloader.run()
        self.assert_complete()
        self.assertTrue(self.server.dropped)
        self.assertGreater(len(self.server.requests), downloader.active_connections + 1)

    def test_network_outage_is_waited_out_and_resumes_without_refetching(self):
        downloader = self.downloader("outage", connections=4)
        downloader.BACKOFF_BASE = 0.1
        waits = []
        downloader.waiting = waits.append
        downloader.run()
        self.assert_complete()
        self.assertTrue(waits, "the downloader should report waiting for the network")
        # Every byte is fetched about once: parts continue where they stopped.
        self.assertLess(self.server.streamed, len(self.server.payload) * 1.3)

    def test_expired_link_keeps_partial_data_and_a_new_link_continues(self):
        downloader = self.downloader("expire-mid", connections=4)
        downloader.BACKOFF_BASE = 0.05
        with self.assertRaises(LinkExpiredError) as caught:
            downloader.run()
        state = caught.exception.state
        self.assertTrue(state.temp_path.is_file())
        self.assertGreater(state.done, 0)
        self.assertFalse(self.target.exists())
        kept = state.done
        with self.server.lock:
            self.server.requests.clear()
        resumed = self.downloader("video", connections=4, resume=state)
        resumed.run()
        self.assert_complete()
        ranges = [r for _, r, _ in self.server.requests if r and r != "bytes=0-0"]
        fetched = sum(int(b) - int(a) + 1 for a, b in (re.fullmatch(r"bytes=(\d+)-(\d+)", r).groups() for r in ranges))
        self.assertEqual(fetched, len(self.server.payload) - kept)

    def test_new_link_to_a_different_file_is_refused_and_keeps_partial(self):
        downloader = self.downloader("expire-mid", connections=2)
        downloader.BACKOFF_BASE = 0.05
        with self.assertRaises(LinkExpiredError) as caught:
            downloader.run()
        state = caught.exception.state
        with self.assertRaisesRegex(DownloadError, "different file"):
            self.downloader("other", resume=state).run()
        state.temp_path.unlink()

    def test_cancel_while_waiting_for_network_stops_quickly(self):
        downloader = self.downloader("outage", connections=2)
        downloader.BACKOFF_BASE = 5.0
        downloader.waiting = lambda retry_in: downloader.cancel.set()
        started = time.monotonic()
        with self.assertRaises(DownloadCancelled):
            downloader.run()
        self.assertLess(time.monotonic() - started, 4)
        self.assertEqual(list(self.root.glob("*.part")), [])

    def test_transient_probe_failure_is_retried(self):
        self.downloader("transient").run()
        self.assert_complete()
        self.assertTrue(self.server.transient)

    def test_invalid_range_or_changed_object_does_not_replace_existing_file(self):
        self.target.write_bytes(b"existing video")
        for mode in ("bad-range", "changed", "expired", "html"):
            with self.subTest(mode=mode):
                with self.assertRaises(DownloadError) as error:
                    self.downloader(mode).run()
                self.assertNotIn("secret", str(error.exception))
                self.assertEqual(self.target.read_bytes(), b"existing video")
                self.assertEqual(list(self.root.glob("*.part")), [])

    def test_cancellation_leaves_no_partial_and_preserves_destination(self):
        self.target.write_bytes(b"original")
        cancel = threading.Event()
        def progress(done, *args):
            if done:
                cancel.set()
        with self.assertRaises(DownloadCancelled):
            self.downloader(progress=progress, cancel=cancel).run()
        self.assertEqual(self.target.read_bytes(), b"original")
        self.assertEqual(list(self.root.glob("*.part")), [])

    def test_destination_created_during_download_is_not_overwritten(self):
        def progress(done, *args):
            if done and not self.target.exists():
                self.target.write_bytes(b"someone else's file")
        with self.assertRaises(DownloadError):
            self.downloader(progress=progress).run()
        self.assertEqual(self.target.read_bytes(), b"someone else's file")
        self.assertEqual(list(self.root.glob("*.part")), [])

    def test_redirect_and_explicit_single_connection(self):
        self.downloader("redirect", connections=1).run()
        self.assert_complete()

    def test_downloaded_archive_is_unpacked_after_http_transfer(self):
        import io
        import tarfile
        import zipfile
        video = self.server.payload
        try:
            for kind in ("zip", "tar.gz"):
                buffer = io.BytesIO()
                if kind == "zip":
                    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_STORED) as archive:
                        archive.writestr("folder/clip.mp4", video)
                else:
                    with tarfile.open(fileobj=buffer, mode="w:gz") as archive:
                        entry = tarfile.TarInfo("folder/clip.mp4")
                        entry.size = len(video)
                        archive.addfile(entry, io.BytesIO(video))
                self.server.payload = buffer.getvalue()
                # Deliberately use a URL without an archive suffix and a misleading
                # video content type: detection must inspect the downloaded bytes.
                self.downloader().run()
                self.assertEqual(hashlib.sha256(self.target.read_bytes()).digest(), hashlib.sha256(video).digest())
                self.assertEqual(list(self.root.iterdir()), [self.target])
        finally:
            self.server.payload = video

    def test_url_validation_and_filename_never_include_signature(self):
        for url in ("file:///tmp/a.mp4", "https://user:password@example.org/a", "https://example.org/a\n", "http://example.org/a", "https://example.org:invalid/a"):
            with self.subTest(url=url), self.assertRaises(DownloadError):
                validate_download_url(url)
        self.assertEqual(suggested_video_name("https://bucket/key/my%20video.mkv?X-Amz-Signature=secret"), "my video.mkv")
        self.assertEqual(suggested_video_name("https://bucket/key?response-content-disposition=secret"), "video.mp4")
        self.assertNotIn("/", suggested_video_name("https://bucket/%2Fetc%2Fvideo.mp4"))

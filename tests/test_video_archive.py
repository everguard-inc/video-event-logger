import gzip
import io
from pathlib import Path
import stat
import tarfile
import tempfile
import threading
import unittest
from unittest.mock import patch
import zipfile

from video_event_logger.services.video_download import DownloadCancelled, DownloadError, VideoDownloader, suggested_video_name


VIDEO = b"\x00\x00\x00\x18ftypisom" + bytes(range(251)) * 4000


def make_archive(kind, entries):
    output = io.BytesIO()
    if kind == "zip":
        with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as archive:
            for name, data in entries:
                archive.writestr(name, data)
    else:
        with tarfile.open(fileobj=output, mode="w:gz" if kind == "tar.gz" else "w") as archive:
            for name, data in entries:
                info = tarfile.TarInfo(name)
                info.size = len(data)
                archive.addfile(info, io.BytesIO(data))
    return output.getvalue()


class Response(io.BytesIO):
    def __init__(self, payload, start, end):
        selected = payload if start is None else payload[start:end + 1]
        super().__init__(selected)
        self.status = 200 if start is None else 206
        self.headers = {"ETag": '"fixture"', "Content-Length": str(len(selected))}
        if start is not None:
            self.headers["Content-Range"] = "bytes %d-%d/%d" % (start, end, len(payload))


class PayloadDownloader(VideoDownloader):
    def __init__(self, payload, destination, **kwargs):
        self.payload = payload
        super().__init__("https://example.org/object?X-Amz-Signature=secret", destination, **kwargs)

    def _open(self, start=None, end=None):
        self._check_cancel()
        return Response(self.payload, start, end)


class VideoArchiveTest(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.target = self.root / "saved.mp4"

    def assert_no_temporary_files(self):
        self.assertEqual(list(self.root.glob(".*.part")), [])

    def test_supported_archives_extract_single_nested_video_and_remove_archive(self):
        for kind in ("zip", "tar", "tar.gz"):
            with self.subTest(kind=kind):
                stages = []
                reports = []
                payload = make_archive(kind, [("readme.txt", b"notes"), ("folder/clip.MP4", VIDEO)])
                result = PayloadDownloader(payload, self.target, stage=stages.append, progress=lambda *args: reports.append(args)).run()
                self.assertEqual(result, self.target)
                self.assertEqual(self.target.read_bytes(), VIDEO)
                self.assertIn("Unpacking archive…", stages)
                self.assertTrue(any(report[3] == 0 for report in reports))
                self.assert_no_temporary_files()
                self.assertEqual(list(self.root.iterdir()), [self.target])

    def test_actual_extension_is_preserved_without_overwriting_different_file(self):
        self.target.write_bytes(b"original mp4")
        payload = make_archive("zip", [("nested/movie.mkv", VIDEO)])
        other = self.target.with_suffix(".mkv")
        result = PayloadDownloader(payload, self.target).run()
        self.assertEqual(result, other)
        self.assertEqual(other.read_bytes(), VIDEO)
        self.assertEqual(self.target.read_bytes(), b"original mp4")
        other.write_bytes(b"existing mkv")
        with self.assertRaisesRegex(DownloadError, "already exists"):
            PayloadDownloader(payload, self.target).run()
        self.assertEqual(other.read_bytes(), b"existing mkv")
        self.assert_no_temporary_files()

    def test_zero_or_multiple_videos_preserve_existing_destination(self):
        self.target.write_bytes(b"original")
        for kind in ("zip", "tar", "tar.gz"):
            for entries in ([("readme.txt", b"text")], [("one.mp4", VIDEO), ("two.mkv", VIDEO)]):
                with self.subTest(kind=kind, count=len(entries)):
                    with self.assertRaises(DownloadError):
                        PayloadDownloader(make_archive(kind, entries), self.target).run()
                    self.assertEqual(self.target.read_bytes(), b"original")
                    self.assert_no_temporary_files()

    def test_unsafe_video_paths_never_escape_destination(self):
        for kind in ("zip", "tar", "tar.gz"):
            for name in ("../escaped.mp4", "/tmp/escaped.mp4", "C:\\escaped.mp4", "folder/../../escaped.mp4"):
                with self.subTest(kind=kind, name=name), self.assertRaisesRegex(DownloadError, "unsafe"):
                    PayloadDownloader(make_archive(kind, [(name, VIDEO)]), self.target).run()
                self.assertEqual(list(self.root.iterdir()), [])

    def test_archive_links_are_not_followed(self):
        for kind in ("zip", "tar"):
            output = io.BytesIO()
            if kind == "zip":
                with zipfile.ZipFile(output, "w") as archive:
                    info = zipfile.ZipInfo("link.mp4")
                    info.create_system = 3
                    info.external_attr = (stat.S_IFLNK | 0o777) << 16
                    archive.writestr(info, "../../secret")
            else:
                with tarfile.open(fileobj=output, mode="w") as archive:
                    info = tarfile.TarInfo("link.mp4")
                    info.type = tarfile.SYMTYPE
                    info.linkname = "../../secret"
                    archive.addfile(info)
            with self.subTest(kind=kind), self.assertRaisesRegex(DownloadError, "regular"):
                PayloadDownloader(output.getvalue(), self.target).run()
            self.assertEqual(list(self.root.iterdir()), [])

    def test_zip_metadata_files_are_ignored(self):
        payload = make_archive("zip", [("__MACOSX/._movie.mp4", b"metadata"), ("movie.mp4", VIDEO)])
        PayloadDownloader(payload, self.target).run()
        self.assertEqual(self.target.read_bytes(), VIDEO)

    def test_cancel_during_extraction_removes_both_temporary_files(self):
        self.target.write_bytes(b"original")
        cancel = threading.Event()
        def progress(done, total, speed, connections):
            if connections == 0 and done > 0:
                cancel.set()
        with self.assertRaises(DownloadCancelled):
            PayloadDownloader(make_archive("zip", [("clip.mp4", VIDEO)]), self.target, cancel=cancel, progress=progress).run()
        self.assertEqual(self.target.read_bytes(), b"original")
        self.assert_no_temporary_files()

    def test_corrupt_zip_and_truncated_or_invalid_gzip_are_rejected(self):
        output = io.BytesIO()
        with zipfile.ZipFile(output, "w", zipfile.ZIP_STORED) as archive:
            archive.writestr("clip.mp4", VIDEO)
        damaged_zip = bytearray(output.getvalue())
        damaged_zip[damaged_zip.index(VIDEO[:20]) + 30] ^= 0xFF
        gzip_tar = make_archive("tar.gz", [("clip.mp4", VIDEO)])
        bad_crc = bytearray(gzip_tar)
        bad_crc[-8] ^= 0xFF
        for payload in (bytes(damaged_zip), gzip_tar[:-8], bytes(bad_crc), b"PK\x03\x04broken", gzip.compress(b"not a tar archive")):
            with self.subTest(size=len(payload)), self.assertRaises(DownloadError):
                PayloadDownloader(payload, self.target).run()
            self.assertFalse(self.target.exists())
            self.assert_no_temporary_files()

    def test_insufficient_space_preserves_original(self):
        self.target.write_bytes(b"original")
        payload = make_archive("zip", [("clip.mp4", VIDEO)])
        from collections import namedtuple
        Usage = namedtuple("Usage", "total used free")
        with patch("video_event_logger.services.video_archive.shutil.disk_usage", return_value=Usage(100, 100, 0)):
            with self.assertRaisesRegex(DownloadError, "disk space"):
                PayloadDownloader(payload, self.target).run()
        self.assertEqual(self.target.read_bytes(), b"original")
        self.assert_no_temporary_files()

    def test_raw_video_is_unchanged_even_when_url_says_zip(self):
        downloader = PayloadDownloader(VIDEO, self.target)
        downloader.url = "https://example.org/misleading.zip"
        downloader.run()
        self.assertEqual(self.target.read_bytes(), VIDEO)
        self.assert_no_temporary_files()

    def test_archive_names_make_useful_video_name_suggestions(self):
        for source, expected in (("trip.zip", "trip.mp4"), ("trip.tar.gz", "trip.mp4"), ("trip.mkv.zip", "trip.mkv"), ("trip.tgz", "trip.mp4")):
            self.assertEqual(suggested_video_name("https://example.org/" + source + "?token=secret"), expected)

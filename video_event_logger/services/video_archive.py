"""Extract exactly one video into a caller-owned temporary file.

Archive member paths are never used as filesystem destinations.
"""
import gzip
import os
from pathlib import PurePosixPath, PureWindowsPath
import shutil
import stat
import tarfile
import zipfile
import zlib


class ArchiveError(Exception):
    pass


VIDEO_SUFFIXES = (".mp4", ".mkv")
MAX_MEMBERS = 10000
BLOCK_SIZE = 256 * 1024


def archive_kind(path, expected=False):
    with path.open("rb") as source:
        header = source.read(512)
    if zipfile.is_zipfile(path):
        return "zip"
    if header.startswith((b"PK\x03\x04", b"PK\x05\x06", b"PK\x07\x08")):
        raise ArchiveError("The ZIP archive is incomplete or damaged.")
    if header.startswith(b"\x1f\x8b"):
        return "tar.gz"
    if header[257:262] == b"ustar" or header == b"\0" * 512:
        return "tar"
    if len(header) == 512:
        try:
            tarfile.TarInfo.frombuf(header, "utf-8", "surrogateescape")
            return "tar"
        except tarfile.HeaderError:
            pass
    if header.startswith((b"7z\xbc\xaf\x27\x1c", b"Rar!\x1a\x07", b"BZh", b"\xfd7zXZ\x00")):
        raise ArchiveError("This archive format is not supported. Use ZIP, TAR, or TAR.GZ.")
    # A misleading URL suffix must not turn a genuine video into an archive.
    video_header = header[4:8] in (b"ftyp", b"moov", b"mdat", b"free", b"wide") or header.startswith(b"\x1aE\xdf\xa3")
    if expected and not video_header:
        raise ArchiveError("The link was expected to contain an archive, but the downloaded archive is invalid.")
    return None


def _video_suffix(name):
    name = name.replace("\\", "/")
    parts = PurePosixPath(name).parts
    if "__MACOSX" in parts or PurePosixPath(name).name.startswith("._"):
        return None
    suffix = PurePosixPath(name).suffix.lower()
    if suffix not in VIDEO_SUFFIXES:
        return None
    if name.startswith("/") or PureWindowsPath(name).drive or ".." in parts:
        raise ArchiveError("The archive contains an unsafe video path.")
    return suffix


def _copy_video(source, output_path, size, check_cancel, progress):
    if size <= 0:
        raise ArchiveError("The video inside the archive is empty.")
    if size > shutil.disk_usage(output_path.parent).free:
        raise ArchiveError("Not enough free disk space to unpack the video. Choose another folder or free some space.")
    done = 0
    progress(0, size)
    with output_path.open("wb") as output:
        while True:
            check_cancel()
            block = source.read(BLOCK_SIZE)
            if not block:
                break
            done += len(block)
            if done > size:
                raise ArchiveError("The video inside the archive has an invalid size.")
            output.write(block)
            progress(done, size)
        if done != size:
            raise ArchiveError("The video inside the archive is incomplete.")
        output.flush()
        os.fsync(output.fileno())


class _CancellableReader:
    """Check cancellation while tarfile scans/skips compressed archive contents."""
    def __init__(self, stream, check_cancel):
        self.stream = stream
        self.check_cancel = check_cancel

    def read(self, size=-1):
        self.check_cancel()
        return self.stream.read(size)

    def __getattr__(self, name):
        return getattr(self.stream, name)


def extract_video(kind, path, output_path, check_cancel, progress):
    try:
        if kind == "zip":
            return _extract_zip(path, output_path, check_cancel, progress)
        return _extract_tar(kind, path, output_path, check_cancel, progress)
    except (zipfile.BadZipFile, zipfile.LargeZipFile, tarfile.TarError, gzip.BadGzipFile, EOFError, zlib.error):
        raise ArchiveError("The archive is incomplete or damaged. Download it again or request a new archive.") from None
    except (NotImplementedError, RuntimeError):
        raise ArchiveError("The archive is encrypted or uses an unsupported compression method. Use an unencrypted ZIP, TAR, or TAR.GZ.") from None


def _extract_zip(path, output_path, check_cancel, progress):
    with zipfile.ZipFile(path) as archive:
        entries = archive.infolist()
        if len(entries) > MAX_MEMBERS:
            raise ArchiveError("The archive contains too many entries.")
        candidates = []
        for entry in entries:
            check_cancel()
            if entry.is_dir():
                continue
            suffix = _video_suffix(entry.filename)
            if suffix:
                mode = stat.S_IFMT(entry.external_attr >> 16)
                if mode not in (0, stat.S_IFREG):
                    raise ArchiveError("The video in the archive must be a regular file, not a link.")
                candidates.append((entry, suffix))
        if len(candidates) != 1:
            _wrong_video_count(len(candidates))
        entry, suffix = candidates[0]
        if entry.flag_bits & 1:
            raise ArchiveError("Password-protected archives are not supported.")
        with archive.open(entry) as source:
            _copy_video(source, output_path, entry.file_size, check_cancel, progress)
        return suffix


def _extract_tar(kind, path, output_path, check_cancel, progress):
    suffix = None
    with path.open("rb") as raw:
        compressed = gzip.GzipFile(fileobj=raw, mode="rb") if kind == "tar.gz" else raw
        try:
            source = _CancellableReader(compressed, check_cancel)
            # Stream once, then drain gzip through EOF to verify its CRC/trailer.
            with tarfile.open(fileobj=source, mode="r|") as archive:
                for index, entry in enumerate(archive):
                    check_cancel()
                    if index >= MAX_MEMBERS:
                        raise ArchiveError("The archive contains too many entries.")
                    if entry.isdir():
                        continue
                    current_suffix = _video_suffix(entry.name)
                    if not current_suffix:
                        continue
                    if not entry.isreg() or entry.issparse():
                        raise ArchiveError("The video in the archive must be a regular, non-sparse file, not a link.")
                    if suffix is not None:
                        _wrong_video_count(2)
                    suffix = current_suffix
                    with archive.extractfile(entry) as video:
                        _copy_video(video, output_path, entry.size, check_cancel, progress)
            if kind == "tar.gz":
                while source.read(BLOCK_SIZE):
                    check_cancel()
        finally:
            if compressed is not raw:
                compressed.close()
    if suffix is None:
        _wrong_video_count(0)
    return suffix


def _wrong_video_count(count):
    if count == 0:
        raise ArchiveError("The archive contains no MP4 or MKV video.")
    raise ArchiveError("The archive contains more than one video. Provide an archive with exactly one MP4 or MKV file.")

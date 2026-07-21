import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from video_event_logger.services.annotation_store import AnnotationStore


class AnnotationStoreAtomicWriteTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.directory = Path(self.temporary_directory.name)
        self.store = AnnotationStore()

    def tearDown(self) -> None:
        self.temporary_directory.cleanup()

    def test_write_json_replaces_existing_file_and_removes_temporary_file(self) -> None:
        output_path = self.directory / "sample.autosave.json"
        output_path.write_text("old content", encoding="utf-8")

        self.store._write_json(output_path, {"value": "new", "unicode": "подія"})

        self.assertEqual(
            json.loads(output_path.read_text(encoding="utf-8")),
            {"value": "new", "unicode": "подія"},
        )
        self.assertEqual(list(self.directory.glob("*.tmp")), [])

    def test_write_json_replaces_symlink_without_modifying_its_target(self) -> None:
        video_path = self.directory / "source.mp4"
        video_content = b"original video bytes"
        video_path.write_bytes(video_content)
        output_path = self.directory / "sample.autosave.json"
        try:
            output_path.symlink_to(video_path)
        except (NotImplementedError, OSError) as exc:
            self.skipTest("Symbolic links are unavailable: %s" % exc)

        self.store._write_json(output_path, {"safe": True})

        self.assertEqual(video_path.read_bytes(), video_content)
        self.assertFalse(output_path.is_symlink())
        self.assertEqual(json.loads(output_path.read_text(encoding="utf-8")), {"safe": True})

    def test_write_json_replaces_hard_link_without_modifying_video_inode(self) -> None:
        video_path = self.directory / "source.mp4"
        video_content = b"original video bytes"
        video_path.write_bytes(video_content)
        output_path = self.directory / "sample.annotations.json"
        try:
            os.link(video_path, output_path)
        except OSError as exc:
            self.skipTest("Hard links are unavailable: %s" % exc)

        self.store._write_json(output_path, {"safe": True})

        self.assertEqual(video_path.read_bytes(), video_content)
        self.assertNotEqual(os.stat(video_path).st_ino, os.stat(output_path).st_ino)
        self.assertEqual(json.loads(output_path.read_text(encoding="utf-8")), {"safe": True})

    def test_failed_replace_preserves_previous_json_and_cleans_up(self) -> None:
        output_path = self.directory / "sample.autosave.json"
        previous_content = '{"value": "previous"}\n'
        output_path.write_text(previous_content, encoding="utf-8")

        with patch(
            "video_event_logger.services.annotation_store.os.replace",
            side_effect=OSError("simulated replace failure"),
        ):
            with self.assertRaises(OSError):
                self.store._write_json(output_path, {"value": "new"})

        self.assertEqual(output_path.read_text(encoding="utf-8"), previous_content)
        self.assertEqual(list(self.directory.glob("*.tmp")), [])


if __name__ == "__main__":
    unittest.main()

import json
import tempfile
import unittest
from pathlib import Path

from PySide6.QtCore import QSettings

from video_event_logger.services.recent_files import RecentFiles


class RecentFilesTest(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.settings = QSettings(str(self.root / "prefs.ini"), QSettings.Format.IniFormat)

    def test_persists_order_deduplicates_and_limits_each_kind(self):
        history = RecentFiles(self.settings)
        for number in range(25):
            history.record("video", self.root / (str(number) + ".mp4"))
        history.record("folder", self.root)
        history.record("video", self.root / "10.mp4")
        self.settings.sync()
        restored = RecentFiles(QSettings(self.settings.fileName(), QSettings.Format.IniFormat))
        self.assertEqual(len(restored.items("video")), 20)
        self.assertEqual(restored.items("video")[0]["path"], str((self.root / "10.mp4").resolve()))
        self.assertEqual(len(restored.items("folder")), 1)

    def test_annotation_video_pair_and_clear_preserve_files(self):
        history = RecentFiles(self.settings)
        source = self.root / "shared.json"
        source.write_text("{}")
        for name in ("first.mp4", "second.mp4", "first.mp4"):
            history.record("annotations", source, self.root / name)
        self.assertEqual(len(history.items("annotations")), 2)
        self.assertTrue(history.items("annotations")[0]["video"].endswith("first.mp4"))
        history.clear()
        self.assertEqual(RecentFiles(self.settings).entries, [])
        self.assertEqual(source.read_text(), "{}")

    def test_bad_preferences_are_ignored_without_losing_valid_entries(self):
        for raw in ("invalid", "null", "{}"):
            self.settings.setValue(RecentFiles.KEY, raw)
            self.assertEqual(RecentFiles(self.settings).entries, [])
        valid = {"kind": "video", "path": str(self.root / "missing.mp4")}
        self.settings.setValue(RecentFiles.KEY, json.dumps([
            None, {"kind": "other"}, {"kind": "video", "path": 10},
            {"kind": "annotations", "path": str(self.root / "a.json")},
            {"kind": "video", "path": "relative.mp4"}, valid, valid,
        ]))
        self.assertEqual(RecentFiles(self.settings).entries, [valid])

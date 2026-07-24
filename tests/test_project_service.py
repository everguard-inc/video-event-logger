import os
import tempfile
import unittest
from pathlib import Path

from video_event_logger.application.project_service import ProjectService
from video_event_logger.models.annotation import AnnotationDocument


class ProjectServiceTest(unittest.TestCase):
    def test_update_runtime_state_keeps_current_ui_state_in_document(self) -> None:
        document = AnnotationDocument.empty("sample.mp4")
        service = ProjectService()

        service.update_runtime_state(
            document=document,
            current_event_type="event",
            current_position_seconds=12.3456,
            duration_seconds=90.0,
        )

        self.assertEqual(document.current_event_type, "event")
        self.assertEqual(document.last_playback_position_seconds, 12.3456)
        self.assertEqual(document.video_metadata.duration_seconds, 90.0)
        self.assertEqual(document.video_metadata.duration_hhmmss, "00:01:30.000")

    def test_choose_existing_source_prefers_legacy_autosave_for_migration(self) -> None:
        service = ProjectService()

        source = service.choose_existing_source(
            {
                "annotation": "annotations.json",
                "legacy_autosave": "autosave.json",
                "backup": "annotations.json.bak",
            }
        )

        self.assertEqual(source, "autosave.json")

    def test_choose_existing_source_uses_backup_when_primary_is_missing(self) -> None:
        service = ProjectService()

        source = service.choose_existing_source(
            {"backup": "annotations.json.bak"}
        )

        self.assertEqual(source, "annotations.json.bak")

    def test_newer_canonical_annotation_wins_over_stale_legacy_autosave(self) -> None:
        service = ProjectService()
        with tempfile.TemporaryDirectory() as temporary_directory:
            directory = Path(temporary_directory)
            legacy_path = directory / "sample.autosave.json"
            annotation_path = directory / "sample.annotations.json"
            legacy_path.write_text("{}", encoding="utf-8")
            annotation_path.write_text("{}", encoding="utf-8")
            os.utime(legacy_path, ns=(1_000_000_000, 1_000_000_000))
            os.utime(annotation_path, ns=(2_000_000_000, 2_000_000_000))

            source = service.choose_existing_source(
                {
                    "legacy_autosave": legacy_path,
                    "annotation": annotation_path,
                }
            )

        self.assertEqual(source, annotation_path)


if __name__ == "__main__":
    unittest.main()

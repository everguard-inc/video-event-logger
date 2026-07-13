import unittest

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

    def test_choose_existing_source_prefers_autosave(self) -> None:
        service = ProjectService()

        source = service.choose_existing_source(
            {
                "final": "final.json",
                "autosave": "autosave.json",
            }
        )

        self.assertEqual(source, "autosave.json")


if __name__ == "__main__":
    unittest.main()

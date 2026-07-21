import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from video_event_logger.application.annotation_service import AnnotationService
from video_event_logger.application.project_service import ProjectService
from video_event_logger.models.annotation import AnnotationDocument
from video_event_logger.services.annotation_store import AnnotationStore
from video_event_logger.tasks.event_logging.controller import EventLoggingController


class EventLoggingControllerEndOfVideoTest(unittest.TestCase):
    def make_controller(self, start_seconds: float = 10.0, duration_seconds: float = 255.0):
        controller = object.__new__(EventLoggingController)
        controller.is_completing_interval = False
        controller.annotation_service = Mock()
        controller.annotation_service.has_pending_interval.return_value = True
        controller.annotation_service.pending_start_seconds = start_seconds
        controller.video_player = Mock()
        controller.video_player.get_duration_seconds.return_value = duration_seconds
        controller.video_player.is_ended.return_value = False
        controller.video_player.is_playing.return_value = False
        controller._complete_pending_interval = Mock()
        return controller

    def test_vlc_ended_state_uses_exact_video_duration_as_interval_end(self) -> None:
        controller = self.make_controller(duration_seconds=255.0)
        controller.video_player.is_ended.return_value = True

        controller._finish_pending_interval_at_video_end(current_seconds=0.0)

        controller._complete_pending_interval.assert_called_once_with(255.0, automatic=True)

    def test_stopped_playback_at_end_uses_exact_video_duration(self) -> None:
        controller = self.make_controller(duration_seconds=255.0)

        controller._finish_pending_interval_at_video_end(current_seconds=254.96)

        controller._complete_pending_interval.assert_called_once_with(255.0, automatic=True)

    def test_playback_near_end_does_not_finish_interval_early(self) -> None:
        controller = self.make_controller(duration_seconds=255.0)
        controller.video_player.is_playing.return_value = True

        controller._finish_pending_interval_at_video_end(current_seconds=254.99)

        controller._complete_pending_interval.assert_not_called()

    def test_interval_cannot_auto_finish_when_start_equals_video_end(self) -> None:
        controller = self.make_controller(start_seconds=255.0, duration_seconds=255.0)
        controller.video_player.is_ended.return_value = True

        controller._finish_pending_interval_at_video_end(current_seconds=255.0)

        controller._complete_pending_interval.assert_not_called()

    def test_automatic_completion_creates_interval_with_exact_video_end(self) -> None:
        controller = object.__new__(EventLoggingController)
        controller.is_completing_interval = False
        controller.annotation_service = AnnotationService()
        document = AnnotationDocument.empty("sample.mp4")
        controller.annotation_service.set_document(document)
        controller.annotation_service.start_interval(250.25)
        controller.workspace = Mock()
        controller.workspace.show_popup_after_interval.return_value = False
        controller.video_player = Mock()
        controller._current_event_type = Mock(return_value="event")
        controller._refresh_table = Mock()
        controller._refresh_counts = Mock()
        controller._save_checkpoint = Mock()

        controller._complete_pending_interval(255.0, automatic=True)

        self.assertEqual(len(document.intervals), 1)
        self.assertEqual(document.intervals[0].start_time_seconds, 250.25)
        self.assertEqual(document.intervals[0].end_time_seconds, 255.0)
        controller.workspace.set_pending_interval_start.assert_called_once_with(None)
        controller._save_checkpoint.assert_called_once_with(
            "Interval reached the end of the video; result JSON and recovery autosave updated."
        )


class EventLoggingControllerCheckpointTest(unittest.TestCase):
    def make_controller(self) -> EventLoggingController:
        controller = object.__new__(EventLoggingController)
        controller.document = AnnotationDocument.empty("sample.mp4")
        annotation_service = AnnotationService()
        annotation_service.set_document(controller.document)
        annotation_service.start_interval(1.25)
        annotation_service.end_interval(2.5, "event", "note")
        controller.annotation_service = annotation_service
        controller.project_service = ProjectService(AnnotationStore())
        controller.video_player = Mock()
        controller.video_player.get_time_seconds.return_value = 2.5
        controller.video_player.get_duration_seconds.return_value = 10.0
        controller.active_event_type = "event"
        controller.workspace = Mock()
        controller.window = Mock()
        controller.last_result_path = None
        controller.result_save_status = "missing"
        controller.autosave_save_status = "missing"
        return controller

    def test_checkpoint_immediately_updates_result_and_recovery_json(self) -> None:
        controller = self.make_controller()
        with tempfile.TemporaryDirectory() as temporary_directory:
            data_directory = Path(temporary_directory)
            with patch(
                "video_event_logger.services.path_utils.AUTOSAVE_DIR",
                data_directory / "autosave",
            ), patch(
                "video_event_logger.services.path_utils.RESULTS_DIR",
                data_directory / "results",
            ):
                saved = controller._save_checkpoint("Both files are current.")
                autosave_path, result_path = controller.project_service.paths_for_video_name(
                    "sample.mp4"
                )
                autosave_data = json.loads(autosave_path.read_text(encoding="utf-8"))
                result_data = json.loads(result_path.read_text(encoding="utf-8"))

        self.assertTrue(saved)
        self.assertEqual(len(result_data["intervals"]), 1)
        self.assertEqual(result_data["intervals"], autosave_data["intervals"])
        self.assertFalse(result_data["is_autosave"])
        self.assertTrue(autosave_data["is_autosave"])
        self.assertEqual(controller.result_save_status, "current")
        self.assertEqual(controller.autosave_save_status, "current")
        controller.workspace.set_persistence_status.assert_called_once_with("current", "current")

    def test_syncing_loaded_work_preserves_saved_resume_position(self) -> None:
        controller = self.make_controller()
        controller.document.last_playback_position_seconds = 7.75
        with tempfile.TemporaryDirectory() as temporary_directory:
            data_directory = Path(temporary_directory)
            with patch(
                "video_event_logger.services.path_utils.AUTOSAVE_DIR",
                data_directory / "autosave",
            ), patch(
                "video_event_logger.services.path_utils.RESULTS_DIR",
                data_directory / "results",
            ):
                controller._save_checkpoint("Loaded work synced.", update_runtime=False)
                _, result_path = controller.project_service.paths_for_video_name("sample.mp4")
                result_data = json.loads(result_path.read_text(encoding="utf-8"))

        self.assertEqual(result_data["last_playback_position_seconds"], 7.75)

    @patch("video_event_logger.tasks.event_logging.controller.QMessageBox.warning")
    def test_result_failure_keeps_successful_recovery_autosave_visible(self, warning: Mock) -> None:
        controller = self.make_controller()
        controller.project_service = Mock()
        controller.project_service.save_autosave.return_value = Path("sample.autosave.json")
        controller.project_service.save_final.side_effect = OSError("disk error")

        saved = controller._save_checkpoint("Both files are current.")

        self.assertFalse(saved)
        self.assertEqual(controller.result_save_status, "failed")
        self.assertEqual(controller.autosave_save_status, "current")
        controller.workspace.set_persistence_status.assert_called_once_with("failed", "current")
        warning.assert_called_once()

    @patch("video_event_logger.tasks.event_logging.controller.QMessageBox.warning")
    def test_autosave_failure_does_not_block_result_json_update(self, warning: Mock) -> None:
        controller = self.make_controller()
        controller.project_service = Mock()
        controller.project_service.save_autosave.side_effect = OSError("disk error")
        controller.project_service.save_final.return_value = Path("sample.annotations.json")

        saved = controller._save_checkpoint("Both files are current.")

        self.assertFalse(saved)
        self.assertEqual(controller.last_result_path, Path("sample.annotations.json"))
        self.assertEqual(controller.result_save_status, "current")
        self.assertEqual(controller.autosave_save_status, "failed")
        controller.workspace.set_persistence_status.assert_called_once_with("current", "failed")
        warning.assert_called_once()


if __name__ == "__main__":
    unittest.main()

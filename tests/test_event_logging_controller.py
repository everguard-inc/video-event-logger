import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from PySide6.QtNetwork import QNetworkReply

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
            "Interval reached the end of the video and was saved."
        )
        controller.workspace.show_fullscreen_notification.assert_called_once_with(
            "Interval added",
            "success",
            False,
        )


class EventLoggingControllerPlaybackControlsTest(unittest.TestCase):
    def test_pending_event_type_marks_annotation_as_unsaved(self) -> None:
        controller = object.__new__(EventLoggingController)
        controller.active_event_type = "old"
        controller.workspace = Mock()
        controller.workspace.event_type_text.return_value = "new"
        controller.event_type_apply_timer = Mock()
        controller._set_event_type_lamp = Mock()
        controller._set_save_state = Mock()

        controller.mark_event_type_pending()

        controller._set_event_type_lamp.assert_called_once_with("pending")
        controller._set_save_state.assert_called_once_with("dirty")
        controller.event_type_apply_timer.start.assert_called_once()

    def test_failed_speed_change_restores_previous_active_button(self) -> None:
        controller = object.__new__(EventLoggingController)
        controller.current_playback_speed = 2.0
        controller.video_player = Mock()
        controller.video_player.set_rate.return_value = False
        controller.workspace = Mock()
        controller._set_status_text = Mock()

        controller._set_speed(4.0)

        controller.workspace.set_active_speed.assert_called_once_with(2.0)
        self.assertEqual(controller.current_playback_speed, 2.0)

    def test_escape_leaves_fullscreen_without_canceling_interval(self) -> None:
        controller = object.__new__(EventLoggingController)
        controller.window = Mock()
        controller.window.video_fullscreen_enabled = True
        controller.annotation_service = Mock()

        controller._hotkey_exit_fullscreen()

        controller.window.set_fullscreen.assert_called_once_with(False)
        controller.annotation_service.has_pending_interval.assert_not_called()

    def test_cancel_replaces_active_badge_with_top_status(self) -> None:
        controller = object.__new__(EventLoggingController)
        controller.window = Mock()
        controller.window.video_fullscreen_enabled = True
        controller.annotation_service = Mock()
        controller.annotation_service.has_pending_interval.return_value = True
        controller.workspace = Mock()
        controller._set_status_text = Mock()

        controller._hotkey_cancel_pending_interval()

        controller.workspace.set_pending_interval_start.assert_called_once_with(None)
        controller.workspace.show_fullscreen_notification.assert_called_once_with(
            "Interval canceled",
            "info",
            False,
        )
        controller.window.set_fullscreen.assert_not_called()

    def test_menu_rotation_updates_video_and_selected_menu_item(self) -> None:
        controller = object.__new__(EventLoggingController)
        controller.document = AnnotationDocument.empty("sample.mp4")
        controller.current_video_path = Path("sample.mp4")
        controller.video_player = Mock()
        controller.video_player.is_playing.return_value = False
        controller.video_player.set_rotation_degrees.return_value = True
        controller.video_player.rotation_degrees = 90
        controller.window = Mock()
        controller._set_status_text = Mock()

        controller.set_video_rotation(90)

        controller.video_player.set_rotation_degrees.assert_called_once_with(90)
        controller.window.set_video_rotation_degrees.assert_called_once_with(90)

    def test_fullscreen_feedback_keeps_errors_visible(self) -> None:
        self.assertEqual(
            EventLoggingController._fullscreen_feedback_appearance(
                "Annotation JSON save failed."
            ),
            ("error", True),
        )
        self.assertEqual(
            EventLoggingController._fullscreen_feedback_appearance(
                "Interval added and saved."
            ),
            ("success", False),
        )

    def test_only_error_status_is_forwarded_automatically_to_fullscreen_hud(self) -> None:
        controller = object.__new__(EventLoggingController)
        controller.workspace = Mock()

        controller._set_status_text("Interval added and saved.")
        controller.workspace.show_fullscreen_notification.assert_not_called()

        controller._set_status_text("Annotation JSON save failed.")
        controller.workspace.show_fullscreen_notification.assert_called_once_with(
            "Annotation JSON save failed.",
            "error",
            True,
        )

    def test_popup_off_start_uses_only_persistent_active_badge(self) -> None:
        controller = object.__new__(EventLoggingController)
        controller.document = AnnotationDocument.empty("sample.mp4")
        controller.current_video_path = Path("sample.mp4")
        controller.annotation_service = AnnotationService()
        controller.annotation_service.set_document(controller.document)
        controller.video_player = Mock()
        controller.video_player.get_time_seconds.return_value = 12.345
        controller.workspace = Mock()
        controller.workspace.show_popup_after_interval.return_value = False
        controller._set_status_text = Mock()

        controller.set_interval_start()

        controller.workspace.set_pending_interval_start.assert_called_once_with(12.345)
        controller.workspace.show_fullscreen_notification.assert_not_called()

    def test_popup_on_start_keeps_persistent_active_interval_badge(self) -> None:
        controller = object.__new__(EventLoggingController)
        controller.document = AnnotationDocument.empty("sample.mp4")
        controller.current_video_path = Path("sample.mp4")
        controller.annotation_service = AnnotationService()
        controller.annotation_service.set_document(controller.document)
        controller.video_player = Mock()
        controller.video_player.get_time_seconds.return_value = 12.345
        controller.workspace = Mock()
        controller.workspace.show_popup_after_interval.return_value = True
        controller._set_status_text = Mock()

        controller.set_interval_start()

        controller.workspace.set_pending_interval_start.assert_called_once_with(12.345)
        controller.workspace.show_fullscreen_notification.assert_not_called()

    def test_repeated_start_does_not_replace_active_interval_timestamp(self) -> None:
        controller = object.__new__(EventLoggingController)
        controller.document = AnnotationDocument.empty("sample.mp4")
        controller.current_video_path = Path("sample.mp4")
        controller.annotation_service = AnnotationService()
        controller.annotation_service.set_document(controller.document)
        controller.annotation_service.start_interval(12.345)
        controller.video_player = Mock()
        controller.video_player.get_time_seconds.return_value = 50.0
        controller.workspace = Mock()
        controller._set_status_text = Mock()

        controller.set_interval_start()

        self.assertEqual(controller.annotation_service.pending_start_seconds, 12.345)
        controller.video_player.get_time_seconds.assert_not_called()
        controller.workspace.set_pending_interval_start.assert_not_called()
        controller._set_status_text.assert_called_once_with(
            "Interval is already active. Press End or D to finish, or Q to cancel."
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
        controller.last_annotation_path = None
        return controller

    def test_checkpoint_immediately_updates_single_annotation_json(self) -> None:
        controller = self.make_controller()
        with tempfile.TemporaryDirectory() as temporary_directory:
            data_directory = Path(temporary_directory)
            with patch(
                "video_event_logger.services.path_utils.LEGACY_AUTOSAVE_DIR",
                data_directory / "autosave",
            ), patch(
                "video_event_logger.services.path_utils.RESULTS_DIR",
                data_directory / "results",
            ):
                saved = controller._save_checkpoint("Annotations saved.")
                result_path = controller.project_service.annotation_path_for_video_name(
                    "sample.mp4"
                )
                result_data = json.loads(result_path.read_text(encoding="utf-8"))

        self.assertTrue(saved)
        self.assertEqual(len(result_data["intervals"]), 1)
        self.assertFalse(result_data["is_autosave"])
        self.assertEqual(controller.last_annotation_path, result_path)
        self.assertEqual(
            [call.args[0] for call in controller.window.set_save_state.call_args_list],
            ["saving", "saved"],
        )
        controller.window.set_annotation_file_available.assert_called_with(True)

    def test_checkpoint_creates_valid_empty_annotation_json(self) -> None:
        controller = self.make_controller()
        controller.document.intervals.clear()
        with tempfile.TemporaryDirectory() as temporary_directory:
            data_directory = Path(temporary_directory)
            with patch(
                "video_event_logger.services.path_utils.RESULTS_DIR",
                data_directory / "results",
            ), patch(
                "video_event_logger.services.path_utils.LEGACY_AUTOSAVE_DIR",
                data_directory / "autosave",
            ):
                saved = controller._save_checkpoint("Empty annotations saved.")
                result_path = controller.project_service.annotation_path_for_video_name(
                    "sample.mp4"
                )
                result_data = json.loads(result_path.read_text(encoding="utf-8"))

        self.assertTrue(saved)
        self.assertEqual(result_data["intervals"], [])

    @patch(
        "video_event_logger.tasks.event_logging.controller.QFileDialog.getOpenFileName",
        return_value=("/tmp/sample.mp4", ""),
    )
    def test_opening_video_immediately_creates_empty_annotation_json(
        self,
        file_dialog: Mock,
    ) -> None:
        controller = object.__new__(EventLoggingController)
        controller.window = Mock()
        controller.workspace = Mock()
        controller.video_player = Mock()
        controller.video_player.load_video.return_value = True
        controller.video_player.rotation_degrees = 0
        controller.project_service = ProjectService(AnnotationStore())
        controller.annotation_service = AnnotationService()
        controller.current_video_path = None
        controller.document = None
        controller.last_annotation_path = None
        controller._set_video_loaded = Mock()
        controller._refresh_duration_metadata = Mock()
        controller._refresh_ui_from_document = Mock()
        controller._prepare_video_preview = Mock()
        controller._clear_event_type_focus = Mock()

        with tempfile.TemporaryDirectory() as temporary_directory:
            data_directory = Path(temporary_directory)
            with patch(
                "video_event_logger.services.path_utils.RESULTS_DIR",
                data_directory / "results",
            ), patch(
                "video_event_logger.services.path_utils.LEGACY_AUTOSAVE_DIR",
                data_directory / "autosave",
            ):
                controller.open_video_file()
                annotation_path = (
                    controller.project_service.annotation_path_for_video_name(
                        "sample.mp4"
                    )
                )
                annotation_data = json.loads(
                    annotation_path.read_text(encoding="utf-8")
                )

        self.assertEqual(annotation_data["intervals"], [])
        self.assertEqual(controller.last_annotation_path, annotation_path)
        controller._set_video_loaded.assert_called_once_with(True)

    def test_syncing_loaded_work_preserves_saved_resume_position(self) -> None:
        controller = self.make_controller()
        controller.document.last_playback_position_seconds = 7.75
        with tempfile.TemporaryDirectory() as temporary_directory:
            data_directory = Path(temporary_directory)
            with patch(
                "video_event_logger.services.path_utils.LEGACY_AUTOSAVE_DIR",
                data_directory / "autosave",
            ), patch(
                "video_event_logger.services.path_utils.RESULTS_DIR",
                data_directory / "results",
            ):
                controller._save_checkpoint("Loaded work synced.", update_runtime=False)
                result_path = controller.project_service.annotation_path_for_video_name(
                    "sample.mp4"
                )
                result_data = json.loads(result_path.read_text(encoding="utf-8"))

        self.assertEqual(result_data["last_playback_position_seconds"], 7.75)

    @patch("video_event_logger.tasks.event_logging.controller.QMessageBox.warning")
    def test_save_failure_keeps_failed_state_visible(self, warning: Mock) -> None:
        controller = self.make_controller()
        controller.project_service = Mock()
        controller.project_service.save.side_effect = OSError("disk error")

        saved = controller._save_checkpoint("Annotations saved.")

        self.assertFalse(saved)
        self.assertEqual(
            [call.args[0] for call in controller.window.set_save_state.call_args_list],
            ["saving", "failed"],
        )
        warning.assert_called_once()


class EventLoggingControllerApiUploadTest(unittest.TestCase):
    def make_controller(self, annotation_path: Path) -> EventLoggingController:
        controller = object.__new__(EventLoggingController)
        controller.document = AnnotationDocument.empty("sample.mp4")
        controller.current_video_path = Path("sample.mp4")
        controller.last_annotation_path = annotation_path
        controller.active_event_type = "event"
        controller.api_upload_reply = None
        controller.api_upload_progress = None
        controller.event_type_apply_timer = Mock()
        controller.workspace = Mock()
        controller.workspace.event_type_text.return_value = "event"
        controller.window = Mock()
        controller.window.api_connection_settings.return_value = (
            "https://example.org/api/v1/annotations",
            "secret-token",
        )
        controller.api_network_manager = Mock()
        controller.annotation_service = Mock()
        controller.annotation_service.has_pending_interval.return_value = False
        controller._set_event_type_lamp = Mock()
        controller._update_document_runtime_state = Mock()
        controller._save_checkpoint = Mock(return_value=True)
        controller._set_status_text = Mock()
        return controller

    @patch("video_event_logger.tasks.event_logging.controller.QProgressDialog")
    def test_upload_posts_exact_annotation_json_with_token_auth(
        self,
        progress_type: Mock,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            annotation_path = Path(temporary_directory) / "sample.annotations.json"
            payload = b'{"video_name":"sample.mp4","intervals":[]}\n'
            annotation_path.write_bytes(payload)
            controller = self.make_controller(annotation_path)
            reply = Mock()
            controller.api_network_manager.post.return_value = reply

            controller.upload_annotations()

        request, posted_payload = controller.api_network_manager.post.call_args.args
        self.assertEqual(
            bytes(request.rawHeader("Authorization")),
            b"TokenAuth secret-token",
        )
        self.assertEqual(bytes(posted_payload), payload)
        controller._save_checkpoint.assert_called_once_with(
            "Annotations saved and ready to upload.",
            update_runtime=False,
        )
        controller.window.set_api_upload_available.assert_called_once_with(False)
        reply.finished.connect.assert_called_once()
        progress_type.return_value.show.assert_called_once_with()

    @patch("video_event_logger.tasks.event_logging.controller.QMessageBox.warning")
    def test_active_interval_must_be_finished_before_upload(
        self,
        warning: Mock,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            annotation_path = Path(temporary_directory) / "sample.annotations.json"
            annotation_path.write_text("{}", encoding="utf-8")
            controller = self.make_controller(annotation_path)
            controller.annotation_service.has_pending_interval.return_value = True

            controller.upload_annotations()

        warning.assert_called_once_with(
            controller.window,
            "Interval active",
            "Finish or cancel the active interval before uploading annotations.",
        )
        controller.api_network_manager.post.assert_not_called()

    @patch("video_event_logger.tasks.event_logging.controller.QMessageBox.information")
    @patch("video_event_logger.tasks.event_logging.controller.QMessageBox.warning")
    def test_duplicate_response_is_reported_separately(
        self,
        warning: Mock,
        information: Mock,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            annotation_path = Path(temporary_directory) / "sample.annotations.json"
            annotation_path.write_text("{}", encoding="utf-8")
            controller = self.make_controller(annotation_path)
            reply = Mock()
            reply.attribute.return_value = 409
            reply.readAll.return_value = b'{"detail":"Already uploaded"}'
            reply.error.return_value = QNetworkReply.NetworkError.ContentConflictError
            reply.errorString.return_value = "Conflict"
            controller.api_upload_reply = reply
            controller.api_upload_progress = Mock()

            controller._finish_api_upload(reply)

        warning.assert_called_once()
        self.assertEqual(warning.call_args.args[1], "Duplicate annotations")
        self.assertIn("Already uploaded", warning.call_args.args[2])
        information.assert_not_called()
        controller.window.set_api_upload_available.assert_called_once_with(True)
        controller._set_status_text.assert_called_once_with(
            "Upload rejected: duplicate annotations."
        )

    @patch("video_event_logger.tasks.event_logging.controller.QMessageBox.warning")
    def test_html_404_uses_friendly_endpoint_message(self, warning: Mock) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            annotation_path = Path(temporary_directory) / "sample.annotations.json"
            annotation_path.write_text("{}", encoding="utf-8")
            controller = self.make_controller(annotation_path)
            reply = Mock()
            reply.attribute.return_value = 404
            reply.readAll.return_value = (
                b"<!doctype html><html><body><h1>Not Found</h1></body></html>"
            )
            reply.error.return_value = QNetworkReply.NetworkError.ContentNotFoundError
            reply.errorString.return_value = "Error transferring: server replied: Not Found"
            controller.api_upload_reply = reply
            controller.api_upload_progress = Mock()

            controller._finish_api_upload(reply)

        warning.assert_called_once_with(
            controller.window,
            "Upload failed",
            "HTTP 404\n\nThe upload endpoint was not found. "
            "Check the URL in Connection \u2192 Settings\u2026",
        )


class VideoPreviewPreparationTest(unittest.TestCase):
    @patch("video_event_logger.tasks.event_logging.controller.QTimer.singleShot")
    def test_zero_position_does_not_seek_before_reference_clock_exists(
        self,
        single_shot: Mock,
    ) -> None:
        controller = object.__new__(EventLoggingController)
        controller.video_player = Mock()

        controller._prepare_video_preview(0.0)

        controller.video_player.play.assert_called_once_with()
        controller.video_player.set_time_seconds.assert_not_called()
        single_shot.assert_called_once_with(950, controller.video_player.pause)

    @patch("video_event_logger.tasks.event_logging.controller.QTimer.singleShot")
    def test_resume_position_is_sought_once_after_playback_starts(
        self,
        single_shot: Mock,
    ) -> None:
        controller = object.__new__(EventLoggingController)
        controller.video_player = Mock()

        controller._prepare_video_preview(12.5)

        self.assertEqual(single_shot.call_count, 2)
        seek_callback = single_shot.call_args_list[0].args[1]
        seek_callback()
        controller.video_player.set_time_seconds.assert_called_once_with(12.5)
        self.assertEqual(
            single_shot.call_args_list[1].args,
            (950, controller.video_player.pause),
        )


if __name__ == "__main__":
    unittest.main()

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

    def _make_play_pause_controller(self, playing: bool) -> EventLoggingController:
        controller = object.__new__(EventLoggingController)
        controller.current_playback_speed = 4.0
        controller.playback_interval_end_seconds = None
        controller.video_player = Mock()
        controller.video_player.is_playing.return_value = playing
        controller.workspace = Mock()
        controller._refresh_rotation_enabled = Mock()
        return controller

    def test_pause_keeps_selected_speed(self) -> None:
        controller = self._make_play_pause_controller(playing=True)

        controller._toggle_play_pause()

        controller.video_player.pause.assert_called_once()
        controller.video_player.set_rate.assert_not_called()
        self.assertEqual(controller.current_playback_speed, 4.0)

    @patch("video_event_logger.tasks.event_logging.controller.QTimer")
    def test_play_resumes_with_selected_speed(self, timer) -> None:
        controller = self._make_play_pause_controller(playing=False)

        controller._toggle_play_pause()

        controller.video_player.play.assert_called_once()
        controller.video_player.set_rate.assert_called_once_with(4.0)
        controller.workspace.set_active_speed.assert_called_once_with(4.0)
        timer.singleShot.assert_called_once_with(100, controller._apply_current_speed)

    def test_escape_leaves_fullscreen_without_canceling_interval(self) -> None:
        controller = object.__new__(EventLoggingController)
        controller.window = Mock()
        controller.window.video_fullscreen_enabled = True
        controller.workspace = Mock()
        controller.annotation_service = Mock()

        controller._hotkey_exit_fullscreen()

        controller.window.set_fullscreen.assert_called_once_with(False)
        controller.annotation_service.has_pending_interval.assert_not_called()

    def test_cancel_replaces_active_badge_with_top_status(self) -> None:
        controller = object.__new__(EventLoggingController)
        controller.window = Mock()
        controller.window.video_fullscreen_enabled = True
        controller.workspace = Mock()
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
        "video_event_logger.tasks.event_logging.controller.QFileDialog.getOpenFileNames",
        return_value=(["/tmp/sample.mp4"], ""),
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
        controller.download_dialog = None
        controller.document = None
        controller.last_annotation_path = None
        controller._set_video_loaded = Mock()
        controller._refresh_duration_metadata = Mock()
        controller._refresh_ui_from_document = Mock()
        controller._prepare_video_preview = Mock()
        controller._clear_event_type_focus = Mock()
        controller.event_type_apply_timer = Mock()
        controller.scrub_seek_timer = Mock()

        with tempfile.TemporaryDirectory() as temporary_directory:
            data_directory = Path(temporary_directory)
            with patch(
                "video_event_logger.services.path_utils.RESULTS_DIR",
                data_directory / "results",
            ), patch(
                "video_event_logger.services.path_utils.LEGACY_AUTOSAVE_DIR",
                data_directory / "autosave",
            ):
                video_path = data_directory / "sample.mp4"
                video_path.touch()
                controller._open_video_path(video_path)
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
        controller.submit_dialog = None
        controller.upload_results = {}
        controller.event_type_apply_timer = Mock()
        controller.workspace = Mock()
        controller.workspace.event_type_text.return_value = "event"
        controller.workspace.playlist_panel.paths = [Path("sample.mp4"), Path("next.mp4")]
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
        controller._annotation_file_exists = Mock(return_value=True)
        return controller

    def finished_reply(self, status, body, error=None):  # type: ignore[no-untyped-def]
        reply = Mock()
        reply.attribute.return_value = status
        reply.readAll.return_value = body
        reply.error.return_value = error or QNetworkReply.NetworkError.NoError
        reply.errorString.return_value = ""
        return reply

    @patch("video_event_logger.tasks.event_logging.controller.SubmitDialog")
    def test_upload_opens_review_then_posts_exact_json_with_token_auth(
        self,
        dialog_type: Mock,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            annotation_path = Path(temporary_directory) / "sample.annotations.json"
            payload = b'{"video_name":"sample.mp4","intervals":[]}\n'
            annotation_path.write_bytes(payload)
            controller = self.make_controller(annotation_path)
            reply = Mock()
            controller.api_network_manager.post.return_value = reply

            controller.upload_annotations()
            dialog = dialog_type.return_value
            dialog.open.assert_called_once_with()
            # Nothing is sent before the annotator confirms the review step.
            controller.api_network_manager.post.assert_not_called()
            self.assertTrue(dialog_type.call_args.args[3])  # has next video
            controller._send_upload()

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
        dialog.show_sending.assert_called_once_with()

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

    def test_every_server_answer_reaches_the_result_screen(self) -> None:
        cases = [
            (201, b'{"status":"export_queued","message":"5 clips queued"}', "success", "Submitted", "5 clips queued"),
            (201, b'{"status":"export_pending","message":"already pending"}', "success", "Submitted", "already pending"),
            (201, b'{"status":"unrecognized","message":"no batch group"}', "attention", "Submitted, but not matched", "no batch group"),
            (201, b'{"status":"no_events","message":"marked reviewed"}', "success", "Marked as reviewed \u2014 no events", "marked reviewed"),
            (409, b'{"detail":"Already uploaded"}', "attention", "Already uploaded", "Already uploaded"),
            (400, b'{"error":"intervals[0] is invalid"}', "error", "The server rejected the annotations", "intervals[0] is invalid"),
            (401, b'{"detail":"Invalid token."}', "error", "Access token not accepted", "Invalid token."),
            (502, b'{"error":"Tracker unavailable"}', "error", "Server problem \u2014 try again later", "Tracker unavailable"),
            (503, b"", "error", "Server problem \u2014 try again later", "The server could not process the upload. Try again later."),
        ]
        for status, body, tone, title, message in cases:
            with self.subTest(status=status, body=body):
                controller = self.make_controller(Path("unused.json"))
                controller.submit_dialog = Mock()
                reply = self.finished_reply(status, body)
                controller.api_upload_reply = reply

                controller._finish_api_upload(reply)

                outcome = controller.submit_dialog.show_result.call_args.args[0]
                self.assertEqual((outcome.tone, outcome.title, outcome.message), (tone, title, message))
                controller.window.set_api_upload_available.assert_called_once_with(True)
                self.assertIs(controller.upload_results[Path("sample.mp4")], outcome)

    def test_canceled_upload_returns_to_review(self) -> None:
        controller = self.make_controller(Path("unused.json"))
        controller.submit_dialog = Mock()
        reply = self.finished_reply(None, b"", QNetworkReply.NetworkError.OperationCanceledError)
        controller.api_upload_reply = reply

        controller._finish_api_upload(reply)

        controller.submit_dialog.show_review.assert_called_once_with()
        controller.submit_dialog.show_result.assert_not_called()
        controller._set_status_text.assert_called_once_with("Annotation upload canceled.")

    @patch("video_event_logger.tasks.event_logging.controller.QMessageBox.warning")
    def test_html_404_uses_friendly_endpoint_message_without_dialog(self, warning: Mock) -> None:
        controller = self.make_controller(Path("unused.json"))
        reply = self.finished_reply(
            404,
            b"<!doctype html><html><body><h1>Not Found</h1></body></html>",
            QNetworkReply.NetworkError.ContentNotFoundError,
        )
        controller.api_upload_reply = reply

        controller._finish_api_upload(reply)

        warning.assert_called_once()
        self.assertIn(
            "The upload endpoint was not found. Check the URL in Connection \u2192 Settings\u2026",
            warning.call_args.args[2],
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
        self.assertEqual(single_shot.call_args.args[0], 950)
        single_shot.call_args.args[1]()
        controller.video_player.pause.assert_called_once_with()

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
        self.assertEqual(single_shot.call_args_list[1].args[0], 950)
        single_shot.call_args_list[1].args[1]()
        controller.video_player.pause.assert_called_once_with()


class PlaylistPreviewRaceTest(unittest.TestCase):
    @patch("video_event_logger.tasks.event_logging.controller.QTimer.singleShot")
    def test_previous_video_callbacks_cannot_seek_or_pause_next_video(self, single_shot):
        controller = object.__new__(EventLoggingController)
        controller.video_player = Mock()
        controller._prepare_video_preview(12.5)
        callbacks = [call.args[1] for call in single_shot.call_args_list]
        controller._prepare_video_preview(0.0, autoplay=True)
        for callback in callbacks:
            callback()
        controller.video_player.pause.assert_not_called()
        controller.video_player.set_time_seconds.assert_not_called()


if __name__ == "__main__":
    unittest.main()

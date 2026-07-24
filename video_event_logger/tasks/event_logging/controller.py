from pathlib import Path
from typing import Optional

from PySide6.QtCore import QByteArray, Qt, QTimer, QUrl
from PySide6.QtGui import QDesktopServices, QKeySequence, QShortcut
from PySide6.QtNetwork import QNetworkAccessManager, QNetworkReply, QNetworkRequest
from PySide6.QtWidgets import (
    QDialog,
    QFileDialog,
    QLineEdit,
    QMessageBox,
    QProgressDialog,
)

from video_event_logger.app_config import DEFAULT_EVENT_TYPE
from video_event_logger.application.annotation_service import AnnotationService
from video_event_logger.application.project_service import ProjectService
from video_event_logger.domain.errors import (
    InvalidIntervalError,
    InvalidIntervalIndexError,
    MissingIntervalStartError,
)
from video_event_logger.models.annotation import AnnotationDocument
from video_event_logger.services.annotation_api import (
    MAX_INTERVALS_PER_UPLOAD,
    build_upload_request,
    default_http_error_message,
    server_response_message,
    validate_api_settings,
)
from video_event_logger.services.annotation_store import AnnotationStore, CorruptedAnnotationError
from video_event_logger.services.path_utils import is_supported_video
from video_event_logger.services.validation import validate_document
from video_event_logger.tasks.event_logging.ui.help_dialog import AnnotatorHelpDialog
from video_event_logger.tasks.event_logging.ui.workspace import EventLoggingWorkspace
from video_event_logger.ui.interval_dialog import IntervalDialog


class EventLoggingController:
    def __init__(self, window, workspace: EventLoggingWorkspace) -> None:  # type: ignore[no-untyped-def]
        self.window = window
        self.workspace = workspace
        self.video_player = self.workspace.video_player
        self.project_service = ProjectService(AnnotationStore())
        self.annotation_service = AnnotationService()
        self.current_video_path = None  # type: Optional[Path]
        self.document = None  # type: Optional[AnnotationDocument]
        self.last_annotation_path = None  # type: Optional[Path]
        self.save_state = "missing"
        self.last_stable_save_state = "missing"
        self.active_event_type = DEFAULT_EVENT_TYPE
        self.is_applying_event_type = False
        self.is_completing_interval = False
        self.pending_scrub_seconds = None  # type: Optional[float]
        self.playback_interval_end_seconds = None  # type: Optional[float]
        self.current_playback_speed = 1.0
        self.api_network_manager = QNetworkAccessManager(window)
        self.api_upload_reply = None  # type: Optional[QNetworkReply]
        self.api_upload_progress = None  # type: Optional[QProgressDialog]
        self.shortcuts = []
        self.event_type_apply_timer = QTimer(window)
        self.event_type_apply_timer.setSingleShot(True)
        self.event_type_apply_timer.setInterval(2000)
        self.scrub_seek_timer = QTimer(window)
        self.scrub_seek_timer.setSingleShot(True)
        self.scrub_seek_timer.setInterval(90)
        self.scrub_seek_timer.timeout.connect(self._apply_pending_scrub_seek)

        self._connect_signals()
        self._connect_shortcuts()
        self._set_video_loaded(False)
        self._set_event_type_lamp("active")
        self._set_save_state("missing")
        if hasattr(self.window, "set_video_rotation_degrees"):
            self.window.set_video_rotation_degrees(self.video_player.rotation_degrees)
        if hasattr(self.window, "set_video_rotation_available"):
            self.window.set_video_rotation_available(False)
        self.workspace.set_pending_interval_start(None)
        self.workspace.set_active_speed(1.0)
        self.workspace.set_playback_active(False)

        self.timer = QTimer(window)
        self.timer.setInterval(300)
        self.timer.timeout.connect(self._update_playback_labels)
        self.timer.start()
        QTimer.singleShot(0, self._clear_event_type_focus)

    def _connect_signals(self) -> None:
        metadata_panel = self.workspace.metadata_panel
        player_panel = self.workspace.player_panel
        intervals_panel = self.workspace.intervals_panel

        metadata_panel.event_type_input.returnPressed.connect(self.apply_event_type)
        metadata_panel.event_type_input.editingFinished.connect(self.apply_event_type)
        metadata_panel.event_type_input.textChanged.connect(self.mark_event_type_pending)
        self.event_type_apply_timer.timeout.connect(self.apply_event_type)

        player_panel.timeline_slider.sliderPressed.connect(self._begin_slider_drag)
        player_panel.timeline_slider.sliderReleased.connect(self._finish_slider_drag)
        player_panel.timeline_slider.sliderMoved.connect(self._preview_slider_position)
        self.video_player.fullscreen_seek_previewed.connect(
            self._preview_fullscreen_slider_position
        )
        self.video_player.fullscreen_seek_requested.connect(
            self._finish_fullscreen_slider_seek
        )
        player_panel.play_pause_button.clicked.connect(self._toggle_play_pause)
        player_panel.seek_back_button.clicked.connect(lambda: self.video_player.seek_relative(-1.0))
        player_panel.seek_forward_button.clicked.connect(lambda: self.video_player.seek_relative(1.0))
        player_panel.seek_back_10_button.clicked.connect(lambda: self.video_player.seek_relative(-10.0))
        player_panel.seek_forward_10_button.clicked.connect(lambda: self.video_player.seek_relative(10.0))
        player_panel.frame_back_button.clicked.connect(self._step_backward_frame)
        player_panel.frame_forward_button.clicked.connect(self._step_forward_frame)
        player_panel.speed_1_button.clicked.connect(lambda: self._set_speed(1.0))
        player_panel.speed_2_button.clicked.connect(lambda: self._set_speed(2.0))
        player_panel.speed_4_button.clicked.connect(lambda: self._set_speed(4.0))
        player_panel.speed_8_button.clicked.connect(lambda: self._set_speed(8.0))
        player_panel.set_start_button.clicked.connect(self.set_interval_start)
        player_panel.set_end_button.clicked.connect(self.set_interval_end)

        intervals_panel.play_requested.connect(self._play_interval_at_row)
        intervals_panel.edit_requested.connect(self._edit_interval_at_row)
        intervals_panel.delete_requested.connect(self._delete_interval_at_row)
        intervals_panel.jump_requested.connect(self._jump_to_interval_start)

    def _connect_shortcuts(self) -> None:
        self._add_shortcut("Space", self._hotkey_toggle_play_pause)
        self._add_shortcut("A", self._hotkey_set_interval_start)
        self._add_shortcut("D", self._hotkey_set_interval_end)
        self._add_shortcut("Delete", self._hotkey_delete_selected_interval)
        self._add_shortcut("Left", lambda: self._hotkey_seek_relative(-1.0))
        self._add_shortcut("Right", lambda: self._hotkey_seek_relative(1.0))
        self._add_shortcut("Shift+Left", lambda: self._hotkey_seek_relative(-10.0))
        self._add_shortcut("Shift+Right", lambda: self._hotkey_seek_relative(10.0))
        self._add_shortcut(",", self._hotkey_step_backward_frame)
        self._add_shortcut(".", self._hotkey_step_forward_frame)
        self._add_shortcut("1", lambda: self._hotkey_set_speed(1.0))
        self._add_shortcut("2", lambda: self._hotkey_set_speed(2.0))
        self._add_shortcut("4", lambda: self._hotkey_set_speed(4.0))
        self._add_shortcut("8", lambda: self._hotkey_set_speed(8.0))
        self._add_shortcut("Escape", self._hotkey_exit_fullscreen)
        self._add_shortcut("Q", self._hotkey_cancel_pending_interval)

    def _add_shortcut(self, key_sequence: str, handler) -> None:  # type: ignore[no-untyped-def]
        shortcut = QShortcut(QKeySequence(key_sequence), self.window)
        shortcut.setContext(Qt.ShortcutContext.WindowShortcut)
        shortcut.activated.connect(handler)
        self.shortcuts.append(shortcut)

    def show_help(self) -> None:
        dialog = AnnotatorHelpDialog(self.window)
        dialog.exec()

    def open_video_file(self) -> None:
        file_path, _ = QFileDialog.getOpenFileName(
            self.window,
            "Open Video File",
            "",
            "Video files (*.mp4 *.mkv)",
        )
        if not file_path:
            return

        video_path = Path(file_path)
        if not is_supported_video(video_path):
            QMessageBox.warning(
                self.window,
                "Unsupported video format",
                "Unsupported video format. Please select .mp4 or .mkv file.",
            )
            return

        existing_paths = self.project_service.existing_paths(video_path.name)
        document = self.project_service.create_empty_document(video_path.name)
        resume_position = False
        continued_existing_work = False

        if existing_paths:
            action = self._ask_existing_project_action()
            if action == "cancel":
                return
            if action == "delete":
                if not self._confirm_delete_project(video_path.name):
                    return
                self.project_service.delete_project(video_path.name)
                self._set_status_text("project deleted")
            elif action == "start_over":
                if not self._confirm_start_over():
                    return
            elif action == "continue":
                corrupted_backups = []
                for source_path in self.project_service.existing_sources(existing_paths):
                    try:
                        document = self.project_service.load_document(
                            source_path,
                            video_path.name,
                        )
                        continued_existing_work = True
                        break
                    except CorruptedAnnotationError as exc:
                        corrupted_backups.append(exc.backup_path)
                if corrupted_backups:
                    recovery_text = (
                        "A valid previous version was recovered."
                        if continued_existing_work
                        else "No valid previous version remained; an empty annotation file will be created."
                    )
                    QMessageBox.warning(
                        self.window,
                        "Corrupted JSON",
                        "Corrupted file(s) were preserved as:\n%s\n\n%s"
                        % (
                            "\n".join(str(path) for path in corrupted_backups),
                            recovery_text,
                        ),
                    )
                if continued_existing_work:
                    self._set_status_text("Existing annotations loaded")
                if document.last_playback_position_seconds > 0:
                    resume_position = self._ask_resume_position()

        if not self.video_player.load_video(video_path):
            details = self.video_player.last_error or "Unknown VLC initialization error."
            QMessageBox.warning(
                self.window,
                "VLC unavailable",
                "Could not initialize VLC playback.\n\n%s\n\nMake sure VLC/libVLC is installed from apt, not only as a Snap app." % details,
            )
            return

        self.current_video_path = video_path
        self.document = document
        self.annotation_service.set_document(document)
        annotation_path = self.project_service.annotation_path_for_video_name(
            document.video_name
        )
        self.last_annotation_path = annotation_path if annotation_path.exists() else None
        self._set_video_loaded(True)
        self.window.set_video_rotation_degrees(self.video_player.rotation_degrees)
        self._refresh_duration_metadata()
        self._refresh_ui_from_document()

        target_position = 0.0
        if resume_position and self.document is not None:
            target_position = self.document.last_playback_position_seconds
        self._save_checkpoint("Annotation JSON saved.", update_runtime=False)
        self._prepare_video_preview(target_position)
        self._clear_event_type_focus()

    def apply_event_type(self) -> None:
        if self.is_applying_event_type:
            return
        self.is_applying_event_type = True
        try:
            self.event_type_apply_timer.stop()
            self.active_event_type = self.workspace.event_type_text().strip() or DEFAULT_EVENT_TYPE
            self._set_event_type_lamp("active")
            self._clear_event_type_focus()
            QTimer.singleShot(0, self._clear_event_type_focus)
            if self.document is not None:
                self.document.current_event_type = self.active_event_type
                self._save_checkpoint("Event type saved.")
        finally:
            self.is_applying_event_type = False

    def mark_event_type_pending(self) -> None:
        typed_value = self.workspace.event_type_text().strip() or DEFAULT_EVENT_TYPE
        if typed_value != self.active_event_type:
            self._set_event_type_lamp("pending")
            self._set_save_state("dirty")
            self.event_type_apply_timer.start()
        else:
            self._set_event_type_lamp("active")
            self.event_type_apply_timer.stop()
            if getattr(self, "save_state", "missing") == "dirty":
                self._set_save_state(
                    getattr(self, "last_stable_save_state", "missing")
                )

    def set_interval_start(self) -> None:
        if not self._has_loaded_video():
            return
        if self.annotation_service.has_pending_interval():
            self._set_status_text(
                "Interval is already active. Press End or D to finish, or Q to cancel."
            )
            return
        start_seconds = self.video_player.get_time_seconds()
        self.annotation_service.start_interval(start_seconds)
        self.workspace.set_pending_interval_start(start_seconds)
        self._set_status_text("Interval start set. Press End or D to finish.")

    def set_interval_end(self) -> None:
        if not self._has_loaded_video():
            return
        self._complete_pending_interval(self.video_player.get_time_seconds())

    def _complete_pending_interval(self, end_seconds: float, automatic: bool = False) -> None:
        if self.is_completing_interval:
            return
        if not self.annotation_service.has_pending_interval():
            QMessageBox.warning(self.window, "Missing start", "Set interval start first.")
            return
        start_seconds = self.annotation_service.pending_start_seconds
        if start_seconds is None:
            QMessageBox.warning(self.window, "Missing start", "Set interval start first.")
            return
        if start_seconds >= end_seconds:
            QMessageBox.warning(self.window, "Invalid interval", "Interval start must be before interval end.")
            return

        self.is_completing_interval = True
        try:
            event_type = self._current_event_type()
            comment = ""
            popup_enabled = self.workspace.show_popup_after_interval()
            if popup_enabled:
                was_playing = self.video_player.is_playing()
                self.video_player.pause()
                dialog = IntervalDialog(start_seconds, end_seconds, event_type, self.window)
                if dialog.exec() != QDialog.DialogCode.Accepted:
                    self.annotation_service.cancel_pending_interval()
                    self.workspace.set_pending_interval_start(None)
                    self.workspace.show_fullscreen_notification(
                        "Interval canceled",
                        "info",
                        False,
                    )
                    self._set_status_text("Interval canceled")
                    if was_playing:
                        self.video_player.play()
                    return
                event_type, comment = dialog.values()

            try:
                self.annotation_service.end_interval(end_seconds, event_type, comment)
            except MissingIntervalStartError:
                QMessageBox.warning(self.window, "Missing start", "Set interval start first.")
                return
            except InvalidIntervalError:
                QMessageBox.warning(self.window, "Invalid interval", "Interval start must be before interval end.")
                return

            self.workspace.set_pending_interval_start(None)
            self._refresh_table()
            self._refresh_counts()
            if automatic:
                saved = self._save_checkpoint(
                    "Interval reached the end of the video and was saved."
                )
            else:
                saved = self._save_checkpoint("Interval added and saved.")
            if saved:
                self.workspace.show_fullscreen_notification(
                    "Interval added",
                    "success",
                    False,
                )
        finally:
            self.is_completing_interval = False

    def validate_and_save(self) -> None:
        if self.document is None:
            QMessageBox.warning(self.window, "No video", "Video is not loaded.")
            return
        self.event_type_apply_timer.stop()
        self.active_event_type = (
            self.workspace.event_type_text().strip() or DEFAULT_EVENT_TYPE
        )
        self.document.current_event_type = self.active_event_type
        self._set_event_type_lamp("active")
        self._update_document_runtime_state()
        errors = validate_document(self.document)
        if errors:
            QMessageBox.warning(self.window, "Validation failed", "\n".join(errors))
            return
        self._save_checkpoint("Annotations validated and saved.")

    def show_annotation_file_in_folder(self) -> None:
        path = self._annotation_path_for_ui()
        if path is None:
            return
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(path.parent)))

    def upload_annotations(self) -> None:
        if self.api_upload_reply is not None:
            return
        if self.document is None:
            QMessageBox.warning(self.window, "No video", "Video is not loaded.")
            return
        if self.annotation_service.has_pending_interval():
            QMessageBox.warning(
                self.window,
                "Interval active",
                "Finish or cancel the active interval before uploading annotations.",
            )
            return

        endpoint_url, token = self.window.api_connection_settings()
        settings_error = validate_api_settings(endpoint_url, token)
        if settings_error is not None:
            QMessageBox.warning(
                self.window,
                "API settings required",
                "%s\n\nOpen Connection → Settings… to configure uploads."
                % settings_error,
            )
            return

        self.event_type_apply_timer.stop()
        self.active_event_type = (
            self.workspace.event_type_text().strip() or DEFAULT_EVENT_TYPE
        )
        self.document.current_event_type = self.active_event_type
        self._set_event_type_lamp("active")
        self._update_document_runtime_state()
        errors = validate_document(self.document)
        if len(self.document.intervals) > MAX_INTERVALS_PER_UPLOAD:
            errors.append(
                "The API accepts at most %d intervals per annotation file."
                % MAX_INTERVALS_PER_UPLOAD
            )
        if errors:
            QMessageBox.warning(
                self.window,
                "Upload validation failed",
                "\n".join(errors),
            )
            return
        if not self._save_checkpoint(
            "Annotations saved and ready to upload.",
            update_runtime=False,
        ):
            return

        annotation_path = self.last_annotation_path
        if annotation_path is None or not annotation_path.exists():
            QMessageBox.warning(
                self.window,
                "Annotation file unavailable",
                "The annotation JSON could not be found.",
            )
            return
        try:
            payload = annotation_path.read_bytes()
        except OSError as exc:
            QMessageBox.warning(
                self.window,
                "Annotation file unavailable",
                "Could not read the annotation JSON.\n\n%s" % exc,
            )
            return

        request = build_upload_request(endpoint_url, token)
        reply = self.api_network_manager.post(request, QByteArray(payload))
        self.api_upload_reply = reply
        self.window.set_api_upload_available(False)

        progress = QProgressDialog(
            "Uploading annotations…",
            "Cancel",
            0,
            0,
            self.window,
        )
        progress.setWindowTitle("Upload Annotations")
        progress.setWindowModality(Qt.WindowModality.ApplicationModal)
        progress.setMinimumDuration(0)
        progress.setAutoClose(False)
        progress.setAutoReset(False)
        progress.canceled.connect(reply.abort)
        self.api_upload_progress = progress
        reply.finished.connect(
            lambda current_reply=reply: self._finish_api_upload(current_reply)
        )
        progress.show()

    def _finish_api_upload(self, reply: QNetworkReply) -> None:
        if reply is not self.api_upload_reply:
            reply.deleteLater()
            return

        progress = self.api_upload_progress
        self.api_upload_progress = None
        self.api_upload_reply = None
        if progress is not None:
            progress.close()
            progress.deleteLater()

        status_value = reply.attribute(
            QNetworkRequest.Attribute.HttpStatusCodeAttribute
        )
        try:
            status_code = int(status_value) if status_value is not None else None
        except (TypeError, ValueError):
            status_code = None
        response_body = bytes(reply.readAll())
        network_error = reply.error()
        network_error_text = reply.errorString().strip()
        reply.deleteLater()

        self.window.set_api_upload_available(self._annotation_file_exists())

        if (
            network_error == QNetworkReply.NetworkError.NoError
            and status_code is not None
            and 200 <= status_code < 300
        ):
            self._set_status_text("Annotations uploaded successfully.")
            QMessageBox.information(
                self.window,
                "Upload complete",
                "The annotation JSON was uploaded successfully.",
            )
            return

        server_message = server_response_message(response_body)
        if status_code == 409:
            detail = server_message or "This annotation file was already uploaded."
            self._set_status_text("Upload rejected: duplicate annotations.")
            QMessageBox.warning(
                self.window,
                "Duplicate annotations",
                "%s\n\nThe server rejected the duplicate upload." % detail,
            )
            return

        if network_error == QNetworkReply.NetworkError.OperationCanceledError:
            self._set_status_text("Annotation upload canceled.")
            QMessageBox.information(
                self.window,
                "Upload canceled",
                "The annotation upload was canceled.",
            )
            return

        if status_code is not None:
            details = server_message or default_http_error_message(status_code)
        else:
            details = network_error_text or "Could not connect to the server."
        status_text = (
            "HTTP %d" % status_code
            if status_code is not None
            else "Network request failed"
        )
        self._set_status_text("Annotation upload failed.")
        QMessageBox.warning(
            self.window,
            "Upload failed",
            "%s\n\n%s" % (status_text, details),
        )

    def close_event(self, event) -> None:  # type: ignore[no-untyped-def]
        if self.document is not None:
            self._save_checkpoint("Current position saved.")
        event.accept()

    def _delete_interval_at_row(self, row: int) -> None:
        if self.document is None:
            return
        try:
            self.annotation_service.delete_interval_at(row)
        except InvalidIntervalIndexError:
            return
        self._refresh_table()
        self._refresh_counts()
        self._save_checkpoint("Interval deleted and annotations saved.")

    def _edit_interval_at_row(self, row: int) -> None:
        interval = self._interval_at_row(row)
        if interval is None:
            return
        dialog = IntervalDialog(
            interval.start_time_seconds,
            interval.end_time_seconds,
            interval.event_type,
            self.window,
            comment=interval.comment,
            title="Edit interval",
        )
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        event_type, comment = dialog.values()
        try:
            self.annotation_service.update_interval_details(row, event_type, comment)
        except InvalidIntervalIndexError:
            return
        self._refresh_table()
        self._refresh_counts()
        self._save_checkpoint("Interval edited and annotations saved.")

    def _play_interval_at_row(self, row: int) -> None:
        interval = self._interval_at_row(row)
        if interval is None:
            return
        self.playback_interval_end_seconds = interval.end_time_seconds
        self.video_player.set_time_seconds(interval.start_time_seconds)
        self.video_player.play()
        self.workspace.set_playback_active(True)
        self._set_status_text("playing interval %d" % interval.interval_id)

    def _jump_to_interval_start(self, row: int) -> None:
        interval = self._interval_at_row(row)
        if interval is None:
            return
        self.playback_interval_end_seconds = None
        self.video_player.set_time_seconds(interval.start_time_seconds)
        self._set_status_text("jumped to interval %d start" % interval.interval_id)

    def _interval_at_row(self, row: int):
        if self.document is None or row < 0 or row >= len(self.document.intervals):
            return None
        return self.document.intervals[row]

    def _hotkey_toggle_play_pause(self) -> None:
        if self._should_ignore_hotkey() or not self._has_loaded_video(silent=True):
            return
        self._toggle_play_pause()

    def _hotkey_set_interval_start(self) -> None:
        if self._should_ignore_hotkey():
            return
        self.set_interval_start()

    def _hotkey_set_interval_end(self) -> None:
        if self._should_ignore_hotkey():
            return
        self.set_interval_end()

    def _hotkey_delete_selected_interval(self) -> None:
        if self._should_ignore_hotkey() or self.document is None:
            return
        row = self.workspace.selected_interval_row()
        if row < 0:
            return
        self._delete_interval_at_row(row)

    def _hotkey_seek_relative(self, seconds_delta: float) -> None:
        if self._should_ignore_hotkey() or not self._has_loaded_video(silent=True):
            return
        self.workspace.notify_fullscreen_user_activity()
        self.playback_interval_end_seconds = None
        self.video_player.seek_relative(seconds_delta)

    def _hotkey_step_backward_frame(self) -> None:
        if self._should_ignore_hotkey() or not self._has_loaded_video(silent=True):
            return
        self._step_backward_frame()

    def _hotkey_step_forward_frame(self) -> None:
        if self._should_ignore_hotkey() or not self._has_loaded_video(silent=True):
            return
        self._step_forward_frame()

    def _hotkey_set_speed(self, speed: float) -> None:
        if self._should_ignore_hotkey() or not self._has_loaded_video(silent=True):
            return
        self._set_speed(speed)

    def _hotkey_cancel_pending_interval(self) -> None:
        if self._should_ignore_hotkey():
            return
        if not self.annotation_service.has_pending_interval():
            return
        self.annotation_service.cancel_pending_interval()
        self.workspace.set_pending_interval_start(None)
        self.workspace.show_fullscreen_notification(
            "Interval canceled",
            "info",
            False,
        )
        self._set_status_text("Interval canceled")

    def _hotkey_exit_fullscreen(self) -> None:
        if self.window.video_fullscreen_enabled:
            self.window.set_fullscreen(False)

    def _save_checkpoint(
        self,
        status_message: str,
        update_runtime: bool = True,
    ) -> bool:
        if self.document is None:
            return False
        if update_runtime:
            self._update_document_runtime_state()

        self._set_save_state("saving")
        try:
            self.last_annotation_path = self.project_service.save(self.document)
        except Exception as exc:
            self._set_save_state("failed")
            self._set_status_text("Annotation JSON save failed.")
            QMessageBox.warning(
                self.window,
                "JSON save failed",
                "Could not save the annotation JSON. The previous valid file was kept.\n\n%s"
                % exc,
            )
            return False

        self._set_save_state("saved")
        self._set_status_text(status_message)
        return True

    def _update_document_runtime_state(self) -> None:
        if self.document is None:
            return
        self.project_service.update_runtime_state(
            document=self.document,
            current_event_type=self._current_event_type(),
            current_position_seconds=self.video_player.get_time_seconds(),
            duration_seconds=self.video_player.get_duration_seconds(),
        )

    def _refresh_duration_metadata(self) -> None:
        if self.document is None:
            return
        self.project_service.update_duration_metadata(
            document=self.document,
            duration_seconds=self.video_player.get_duration_seconds(),
        )

    def _refresh_ui_from_document(self) -> None:
        self.workspace.set_pending_interval_start(None)
        if self.document is None:
            self.workspace.set_video_name("N/A")
            self.workspace.clear_intervals()
            return
        self.workspace.set_video_name(self.document.video_name)
        self.active_event_type = (self.document.current_event_type or DEFAULT_EVENT_TYPE)[:25]
        self.workspace.set_event_type(self.active_event_type)
        self._set_event_type_lamp("active")
        self._clear_event_type_focus()
        self._refresh_table()
        self._refresh_counts()

    def _refresh_table(self) -> None:
        if self.document is None:
            self.workspace.clear_intervals()
            return
        self.document.refresh_interval_ids()
        self.workspace.refresh_intervals(list(self.document.intervals))

    def _refresh_counts(self) -> None:
        if self.document is None:
            self.workspace.refresh_counts(0, {})
            return
        counts = self.annotation_service.event_counts()
        self.workspace.refresh_counts(len(self.document.intervals), counts)

    def _update_playback_labels(self) -> None:
        current = self.video_player.get_time_seconds()
        self._update_timeline(current)
        self._stop_interval_playback_if_needed(current)
        self._finish_pending_interval_at_video_end(current)
        self._refresh_rotation_enabled()
        self.workspace.set_playback_active(self.video_player.is_playing())
        if self.document is not None:
            old_duration = self.document.video_metadata.duration_seconds
            self._refresh_duration_metadata()
            if self.document.video_metadata.duration_seconds != old_duration:
                self._update_timeline(current)

    def _ask_existing_project_action(self) -> str:
        message = QMessageBox(self.window)
        message.setWindowTitle("Existing annotations")
        message.setText("Annotations already exist for this video.\n\nDo you want to continue existing work or start over?")
        continue_button = message.addButton("Continue Existing Work", QMessageBox.ButtonRole.AcceptRole)
        start_over_button = message.addButton("Start Over", QMessageBox.ButtonRole.DestructiveRole)
        delete_button = message.addButton("Delete Project", QMessageBox.ButtonRole.DestructiveRole)
        cancel_button = message.addButton(QMessageBox.StandardButton.Cancel)
        message.exec()
        clicked = message.clickedButton()
        if clicked == continue_button:
            return "continue"
        if clicked == start_over_button:
            return "start_over"
        if clicked == delete_button:
            return "delete"
        if clicked == cancel_button:
            return "cancel"
        return "cancel"

    def _confirm_start_over(self) -> bool:
        response = QMessageBox.question(
            self.window,
            "Start over",
            "This will overwrite existing annotations for this video. Continue?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        return response == QMessageBox.StandardButton.Yes

    def _confirm_delete_project(self, video_name: str) -> bool:
        response = QMessageBox.question(
            self.window,
            "Delete Project",
            "Delete the annotation JSON and its backup for %s?\n\nThe video file will not be deleted."
            % video_name,
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        return response == QMessageBox.StandardButton.Yes

    def _ask_resume_position(self) -> bool:
        response = QMessageBox.question(
            self.window,
            "Resume position",
            "Continue from last position?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        return response == QMessageBox.StandardButton.Yes

    def _set_speed(self, speed: float) -> None:
        self.workspace.notify_fullscreen_user_activity()
        if not self.video_player.set_rate(speed):
            self._set_status_text("Could not set speed x%s" % speed)
            self.workspace.set_active_speed(self.current_playback_speed)
        else:
            self.current_playback_speed = speed
            self.workspace.set_active_speed(speed)

    def set_video_rotation(self, degrees: int) -> None:
        if not self._has_loaded_video(silent=True):
            return
        if self.video_player.is_playing():
            self._set_status_text("pause video before rotation")
            self._refresh_rotation_enabled()
            return
        if self.video_player.set_rotation_degrees(degrees):
            self.window.set_video_rotation_degrees(self.video_player.rotation_degrees)
            self._set_status_text("rotation %ddeg" % self.video_player.rotation_degrees)
        else:
            self.window.set_video_rotation_degrees(self.video_player.rotation_degrees)
            self._set_status_text("could not change video rotation")

    def _step_backward_frame(self) -> None:
        if not self._has_loaded_video(silent=True):
            return
        self.workspace.notify_fullscreen_user_activity()
        self.playback_interval_end_seconds = None
        if self.video_player.step_backward_frame():
            self._set_status_text("previous frame")
            self._refresh_rotation_enabled()

    def _step_forward_frame(self) -> None:
        if not self._has_loaded_video(silent=True):
            return
        self.workspace.notify_fullscreen_user_activity()
        self.playback_interval_end_seconds = None
        if self.video_player.step_forward_frame():
            self._set_status_text("next frame")
            self._refresh_rotation_enabled()

    def _toggle_play_pause(self) -> None:
        self.workspace.notify_fullscreen_user_activity()
        if self.video_player.is_playing():
            self.video_player.pause()
            self.workspace.set_playback_active(False)
            self.playback_interval_end_seconds = None
            self._reset_speed_to_normal()
            self._refresh_rotation_enabled()
            return
        self._reset_speed_to_normal()
        self.video_player.play()
        self.workspace.set_playback_active(True)
        self._refresh_rotation_enabled()
        QTimer.singleShot(100, self._reset_speed_to_normal)

    def _reset_speed_to_normal(self) -> None:
        self.video_player.set_rate(1.0)
        self.current_playback_speed = 1.0
        self.workspace.set_active_speed(1.0)

    def _set_video_loaded(self, loaded: bool) -> None:
        self.workspace.set_video_loaded(loaded)
        if hasattr(self.window, "set_video_fullscreen_available"):
            self.window.set_video_fullscreen_available(loaded)
        if hasattr(self.window, "set_file_actions_video_loaded"):
            self.window.set_file_actions_video_loaded(loaded)
        if hasattr(self.window, "set_annotation_file_available"):
            self.window.set_annotation_file_available(
                loaded
                and self.last_annotation_path is not None
                and self.last_annotation_path.exists()
            )
        if hasattr(self.window, "set_api_upload_available"):
            self.window.set_api_upload_available(
                loaded and self._annotation_file_exists()
            )
        if not loaded:
            self.workspace.set_playback_active(False)
            self.current_playback_speed = 1.0
            self.workspace.set_active_speed(1.0)
        self._refresh_rotation_enabled()

    def _refresh_rotation_enabled(self) -> None:
        self.window.set_video_rotation_available(
            self.document is not None
            and self.current_video_path is not None
            and not self.video_player.is_playing()
        )

    def _has_loaded_video(self, silent: bool = False) -> bool:
        if self.document is None or self.current_video_path is None:
            if not silent:
                QMessageBox.warning(self.window, "No video", "Video is not loaded.")
            return False
        return True

    def _should_ignore_hotkey(self) -> bool:
        focused_widget = self.window.focusWidget()
        return isinstance(focused_widget, QLineEdit)

    def _current_event_type(self) -> str:
        return self.active_event_type.strip() or DEFAULT_EVENT_TYPE

    def _clear_event_type_focus(self) -> None:
        self.workspace.clear_event_type_focus()
        central = self.window.centralWidget()
        if central is not None:
            central.setFocus(Qt.FocusReason.OtherFocusReason)

    def _set_event_type_lamp(self, state: str) -> None:
        self.workspace.set_event_type_lamp(state)

    def _set_save_state(self, state: str) -> None:
        self.save_state = state
        if state in ("missing", "saved", "failed"):
            self.last_stable_save_state = state
        if hasattr(self.window, "set_save_state"):
            self.window.set_save_state(state)
        if hasattr(self.window, "set_annotation_file_available"):
            self.window.set_annotation_file_available(
                self.last_annotation_path is not None
                and self.last_annotation_path.exists()
            )
        if hasattr(self.window, "set_api_upload_available"):
            self.window.set_api_upload_available(self._annotation_file_exists())

    def _annotation_file_exists(self) -> bool:
        return (
            self.last_annotation_path is not None
            and self.last_annotation_path.exists()
        )

    def _set_status_text(self, text: str) -> None:
        self.workspace.set_status_text(text)
        level, persistent = self._fullscreen_feedback_appearance(text)
        if level == "error":
            self.workspace.show_fullscreen_notification(text, level, persistent)

    @staticmethod
    def _fullscreen_feedback_appearance(text: str):  # type: ignore[no-untyped-def]
        normalized = text.strip().lower()
        if any(word in normalized for word in ("failed", "could not", "error")):
            return "error", True
        if any(
            phrase in normalized
            for phrase in (
                "updated",
                "saved",
                "up to date",
                "interval added",
                "interval edited",
                "interval deleted",
                "validated",
            )
        ):
            return "success", False
        return "info", False

    def _begin_slider_drag(self) -> None:
        self.pending_scrub_seconds = None
        self.workspace.begin_slider_drag()

    def _finish_slider_drag(self) -> None:
        self.pending_scrub_seconds = None
        self.scrub_seek_timer.stop()
        self.video_player.set_time_seconds(self.workspace.finish_slider_drag())

    def _preview_slider_position(self, value: int) -> None:
        self.workspace.preview_slider_position(value)
        if self._has_loaded_video(silent=True):
            self.pending_scrub_seconds = value / 1000.0
            if not self.scrub_seek_timer.isActive():
                self.scrub_seek_timer.start()

    def _preview_fullscreen_slider_position(self, seconds: float) -> None:
        if not self._has_loaded_video(silent=True):
            return
        self.pending_scrub_seconds = seconds
        if not self.scrub_seek_timer.isActive():
            self.scrub_seek_timer.start()

    def _finish_fullscreen_slider_seek(self, seconds: float) -> None:
        if not self._has_loaded_video(silent=True):
            return
        self.pending_scrub_seconds = None
        self.scrub_seek_timer.stop()
        self.playback_interval_end_seconds = None
        self.video_player.set_time_seconds(seconds)

    def _update_timeline(self, current_seconds: float) -> None:
        self.workspace.update_timeline(current_seconds, self.video_player.get_duration_seconds())

    def _apply_pending_scrub_seek(self) -> None:
        if self.pending_scrub_seconds is None or not self._has_loaded_video(silent=True):
            return
        seconds = self.pending_scrub_seconds
        self.pending_scrub_seconds = None
        self.video_player.set_time_seconds(seconds)

    def _stop_interval_playback_if_needed(self, current_seconds: float) -> None:
        if self.playback_interval_end_seconds is None:
            return
        if current_seconds >= self.playback_interval_end_seconds:
            self.video_player.pause()
            self.workspace.set_playback_active(False)
            self.playback_interval_end_seconds = None
            self._set_status_text("interval playback finished")

    def _finish_pending_interval_at_video_end(self, current_seconds: float) -> None:
        if self.is_completing_interval or not self.annotation_service.has_pending_interval():
            return
        duration_seconds = self.video_player.get_duration_seconds()
        start_seconds = self.annotation_service.pending_start_seconds
        if duration_seconds is None or duration_seconds <= 0:
            return
        if start_seconds is None or start_seconds >= duration_seconds:
            return

        reached_end = self.video_player.is_ended()
        if not reached_end and not self.video_player.is_playing():
            reached_end = current_seconds >= max(0.0, duration_seconds - 0.05)
        if reached_end:
            self._complete_pending_interval(duration_seconds, automatic=True)

    def _prepare_video_preview(self, position_seconds: float) -> None:
        self.video_player.play()
        if position_seconds > 0.001:
            QTimer.singleShot(700, lambda: self.video_player.set_time_seconds(position_seconds))
        QTimer.singleShot(950, self.video_player.pause)

    def _annotation_path_for_ui(self) -> Optional[Path]:
        if self.last_annotation_path is not None:
            return self.last_annotation_path
        if self.document is None:
            QMessageBox.warning(
                self.window,
                "No annotations",
                "No annotation JSON has been saved yet.",
            )
            return None
        annotation_path = self.project_service.annotation_path_for_video_name(
            self.document.video_name
        )
        if not annotation_path.exists():
            QMessageBox.warning(
                self.window,
                "No annotations",
                "No annotation JSON has been saved yet.",
            )
            return None
        return annotation_path

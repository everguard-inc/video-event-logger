import copy
import json
import time

from pathlib import Path
from typing import Optional

from PySide6.QtCore import QByteArray, Qt, QTimer
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtNetwork import QNetworkAccessManager, QNetworkReply, QNetworkRequest
from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QFileDialog,
    QLineEdit,
    QAbstractSpinBox,
    QTextEdit,
    QMessageBox,
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
    SAVED_LOCALLY,
    UploadOutcome,
    build_upload_request,
    classify_upload_response,
    validate_api_settings,
)
from video_event_logger.services.annotation_store import AnnotationStore, CorruptedAnnotationError
from video_event_logger.services.file_manager import show_file_in_folder
from video_event_logger.services.path_utils import is_supported_video
from video_event_logger.services.time_utils import seconds_to_hhmmss
from video_event_logger.services.validation import validate_document
from video_event_logger.tasks.event_logging.ui.help_dialog import AnnotatorHelpDialog
from video_event_logger.tasks.event_logging.ui.workspace import EventLoggingWorkspace
from video_event_logger.tasks.event_logging.ui.playlist_panel import AnnotationSourceDialog
from video_event_logger.ui.fullscreen_hud import FullscreenHud
from video_event_logger.ui.interval_dialog import IntervalDialog
from video_event_logger.ui.submit_dialog import SubmitDialog
from video_event_logger.ui.work_time_monitor import WorkTimeMonitor
from video_event_logger.ui.video_download_dialog import VideoDownloadDialog, auto_playlist_enabled
from video_event_logger.services.download_queue import DownloadQueue


class EventLoggingController:
    def __init__(self, window, workspace: EventLoggingWorkspace) -> None:  # type: ignore[no-untyped-def]
        self.window = window
        self.workspace = workspace
        self.video_player = self.workspace.video_player
        self.project_service = ProjectService(AnnotationStore())
        self.annotation_service = AnnotationService()
        self.current_video_path = None  # type: Optional[Path]
        self.download_dialog = None
        self.close_after_download = False
        self.download_queue = DownloadQueue(window, lambda: self.current_video_path)
        self.download_queue.completed.connect(self._download_completed)
        self.download_queue.idle.connect(self._download_stopped)
        self.download_queue.changed.connect(self._update_download_status)
        self.document = None  # type: Optional[AnnotationDocument]
        self.last_annotation_path = None  # type: Optional[Path]
        self.save_state = "missing"
        self.last_stable_save_state = "missing"
        self.active_event_type = DEFAULT_EVENT_TYPE
        self.is_applying_event_type = False
        self.is_completing_interval = False
        self.pending_scrub_seconds = None  # type: Optional[float]
        self._cancel_interval_playback()
        self.current_playback_speed = 1.0
        self.api_network_manager = QNetworkAccessManager(window)
        self.api_upload_reply = None  # type: Optional[QNetworkReply]
        self.submit_dialog = None  # type: Optional[SubmitDialog]
        self.upload_results = {}  # video path -> last UploadOutcome
        self.shortcuts = []
        self.interval_undo = []
        self.end_undo_entry = None
        self.export_paths = {}
        self.preview_generation = 0
        self.auto_advance_handled = False
        self.event_type_apply_timer = QTimer(window)
        self.event_type_apply_timer.setSingleShot(True)
        self.event_type_apply_timer.setInterval(2000)
        self.scrub_seek_timer = QTimer(window)
        self.scrub_seek_timer.setSingleShot(True)
        self.scrub_seek_timer.setInterval(90)
        self.scrub_seek_timer.timeout.connect(self._apply_pending_scrub_seek)
        self.interval_start_timer = QTimer(window)
        self.interval_start_timer.setInterval(25)
        self.interval_start_timer.timeout.connect(self._try_start_interval_playback)

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
        self.timer.setInterval(50)
        self.timer.timeout.connect(self._update_playback_labels)
        self.timer.start()
        self.work_time_monitor = WorkTimeMonitor(self)
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
        player_panel.cancel_interval_button.clicked.connect(self.cancel_pending_interval)
        player_panel.event_type_chosen.connect(self.choose_event_type)
        metadata_panel.submit_button.clicked.connect(self.upload_annotations)
        metadata_panel.settings_button.clicked.connect(self.window.show_connection_settings)
        details = intervals_panel.details
        details.applied.connect(self._apply_interval_details)
        details.playhead_provider = self.video_player.get_time_seconds
        details.frame_provider = self.video_player.get_frame_duration_seconds
        hud = getattr(self.video_player, "fullscreen_hud", None)
        if hud is not None:
            hud.play_pause_requested.connect(self._toggle_play_pause)
            hud.frame_step_requested.connect(
                lambda step: self._step_forward_frame() if step > 0 else self._step_backward_frame()
            )
            hud.speed_requested.connect(self._set_speed)
            hud.interval_start_requested.connect(self.set_interval_start)
            hud.interval_end_requested.connect(self.set_interval_end)
            hud.interval_cancel_requested.connect(self.cancel_pending_interval)

        intervals_panel.play_requested.connect(self._play_interval_at_row)
        intervals_panel.edit_requested.connect(self._edit_interval_at_row)
        intervals_panel.delete_requested.connect(self._delete_interval_at_row)
        intervals_panel.jump_requested.connect(self._jump_to_interval_start)
        timeline = player_panel.annotation_timeline
        timeline.track.bounds_changed.connect(self._edit_interval_bounds)
        timeline.track.selected.connect(intervals_panel.interval_table.selectRow)
        timeline.track.seek_requested.connect(self._finish_fullscreen_slider_seek)
        timeline.track.edit_requested.connect(self._edit_interval_at_row)
        timeline.track.play_requested.connect(self._play_interval_at_row)
        timeline.track.delete_requested.connect(self._delete_interval_at_row)
        intervals_panel.interval_table.itemSelectionChanged.connect(
            lambda: timeline.select_row(intervals_panel.selected_row())
        )
        playlist = self.workspace.playlist_panel
        playlist.add_videos.connect(self.open_video_file)
        playlist.add_folder.connect(self.open_video_folder)
        playlist.open_annotations.connect(self.open_annotations)
        playlist.activated.connect(self._activate_playlist_row)
        playlist.previous.connect(lambda: self._step_playlist(-1))
        playlist.next_video.connect(lambda: self._step_playlist(1))

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
        self._add_shortcut("E", self._hotkey_toggle_events_bar)

    def _add_shortcut(self, key_sequence: str, handler) -> None:  # type: ignore[no-untyped-def]
        shortcut = QShortcut(QKeySequence(key_sequence), self.window)
        shortcut.setContext(Qt.ShortcutContext.WindowShortcut)
        shortcut.activated.connect(handler)
        self.shortcuts.append(shortcut)

    def show_help(self) -> None:
        dialog = AnnotatorHelpDialog(self.window)
        dialog.exec()

    def open_video_file(self) -> None:
        paths, _ = QFileDialog.getOpenFileNames(
            self.window, "Open Videos", "", "Video files (*.mp4 *.mkv)"
        )
        if paths:
            self._add_videos([Path(path) for path in paths])

    def download_video(self) -> None:
        if self.download_dialog is None:
            dialog = VideoDownloadDialog(self.window.settings, self.download_queue, self.window)
            self.download_dialog = dialog
            dialog.open_requested.connect(self._open_video_path)
            dialog.playlist_requested.connect(self._add_download_to_playlist)
        self.download_dialog.show()
        self.download_dialog.raise_()
        self.download_dialog.activateWindow()

    def _add_download_to_playlist(self, path) -> None:
        self.workspace.playlist_panel.add_paths([path])
        self._set_status_text("Added to playlist: %s" % path.name)

    def _download_completed(self, path) -> None:
        if auto_playlist_enabled(self.window.settings):
            self.workspace.playlist_panel.add_paths([path])
            self._set_status_text("Video ready and added to the playlist: %s" % path.name)
            return
        self._set_status_text("Video ready: %s. Open Downloads to open it or add it to the playlist." % path.name)

    def _update_download_status(self) -> None:
        if hasattr(self.window, "download_status_button"):
            self.window.download_status_button.setText(self.download_queue.summary())

    def _download_stopped(self) -> None:
        if self.close_after_download:
            self.close_after_download = False
            QTimer.singleShot(0, self.window.close)

    def open_video_folder(self) -> None:
        directory = QFileDialog.getExistingDirectory(self.window, "Open Video Folder")
        if not directory:
            return
        self._open_video_folder(Path(directory))

    def _open_video_folder(self, directory: Path) -> None:
        try:
            paths = sorted((p for p in directory.iterdir() if p.is_file() and is_supported_video(p)),
                           key=lambda p: p.name.casefold())
        except OSError as exc:
            QMessageBox.warning(self.window, "Cannot open folder", str(exc))
            return
        if not paths:
            QMessageBox.information(self.window, "No videos", "This folder contains no MP4 or MKV videos.")
            return
        if self._add_videos(paths):
            self._record_recent("folder", directory)

    def _add_videos(self, paths) -> bool:
        paths = [path.resolve() for path in paths if is_supported_video(path)]
        if not paths:
            return False
        dialog = AnnotationSourceDialog(paths[0], self.window)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return False
        if not self._open_video_path(paths[0], dialog.annotation_path()):
            return False
        self.workspace.playlist_panel.add_paths(paths)
        # All explicitly selected videos belong in history, with the active one first.
        for path in reversed(paths):
            if path.is_file():
                self._record_recent("video", path)
        return True

    def _record_recent(self, kind, path, video=None) -> None:
        history = getattr(self.window, "recent_files", None)
        if history is not None:
            history.record(kind, path, video)

    def open_recent(self, entry) -> None:
        path = Path(entry["path"])
        if entry["kind"] == "video":
            self._open_video_path(path)
        elif entry["kind"] == "folder":
            self._open_video_folder(path)
        elif entry["kind"] == "annotations":
            video = Path(entry["video"])
            if video == self.current_video_path:
                self._open_annotations_path(path)
            else:
                self._open_video_path(video, path)

    def _save_before_switch(self) -> bool:
        if self.document is None:
            return True
        if self.annotation_service.has_pending_interval():
            QMessageBox.warning(self.window, "Interval active", "Finish the interval or cancel it with Q before switching video or annotations.")
            return False
        self.event_type_apply_timer.stop()
        self.active_event_type = self.workspace.event_type_text().strip() or DEFAULT_EVENT_TYPE
        return self._save_checkpoint("Current annotations saved.")

    def _read_import(self, path: Path, video_path: Path, duration=None):
        # Imported files are read without recovery renames or writes to their source.
        try:
            def reject_constant(value):
                raise ValueError("Invalid number: " + value)
            data = json.loads(path.read_text(encoding="utf-8"), parse_constant=reject_constant)
            if not isinstance(data, dict) or not isinstance(data.get("intervals"), list):
                raise ValueError("Expected an annotation JSON object with an intervals list.")
            if any(not isinstance(item, dict) or not all(key in item for key in ("start_time_seconds", "end_time_seconds")) for item in data["intervals"]):
                raise ValueError("Every interval must contain start_time_seconds and end_time_seconds.")
            document = AnnotationDocument.from_dict(data)
            original_name = document.video_name
            document.video_name = video_path.name
            if duration is not None:
                document.video_metadata.duration_seconds = duration
            errors = validate_document(document)
            if errors:
                raise ValueError("\n".join(errors))
            if original_name and original_name != video_path.name:
                answer = QMessageBox.question(self.window, "Different video name",
                    "These annotations name %s, but the selected video is %s. Use them for this video?" % (original_name, video_path.name),
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
                if answer != QMessageBox.StandardButton.Yes:
                    return None
            return document
        except (OSError, ValueError, TypeError, AttributeError, OverflowError) as exc:
            QMessageBox.warning(self.window, "Cannot open annotations", str(exc))
            return None

    def _open_video_path(self, video_path: Path, annotation_path: Optional[Path] = None, autoplay=False) -> bool:
        video_path = video_path.resolve()
        if getattr(self, "download_queue", None) is not None and self.download_queue.reserves_path(video_path):
            self._set_status_text("This file is being downloaded. Wait for the download to finish before opening it.")
            return False
        if not video_path.is_file() or not is_supported_video(video_path):
            QMessageBox.warning(self.window, "Cannot open video", "Select an existing MP4 or MKV file.\n%s" % video_path)
            return False
        if not self._save_before_switch():
            return False
        project = ProjectService(AnnotationStore(video_path))
        document = project.create_empty_document(video_path.name)
        if annotation_path is not None:
            document = self._read_import(annotation_path, video_path)
            if document is None:
                return False
        else:
            paths = project.existing_paths(video_path.name)
            legacy_paths = {}
            for old_key, source_key in (("legacy_annotation", "annotation"),
                                        ("legacy_backup", "backup"),
                                        ("legacy_autosave", "legacy_autosave")):
                if old_key in paths:
                    legacy_paths[source_key] = paths[old_key]
            legacy = project.existing_sources(legacy_paths)
            sources = project.existing_sources({key: value for key, value in paths.items() if not key.startswith("legacy_")})
            if not sources and legacy:
                answer = QMessageBox.question(self.window, "Existing annotations",
                    "Older annotations were found for this filename. Load them for this video?\n\n%s" % legacy[0],
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
                if answer == QMessageBox.StandardButton.Yes:
                    sources = legacy
            recovered = False
            for source in sources:
                try:
                    document = project.load_document(source, video_path.name)
                    document.video_name = video_path.name
                    if validate_document(document):
                        raise ValueError("Invalid saved annotation data")
                    recovered = True
                    break
                except (OSError, ValueError, TypeError, AttributeError, OverflowError, CorruptedAnnotationError) as exc:
                    QMessageBox.warning(self.window, "Cannot load saved annotations", "%s\n%s\nTrying the next recovery file, if available." % (source, exc))
                    document = project.create_empty_document(video_path.name)
            if sources and not recovered:
                return False
        if self.current_video_path == video_path and self.document is not None:
            document.active_work_seconds = max(document.active_work_seconds, self.document.active_work_seconds)
        self.preview_generation = getattr(self, "preview_generation", 0) + 1
        if not self.video_player.load_video(video_path):
            QMessageBox.warning(self.window, "VLC unavailable", "Could not initialize VLC playback.\n%s" % self.video_player.last_error)
            return False
        self.event_type_apply_timer.stop()
        self.scrub_seek_timer.stop()
        self.pending_scrub_seconds = None
        self._cancel_interval_playback()
        self.interval_undo = []
        self.auto_advance_handled = False
        self.current_video_path = video_path
        self.project_service = project
        self.document = document
        monitor = getattr(self, "work_time_monitor", None)
        if monitor is not None:
            monitor.attach(document)
        self.annotation_service.set_document(document)
        annotation_file = project.annotation_path_for_video_name(document.video_name)
        self.last_annotation_path = annotation_file if annotation_file.exists() else None
        self._set_video_loaded(True)
        self.window.set_video_rotation_degrees(self.video_player.rotation_degrees)
        self.workspace.player_panel.annotation_timeline.zoom.setValue(1)
        self.workspace.playlist_panel.add_paths([video_path])
        self.workspace.playlist_panel.set_current(video_path)
        self.workspace.playlist_panel.annotation_label.setText("Autosave in results folder\nUse Save Annotations to export.")
        self.workspace.playlist_panel.annotation_label.setToolTip(str(annotation_file))
        self._refresh_duration_metadata()
        self._refresh_ui_from_document()
        target = document.last_playback_position_seconds
        if self.document.video_metadata.duration_seconds is not None and target >= self.document.video_metadata.duration_seconds:
            target = 0.0
        self._save_checkpoint("Annotation JSON saved.", update_runtime=False)
        self._prepare_video_preview(0.0 if autoplay else target, autoplay=autoplay)
        self._clear_event_type_focus()
        self._record_recent("video", video_path)
        if annotation_path is not None:
            self._record_recent("annotations", annotation_path, video_path)
        return True

    def open_annotations(self) -> None:
        if not self._has_loaded_video():
            return
        path, _ = QFileDialog.getOpenFileName(self.window, "Open Annotations", str(self.current_video_path.parent), "Annotations (*.json)")
        if not path:
            return
        self._open_annotations_path(Path(path))

    def _open_annotations_path(self, path: Path) -> None:
        document = self._read_import(path, self.current_video_path, self.video_player.get_duration_seconds())
        if document is None or not self._save_before_switch():
            return
        # Reimporting intervals must not erase time already spent on this video
        # or double-count a previously exported copy of its counter.
        document.active_work_seconds = max(document.active_work_seconds, self.document.active_work_seconds)
        self.document = document
        self.work_time_monitor.attach(document)
        self.annotation_service.set_document(document)
        self.interval_undo = []
        self._cancel_interval_playback()
        self._refresh_duration_metadata()
        self._refresh_ui_from_document()
        self._save_checkpoint("Imported annotations saved to the working file.")
        self._record_recent("annotations", path, self.current_video_path)

    def _activate_playlist_row(self, row: int, autoplay=False) -> None:
        paths = self.workspace.playlist_panel.paths
        if 0 <= row < len(paths) and paths[row] != self.current_video_path:
            if not self._open_video_path(paths[row], autoplay=autoplay):
                self.workspace.playlist_panel.set_current(self.current_video_path)

    def _step_playlist(self, delta: int, autoplay=False) -> None:
        paths = self.workspace.playlist_panel.paths
        if self.current_video_path in paths:
            self._activate_playlist_row(paths.index(self.current_video_path) + delta, autoplay)

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
                self._refresh_recent_event_types()
        finally:
            self.is_applying_event_type = False

    def choose_event_type(self, event_type: str) -> None:
        self.workspace.set_event_type(event_type)
        self.apply_event_type()
        self._refresh_counts()

    def _apply_interval_details(self, row: int, start: float, end: float, event_type: str, comment: str) -> None:
        interval = self._interval_at_row(row)
        if interval is None:
            return
        self._cancel_interval_playback()
        previous = copy.deepcopy(self.document.intervals)
        try:
            self.annotation_service.update_interval_bounds(row, start, end)
            self.annotation_service.update_interval_details(row, event_type or DEFAULT_EVENT_TYPE, comment)
        except (InvalidIntervalIndexError, InvalidIntervalError) as exc:
            self.document.intervals = previous
            self._notify(str(exc) or "Start must be before End.", "error")
            self._refresh_table()
            return
        self.interval_undo.append(previous)
        self.interval_undo = self.interval_undo[-50:]
        self.end_undo_entry = None
        self._refresh_table()
        self._refresh_counts()
        self.workspace.intervals_panel.interval_table.selectRow(row)
        self._save_checkpoint("Interval #%d updated and saved. Ctrl+Z undoes it." % (row + 1))

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

    def _notify(self, text: str, level: str = "info") -> None:
        """Non-blocking feedback in both the status bar and the fullscreen HUD."""
        self._set_status_text(text)
        self.workspace.show_fullscreen_notification(text, level, False)

    def _complete_pending_interval(self, end_seconds: float, automatic: bool = False) -> None:
        if self.is_completing_interval:
            return
        start_seconds = self.annotation_service.pending_start_seconds
        if not self.annotation_service.has_pending_interval() or start_seconds is None:
            self._notify("No interval is active. Press A (Start) first.", "error")
            return
        if start_seconds >= end_seconds:
            self._notify(
                "End must be after Start (%s). Move forward and press D again."
                % seconds_to_hhmmss(start_seconds),
                "error",
            )
            return

        self.is_completing_interval = True
        try:
            event_type = self._current_event_type()
            comment = ""
            popup_enabled = self.workspace.show_popup_after_interval()
            if popup_enabled:
                was_playing = self.video_player.is_playing()
                self.video_player.pause()
                dialog = IntervalDialog(
                    start_seconds, end_seconds, event_type, self.window,
                    keep_recording_option=not automatic,
                )
                result = dialog.exec()
                if result != QDialog.DialogCode.Accepted:
                    if result == IntervalDialog.DISCARD or automatic:
                        self.annotation_service.cancel_pending_interval()
                        self.workspace.set_pending_interval_start(None)
                        self._notify("Interval discarded")
                    else:
                        # Keep recording: the start stays, nothing is saved yet.
                        self._notify(
                            "Still recording from %s. Press D at the real end."
                            % seconds_to_hhmmss(start_seconds),
                            "info",
                        )
                    if was_playing:
                        self.video_player.play()
                    return
                event_type, comment = dialog.values()

            try:
                self._remember_interval_edit()
                self.annotation_service.end_interval(end_seconds, event_type, comment)
            except (MissingIntervalStartError, InvalidIntervalError):
                self.interval_undo.pop()
                self._notify("The interval could not be saved. Check Start and End.", "error")
                return
            # Ctrl+Z right after End reopens this interval instead of deleting it.
            self.end_undo_entry = (self.interval_undo[-1], start_seconds)

            self.workspace.set_pending_interval_start(None)
            self._refresh_table()
            self._refresh_counts()
            if automatic:
                saved = self._save_checkpoint(
                    "Interval reached the end of the video and was saved."
                )
            else:
                saved = self._save_checkpoint(
                    "Interval added and saved. Ended too early? Ctrl+Z keeps recording."
                )
            if saved:
                self.workspace.show_fullscreen_notification(
                    "Interval added" if automatic else "Interval added · Ctrl+Z keeps recording",
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
        default_dir = str(self.current_video_path.parent) if self.current_video_path else ""
        default_dir = str(self.window.settings.value("annotations/export_directory", default_dir) or default_dir)
        destination, _ = QFileDialog.getSaveFileName(self.window, "Save Annotations", str(Path(default_dir) / (self.document.video_name + ".annotations.json")), "Annotations (*.json)")
        if not destination:
            return
        path = Path(destination)
        if not path.suffix:
            path = path.with_suffix(".json")
        if not self._save_checkpoint("Working annotations saved."):
            return
        try:
            self.project_service.store.export(self.document, path)
        except (OSError, ValueError) as exc:
            QMessageBox.warning(self.window, "Export failed", str(exc))
            return
        self.window.settings.setValue("annotations/export_directory", str(path.parent))
        self.export_paths[self.current_video_path] = path
        self._set_status_text("Annotations exported to %s" % path)
        self.workspace.playlist_panel.annotation_label.setText("Exported snapshot: %s\nUse Save Annotations again after editing." % path.name)
        self.workspace.playlist_panel.annotation_label.setToolTip(str(path))

    def show_annotation_file_in_folder(self) -> None:
        path = getattr(self, "export_paths", {}).get(self.current_video_path) or self._annotation_path_for_ui()
        if path is None:
            return
        show_file_in_folder(path)

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

        dialog = SubmitDialog(
            self.document.video_name,
            list(self.document.intervals),
            float(self.document.active_work_seconds or 0.0),
            self._has_next_video(),
            self.window,
        )
        dialog.submit_requested.connect(self._send_upload)
        dialog.cancel_upload_requested.connect(self._abort_upload)
        dialog.settings_requested.connect(self.window.show_connection_settings)
        dialog.next_video_requested.connect(lambda: self._step_playlist(1))
        dialog.finished.connect(lambda _result, current=dialog: self._submit_dialog_closed(current))
        self.submit_dialog = dialog
        dialog.open()

    def _has_next_video(self) -> bool:
        paths = self.workspace.playlist_panel.paths
        return self.current_video_path in paths and paths.index(self.current_video_path) + 1 < len(paths)

    def _submit_dialog_closed(self, dialog) -> None:  # type: ignore[no-untyped-def]
        if getattr(self, "submit_dialog", None) is dialog:
            self.submit_dialog = None
        dialog.deleteLater()

    def _abort_upload(self) -> None:
        if self.api_upload_reply is not None:
            self.api_upload_reply.abort()

    def _send_upload(self) -> None:
        if self.api_upload_reply is not None:
            return
        endpoint_url, token = self.window.api_connection_settings()
        settings_error = validate_api_settings(endpoint_url, token)
        annotation_path = self.last_annotation_path
        payload = None
        if settings_error is None and annotation_path is not None:
            try:
                payload = annotation_path.read_bytes()
            except OSError:
                payload = None
        dialog = getattr(self, "submit_dialog", None)
        if settings_error is not None or payload is None:
            outcome = UploadOutcome(
                "error",
                "Connection settings needed" if settings_error else "Annotation file unavailable",
                settings_error or "The annotation JSON could not be read. " + SAVED_LOCALLY,
                "", "", "settings" if settings_error else "close",
                "Annotation upload failed.",
            )
            self._show_upload_outcome(outcome)
            return

        request = build_upload_request(endpoint_url, token)
        reply = self.api_network_manager.post(request, QByteArray(payload))
        self.api_upload_reply = reply
        self.window.set_api_upload_available(False)
        self._set_status_text("Uploading annotations…")
        reply.finished.connect(
            lambda current_reply=reply: self._finish_api_upload(current_reply)
        )
        if dialog is not None:
            dialog.show_sending()

    def _finish_api_upload(self, reply: QNetworkReply) -> None:
        if reply is not self.api_upload_reply:
            reply.deleteLater()
            return
        self.api_upload_reply = None

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
        canceled = (
            status_code is None
            and network_error == QNetworkReply.NetworkError.OperationCanceledError
        )
        outcome = classify_upload_response(
            status_code, response_body, network_error_text, canceled
        )
        if self.current_video_path is not None and outcome.tone != "canceled":
            self.upload_results[self.current_video_path] = outcome
            playlist = self.workspace.playlist_panel
            if hasattr(playlist, "set_upload_state"):
                playlist.set_upload_state(self.current_video_path, outcome)
        self._show_upload_outcome(outcome)

    def _show_upload_outcome(self, outcome: UploadOutcome) -> None:
        self._set_status_text(outcome.status_text)
        dialog = getattr(self, "submit_dialog", None)
        if dialog is not None:
            if outcome.tone == "canceled":
                dialog.show_review()
                return
            dialog.show_result(outcome)
            return
        # No dialog (closed meanwhile): fall back to a plain message.
        if outcome.tone == "canceled":
            return
        text = outcome.lead + ("\n\n" + outcome.message if outcome.message else "")
        if outcome.tone == "error":
            QMessageBox.warning(self.window, outcome.title, text)
        else:
            QMessageBox.information(self.window, outcome.title, text)

    def close_event(self, event) -> None:  # type: ignore[no-untyped-def]
        downloads = getattr(self, "download_queue", None)
        if downloads is not None and downloads.busy:
            event.ignore()
            if self.close_after_download:
                return
            answer = QMessageBox.question(
                self.window, "Downloads are active",
                "Cancel all active and queued downloads and exit?\n"
                "Choose No to keep annotating and downloading.",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if answer == QMessageBox.StandardButton.Yes:
                self.close_after_download = True
                downloads.cancel_all()
            return
        if self.document is not None:
            self.event_type_apply_timer.stop()
            self.active_event_type = self.workspace.event_type_text().strip() or DEFAULT_EVENT_TYPE
            if not self._save_checkpoint("Current position saved."):
                event.ignore()
                return
        event.accept()

    def _delete_interval_at_row(self, row: int) -> None:
        if self.document is None:
            return
        try:
            self._remember_interval_edit()
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
            editable_times=True,
            duration_seconds=self.document.video_metadata.duration_seconds,
        )
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        event_type, comment = dialog.values()
        self._cancel_interval_playback()
        try:
            self._remember_interval_edit()
            start, end = dialog.time_values()
            self.annotation_service.update_interval_bounds(row, start, end)
            self.annotation_service.update_interval_details(row, event_type, comment)
        except (InvalidIntervalIndexError, InvalidIntervalError):
            return
        self._refresh_table()
        self._refresh_counts()
        self._save_checkpoint("Interval edited and annotations saved.")

    def _remember_interval_edit(self) -> None:
        document = getattr(self, "document", self.annotation_service.document)
        if document is None:
            return
        if not hasattr(self, "interval_undo"):
            self.interval_undo = []
        self.interval_undo.append(copy.deepcopy(document.intervals))
        self.interval_undo = self.interval_undo[-50:]
        self.end_undo_entry = None

    def _edit_interval_bounds(self, row: int, start: float, end: float) -> None:
        if self._interval_at_row(row) is None:
            return
        previous = copy.deepcopy(self.document.intervals)
        try:
            self.annotation_service.update_interval_bounds(row, start, end)
        except InvalidIntervalError as exc:
            QMessageBox.warning(self.window, "Invalid interval", str(exc))
            self._refresh_table()
            return
        self.interval_undo.append(previous)
        self.interval_undo = self.interval_undo[-50:]
        self.end_undo_entry = None
        self._cancel_interval_playback()
        self._refresh_table()
        self.workspace.intervals_panel.interval_table.selectRow(row)
        self._save_checkpoint("Interval boundaries saved.")

    def undo_interval_edit(self) -> None:
        if self._should_ignore_hotkey() or self.document is None or not self.interval_undo:
            return
        snapshot = self.interval_undo.pop()
        end_entry = getattr(self, "end_undo_entry", None)
        self.end_undo_entry = None
        if (
            end_entry is not None
            and end_entry[0] is snapshot
            and not self.annotation_service.has_pending_interval()
        ):
            # Undo of End: back to recording with the same start.
            start_seconds = end_entry[1]
            self.document.intervals = snapshot
            self.annotation_service.start_interval(start_seconds)
            self.workspace.set_pending_interval_start(start_seconds)
            self._cancel_interval_playback()
            self._refresh_table()
            self._refresh_counts()
            self._save_checkpoint(
                "Back to recording from %s. Press D at the real end."
                % seconds_to_hhmmss(start_seconds)
            )
            self.workspace.show_fullscreen_notification(
                "Back to recording from %s" % seconds_to_hhmmss(start_seconds),
                "info",
                False,
            )
            return
        self.document.intervals = snapshot
        self._cancel_interval_playback()
        self._refresh_table()
        self._refresh_counts()
        self._save_checkpoint("Interval change undone and saved.")

    def _cancel_interval_playback(self) -> None:
        pending = getattr(self, "pending_interval_playback", None)
        if pending and pending["temporary_rate"]:
            self.video_player.set_rate(self.current_playback_speed)
        self.playback_interval_end_seconds = None
        self.pending_interval_playback = None
        timer = getattr(self, "interval_start_timer", None)
        if timer is not None:
            timer.stop()

    def _play_interval_at_row(self, row: int) -> None:
        interval = self._interval_at_row(row)
        if interval is not None:
            self._position_interval(interval.start_time_seconds, interval.end_time_seconds, row, play=True)

    def _position_interval(self, start: float, end: float, row: int, play: bool) -> None:
        self._cancel_interval_playback()
        self.preview_generation = getattr(self, "preview_generation", 0) + 1
        ended = self.video_player.is_ended()
        self.pending_interval_playback = {
            "document": self.document, "row": row, "start": start, "end": end,
            "deadline": time.monotonic() + 2.0, "play": play,
            "phase": "opening" if ended else "seeking", "temporary_rate": ended,
        }
        if ended:
            # Ended inputs ignore seeks. Reopen at normal speed so even a short
            # clip cannot reach EOF again before the input is ready to pause.
            self.video_player.play()
            self.video_player.set_rate(1.0)
        else:
            self.video_player.pause()
            self.video_player.set_time_seconds(start)
        self._try_start_interval_playback()
        if self.pending_interval_playback is not None:
            self.interval_start_timer.start()

    def _try_start_interval_playback(self) -> None:
        request = self.pending_interval_playback
        if request is None:
            self.interval_start_timer.stop()
            return
        if request["document"] is not self.document:
            self._cancel_interval_playback()
            return
        if time.monotonic() >= request["deadline"]:
            self.video_player.pause()
            self._cancel_interval_playback()
            self._set_status_text("Could not seek to the interval boundary. Try Play again.")
            return
        if request["phase"] == "opening":
            if self.video_player.is_playing():
                self.video_player.pause()
                self.video_player.set_time_seconds(request["start"])
                request["phase"] = "seeking"
            return
        # libVLC seeks asynchronously. Do not arm the end check against the
        # previous playback position while the start seek is still pending.
        actual = self.video_player.get_time_seconds()
        span = request["end"] - request["start"]
        tolerance = min(0.05, span / 2) if span > 0 else 0.05
        if abs(actual - request["start"]) <= tolerance:
            self.interval_start_timer.stop()
            self.pending_interval_playback = None
            if request["temporary_rate"]:
                self.video_player.set_rate(self.current_playback_speed)
            self._update_timeline(request["start"])
            if request["play"]:
                self.playback_interval_end_seconds = request["end"]
                self.video_player.play()
                self.workspace.set_playback_active(True)
                self._set_status_text("playing interval %d" % (request["row"] + 1))
            else:
                self.workspace.set_playback_active(False)
                self._set_status_text("interval playback finished")

    def _jump_to_interval_start(self, row: int) -> None:
        interval = self._interval_at_row(row)
        if interval is None:
            return
        self._cancel_interval_playback()
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
        self._cancel_interval_playback()
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

    def _hotkey_toggle_events_bar(self) -> None:
        if self._should_ignore_hotkey() or not hasattr(self.window, "toggle_events_bar"):
            return
        self.window.toggle_events_bar()

    def _hotkey_cancel_pending_interval(self) -> None:
        if self._should_ignore_hotkey():
            return
        self.cancel_pending_interval()

    def cancel_pending_interval(self) -> None:
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
        self.workspace.player_panel.annotation_timeline.track.cancel_drag()
        if self.window.video_fullscreen_enabled:
            self.window.set_fullscreen(False)

    def _save_checkpoint(
        self,
        status_message: str,
        update_runtime: bool = True,
        quiet: bool = False,
    ) -> bool:
        if self.document is None:
            return False
        monitor = getattr(self, "work_time_monitor", None)
        if monitor is not None:
            monitor.flush()
        if update_runtime:
            self._update_document_runtime_state()

        if not quiet:
            self._set_save_state("saving")
        try:
            errors = validate_document(self.document)
            if errors:
                raise ValueError("\n".join(errors))
            self.last_annotation_path = self.project_service.save(self.document)
        except Exception as exc:
            self._set_save_state("failed")
            self._set_status_text("Annotation JSON save failed.")
            if not quiet:
                QMessageBox.warning(
                    self.window,
                    "JSON save failed",
                    "Could not save the annotation JSON. The previous valid file was kept.\n\n%s"
                    % exc,
                )
            return False

        if not quiet:
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
        self.workspace.intervals_panel.set_empty_hint_visible(not self.document.intervals)

    def _refresh_counts(self) -> None:
        if self.document is None:
            self.workspace.refresh_counts(0, {})
            return
        counts = self.annotation_service.event_counts()
        self.workspace.refresh_counts(len(self.document.intervals), counts)
        self._refresh_recent_event_types()


    def _refresh_recent_event_types(self) -> None:
        counts = {}
        for interval in self.document.intervals if self.document is not None else []:
            counts[interval.event_type] = counts.get(interval.event_type, 0) + 1
        ordered = sorted(counts, key=lambda name: (-counts[name], name))
        active = getattr(self, "active_event_type", DEFAULT_EVENT_TYPE)
        types = [active] + [name for name in ordered if name != active]
        types = [name for name in types if name and name != DEFAULT_EVENT_TYPE] or [active]
        self.workspace.player_panel.set_recent_event_types(types[:4], active)
    def _update_playback_labels(self) -> None:
        current = self.video_player.get_time_seconds()
        self._update_timeline(current)
        self._stop_interval_playback_if_needed(current)
        interaction_idle = (
            QApplication.activePopupWidget() is None
            and QApplication.activeModalWidget() is None
            and self.pending_interval_playback is None
            and self.workspace.player_panel.annotation_timeline.track.drag is None
        )
        if interaction_idle:
            self._finish_pending_interval_at_video_end(current)
        if interaction_idle and not self.is_completing_interval and self.video_player.is_ended() and not self.auto_advance_handled and self.workspace.playlist_panel.auto_next.isChecked():
            self.auto_advance_handled = True
            self._step_playlist(1, autoplay=True)
            return
        if self.video_player.is_playing():
            self.auto_advance_handled = False
        self._refresh_rotation_enabled()
        self.workspace.set_playback_active(self.video_player.is_playing())
        if self.document is not None:
            old_duration = self.document.video_metadata.duration_seconds
            self._refresh_duration_metadata()
            if self.document.video_metadata.duration_seconds != old_duration:
                self._update_timeline(current)

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
        self._cancel_interval_playback()
        if self.video_player.step_backward_frame():
            self._set_status_text("previous frame")
            self._refresh_rotation_enabled()

    def _step_forward_frame(self) -> None:
        if not self._has_loaded_video(silent=True):
            return
        self.workspace.notify_fullscreen_user_activity()
        self._cancel_interval_playback()
        if self.video_player.step_forward_frame():
            self._set_status_text("next frame")
            self._refresh_rotation_enabled()

    def _toggle_play_pause(self) -> None:
        self._cancel_interval_playback()
        self.workspace.notify_fullscreen_user_activity()
        if self.video_player.is_playing():
            self.video_player.pause()
            self.workspace.set_playback_active(False)
            self._cancel_interval_playback()
            self._refresh_rotation_enabled()
            return
        self._apply_current_speed()
        self.video_player.play()
        self.workspace.set_playback_active(True)
        self._refresh_rotation_enabled()
        QTimer.singleShot(100, self._apply_current_speed)

    def _apply_current_speed(self) -> None:
        self.video_player.set_rate(self.current_playback_speed)
        self.workspace.set_active_speed(self.current_playback_speed)

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
        return isinstance(focused_widget, (QLineEdit, QAbstractSpinBox, QTextEdit))

    def _current_event_type(self) -> str:
        return self.active_event_type.strip() or DEFAULT_EVENT_TYPE

    def _clear_event_type_focus(self) -> None:
        self.workspace.clear_event_type_focus()
        central = self.window.centralWidget()
        if central is not None:
            central.setFocus(Qt.FocusReason.OtherFocusReason)

    def _set_event_type_lamp(self, state: str) -> None:
        self.workspace.set_event_type_lamp(state)

    def _update_hud_info(self) -> None:
        hud = getattr(getattr(self, "video_player", None), "fullscreen_hud", None)
        if not isinstance(hud, FullscreenHud):
            return
        current = getattr(self, "current_video_path", None)
        if current is None:
            hud.set_info("")
            return
        parts = [current.name]
        paths = self.workspace.playlist_panel.paths
        if current in paths and len(paths) > 1:
            parts.append("%d / %d" % (paths.index(current) + 1, len(paths)))
        subtitle = list(parts[1:])
        document = getattr(self, "document", None)
        duration = document.video_metadata.duration_seconds if document is not None else None
        if duration:
            subtitle.append(seconds_to_hhmmss(duration).split(".")[0])
        work = document.active_work_seconds if document is not None else 0
        if work:
            subtitle.append("work %s" % seconds_to_hhmmss(float(work)).split(".")[0])
        result = getattr(self, "upload_results", {}).get(current)
        if result is not None:
            subtitle.append(result.title)
        if subtitle and len(parts) > 1:
            subtitle[0] = "Video " + subtitle[0].replace(" / ", " of ")
        self.workspace.metadata_panel.set_video_subtitle("  ·  ".join(subtitle))
        parts.append({
            "saved": "✓ Saved", "saving": "Saving…", "dirty": "Unsaved changes", "failed": "⚠ Save failed",
        }.get(getattr(self, "save_state", ""), ""))
        hud.set_info("  ·  ".join(part for part in parts if part))

    def _set_save_state(self, state: str) -> None:
        self.save_state = state
        self._update_hud_info()
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
        self._cancel_interval_playback()
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
        self._cancel_interval_playback()
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
        ended = self.video_player.is_ended()
        if current_seconds >= self.playback_interval_end_seconds or ended:
            end_seconds = self.playback_interval_end_seconds
            self._position_interval(end_seconds, end_seconds, -1, play=False)
            self._update_timeline(end_seconds)

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

    def _prepare_video_preview(self, position_seconds: float, autoplay=False) -> None:
        self.preview_generation = getattr(self, "preview_generation", 0) + 1
        generation = self.preview_generation
        def still_current():
            return generation == self.preview_generation
        self.video_player.play()
        if position_seconds > 0.001:
            QTimer.singleShot(700, lambda: self.video_player.set_time_seconds(position_seconds) if still_current() else None)
        if not autoplay:
            QTimer.singleShot(950, lambda: self.video_player.pause() if still_current() else None)

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

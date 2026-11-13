import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtCore import QPoint, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QDialog, QMessageBox

from video_event_logger.application.annotation_service import AnnotationService
from video_event_logger.domain.errors import InvalidIntervalError
from video_event_logger.models.annotation import AnnotationDocument
from video_event_logger.models.interval import Interval
from video_event_logger.services.annotation_store import AnnotationStore
from video_event_logger.services.validation import validate_document
from video_event_logger.tasks.event_logging.ui.annotation_timeline import IntervalTrack
from video_event_logger.ui.interval_dialog import IntervalDialog
from video_event_logger.ui.main_window import MainWindow


class NewWorkflowTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.directory = Path(temporary.name)
        for constant, suffix in (("RESULTS_DIR", "results"), ("LEGACY_AUTOSAVE_DIR", "autosave")):
            patcher = patch("video_event_logger.services.path_utils." + constant, self.directory / suffix)
            patcher.start()
            self.addCleanup(patcher.stop)
        settings = Mock()
        settings.value.side_effect = lambda key, default: default
        with patch("video_event_logger.ui.main_window.QSettings", return_value=settings):
            self.window = MainWindow()
        self.addCleanup(self.dispose_window)
        self.controller = self.window.controller
        self.controller.timer.stop()
        self.controller._prepare_video_preview = Mock()
        player = self.controller.video_player
        player.load_video = Mock(return_value=True)
        player.get_duration_seconds = Mock(return_value=100.0)
        player.get_time_seconds = Mock(return_value=0.0)
        player.is_playing = Mock(return_value=False)
        player.is_ended = Mock(return_value=False)
        player.set_time_seconds = Mock()
        self.video = self.directory / "clip.mp4"
        self.video.write_bytes(b"video content")
        self.assertTrue(self.controller._open_video_path(self.video))

    def dispose_window(self):
        self.controller.work_time_monitor.stop()
        self.window.deleteLater()

    def add_interval(self, start=10.0, end=20.0):
        self.controller.annotation_service.start_interval(start)
        self.controller.annotation_service.end_interval(end, "vehicle", "review")
        self.controller._refresh_table()

    def prepare_work_clock(self):
        monitor = self.controller.work_time_monitor
        monitor.timer.stop()
        now = [0.0]
        monitor.tracker.clock = lambda: now[0]
        monitor._foreground = Mock(return_value=True)
        monitor.attach(self.controller.document)
        return monitor, now

    def test_work_time_autosaves_without_intervals_and_restores_when_reopened(self):
        monitor, now = self.prepare_work_clock()
        for value in range(1, 31):
            now[0] = value
            monitor._tick()
        saved = json.loads(self.controller.last_annotation_path.read_text())
        self.assertEqual(saved["active_work_seconds"], 30)
        self.assertEqual(saved["intervals"], [])
        other = self.directory / "other.mp4"
        other.touch()
        self.assertTrue(self.controller._open_video_path(other))
        self.assertEqual(self.controller.document.active_work_seconds, 0)
        self.assertTrue(self.controller._open_video_path(self.video))
        self.assertEqual(self.controller.document.active_work_seconds, 30)

    def test_export_includes_time_since_last_timer_tick(self):
        monitor, now = self.prepare_work_clock()
        now[0] = 2.5
        output = self.directory / "export.json"
        with patch("video_event_logger.tasks.event_logging.controller.QFileDialog.getSaveFileName",
                   return_value=(str(output), "")):
            self.controller.validate_and_save()
        self.assertEqual(json.loads(output.read_text())["active_work_seconds"], 2.5)

    def test_importing_annotations_preserves_work_time_without_adding_it_twice(self):
        monitor, now = self.prepare_work_clock()
        self.controller.document.active_work_seconds = 200
        source = self.directory / "incoming.json"
        data = self.controller.document.to_dict()
        data["active_work_seconds"] = 100
        source.write_text(json.dumps(data))
        self.controller._open_annotations_path(source)
        self.assertEqual(self.controller.document.active_work_seconds, 200)
        self.controller._open_annotations_path(source)
        self.assertEqual(self.controller.document.active_work_seconds, 200)
        self.assertTrue(self.controller._open_video_path(self.video, source))
        self.assertEqual(self.controller.document.active_work_seconds, 200)
        self.assertEqual(json.loads(source.read_text())["active_work_seconds"], 100)

    def test_work_timer_detects_input_and_excludes_download_window(self):
        from PySide6.QtCore import QEvent
        from PySide6.QtGui import QKeyEvent
        monitor, now = self.prepare_work_clock()
        monitor.tracker.last_activity = -1000
        self.controller.download_video()
        download = self.controller.download_dialog
        event = QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_A, Qt.KeyboardModifier.NoModifier)
        monitor.eventFilter(download.url_input, event)
        self.assertEqual(monitor.tracker.last_activity, -1000)
        monitor.eventFilter(self.window.workspace, event)
        self.assertEqual(monitor.tracker.last_activity, 0)
        download.reject()

    def test_work_time_foreground_scope(self):
        monitor = self.controller.work_time_monitor
        editor = IntervalDialog(1, 2, "event", self.window)
        with patch("video_event_logger.ui.work_time_monitor.QApplication.applicationState",
                   return_value=Qt.ApplicationState.ApplicationActive) as state, \
                patch("video_event_logger.ui.work_time_monitor.QApplication.activeWindow",
                      return_value=editor) as active, \
                patch.object(self.window, "isVisible", return_value=True), \
                patch.object(self.window, "isMinimized", return_value=False) as minimized:
            self.assertTrue(monitor._foreground())
            minimized.return_value = True
            self.assertFalse(monitor._foreground())
            minimized.return_value = False
            state.return_value = Qt.ApplicationState.ApplicationInactive
            self.assertFalse(monitor._foreground())
            state.return_value = Qt.ApplicationState.ApplicationActive
            self.controller.download_video()
            active.return_value = self.controller.download_dialog
            self.assertFalse(monitor._foreground())
            self.controller.download_dialog.reject()
        editor.deleteLater()

    @patch("video_event_logger.tasks.event_logging.controller.QMessageBox.warning")
    def test_work_time_autosave_failure_keeps_counter_and_does_not_interrupt(self, warning):
        monitor, now = self.prepare_work_clock()
        original = self.controller.last_annotation_path.read_bytes()
        with patch.object(self.controller.project_service, "save", side_effect=OSError("disk full")):
            for value in range(1, 31):
                now[0] = value
                monitor._tick()
        self.assertEqual(self.controller.document.active_work_seconds, 30)
        self.assertEqual(self.controller.last_annotation_path.read_bytes(), original)
        warning.assert_not_called()

    def test_same_name_videos_keep_separate_autosaves_and_restore_intervals(self):
        self.add_interval()
        first_output = self.controller.last_annotation_path
        second = self.directory / "other" / "clip.mp4"
        second.parent.mkdir()
        second.touch()
        self.assertTrue(self.controller._open_video_path(second))
        self.assertNotEqual(first_output, self.controller.last_annotation_path)
        self.assertEqual(self.controller.document.intervals, [])
        self.assertTrue(self.controller._open_video_path(self.video))
        self.assertEqual(len(self.controller.document.intervals), 1)
        self.assertEqual(self.controller.document.intervals[0].start_time_seconds, 10.0)
        self.assertEqual(len(self.window.workspace.playlist_panel.paths), 2)

    @patch("video_event_logger.tasks.event_logging.controller.QMessageBox.warning")
    def test_failed_checkpoint_and_pending_interval_block_switch(self, warning):
        second = self.directory / "second.mp4"
        second.touch()
        self.controller.annotation_service.start_interval(5)
        self.assertFalse(self.controller._open_video_path(second))
        self.assertEqual(self.controller.current_video_path, self.video.resolve())
        self.controller.annotation_service.cancel_pending_interval()
        with patch.object(self.controller.project_service, "save", side_effect=OSError("disk full")):
            self.assertFalse(self.controller._open_video_path(second))
        self.assertEqual(self.controller.current_video_path, self.video.resolve())

    def test_export_explicit_destination_is_snapshot_and_does_not_change_autosave(self):
        self.add_interval()
        working = self.controller.last_annotation_path
        output = self.directory / "delivery" / "chosen.json"
        with patch("video_event_logger.tasks.event_logging.controller.QFileDialog.getSaveFileName", return_value=(str(output), "")):
            self.controller.validate_and_save()
        self.assertTrue(output.exists())
        self.assertEqual(self.controller.last_annotation_path, working)
        self.controller._edit_interval_bounds(0, 12, 22)
        self.assertEqual(json.loads(output.read_text())["intervals"][0]["start_time_seconds"], 10)
        self.assertEqual(json.loads(working.read_text())["intervals"][0]["start_time_seconds"], 12)
        self.assertNotIn(str(self.directory), output.read_text())

    def test_cancel_export_creates_no_delivery_file(self):
        with patch("video_event_logger.tasks.event_logging.controller.QFileDialog.getSaveFileName", return_value=("", "")):
            self.controller.validate_and_save()
        self.assertEqual(self.controller.export_paths, {})

    def test_import_shows_intervals_and_never_modifies_source(self):
        data = AnnotationDocument.empty(self.video.name)
        data.intervals = [Interval.create(1, 11, 23, "person", "shared")]
        source = self.directory / "received.json"
        source.write_text(json.dumps(data.to_dict()))
        original = source.read_bytes()
        with patch("video_event_logger.tasks.event_logging.controller.QFileDialog.getOpenFileName", return_value=(str(source), "")):
            self.controller.open_annotations()
        self.assertEqual(self.window.workspace.intervals_panel.interval_table.rowCount(), 1)
        self.assertEqual(len(self.window.workspace.player_panel.annotation_timeline.track.intervals), 1)
        self.controller._edit_interval_bounds(0, 12, 24)
        self.assertEqual(source.read_bytes(), original)
        self.assertFalse(source.with_suffix(".json.bak").exists())

    @patch("video_event_logger.tasks.event_logging.controller.QMessageBox.warning")
    def test_invalid_import_preserves_document_and_source(self, warning):
        self.add_interval()
        source = self.directory / "bad.json"
        for payload in ('{"intervals": [null]}', '{"intervals":[{"start_time_seconds":0,"end_time_seconds":NaN}]}', '{"intervals":[{"start_time_seconds":0,"end_time_seconds":101}]}', 'broken'):
            source.write_text(payload)
            with patch("video_event_logger.tasks.event_logging.controller.QFileDialog.getOpenFileName", return_value=(str(source), "")):
                self.controller.open_annotations()
            self.assertEqual(self.controller.document.intervals[0].start_time_seconds, 10)
            self.assertEqual(source.read_text(), payload)

    def test_edge_edit_updates_table_autosave_and_undo(self):
        self.add_interval()
        self.controller._edit_interval_bounds(0, 12.345, 24.678)
        interval = self.controller.document.intervals[0]
        self.assertEqual(interval.start_time_hhmmss, "00:00:12.345")
        self.assertEqual(self.window.workspace.intervals_panel.interval_table.item(0, 2).text(), "00:00:24.678")
        self.window.workspace.setFocus()
        self.controller.undo_interval_edit()
        self.assertEqual(self.controller.document.intervals[0].start_time_seconds, 10)
        self.assertEqual(json.loads(self.controller.last_annotation_path.read_text())["intervals"][0]["end_time_seconds"], 20)

    def press_end_at(self, seconds):
        self.controller.video_player.get_time_seconds.return_value = seconds
        self.window.workspace.setFocus()
        self.controller.set_interval_end()

    def test_undo_right_after_end_returns_to_recording_with_same_start(self):
        self.window.workspace.set_show_popup_after_interval(False)
        self.controller.video_player.get_time_seconds.return_value = 12.5
        self.controller.set_interval_start()
        self.press_end_at(14.0)
        self.assertEqual(len(self.controller.document.intervals), 1)
        self.assertFalse(self.controller.annotation_service.has_pending_interval())

        self.controller.undo_interval_edit()

        self.assertEqual(self.controller.document.intervals, [])
        self.assertEqual(self.controller.annotation_service.pending_start_seconds, 12.5)
        saved = json.loads(self.controller.last_annotation_path.read_text())
        self.assertEqual(saved["intervals"], [])
        self.press_end_at(19.0)
        interval = self.controller.document.intervals[0]
        self.assertEqual((interval.start_time_seconds, interval.end_time_seconds), (12.5, 19.0))

    def test_undo_after_a_later_edit_is_a_normal_undo(self):
        self.window.workspace.set_show_popup_after_interval(False)
        self.controller.video_player.get_time_seconds.return_value = 10.0
        self.controller.set_interval_start()
        self.press_end_at(20.0)
        self.controller._edit_interval_bounds(0, 11.0, 20.0)
        self.controller.undo_interval_edit()
        self.assertEqual(self.controller.document.intervals[0].start_time_seconds, 10.0)
        self.assertFalse(self.controller.annotation_service.has_pending_interval())

    def test_popup_escape_keeps_recording_and_discard_drops_interval(self):
        self.window.workspace.set_show_popup_after_interval(True)
        self.controller.video_player.get_time_seconds.return_value = 5.0
        self.controller.set_interval_start()
        with patch("video_event_logger.tasks.event_logging.controller.IntervalDialog.exec",
                   return_value=QDialog.DialogCode.Rejected):
            self.press_end_at(7.0)
        self.assertEqual(self.controller.annotation_service.pending_start_seconds, 5.0)
        self.assertEqual(self.controller.document.intervals, [])
        with patch("video_event_logger.tasks.event_logging.controller.IntervalDialog.exec",
                   return_value=IntervalDialog.DISCARD):
            self.press_end_at(9.0)
        self.assertFalse(self.controller.annotation_service.has_pending_interval())
        self.assertEqual(self.controller.document.intervals, [])

    @patch("video_event_logger.tasks.event_logging.controller.QMessageBox.warning")
    def test_end_without_start_does_not_open_a_modal(self, warning):
        self.press_end_at(3.0)
        warning.assert_not_called()
        self.assertEqual(self.controller.document.intervals, [])

    def test_playlist_shows_current_and_submit_status(self):
        from video_event_logger.services.annotation_api import classify_upload_response
        panel = self.window.workspace.playlist_panel
        self.assertIn("In progress", panel.list.item(0).text())
        panel.set_upload_state(self.video, classify_upload_response(201, b'{"status":"no_events"}'))
        self.assertIn("\u2713 Marked as reviewed", panel.list.item(0).text())
        panel.set_upload_state(self.video, classify_upload_response(503, b""))
        self.assertIn("Submit failed", panel.list.item(0).text())

    def test_details_panel_applies_exact_bounds_with_undo(self):
        self.add_interval()
        self.controller._refresh_counts()
        panel = self.window.workspace.intervals_panel
        panel.interval_table.selectRow(0)
        details = panel.details
        self.assertEqual(details.row, 0)
        details.start_input.setValue(10.5)
        details.end_input.setValue(21.25)
        details.type_input.setText("forklift")
        details.apply_button.click()
        interval = self.controller.document.intervals[0]
        self.assertEqual((interval.start_time_seconds, interval.end_time_seconds, interval.event_type), (10.5, 21.25, "forklift"))
        saved = json.loads(self.controller.last_annotation_path.read_text())
        self.assertEqual(saved["intervals"][0]["end_time_seconds"], 21.25)
        self.window.workspace.setFocus()
        self.controller.undo_interval_edit()
        self.assertEqual(self.controller.document.intervals[0].start_time_seconds, 10)
        details.start_input.setValue(30)
        self.assertFalse(details.apply_button.isEnabled())

    def test_type_chips_switch_the_event_type_for_new_intervals(self):
        self.add_interval()
        self.controller._refresh_counts()
        chips = self.window.workspace.player_panel.type_chip_buttons
        vehicle = next(chip for chip in chips if "vehicle" in chip.text())
        vehicle.click()
        self.assertEqual(self.controller.active_event_type, "vehicle")
        self.assertEqual(self.controller.document.current_event_type, "vehicle")

    def test_auto_next_is_opt_in_and_starts_next_video(self):
        second = self.directory / "second.mkv"
        second.touch()
        self.window.workspace.playlist_panel.add_paths([second])
        self.controller.video_player.is_ended.return_value = True
        self.controller._update_playback_labels()
        self.assertEqual(self.controller.current_video_path, self.video.resolve())
        self.window.workspace.playlist_panel.auto_next.setChecked(True)
        self.controller._update_playback_labels()
        self.assertEqual(self.controller.current_video_path, second.resolve())
        self.controller._prepare_video_preview.assert_called_with(0.0, autoplay=True)

    def test_auto_next_waits_for_modal_edit_or_active_drag(self):
        second = self.directory / "second.mp4"
        second.touch()
        panel = self.window.workspace.playlist_panel
        panel.add_paths([second])
        panel.auto_next.setChecked(True)
        self.controller.video_player.is_ended.return_value = True
        with patch("video_event_logger.tasks.event_logging.controller.QApplication.activeModalWidget", return_value=object()):
            self.controller._update_playback_labels()
        self.assertEqual(self.controller.current_video_path, self.video.resolve())
        with patch("video_event_logger.tasks.event_logging.controller.QApplication.activePopupWidget", return_value=object()):
            self.controller._update_playback_labels()
        self.assertEqual(self.controller.current_video_path, self.video.resolve())
        track = self.window.workspace.player_panel.annotation_timeline.track
        track.drag = (0, "start", 1, 2)
        self.controller._update_playback_labels()
        self.assertEqual(self.controller.current_video_path, self.video.resolve())
        track.drag = None
        self.controller._update_playback_labels()
        self.assertEqual(self.controller.current_video_path, second.resolve())

    def test_events_bar_preference_and_fullscreen_visibility(self):
        panel = self.window.workspace.player_panel
        self.window.events_bar_action.setChecked(False)
        self.window.settings.setValue.assert_any_call("appearance/events_bar", False)
        self.assertTrue(panel.annotation_timeline.isHidden())
        panel.set_video_only_mode(True)
        panel.set_video_only_mode(False)
        self.assertTrue(panel.annotation_timeline.isHidden())
        self.window.events_bar_action.setChecked(True)
        self.assertFalse(panel.annotation_timeline.isHidden())
        panel.set_video_only_mode(True)
        self.assertTrue(panel.annotation_timeline.isHidden())
        panel.set_video_only_mode(False)
        self.assertFalse(panel.annotation_timeline.isHidden())

    def test_fullscreen_events_bar_has_independent_preference_and_keeps_edits(self):
        panel = self.window.workspace.player_panel
        self.add_interval()
        self.window.events_bar_action.setChecked(False)
        self.window.fullscreen_events_bar_action.setChecked(True)
        self.window.settings.setValue.assert_any_call("appearance/fullscreen_events_bar", True)
        self.assertTrue(panel.annotation_timeline.isHidden())
        panel.set_video_only_mode(True)
        self.assertFalse(panel.annotation_timeline.isHidden())
        self.assertTrue(panel.timeline_slider.isHidden())
        hud = panel.video_player.fullscreen_hud
        # Floating overlay: the video keeps the whole player area.
        self.assertIs(panel.annotation_timeline.parentWidget(), hud.events_panel)
        panel.annotation_timeline.track.bounds_changed.emit(0, 12, 22)
        self.assertEqual(self.controller.document.intervals[0].start_time_seconds, 12)
        panel.set_video_only_mode(False)
        self.assertTrue(panel.annotation_timeline.isHidden())
        self.assertEqual(panel.annotation_timeline.track.intervals[0].end_time_seconds, 22)
        self.assertIs(panel.annotation_timeline.parentWidget(), panel)
        self.assertIs(panel.layout().itemAt(1).widget(), panel.annotation_timeline)

    def test_e_toggles_the_events_bar_of_the_current_view(self):
        self.window.workspace.setFocus()
        self.window.set_events_bar_enabled(True)
        self.controller._hotkey_toggle_events_bar()
        self.assertFalse(self.window.events_bar_enabled)
        self.window.video_fullscreen_enabled = True
        self.window.set_fullscreen_events_bar_enabled(False)
        self.controller._hotkey_toggle_events_bar()
        self.assertTrue(self.window.fullscreen_events_bar_enabled)
        self.window.video_fullscreen_enabled = False

    def test_recent_video_reopens_working_edits_not_original_import(self):
        source = self.directory / "received.json"
        document = AnnotationDocument.empty(self.video.name)
        document.intervals = [Interval.create(1, 10, 20, "event", "")]
        source.write_text(json.dumps(document.to_dict()))
        self.controller._open_annotations_path(source)
        self.controller._edit_interval_bounds(0, 12, 24)
        self.controller.open_recent(self.window.recent_files.items("video")[0])
        self.assertEqual(self.controller.document.intervals[0].start_time_seconds, 12)
        self.assertEqual(json.loads(source.read_text())["intervals"][0]["start_time_seconds"], 10)

    def test_recent_annotations_open_with_their_video(self):
        source = self.directory / "received.json"
        document = AnnotationDocument.empty(self.video.name)
        document.intervals = [Interval.create(1, 10, 20, "event", "")]
        source.write_text(json.dumps(document.to_dict()))
        self.controller._open_annotations_path(source)
        entry = self.window.recent_files.items("annotations")[0]
        second = self.directory / "second.mp4"
        second.touch()
        self.controller._open_video_path(second)
        self.controller.open_recent(entry)
        self.assertEqual(self.controller.current_video_path, self.video.resolve())
        self.assertEqual(self.controller.document.intervals[0].start_time_seconds, 10)

    @patch("video_event_logger.tasks.event_logging.controller.QMessageBox.warning")
    def test_missing_recent_video_preserves_current_document_and_history(self, warning):
        self.add_interval()
        history = list(self.window.recent_files.entries)
        self.controller.open_recent({"kind": "video", "path": str(self.directory / "missing.mp4")})
        warning.assert_called_once()
        self.assertEqual(self.window.recent_files.entries, history)
        self.assertEqual(len(self.controller.document.intervals), 1)

    def test_recent_menu_reopens_selected_path_and_clear_keeps_playlist(self):
        self.window._refresh_recent_menu()
        video_menu = self.window.recent_menu.actions()[0].menu()
        with patch.object(self.controller, "open_recent") as reopen:
            video_menu.actions()[0].trigger()
        reopen.assert_called_once_with(self.window.recent_files.items("video")[0])
        self.window.recent_menu.actions()[-1].trigger()
        self.assertEqual(self.window.recent_files.entries, [])
        self.assertEqual(self.window.workspace.playlist_panel.paths, [self.video.resolve()])
        self.assertTrue(self.video.exists())

    @patch("video_event_logger.tasks.event_logging.controller.AnnotationSourceDialog")
    def test_folder_history_records_accepted_selection_and_cancel_changes_nothing(self, dialog):
        from PySide6.QtWidgets import QDialog
        second = self.directory / "second.mkv"
        second.touch()
        before = list(self.window.recent_files.entries)
        dialog.return_value.exec.return_value = QDialog.DialogCode.Rejected
        self.controller._open_video_folder(self.directory)
        self.assertEqual(self.window.recent_files.entries, before)
        self.assertEqual(len(self.window.workspace.playlist_panel.paths), 1)
        dialog.return_value.exec.return_value = QDialog.DialogCode.Accepted
        dialog.return_value.annotation_path.return_value = None
        self.controller._open_video_folder(self.directory)
        self.assertEqual(len(self.window.recent_files.items("folder")), 1)
        self.assertEqual(len(self.window.recent_files.items("video")), 2)
        self.assertEqual(self.window.recent_files.items("video")[0]["path"], str(self.video.resolve()))

    def test_playlist_close_and_view_toggle_preserve_selection(self):
        playlist = self.window.workspace.playlist_panel
        playlist.close_button.click()
        self.assertTrue(playlist.isHidden())
        self.assertFalse(self.window.playlist_action.isChecked())
        self.window.settings.setValue.assert_any_call("appearance/playlist", False)
        self.window.playlist_action.setChecked(True)
        self.assertFalse(playlist.isHidden())
        self.assertEqual(playlist.paths, [self.video.resolve()])
        self.assertEqual(playlist.list.currentRow(), 0)

    def test_fullscreen_playlist_edge_delay_menu_and_restore(self):
        from PySide6.QtCore import QPoint
        self.window.show()
        self.window.set_fullscreen(True)
        self.app.processEvents()
        workspace = self.window.workspace
        overlay = workspace.playlist_overlay
        overlay.timer.stop()
        width = workspace.video_player.width()
        edge = workspace.mapToGlobal(QPoint(1, 100))
        far = workspace.mapToGlobal(QPoint(workspace.width() - 10, 100))
        with patch("video_event_logger.tasks.event_logging.ui.playlist_overlay.QApplication.activeWindow", return_value=self.window), patch("video_event_logger.tasks.event_logging.ui.playlist_overlay.QCursor.pos", return_value=far) as cursor, patch("video_event_logger.tasks.event_logging.ui.playlist_overlay.time.monotonic", return_value=0) as clock:
            overlay.check_pointer()
            self.assertFalse(overlay.frame.isVisible())
            cursor.return_value = edge
            overlay.check_pointer()
            self.assertTrue(overlay.frame.isVisible())
            self.assertEqual(workspace.video_player.width(), width)
            cursor.return_value = far
            with patch("video_event_logger.tasks.event_logging.ui.playlist_overlay.QApplication.activePopupWidget", return_value=object()):
                overlay.check_pointer()
                self.assertIsNone(overlay.outside_since)
            overlay.check_pointer()
            clock.return_value = 0.2
            overlay.check_pointer()
            self.assertTrue(overlay.frame.isVisible())
            clock.return_value = 0.5
            overlay.check_pointer()
            self.assertFalse(overlay.frame.isVisible())
            cursor.return_value = edge
            self.window.set_playlist_enabled(False)
            overlay.check_pointer()
            self.assertFalse(overlay.frame.isVisible())
            self.window.set_playlist_enabled(True)
        self.window.set_fullscreen(False)
        self.app.processEvents()
        self.assertFalse(overlay.frame.isVisible())
        self.assertFalse(overlay.timer.isActive())
        self.assertIs(workspace.horizontal_splitter.widget(1), workspace.playlist_panel)
        self.assertTrue(workspace.playlist_panel.isVisible())
        self.assertEqual(workspace.playlist_panel.list.currentRow(), 0)
        self.window.hide()

    def test_fullscreen_playlist_close_stays_disabled_after_exit(self):
        self.window.show()
        self.window.set_fullscreen(True)
        self.app.processEvents()
        self.window.workspace.playlist_panel.close_button.click()
        self.window.set_fullscreen(False)
        self.assertTrue(self.window.workspace.playlist_panel.isHidden())
        self.assertFalse(self.window.playlist_action.isChecked())
        self.window.hide()

    def test_wheel_zoom_keeps_time_under_cursor_and_shift_pans(self):
        from PySide6.QtCore import QPointF
        from PySide6.QtGui import QWheelEvent
        timeline = self.window.workspace.player_panel.annotation_timeline
        self.window.show()
        self.window.workspace.update_timeline(10, 100)
        self.app.processEvents()
        viewport = timeline.scroll.viewport()
        point = QPoint(viewport.width() * 2 // 3, 30)
        horizontal = timeline.scroll.horizontalScrollBar()
        anchor = timeline.track.time_for_x(point.x())
        def wheel(delta, modifiers=Qt.KeyboardModifier.NoModifier):
            event = QWheelEvent(QPointF(point), QPointF(viewport.mapToGlobal(point)), QPoint(), QPoint(0, delta), Qt.MouseButton.NoButton, modifiers, Qt.ScrollPhase.NoScrollPhase, False)
            self.app.sendEvent(viewport, event)
            self.app.processEvents()
        wheel(120)
        self.assertEqual(timeline.zoom.value(), 2)
        self.assertAlmostEqual(timeline.track.time_for_x(point.x() + horizontal.value()), anchor, delta=0.1)
        wheel(240)
        self.assertEqual(timeline.zoom.value(), 4)
        self.assertAlmostEqual(timeline.track.time_for_x(point.x() + horizontal.value()), anchor, delta=0.1)
        before = horizontal.value()
        wheel(-120, Qt.KeyboardModifier.ShiftModifier)
        self.assertGreater(horizontal.value(), before)
        self.assertEqual(timeline.zoom.value(), 4)
        wheel(-9999)
        self.assertEqual(timeline.zoom.value(), 1)
        self.assertEqual(horizontal.value(), 0)
        self.window.hide()

    def test_events_height_drag_persists_and_exposes_more_lanes_in_fullscreen(self):
        from PySide6.QtCore import QEvent, QPointF
        from PySide6.QtGui import QMouseEvent
        timeline = self.window.workspace.player_panel.annotation_timeline
        self.window.set_fullscreen_events_bar_enabled(True)
        self.window.show()
        self.window.set_fullscreen(True)
        self.app.processEvents()
        timeline.track.set_intervals([Interval.create(i + 1, 1, 30, "event", "") for i in range(8)])
        self.app.processEvents()
        before = timeline.height()
        overflow = timeline.scroll.verticalScrollBar().maximum()
        handle = timeline.resize_handle
        start = handle.mapToGlobal(QPoint(20, 3))
        end = start - QPoint(0, 140)
        for kind, point, button, buttons in (
            (QEvent.Type.MouseButtonPress, start, Qt.MouseButton.LeftButton, Qt.MouseButton.LeftButton),
            (QEvent.Type.MouseMove, end, Qt.MouseButton.NoButton, Qt.MouseButton.LeftButton),
            (QEvent.Type.MouseButtonRelease, end, Qt.MouseButton.LeftButton, Qt.MouseButton.NoButton),
        ):
            event = QMouseEvent(kind, QPointF(handle.mapFromGlobal(point)), QPointF(point), button, buttons, Qt.KeyboardModifier.NoModifier)
            self.app.sendEvent(handle, event)
            self.app.processEvents()
        self.assertGreater(timeline.height(), before)
        self.assertLess(timeline.scroll.verticalScrollBar().maximum(), overflow)
        self.window.settings.setValue.assert_any_call("appearance/events_bar_height", timeline.user_height)
        saved = timeline.user_height
        self.window.set_fullscreen(False)
        self.app.processEvents()
        timeline.track.set_intervals([])
        self.assertEqual(timeline.user_height, saved)
        self.window.hide()

    def test_track_context_actions_and_left_double_click_use_selected_interval(self):
        from PySide6.QtCore import QTimer
        from PySide6.QtGui import QContextMenuEvent
        self.add_interval()
        self.add_interval(30, 40)
        self.window.show()
        self.window.workspace.update_timeline(0, 100)
        self.app.processEvents()
        track = self.window.workspace.player_panel.annotation_timeline.track
        point = track.rect_for_row(1).center().toPoint()
        for label, signal in (("Play", track.play_requested), ("Edit", track.edit_requested), ("Delete", track.delete_requested)):
            # Observe dispatch without opening an editor or deleting this fixture.
            signal.disconnect()
            received = []
            signal.connect(received.append)
            def choose():
                menu = track.context_menu
                next(action for action in menu.actions() if action.text() == label).trigger()
                menu.close()
            QTimer.singleShot(0, choose)
            event = QContextMenuEvent(QContextMenuEvent.Reason.Mouse, point, track.mapToGlobal(point))
            self.app.sendEvent(track, event)
            self.assertEqual(received, [1])
            self.assertEqual(self.window.workspace.selected_interval_row(), 1)
        edits = []
        track.edit_requested.disconnect()
        track.edit_requested.connect(edits.append)
        QTest.mouseDClick(track, Qt.MouseButton.RightButton, pos=point)
        self.assertEqual(edits, [])
        QTest.mouseDClick(track, Qt.MouseButton.LeftButton, pos=point)
        self.assertEqual(edits, [1])
        self.window.hide()

    def test_playlist_and_events_height_preferences_restore_on_startup(self):
        settings = Mock()
        values = {"appearance/playlist": False, "appearance/events_bar_height": 240}
        settings.value.side_effect = lambda key, default: values.get(key, default)
        with patch("video_event_logger.ui.main_window.QSettings", return_value=settings):
            restored = MainWindow()
        self.addCleanup(restored.deleteLater)
        restored.controller.timer.stop()
        self.assertFalse(restored.playlist_action.isChecked())
        self.assertTrue(restored.workspace.playlist_panel.isHidden())
        self.assertEqual(restored.workspace.player_panel.annotation_timeline.user_height, 240)

    def test_download_completion_adds_to_playlist_only_when_opted_in(self):
        downloaded = self.directory / "opted.mp4"
        downloaded.touch()
        self.window.settings.value.side_effect = (
            lambda key, default=None: True if key == "downloads/auto_playlist" else default
        )
        self.controller._download_completed(downloaded)
        self.assertIn(downloaded.resolve(), self.window.workspace.playlist_panel.paths)
        self.assertEqual(self.controller.current_video_path, self.video.resolve())

    def test_download_completion_never_switches_video_or_adds_to_playlist_implicitly(self):
        downloaded = self.directory / "downloaded.mp4"
        downloaded.touch()
        self.controller.download_video()
        dialog = self.controller.download_dialog
        self.assertFalse(dialog.isModal())
        self.controller._download_completed(downloaded)
        self.assertNotIn(downloaded.resolve(), self.window.workspace.playlist_panel.paths)
        self.assertEqual(self.controller.current_video_path, self.video.resolve())
        dialog.playlist_requested.emit(downloaded)
        self.assertIn(downloaded.resolve(), self.window.workspace.playlist_panel.paths)
        self.assertEqual(self.controller.current_video_path, self.video.resolve())
        dialog.open_requested.emit(downloaded)
        self.assertEqual(self.controller.current_video_path, downloaded.resolve())

    def test_download_window_can_be_hidden_and_reopened_from_status(self):
        self.controller.download_video()
        dialog = self.controller.download_dialog
        dialog.reject()
        self.assertFalse(dialog.isVisible())
        self.window.download_status_button.click()
        self.assertIs(self.controller.download_dialog, dialog)
        self.assertTrue(dialog.isVisible())

    def test_background_transfer_keeps_annotation_editing_and_minimize_available(self):
        import threading
        import time
        release = threading.Event()
        def transfer(downloader):
            release.wait(3)
            return downloader.destination
        queue = self.controller.download_queue
        with patch("video_event_logger.services.download_queue.VideoDownloader.run", transfer):
            self.window.show()
            self.controller.download_video()
            dialog = self.controller.download_dialog
            job = queue.enqueue("https://example.org/video.mp4", self.directory / "download.mp4")
            QTest.qWait(30)
            worker = queue.worker
            try:
                dialog.background_button.click()
                self.assertIsNone(self.app.activeModalWidget())
                self.add_interval(1, 5)
                self.controller._edit_interval_bounds(0, 2, 6)
                self.assertTrue(self.controller._save_checkpoint("Saved while downloading"))
                self.window.showMinimized()
                QTest.qWait(10)
                self.assertIs(queue.worker, worker)
                self.assertFalse(worker.cancel_event.is_set())
                self.window.showNormal()
                self.controller.download_video()
                self.assertIs(self.controller.download_dialog, dialog)
            finally:
                release.set()
                deadline = time.monotonic() + 5
                while queue.busy and time.monotonic() < deadline:
                    QTest.qWait(10)
            self.assertFalse(queue.busy)
            self.assertEqual(job.state, "completed")
            self.assertEqual(self.controller.current_video_path, self.video.resolve())
            self.assertEqual(self.controller.document.intervals[0].start_time_seconds, 2)
            self.assertIn("ready", self.window.download_status_button.text())
            self.window.hide()

    def test_cannot_open_queued_destination_even_with_download_window_hidden(self):
        target = self.directory / "queued.mp4"
        target.touch()
        queue = self.controller.download_queue
        queue.enqueue("https://example.org/video.mp4", target, overwrite=True)
        try:
            with patch.object(self.controller, "_save_before_switch") as save:
                self.assertFalse(self.controller._open_video_path(target))
                save.assert_not_called()
        finally:
            queue.cancel_all()

    def test_exit_declined_keeps_queue_and_confirmed_exit_waits_for_cleanup(self):
        import threading
        import time
        from video_event_logger.services.video_download import DownloadCancelled
        entered, release = threading.Event(), threading.Event()
        def transfer(downloader):
            entered.set()
            downloader.cancel.wait(3)
            release.wait(3)
            raise DownloadCancelled()
        queue = self.controller.download_queue
        with patch("video_event_logger.services.download_queue.VideoDownloader.run", transfer), \
                patch("video_event_logger.tasks.event_logging.controller.QMessageBox.question") as question, \
                patch.object(self.window, "close") as close:
            queue.enqueue("https://example.org/video.mp4", self.directory / "download.mp4")
            queued = queue.enqueue("https://example.org/next.mp4", self.directory / "next.mp4")
            deadline = time.monotonic() + 5
            while not entered.is_set() and time.monotonic() < deadline:
                QTest.qWait(10)
            worker = queue.worker
            question.return_value = QMessageBox.StandardButton.No
            event = Mock()
            self.controller.close_event(event)
            event.ignore.assert_called_once()
            self.assertFalse(worker.cancel_event.is_set())
            question.return_value = QMessageBox.StandardButton.Yes
            self.controller.close_event(Mock())
            self.assertTrue(worker.cancel_event.is_set())
            self.assertEqual(queued.state, "cancelled")
            close.assert_not_called()
            self.assertTrue(queue.busy)
            release.set()
            deadline = time.monotonic() + 5
            while not close.called and time.monotonic() < deadline:
                QTest.qWait(10)
            self.assertFalse(queue.busy)
            close.assert_called_once()

    def test_track_height_and_progress_axis_match_at_fit(self):
        from PySide6.QtWidgets import QStyle, QStyleOptionSlider
        panel = self.window.workspace.player_panel
        timeline = panel.annotation_timeline
        self.window.show()
        for rows in (0, 1, 2, 4, 6):
            for zoom in (1, 4):
                intervals = [Interval.create(i + 1, 2, 20, "event", "") for i in range(rows)]
                timeline.track.set_intervals(intervals)
                timeline.zoom.setValue(zoom)
                panel.update_timeline(12.979, 55.123)
                self.app.processEvents()
                self.assertEqual(timeline.scroll.verticalScrollBar().maximum() > 0, rows > 4)
                self.assertEqual(timeline.scroll.horizontalScrollBar().maximum() > 0, zoom > 1)
                if zoom == 1:
                    option = QStyleOptionSlider()
                    panel.timeline_slider.initStyleOption(option)
                    handle = panel.timeline_slider.style().subControlRect(QStyle.ComplexControl.CC_Slider, option, QStyle.SubControl.SC_SliderHandle, panel.timeline_slider)
                    track_x = timeline.track.mapTo(panel, QPoint(0, 0)).x() + timeline.track.x_for_time(12.979)
                    slider_x = panel.timeline_slider.mapTo(panel, QPoint(0, 0)).x() + handle.center().x()
                    self.assertAlmostEqual(track_x, slider_x, delta=1.5)
        self.window.hide()

    def test_interval_playback_overshoot_seeks_exact_end_and_updates_both_bars(self):
        self.add_interval(10, 20)
        self.controller.video_player.get_time_seconds.return_value = 10.0
        self.controller._play_interval_at_row(0)
        self.controller.video_player.set_time_seconds.reset_mock()
        self.controller._stop_interval_playback_if_needed(21.75)
        self.controller.video_player.set_time_seconds.assert_called_once_with(20)
        panel = self.window.workspace.player_panel
        self.assertEqual(panel.annotation_timeline.track.position, 20)
        self.assertEqual(panel.timeline_slider.value(), 20000)
        self.assertIsNone(self.controller.playback_interval_end_seconds)

    def test_interval_replay_waits_for_start_seek_before_arming_end(self):
        self.add_interval(10, 20)
        player = self.controller.video_player
        player.play = Mock()
        player.get_time_seconds.return_value = 20.0
        self.controller._play_interval_at_row(0)
        self.controller._stop_interval_playback_if_needed(20)
        player.play.assert_not_called()
        self.assertIsNotNone(self.controller.pending_interval_playback)
        player.get_time_seconds.return_value = 10.0
        self.controller._try_start_interval_playback()
        player.play.assert_called_once()
        self.assertEqual(self.controller.playback_interval_end_seconds, 20)

    def test_user_seek_cancels_pending_interval_start(self):
        self.add_interval(10, 20)
        player = self.controller.video_player
        player.play = Mock()
        player.get_time_seconds.return_value = 0.0
        self.controller._play_interval_at_row(0)
        self.controller._finish_fullscreen_slider_seek(5)
        self.controller._try_start_interval_playback()
        player.play.assert_not_called()
        self.assertIsNone(self.controller.pending_interval_playback)
        self.assertFalse(self.controller.interval_start_timer.isActive())

    def test_vlc_ended_with_stale_time_restores_interval_end(self):
        self.controller.playback_interval_end_seconds = 20
        player = self.controller.video_player
        player.play = Mock()
        player.is_ended.return_value = True
        self.controller._stop_interval_playback_if_needed(10)
        player.play.assert_called_once()
        player.is_playing.return_value = True
        self.controller._try_start_interval_playback()
        player.get_time_seconds.return_value = 20
        self.controller._try_start_interval_playback()
        player.set_time_seconds.assert_called_with(20)
        self.assertEqual(self.window.workspace.player_panel.annotation_timeline.track.position, 20)
        self.assertIsNone(self.controller.playback_interval_end_seconds)

    def test_endpoint_restore_does_not_auto_advance_playlist(self):
        second = self.directory / "next.mp4"
        second.touch()
        playlist = self.window.workspace.playlist_panel
        playlist.add_paths([second])
        playlist.auto_next.setChecked(True)
        self.controller.playback_interval_end_seconds = 20
        self.controller.video_player.is_ended.return_value = True
        self.controller.video_player.play = Mock()
        self.controller._update_playback_labels()
        self.assertEqual(self.controller.current_video_path, self.video.resolve())
        self.assertIsNotNone(self.controller.pending_interval_playback)

    def test_folder_only_adds_direct_supported_files(self):
        folder = self.directory / "batch"
        folder.mkdir()
        for name in ("B.MP4", "a.mkv", "notes.txt"):
            (folder / name).touch()
        (folder / "nested").mkdir()
        (folder / "nested" / "hidden.mp4").touch()
        with patch("video_event_logger.tasks.event_logging.controller.QFileDialog.getExistingDirectory", return_value=str(folder)), patch.object(self.controller, "_add_videos") as add:
            self.controller.open_video_folder()
        self.assertEqual([p.name for p in add.call_args.args[0]], ["a.mkv", "B.MP4"])

    def test_export_rejects_alias_to_source_video(self):
        alias = self.directory / "danger.json"
        alias.symlink_to(self.video)
        with self.assertRaises(ValueError):
            self.controller.project_service.store.export(self.controller.document, alias)
        self.assertEqual(self.video.read_bytes(), b"video content")

    def test_legacy_annotation_is_offered_without_overwriting_legacy(self):
        other = self.directory / "legacy.mp4"
        other.touch()
        legacy_store = AnnotationStore()
        old = AnnotationDocument.empty(other.name)
        old.intervals = [Interval.create(1, 2, 3, "event", "")]
        legacy_path = legacy_store.save(old)
        original = legacy_path.read_bytes()
        with patch("video_event_logger.tasks.event_logging.controller.QMessageBox.question", return_value=QMessageBox.StandardButton.Yes):
            self.assertTrue(self.controller._open_video_path(other))
        self.assertEqual(len(self.controller.document.intervals), 1)
        self.assertNotEqual(self.controller.last_annotation_path, legacy_path)
        self.assertEqual(legacy_path.read_bytes(), original)

    def test_open_multiple_videos_with_optional_annotations(self):
        second = self.directory / "second.mp4"
        second.touch()
        imported = AnnotationDocument.empty(self.video.name)
        imported.intervals = [Interval.create(1, 4, 8, "event", "")]
        source = self.directory / "shared.json"
        source.write_text(json.dumps(imported.to_dict()))
        with patch("video_event_logger.tasks.event_logging.controller.QFileDialog.getOpenFileNames", return_value=([str(self.video), str(second)], "")), patch("video_event_logger.tasks.event_logging.controller.AnnotationSourceDialog") as dialog:
            dialog.return_value.exec.return_value = 1
            dialog.return_value.annotation_path.return_value = source
            self.controller.open_video_file()
        self.assertEqual(len(self.window.workspace.playlist_panel.paths), 2)
        self.assertEqual(self.controller.document.intervals[0].start_time_seconds, 4)

    def test_semantically_invalid_primary_does_not_replace_valid_backup(self):
        self.add_interval()
        self.controller._save_checkpoint("saved")
        self.controller._save_checkpoint("saved twice")
        path = self.controller.last_annotation_path
        backup = path.with_name(path.name + ".bak")
        original_backup = backup.read_bytes()
        path.write_text('{"video_name":"clip.mp4","intervals":[],"last_playback_position_seconds":-1}')
        self.controller.project_service.store.save(self.controller.document)
        self.assertEqual(backup.read_bytes(), original_backup)

    @patch("video_event_logger.tasks.event_logging.controller.QMessageBox.warning")
    def test_all_invalid_recovery_files_abort_open_without_wiping_data(self, warning):
        second = self.directory / "second.mp4"
        second.touch()
        store = AnnotationStore(second)
        path = store.annotation_path_for_video_name(second.name)
        invalid = '{"video_name":"second.mp4","last_playback_position_seconds":-1}'
        path.write_text(invalid)
        self.assertFalse(self.controller._open_video_path(second))
        self.assertEqual(self.controller.current_video_path, self.video.resolve())
        self.assertEqual(path.read_text(), invalid)

    def test_import_uses_numeric_times_instead_of_stale_display_strings(self):
        source = self.directory / "shared.json"
        source.write_text(json.dumps({"video_name": "clip.mp4", "intervals": [{"start_time_seconds": 5, "end_time_seconds": 6, "start_time_hhmmss": ["invalid"], "end_time_hhmmss": "stale"}]}))
        document = self.controller._read_import(source, self.video, 100)
        self.assertEqual(document.intervals[0].start_time_hhmmss, "00:00:05.000")
        self.assertEqual(document.intervals[0].end_time_hhmmss, "00:00:06.000")


class TimelineInteractionTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def make_track(self):
        track = IntervalTrack()
        track.duration = 100
        track.resize(1020, 120)
        track.set_intervals([Interval.create(1, 10, 30, "car", ""), Interval.create(2, 20, 40, "person", "")])
        track.show()
        self.app.processEvents()
        self.addCleanup(track.close)
        return track

    def test_overlap_lanes_and_edge_drag_commit_only_on_release(self):
        track = self.make_track()
        self.assertNotEqual(track.lanes[0], track.lanes[1])
        changed = Mock()
        track.bounds_changed.connect(changed)
        point = QPoint(round(track.x_for_time(10)), track.HEADER + 10)
        QTest.mousePress(track, Qt.MouseButton.LeftButton, pos=point)
        QTest.mouseMove(track, QPoint(round(track.x_for_time(15)), point.y()))
        changed.assert_not_called()
        self.assertEqual(track.intervals[0].start_time_seconds, 10)
        QTest.mouseRelease(track, Qt.MouseButton.LeftButton, pos=QPoint(round(track.x_for_time(15)), point.y()))
        changed.assert_called_once()
        self.assertEqual(changed.call_args.args[0], 0)
        self.assertAlmostEqual(changed.call_args.args[1], 15.0, delta=0.05)
        self.assertEqual(changed.call_args.args[2], 30.0)

    def test_right_edge_clamps_at_duration_and_escape_cancels(self):
        track = self.make_track()
        changed = Mock()
        track.bounds_changed.connect(changed)
        point = QPoint(round(track.x_for_time(30)), track.HEADER + 10)
        QTest.mousePress(track, Qt.MouseButton.LeftButton, pos=point)
        QTest.mouseMove(track, QPoint(track.width() + 100, point.y()))
        self.assertEqual(track.bounds(0)[1], 100)
        QTest.keyClick(track, Qt.Key.Key_Escape)
        QTest.mouseRelease(track, Qt.MouseButton.LeftButton)
        changed.assert_not_called()
        self.assertEqual(track.bounds(0), (10, 30))

    def test_body_drag_does_not_move_interval(self):
        track = self.make_track()
        changed = Mock()
        track.bounds_changed.connect(changed)
        point = QPoint(round(track.x_for_time(20)), track.HEADER + 10)
        QTest.mousePress(track, Qt.MouseButton.LeftButton, pos=point)
        QTest.mouseMove(track, QPoint(point.x() + 100, point.y()))
        QTest.mouseRelease(track, Qt.MouseButton.LeftButton)
        self.assertIsNone(track.drag)
        changed.assert_not_called()

    def test_playlist_double_click_activates_once(self):
        from video_event_logger.tasks.event_logging.ui.playlist_panel import PlaylistPanel
        panel = PlaylistPanel()
        panel.add_paths([Path("/tmp/a.mp4"), Path("/tmp/b.mkv")])
        panel.resize(300, 400)
        panel.show()
        self.app.processEvents()
        activated = Mock()
        panel.activated.connect(activated)
        point = panel.list.visualItemRect(panel.list.item(1)).center()
        QTest.mouseClick(panel.list.viewport(), Qt.MouseButton.LeftButton, pos=point)
        QTest.mouseDClick(panel.list.viewport(), Qt.MouseButton.LeftButton, pos=point)
        activated.assert_called_once_with(1)
        panel.close()

    def test_exact_time_dialog_accepts_milliseconds_and_rejects_reversed_bounds(self):
        dialog = IntervalDialog(10, 20, "event", editable_times=True, duration_seconds=100)
        dialog.start_input.setValue(12.345)
        dialog.end_input.setValue(24.678)
        self.assertEqual(dialog.time_values(), (12.345, 24.678))
        dialog.start_input.setValue(30)
        with patch("video_event_logger.ui.interval_dialog.QMessageBox.warning") as warning:
            dialog.accept()
        warning.assert_called_once()
        self.assertNotEqual(dialog.result(), dialog.DialogCode.Accepted)


class BoundsValidationTest(unittest.TestCase):
    def test_invalid_bounds_leave_original_interval_unchanged(self):
        document = AnnotationDocument.empty("video.mp4")
        document.video_metadata.duration_seconds = 100
        document.intervals = [Interval.create(1, 10, 20, "event", "")]
        service = AnnotationService()
        service.set_document(document)
        for start, end in ((-1, 20), (20, 10), (1, 101), (10, 10.0001), (float("nan"), 20)):
            with self.assertRaises(InvalidIntervalError):
                service.update_interval_bounds(0, start, end)
            self.assertEqual(document.intervals[0].start_time_seconds, 10)
        document.intervals[0].end_time_seconds = float("nan")
        self.assertTrue(validate_document(document))

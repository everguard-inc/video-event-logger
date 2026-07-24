import os
import unittest
from unittest.mock import Mock, patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QLineEdit, QWidget

from video_event_logger.tasks.event_logging.ui.metadata_panel import MetadataPanel
from video_event_logger.tasks.event_logging.ui.player_panel import PlayerPanel
from video_event_logger.ui.api_settings_dialog import ApiSettingsDialog
from video_event_logger.ui.main_window import MainWindow
from video_event_logger.ui.theme import DARK_STYLE_SHEET, LIGHT_STYLE_SHEET, apply_theme


class UiFeedbackTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.application = QApplication.instance() or QApplication([])

    def make_player_panel(self) -> PlayerPanel:
        with patch(
            "video_event_logger.tasks.event_logging.ui.player_panel.VideoPlayer",
            side_effect=lambda parent=None: QWidget(parent),
        ):
            return PlayerPanel()

    def test_connection_settings_has_wide_url_and_token_visibility_control(self) -> None:
        dialog = ApiSettingsDialog(
            "https://example.org/api/v1/annotations",
            "secret-token",
        )
        self.addCleanup(dialog.deleteLater)

        self.assertGreaterEqual(dialog.minimumWidth(), 780)
        self.assertGreaterEqual(dialog.endpoint_input.minimumWidth(), 620)
        self.assertGreaterEqual(dialog.endpoint_input.maxLength(), 256)
        self.assertEqual(
            dialog.token_input.echoMode(),
            QLineEdit.EchoMode.Password,
        )
        self.assertEqual(
            dialog.token_visibility_action.toolTip(),
            "Show token",
        )

        dialog.token_visibility_action.trigger()

        self.assertEqual(
            dialog.token_input.echoMode(),
            QLineEdit.EchoMode.Normal,
        )
        self.assertEqual(
            dialog.token_visibility_action.toolTip(),
            "Hide token",
        )

    def test_pending_interval_shows_start_time_and_highlights_controls(self) -> None:
        panel = self.make_player_panel()

        panel.set_pending_interval_start(12.345)

        self.assertEqual(panel.interval_state_label.text(), "INTERVAL ACTIVE — start 00:00:12.345")
        self.assertEqual(panel.set_start_button.text(), "Start set")
        self.assertEqual(panel.interval_state_label.property("feedbackState"), "active")
        self.assertEqual(panel.set_start_button.property("feedbackState"), "start-set")
        self.assertEqual(panel.set_end_button.property("feedbackState"), "finish-ready")

    def test_clearing_pending_interval_restores_ready_state(self) -> None:
        panel = self.make_player_panel()
        panel.set_pending_interval_start(12.345)

        panel.set_pending_interval_start(None)

        self.assertEqual(panel.interval_state_label.text(), "Interval: ready")
        self.assertEqual(panel.set_start_button.text(), "Start")
        self.assertEqual(panel.interval_state_label.property("feedbackState"), "ready")
        self.assertEqual(panel.set_start_button.property("feedbackState"), "idle")
        self.assertEqual(panel.set_end_button.property("feedbackState"), "idle")

    def test_playback_and_selected_speed_have_active_button_states(self) -> None:
        panel = self.make_player_panel()

        self.assertTrue(panel.speed_1_button.isChecked())
        self.assertFalse(panel.speed_4_button.isChecked())
        self.assertFalse(panel.play_pause_button.isChecked())

        panel.set_active_speed(4.0)
        panel.set_playback_active(True)

        self.assertFalse(panel.speed_1_button.isChecked())
        self.assertTrue(panel.speed_4_button.isChecked())
        self.assertTrue(panel.play_pause_button.isChecked())
        self.assertEqual(panel.play_pause_button.toolTip(), "Pause playback")

    def test_timeline_does_not_duplicate_speed_as_text(self) -> None:
        panel = self.make_player_panel()

        self.assertFalse(hasattr(panel, "timeline_speed_label"))

    def test_theme_switch_is_not_shown_on_player_panel(self) -> None:
        panel = self.make_player_panel()

        self.assertFalse(hasattr(panel, "dark_mode_toggle"))

    def test_fullscreen_control_is_not_shown_on_player_panel(self) -> None:
        panel = self.make_player_panel()

        self.assertFalse(hasattr(panel, "fullscreen_button"))

    def test_video_only_fullscreen_hides_player_chrome(self) -> None:
        panel = self.make_player_panel()

        panel.set_video_only_mode(True)

        self.assertTrue(panel.timeline_slider.isHidden())
        self.assertTrue(panel.play_pause_button.isHidden())
        self.assertTrue(panel.interval_state_label.isHidden())
        self.assertFalse(panel.video_player.isHidden())

        panel.set_video_only_mode(False)

        self.assertFalse(panel.timeline_slider.isHidden())
        self.assertFalse(panel.play_pause_button.isHidden())

    def test_rotation_control_is_not_shown_on_player_panel(self) -> None:
        panel = self.make_player_panel()

        self.assertFalse(hasattr(panel, "rotate_button"))
        self.assertFalse(hasattr(panel, "timeline_rotation_label"))

    def test_theme_switch_applies_bright_and_dark_styles(self) -> None:
        apply_theme(self.application, True)
        self.assertEqual(self.application.styleSheet(), DARK_STYLE_SHEET)

        apply_theme(self.application, False)
        self.assertEqual(self.application.styleSheet(), LIGHT_STYLE_SHEET)

    def test_metadata_panel_keeps_only_video_and_event_type_feedback(self) -> None:
        panel = MetadataPanel()

        self.assertTrue(hasattr(panel, "video_name_label"))
        self.assertTrue(hasattr(panel, "event_type_input"))
        self.assertFalse(hasattr(panel, "open_button"))
        self.assertFalse(hasattr(panel, "show_popup_checkbox"))
        self.assertFalse(hasattr(panel, "result_status_lamp"))
        self.assertFalse(hasattr(panel, "autosave_status_lamp"))

    @patch("video_event_logger.ui.main_window.EventLoggingController")
    @patch("video_event_logger.ui.main_window.QSettings")
    def test_popup_preference_is_loaded_and_saved(
        self,
        settings_type: Mock,
        controller_type: Mock,
    ) -> None:
        settings = Mock()
        settings.value.side_effect = (
            lambda key, default: False
            if key == "annotation/show_popup_after_interval"
            else default
        )
        settings_type.return_value = settings
        window = MainWindow()
        self.addCleanup(window.deleteLater)

        self.assertFalse(window.workspace.show_popup_after_interval())
        self.assertFalse(window.interval_popup_action.isChecked())

        settings.setValue.reset_mock()
        window.interval_popup_action.setChecked(True)

        settings.setValue.assert_called_once_with(
            "annotation/show_popup_after_interval",
            True,
        )
        self.assertTrue(window.show_popup_after_interval_enabled)

    @patch("video_event_logger.ui.main_window.EventLoggingController")
    @patch("video_event_logger.ui.main_window.QSettings")
    def test_file_actions_are_in_menu_and_disabled_before_video_load(
        self,
        settings_type: Mock,
        controller_type: Mock,
    ) -> None:
        settings = Mock()
        settings.value.side_effect = lambda key, default: default
        settings_type.return_value = settings
        window = MainWindow()
        self.addCleanup(window.deleteLater)

        self.assertTrue(window.open_video_action.isEnabled())
        self.assertFalse(window.validate_save_action.isEnabled())
        self.assertFalse(window.show_annotation_file_action.isEnabled())
        self.assertFalse(hasattr(window, "api_menu"))
        self.assertTrue(window.connection_settings_action.isEnabled())
        self.assertFalse(window.upload_annotations_action.isEnabled())
        self.assertIn(window.upload_annotations_action, window.file_menu.actions())
        self.assertNotIn(
            window.upload_annotations_action,
            window.connection_menu.actions(),
        )
        self.assertFalse(hasattr(window.workspace, "export_actions"))
        self.assertEqual(window.save_state_label.text(), "No video loaded")

        window.set_save_state("saved")

        self.assertTrue(window.save_state_label.text().startswith("✓ Saved · "))

    @patch("video_event_logger.ui.main_window.ApiSettingsDialog")
    @patch("video_event_logger.ui.main_window.EventLoggingController")
    @patch("video_event_logger.ui.main_window.QSettings")
    def test_api_settings_are_loaded_and_saved_locally(
        self,
        settings_type: Mock,
        controller_type: Mock,
        dialog_type: Mock,
    ) -> None:
        settings = Mock()
        stored_values = {
            "api/endpoint_url": "https://example.org/api/v1/annotations",
            "api/access_token": "old-token",
        }
        settings.value.side_effect = lambda key, default: stored_values.get(key, default)
        settings_type.return_value = settings
        dialog = Mock()
        dialog.exec.return_value = 1
        dialog.endpoint_url.return_value = "https://new.example.org/upload"
        dialog.token.return_value = "new-token"
        dialog_type.return_value = dialog

        window = MainWindow()
        self.addCleanup(window.deleteLater)
        self.assertEqual(
            window.api_connection_settings(),
            ("https://example.org/api/v1/annotations", "old-token"),
        )

        settings.setValue.reset_mock()
        window.show_connection_settings()

        settings.setValue.assert_any_call(
            "api/endpoint_url",
            "https://new.example.org/upload",
        )
        settings.setValue.assert_any_call("api/access_token", "new-token")
        settings.sync.assert_called_once_with()
        self.assertEqual(
            window.api_connection_settings(),
            ("https://new.example.org/upload", "new-token"),
        )


if __name__ == "__main__":
    unittest.main()

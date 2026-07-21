import os
import unittest
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QWidget

from video_event_logger.tasks.event_logging.ui.metadata_panel import MetadataPanel
from video_event_logger.tasks.event_logging.ui.export_actions import ExportActions
from video_event_logger.tasks.event_logging.ui.player_panel import PlayerPanel


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

    def test_pending_interval_shows_start_time_and_highlights_controls(self) -> None:
        panel = self.make_player_panel()

        panel.set_pending_interval_start(12.345)

        self.assertEqual(panel.interval_state_label.text(), "INTERVAL ACTIVE — start 00:00:12.345")
        self.assertEqual(panel.set_start_button.text(), "Start set")
        self.assertIn("#fff3cd", panel.set_start_button.styleSheet())
        self.assertIn("#e4f4e9", panel.set_end_button.styleSheet())

    def test_clearing_pending_interval_restores_ready_state(self) -> None:
        panel = self.make_player_panel()
        panel.set_pending_interval_start(12.345)

        panel.set_pending_interval_start(None)

        self.assertEqual(panel.interval_state_label.text(), "Interval: ready")
        self.assertEqual(panel.set_start_button.text(), "Start")
        self.assertEqual(panel.set_start_button.styleSheet(), "")
        self.assertEqual(panel.set_end_button.styleSheet(), "")

    def test_status_message_is_visible_and_has_tooltip(self) -> None:
        panel = MetadataPanel()

        panel.set_status_text("Interval autosaved.")

        self.assertEqual(panel.status_label.text(), "Interval autosaved.")
        self.assertEqual(panel.status_label.toolTip(), "Interval autosaved.")
        self.assertFalse(panel.status_label.isHidden())

    def test_result_and_autosave_have_independent_status_lamps(self) -> None:
        panel = MetadataPanel()

        panel.set_persistence_status("current", "failed")

        self.assertIn("#1c9c4a", panel.result_status_lamp.styleSheet())
        self.assertEqual(panel.result_status_lamp.toolTip(), "Result JSON: up to date")
        self.assertIn("#c62828", panel.autosave_status_lamp.styleSheet())
        self.assertEqual(panel.autosave_status_lamp.toolTip(), "Recovery autosave: save failed")

    def test_explicit_save_button_explains_that_it_validates_and_saves_now(self) -> None:
        actions = ExportActions()

        self.assertEqual(actions.save_now_button.text(), "Validate & Save JSON Now")
        self.assertIn("rewrite both JSON files", actions.save_now_button.toolTip())


if __name__ == "__main__":
    unittest.main()

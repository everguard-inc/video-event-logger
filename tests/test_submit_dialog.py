import os
import unittest
from unittest.mock import Mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from video_event_logger.models.interval import Interval
from video_event_logger.services.annotation_api import classify_upload_response
from video_event_logger.ui.submit_dialog import SubmitDialog


class SubmitDialogTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.application = QApplication.instance() or QApplication([])

    def test_no_events_needs_explicit_confirmation(self) -> None:
        dialog = SubmitDialog("cam.mp4", [], 120.0)
        submitted = Mock()
        dialog.submit_requested.connect(submitted)

        self.assertEqual(dialog.submit_button.text(), "Submit as “No events”")
        self.assertFalse(dialog.submit_button.isEnabled())
        dialog.submit_button.click()
        submitted.assert_not_called()

        dialog.confirm_empty.setChecked(True)
        dialog.submit_button.click()
        submitted.assert_called_once_with()

    def test_review_summarises_intervals_and_warns_about_undefined(self) -> None:
        intervals = [
            Interval.create(1, 1.0, 3.5, "no_helmet", ""),
            Interval.create(2, 5.0, 6.0, "undefined", ""),
        ]
        dialog = SubmitDialog("cam.mp4", intervals, 61.0)
        self.assertEqual(dialog.submit_button.text(), "Submit 2 intervals")
        self.assertTrue(dialog.submit_button.isEnabled())
        texts = [label.text() for label in dialog.review_page.findChildren(type(dialog.result_title))]
        self.assertIn("3.5 s", texts)
        self.assertIn("01:01", texts)
        self.assertTrue(any("#2" in text and "undefined" in text for text in texts))

    def test_result_buttons_follow_the_next_step(self) -> None:
        dialog = SubmitDialog("cam.mp4", [], 0.0, has_next_video=True)
        retry, settings, next_video = Mock(), Mock(), Mock()
        dialog.submit_requested.connect(retry)
        dialog.settings_requested.connect(settings)
        dialog.next_video_requested.connect(next_video)

        dialog.show_result(classify_upload_response(503, b""))
        self.assertEqual(dialog.result_primary.text(), "Retry")
        dialog.result_primary.click()
        retry.assert_called_once_with()

        dialog.show_result(classify_upload_response(401, b'{"detail":"Invalid token."}'))
        self.assertEqual(dialog.result_primary.text(), "Open connection settings")
        dialog.result_primary.click()
        settings.assert_called_once_with()

        dialog.show_result(classify_upload_response(201, b'{"status":"no_events","message":"ok"}'))
        self.assertEqual(dialog.result_primary.text(), "Open next video")
        self.assertEqual(dialog.result_message.text(), "ok")
        dialog.result_primary.click()
        next_video.assert_called_once_with()

    def test_escape_while_sending_cancels_instead_of_hiding(self) -> None:
        dialog = SubmitDialog("cam.mp4", [], 0.0)
        canceled = Mock()
        dialog.cancel_upload_requested.connect(canceled)
        dialog.show()
        dialog.show_sending()
        dialog.reject()
        canceled.assert_called_once_with()
        self.assertTrue(dialog.isVisible())


if __name__ == "__main__":
    unittest.main()

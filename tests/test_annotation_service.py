import unittest

from video_event_logger.application.annotation_service import AnnotationService
from video_event_logger.domain.errors import (
    InvalidIntervalError,
    InvalidIntervalIndexError,
    MissingIntervalStartError,
    NoAnnotationDocumentError,
)
from video_event_logger.models.annotation import AnnotationDocument


class AnnotationServiceTest(unittest.TestCase):
    def setUp(self) -> None:
        self.document = AnnotationDocument.empty("sample.mp4")
        self.service = AnnotationService()
        self.service.set_document(self.document)

    def test_start_interval_sets_pending_start(self) -> None:
        self.service.start_interval(12.345)

        self.assertTrue(self.service.has_pending_interval())
        self.assertEqual(self.service.pending_start_seconds, 12.345)

    def test_end_interval_requires_start(self) -> None:
        with self.assertRaises(MissingIntervalStartError):
            self.service.end_interval(20.0, "event", "")

    def test_end_interval_rejects_end_before_start(self) -> None:
        self.service.start_interval(20.0)

        with self.assertRaises(InvalidIntervalError):
            self.service.end_interval(19.0, "event", "")

    def test_end_interval_creates_interval_and_clears_pending_start(self) -> None:
        self.service.start_interval(1.23456)

        interval = self.service.end_interval(3.45678, "goal", "comment")

        self.assertFalse(self.service.has_pending_interval())
        self.assertEqual(interval.interval_id, 1)
        self.assertEqual(interval.start_time_seconds, 1.235)
        self.assertEqual(interval.end_time_seconds, 3.457)
        self.assertEqual(interval.event_type, "goal")
        self.assertEqual(interval.comment, "comment")
        self.assertEqual(self.document.intervals, [interval])

    def test_cancel_pending_interval(self) -> None:
        self.service.start_interval(1.0)

        canceled = self.service.cancel_pending_interval()

        self.assertTrue(canceled)
        self.assertFalse(self.service.has_pending_interval())

    def test_delete_interval_refreshes_ids(self) -> None:
        self.service.start_interval(1.0)
        first = self.service.end_interval(2.0, "a", "")
        self.service.start_interval(3.0)
        second = self.service.end_interval(4.0, "b", "")

        deleted = self.service.delete_interval_at(0)

        self.assertEqual(deleted, first)
        self.assertEqual(self.document.intervals, [second])
        self.assertEqual(second.interval_id, 1)

    def test_delete_interval_rejects_invalid_row(self) -> None:
        with self.assertRaises(InvalidIntervalIndexError):
            self.service.delete_interval_at(0)

    def test_update_interval_details_changes_event_type_and_comment(self) -> None:
        self.service.start_interval(1.0)
        interval = self.service.end_interval(2.0, "old", "old comment")

        updated = self.service.update_interval_details(0, "new", "new comment")

        self.assertEqual(updated, interval)
        self.assertEqual(interval.event_type, "new")
        self.assertEqual(interval.comment, "new comment")

    def test_update_interval_details_rejects_invalid_row(self) -> None:
        with self.assertRaises(InvalidIntervalIndexError):
            self.service.update_interval_details(0, "new", "")

    def test_event_counts(self) -> None:
        self.service.start_interval(1.0)
        self.service.end_interval(2.0, "a", "")
        self.service.start_interval(3.0)
        self.service.end_interval(4.0, "a", "")
        self.service.start_interval(5.0)
        self.service.end_interval(6.0, "b", "")

        self.assertEqual(self.service.event_counts(), {"a": 2, "b": 1})

    def test_requires_document(self) -> None:
        service = AnnotationService()

        with self.assertRaises(NoAnnotationDocumentError):
            service.start_interval(1.0)


if __name__ == "__main__":
    unittest.main()

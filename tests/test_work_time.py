import unittest

from video_event_logger.models.annotation import AnnotationDocument
from video_event_logger.services.validation import validate_document
from video_event_logger.services.work_time import WorkTimeTracker


class WorkTimeTest(unittest.TestCase):
    def setUp(self):
        self.now = 0.0
        self.tracker = WorkTimeTracker(lambda: self.now)
        self.document = AnnotationDocument.empty("video.mp4")
        self.tracker.attach(self.document)
        self.tracker.sample(True, False, activity=True)

    def advance(self, seconds, foreground=True, playing=False, activity=False):
        for _ in range(seconds):
            self.now += 1
            self.tracker.sample(foreground, playing, activity)

    def test_paused_idle_time_stops_at_threshold_and_input_resumes_without_backfill(self):
        self.advance(120)
        self.assertEqual(self.document.active_work_seconds, 60)
        self.tracker.sample(True, False, activity=True)
        self.advance(10)
        self.assertEqual(self.document.active_work_seconds, 70)

    def test_foreground_playback_counts_real_time_without_mouse_activity(self):
        self.tracker.sample(True, True)
        self.advance(180, playing=True)
        self.assertEqual(self.document.active_work_seconds, 180)

    def test_inputs_during_playback_do_not_double_count(self):
        self.tracker.sample(True, True)
        self.advance(120, playing=True, activity=True)
        self.assertEqual(self.document.active_work_seconds, 120)

    def test_paused_annotation_activity_keeps_counter_running(self):
        self.advance(180, activity=True)
        self.assertEqual(self.document.active_work_seconds, 180)

    def test_background_playback_is_excluded_and_return_does_not_backfill(self):
        self.advance(10)
        self.tracker.sample(False, True)
        self.advance(200, foreground=False, playing=True)
        self.assertEqual(self.document.active_work_seconds, 10)
        self.tracker.sample(True, False, activity=True)
        self.advance(5)
        self.assertEqual(self.document.active_work_seconds, 15)

    def test_sleep_or_blocked_event_loop_is_not_charged(self):
        self.tracker.sample(True, True)
        self.advance(3, playing=True)
        self.now += 3600
        self.tracker.sample(True, True)
        self.assertEqual(self.document.active_work_seconds, 3)
        self.advance(2, playing=True)
        self.assertEqual(self.document.active_work_seconds, 5)

    def test_switching_documents_keeps_separate_accumulating_totals(self):
        self.advance(10)
        other = AnnotationDocument.empty("other.mp4")
        other.active_work_seconds = 100
        self.tracker.attach(other)
        self.tracker.sample(True, False, activity=True)
        self.advance(20)
        self.assertEqual(other.active_work_seconds, 120)
        self.assertEqual(self.document.active_work_seconds, 10)
        self.tracker.attach(self.document)
        self.tracker.sample(True, False, activity=True)
        self.advance(5)
        self.assertEqual(self.document.active_work_seconds, 15)

    def test_no_loaded_video_has_no_counter(self):
        self.tracker.attach(None)
        self.advance(60, playing=True)
        self.assertEqual(self.document.active_work_seconds, 0)

    def test_idle_boundary_is_precise_for_fractional_samples(self):
        self.advance(59)
        self.now = 60.75
        self.tracker.sample(True, False)
        self.assertEqual(self.document.active_work_seconds, 60)

    def test_legacy_json_defaults_to_zero_and_new_json_round_trips(self):
        document = AnnotationDocument.from_dict({"video_name": "legacy.mp4"})
        self.assertEqual(document.active_work_seconds, 0)
        document.active_work_seconds = 123.45678
        restored = AnnotationDocument.from_dict(document.to_dict())
        self.assertEqual(restored.active_work_seconds, 123.457)
        self.assertEqual(validate_document(restored), [])

    def test_invalid_counter_is_rejected(self):
        for value in (-1, float("inf"), float("nan"), True, "10", None, {}):
            with self.subTest(value=value):
                document = AnnotationDocument.from_dict({"video_name": "video.mp4", "active_work_seconds": value})
                self.assertIn("Active work time must be a finite, non-negative number.", validate_document(document))

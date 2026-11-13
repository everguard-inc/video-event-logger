import math
from typing import List, Optional

from video_event_logger.models.annotation import AnnotationDocument


def _finite_number(value) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def validate_document(document: Optional[AnnotationDocument]) -> List[str]:
    if document is None:
        return ["Video is not loaded."]
    errors = []
    if not _finite_number(document.active_work_seconds) or document.active_work_seconds < 0:
        errors.append("Active work time must be a finite, non-negative number.")
    if not isinstance(document.video_name, str) or not document.video_name:
        errors.append("Video name is missing.")
    if not isinstance(document.current_event_type, str):
        errors.append("Current event type must be text.")
    duration = document.video_metadata.duration_seconds
    if duration is not None and (not _finite_number(duration) or duration < 0):
        errors.append("Video duration must be a finite, non-negative number.")
        duration = None
    if not _finite_number(document.last_playback_position_seconds) or document.last_playback_position_seconds < 0:
        errors.append("Playback position must be a finite, non-negative number.")
    for index, interval in enumerate(document.intervals, start=1):
        start, end = interval.start_time_seconds, interval.end_time_seconds
        if not _finite_number(start) or not _finite_number(end):
            errors.append("Interval %d must have finite start and end times." % index)
            continue
        if start < 0 or start >= end:
            errors.append("Interval %d must have 0 ≤ Start < End." % index)
        if not isinstance(interval.event_type, str) or not interval.event_type.strip():
            errors.append("Interval %d event_type is empty or invalid." % index)
        if not isinstance(interval.comment, str):
            errors.append("Interval %d comment must be text." % index)
        if duration is not None and end > duration:
            errors.append("Interval %d is outside video duration." % index)
    return errors

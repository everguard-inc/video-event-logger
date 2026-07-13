from typing import List, Optional

from video_event_logger.models.annotation import AnnotationDocument


def validate_document(document: Optional[AnnotationDocument]) -> List[str]:
    if document is None:
        return ["Video is not loaded."]
    errors = []
    if not document.video_name:
        errors.append("Video name is missing.")
    duration = document.video_metadata.duration_seconds
    for index, interval in enumerate(document.intervals, start=1):
        if interval.start_time_seconds is None:
            errors.append("Interval %d start time is missing." % index)
        if interval.end_time_seconds is None:
            errors.append("Interval %d end time is missing." % index)
        if interval.start_time_seconds >= interval.end_time_seconds:
            errors.append("Interval %d start time must be before end time." % index)
        if not interval.event_type.strip():
            errors.append("Interval %d event_type is empty." % index)
        if duration is not None:
            if interval.start_time_seconds < 0 or interval.end_time_seconds > duration:
                errors.append("Interval %d is outside video duration." % index)
    return errors

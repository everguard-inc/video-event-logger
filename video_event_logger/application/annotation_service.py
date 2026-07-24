from collections import Counter
from typing import Dict, List, Optional

from video_event_logger.models.annotation import AnnotationDocument
from video_event_logger.models.interval import Interval
from video_event_logger.domain.errors import (
    InvalidIntervalError,
    InvalidIntervalIndexError,
    MissingIntervalStartError,
    NoAnnotationDocumentError,
)


class AnnotationService:
    def __init__(self) -> None:
        self._document = None  # type: Optional[AnnotationDocument]
        self._pending_start_seconds = None  # type: Optional[float]

    @property
    def document(self) -> Optional[AnnotationDocument]:
        return self._document

    @property
    def pending_start_seconds(self) -> Optional[float]:
        return self._pending_start_seconds

    def set_document(self, document: Optional[AnnotationDocument]) -> None:
        self._document = document
        self._pending_start_seconds = None

    def has_pending_interval(self) -> bool:
        return self._pending_start_seconds is not None

    def start_interval(self, start_seconds: float) -> bool:
        self._require_document()
        if self._pending_start_seconds is not None:
            return False
        self._pending_start_seconds = start_seconds
        return True

    def end_interval(self, end_seconds: float, event_type: str, comment: str) -> Interval:
        document = self._require_document()
        if self._pending_start_seconds is None:
            raise MissingIntervalStartError("Set interval start first.")
        start_seconds = self._pending_start_seconds
        if start_seconds >= end_seconds:
            raise InvalidIntervalError("Interval start must be before interval end.")
        interval = Interval.create(
            interval_id=len(document.intervals) + 1,
            start_time_seconds=start_seconds,
            end_time_seconds=end_seconds,
            event_type=event_type,
            comment=comment,
        )
        document.intervals.append(interval)
        self._pending_start_seconds = None
        return interval

    def cancel_pending_interval(self) -> bool:
        had_pending = self._pending_start_seconds is not None
        self._pending_start_seconds = None
        return had_pending

    def delete_interval_at(self, row: int) -> Interval:
        document = self._require_document()
        if row < 0 or row >= len(document.intervals):
            raise InvalidIntervalIndexError("Invalid interval row: %s" % row)
        interval = document.intervals.pop(row)
        document.refresh_interval_ids()
        return interval

    def update_interval_details(self, row: int, event_type: str, comment: str) -> Interval:
        document = self._require_document()
        if row < 0 or row >= len(document.intervals):
            raise InvalidIntervalIndexError("Invalid interval row: %s" % row)
        interval = document.intervals[row]
        interval.event_type = event_type.strip() or interval.event_type
        interval.comment = comment
        return interval

    def intervals(self) -> List[Interval]:
        document = self._require_document()
        document.refresh_interval_ids()
        return list(document.intervals)

    def event_counts(self) -> Dict[str, int]:
        document = self._require_document()
        return dict(Counter([interval.event_type for interval in document.intervals]))

    def _require_document(self) -> AnnotationDocument:
        if self._document is None:
            raise NoAnnotationDocumentError("Video is not loaded.")
        return self._document

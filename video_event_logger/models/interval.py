from dataclasses import dataclass
from typing import Any, Dict, Optional

from video_event_logger.app_config import DEFAULT_EVENT_TYPE
from video_event_logger.services.time_utils import seconds_to_hhmmss


@dataclass
class Interval:
    interval_id: int
    start_time_seconds: float
    end_time_seconds: float
    start_time_hhmmss: str
    end_time_hhmmss: str
    start_frame: Optional[int]
    end_frame: Optional[int]
    frame_source: str
    event_type: str
    comment: str = ""

    @classmethod
    def create(
        cls,
        interval_id: int,
        start_time_seconds: float,
        end_time_seconds: float,
        event_type: str,
        comment: str,
    ) -> "Interval":
        clean_event_type = event_type.strip() or DEFAULT_EVENT_TYPE
        return cls(
            interval_id=interval_id,
            start_time_seconds=round(start_time_seconds, 3),
            end_time_seconds=round(end_time_seconds, 3),
            start_time_hhmmss=seconds_to_hhmmss(start_time_seconds),
            end_time_hhmmss=seconds_to_hhmmss(end_time_seconds),
            start_frame=None,
            end_frame=None,
            frame_source="unavailable",
            event_type=clean_event_type,
            comment=comment,
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "interval_id": self.interval_id,
            "start_time_seconds": self.start_time_seconds,
            "end_time_seconds": self.end_time_seconds,
            "start_time_hhmmss": self.start_time_hhmmss,
            "end_time_hhmmss": self.end_time_hhmmss,
            "start_frame": self.start_frame,
            "end_frame": self.end_frame,
            "frame_source": self.frame_source,
            "event_type": self.event_type,
            "comment": self.comment,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Interval":
        start_seconds = float(data.get("start_time_seconds", 0.0))
        end_seconds = float(data.get("end_time_seconds", 0.0))
        return cls(
            interval_id=int(data.get("interval_id", 0)),
            start_time_seconds=start_seconds,
            end_time_seconds=end_seconds,
            start_time_hhmmss=data.get("start_time_hhmmss") or seconds_to_hhmmss(start_seconds),
            end_time_hhmmss=data.get("end_time_hhmmss") or seconds_to_hhmmss(end_seconds),
            start_frame=data.get("start_frame"),
            end_frame=data.get("end_frame"),
            frame_source=data.get("frame_source") or "unavailable",
            event_type=(data.get("event_type") or DEFAULT_EVENT_TYPE),
            comment=data.get("comment") or "",
        )

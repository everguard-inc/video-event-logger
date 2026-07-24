from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from video_event_logger.app_config import APP_NAME, APP_VERSION, DEFAULT_EVENT_TYPE, SCHEMA_VERSION
from video_event_logger.models.interval import Interval
from video_event_logger.models.video_metadata import VideoMetadata


@dataclass
class AnnotationDocument:
    video_name: str
    video_metadata: VideoMetadata = field(default_factory=VideoMetadata)
    intervals: List[Interval] = field(default_factory=list)
    current_event_type: str = DEFAULT_EVENT_TYPE
    last_playback_position_seconds: float = 0.0
    schema_version: str = SCHEMA_VERSION
    app_name: str = APP_NAME
    app_version: str = APP_VERSION
    is_autosave: bool = False
    created_at: Optional[str] = None

    def refresh_interval_ids(self) -> None:
        for index, interval in enumerate(self.intervals, start=1):
            interval.interval_id = index

    def to_dict(self, is_autosave: bool = False) -> Dict[str, Any]:
        self.refresh_interval_ids()
        if self.created_at is None:
            self.created_at = datetime.now(timezone.utc).astimezone().isoformat()
        return {
            "schema_version": self.schema_version,
            "app_name": self.app_name,
            "app_version": self.app_version,
            "is_autosave": is_autosave,
            "created_at": self.created_at,
            "video_name": self.video_name,
            "current_event_type": self.current_event_type.strip() or DEFAULT_EVENT_TYPE,
            "last_playback_position_seconds": round(self.last_playback_position_seconds, 3),
            "video_metadata": self.video_metadata.to_dict(),
            "intervals": [interval.to_dict() for interval in self.intervals],
        }

    @classmethod
    def empty(cls, video_name: str) -> "AnnotationDocument":
        return cls(video_name=video_name)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "AnnotationDocument":
        intervals = []
        for item in data.get("intervals", []):
            if isinstance(item, dict):
                intervals.append(Interval.from_dict(item))
        document = cls(
            video_name=data.get("video_name") or "",
            video_metadata=VideoMetadata.from_dict(data.get("video_metadata", {})),
            intervals=intervals,
            current_event_type=data.get("current_event_type") or DEFAULT_EVENT_TYPE,
            last_playback_position_seconds=float(data.get("last_playback_position_seconds") or 0.0),
            schema_version=data.get("schema_version") or SCHEMA_VERSION,
            app_name=data.get("app_name") or APP_NAME,
            app_version=data.get("app_version") or APP_VERSION,
            is_autosave=bool(data.get("is_autosave", False)),
            created_at=data.get("created_at"),
        )
        document.refresh_interval_ids()
        return document

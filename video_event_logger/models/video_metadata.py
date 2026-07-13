from dataclasses import dataclass
from typing import Any, Dict, Optional


@dataclass
class VideoMetadata:
    duration_seconds: Optional[float] = None
    duration_hhmmss: str = "00:00:00.000"
    fps: Optional[float] = None
    frame_count: Optional[int] = None
    resolution: Optional[Dict[str, int]] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "duration_seconds": self.duration_seconds,
            "duration_hhmmss": self.duration_hhmmss,
            "fps": self.fps,
            "frame_count": self.frame_count,
            "resolution": self.resolution,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "VideoMetadata":
        if not isinstance(data, dict):
            data = {}
        return cls(
            duration_seconds=data.get("duration_seconds"),
            duration_hhmmss=data.get("duration_hhmmss") or "00:00:00.000",
            fps=data.get("fps"),
            frame_count=data.get("frame_count"),
            resolution=data.get("resolution"),
        )

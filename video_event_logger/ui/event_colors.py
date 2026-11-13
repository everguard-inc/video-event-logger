"""One stable color per event_type, shared by the timeline, list, chips and HUD."""
import zlib

from PySide6.QtGui import QColor

from video_event_logger.app_config import DEFAULT_EVENT_TYPE

UNDEFINED_COLOR = "#8b93a1"


def event_type_qcolor(event_type: str) -> QColor:
    name = (event_type or "").strip()
    if not name or name == DEFAULT_EVENT_TYPE:
        return QColor(UNDEFINED_COLOR)
    return QColor.fromHsv(zlib.crc32(name.encode()) % 360, 150, 225)


def event_type_color(event_type: str) -> str:
    return event_type_qcolor(event_type).name()

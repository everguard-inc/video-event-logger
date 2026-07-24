from pathlib import Path
from video_event_logger.app_config import (
    LEGACY_AUTOSAVE_DIR,
    RESULTS_DIR,
    SUPPORTED_VIDEO_EXTENSIONS,
)


def ensure_data_dirs() -> None:
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)


def is_supported_video(path: Path) -> bool:
    return path.suffix.lower() in SUPPORTED_VIDEO_EXTENSIONS


def annotation_path_for_video_name(video_name: str) -> Path:
    ensure_data_dirs()
    stem = Path(video_name).stem
    return RESULTS_DIR / ("%s.annotations.json" % stem)


def annotation_backup_path_for_video_name(video_name: str) -> Path:
    annotation_path = annotation_path_for_video_name(video_name)
    return annotation_path.with_name("%s.bak" % annotation_path.name)


def legacy_autosave_path_for_video_name(video_name: str) -> Path:
    stem = Path(video_name).stem
    return LEGACY_AUTOSAVE_DIR / ("%s.autosave.json" % stem)

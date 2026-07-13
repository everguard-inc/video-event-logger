from pathlib import Path
from typing import Tuple

from video_event_logger.app_config import AUTOSAVE_DIR, RESULTS_DIR, SUPPORTED_VIDEO_EXTENSIONS


def ensure_data_dirs() -> None:
    AUTOSAVE_DIR.mkdir(parents=True, exist_ok=True)
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)


def is_supported_video(path: Path) -> bool:
    return path.suffix.lower() in SUPPORTED_VIDEO_EXTENSIONS


def annotation_paths_for_video_name(video_name: str) -> Tuple[Path, Path]:
    ensure_data_dirs()
    stem = Path(video_name).stem
    autosave_path = AUTOSAVE_DIR / ("%s.autosave.json" % stem)
    final_path = RESULTS_DIR / ("%s.annotations.json" % stem)
    return autosave_path, final_path

from pathlib import Path
from typing import Tuple


APP_NAME = "Video Event Logger"
APP_VERSION = "0.2.0"
SCHEMA_VERSION = "1.0"
APP_PACKAGE_DIR = Path(__file__).resolve().parent
APP_ICON_PATH = APP_PACKAGE_DIR / "assets" / "app_icon.svg"

DEFAULT_EVENT_TYPE = "undefined"
SUPPORTED_VIDEO_EXTENSIONS = (".mp4", ".mkv")  # type: Tuple[str, str]

APP_DATA_DIR = Path.home() / "VideoEventLogger"
AUTOSAVE_DIR = APP_DATA_DIR / "autosave"
RESULTS_DIR = APP_DATA_DIR / "results"

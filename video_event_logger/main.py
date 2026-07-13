import sys

from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication

from video_event_logger.app_config import APP_ICON_PATH, APP_NAME, APP_VERSION
from video_event_logger.services.path_utils import ensure_data_dirs
from video_event_logger.ui.main_window import MainWindow


def main() -> int:
    ensure_data_dirs()
    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setApplicationVersion(APP_VERSION)

    app_icon = QIcon(str(APP_ICON_PATH))
    if not app_icon.isNull():
        app.setWindowIcon(app_icon)

    window = MainWindow()
    if not app_icon.isNull():
        window.setWindowIcon(app_icon)
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())

import sys
from typing import List, Optional

from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication

from video_event_logger.app_config import APP_ICON_PATH, APP_NAME, APP_VERSION
from video_event_logger.services.path_utils import ensure_data_dirs


def _create_application(arguments: Optional[List[str]] = None) -> QApplication:
    app = QApplication.instance() or QApplication(arguments or sys.argv)
    app.setApplicationName(APP_NAME)
    app.setApplicationVersion(APP_VERSION)
    return app


def run_smoke_test() -> int:
    try:
        app = _create_application([sys.argv[0], "--smoke-test"])
        from video_event_logger.models.annotation import AnnotationDocument
        from video_event_logger.ui.main_window import MainWindow
        from video_event_logger.ui.video_player import VLC_IMPORT_ERROR, vlc

        if not APP_ICON_PATH.is_file():
            raise RuntimeError("Application icon is missing: %s" % APP_ICON_PATH)
        if QIcon(str(APP_ICON_PATH)).isNull():
            raise RuntimeError("Qt could not load the application icon: %s" % APP_ICON_PATH)
        if vlc is None:
            raise RuntimeError("python-vlc could not be imported: %s" % VLC_IMPORT_ERROR)

        libvlc_version = vlc.libvlc_get_version()
        if isinstance(libvlc_version, bytes):
            libvlc_version = libvlc_version.decode("utf-8", errors="replace")
        if not libvlc_version:
            raise RuntimeError("libVLC did not report a version")

        vlc_instance = vlc.Instance("--intf=dummy", "--no-audio", "--no-video-title-show")
        if vlc_instance is None:
            raise RuntimeError("libVLC could not create an Instance")
        media_player = vlc_instance.media_player_new()
        if media_player is None:
            vlc_instance.release()
            raise RuntimeError("libVLC could not create a MediaPlayer")
        media_player.release()
        vlc_instance.release()

        _ = (app, AnnotationDocument, MainWindow)
        print("Video Event Logger smoke test passed.")
        print("Application version: %s" % APP_VERSION)
        print("libVLC version: %s" % libvlc_version)
        print("libVLC Instance and MediaPlayer: initialized")
        print("Application icon: %s" % APP_ICON_PATH)
        return 0
    except Exception as exc:
        print("Video Event Logger smoke test failed: %s" % exc, file=sys.stderr)
        return 1


def main() -> int:
    if "--smoke-test" in sys.argv[1:]:
        return run_smoke_test()

    ensure_data_dirs()
    app = _create_application()
    from video_event_logger.ui.main_window import MainWindow

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

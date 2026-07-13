from PySide6.QtWidgets import QMainWindow

from video_event_logger.app_config import APP_NAME, APP_VERSION
from video_event_logger.tasks.event_logging.controller import EventLoggingController
from video_event_logger.tasks.event_logging.ui.workspace import EventLoggingWorkspace


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("%s v%s" % (APP_NAME, APP_VERSION))
        self.resize(1180, 820)

        self.workspace = EventLoggingWorkspace(self)
        self.setCentralWidget(self.workspace)
        self.controller = EventLoggingController(self, self.workspace)
        self._build_menu_bar()

    def _build_menu_bar(self) -> None:
        help_menu = self.menuBar().addMenu("&Help")
        annotator_guide_action = help_menu.addAction("Annotator Guide")
        annotator_guide_action.setStatusTip("Show keyboard shortcuts and annotation workflow")
        annotator_guide_action.triggered.connect(self.controller.show_help)

    def closeEvent(self, event) -> None:  # type: ignore[no-untyped-def]
        self.controller.close_event(event)

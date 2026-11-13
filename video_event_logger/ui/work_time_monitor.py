from PySide6.QtCore import QEvent, QObject, Qt, QTimer
from PySide6.QtGui import QCursor
from PySide6.QtWidgets import QApplication, QWidget

from video_event_logger.services.work_time import WorkTimeTracker


class WorkTimeMonitor(QObject):
    """Observe activity only in this player's UI, including annotation dialogs."""
    INPUT_EVENTS = {
        QEvent.Type.KeyPress, QEvent.Type.MouseButtonPress,
        QEvent.Type.MouseButtonRelease, QEvent.Type.MouseButtonDblClick,
        QEvent.Type.Wheel, QEvent.Type.TouchBegin, QEvent.Type.TouchUpdate,
    }

    def __init__(self, controller):
        super().__init__(controller.window)
        self.controller = controller
        self.window = controller.window
        self.tracker = WorkTimeTracker()
        self.last_cursor = QCursor.pos()
        self.last_saved = self.tracker.clock()
        self.saved_seconds = 0.0
        app = QApplication.instance()
        app.installEventFilter(self)
        app.applicationStateChanged.connect(self._application_state_changed)
        self.timer = QTimer(self)
        self.timer.setInterval(1000)
        self.timer.timeout.connect(self._tick)
        self.timer.start()

    def stop(self):
        self.timer.stop()
        app = QApplication.instance()
        app.removeEventFilter(self)
        app.applicationStateChanged.disconnect(self._application_state_changed)

    def _belongs_to_player(self, widget):
        # Download management does not count as annotating the current video.
        download = self.controller.download_dialog
        while widget is not None:
            if download is not None and widget is download:
                return False
            if widget is self.window:
                return True
            widget = widget.parent()
        return False

    def _foreground(self):
        return (
            QApplication.applicationState() == Qt.ApplicationState.ApplicationActive
            and self.window.isVisible()
            and not self.window.isMinimized()
            and self._belongs_to_player(QApplication.activeWindow())
        )

    def attach(self, document):
        self.tracker.attach(document)
        self.last_saved = self.tracker.clock()
        self.saved_seconds = document.active_work_seconds
        self.flush(activity=True)

    def flush(self, activity=False):
        self.tracker.sample(self._foreground(), self.controller.video_player.is_playing(), activity)

    def _application_state_changed(self, state):
        self.flush(activity=state == Qt.ApplicationState.ApplicationActive)

    def eventFilter(self, watched, event):
        if event.type() in self.INPUT_EVENTS and self._belongs_to_player(watched):
            self.flush(activity=True)
        return False

    def _tick(self):
        # Native VLC video surfaces may not deliver Qt mouse-move events.
        cursor = QCursor.pos()
        moved = cursor != self.last_cursor
        self.last_cursor = cursor
        widget = QApplication.widgetAt(cursor) if moved else None
        activity = moved and isinstance(widget, QWidget) and self._belongs_to_player(widget)
        self.flush(activity=activity)
        now = self.tracker.clock()
        document = self.tracker.document
        if document is not None and now - self.last_saved >= 30:
            self.last_saved = now
            if document.active_work_seconds != self.saved_seconds:
                if self.controller._save_checkpoint("Work time saved.", update_runtime=False, quiet=True):
                    self.saved_seconds = document.active_work_seconds

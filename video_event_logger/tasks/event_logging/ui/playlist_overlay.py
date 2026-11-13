"""Native overlay for the playlist above VLC's native video surface."""
import time

from PySide6.QtCore import QObject, QPoint, QRect, Qt, QTimer
from PySide6.QtGui import QCursor, QKeySequence, QShortcut
from PySide6.QtWidgets import QApplication, QFrame, QVBoxLayout


class PlaylistOverlay(QObject):
    EDGE_WIDTH = 6
    HIDE_DELAY = 0.4

    def __init__(self, workspace):
        super().__init__(workspace)
        self.workspace = workspace
        self.active = False
        self.enabled = True
        self.outside_since = None
        self.panel = workspace.playlist_panel
        self.frame = QFrame(workspace.window(), Qt.WindowType.Tool | Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint)
        self.frame.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)
        self.frame.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.frame.setFrameShape(QFrame.Shape.StyledPanel)
        self.layout = QVBoxLayout(self.frame)
        self.layout.setContentsMargins(8, 8, 8, 8)
        self.timer = QTimer(self)
        self.timer.setInterval(80)
        self.timer.timeout.connect(self.check_pointer)
        self.shortcuts = []
        for key in ("Escape", "F11"):
            shortcut = QShortcut(QKeySequence(key), self.frame)
            shortcut.activated.connect(lambda: workspace.window().set_fullscreen(False))
            self.shortcuts.append(shortcut)

    def set_active(self, active):
        if self.active == active:
            return
        self.active = active
        self.hide()
        if active:
            self.normal_sizes = self.workspace.horizontal_splitter.sizes()
            self.layout.addWidget(self.panel)
            self.panel.show()
            self.timer.start()
        else:
            self.timer.stop()
            self.workspace.horizontal_splitter.addWidget(self.panel)
            self.panel.setVisible(self.enabled)
            self.workspace.horizontal_splitter.setSizes(self.normal_sizes)

    def set_enabled(self, enabled):
        self.enabled = enabled
        if self.active:
            if not enabled:
                self.hide()
        else:
            self.panel.setVisible(enabled)

    def hide(self):
        had_focus = self.frame.isActiveWindow()
        self.frame.hide()
        self.outside_since = None
        if had_focus and self.workspace.window().isVisible():
            self.workspace.window().activateWindow()
            self.workspace.video_player.setFocus()

    def check_pointer(self):
        window = self.workspace.window()
        if not self.active or not self.enabled or not window.isVisible() or window.isMinimized():
            self.hide()
            return
        # Cursor polling also works when VLC consumes native mouse events.
        active = QApplication.activeWindow()
        modal = QApplication.activeModalWidget()
        popup = QApplication.activePopupWidget()
        if active is None or (active not in (window, self.frame) and not modal and not popup):
            self.hide()
            return
        origin = self.workspace.mapToGlobal(QPoint(0, 0))
        bounds = QRect(origin, self.workspace.size())
        position = QCursor.pos()
        if not self.frame.isVisible():
            if modal or popup or not bounds.contains(position):
                return
            if position.x() >= origin.x() + self.EDGE_WIDTH:
                return
        width = min(max(280, self.panel.minimumSizeHint().width() + 16), max(280, bounds.width() // 3))
        self.frame.setGeometry(bounds.x(), bounds.y(), width, bounds.height())
        if not self.frame.isVisible():
            self.frame.show()
            self.frame.raise_()
        if self.frame.geometry().contains(position) or modal or popup or QApplication.mouseButtons() != Qt.MouseButton.NoButton:
            self.outside_since = None
            return
        now = time.monotonic()
        if self.outside_since is None:
            self.outside_since = now
        elif now - self.outside_since >= self.HIDE_DELAY:
            self.hide()

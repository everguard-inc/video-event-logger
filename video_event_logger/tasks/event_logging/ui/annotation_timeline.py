"""Scrollable interval track. Drag previews are committed only on release."""
import math

from PySide6.QtCore import QEvent, QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import (
    QFrame, QHBoxLayout, QLabel, QMenu, QPushButton, QScrollArea, QSlider, QToolTip,
    QVBoxLayout, QWidget,
)

from video_event_logger.services.time_utils import seconds_to_hhmmss
from video_event_logger.ui.event_colors import event_type_qcolor


def axis_label(seconds, step):
    """Short ruler labels: 0:20, 1:05 or 1:02:03; tenths only when steps are below a second."""
    seconds = max(0.0, seconds)
    hours, rest = divmod(seconds, 3600)
    minutes, secs = divmod(rest, 60)
    text = "%02d" % int(secs) if step >= 1 else "%04.1f" % secs
    if hours >= 1:
        return "%d:%02d:%s" % (hours, minutes, text)
    return "%d:%s" % (minutes, text)


class IntervalTrack(QWidget):
    layout_changed = Signal()
    selected = Signal(int)
    bounds_changed = Signal(int, float, float)
    seek_requested = Signal(float)
    edit_requested = Signal(int)
    play_requested = Signal(int)
    delete_requested = Signal(int)
    ROW_HEIGHT = 24
    HEADER = 21
    MARGIN = 8

    def __init__(self, parent=None):
        super().__init__(parent)
        self.context_menu = None
        self.intervals = []
        self.duration = 0.0
        self.position = 0.0
        self.selected_row = -1
        self.pending_start = None  # start of the interval being recorded
        self.drag = None
        self.lanes = {}
        self.lane_count = 1
        self.axis_margin = float(self.MARGIN)
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setFixedHeight(self.HEADER + self.ROW_HEIGHT + 4)

    def set_intervals(self, intervals):
        self.cancel_drag()
        if self.context_menu is not None:
            self.context_menu.close()
        self.intervals = list(intervals)
        self._layout_lanes()
        if self.selected_row >= len(intervals):
            self.selected_row = -1
        self.update()

    def _layout_lanes(self):
        ends = []
        self.lanes = {}
        for row in sorted(range(len(self.intervals)), key=lambda i: self.intervals[i].start_time_seconds):
            interval = self.intervals[row]
            lane = next((i for i, end in enumerate(ends) if end <= interval.start_time_seconds), len(ends))
            if lane == len(ends):
                ends.append(0)
            ends[lane] = interval.end_time_seconds
            self.lanes[row] = lane
        self.lane_count = max(1, len(ends))
        self.setFixedHeight(self.HEADER + self.lane_count * self.ROW_HEIGHT + 4)
        self.layout_changed.emit()

    def x_for_time(self, seconds):
        return self.axis_margin + seconds / max(self.duration, 0.001) * max(1, self.width() - 2 * self.axis_margin)

    def time_for_x(self, x):
        return round(max(0, min(self.duration, (x - self.axis_margin) / max(1, self.width() - 2 * self.axis_margin) * self.duration)), 3)

    def bounds(self, row):
        if self.drag and self.drag[0] == row:
            return self.drag[2], self.drag[3]
        item = self.intervals[row]
        return item.start_time_seconds, item.end_time_seconds

    def rect_for_row(self, row):
        start, end = self.bounds(row)
        left, right = self.x_for_time(start), self.x_for_time(end)
        return QRectF(left, self.HEADER + self.lanes[row] * self.ROW_HEIGHT, max(2, right - left), 18)

    def set_selected(self, row):
        self.selected_row = row
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.fillRect(self.rect(), self.palette().base())
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(self.palette().text().color())
        # Use readable 1/2/5-based time steps instead of arbitrary duration fractions.
        label_width = painter.fontMetrics().horizontalAdvance(axis_label(self.duration, 1.0)) + 12
        raw_step = max(self.duration, 0.001) / max(1, self.width() // (label_width + 30))
        magnitude = 10 ** math.floor(math.log10(raw_step))
        step = next(factor * magnitude for factor in (1, 2, 5, 10) if factor * magnitude >= raw_step)
        ticks = [index * step for index in range(int(self.duration / step) + 1)]
        if not ticks or abs(ticks[-1] - self.duration) > 0.001:
            ticks.append(self.duration)
        for tick in ticks:
            x = self.x_for_time(tick)
            painter.setPen(QPen(self.palette().mid().color(), 0.75))
            painter.drawLine(QPointF(x, self.HEADER - 4), QPointF(x, self.height()))
            last = tick == self.duration
            if last or x + label_width < self.width() - label_width:
                painter.setPen(self.palette().text().color())
                label_x = self.width() - label_width if last else x + 3
                painter.drawText(QRectF(label_x, 0, label_width, 20), axis_label(tick, step))
        if not self.intervals:
            painter.drawText(QRectF(14, self.HEADER, self.width() - 28, 26), "No intervals")
        for row, interval in enumerate(self.intervals):
            rect = self.rect_for_row(row)
            color = event_type_qcolor(interval.event_type)
            painter.setBrush(color)
            selected = row == self.selected_row
            painter.setPen(QPen(self.palette().text().color() if selected else color.darker(140), 2 if selected else 0.75))
            painter.drawRoundedRect(rect, 3, 3)
            painter.setPen(QColor("#0b0d10"))
            if rect.width() > 12:
                painter.drawLine(QPointF(rect.left() + 4, rect.top() + 4), QPointF(rect.left() + 4, rect.bottom() - 4))
                painter.drawLine(QPointF(rect.right() - 4, rect.top() + 4), QPointF(rect.right() - 4, rect.bottom() - 4))
            if rect.width() > 40:
                text = painter.fontMetrics().elidedText(interval.event_type, Qt.TextElideMode.ElideRight, int(rect.width() - 20))
                painter.drawText(rect.adjusted(10, 0, -10, 0), Qt.AlignmentFlag.AlignVCenter, text)
        if self.pending_start is not None and self.duration > 0:
            x0 = self.x_for_time(self.pending_start)
            x1 = max(x0 + 2, self.x_for_time(max(self.pending_start, self.position)))
            band = QRectF(x0, self.HEADER, x1 - x0, max(8.0, self.height() - self.HEADER - 4))
            painter.setBrush(QColor(255, 90, 95, 70))
            painter.setPen(QPen(QColor("#ff5a5f"), 1.5, Qt.PenStyle.DashLine))
            painter.drawRoundedRect(band, 3, 3)
        painter.setPen(QPen(QColor("#e45745"), 1))
        x = self.x_for_time(self.position)
        painter.drawLine(QPointF(x, 0), QPointF(x, self.height()))
        if self.drag:
            start, end = self.bounds(self.drag[0])
            painter.fillRect(QRectF(0, 0, self.width(), self.HEADER), self.palette().base())
            painter.setPen(self.palette().text().color())
            painter.drawText(QRectF(10, 0, self.width() - 20, self.HEADER), "%s → %s   (%s)" % (seconds_to_hhmmss(start), seconds_to_hhmmss(end), seconds_to_hhmmss(end - start)))

    def hit_test(self, point):
        for row in reversed(range(len(self.intervals))):
            rect = self.rect_for_row(row)
            if rect.adjusted(-5, 0, 5, 0).contains(point):
                left, right = abs(point.x() - rect.left()), abs(point.x() - rect.right())
                edge = ("start" if left <= right else "end") if min(left, right) <= 7 else None
                return row, edge
        return -1, None

    def mousePressEvent(self, event):
        if event.button() != Qt.MouseButton.LeftButton or self.duration <= 0:
            return
        self.setFocus()
        row, edge = self.hit_test(event.position())
        if row < 0:
            self.seek_requested.emit(self.time_for_x(event.position().x()))
            return
        self.set_selected(row)
        self.selected.emit(row)
        if edge:
            start, end = self.bounds(row)
            self.drag = (row, edge, start, end)
            self.grabMouse()

    def mouseMoveEvent(self, event):
        if self.drag:
            row, edge, start, end = self.drag
            value = self.time_for_x(event.position().x())
            if edge == "start":
                start = max(0, min(value, end - 0.001))
            else:
                end = min(self.duration, max(value, start + 0.001))
            self.drag = (row, edge, round(start, 3), round(end, 3))
            self.update()
            return
        row, edge = self.hit_test(event.position())
        self.setCursor(Qt.CursorShape.SizeHorCursor if edge else Qt.CursorShape.ArrowCursor)
        if row >= 0:
            item = self.intervals[row]
            start, end = self.bounds(row)
            QToolTip.showText(event.globalPosition().toPoint(), "%s\n%s → %s\nDuration: %s" % (item.event_type, seconds_to_hhmmss(start), seconds_to_hhmmss(end), seconds_to_hhmmss(end-start)), self)
        else:
            QToolTip.hideText()

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton and self.drag:
            row, edge, start, end = self.drag
            self.drag = None
            self.releaseMouse()
            item = self.intervals[row]
            if (start, end) != (item.start_time_seconds, item.end_time_seconds):
                self.bounds_changed.emit(row, start, end)
            self.update()

    def mouseDoubleClickEvent(self, event):
        if event.button() != Qt.MouseButton.LeftButton:
            return
        row, _ = self.hit_test(event.position())
        self.cancel_drag()
        if row >= 0:
            self.set_selected(row)
            self.selected.emit(row)
            self.edit_requested.emit(row)

    def contextMenuEvent(self, event):
        row, _ = self.hit_test(QPointF(event.pos()))
        if row < 0:
            return
        self.cancel_drag()
        QToolTip.hideText()
        self.set_selected(row)
        self.selected.emit(row)
        menu = QMenu(self)
        self.context_menu = menu
        for label, signal in (("Play", self.play_requested), ("Edit", self.edit_requested), ("Delete", self.delete_requested)):
            action = menu.addAction(label)
            action.triggered.connect(lambda checked=False, requested=signal: requested.emit(row))
        try:
            menu.exec(event.globalPos())
        finally:
            self.context_menu = None
            menu.deleteLater()

    def cancel_drag(self):
        if self.drag:
            self.drag = None
            self.releaseMouse()
            self.update()

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Escape and self.drag:
            self.cancel_drag()
        else:
            super().keyPressEvent(event)

    def hideEvent(self, event):
        self.cancel_drag()
        super().hideEvent(event)


class TimelineResizeHandle(QWidget):
    height_requested = Signal(int)
    resize_finished = Signal()

    def __init__(self, parent):
        super().__init__(parent)
        self.setFixedHeight(7)
        self.setCursor(Qt.CursorShape.SizeVerCursor)
        self.setToolTip("Drag to resize the Events Bar")
        self.origin = None

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setPen(QPen(self.palette().mid().color(), 1))
        painter.drawLine(self.width() // 2 - 20, 3, self.width() // 2 + 20, 3)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.origin = (event.globalPosition().y(), self.parentWidget().height())
            self.grabMouse()

    def mouseMoveEvent(self, event):
        if self.origin is not None:
            y, height = self.origin
            self.height_requested.emit(round(height + y - event.globalPosition().y()))

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton and self.origin is not None:
            self.mouseMoveEvent(event)
            self.origin = None
            self.releaseMouse()
            self.resize_finished.emit()

    def hideEvent(self, event):
        if self.origin is not None:
            self.origin = None
            self.releaseMouse()
            self.resize_finished.emit()
        super().hideEvent(event)


class AnnotationTimeline(QWidget):
    viewport_changed = Signal()
    height_changed = Signal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.user_height = None
        self.wheel_remainder = 0.0
        self.zoom_anchor = None
        self.wheel_zoom_active = False
        font = self.font()
        font.setPointSizeF(max(8.0, font.pointSizeF() - 2.0))
        self.setFont(font)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 2, 0, 2)
        layout.setSpacing(2)
        self.resize_handle = TimelineResizeHandle(self)
        self.resize_handle.height_requested.connect(self._resize_from_handle)
        self.resize_handle.resize_finished.connect(self._save_height)
        layout.addWidget(self.resize_handle)
        controls = QHBoxLayout()
        self.controls_layout = controls
        controls.addWidget(QLabel("Intervals · drag edges to trim"))
        controls.addStretch()
        controls.addWidget(QLabel("Time zoom"))
        self.zoom = QSlider(Qt.Orientation.Horizontal)
        self.zoom.setRange(1, 32)
        self.zoom.setValue(1)
        self.zoom.setFixedWidth(100)
        controls.addWidget(self.zoom)
        fit = QPushButton("Fit")
        fit.clicked.connect(lambda: self.zoom.setValue(1))
        controls.addWidget(fit)
        layout.addLayout(controls)
        self.scroll = QScrollArea()
        self.scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.scroll.setWidgetResizable(True)
        self.track = IntervalTrack()
        self.track.setToolTip("Right-click: Play / Edit / Delete\nDouble-click: Edit\nWheel: zoom at cursor; Shift+wheel: scroll")
        self.scroll.setWidget(self.track)
        # Initially fit up to four lanes; the resize handle can expose more.
        # Wheel gestures over the track control time zoom rather than lane scrolling.
        self.scroll.setStyleSheet("""
            QScrollArea { border: 0; }
            QScrollBar:vertical { width: 8px; margin: 0; background: palette(base); }
            QScrollBar:horizontal { height: 8px; margin: 0; background: palette(base); }
            QScrollBar::handle { background: palette(mid); border-radius: 4px; min-width: 20px; min-height: 20px; }
            QScrollBar::add-line, QScrollBar::sub-line { width: 0; height: 0; }
            QScrollBar::add-page, QScrollBar::sub-page { background: transparent; }
        """)
        self.track.layout_changed.connect(self._update_geometry)
        self.scroll.viewport().installEventFilter(self)
        self.track.installEventFilter(self)
        if parent is not None:
            parent.installEventFilter(self)
        layout.addWidget(self.scroll)
        self.zoom.valueChanged.connect(self._zoom_changed)
        self.scroll.horizontalScrollBar().actionTriggered.connect(self._clear_zoom_anchor)
        self.scroll.horizontalScrollBar().sliderPressed.connect(self._clear_zoom_anchor)
        self._update_geometry()

    def _update_geometry(self):
        zoomed = self.zoom.value() > 1
        self.scroll.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOn if zoomed else Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        visible_lanes = min(4, self.track.lane_count)
        height = self.track.HEADER + visible_lanes * self.track.ROW_HEIGHT + 4
        if zoomed:
            height += self.scroll.horizontalScrollBar().sizeHint().height()
        margins = self.layout().contentsMargins()
        chrome = margins.top() + margins.bottom() + 2 * self.layout().spacing() + self.resize_handle.height() + self.controls_layout.sizeHint().height()
        if self.user_height is not None:
            total = self._bounded_height(self.user_height)
            height = max(self.track.HEADER + self.track.ROW_HEIGHT + 4, total - chrome)
        self.scroll.setFixedHeight(height)
        self._update_zoom()
        self.setFixedHeight(chrome + height)

    def _update_zoom(self):
        width = max(1, self.scroll.viewport().width()) * self.zoom.value()
        self.track.setMinimumWidth(width)
        self.track.resize(width, self.track.height())
        if self.zoom_anchor is not None:
            seconds, viewport_x = self.zoom_anchor
            self.scroll.horizontalScrollBar().setValue(round(self.track.x_for_time(seconds) - viewport_x))

    def _clear_zoom_anchor(self, *args):
        self.zoom_anchor = None

    def _zoom_changed(self):
        if not self.wheel_zoom_active:
            self._clear_zoom_anchor()
        self._update_geometry()

    def restore_height(self, value):
        try:
            height = int(value)
        except (ValueError, TypeError, OverflowError):
            return
        if height > 0:
            self.user_height = min(1200, max(100, height))
            self._update_geometry()

    def _bounded_height(self, height):
        parent = self.parentWidget()
        if parent is not None and parent.objectName() == "hudEvents":
            # Floating over the fullscreen video: up to about half of the screen.
            screen = self.screen()
            available = int(screen.availableGeometry().height() * 0.5) if screen else 1200
        else:
            available = parent.height() - 180 if parent else 1200
        return max(100, min(height, max(100, available), 1200))

    def _resize_from_handle(self, height):
        self.user_height = self._bounded_height(height)
        self._update_geometry()

    def _save_height(self):
        if self.user_height is not None:
            self.height_changed.emit(self.user_height)

    def _wheel(self, event):
        if self.track.drag or self.track.duration <= 0:
            event.accept()
            return
        delta = event.pixelDelta() if not event.pixelDelta().isNull() else event.angleDelta()
        horizontal = self.scroll.horizontalScrollBar()
        if event.modifiers() & Qt.KeyboardModifier.ShiftModifier or (delta.x() and not delta.y()):
            self._clear_zoom_anchor()
            horizontal.setValue(horizontal.value() - (delta.y() or delta.x()))
        else:
            units = 40.0 if not event.pixelDelta().isNull() else 120.0
            self.wheel_remainder += delta.y() / units
            steps = math.trunc(self.wheel_remainder)
            self.wheel_remainder -= steps
            if steps:
                viewport_x = self.scroll.viewport().mapFromGlobal(event.globalPosition().toPoint()).x()
                anchor = self.track.time_for_x(horizontal.value() + viewport_x)
                self.zoom_anchor = (anchor, viewport_x)
                self.wheel_zoom_active = True
                try:
                    self.zoom.setValue(max(self.zoom.minimum(), min(self.zoom.maximum(), self.zoom.value() + steps)))
                    self._update_zoom()
                finally:
                    self.wheel_zoom_active = False
        event.accept()

    def eventFilter(self, watched, event):
        if watched in (self.track, self.scroll.viewport()) and event.type() == QEvent.Type.Wheel:
            self._wheel(event)
            return True
        if watched is self.parentWidget() and event.type() == QEvent.Type.Resize:
            self._update_geometry()
        if watched is self.scroll.viewport() and event.type() == QEvent.Type.Resize:
            self._update_zoom()
            self.viewport_changed.emit()
        return super().eventFilter(watched, event)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._update_zoom()

    def update_position(self, current, duration):
        self.track.position = current
        self.track.duration = duration or 0.0
        self.track.update()

    def select_row(self, row):
        self._clear_zoom_anchor()
        if self.track.selected_row == row:
            return
        self.track.set_selected(row)
        if 0 <= row < len(self.track.intervals):
            rect = self.track.rect_for_row(row)
            viewport_width = self.scroll.viewport().width()
            center = min(rect.center().x(), rect.left() + viewport_width / 2 - 20)
            self.scroll.horizontalScrollBar().setValue(int(center - viewport_width / 2))
            self.scroll.ensureVisible(int(center), int(rect.center().y()), 20, 20)

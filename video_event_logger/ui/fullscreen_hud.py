from typing import List, Optional, Sequence, Tuple

from PySide6.QtCore import QEvent, QObject, QPoint, QRectF, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QCursor, QPainter
from PySide6.QtWidgets import (
    QButtonGroup, QFrame, QHBoxLayout, QLabel, QPushButton, QSlider, QStyle,
    QStyleOptionSlider, QVBoxLayout, QWidget,
)

from video_event_logger.services.time_utils import seconds_to_hhmmss
from video_event_logger.ui.event_colors import event_type_color

HUD_STYLE = """
QFrame#hudBar { background: rgba(10, 12, 16, 228); border: 1px solid rgba(255, 255, 255, 40); border-radius: 12px; }
QFrame#hudBar QLabel { color: #f2f4f7; background: transparent; border: 0; }
QLabel#hudTime { font-family: Menlo, "DejaVu Sans Mono", monospace; font-weight: 600; }
QLabel#hudDuration { font-family: Menlo, "DejaVu Sans Mono", monospace; color: #aeb6c4; }
QLabel#hudCaption { color: #aeb6c4; }
QSlider { background: transparent; border: 0; }
QSlider::groove:horizontal { height: 4px; background: rgba(255, 255, 255, 50); border: 0; border-radius: 2px; }
QSlider::sub-page:horizontal { background: rgba(255, 255, 255, 140); border-radius: 2px; }
QSlider::handle:horizontal { width: 14px; margin: -5px 0; background: #ffffff; border: 0; border-radius: 7px; }
QPushButton { color: #f2f4f7; background: rgba(255, 255, 255, 22); border: 0; border-radius: 7px; padding: 6px 10px; }
QPushButton:hover { background: rgba(255, 255, 255, 45); }
QPushButton:checked { background: #3b7bf6; color: #ffffff; font-weight: 600; }
QPushButton#hudPlay { background: #f2f4f7; color: #0b0d10; font-weight: 700; min-width: 74px; }
QPushButton#hudStart { background: #2a1215; color: #ffe1e2; border: 1px solid #ff5a5f; font-weight: 600; }
QPushButton#hudEnd { background: #ff5a5f; color: #1a0507; font-weight: 700; }
"""

EVENTS_PANEL_STYLE = (
    "QFrame#hudEvents { background: rgba(10, 12, 16, 228); "
    "border: 1px solid rgba(255, 255, 255, 40); border-radius: 12px; }"
)

PILL_STYLE = (
    "QLabel { color: #ffe1e2; background: #2a1215; border: 1px solid #ff5a5f; "
    "border-radius: 16px; padding: 7px 16px; font-weight: 600; }"
)
INFO_STYLE = (
    "QLabel { color: #f2f4f7; background: rgba(10, 12, 16, 200); border: 0; "
    "border-radius: 9px; padding: 7px 12px; }"
)
TOAST_STYLES = {
    "success": ("#cff5dd", "#16301f", "#2f8f55"),
    "error": ("#ffd7d8", "#33161a", "#c4464c"),
    "info": ("#cfe0ff", "#1f2a3d", "#3b7bf6"),
}


class MarkedSlider(QSlider):
    """Seek slider that also paints interval segments and the recording range."""

    def __init__(self, orientation, parent=None):
        super().__init__(orientation, parent)
        self.duration = 0.0
        self.segments = []  # type: List[Tuple[float, float, str]]
        self.pending = None  # type: Optional[Tuple[float, float]]

    def set_segments(self, segments: Sequence[Tuple[float, float, str]]) -> None:
        self.segments = list(segments)
        self.update()

    def set_pending(self, pending: Optional[Tuple[float, float]]) -> None:
        self.pending = pending
        self.update()

    def _groove(self):
        option = QStyleOptionSlider()
        self.initStyleOption(option)
        handle = self.style().subControlRect(QStyle.ComplexControl.CC_Slider, option, QStyle.SubControl.SC_SliderHandle, self)
        margin = handle.width() / 2.0
        return margin, max(1.0, self.width() - 2 * margin)

    def paintEvent(self, event):  # type: ignore[no-untyped-def]
        super().paintEvent(event)
        if self.duration <= 0 or not (self.segments or self.pending):
            return
        left, width = self._groove()
        middle = self.height() / 2.0
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(Qt.PenStyle.NoPen)
        def rect(start, end, height):
            x0 = left + width * max(0.0, start) / self.duration
            x1 = left + width * min(self.duration, end) / self.duration
            return QRectF(x0, middle - height / 2.0, max(2.0, x1 - x0), height)
        for start, end, color in self.segments:
            painter.setBrush(QColor(color))
            painter.drawRoundedRect(rect(start, end, 8), 2, 2)
        if self.pending is not None:
            painter.setBrush(QColor("#ff5a5f"))
            painter.drawRoundedRect(rect(self.pending[0], self.pending[1], 12), 2, 2)
        painter.end()


class FullscreenHud(QObject):
    seek_previewed = Signal(float)
    seek_requested = Signal(float)
    seek_relative_requested = Signal(float)
    play_pause_requested = Signal()
    frame_step_requested = Signal(int)
    speed_requested = Signal(float)
    interval_start_requested = Signal()
    interval_end_requested = Signal()
    interval_cancel_requested = Signal()
    events_bar_toggled = Signal(bool)

    MAX_CONTROL_BAR_WIDTH = 1240
    MAX_STATUS_LABEL_WIDTH = 760

    def __init__(self, video_surface: QWidget) -> None:
        super().__init__(video_surface)
        self.video_surface = video_surface
        self.foreground_overlay = None
        self.active = False
        self.controls_visible = False
        self.controls_always_visible = False
        self.is_slider_dragging = False
        self.notification_active = False
        self.duration_seconds = None  # type: Optional[float]
        self.current_seconds = 0.0
        self.interval_start_seconds = None  # type: Optional[float]
        self.interval_indicator_persistent = False
        self.event_type = "undefined"
        self.last_mouse_position = QCursor.pos()
        self.overlay_parent = video_surface.window()
        overlay_flags = (
            Qt.WindowType.Tool
            | Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.WindowDoesNotAcceptFocus
        )
        passive_overlay_flags = overlay_flags | Qt.WindowType.WindowTransparentForInput

        def passive_label(style: str) -> QLabel:
            label = QLabel(self.overlay_parent, passive_overlay_flags)
            label.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
            label.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)
            label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
            label.setTextFormat(Qt.TextFormat.PlainText)
            label.setStyleSheet(style)
            label.hide()
            return label

        # Recording pill: always on while an interval is active, never replaced by toasts.
        self.interval_label = passive_label(PILL_STYLE)
        # Short-lived feedback above the control bar.
        self.toast_label = passive_label("")
        self.toast_label.setWordWrap(True)
        # Video name, playlist position, save state (shown with the controls).
        self.info_label = passive_label(INFO_STYLE)
        self.info_text = ""

        self.notification_timer = QTimer(self)
        self.notification_timer.setSingleShot(True)
        self.notification_timer.timeout.connect(self._hide_notification)
        self.controls_hide_timer = QTimer(self)
        self.controls_hide_timer.setSingleShot(True)
        self.controls_hide_timer.setInterval(3000)
        self.controls_hide_timer.timeout.connect(self._auto_hide_controls)

        self.bottom_bar = QFrame(self.overlay_parent, overlay_flags)
        self.bottom_bar.setObjectName("hudBar")
        self.bottom_bar.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)
        self.bottom_bar.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.bottom_bar.setStyleSheet(HUD_STYLE)
        # Optional events bar: an overlay above the controls, never shrinking the video.
        self.events_panel = QFrame(self.overlay_parent, overlay_flags)
        self.events_panel.setObjectName("hudEvents")
        self.events_panel.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)
        self.events_panel.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.events_panel.setStyleSheet(EVENTS_PANEL_STYLE)
        self.events_layout = QVBoxLayout(self.events_panel)
        self.events_layout.setContentsMargins(8, 6, 8, 8)
        self.events_widget = None  # type: Optional[QWidget]
        self.events_panel.hide()
        bar_layout = QVBoxLayout(self.bottom_bar)
        bar_layout.setContentsMargins(14, 10, 14, 10)
        bar_layout.setSpacing(8)

        seek_row = QHBoxLayout()
        seek_row.setSpacing(10)
        self.current_time_label = QLabel("00:00:00.000")
        self.current_time_label.setObjectName("hudTime")
        self.timeline_slider = MarkedSlider(Qt.Orientation.Horizontal)
        self.timeline_slider.setRange(0, 0)
        self.timeline_slider.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.duration_label = QLabel("00:00:00.000")
        self.duration_label.setObjectName("hudDuration")
        seek_row.addWidget(self.current_time_label)
        seek_row.addWidget(self.timeline_slider, 1)
        seek_row.addWidget(self.duration_label)
        bar_layout.addLayout(seek_row)

        buttons = QHBoxLayout()
        buttons.setSpacing(6)
        self.play_button = self._button("▶ Play", self.play_pause_requested.emit, "hudPlay", "Play / pause (Space)")
        self.playback_label = self.play_button  # kept name: shows the playback state
        self.seek_back_10_button = self._make_seek_button("−10s", -10.0)
        self.seek_back_button = self._make_seek_button("−1s", -1.0)
        self.frame_back_button = self._button("‹", lambda: self.frame_step_requested.emit(-1), tip="Previous frame (,)")
        self.frame_forward_button = self._button("›", lambda: self.frame_step_requested.emit(1), tip="Next frame (.)")
        self.seek_forward_button = self._make_seek_button("+1s", 1.0)
        self.seek_forward_10_button = self._make_seek_button("+10s", 10.0)
        for widget in (self.play_button, self.seek_back_10_button, self.seek_back_button,
                       self.frame_back_button, self.frame_forward_button,
                       self.seek_forward_button, self.seek_forward_10_button):
            buttons.addWidget(widget)
        buttons.addSpacing(8)
        self.speed_group = QButtonGroup(self)
        self.speed_group.setExclusive(True)
        self.speed_buttons = {}
        for speed in (1.0, 2.0, 4.0, 8.0):
            button = self._button("×%d" % speed, lambda checked=False, s=speed: self.speed_requested.emit(s),
                                  tip="Playback speed (%d)" % speed)
            button.setCheckable(True)
            self.speed_group.addButton(button)
            self.speed_buttons[speed] = button
            buttons.addWidget(button)
        self.speed_label = QLabel("x1")  # compact speed text, kept for status/tests
        self.speed_label.hide()
        buttons.addStretch(1)
        self.events_button = self._button("Events  E", lambda: self.events_bar_toggled.emit(self.events_button.isChecked()),
                                          tip="Show the editable events bar above these controls (E)")
        self.events_button.setCheckable(True)
        buttons.addWidget(self.events_button)
        buttons.addSpacing(8)
        self.type_label = QLabel()
        self.type_label.setObjectName("hudCaption")
        self.type_label.setTextFormat(Qt.TextFormat.RichText)
        buttons.addWidget(self.type_label)
        buttons.addSpacing(8)
        self.start_button = self._button("● Start  A", self.interval_start_requested.emit, "hudStart", "Start an interval (A)")
        self.cancel_button = self._button("Cancel  Q", self.interval_cancel_requested.emit, tip="Cancel the active interval (Q)")
        self.end_button = self._button("End  D", self.interval_end_requested.emit, "hudEnd", "End the active interval (D)")
        for widget in (self.start_button, self.cancel_button, self.end_button):
            buttons.addWidget(widget)
        bar_layout.addLayout(buttons)

        self.timeline_slider.sliderPressed.connect(self._begin_slider_drag)
        self.timeline_slider.sliderMoved.connect(self._preview_slider_position)
        self.timeline_slider.sliderReleased.connect(self._finish_slider_drag)
        self.video_surface.installEventFilter(self)
        self.set_speed(1.0)
        self.set_event_type(self.event_type)
        self._sync_interval_buttons()
        self.set_active(False)

    def _button(self, text, handler, name="", tip=""):  # type: ignore[no-untyped-def]
        button = QPushButton(text)
        button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        if name:
            button.setObjectName(name)
        if tip:
            button.setToolTip(tip)
        button.clicked.connect(lambda checked=False: (self.notify_user_activity(), handler()))
        return button

    def _make_seek_button(self, text: str, seconds_delta: float) -> QPushButton:
        return self._button(text, lambda: self.seek_relative_requested.emit(seconds_delta),
                            tip="Seek %+d s" % seconds_delta)

    def eventFilter(self, watched, event) -> bool:  # type: ignore[no-untyped-def]
        if watched is self.events_widget and event.type() == QEvent.Type.Resize:
            self._layout_widgets()
        if watched is self.video_surface and event.type() in (
            QEvent.Type.Resize,
            QEvent.Type.Show,
        ):
            self._layout_widgets()
        # Hiding an overlay makes macOS send Enter/MouseMove to the video even
        # though the pointer did not move; only real movement shows the controls.
        if watched is self.video_surface and event.type() in (QEvent.Type.Enter, QEvent.Type.MouseMove):
            current_position = QCursor.pos()
            if current_position != self.last_mouse_position:
                self.last_mouse_position = current_position
                self.notify_user_activity()
        return super().eventFilter(watched, event)

    def set_active(self, active: bool) -> None:
        self.active = active
        if active:
            self.controls_visible = True
            self._layout_widgets()
            self._raise_widgets()
            self.controls_hide_timer.start()
            QTimer.singleShot(0, self._restore_active_overlays)
            QTimer.singleShot(150, self._restore_active_overlays)
            QTimer.singleShot(500, self._restore_active_overlays)
        else:
            self.controls_visible = False
            self.controls_hide_timer.stop()
            self.notification_timer.stop()
            self.notification_active = False
            for widget in (self.bottom_bar, self.interval_label, self.toast_label, self.info_label, self.events_panel):
                widget.hide()

    def set_controls_always_visible(self, enabled: bool) -> None:
        self.controls_always_visible = enabled
        if not self.active:
            return
        if enabled:
            self.controls_hide_timer.stop()
        self.notify_user_activity()

    def notify_user_activity(self) -> None:
        if not self.active:
            return
        self.controls_visible = True
        self._layout_widgets()
        self._raise_widgets()
        if self.is_slider_dragging:
            self.controls_hide_timer.stop()
        else:
            self.controls_hide_timer.start()

    # State from the controller ----------------------------------------

    def update_timeline(
        self,
        current_seconds: float,
        duration_seconds: Optional[float],
    ) -> None:
        self.duration_seconds = duration_seconds
        self.current_seconds = current_seconds
        if duration_seconds is None or duration_seconds <= 0:
            self.timeline_slider.setRange(0, 0)
            self.timeline_slider.setEnabled(False)
            self.timeline_slider.duration = 0.0
            self.duration_label.setText("00:00:00.000")
        else:
            maximum = int(duration_seconds * 1000)
            if self.timeline_slider.maximum() != maximum:
                self.timeline_slider.setRange(0, maximum)
            self.timeline_slider.duration = duration_seconds
            self.timeline_slider.setEnabled(True)
            self.duration_label.setText(seconds_to_hhmmss(duration_seconds))
        if not self.is_slider_dragging:
            self.timeline_slider.setValue(int(max(0.0, current_seconds) * 1000))
            self.current_time_label.setText(seconds_to_hhmmss(current_seconds))
        if self.interval_start_seconds is not None:
            self.timeline_slider.set_pending((self.interval_start_seconds, max(self.interval_start_seconds, current_seconds)))
            self._update_pill_text()
        if self.active:
            self._raise_widgets()

    def set_intervals(self, intervals) -> None:  # type: ignore[no-untyped-def]
        self.timeline_slider.set_segments([
            (i.start_time_seconds, i.end_time_seconds, event_type_color(i.event_type)) for i in intervals
        ])

    def set_event_type(self, event_type: str) -> None:
        self.event_type = (event_type or "").strip() or "undefined"
        self.type_label.setText(
            "Type <span style='color:%s'>●</span> <b style='color:#f2f4f7'>%s</b>"
            % (event_type_color(self.event_type), self.event_type.replace("&", "&amp;").replace("<", "&lt;"))
        )
        self._update_pill_text()

    def attach_events_bar(self, widget: QWidget) -> None:
        if self.events_widget is widget:
            return
        self.events_widget = widget
        self.events_layout.addWidget(widget)
        widget.installEventFilter(self)
        widget.show()
        self.set_events_bar_checked(True)
        self._layout_widgets()
        self._raise_widgets()

    def detach_events_bar(self) -> Optional[QWidget]:
        widget, self.events_widget = self.events_widget, None
        if widget is not None:
            widget.removeEventFilter(self)
            self.events_layout.removeWidget(widget)
        self.events_panel.hide()
        self.set_events_bar_checked(False)
        return widget

    def set_events_bar_checked(self, checked: bool) -> None:
        self.events_button.blockSignals(True)
        self.events_button.setChecked(checked)
        self.events_button.blockSignals(False)

    def _pointer_over_controls(self) -> bool:
        position = QCursor.pos()
        panels = [self.bottom_bar] + ([self.events_panel] if self.events_widget is not None else [])
        return any(panel.isVisible() and panel.geometry().contains(position) for panel in panels)

    def _interaction_in_progress(self) -> bool:
        from PySide6.QtWidgets import QApplication
        track = getattr(self.events_widget, "track", None)
        return (
            self.is_slider_dragging
            or getattr(track, "drag", None) is not None
            or QApplication.activePopupWidget() is not None
        )

    def set_info(self, text: str) -> None:
        self.info_text = text
        self.info_label.setText(text)
        if self.active:
            self._layout_widgets()
            self._raise_widgets()

    def set_playback_active(self, active: bool) -> None:
        self.play_button.setText("❚❚ Pause" if active else "▶ Play")
        self.playing = active

    def set_speed(self, speed: float) -> None:
        self.speed_label.setText("x%d" % int(speed))
        button = self.speed_buttons.get(float(speed))
        if button is not None:
            button.setChecked(True)

    def set_pending_interval_start(
        self,
        start_seconds: Optional[float],
        persistent: bool = True,
    ) -> None:
        self.interval_start_seconds = start_seconds
        self.interval_indicator_persistent = start_seconds is not None and persistent
        self._sync_interval_buttons()
        if start_seconds is None:
            self.timeline_slider.set_pending(None)
            self.interval_label.hide()
            return
        self.timeline_slider.set_pending((start_seconds, max(start_seconds, self.current_seconds)))
        self._show_active_interval()

    def show_notification(
        self,
        text: str,
        level: str = "info",
        persistent: bool = False,
    ) -> None:
        if not self.active or not text.strip():
            return
        foreground, background, border = TOAST_STYLES.get(level, TOAST_STYLES["info"])
        self.toast_label.setStyleSheet(
            "QLabel { color: %s; background: %s; border: 1px solid %s; "
            "border-radius: 9px; padding: 8px 14px; font-weight: 600; }"
            % (foreground, background, border)
        )
        self.toast_label.setText(text.strip())
        self.notification_active = True
        self._layout_widgets()
        self._raise_widgets()
        self.notification_timer.stop()
        if not persistent:
            self.notification_timer.start(2600)

    # Internals ----------------------------------------------------------

    def _sync_interval_buttons(self) -> None:
        recording = self.interval_start_seconds is not None
        self.start_button.setVisible(not recording)
        self.cancel_button.setVisible(recording)
        self.end_button.setVisible(recording)

    def _update_pill_text(self) -> None:
        if self.interval_start_seconds is None:
            return
        elapsed = max(0.0, self.current_seconds - self.interval_start_seconds)
        self.interval_label.setText(
            "● REC  %s  ·  from %s  ·  %.1f s     D end  ·  Q cancel"
            % (self.event_type, seconds_to_hhmmss(self.interval_start_seconds), elapsed)
        )

    def _begin_slider_drag(self) -> None:
        self.is_slider_dragging = True
        self.notify_user_activity()

    def _preview_slider_position(self, value: int) -> None:
        seconds = value / 1000.0
        self.current_time_label.setText(seconds_to_hhmmss(seconds))
        self.notify_user_activity()
        self.seek_previewed.emit(seconds)

    def _finish_slider_drag(self) -> None:
        self.is_slider_dragging = False
        seconds = self.timeline_slider.value() / 1000.0
        self.current_time_label.setText(seconds_to_hhmmss(seconds))
        self.notify_user_activity()
        self.seek_requested.emit(seconds)

    def _request_relative_seek(self, seconds_delta: float) -> None:
        self.notify_user_activity()
        self.seek_relative_requested.emit(seconds_delta)

    def _hide_notification(self) -> None:
        self.notification_active = False
        self.toast_label.hide()

    def _show_active_interval(self) -> None:
        if self.interval_start_seconds is None:
            return
        self._update_pill_text()
        self._layout_widgets()
        self._raise_widgets()

    def _auto_hide_controls(self) -> None:
        if not self.active or self.controls_always_visible:
            return
        if self._interaction_in_progress() or self._pointer_over_controls():
            self.controls_hide_timer.start(500)
            return
        self.controls_visible = False
        self.last_mouse_position = QCursor.pos()
        self.bottom_bar.hide()
        self.info_label.hide()
        self.events_panel.hide()
        self._layout_widgets()

    def _restore_active_overlays(self) -> None:
        if not self.active:
            return
        self._layout_widgets()
        self._raise_widgets()

    def _layout_widgets(self) -> None:
        width = self.video_surface.width()
        height = self.video_surface.height()
        if width <= 0 or height <= 0:
            return
        origin = self.video_surface.mapToGlobal(QPoint(0, 0))
        margin = max(12, min(24, width // 50))
        available_width = max(1, width - (margin * 2))
        bar_height = 88
        bar_width = min(self.MAX_CONTROL_BAR_WIDTH, available_width)
        bar_x = origin.x() + max(0, (width - bar_width) // 2)
        bar_y = origin.y() + max(margin, height - bar_height - margin)
        self.bottom_bar.setGeometry(bar_x, bar_y, bar_width, bar_height)

        events_top = bar_y
        if self.events_widget is not None:
            panel_height = max(110, min(int(height * 0.55), self.events_widget.height() + 14))
            events_top = bar_y - panel_height - 8
            self.events_panel.setGeometry(bar_x, events_top, bar_width, panel_height)

        max_label_width = max(1, min(self.MAX_STATUS_LABEL_WIDTH, available_width))
        self.interval_label.setMaximumWidth(max_label_width)
        self.interval_label.adjustSize()
        label_x = origin.x() + max(0, (width - self.interval_label.width()) // 2)
        self.interval_label.move(label_x, origin.y() + margin)

        self.toast_label.setMaximumWidth(max_label_width)
        self.toast_label.adjustSize()
        toast_bottom = (events_top - 12) if self.controls_visible else (origin.y() + height - margin)
        self.toast_label.move(
            origin.x() + max(0, (width - self.toast_label.width()) // 2),
            toast_bottom - self.toast_label.height(),
        )

        self.info_label.setMaximumWidth(max(1, available_width // 2 - 40))
        self.info_label.adjustSize()
        self.info_label.move(origin.x() + margin, origin.y() + margin)

    def _raise_widgets(self) -> None:
        if not self.active:
            return
        if self.controls_visible:
            self.bottom_bar.show()
            self.bottom_bar.raise_()
        else:
            self.bottom_bar.hide()
        show_events = self.controls_visible and self.events_widget is not None
        if show_events != self.events_panel.isVisible():
            self.events_panel.setVisible(show_events)
        if show_events:
            self.events_panel.raise_()
        self.info_label.setVisible(self.controls_visible and bool(self.info_text))
        if self.info_label.isVisible():
            self.info_label.raise_()
        if self.interval_indicator_persistent and self.interval_start_seconds is not None:
            self.interval_label.show()
            self.interval_label.raise_()
        else:
            self.interval_label.hide()
        if self.notification_active:
            self.toast_label.show()
            self.toast_label.raise_()
        else:
            self.toast_label.hide()
        if self.foreground_overlay is not None and self.foreground_overlay.isVisible():
            self.foreground_overlay.raise_()

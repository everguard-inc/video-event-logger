from typing import Optional

from PySide6.QtCore import QEvent, QObject, QPoint, Qt, QTimer, Signal
from PySide6.QtGui import QCursor
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QPushButton, QSlider, QWidget

from video_event_logger.services.time_utils import seconds_to_hhmmss


class FullscreenHud(QObject):
    seek_previewed = Signal(float)
    seek_requested = Signal(float)
    seek_relative_requested = Signal(float)

    MAX_CONTROL_BAR_WIDTH = 920
    MAX_STATUS_LABEL_WIDTH = 560

    def __init__(self, video_surface: QWidget) -> None:
        super().__init__(video_surface)
        self.video_surface = video_surface
        self.active = False
        self.controls_visible = False
        self.controls_always_visible = False
        self.is_slider_dragging = False
        self.notification_active = False
        self.duration_seconds = None  # type: Optional[float]
        self.interval_start_seconds = None  # type: Optional[float]
        self.interval_indicator_persistent = False
        self.last_mouse_position = QCursor.pos()
        self.overlay_parent = video_surface.window()
        overlay_flags = (
            Qt.WindowType.Tool
            | Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.WindowDoesNotAcceptFocus
        )
        passive_overlay_flags = overlay_flags | Qt.WindowType.WindowTransparentForInput

        self.interval_label = QLabel(self.overlay_parent, passive_overlay_flags)
        self.interval_label.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.interval_label.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)
        self.interval_label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.interval_label.setWordWrap(True)
        self.notification_timer = QTimer(self)
        self.notification_timer.setSingleShot(True)
        self.notification_timer.timeout.connect(self._hide_notification)
        self.controls_hide_timer = QTimer(self)
        self.controls_hide_timer.setSingleShot(True)
        self.controls_hide_timer.setInterval(3000)
        self.controls_hide_timer.timeout.connect(self._auto_hide_controls)

        self.bottom_bar = QFrame(self.overlay_parent, overlay_flags)
        self.bottom_bar.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)
        self.bottom_bar.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.bottom_bar.setStyleSheet(
            "QFrame { background: #111820; "
            "border: 1px solid #7b8794; border-radius: 6px; }"
            "QLabel { color: #f5f7fa; background: transparent; border: 0; }"
            "QSlider { background: transparent; border: 0; }"
            "QSlider::groove:horizontal { height: 6px; background: #69737e; "
            "border: 0; border-radius: 3px; }"
            "QSlider::sub-page:horizontal { background: #3e9bf2; border-radius: 3px; }"
            "QSlider::handle:horizontal { width: 16px; margin: -5px 0; "
            "background: #ffffff; border: 1px solid #2d78bd; border-radius: 8px; }"
            "QPushButton { color: #f5f7fa; background: #26313d; "
            "border: 1px solid #7b8794; border-radius: 4px; padding: 3px 6px; }"
            "QPushButton:hover { background: #34424f; }"
            "QPushButton:pressed { background: #246fbd; }"
        )
        bottom_layout = QHBoxLayout(self.bottom_bar)
        bottom_layout.setContentsMargins(8, 4, 8, 4)
        bottom_layout.setSpacing(6)

        self.current_time_label = QLabel("00:00:00.000")
        self.current_time_label.setMinimumWidth(92)
        self.current_time_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.timeline_slider = QSlider(Qt.Orientation.Horizontal)
        self.timeline_slider.setRange(0, 0)
        self.timeline_slider.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.duration_label = QLabel("00:00:00.000")
        self.duration_label.setMinimumWidth(92)
        self.duration_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.playback_label = QLabel("PAUSED")
        self.playback_label.setMinimumWidth(58)
        self.playback_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.speed_label = QLabel("x1")
        self.speed_label.setMinimumWidth(34)
        self.speed_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.speed_label.setStyleSheet(
            "QLabel { color: #ffffff; background: #246fbd; border: 1px solid #79b8f2; "
            "border-radius: 4px; padding: 3px 5px; font-weight: 700; }"
        )

        self.seek_back_10_button = self._make_seek_button("-10s", -10.0)
        self.seek_back_button = self._make_seek_button("-1s", -1.0)
        self.seek_forward_button = self._make_seek_button("+1s", 1.0)
        self.seek_forward_10_button = self._make_seek_button("+10s", 10.0)

        bottom_layout.addWidget(self.seek_back_10_button)
        bottom_layout.addWidget(self.seek_back_button)
        bottom_layout.addWidget(self.current_time_label)
        bottom_layout.addWidget(self.timeline_slider, 1)
        bottom_layout.addWidget(self.duration_label)
        bottom_layout.addWidget(self.seek_forward_button)
        bottom_layout.addWidget(self.seek_forward_10_button)
        bottom_layout.addWidget(self.playback_label)
        bottom_layout.addWidget(self.speed_label)

        self.timeline_slider.sliderPressed.connect(self._begin_slider_drag)
        self.timeline_slider.sliderMoved.connect(self._preview_slider_position)
        self.timeline_slider.sliderReleased.connect(self._finish_slider_drag)
        self.video_surface.installEventFilter(self)
        self.set_active(False)

    def _make_seek_button(self, text: str, seconds_delta: float) -> QPushButton:
        button = QPushButton(text)
        button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        button.clicked.connect(lambda: self._request_relative_seek(seconds_delta))
        return button

    def eventFilter(self, watched, event) -> bool:  # type: ignore[no-untyped-def]
        if watched is self.video_surface and event.type() in (
            QEvent.Type.Resize,
            QEvent.Type.Show,
        ):
            self._layout_widgets()
        if watched is self.video_surface and event.type() == QEvent.Type.Enter:
            self.last_mouse_position = QCursor.pos()
            self.notify_user_activity()
        if watched is self.video_surface and event.type() == QEvent.Type.MouseMove:
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
            self.bottom_bar.hide()
            self.interval_label.hide()

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
        self.bottom_bar.show()
        self.bottom_bar.raise_()
        if self.is_slider_dragging:
            self.controls_hide_timer.stop()
        else:
            self.controls_hide_timer.start()

    def update_timeline(
        self,
        current_seconds: float,
        duration_seconds: Optional[float],
    ) -> None:
        self.duration_seconds = duration_seconds
        if duration_seconds is None or duration_seconds <= 0:
            self.timeline_slider.setRange(0, 0)
            self.timeline_slider.setEnabled(False)
            self.duration_label.setText("00:00:00.000")
        else:
            maximum = int(duration_seconds * 1000)
            if self.timeline_slider.maximum() != maximum:
                self.timeline_slider.setRange(0, maximum)
            self.timeline_slider.setEnabled(True)
            self.duration_label.setText(seconds_to_hhmmss(duration_seconds))
        if not self.is_slider_dragging:
            self.timeline_slider.setValue(int(max(0.0, current_seconds) * 1000))
            self.current_time_label.setText(seconds_to_hhmmss(current_seconds))
        if self.active:
            self._raise_widgets()

    def set_playback_active(self, active: bool) -> None:
        self.playback_label.setText("PLAYING" if active else "PAUSED")

    def set_speed(self, speed: float) -> None:
        self.speed_label.setText("x%d" % int(speed))

    def set_pending_interval_start(
        self,
        start_seconds: Optional[float],
        persistent: bool = True,
    ) -> None:
        self.interval_start_seconds = start_seconds
        self.interval_indicator_persistent = start_seconds is not None and persistent
        if start_seconds is None:
            if not self.notification_active:
                self.interval_label.hide()
            return
        self.notification_timer.stop()
        self.notification_active = False
        self._show_active_interval()

    def show_notification(
        self,
        text: str,
        level: str = "info",
        persistent: bool = False,
    ) -> None:
        if not self.active or not text.strip():
            return
        appearances = {
            "success": ("#d5f5df", "#145c2e", "#62a978"),
            "error": ("#ffd9dc", "#701b23", "#d66a73"),
            "info": ("#e7f2ff", "#184169", "#6ea8dc"),
        }
        foreground, background, border = appearances.get(level, appearances["info"])
        self.interval_label.setStyleSheet(
            "QLabel { color: %s; background: %s; border: 1px solid %s; "
            "border-radius: 5px; padding: 7px 12px; font-weight: 600; }"
            % (foreground, background, border)
        )
        self.interval_label.setText(text.strip())
        self.notification_active = True
        self.interval_label.show()
        self._layout_widgets()
        self._raise_widgets()
        self.notification_timer.stop()
        if not persistent:
            self.notification_timer.start(2200)

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
        if self.interval_indicator_persistent and self.interval_start_seconds is not None:
            self._show_active_interval()
        else:
            self.interval_label.hide()

    def _show_active_interval(self) -> None:
        if self.interval_start_seconds is None:
            return
        self.interval_label.setStyleSheet(
            "QLabel { color: #ffe3a3; background: #4f3b08; "
            "border: 1px solid #e0ad16; border-radius: 5px; "
            "padding: 6px 10px; font-weight: 700; }"
        )
        self.interval_label.setText(
            "● INTERVAL ACTIVE · start %s"
            % seconds_to_hhmmss(self.interval_start_seconds)
        )
        self.interval_label.setVisible(self.active and self.interval_indicator_persistent)
        self._layout_widgets()
        self._raise_widgets()

    def _auto_hide_controls(self) -> None:
        if not self.active or self.controls_always_visible:
            return
        if self.is_slider_dragging or self.bottom_bar.geometry().contains(QCursor.pos()):
            self.controls_hide_timer.start(500)
            return
        self.controls_visible = False
        self.bottom_bar.hide()

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
        bar_height = 42
        bar_width = min(self.MAX_CONTROL_BAR_WIDTH, available_width)
        bar_x = origin.x() + max(0, (width - bar_width) // 2)
        self.bottom_bar.setGeometry(
            bar_x,
            origin.y() + max(margin, height - bar_height - margin),
            bar_width,
            bar_height,
        )

        max_label_width = max(
            1,
            min(self.MAX_STATUS_LABEL_WIDTH, available_width),
        )
        self.interval_label.setMaximumWidth(max_label_width)
        self.interval_label.adjustSize()
        label_x = origin.x() + max(0, (width - self.interval_label.width()) // 2)
        self.interval_label.move(label_x, origin.y() + margin)

    def _raise_widgets(self) -> None:
        if self.active:
            if self.controls_visible:
                self.bottom_bar.show()
                self.bottom_bar.raise_()
            else:
                self.bottom_bar.hide()
            if self.interval_indicator_persistent or self.notification_active:
                self.interval_label.show()
                self.interval_label.raise_()
            else:
                self.interval_label.hide()

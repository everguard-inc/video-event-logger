from typing import Optional

from PySide6.QtCore import QEvent, Qt, Signal
from PySide6.QtGui import QColor, QPalette
from PySide6.QtWidgets import (
    QButtonGroup,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QSlider,
    QStyle,
    QStyleOptionSlider,
    QVBoxLayout,
    QWidget,
)

from video_event_logger.services.time_utils import seconds_to_hhmmss
from video_event_logger.ui.event_colors import event_type_color
from video_event_logger.ui.video_player import VideoPlayer
from video_event_logger.tasks.event_logging.ui.annotation_timeline import AnnotationTimeline


class TimelineSlider(QSlider):
    axis_changed = Signal()

    def axis_margin(self):
        option = QStyleOptionSlider()
        self.initStyleOption(option)
        option.sliderPosition = option.minimum
        handle = self.style().subControlRect(
            QStyle.ComplexControl.CC_Slider, option, QStyle.SubControl.SC_SliderHandle, self
        )
        return handle.width() / 2.0

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.axis_changed.emit()

    def changeEvent(self, event):
        super().changeEvent(event)
        if event.type() == QEvent.Type.StyleChange:
            self.axis_changed.emit()


class PlayerPanel(QWidget):
    event_type_chosen = Signal(str)

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.is_slider_dragging = False
        self.events_bar_enabled = True
        self.fullscreen_events_bar_enabled = False
        self.video_only_mode = False
        self.video_player = VideoPlayer(self)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self.video_player, 1)

        self.annotation_timeline = AnnotationTimeline(self)
        layout.addWidget(self.annotation_timeline)

        timeline_layout = QHBoxLayout()
        timeline_layout.setContentsMargins(0, 0, 0, 0)
        timeline_layout.setSpacing(6)
        self.timeline_current_label = QLabel("00:00:00.000")
        self.timeline_current_label.setMinimumWidth(92)
        self.timeline_duration_label = QLabel("00:00:00.000")
        self.timeline_duration_label.setMinimumWidth(92)
        self.timeline_slider = TimelineSlider(Qt.Orientation.Horizontal)
        self.timeline_slider.axis_changed.connect(self._sync_timeline_axis)
        self.timeline_slider.setRange(0, 0)
        self.timeline_slider.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        timeline_layout.addWidget(self.timeline_current_label)
        timeline_layout.addWidget(QLabel("/"))
        timeline_layout.addWidget(self.timeline_duration_label)
        self.interval_state_label = QLabel("Interval: ready")
        self.interval_state_label.setObjectName("intervalStateLabel")
        self.interval_state_label.setMinimumWidth(250)
        self.interval_state_label.setAlignment(
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
        )
        timeline_layout.addStretch()
        timeline_layout.addWidget(self.interval_state_label)
        self.seek_layout = QHBoxLayout()
        self.seek_layout.setContentsMargins(0, 0, 0, 0)
        self.seek_layout.addWidget(self.timeline_slider)
        layout.addLayout(self.seek_layout)
        self.annotation_timeline.viewport_changed.connect(self._sync_seek_width)
        self.timeline_info = QWidget()
        self.timeline_info.setLayout(timeline_layout)
        layout.addWidget(self.timeline_info)

        def segmented(buttons):
            frame = QFrame()
            frame.setObjectName("segmented")
            row = QHBoxLayout(frame)
            row.setContentsMargins(2, 2, 2, 2)
            row.setSpacing(2)
            for button in buttons:
                row.addWidget(button)
            return frame

        self.play_pause_button = QPushButton("▶ Play")
        self.play_pause_button.setMinimumWidth(92)
        self.seek_back_10_button = QPushButton("−10s")
        self.seek_back_button = QPushButton("−1s")
        self.seek_forward_button = QPushButton("+1s")
        self.seek_forward_10_button = QPushButton("+10s")
        self.frame_back_button = QPushButton("‹ frame")
        self.frame_forward_button = QPushButton("frame ›")
        self.speed_1_button = QPushButton("×1")
        self.speed_2_button = QPushButton("×2")
        self.speed_4_button = QPushButton("×4")
        self.speed_8_button = QPushButton("×8")
        self.set_start_button = QPushButton("Start")
        self.set_start_button.setObjectName("startButton")
        self.set_end_button = QPushButton("End")
        self.set_end_button.setObjectName("endButton")
        self.cancel_interval_button = QPushButton("Cancel")
        self.cancel_interval_button.setObjectName("cancelIntervalButton")
        self.cancel_interval_button.setToolTip("Cancel the active interval (Q)")
        for button, tip in (
            (self.seek_back_10_button, "Back 10 s (Shift+←)"), (self.seek_back_button, "Back 1 s (←)"),
            (self.seek_forward_button, "Forward 1 s (→)"), (self.seek_forward_10_button, "Forward 10 s (Shift+→)"),
            (self.frame_back_button, "Previous frame (,)"), (self.frame_forward_button, "Next frame (.)"),
            (self.speed_1_button, "Normal speed (1)"), (self.speed_2_button, "Speed ×2 (2)"),
            (self.speed_4_button, "Speed ×4 (4)"), (self.speed_8_button, "Speed ×8 (8)"),
        ):
            button.setToolTip(tip)
        self.control_buttons = [
            self.play_pause_button,
            self.seek_back_10_button,
            self.seek_back_button,
            self.seek_forward_button,
            self.seek_forward_10_button,
            self.frame_back_button,
            self.frame_forward_button,
            self.speed_1_button,
            self.speed_2_button,
            self.speed_4_button,
            self.speed_8_button,
            self.set_start_button,
            self.set_end_button,
        ]
        for button in self.control_buttons + [self.cancel_interval_button]:
            button.setFocusPolicy(Qt.FocusPolicy.NoFocus)

        # Transport: play, seek and frame steps, speed.
        self.transport_bar = QWidget()
        transport = QHBoxLayout(self.transport_bar)
        transport.setContentsMargins(0, 6, 0, 0)
        transport.setSpacing(8)
        transport.addWidget(self.play_pause_button)
        transport.addWidget(segmented([
            self.seek_back_10_button, self.seek_back_button, self.frame_back_button,
            self.frame_forward_button, self.seek_forward_button, self.seek_forward_10_button,
        ]))
        transport.addWidget(segmented([self.speed_1_button, self.speed_2_button, self.speed_4_button, self.speed_8_button]))
        transport.addStretch(1)
        layout.addWidget(self.transport_bar)

        # Mark bar: event type for new intervals, Start / End / Cancel.
        self.mark_bar = QFrame()
        self.mark_bar.setObjectName("controlCard")
        mark = QHBoxLayout(self.mark_bar)
        mark.setContentsMargins(12, 8, 12, 8)
        mark.setSpacing(8)
        caption = QLabel("Event type")
        caption.setObjectName("sectionCaption")
        mark.addWidget(caption)
        self.event_type_slot = QHBoxLayout()
        self.event_type_slot.setSpacing(6)
        mark.addLayout(self.event_type_slot)
        self.type_chips_layout = QHBoxLayout()
        self.type_chips_layout.setSpacing(6)
        mark.addLayout(self.type_chips_layout)
        mark.addStretch(1)
        mark.addWidget(self.set_start_button)
        mark.addWidget(self.cancel_interval_button)
        mark.addWidget(self.set_end_button)
        self.type_chip_buttons = []
        layout.addSpacing(6)
        layout.addWidget(self.mark_bar)

        self.play_pause_button.setCheckable(True)
        self.speed_button_group = QButtonGroup(self)
        self.speed_button_group.setExclusive(True)
        self.speed_buttons = {
            1.0: self.speed_1_button,
            2.0: self.speed_2_button,
            4.0: self.speed_4_button,
            8.0: self.speed_8_button,
        }
        for speed_button in self.speed_buttons.values():
            speed_button.setCheckable(True)
            self.speed_button_group.addButton(speed_button)
        self.set_active_speed(1.0)
        self.set_playback_active(False)
        self.video_chrome_widgets = [
            self.timeline_info,
            self.timeline_current_label,
            self.timeline_slider,
            self.timeline_duration_label,
            self.interval_state_label,
            self.transport_bar,
            self.mark_bar,
            *self.control_buttons,
        ]
        self.set_pending_interval_start(None)

        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setMinimumHeight(180)

    def set_recent_event_types(self, event_types, current: str) -> None:
        """One-click chips for the event types used most in this video."""
        while self.type_chip_buttons:
            button = self.type_chip_buttons.pop()
            self.type_chips_layout.removeWidget(button)
            button.deleteLater()
        for index, event_type in enumerate(event_types[:4], start=1):
            button = QPushButton("●  %s" % event_type)
            button.setObjectName("typeChip")
            button.setCheckable(True)
            button.setChecked(event_type == current)
            button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            button.setToolTip("Use %s for new intervals" % event_type)
            button.setStyleSheet("QPushButton#typeChip { color: %s; }" % event_type_color(event_type) if event_type != current else "")
            button.clicked.connect(lambda checked=False, value=event_type: self.event_type_chosen.emit(value))
            self.type_chips_layout.addWidget(button)
            self.type_chip_buttons.append(button)

    def set_video_loaded(self, loaded: bool) -> None:
        for button in self.control_buttons:
            button.setEnabled(loaded)
        self.timeline_slider.setEnabled(loaded)
        self.annotation_timeline.setEnabled(loaded)

    def set_video_only_mode(self, enabled: bool) -> None:
        self.video_only_mode = enabled
        # The fullscreen events bar is always dark, whatever the app theme.
        self.annotation_timeline.setProperty("fullscreen", enabled)
        if enabled:
            palette = QPalette(self.annotation_timeline.palette())
            for role, color in (
                (QPalette.ColorRole.Window, "#0e1116"), (QPalette.ColorRole.Base, "#0e1116"),
                (QPalette.ColorRole.Text, "#c9ced8"), (QPalette.ColorRole.WindowText, "#c9ced8"),
                (QPalette.ColorRole.Mid, "#2a303a"), (QPalette.ColorRole.Button, "#1d222b"),
                (QPalette.ColorRole.ButtonText, "#e6e8ec"), (QPalette.ColorRole.Highlight, "#ffffff"),
            ):
                palette.setColor(role, QColor(color))
            self.annotation_timeline.setPalette(palette)
            self.annotation_timeline.setAutoFillBackground(True)
            self.annotation_timeline.setStyleSheet(
                "QWidget { background: #0e1116; color: #c9ced8; } "
                "QPushButton { background: #1d222b; border: 1px solid #2c323d; color: #e6e8ec; }"
            )
        else:
            self.annotation_timeline.setPalette(QPalette())
            self.annotation_timeline.setAutoFillBackground(False)
            self.annotation_timeline.setStyleSheet("")
        self._update_events_bar_visibility()
        for widget in self.video_chrome_widgets:
            widget.setVisible(not enabled)
        if hasattr(self.video_player, "set_fullscreen_hud_active"):
            self.video_player.set_fullscreen_hud_active(enabled)

    def set_events_bar_enabled(self, enabled: bool) -> None:
        self.events_bar_enabled = enabled
        self._update_events_bar_visibility()
        self._sync_seek_width()

    def set_fullscreen_events_bar_enabled(self, enabled: bool) -> None:
        self.fullscreen_events_bar_enabled = enabled
        self._update_events_bar_visibility()

    def _update_events_bar_visibility(self) -> None:
        hud = getattr(self.video_player, "fullscreen_hud", None)
        overlay = self.video_only_mode and self.fullscreen_events_bar_enabled and hasattr(hud, "attach_events_bar")
        if overlay:
            # Fullscreen: the events bar floats above the controls, so the video keeps its full size.
            hud.attach_events_bar(self.annotation_timeline)
            self.annotation_timeline.setVisible(True)
            return
        if hasattr(hud, "detach_events_bar") and getattr(hud, "events_widget", None) is self.annotation_timeline:
            hud.detach_events_bar()
            self.layout().insertWidget(1, self.annotation_timeline)
        if hasattr(hud, "set_events_bar_checked"):
            hud.set_events_bar_checked(self.fullscreen_events_bar_enabled)
        self.annotation_timeline.setVisible(
            False if self.video_only_mode else self.events_bar_enabled
        )

    def _sync_seek_width(self) -> None:
        scroll = self.annotation_timeline.scroll
        right_margin = max(0, scroll.width() - scroll.viewport().width()) if self.events_bar_enabled else 0
        self.seek_layout.setContentsMargins(0, 0, right_margin, 0)

    def _sync_timeline_axis(self) -> None:
        self.annotation_timeline.track.axis_margin = self.timeline_slider.axis_margin()
        self.annotation_timeline.track.update()

    def set_active_speed(self, speed: float) -> None:
        for button_speed, button in self.speed_buttons.items():
            button.setChecked(button_speed == speed)
        if hasattr(self.video_player, "set_fullscreen_hud_speed"):
            self.video_player.set_fullscreen_hud_speed(speed)

    def set_playback_active(self, active: bool) -> None:
        self.play_pause_button.setChecked(active)
        self.play_pause_button.setText("❚❚ Pause" if active else "▶ Play")
        self.play_pause_button.setToolTip("Pause playback" if active else "Start playback")
        if hasattr(self.video_player, "set_fullscreen_hud_playback_active"):
            self.video_player.set_fullscreen_hud_playback_active(active)

    def set_pending_interval_start(
        self,
        start_seconds: Optional[float],
        persistent_in_fullscreen: bool = True,
    ) -> None:
        if hasattr(self.video_player, "set_fullscreen_hud_interval_state"):
            self.video_player.set_fullscreen_hud_interval_state(
                start_seconds,
                persistent_in_fullscreen,
            )
        elif hasattr(self.video_player, "set_fullscreen_hud_interval_start"):
            self.video_player.set_fullscreen_hud_interval_start(start_seconds)
        if start_seconds is None:
            self.interval_state_label.setText("Interval: ready")
            self._set_feedback_state(self.interval_state_label, "ready")
            self.interval_state_label.setToolTip("Press Start or A to begin an interval.")
            self.set_start_button.setText("Start")
            self._set_feedback_state(self.set_start_button, "idle")
            self.set_start_button.setToolTip("Start an interval at the current frame (A)")
            self._set_feedback_state(self.set_end_button, "idle")
            self.set_end_button.setToolTip("End the active interval (D)")
            self.cancel_interval_button.hide()
            return

        formatted_start = seconds_to_hhmmss(start_seconds)
        self.interval_state_label.setText("INTERVAL ACTIVE — start %s" % formatted_start)
        self._set_feedback_state(self.interval_state_label, "active")
        self.interval_state_label.setToolTip(
            "Interval start is set to %s. Press End or D to finish." % formatted_start
        )
        self.set_start_button.setText("Start set")
        self._set_feedback_state(self.set_start_button, "start-set")
        self.set_start_button.setToolTip(
            "Interval start is already set. Finish with End/D or cancel with Q."
        )
        self._set_feedback_state(self.set_end_button, "finish-ready")
        self.set_end_button.setToolTip("Finish the active interval (D)")
        self.cancel_interval_button.setVisible(not self.video_only_mode)

    @staticmethod
    def _set_feedback_state(widget: QWidget, state: str) -> None:
        widget.setProperty("feedbackState", state)
        widget.style().unpolish(widget)
        widget.style().polish(widget)
        widget.update()

    def begin_slider_drag(self) -> None:
        self.is_slider_dragging = True

    def finish_slider_drag(self) -> float:
        self.is_slider_dragging = False
        return self.timeline_slider.value() / 1000.0

    def preview_slider_position(self, value: int) -> None:
        self.timeline_current_label.setText(seconds_to_hhmmss(value / 1000.0))
        self.annotation_timeline.track.position = value / 1000.0
        self.annotation_timeline.track.update()

    def update_timeline(self, current_seconds: float, duration_seconds: Optional[float]) -> None:
        shown_seconds = self.timeline_slider.value() / 1000.0 if self.is_slider_dragging else current_seconds
        self.annotation_timeline.update_position(shown_seconds, duration_seconds)
        if hasattr(self.video_player, "update_fullscreen_hud_timeline"):
            self.video_player.update_fullscreen_hud_timeline(
                current_seconds,
                duration_seconds,
            )
        if duration_seconds is None:
            self.timeline_slider.setRange(0, 0)
            self.timeline_current_label.setText(seconds_to_hhmmss(current_seconds))
            self.timeline_duration_label.setText("00:00:00.000")
            return
        max_value = int(duration_seconds * 1000)
        if self.timeline_slider.maximum() != max_value:
            self.timeline_slider.setRange(0, max_value)
            self.timeline_duration_label.setText(seconds_to_hhmmss(duration_seconds))
        if not self.is_slider_dragging:
            self.timeline_slider.setValue(int(current_seconds * 1000))
            self.timeline_current_label.setText(seconds_to_hhmmss(current_seconds))

    def show_fullscreen_notification(
        self,
        text: str,
        level: str = "info",
        persistent: bool = False,
    ) -> None:
        if hasattr(self.video_player, "show_fullscreen_notification"):
            self.video_player.show_fullscreen_notification(text, level, persistent)

    def notify_fullscreen_user_activity(self) -> None:
        if hasattr(self.video_player, "notify_fullscreen_user_activity"):
            self.video_player.notify_fullscreen_user_activity()

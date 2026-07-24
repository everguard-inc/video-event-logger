from typing import Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QButtonGroup,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QSlider,
    QVBoxLayout,
    QWidget,
)

from video_event_logger.services.time_utils import seconds_to_hhmmss
from video_event_logger.ui.video_player import VideoPlayer


class PlayerPanel(QWidget):
    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.is_slider_dragging = False
        self.video_player = VideoPlayer(self)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self.video_player, 1)

        timeline_layout = QHBoxLayout()
        timeline_layout.setContentsMargins(0, 0, 0, 0)
        timeline_layout.setSpacing(6)
        self.timeline_current_label = QLabel("00:00:00.000")
        self.timeline_current_label.setMinimumWidth(92)
        self.timeline_duration_label = QLabel("00:00:00.000")
        self.timeline_duration_label.setMinimumWidth(92)
        self.timeline_slider = QSlider(Qt.Orientation.Horizontal)
        self.timeline_slider.setRange(0, 0)
        self.timeline_slider.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        timeline_layout.addWidget(self.timeline_current_label)
        timeline_layout.addWidget(self.timeline_slider, 1)
        timeline_layout.addWidget(self.timeline_duration_label)
        self.interval_state_label = QLabel("Interval: ready")
        self.interval_state_label.setObjectName("intervalStateLabel")
        self.interval_state_label.setMinimumWidth(250)
        self.interval_state_label.setAlignment(
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
        )
        timeline_layout.addWidget(self.interval_state_label)
        layout.addLayout(timeline_layout)

        controls = QHBoxLayout()
        controls.setContentsMargins(0, 0, 0, 0)
        controls.setSpacing(4)
        self.play_pause_button = QPushButton("Play/Pause")
        self.seek_back_10_button = QPushButton("-10s")
        self.seek_back_button = QPushButton("-1s")
        self.seek_forward_button = QPushButton("+1s")
        self.seek_forward_10_button = QPushButton("+10s")
        self.frame_back_button = QPushButton("Frame -")
        self.frame_forward_button = QPushButton("Frame +")
        self.speed_1_button = QPushButton("x1")
        self.speed_2_button = QPushButton("x2")
        self.speed_4_button = QPushButton("x4")
        self.speed_8_button = QPushButton("x8")
        self.set_start_button = QPushButton("Start")
        self.set_end_button = QPushButton("End")
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
        for button in self.control_buttons:
            button.setMaximumHeight(26)
            button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            controls.addWidget(button)
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
        layout.addLayout(controls)
        self.video_chrome_widgets = [
            self.timeline_current_label,
            self.timeline_slider,
            self.timeline_duration_label,
            self.interval_state_label,
            *self.control_buttons,
        ]
        self.set_pending_interval_start(None)

        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setMinimumHeight(180)

    def set_video_loaded(self, loaded: bool) -> None:
        for button in self.control_buttons:
            button.setEnabled(loaded)
        self.timeline_slider.setEnabled(loaded)

    def set_video_only_mode(self, enabled: bool) -> None:
        for widget in self.video_chrome_widgets:
            widget.setVisible(not enabled)
        if hasattr(self.video_player, "set_fullscreen_hud_active"):
            self.video_player.set_fullscreen_hud_active(enabled)

    def set_active_speed(self, speed: float) -> None:
        for button_speed, button in self.speed_buttons.items():
            button.setChecked(button_speed == speed)
        if hasattr(self.video_player, "set_fullscreen_hud_speed"):
            self.video_player.set_fullscreen_hud_speed(speed)

    def set_playback_active(self, active: bool) -> None:
        self.play_pause_button.setChecked(active)
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
            self.set_start_button.setToolTip("Set interval start")
            self._set_feedback_state(self.set_end_button, "idle")
            self.set_end_button.setToolTip("Set interval end")
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
        self.set_end_button.setToolTip("Finish the active interval")

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

    def update_timeline(self, current_seconds: float, duration_seconds: Optional[float]) -> None:
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

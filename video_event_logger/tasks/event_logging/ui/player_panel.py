from typing import Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
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
        self.timeline_speed_label = QLabel("x1")
        self.timeline_speed_label.setMinimumWidth(26)
        self.timeline_rotation_label = QLabel("0deg")
        self.timeline_rotation_label.setMinimumWidth(34)
        self.timeline_slider = QSlider(Qt.Orientation.Horizontal)
        self.timeline_slider.setRange(0, 0)
        self.timeline_slider.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        timeline_layout.addWidget(self.timeline_current_label)
        timeline_layout.addWidget(self.timeline_slider, 1)
        timeline_layout.addWidget(self.timeline_duration_label)
        timeline_layout.addWidget(self.timeline_speed_label)
        layout.addLayout(timeline_layout)

        rotation_layout = QHBoxLayout()
        rotation_layout.setContentsMargins(0, 0, 0, 0)
        rotation_layout.setSpacing(4)
        self.rotate_button = QPushButton("Rotate 90")
        self.rotate_button.setMaximumHeight(26)
        self.rotate_button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.interval_state_label = QLabel("Interval: ready")
        self.interval_state_label.setMinimumWidth(250)
        self.interval_state_label.setAlignment(
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
        )
        rotation_layout.addWidget(QLabel("Rotation"))
        rotation_layout.addWidget(self.timeline_rotation_label)
        rotation_layout.addWidget(self.rotate_button)
        rotation_layout.addStretch(1)
        rotation_layout.addWidget(self.interval_state_label)
        layout.addLayout(rotation_layout)

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
        layout.addLayout(controls)
        self.set_pending_interval_start(None)

        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setMinimumHeight(180)

    def set_video_loaded(self, loaded: bool) -> None:
        for button in self.control_buttons:
            button.setEnabled(loaded)
        self.timeline_slider.setEnabled(loaded)
        self.rotate_button.setEnabled(loaded)

    def set_rotation_enabled(self, enabled: bool) -> None:
        self.rotate_button.setEnabled(enabled)

    def set_speed_label(self, speed: float) -> None:
        self.timeline_speed_label.setText("x%s" % int(speed))

    def set_rotation_label(self, degrees: int) -> None:
        self.timeline_rotation_label.setText("%ddeg" % degrees)

    def set_pending_interval_start(self, start_seconds: Optional[float]) -> None:
        if start_seconds is None:
            self.interval_state_label.setText("Interval: ready")
            self.interval_state_label.setStyleSheet("color: #666;")
            self.interval_state_label.setToolTip("Press Start or A to begin an interval.")
            self.set_start_button.setText("Start")
            self.set_start_button.setStyleSheet("")
            self.set_start_button.setToolTip("Set interval start")
            self.set_end_button.setStyleSheet("")
            self.set_end_button.setToolTip("Set interval end")
            return

        formatted_start = seconds_to_hhmmss(start_seconds)
        self.interval_state_label.setText("INTERVAL ACTIVE — start %s" % formatted_start)
        self.interval_state_label.setStyleSheet(
            "color: #8a5a00; background: #fff3cd; border: 1px solid #d6a800; "
            "border-radius: 3px; padding: 2px 6px; font-weight: 600;"
        )
        self.interval_state_label.setToolTip(
            "Interval start is set to %s. Press End or D to finish." % formatted_start
        )
        self.set_start_button.setText("Start set")
        self.set_start_button.setStyleSheet(
            "QPushButton { background: #fff3cd; color: #5f4300; "
            "border: 1px solid #d6a800; font-weight: 600; }"
        )
        self.set_start_button.setToolTip("Replace the current interval start")
        self.set_end_button.setStyleSheet(
            "QPushButton { background: #e4f4e9; color: #145c2e; "
            "border: 1px solid #62a978; font-weight: 600; }"
        )
        self.set_end_button.setToolTip("Finish the active interval")

    def begin_slider_drag(self) -> None:
        self.is_slider_dragging = True

    def finish_slider_drag(self) -> float:
        self.is_slider_dragging = False
        return self.timeline_slider.value() / 1000.0

    def preview_slider_position(self, value: int) -> None:
        self.timeline_current_label.setText(seconds_to_hhmmss(value / 1000.0))

    def update_timeline(self, current_seconds: float, duration_seconds: Optional[float]) -> None:
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

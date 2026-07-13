from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QCheckBox,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QProgressBar,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
)

from video_event_logger.app_config import DEFAULT_EVENT_TYPE


class MetadataPanel(QFrame):
    def __init__(self) -> None:
        super().__init__()
        self.setFrameShape(QFrame.Shape.StyledPanel)
        self.setMaximumHeight(96)
        self.setMinimumHeight(96)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 6, 8, 6)
        layout.setSpacing(10)

        action_layout = QVBoxLayout()
        action_layout.setContentsMargins(0, 0, 0, 0)
        action_layout.setSpacing(4)
        self.open_button = QPushButton("Open Video")
        self.show_popup_checkbox = QCheckBox("Show popup after each interval")
        self.show_popup_checkbox.setChecked(True)
        action_layout.addWidget(self.open_button)
        action_layout.addWidget(self.show_popup_checkbox)
        action_layout.addStretch(1)

        divider = QFrame()
        divider.setFrameShape(QFrame.Shape.VLine)
        divider.setFrameShadow(QFrame.Shadow.Sunken)

        metadata_layout = QGridLayout()
        metadata_layout.setContentsMargins(0, 0, 0, 0)
        metadata_layout.setVerticalSpacing(3)
        metadata_layout.setHorizontalSpacing(4)

        self.save_status_lamp = QLabel()
        self.save_status_lamp.setFixedSize(12, 12)
        self.status_label = QLabel("")
        self.status_label.setMaximumHeight(20)
        self.status_label.setVisible(False)
        self.video_name_label = QLabel("N/A")
        self.autosave_indicator = QProgressBar()
        self.autosave_indicator.setRange(0, 0)
        self.autosave_indicator.setMaximumWidth(90)
        self.autosave_indicator.setMaximumHeight(8)
        self.autosave_indicator.setVisible(False)
        self.event_type_input = QLineEdit(DEFAULT_EVENT_TYPE)
        self.event_type_input.setMaxLength(25)
        self.event_type_input.setFixedWidth(190)
        self.event_type_input.setFocusPolicy(Qt.FocusPolicy.ClickFocus)
        self.event_type_input.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        self.event_type_lamp = QLabel()
        self.event_type_lamp.setFixedSize(12, 12)

        metadata_layout.addWidget(QLabel("status"), 0, 0)
        metadata_layout.addWidget(self.save_status_lamp, 0, 1)
        metadata_layout.addWidget(self.autosave_indicator, 0, 2)
        metadata_layout.addWidget(QLabel("video"), 1, 0)
        metadata_layout.addWidget(self.video_name_label, 1, 1, 1, 4)
        metadata_layout.addWidget(QLabel("event_type"), 2, 0)
        metadata_layout.addWidget(self.event_type_input, 2, 1)
        metadata_layout.addWidget(self.event_type_lamp, 2, 2)
        metadata_layout.setColumnStretch(4, 1)

        layout.addLayout(action_layout)
        layout.addWidget(divider)
        layout.addLayout(metadata_layout, 1)

    def show_popup_after_interval(self) -> bool:
        return self.show_popup_checkbox.isChecked()

    def set_video_name(self, video_name: str) -> None:
        self.video_name_label.setText(video_name or "N/A")

    def set_event_type(self, event_type: str) -> None:
        self.event_type_input.setText((event_type or DEFAULT_EVENT_TYPE)[:25])

    def event_type_text(self) -> str:
        return self.event_type_input.text()

    def clear_event_type_focus(self) -> None:
        self.event_type_input.clearFocus()

    def set_event_type_lamp(self, state: str) -> None:
        if state == "pending":
            color = "#d6a800"
            tooltip = "event_type pending"
        else:
            color = "#1c9c4a"
            tooltip = "event_type active"
        self.event_type_lamp.setStyleSheet("border-radius: 6px; background: %s;" % color)
        self.event_type_lamp.setToolTip(tooltip)

    def set_save_status(self, status: str) -> None:
        color = "#c62828" if status == "not_saved" else "#1c9c4a"
        self.save_status_lamp.setStyleSheet("border-radius: 6px; background: %s;" % color)
        self.save_status_lamp.setToolTip(status)

    def set_status_text(self, text: str) -> None:
        self.status_label.setText(text)

    def show_autosave_indicator(self) -> None:
        self.autosave_indicator.setVisible(True)
        QTimer.singleShot(650, lambda: self.autosave_indicator.setVisible(False))

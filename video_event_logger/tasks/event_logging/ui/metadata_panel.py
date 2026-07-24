from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QSizePolicy,
)

from video_event_logger.app_config import DEFAULT_EVENT_TYPE


class MetadataPanel(QFrame):
    def __init__(self) -> None:
        super().__init__()
        self.setFrameShape(QFrame.Shape.StyledPanel)
        self.setMaximumHeight(40)
        self.setMinimumHeight(40)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 6, 8, 6)
        layout.setSpacing(6)

        self.video_name_label = QLabel("N/A")
        self.event_type_input = QLineEdit(DEFAULT_EVENT_TYPE)
        self.event_type_input.setMaxLength(25)
        self.event_type_input.setFixedWidth(190)
        self.event_type_input.setFocusPolicy(Qt.FocusPolicy.ClickFocus)
        self.event_type_input.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        self.event_type_lamp = QLabel()
        self.event_type_lamp.setFixedSize(12, 12)

        layout.addWidget(QLabel("video"))
        layout.addWidget(self.video_name_label, 1)
        layout.addWidget(QLabel("event_type"))
        layout.addWidget(self.event_type_input)
        layout.addWidget(self.event_type_lamp)

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

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
)

from video_event_logger.app_config import DEFAULT_EVENT_TYPE


class MetadataPanel(QFrame):
    """Header bar: current video, its position, connection settings and Submit.

    The event_type field belongs here for the controller, but the workspace
    places it in the mark bar next to Start / End where it is used.
    """

    def __init__(self) -> None:
        super().__init__()
        self.setObjectName("headerBar")
        self.setFixedHeight(58)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(16, 6, 12, 6)
        layout.setSpacing(12)

        titles = QVBoxLayout()
        titles.setSpacing(0)
        self.video_name_label = QLabel("No video loaded")
        self.video_name_label.setObjectName("videoTitle")
        self.video_name_label.setTextFormat(Qt.TextFormat.PlainText)
        self.video_name_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.video_name_label.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        self.video_subtitle_label = QLabel("Add videos from the playlist or File → Open Videos…")
        self.video_subtitle_label.setObjectName("videoSubtitle")
        self.video_subtitle_label.setTextFormat(Qt.TextFormat.PlainText)
        titles.addWidget(self.video_name_label)
        titles.addWidget(self.video_subtitle_label)
        layout.addLayout(titles, 1)

        self.settings_button = QPushButton("Connection…")
        self.settings_button.setToolTip("Upload endpoint and your access token")
        self.settings_button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        layout.addWidget(self.settings_button)
        self.submit_button = QPushButton("Submit…   Ctrl+↵")
        self.submit_button.setObjectName("submitButton")
        self.submit_button.setToolTip("Review and upload this video's annotations (Ctrl/Cmd+Enter)")
        self.submit_button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.submit_button.setEnabled(False)
        layout.addWidget(self.submit_button)

        self.event_type_input = QLineEdit(DEFAULT_EVENT_TYPE)
        self.event_type_input.setMaxLength(25)
        self.event_type_input.setFixedWidth(170)
        self.event_type_input.setPlaceholderText(DEFAULT_EVENT_TYPE)
        self.event_type_input.setToolTip("event_type for new intervals (Enter to apply)")
        self.event_type_input.setFocusPolicy(Qt.FocusPolicy.ClickFocus)
        self.event_type_input.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        self.event_type_lamp = QLabel()
        self.event_type_lamp.setFixedSize(10, 10)

    def set_video_name(self, video_name: str) -> None:
        self.video_name_label.setText(video_name or "No video loaded")
        self.video_name_label.setToolTip(video_name or "")

    def set_video_subtitle(self, text: str) -> None:
        self.video_subtitle_label.setText(text)

    def set_event_type(self, event_type: str) -> None:
        self.event_type_input.setText((event_type or DEFAULT_EVENT_TYPE)[:25])

    def event_type_text(self) -> str:
        return self.event_type_input.text()

    def clear_event_type_focus(self) -> None:
        self.event_type_input.clearFocus()

    def set_event_type_lamp(self, state: str) -> None:
        if state == "pending":
            color = "#d6a800"
            tooltip = "event_type not applied yet — press Enter"
        else:
            color = "#3fb06e"
            tooltip = "event_type active"
        self.event_type_lamp.setStyleSheet("border-radius: 5px; background: %s;" % color)
        self.event_type_lamp.setToolTip(tooltip)

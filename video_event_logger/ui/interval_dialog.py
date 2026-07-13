from typing import Optional, Tuple

from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QLabel,
    QLineEdit,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from video_event_logger.app_config import DEFAULT_EVENT_TYPE
from video_event_logger.services.time_utils import seconds_to_hhmmss


class IntervalDialog(QDialog):
    def __init__(
        self,
        start_seconds: float,
        end_seconds: float,
        event_type: str,
        parent: Optional[QWidget] = None,
        comment: str = "",
        title: str = "Save interval",
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle(title)
        self.event_type_input = QLineEdit(event_type.strip() or DEFAULT_EVENT_TYPE)
        self.event_type_input.setMaxLength(25)
        self.comment_input = QTextEdit()
        self.comment_input.setFixedHeight(80)
        self.comment_input.setPlainText(comment)

        form = QFormLayout()
        form.addRow("Start", QLabel(seconds_to_hhmmss(start_seconds)))
        form.addRow("End", QLabel(seconds_to_hhmmss(end_seconds)))
        form.addRow("event_type", self.event_type_input)
        form.addRow("comment", self.comment_input)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(buttons)

    def values(self) -> Tuple[str, str]:
        event_type = self.event_type_input.text().strip() or DEFAULT_EVENT_TYPE
        comment = self.comment_input.toPlainText().strip()
        return event_type, comment

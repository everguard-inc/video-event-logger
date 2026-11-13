from typing import Optional, Tuple

from PySide6.QtWidgets import (
    QDialog,
    QDoubleSpinBox,
    QMessageBox,
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
    # exec() result when the user throws the new interval away.
    DISCARD = 2

    def __init__(
        self,
        start_seconds: float,
        end_seconds: float,
        event_type: str,
        parent: Optional[QWidget] = None,
        comment: str = "",
        title: str = "Save interval",
        editable_times: bool = False,
        duration_seconds: Optional[float] = None,
        keep_recording_option: bool = False,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle(title)
        self.event_type_input = QLineEdit(event_type.strip() or DEFAULT_EVENT_TYPE)
        self.event_type_input.setMaxLength(25)
        self.comment_input = QTextEdit()
        self.comment_input.setFixedHeight(80)
        self.comment_input.setPlainText(comment)

        form = QFormLayout()
        self.start_input = QDoubleSpinBox()
        self.end_input = QDoubleSpinBox()
        for field, value in ((self.start_input, start_seconds), (self.end_input, end_seconds)):
            field.setDecimals(3)
            field.setRange(0, duration_seconds if duration_seconds is not None else 1e9)
            field.setSingleStep(0.001)
            field.setSuffix(" s")
            field.setValue(value)
        self.editable_times = editable_times
        form.addRow("Start", self.start_input if editable_times else QLabel(seconds_to_hhmmss(start_seconds)))
        form.addRow("End", self.end_input if editable_times else QLabel(seconds_to_hhmmss(end_seconds)))
        form.addRow("event_type", self.event_type_input)
        form.addRow("comment", self.comment_input)

        layout = QVBoxLayout(self)
        layout.addLayout(form)
        if keep_recording_option:
            # Shown right after End: Esc must not throw the interval away.
            buttons = QDialogButtonBox()
            self.discard_button = buttons.addButton(
                "Discard interval", QDialogButtonBox.ButtonRole.DestructiveRole
            )
            self.discard_button.setObjectName("dangerButton")
            self.discard_button.clicked.connect(lambda: self.done(self.DISCARD))
            self.keep_recording_button = buttons.addButton(
                "Keep recording", QDialogButtonBox.ButtonRole.RejectRole
            )
            self.keep_recording_button.setToolTip(
                "Pressed End too early? Return to the active interval with the same start (Esc)."
            )
            self.save_button = buttons.addButton(QDialogButtonBox.StandardButton.Save)
            self.save_button.setDefault(True)
            hint = QLabel(
                "Pressed End too early? Keep recording (Esc) returns to the active "
                "interval with the same start."
            )
            hint.setObjectName("dialogHint")
            hint.setWordWrap(True)
            layout.addWidget(hint)
        else:
            buttons = QDialogButtonBox(
                QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel
            )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def values(self) -> Tuple[str, str]:
        event_type = self.event_type_input.text().strip() or DEFAULT_EVENT_TYPE
        comment = self.comment_input.toPlainText().strip()
        return event_type, comment

    def time_values(self) -> Tuple[float, float]:
        return self.start_input.value(), self.end_input.value()

    def accept(self) -> None:
        if self.editable_times and self.start_input.value() >= self.end_input.value():
            QMessageBox.warning(self, "Invalid interval", "Start must be before End.")
            return
        super().accept()

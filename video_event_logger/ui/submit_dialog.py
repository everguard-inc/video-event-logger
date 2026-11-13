"""Submit flow: review → uploading → result, in one modal dialog."""
from typing import Dict, List, Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QPushButton,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from video_event_logger.app_config import DEFAULT_EVENT_TYPE
from video_event_logger.models.interval import Interval
from video_event_logger.services.annotation_api import UploadOutcome
from video_event_logger.ui.event_colors import event_type_color

TONE_GLYPHS = {"success": "✓", "attention": "!", "error": "×", "canceled": "–"}


def format_work_time(seconds: float) -> str:
    total = int(max(0.0, seconds))
    hours, rest = divmod(total, 3600)
    minutes, secs = divmod(rest, 60)
    if hours:
        return "%d:%02d:%02d" % (hours, minutes, secs)
    return "%02d:%02d" % (minutes, secs)


def _label(text: str = "", object_name: str = "", wrap: bool = False) -> QLabel:
    label = QLabel(text)
    label.setTextFormat(Qt.TextFormat.PlainText)
    if object_name:
        label.setObjectName(object_name)
    label.setWordWrap(wrap)
    return label


def _repolish(widget: QWidget) -> None:
    widget.style().unpolish(widget)
    widget.style().polish(widget)


class SubmitDialog(QDialog):
    submit_requested = Signal()
    cancel_upload_requested = Signal()
    settings_requested = Signal()
    next_video_requested = Signal()

    def __init__(
        self,
        video_name: str,
        intervals: List[Interval],
        active_work_seconds: float,
        has_next_video: bool = False,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("submitDialog")
        self.setWindowTitle("Submit annotations")
        self.setModal(True)
        self.setMinimumWidth(560)
        self.intervals = list(intervals)
        self.has_next_video = has_next_video
        self.sending = False
        self.outcome = None  # type: Optional[UploadOutcome]

        self.pages = QStackedWidget()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.pages)
        self.review_page = self._build_review_page(video_name, active_work_seconds)
        self.sending_page = self._build_sending_page()
        self.result_page = self._build_result_page()
        for page in (self.review_page, self.sending_page, self.result_page):
            self.pages.addWidget(page)
        self.show_review()

    # Review -------------------------------------------------------------

    def _build_review_page(self, video_name: str, work_seconds: float) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(24, 22, 24, 18)
        layout.setSpacing(14)
        layout.addWidget(_label("Submit annotations", "dialogTitle"))
        name = _label(video_name, "dialogSubtitle")
        name.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        layout.addWidget(name)

        count = len(self.intervals)
        if count:
            tiles = QGridLayout()
            tiles.setSpacing(10)
            marked = sum(i.end_time_seconds - i.start_time_seconds for i in self.intervals)
            for column, (caption, value) in enumerate((
                ("Intervals", str(count)),
                ("Marked time", "%.1f s" % marked),
                ("Work time", format_work_time(work_seconds)),
            )):
                tile = QFrame()
                tile.setObjectName("statTile")
                tile_layout = QVBoxLayout(tile)
                tile_layout.setContentsMargins(12, 10, 12, 10)
                tile_layout.addWidget(_label(caption, "statCaption"))
                tile_layout.addWidget(_label(value, "statValue"))
                tiles.addWidget(tile, 0, column)
            layout.addLayout(tiles)

            chips = QHBoxLayout()
            chips.setSpacing(6)
            for event_type, number in sorted(self._counts().items()):
                chip = _label("●  %s  %d" % (event_type, number), "typeChip")
                chip.setStyleSheet("QLabel#typeChip { color: %s; }" % event_type_color(event_type))
                chip.setToolTip(event_type)
                chips.addWidget(chip)
            chips.addStretch()
            layout.addLayout(chips)

            undefined = [n for n, i in enumerate(self.intervals, 1) if i.event_type.strip() in ("", DEFAULT_EVENT_TYPE)]
            if undefined:
                numbers = ", ".join("#%d" % n for n in undefined[:6]) + ("…" if len(undefined) > 6 else "")
                warning = _label(
                    "Interval %s still %s event_type “%s”. You can submit anyway or go back and set it."
                    % (numbers, "has" if len(undefined) == 1 else "have", DEFAULT_EVENT_TYPE),
                    "warningBox", wrap=True,
                )
                layout.addWidget(warning)
            self.confirm_empty = None
        else:
            empty = QFrame()
            empty.setObjectName("noEventsBox")
            empty_layout = QVBoxLayout(empty)
            empty_layout.setContentsMargins(16, 14, 16, 14)
            empty_layout.addWidget(_label("No events in this video", "noEventsTitle"))
            empty_layout.addWidget(_label(
                "The server will mark this batch group as reviewed, nothing found. No clips are made.",
                "noEventsText", wrap=True,
            ))
            layout.addWidget(empty)
            self.confirm_empty = QCheckBox("I watched the whole video and found no events")
            self.confirm_empty.toggled.connect(self._update_submit_enabled)
            layout.addWidget(self.confirm_empty)

        layout.addStretch()
        footer = QHBoxLayout()
        footer.addWidget(_label("Saved locally first · server from Connection settings", "dialogHint"))
        footer.addStretch()
        self.back_button = QPushButton("Back")
        self.back_button.clicked.connect(self.reject)
        self.submit_button = QPushButton(
            "Submit %d interval%s" % (count, "" if count == 1 else "s") if count
            else "Submit as “No events”"
        )
        self.submit_button.setObjectName("primaryButton")
        self.submit_button.clicked.connect(self._submit)
        footer.addWidget(self.back_button)
        footer.addWidget(self.submit_button)
        layout.addLayout(footer)
        return page

    def _counts(self) -> Dict[str, int]:
        counts = {}  # type: Dict[str, int]
        for interval in self.intervals:
            counts[interval.event_type] = counts.get(interval.event_type, 0) + 1
        return counts

    def _update_submit_enabled(self) -> None:
        self.submit_button.setEnabled(self.confirm_empty is None or self.confirm_empty.isChecked())

    def _submit(self) -> None:
        if self.submit_button.isEnabled():
            self.submit_requested.emit()

    # Sending ------------------------------------------------------------

    def _build_sending_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(24, 36, 24, 28)
        layout.setSpacing(12)
        layout.addWidget(_label("Uploading annotations…", "dialogTitle"), 0, Qt.AlignmentFlag.AlignHCenter)
        layout.addWidget(_label("Up to 30 s. You can cancel; nothing is lost.", "dialogHint"), 0, Qt.AlignmentFlag.AlignHCenter)
        bar = QProgressBar()
        bar.setRange(0, 0)
        bar.setTextVisible(False)
        bar.setFixedHeight(6)
        layout.addWidget(bar)
        self.cancel_upload_button = QPushButton("Cancel")
        self.cancel_upload_button.clicked.connect(self.cancel_upload_requested.emit)
        layout.addWidget(self.cancel_upload_button, 0, Qt.AlignmentFlag.AlignHCenter)
        return page

    # Result -------------------------------------------------------------

    def _build_result_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(24, 22, 24, 18)
        layout.setSpacing(10)
        head = QHBoxLayout()
        head.setSpacing(16)
        self.result_icon = _label("", "resultIcon")
        self.result_icon.setFixedSize(44, 44)
        self.result_icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        head.addWidget(self.result_icon, 0, Qt.AlignmentFlag.AlignTop)
        texts = QVBoxLayout()
        texts.setSpacing(6)
        self.result_title = _label("", "dialogTitle", wrap=True)
        self.result_lead = _label("", "resultLead", wrap=True)
        texts.addWidget(self.result_title)
        texts.addWidget(self.result_lead)
        head.addLayout(texts, 1)
        layout.addLayout(head)
        self.result_message_caption = _label("Server message", "dialogHint")
        self.result_message = _label("", "messageBox", wrap=True)
        self.result_message.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.result_footer = _label("", "dialogHint")
        for widget in (self.result_message_caption, self.result_message, self.result_footer):
            layout.addWidget(widget)
        layout.addStretch()
        buttons = QHBoxLayout()
        buttons.addStretch()
        self.result_secondary = QPushButton()
        self.result_secondary.clicked.connect(self.accept)
        self.result_primary = QPushButton()
        self.result_primary.setObjectName("primaryButton")
        self.result_primary.clicked.connect(self._result_primary_clicked)
        buttons.addWidget(self.result_secondary)
        buttons.addWidget(self.result_primary)
        layout.addLayout(buttons)
        return page

    def show_review(self) -> None:
        self.sending = False
        self.pages.setCurrentWidget(self.review_page)
        self._update_submit_enabled()
        self.submit_button.setDefault(True)
        self.submit_button.setFocus()

    def show_sending(self) -> None:
        self.sending = True
        self.pages.setCurrentWidget(self.sending_page)
        self.cancel_upload_button.setFocus()

    def show_result(self, outcome: UploadOutcome) -> None:
        self.sending = False
        self.outcome = outcome
        self.result_icon.setText(TONE_GLYPHS.get(outcome.tone, ""))
        self.result_icon.setProperty("tone", outcome.tone)
        _repolish(self.result_icon)
        self.result_title.setText(outcome.title)
        self.result_lead.setText(outcome.lead)
        self.result_message_caption.setText("Server message" if outcome.tone != "error" else "Details from the server")
        self.result_message_caption.setVisible(bool(outcome.message))
        self.result_message.setText(outcome.message)
        self.result_message.setVisible(bool(outcome.message))
        self.result_footer.setText(outcome.footer)
        self.result_footer.setVisible(bool(outcome.footer))
        primary, secondary = {
            "next": ("Open next video" if self.has_next_video else "Done", "Stay here" if self.has_next_video else ""),
            "back": ("Back to editing", ""),
            "settings": ("Open connection settings", "Close"),
            "retry": ("Retry", "Close"),
            "close": ("Close", ""),
        }.get(outcome.primary, ("Close", ""))
        self.result_primary.setText(primary)
        self.result_secondary.setText(secondary)
        self.result_secondary.setVisible(bool(secondary))
        self.pages.setCurrentWidget(self.result_page)
        self.result_primary.setDefault(True)
        self.result_primary.setFocus()

    def _result_primary_clicked(self) -> None:
        action = self.outcome.primary if self.outcome else "close"
        if action == "retry":
            self.submit_requested.emit()
            return
        if action == "settings":
            self.accept()
            self.settings_requested.emit()
            return
        if action == "next" and self.has_next_video:
            self.accept()
            self.next_video_requested.emit()
            return
        self.accept()

    def reject(self) -> None:
        # Esc while uploading cancels the request instead of hiding it.
        if self.sending:
            self.cancel_upload_requested.emit()
            return
        super().reject()

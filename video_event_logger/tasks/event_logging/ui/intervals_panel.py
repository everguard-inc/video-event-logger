from typing import Callable, Dict, List, Optional

from PySide6.QtCore import QLocale, Qt, Signal
from PySide6.QtGui import QColor, QIcon, QPainter, QPixmap
from PySide6.QtWidgets import (
    QAbstractItemView,
    QDoubleSpinBox,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QPushButton,
    QSizePolicy,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from video_event_logger.models.interval import Interval
from video_event_logger.services.time_utils import seconds_to_hhmmss
from video_event_logger.ui.event_colors import event_type_qcolor


def color_dot(color: QColor, size: int = 10) -> QIcon:
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(color)
    painter.drawEllipse(0, 0, size, size)
    painter.end()
    return QIcon(pixmap)


class IntervalDetailsPanel(QFrame):
    """Exact editing of the selected interval without a modal dialog."""

    applied = Signal(int, float, float, str, str)
    delete_requested = Signal(int)

    def __init__(self) -> None:
        super().__init__()
        self.setObjectName("detailsCard")
        self.row = -1
        self.playhead_provider = None  # type: Optional[Callable[[], float]]
        self.frame_provider = None  # type: Optional[Callable[[], float]]
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(6)
        head = QHBoxLayout()
        self.title_label = QLabel("Select an interval")
        self.title_label.setStyleSheet("font-weight: 600;")
        head.addWidget(self.title_label)
        head.addStretch()
        self.hint_label = QLabel("or drag its edges")
        self.hint_label.setObjectName("dialogHint")
        head.addWidget(self.hint_label)
        layout.addLayout(head)

        grid = QGridLayout()
        grid.setHorizontalSpacing(6)
        grid.setVerticalSpacing(4)
        self.start_input = self._seconds_box()
        self.end_input = self._seconds_box()
        for row, (caption, box) in enumerate((("Start", self.start_input), ("End", self.end_input))):
            label = QLabel(caption)
            label.setObjectName("sectionCaption")
            minus = self._small_button("−", "One frame earlier", lambda checked=False, b=box: self._nudge(b, -1))
            plus = self._small_button("+", "One frame later", lambda checked=False, b=box: self._nudge(b, 1))
            here = self._small_button("⌖ Now", "Set to the current video position (playhead)",
                                      lambda checked=False, b=box: self._from_playhead(b))
            grid.addWidget(label, row, 0)
            grid.addWidget(minus, row, 1)
            grid.addWidget(box, row, 2)
            grid.addWidget(plus, row, 3)
            grid.addWidget(here, row, 4)
        grid.setColumnStretch(2, 1)
        layout.addLayout(grid)

        self.type_input = QLineEdit()
        self.type_input.setMaxLength(25)
        self.type_input.setPlaceholderText("event_type")
        self.comment_input = QLineEdit()
        self.comment_input.setPlaceholderText("comment")
        layout.addWidget(self.type_input)
        layout.addWidget(self.comment_input)
        self.error_label = QLabel("")
        self.error_label.setObjectName("warningBox")
        self.error_label.setWordWrap(True)
        self.error_label.hide()
        layout.addWidget(self.error_label)
        buttons = QHBoxLayout()
        self.delete_button = QPushButton("Delete")
        self.delete_button.setObjectName("dangerButton")
        self.delete_button.clicked.connect(lambda: self.delete_requested.emit(self.row))
        self.apply_button = QPushButton("Apply")
        self.apply_button.setObjectName("primaryButton")
        self.apply_button.clicked.connect(self._apply)
        buttons.addWidget(self.delete_button)
        buttons.addStretch()
        buttons.addWidget(self.apply_button)
        layout.addLayout(buttons)
        for field in (self.type_input, self.comment_input):
            field.returnPressed.connect(self._apply)
        self.start_input.valueChanged.connect(self._validate)
        self.end_input.valueChanged.connect(self._validate)
        self.show_interval(-1, None)

    def _seconds_box(self) -> QDoubleSpinBox:
        box = QDoubleSpinBox()
        box.setDecimals(3)
        box.setRange(0, 1e9)
        box.setSingleStep(0.001)
        box.setSuffix(" s")
        box.setAlignment(Qt.AlignmentFlag.AlignRight)
        box.setKeyboardTracking(False)
        box.setLocale(QLocale.c())  # always 12.345, never 12,345
        box.setButtonSymbols(QDoubleSpinBox.ButtonSymbols.NoButtons)
        return box

    @staticmethod
    def _small_button(text, tip, handler):  # type: ignore[no-untyped-def]
        button = QPushButton(text)
        button.setToolTip(tip)
        button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        button.clicked.connect(handler)
        return button

    def _nudge(self, box: QDoubleSpinBox, frames: int) -> None:
        step = self.frame_provider() if self.frame_provider else 1 / 30.0
        box.setValue(box.value() + frames * step)

    def _from_playhead(self, box: QDoubleSpinBox) -> None:
        if self.playhead_provider is not None:
            box.setValue(self.playhead_provider())

    def _validate(self) -> bool:
        valid = self.start_input.value() < self.end_input.value()
        self.error_label.setText("" if valid else "Start must be before End.")
        self.error_label.setVisible(not valid and self.row >= 0)
        self.apply_button.setEnabled(valid and self.row >= 0)
        return valid

    def _apply(self) -> None:
        if self.row < 0 or not self._validate():
            return
        self.applied.emit(
            self.row, self.start_input.value(), self.end_input.value(),
            self.type_input.text().strip(), self.comment_input.text().strip(),
        )

    def set_duration(self, duration: Optional[float]) -> None:
        maximum = duration if duration else 1e9
        for box in (self.start_input, self.end_input):
            box.setMaximum(maximum)

    def show_interval(self, row: int, interval: Optional[Interval]) -> None:
        self.row = row if interval is not None else -1
        enabled = interval is not None
        for widget in self.findChildren(QWidget):
            if widget is not self.title_label:
                widget.setEnabled(enabled)
        if interval is None:
            self.title_label.setText("Select an interval to edit it")
            for box in (self.start_input, self.end_input):
                box.blockSignals(True)
                box.setValue(0)
                box.blockSignals(False)
            self.type_input.clear()
            self.comment_input.clear()
            self.error_label.hide()
            return
        self.title_label.setText("Interval #%d · %.1f s" % (row + 1, interval.end_time_seconds - interval.start_time_seconds))
        for box, value in ((self.start_input, interval.start_time_seconds), (self.end_input, interval.end_time_seconds)):
            box.blockSignals(True)
            box.setValue(value)
            box.blockSignals(False)
        self.type_input.setText(interval.event_type)
        self.comment_input.setText(interval.comment)
        self._validate()


class IntervalsPanel(QWidget):
    play_requested = Signal(int)
    edit_requested = Signal(int)
    delete_requested = Signal(int)
    jump_requested = Signal(int)

    def __init__(self) -> None:
        super().__init__()
        self.setMinimumHeight(80)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.intervals = []  # type: List[Interval]

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)

        left = QVBoxLayout()
        left.setSpacing(6)
        head = QHBoxLayout()
        self.event_counts_total_label = QLabel("Intervals")
        self.event_counts_total_label.setStyleSheet("font-weight: 600;")
        self.event_counts_label = QLabel("")
        self.event_counts_label.setTextFormat(Qt.TextFormat.RichText)
        self.event_counts_label.setObjectName("dialogHint")
        head.addWidget(self.event_counts_total_label)
        head.addSpacing(8)
        head.addWidget(self.event_counts_label, 1)
        left.addLayout(head)

        self.interval_table = QTableWidget(0, 6)
        self.interval_table.setHorizontalHeaderLabels(["#", "start", "end", "event_type", "comment", ""])
        self.interval_table.verticalHeader().setVisible(False)
        self.interval_table.setShowGrid(False)
        self.interval_table.setAlternatingRowColors(True)
        self.interval_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.interval_table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.interval_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.interval_table.setSortingEnabled(False)
        self.interval_table.setMinimumHeight(70)
        self.interval_table.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.interval_table.setTextElideMode(Qt.TextElideMode.ElideRight)
        self.interval_table.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.interval_table.doubleClicked.connect(lambda index: self.jump_requested.emit(index.row()))
        self.interval_table.verticalHeader().setDefaultSectionSize(30)
        self._configure_table_columns()
        left.addWidget(self.interval_table, 1)
        self.empty_hint = QLabel(
            "No events marked yet. Press A when an event starts and D when it ends.\n"
            "Watched the whole video and nothing happened? Submit it as “No events”."
        )
        self.empty_hint.setObjectName("emptyHint")
        self.empty_hint.setWordWrap(True)
        left.addWidget(self.empty_hint)
        layout.addLayout(left, 7)

        self.details = IntervalDetailsPanel()
        self.details.setMinimumWidth(300)
        self.details.delete_requested.connect(self.delete_requested.emit)
        layout.addWidget(self.details, 3)
        self.interval_table.itemSelectionChanged.connect(self._selection_changed)
        self.set_empty_hint_visible(False)

    def set_empty_hint_visible(self, visible: bool) -> None:
        self.empty_hint.setVisible(visible)
        self.interval_table.setVisible(not visible)

    def selected_row(self) -> int:
        row = self.interval_table.currentRow()
        if row < 0 and self.interval_table.selectedItems():
            row = self.interval_table.selectedItems()[0].row()
        return row

    def _selection_changed(self) -> None:
        rows = {index.row() for index in self.interval_table.selectionModel().selectedRows()}
        row = min(rows) if rows else -1
        self.details.show_interval(row, self.intervals[row] if 0 <= row < len(self.intervals) else None)

    def refresh_intervals(self, intervals: List[Interval]) -> None:
        selected = self.selected_row()
        self.intervals = list(intervals)
        self.interval_table.setRowCount(0)
        self.interval_table.setRowCount(len(intervals))
        for row, interval in enumerate(intervals):
            number = QTableWidgetItem(str(row + 1))
            number.setForeground(QColor("#7d8696"))
            self.interval_table.setItem(row, 0, number)
            self.interval_table.setItem(row, 1, QTableWidgetItem(interval.start_time_hhmmss))
            self.interval_table.setItem(row, 2, QTableWidgetItem(interval.end_time_hhmmss))
            event_type_item = QTableWidgetItem(interval.event_type)
            event_type_item.setIcon(color_dot(event_type_qcolor(interval.event_type)))
            event_type_item.setToolTip(interval.event_type)
            self.interval_table.setItem(row, 3, event_type_item)
            comment_item = QTableWidgetItem(interval.comment)
            comment_item.setToolTip(interval.comment)
            self.interval_table.setItem(row, 4, comment_item)

            action_widget = QWidget()
            action_widget.setStyleSheet("background: transparent;")
            action_layout = QHBoxLayout(action_widget)
            action_layout.setContentsMargins(2, 0, 2, 0)
            action_layout.setSpacing(2)
            for text, role, tip, signal in (
                ("▶", "play", "Play this interval", self.play_requested),
                ("✎", "edit", "Edit in a dialog", self.edit_requested),
                ("✕", "delete", "Delete (Del)", self.delete_requested),
            ):
                button = QPushButton(text)
                button.setFixedWidth(30)
                button.setToolTip(tip)
                button.setProperty("actionRole", role)
                button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
                button.clicked.connect(lambda checked=False, row_index=row, s=signal: s.emit(row_index))
                action_layout.addWidget(button)
            self.interval_table.setCellWidget(row, 5, action_widget)
        self._configure_table_columns()
        if 0 <= selected < len(intervals):
            self.interval_table.selectRow(selected)
        else:
            self._selection_changed()

    def _configure_table_columns(self) -> None:
        header = self.interval_table.horizontalHeader()
        header.setStretchLastSection(False)
        header.setDefaultAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        for column in (0, 1, 2, 3, 5):
            header.setSectionResizeMode(column, QHeaderView.ResizeMode.Fixed)
        header.setSectionResizeMode(4, QHeaderView.ResizeMode.Stretch)
        self.interval_table.setColumnWidth(0, 36)
        self.interval_table.setColumnWidth(1, 108)
        self.interval_table.setColumnWidth(2, 108)
        self.interval_table.setColumnWidth(3, 170)
        self.interval_table.setColumnWidth(5, 104)

    def refresh_counts(self, total: int, counts: Dict[str, int]) -> None:
        self.event_counts_total_label.setText("%d interval%s" % (total, "" if total == 1 else "s"))
        chips = []
        for event_type, count in sorted(counts.items()):
            color = event_type_qcolor(event_type).name()
            name = event_type.replace("&", "&amp;").replace("<", "&lt;")
            chips.append("<span style='color:%s'>●</span> %s <b>%d</b>" % (color, name, count))
        self.event_counts_label.setText(" &nbsp;&nbsp; ".join(chips))

    def clear(self) -> None:
        self.intervals = []
        self.interval_table.setRowCount(0)
        self.refresh_counts(0, {})
        self.details.show_interval(-1, None)


__all__ = ["IntervalsPanel", "IntervalDetailsPanel", "seconds_to_hhmmss"]

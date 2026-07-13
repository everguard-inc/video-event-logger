from typing import Dict, List

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QAbstractItemView,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from video_event_logger.models.interval import Interval


class IntervalsPanel(QWidget):
    play_requested = Signal(int)
    edit_requested = Signal(int)
    delete_requested = Signal(int)
    jump_requested = Signal(int)

    def __init__(self) -> None:
        super().__init__()
        self.setMinimumHeight(80)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        self.interval_table = QTableWidget(0, 6)
        self.interval_table.setHorizontalHeaderLabels(["#", "start", "end", "event_type", "comment", "actions"])
        self.interval_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.interval_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.interval_table.setSortingEnabled(False)
        self.interval_table.setMinimumHeight(70)
        self.interval_table.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.interval_table.setTextElideMode(Qt.TextElideMode.ElideRight)
        self.interval_table.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.interval_table.doubleClicked.connect(lambda index: self.jump_requested.emit(index.row()))
        self._configure_table_columns()

        counts_group = QGroupBox("Event Counts")
        counts_group.setMinimumHeight(70)
        counts_group.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        counts_layout = QVBoxLayout(counts_group)
        counts_layout.setContentsMargins(6, 6, 6, 6)
        self.event_counts_total_label = QLabel("Total: 0")
        self.event_counts_total_label.setMaximumHeight(20)
        self.event_counts_label = QLabel("")
        self.event_counts_label.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.event_counts_label.setWordWrap(True)
        self.event_counts_scroll = QScrollArea()
        self.event_counts_scroll.setWidgetResizable(True)
        self.event_counts_scroll.setWidget(self.event_counts_label)
        counts_layout.addWidget(self.event_counts_total_label)
        counts_layout.addWidget(self.event_counts_scroll)

        layout.addWidget(self.interval_table, 7)
        layout.addWidget(counts_group, 3)

    def selected_row(self) -> int:
        row = self.interval_table.currentRow()
        if row < 0 and self.interval_table.selectedItems():
            row = self.interval_table.selectedItems()[0].row()
        return row

    def refresh_intervals(self, intervals: List[Interval]) -> None:
        self.interval_table.setRowCount(0)
        self.interval_table.setRowCount(len(intervals))
        for row, interval in enumerate(intervals):
            self.interval_table.setItem(row, 0, QTableWidgetItem(str(row + 1)))
            self.interval_table.setItem(row, 1, QTableWidgetItem(interval.start_time_hhmmss))
            self.interval_table.setItem(row, 2, QTableWidgetItem(interval.end_time_hhmmss))
            event_type_item = QTableWidgetItem(interval.event_type)
            event_type_item.setToolTip(interval.event_type)
            self.interval_table.setItem(row, 3, event_type_item)
            comment_item = QTableWidgetItem(interval.comment)
            comment_item.setToolTip(interval.comment)
            self.interval_table.setItem(row, 4, comment_item)

            action_widget = QWidget()
            action_layout = QHBoxLayout(action_widget)
            action_layout.setContentsMargins(2, 0, 2, 0)
            action_layout.setSpacing(2)
            play_button = QPushButton("Play")
            play_button.setFixedWidth(42)
            play_button.setStyleSheet(
                "QPushButton { background: #eaf4ee; color: #163b25; border: 1px solid #9bb9a7; }"
                "QPushButton:pressed { background: #d8e8df; }"
            )
            play_button.clicked.connect(lambda checked=False, row_index=row: self.play_requested.emit(row_index))
            edit_button = QPushButton("Edit")
            edit_button.setFixedWidth(42)
            edit_button.setStyleSheet(
                "QPushButton { background: #f3eee3; color: #4a3520; border: 1px solid #b9aa92; }"
                "QPushButton:pressed { background: #e8dfd0; }"
            )
            edit_button.clicked.connect(lambda checked=False, row_index=row: self.edit_requested.emit(row_index))
            delete_button = QPushButton("Del")
            delete_button.setFixedWidth(42)
            delete_button.setStyleSheet(
                "QPushButton { background: #f5eded; color: #5a1d1d; border: 1px solid #c8a4a4; }"
                "QPushButton:pressed { background: #eadada; }"
            )
            delete_button.clicked.connect(lambda checked=False, row_index=row: self.delete_requested.emit(row_index))
            action_layout.addWidget(play_button)
            action_layout.addWidget(edit_button)
            action_layout.addWidget(delete_button)
            self.interval_table.setCellWidget(row, 5, action_widget)
        self._configure_table_columns()

    def _configure_table_columns(self) -> None:
        header = self.interval_table.horizontalHeader()
        header.setStretchLastSection(False)
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Fixed)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Fixed)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.Fixed)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.Fixed)
        header.setSectionResizeMode(4, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(5, QHeaderView.ResizeMode.Fixed)
        self.interval_table.setColumnWidth(0, 42)
        self.interval_table.setColumnWidth(1, 112)
        self.interval_table.setColumnWidth(2, 112)
        self.interval_table.setColumnWidth(3, 185)
        self.interval_table.setColumnWidth(5, 150)

    def refresh_counts(self, total: int, counts: Dict[str, int]) -> None:
        self.event_counts_total_label.setText("Total: %d" % total)
        lines = []
        for event_type, count in sorted(counts.items()):
            lines.append("%s: %d" % (event_type, count))
        self.event_counts_label.setText("\n".join(lines))

    def clear(self) -> None:
        self.interval_table.setRowCount(0)
        self.refresh_counts(0, {})

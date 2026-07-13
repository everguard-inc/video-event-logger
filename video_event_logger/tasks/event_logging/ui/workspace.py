from typing import Dict, List, Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QSplitter, QVBoxLayout, QWidget

from video_event_logger.models.interval import Interval
from video_event_logger.tasks.event_logging.ui.export_actions import ExportActions
from video_event_logger.tasks.event_logging.ui.intervals_panel import IntervalsPanel
from video_event_logger.tasks.event_logging.ui.metadata_panel import MetadataPanel
from video_event_logger.tasks.event_logging.ui.player_panel import PlayerPanel


class EventLoggingWorkspace(QWidget):
    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

        self.metadata_panel = MetadataPanel()
        self.player_panel = PlayerPanel(self)
        self.intervals_panel = IntervalsPanel()
        self.export_actions = ExportActions()
        self.video_player = self.player_panel.video_player

        root = QVBoxLayout(self)
        root.setContentsMargins(6, 6, 6, 6)
        root.setSpacing(6)
        root.addWidget(self.metadata_panel, 0)

        self.main_splitter = QSplitter(Qt.Orientation.Vertical)
        self.main_splitter.addWidget(self.player_panel)
        self.main_splitter.addWidget(self.intervals_panel)
        self.main_splitter.setStretchFactor(0, 5)
        self.main_splitter.setStretchFactor(1, 1)
        self.main_splitter.setCollapsible(0, False)
        self.main_splitter.setCollapsible(1, False)
        self.main_splitter.setSizes([620, 160])
        self.main_splitter.setHandleWidth(5)
        self.main_splitter.setStyleSheet(
            "QSplitter::handle:vertical { background: #b8b8b8; margin: 2px 0; }"
        )
        root.addWidget(self.main_splitter, 1)
        root.addWidget(self.export_actions, 0)

    def set_video_loaded(self, loaded: bool) -> None:
        self.player_panel.set_video_loaded(loaded)
        self.export_actions.set_video_loaded(loaded)

    def set_video_name(self, video_name: str) -> None:
        self.metadata_panel.set_video_name(video_name)

    def set_event_type(self, event_type: str) -> None:
        self.metadata_panel.set_event_type(event_type)

    def event_type_text(self) -> str:
        return self.metadata_panel.event_type_text()

    def show_popup_after_interval(self) -> bool:
        return self.metadata_panel.show_popup_after_interval()

    def clear_event_type_focus(self) -> None:
        self.metadata_panel.clear_event_type_focus()

    def set_event_type_lamp(self, state: str) -> None:
        self.metadata_panel.set_event_type_lamp(state)

    def set_save_status(self, status: str) -> None:
        self.metadata_panel.set_save_status(status)

    def set_status_text(self, text: str) -> None:
        self.metadata_panel.set_status_text(text)

    def show_autosave_indicator(self) -> None:
        self.metadata_panel.show_autosave_indicator()

    def selected_interval_row(self) -> int:
        return self.intervals_panel.selected_row()

    def refresh_intervals(self, intervals: List[Interval]) -> None:
        self.intervals_panel.refresh_intervals(intervals)

    def refresh_counts(self, total: int, counts: Dict[str, int]) -> None:
        self.intervals_panel.refresh_counts(total, counts)

    def clear_intervals(self) -> None:
        self.intervals_panel.clear()

    def set_speed_label(self, speed: float) -> None:
        self.player_panel.set_speed_label(speed)

    def set_rotation_label(self, degrees: int) -> None:
        self.player_panel.set_rotation_label(degrees)

    def set_rotation_enabled(self, enabled: bool) -> None:
        self.player_panel.set_rotation_enabled(enabled)

    def begin_slider_drag(self) -> None:
        self.player_panel.begin_slider_drag()

    def finish_slider_drag(self) -> float:
        return self.player_panel.finish_slider_drag()

    def preview_slider_position(self, value: int) -> None:
        self.player_panel.preview_slider_position(value)

    def update_timeline(self, current_seconds: float, duration_seconds: Optional[float]) -> None:
        self.player_panel.update_timeline(current_seconds, duration_seconds)

from typing import Dict, List, Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QSplitter, QVBoxLayout, QWidget

from video_event_logger.models.interval import Interval
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
        self.video_player = self.player_panel.video_player
        self.show_popup_after_interval_enabled = True

        self.root_layout = QVBoxLayout(self)
        self.root_layout.setContentsMargins(6, 6, 6, 6)
        self.root_layout.setSpacing(6)
        self.root_layout.addWidget(self.metadata_panel, 0)

        self.main_splitter = QSplitter(Qt.Orientation.Vertical)
        self.main_splitter.addWidget(self.player_panel)
        self.main_splitter.addWidget(self.intervals_panel)
        self.main_splitter.setStretchFactor(0, 5)
        self.main_splitter.setStretchFactor(1, 1)
        self.main_splitter.setCollapsible(0, False)
        self.main_splitter.setCollapsible(1, False)
        self.main_splitter.setSizes([620, 160])
        self.main_splitter.setHandleWidth(5)
        self.root_layout.addWidget(self.main_splitter, 1)
        self.normal_splitter_sizes = [620, 160]

    def set_video_loaded(self, loaded: bool) -> None:
        self.player_panel.set_video_loaded(loaded)

    def set_video_name(self, video_name: str) -> None:
        self.metadata_panel.set_video_name(video_name)

    def set_event_type(self, event_type: str) -> None:
        self.metadata_panel.set_event_type(event_type)

    def event_type_text(self) -> str:
        return self.metadata_panel.event_type_text()

    def show_popup_after_interval(self) -> bool:
        return self.show_popup_after_interval_enabled

    def set_show_popup_after_interval(self, enabled: bool) -> None:
        self.show_popup_after_interval_enabled = enabled

    def clear_event_type_focus(self) -> None:
        self.metadata_panel.clear_event_type_focus()

    def set_event_type_lamp(self, state: str) -> None:
        self.metadata_panel.set_event_type_lamp(state)

    def set_status_text(self, text: str) -> None:
        window = self.window()
        if hasattr(window, "show_status_message"):
            window.show_status_message(text)

    def show_fullscreen_notification(
        self,
        text: str,
        level: str = "info",
        persistent: bool = False,
    ) -> None:
        self.player_panel.show_fullscreen_notification(text, level, persistent)

    def notify_fullscreen_user_activity(self) -> None:
        self.player_panel.notify_fullscreen_user_activity()

    def selected_interval_row(self) -> int:
        return self.intervals_panel.selected_row()

    def refresh_intervals(self, intervals: List[Interval]) -> None:
        self.intervals_panel.refresh_intervals(intervals)

    def refresh_counts(self, total: int, counts: Dict[str, int]) -> None:
        self.intervals_panel.refresh_counts(total, counts)

    def clear_intervals(self) -> None:
        self.intervals_panel.clear()

    def set_active_speed(self, speed: float) -> None:
        self.player_panel.set_active_speed(speed)

    def set_playback_active(self, active: bool) -> None:
        self.player_panel.set_playback_active(active)

    def set_video_fullscreen(self, active: bool) -> None:
        if active:
            self.normal_splitter_sizes = self.main_splitter.sizes()
        self.metadata_panel.setVisible(not active)
        self.intervals_panel.setVisible(not active)
        self.player_panel.set_video_only_mode(active)
        margin = 0 if active else 6
        self.root_layout.setContentsMargins(margin, margin, margin, margin)
        self.root_layout.setSpacing(0 if active else 6)
        self.main_splitter.setHandleWidth(0 if active else 5)
        if not active:
            self.main_splitter.setSizes(self.normal_splitter_sizes)

    def set_pending_interval_start(
        self,
        start_seconds: Optional[float],
        persistent_in_fullscreen: bool = True,
    ) -> None:
        self.player_panel.set_pending_interval_start(
            start_seconds,
            persistent_in_fullscreen,
        )

    def begin_slider_drag(self) -> None:
        self.player_panel.begin_slider_drag()

    def finish_slider_drag(self) -> float:
        return self.player_panel.finish_slider_drag()

    def preview_slider_position(self, value: int) -> None:
        self.player_panel.preview_slider_position(value)

    def update_timeline(self, current_seconds: float, duration_seconds: Optional[float]) -> None:
        self.player_panel.update_timeline(current_seconds, duration_seconds)

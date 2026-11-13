from typing import Dict, List, Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QLabel, QSplitter, QVBoxLayout, QWidget

from video_event_logger.models.interval import Interval
from video_event_logger.tasks.event_logging.ui.intervals_panel import IntervalsPanel
from video_event_logger.tasks.event_logging.ui.metadata_panel import MetadataPanel
from video_event_logger.tasks.event_logging.ui.player_panel import PlayerPanel
from video_event_logger.tasks.event_logging.ui.playlist_panel import PlaylistPanel
from video_event_logger.tasks.event_logging.ui.playlist_overlay import PlaylistOverlay


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
        self.root_layout.setContentsMargins(0, 0, 0, 0)
        self.root_layout.setSpacing(0)
        self.root_layout.addWidget(self.metadata_panel, 0)
        # The event type is chosen where it is used: next to Start / End.
        self.player_panel.event_type_slot.addWidget(self.metadata_panel.event_type_input)
        self.player_panel.event_type_slot.addWidget(self.metadata_panel.event_type_lamp)

        self.main_splitter = QSplitter(Qt.Orientation.Vertical)
        self.main_splitter.addWidget(self.player_panel)
        self.main_splitter.addWidget(self.intervals_panel)
        self.main_splitter.setStretchFactor(0, 5)
        self.main_splitter.setStretchFactor(1, 2)
        self.main_splitter.setCollapsible(0, False)
        self.main_splitter.setCollapsible(1, False)
        self.main_splitter.setSizes([640, 230])
        self.main_splitter.setHandleWidth(8)
        self.playlist_panel = PlaylistPanel(self)
        self.horizontal_splitter = QSplitter(Qt.Orientation.Horizontal)
        self.horizontal_splitter.addWidget(self.main_splitter)
        self.horizontal_splitter.addWidget(self.playlist_panel)
        self.horizontal_splitter.setChildrenCollapsible(False)
        self.horizontal_splitter.setStretchFactor(0, 1)
        self.horizontal_splitter.setStretchFactor(1, 0)
        self.horizontal_splitter.setSizes([1000, 280])
        self.horizontal_splitter.setHandleWidth(8)
        self.content = QWidget()
        content_layout = QVBoxLayout(self.content)
        content_layout.setContentsMargins(12, 10, 12, 6)
        content_layout.setSpacing(6)
        content_layout.addWidget(self.horizontal_splitter, 1)
        self.shortcut_strip = QLabel(
            "Space play  ·  A start  ·  D end  ·  Q cancel  ·  Ctrl+Z undo (right after End: keep recording)  ·  "
            "←/→ 1 s  ·  ⇧←/⇧→ 10 s  ·  , . frame  ·  1 2 4 8 speed  ·  E events bar  ·  F11 full screen  ·  Ctrl+↵ submit"
        )
        self.shortcut_strip.setObjectName("shortcutStrip")
        content_layout.addWidget(self.shortcut_strip)
        self.root_layout.addWidget(self.content, 1)
        self.normal_splitter_sizes = [640, 230]
        self.playlist_overlay = PlaylistOverlay(self)
        self.video_player.fullscreen_hud.foreground_overlay = self.playlist_overlay.frame
        hud = self.video_player.fullscreen_hud
        hud.set_event_type(self.metadata_panel.event_type_text())
        self.metadata_panel.event_type_input.textChanged.connect(hud.set_event_type)

    def set_playlist_enabled(self, enabled: bool) -> None:
        self.playlist_overlay.set_enabled(enabled)

    def hideEvent(self, event):
        self.playlist_overlay.hide()
        super().hideEvent(event)

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
        self.player_panel.annotation_timeline.track.set_intervals(intervals)
        self.video_player.fullscreen_hud.set_intervals(intervals)
        self.intervals_panel.refresh_intervals(intervals)

    def refresh_counts(self, total: int, counts: Dict[str, int]) -> None:
        self.intervals_panel.refresh_counts(total, counts)

    def clear_intervals(self) -> None:
        self.intervals_panel.clear()
        self.player_panel.annotation_timeline.track.set_intervals([])
        self.video_player.fullscreen_hud.set_intervals([])

    def set_active_speed(self, speed: float) -> None:
        self.player_panel.set_active_speed(speed)

    def set_playback_active(self, active: bool) -> None:
        self.player_panel.set_playback_active(active)

    def set_video_fullscreen(self, active: bool) -> None:
        if active:
            self.normal_splitter_sizes = self.main_splitter.sizes()
        self.playlist_overlay.set_active(active)
        self.metadata_panel.setVisible(not active)
        self.intervals_panel.setVisible(not active)
        self.shortcut_strip.setVisible(not active)
        self.player_panel.set_video_only_mode(active)
        margin = 0 if active else 12
        self.content.layout().setContentsMargins(margin, 0 if active else 10, margin, 0 if active else 6)
        self.main_splitter.setHandleWidth(0 if active else 8)
        if not active:
            self.main_splitter.setSizes(self.normal_splitter_sizes)

    def set_pending_interval_start(
        self,
        start_seconds: Optional[float],
        persistent_in_fullscreen: bool = True,
    ) -> None:
        track = self.player_panel.annotation_timeline.track
        track.pending_start = start_seconds
        track.update()
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

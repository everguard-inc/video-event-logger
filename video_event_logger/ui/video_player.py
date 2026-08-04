import os
import sys
from ctypes.util import find_library
from pathlib import Path
from typing import List, Optional

from PySide6.QtCore import QEvent, QPointF, QRect, Qt, QTimer, Signal
from PySide6.QtGui import QPainter, QRegion, QWheelEvent
from PySide6.QtWidgets import QSizePolicy, QVBoxLayout, QWidget

from video_event_logger.ui.fullscreen_hud import FullscreenHud


def _detect_linux_libvlc() -> Optional[str]:
    configured_path = os.environ.get("PYTHON_VLC_LIB_PATH", "")
    if configured_path and (not os.path.isabs(configured_path) or os.path.isfile(configured_path)):
        return configured_path

    for candidate in (
        "/usr/lib/x86_64-linux-gnu/libvlc.so.5",
        "/lib/x86_64-linux-gnu/libvlc.so.5",
        "/usr/local/lib/libvlc.so.5",
    ):
        if os.path.isfile(candidate):
            return candidate

    detected = find_library("vlc")
    return detected or None


def _detect_linux_vlc_plugins(libvlc_path: Optional[str]) -> Optional[str]:
    configured_path = os.environ.get("VLC_PLUGIN_PATH", "")
    if configured_path and os.path.isdir(configured_path):
        return configured_path

    candidates = []
    if libvlc_path and os.path.isabs(libvlc_path):
        candidates.append(str(Path(libvlc_path).parent / "vlc" / "plugins"))
    candidates.extend(
        (
            "/usr/lib/x86_64-linux-gnu/vlc/plugins",
            "/usr/lib/vlc/plugins",
            "/usr/local/lib/vlc/plugins",
        )
    )
    for candidate in candidates:
        if os.path.isdir(candidate):
            return candidate
    return None


def _configure_vlc_environment() -> None:
    if not sys.platform.startswith("linux"):
        return

    libvlc_path = _detect_linux_libvlc()
    plugin_path = _detect_linux_vlc_plugins(libvlc_path)
    if libvlc_path:
        os.environ["PYTHON_VLC_LIB_PATH"] = libvlc_path
    elif os.path.isabs(os.environ.get("PYTHON_VLC_LIB_PATH", "")):
        os.environ.pop("PYTHON_VLC_LIB_PATH", None)
    if plugin_path:
        os.environ["VLC_PLUGIN_PATH"] = plugin_path
    elif os.environ.get("VLC_PLUGIN_PATH"):
        os.environ.pop("VLC_PLUGIN_PATH", None)


def _vlc_initialization_attempts(
    platform_name: Optional[str] = None,
) -> List[List[str]]:
    platform_name = platform_name or sys.platform
    if platform_name.startswith("linux"):
        # VLC 3.0.9.2 on Ubuntu 20.04 can render VA-API frames with shifted
        # chroma planes (a green band at the top). The VA-API DRM path avoids
        # the affected decoder/output interop, while plain X11 remains
        # embeddable through libVLC on both Xorg and Ubuntu 24.04's XWayland.
        # Qt owns the application's HUD, so VLC subpictures/OSD are unnecessary
        # and would otherwise trigger repeated YUVA -> VAOP blending errors.
        stable_linux_args = [
            "--ignore-config",
            "--avcodec-hw=vaapi_drm",
            "--vout=xcb_x11",
            "--no-osd",
            "--no-spu",
            "--no-video-title-show",
        ]
        return [
            stable_linux_args,
            ["--avcodec-hw=none", "--vout=xcb_x11", "--no-video-title-show"],
            ["--no-video-title-show"],
        ]
    return [
        ["--avcodec-hw=none", "--no-video-title-show"],
        ["--no-video-title-show"],
        [],
    ]


_configure_vlc_environment()

try:
    import vlc
except (ImportError, NotImplementedError, OSError, SystemExit) as exc:
    vlc = None
    VLC_IMPORT_ERROR = exc
else:
    VLC_IMPORT_ERROR = None


class VideoPlayer(QWidget):
    fullscreen_toggle_requested = Signal()
    fullscreen_seek_previewed = Signal(float)
    fullscreen_seek_requested = Signal(float)

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.instance = None
        self.media_player = None
        self.current_path = None  # type: Optional[Path]
        self.last_error = None  # type: Optional[str]
        self.rotation_degrees = 0
        self._zoom_level = 1.0
        self._pan_x = 0.0
        self._pan_y = 0.0

        # Create a container widget to clip the video surface
        self.video_container = QWidget(self)
        self.video_container.setStyleSheet("background: #111;")
        self.video_container.setMinimumHeight(120)
        self.video_container.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.video_container.setAutoFillBackground(True)  # Fill with background to prevent UI bleeding through

        self.video_surface = QWidget(self.video_container)
        self.video_surface.setAttribute(Qt.WidgetAttribute.WA_NativeWindow, True)
        self.video_surface.setAttribute(Qt.WidgetAttribute.WA_DontCreateNativeAncestors, True)
        self.video_surface.setStyleSheet("background: #111;")
        self.video_surface.setMouseTracking(True)
        self.video_surface.installEventFilter(self)

        self.fullscreen_hud = FullscreenHud(self.video_surface)
        self.fullscreen_hud.seek_previewed.connect(self.fullscreen_seek_previewed.emit)
        self.fullscreen_hud.seek_requested.connect(self.fullscreen_seek_requested.emit)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self.video_container, 1)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

        # Install event filter on container to handle resizing
        self.video_container.installEventFilter(self)

        if vlc is None:
            self.last_error = "python-vlc could not be imported: %s" % VLC_IMPORT_ERROR
            self.video_surface.setToolTip(self.last_error)
            return

        self._initialize_vlc()

    def set_fullscreen_hud_active(self, active: bool) -> None:
        self.fullscreen_hud.set_active(active)

    def update_fullscreen_hud_timeline(
        self,
        current_seconds: float,
        duration_seconds: Optional[float],
    ) -> None:
        self.fullscreen_hud.update_timeline(current_seconds, duration_seconds)

    def set_fullscreen_hud_playback_active(self, active: bool) -> None:
        self.fullscreen_hud.set_playback_active(active)

    def set_fullscreen_hud_speed(self, speed: float) -> None:
        self.fullscreen_hud.set_speed(speed)

    def set_fullscreen_hud_interval_start(self, start_seconds: Optional[float]) -> None:
        self.fullscreen_hud.set_pending_interval_start(start_seconds)

    def set_fullscreen_hud_interval_state(
        self,
        start_seconds: Optional[float],
        persistent: bool,
    ) -> None:
        self.fullscreen_hud.set_pending_interval_start(start_seconds, persistent)

    def notify_fullscreen_user_activity(self) -> None:
        self.fullscreen_hud.notify_user_activity()

    def show_fullscreen_notification(
        self,
        text: str,
        level: str = "info",
        persistent: bool = False,
    ) -> None:
        self.fullscreen_hud.show_notification(text, level, persistent)

    def eventFilter(self, watched, event) -> bool:  # type: ignore[no-untyped-def]
        if watched is self.video_surface:
            if event.type() == QEvent.Type.MouseButtonDblClick:
                self.fullscreen_toggle_requested.emit()
                return True
            elif event.type() == QEvent.Type.Wheel:
                return self._handle_wheel_event(event)
        elif watched is self.video_container:
            if event.type() == QEvent.Type.Resize:
                self._apply_zoom_transform()

        return super().eventFilter(watched, event)

    def is_available(self) -> bool:
        return self.media_player is not None and self.instance is not None

    def _reset_zoom(self) -> None:
        """Reset zoom to 1.0x (original size) and center the video."""
        self._zoom_level = 1.0
        self._pan_x = 0.0
        self._pan_y = 0.0
        self._apply_zoom_transform()

    def _handle_wheel_event(self, event: QWheelEvent) -> bool:
        """Handle Ctrl+Scroll zoom interaction."""
        if not (event.modifiers() & Qt.KeyboardModifier.ControlModifier):
            return False

        new_zoom = self._calculate_new_zoom_level(event.angleDelta().y())
        if new_zoom == self._zoom_level:
            return True

        mouse_container_pos = self._get_mouse_position_in_container(event.position())
        new_pan_x, new_pan_y = self._calculate_pan_for_cursor_zoom(
            mouse_container_pos, new_zoom
        )

        self._zoom_level = new_zoom
        self._pan_x = new_pan_x
        self._pan_y = new_pan_y

        self._apply_zoom_transform()
        return True

    def _calculate_new_zoom_level(self, wheel_delta: float) -> float:
        """Calculate new zoom level from wheel delta, clamped to valid range."""
        ZOOM_FACTOR = 1.05
        MIN_ZOOM = 1.0
        MAX_ZOOM = 5.0

        zoom_multiplier = ZOOM_FACTOR if wheel_delta > 0 else 1.0 / ZOOM_FACTOR
        new_zoom = self._zoom_level * zoom_multiplier
        return max(MIN_ZOOM, min(new_zoom, MAX_ZOOM))

    def _get_mouse_position_in_container(self, surface_pos: QPointF) -> QPointF:
        """Convert mouse position from video_surface to video_container coordinates."""
        mouse_global = self.video_surface.mapToGlobal(surface_pos.toPoint())
        return self.video_container.mapFromGlobal(mouse_global)

    def _calculate_pan_for_cursor_zoom(
        self, cursor_pos: QPointF, new_zoom: float
    ) -> tuple[float, float]:
        """Calculate pan offset to keep the point under cursor fixed during zoom."""
        container_width = self.video_container.width()
        container_height = self.video_container.height()
        center_x = container_width / 2.0
        center_y = container_height / 2.0

        # Map cursor position to unzoomed video coordinate space
        unzoomed_x = (cursor_pos.x() - center_x - self._pan_x) / self._zoom_level
        unzoomed_y = (cursor_pos.y() - center_y - self._pan_y) / self._zoom_level

        # Calculate pan that keeps that point under the cursor at new zoom
        new_pan_x = cursor_pos.x() - center_x - unzoomed_x * new_zoom
        new_pan_y = cursor_pos.y() - center_y - unzoomed_y * new_zoom

        return new_pan_x, new_pan_y

    def _apply_zoom_transform(self) -> None:
        """Apply zoom and pan transformation to video surface."""
        container_width = self.video_container.width()
        container_height = self.video_container.height()

        surface_width = int(container_width * self._zoom_level)
        surface_height = int(container_height * self._zoom_level)

        x, y = self._calculate_constrained_position(
            container_width, container_height, surface_width, surface_height
        )

        self._apply_geometry_with_mask(x, y, surface_width, surface_height)

    def _calculate_constrained_position(
        self,
        container_width: int,
        container_height: int,
        surface_width: int,
        surface_height: int,
    ) -> tuple[int, int]:
        """Calculate video surface position, constrained to fill viewport."""
        # Start with centered position plus pan offset
        x = int((container_width - surface_width) / 2.0 + self._pan_x)
        y = int((container_height - surface_height) / 2.0 + self._pan_y)

        # Constrain horizontally
        if x > 0:
            x = 0
            self._pan_x = x - (container_width - surface_width) / 2.0
        elif x + surface_width < container_width:
            x = container_width - surface_width
            self._pan_x = x - (container_width - surface_width) / 2.0

        # Constrain vertically
        if y > 0:
            y = 0
            self._pan_y = y - (container_height - surface_height) / 2.0
        elif y + surface_height < container_height:
            y = container_height - surface_height
            self._pan_y = y - (container_height - surface_height) / 2.0

        return x, y

    def _apply_geometry_with_mask(
        self, x: int, y: int, width: int, height: int
    ) -> None:
        """Apply geometry and clipping mask to video surface, preventing visual artifacts."""
        was_visible = self.video_surface.isVisible()
        if was_visible:
            self.video_surface.hide()

        self._update_clipping_mask(x, y, width, height)
        self.video_surface.setGeometry(x, y, width, height)

        if was_visible:
            self.video_surface.show()

    def _update_clipping_mask(self, x: int, y: int, width: int, height: int) -> None:
        """Update clipping mask to prevent video from rendering outside viewport."""
        container_width = self.video_container.width()
        container_height = self.video_container.height()

        if not self._needs_clipping(x, y, width, height, container_width, container_height):
            self.video_surface.clearMask()
            return

        visible_x = max(0, -x)
        visible_y = max(0, -y)
        visible_width = min(width - visible_x, container_width - max(0, x))
        visible_height = min(height - visible_y, container_height - max(0, y))

        mask_region = QRegion(visible_x, visible_y, visible_width, visible_height)
        self.video_surface.setMask(mask_region)

    @staticmethod
    def _needs_clipping(
        x: int,
        y: int,
        width: int,
        height: int,
        container_width: int,
        container_height: int,
    ) -> bool:
        """Check if video surface extends beyond container bounds."""
        return (
            x < 0
            or y < 0
            or x + width > container_width
            or y + height > container_height
        )

    def _initialize_vlc(self) -> bool:
        attempts = _vlc_initialization_attempts()

        rotation_args = self._rotation_vlc_args()
        errors = []
        for args in attempts:
            full_args = args + rotation_args
            try:
                instance = vlc.Instance(*full_args)
                if instance is None:
                    errors.append("vlc.Instance returned None for args: %s" % (full_args or ["<none>"]))
                    continue
                media_player = instance.media_player_new()
                if media_player is None:
                    errors.append("media_player_new returned None for args: %s" % (full_args or ["<none>"]))
                    continue
                self.instance = instance
                self.media_player = media_player
                self.last_error = None
                return True
            except Exception as exc:
                errors.append("%s for args: %s" % (exc, full_args or ["<none>"]))

        self.instance = None
        self.media_player = None
        self.last_error = (
            "Could not initialize VLC. Attempts: %s. "
            "PYTHON_VLC_LIB_PATH=%s VLC_PLUGIN_PATH=%s"
        ) % (
            " | ".join(errors),
            os.environ.get("PYTHON_VLC_LIB_PATH", ""),
            os.environ.get("VLC_PLUGIN_PATH", ""),
        )
        self.video_surface.setToolTip(self.last_error)
        return False

    def _rotation_vlc_args(self) -> List[str]:
        if self.rotation_degrees == 0:
            return []
        return ["--video-filter=transform", "--transform-type=%d" % self.rotation_degrees]

    def load_video(self, path: Path) -> bool:
        if not self.is_available():
            return False
        media = self._create_media(path)
        self.media_player.set_media(media)
        self._attach_video_surface()
        self.current_path = path
        self.last_error = None
        self.video_surface.setToolTip("")
        return True

    def play_pause(self) -> None:
        if not self.is_available():
            return
        if self.media_player.is_playing():
            self.pause()
        else:
            if self.is_ended() or self.is_at_end():
                self.restart()
            self.media_player.play()

    def pause(self) -> None:
        if not self.is_available():
            return
        if hasattr(self.media_player, "set_pause"):
            self.media_player.set_pause(1)
        elif self.media_player.is_playing():
            self.media_player.pause()

    def play(self) -> None:
        if self.is_available():
            if self.is_ended() or self.is_at_end():
                self.restart()
            self.media_player.play()

    def is_playing(self) -> bool:
        if not self.is_available():
            return False
        return bool(self.media_player.is_playing())

    def is_ended(self) -> bool:
        if not self.is_available() or vlc is None:
            return False
        return self.media_player.get_state() == vlc.State.Ended

    def restart(self) -> None:
        if not self.is_available():
            return
        self.media_player.stop()
        self.media_player.set_time(0)

    def is_at_end(self) -> bool:
        duration = self.get_duration_seconds()
        if duration is None:
            return False
        return self.get_time_seconds() >= max(0.0, duration - 0.25)

    def seek_relative(self, seconds_delta: float) -> None:
        if not self.is_available():
            return
        current = self.get_time_seconds()
        target = max(0.0, current + seconds_delta)
        duration = self.get_duration_seconds()
        if duration is not None:
            target = min(target, duration)
        self.set_time_seconds(target)

    def set_time_seconds(self, seconds: float) -> None:
        if self.is_available():
            self.media_player.set_time(int(max(0.0, seconds) * 1000))

    def get_time_seconds(self) -> float:
        if not self.is_available():
            return 0.0
        milliseconds = self.media_player.get_time()
        if milliseconds < 0:
            return 0.0
        return milliseconds / 1000.0

    def get_duration_seconds(self) -> Optional[float]:
        if not self.is_available():
            return None
        milliseconds = self.media_player.get_length()
        if milliseconds <= 0:
            return None
        return milliseconds / 1000.0

    def set_rate(self, rate: float) -> bool:
        if not self.is_available():
            return False
        result = self.media_player.set_rate(rate)
        return result == 0

    def step_forward_frame(self) -> bool:
        if not self.is_available():
            return False
        self.pause()
        self.seek_relative(self.get_frame_duration_seconds())
        return True

    def step_backward_frame(self) -> bool:
        if not self.is_available():
            return False
        self.pause()
        self.seek_relative(-self.get_frame_duration_seconds())
        return True

    def get_frame_duration_seconds(self) -> float:
        fps = self.get_fps()
        if fps is None or fps <= 0:
            return 1.0 / 30.0
        return 1.0 / fps

    def get_fps(self) -> Optional[float]:
        if not self.is_available():
            return None
        try:
            fps = float(self.media_player.get_fps())
        except Exception:
            return None
        if fps <= 0:
            return None
        return fps

    def rotate_clockwise(self) -> int:
        next_rotation = (self.rotation_degrees + 90) % 360
        if not self.set_rotation_degrees(next_rotation):
            return self.rotation_degrees
        return self.rotation_degrees

    def set_rotation_degrees(self, degrees: int) -> bool:
        normalized = degrees % 360
        if normalized not in (0, 90, 180, 270):
            return False
        if self.is_playing():
            return False
        if normalized == self.rotation_degrees:
            return True
        previous_rotation = self.rotation_degrees
        self.rotation_degrees = normalized
        if self.current_path is None:
            return True
        if self._reload_current_media():
            return True
        self.rotation_degrees = previous_rotation
        self._reload_current_media()
        return False

    def _create_media(self, path: Path):
        return self.instance.media_new(str(path))

    def _reload_current_media(self) -> bool:
        if not self.is_available() or self.current_path is None:
            return False
        position_seconds = self.get_time_seconds()
        was_playing = self.is_playing()
        try:
            current_rate = self.media_player.get_rate()
        except Exception:
            current_rate = 1.0

        path = self.current_path
        self.media_player.stop()
        if not self._initialize_vlc():
            return False
        self.load_video(path)
        self.media_player.play()
        QTimer.singleShot(100, lambda: self.set_rate(current_rate))
        QTimer.singleShot(180, lambda: self.set_time_seconds(position_seconds))
        if not was_playing:
            QTimer.singleShot(360, self.pause)
        return True

    def _attach_video_surface(self) -> None:
        if not self.is_available():
            return
        window_id = int(self.video_surface.winId())
        if sys.platform.startswith("linux"):
            self.media_player.set_xwindow(window_id)
        elif sys.platform == "darwin":
            self.media_player.set_nsobject(window_id)
        elif sys.platform.startswith("win"):
            self.media_player.set_hwnd(window_id)
        try:
            self.media_player.video_set_mouse_input(False)
            self.media_player.video_set_key_input(False)
        except (AttributeError, TypeError):
            pass

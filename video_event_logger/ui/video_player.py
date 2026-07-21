import os
import sys
from ctypes.util import find_library
from pathlib import Path
from typing import List, Optional

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import QSizePolicy, QVBoxLayout, QWidget


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


_configure_vlc_environment()

try:
    import vlc
except (ImportError, NotImplementedError, OSError, SystemExit) as exc:
    vlc = None
    VLC_IMPORT_ERROR = exc
else:
    VLC_IMPORT_ERROR = None


class VideoPlayer(QWidget):
    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.instance = None
        self.media_player = None
        self.current_path = None  # type: Optional[Path]
        self.last_error = None  # type: Optional[str]
        self.rotation_degrees = 0

        self.video_surface = QWidget(self)
        self.video_surface.setAttribute(Qt.WidgetAttribute.WA_NativeWindow, True)
        self.video_surface.setAttribute(Qt.WidgetAttribute.WA_DontCreateNativeAncestors, True)
        self.video_surface.setMinimumHeight(120)
        self.video_surface.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.video_surface.setStyleSheet("background: #111;")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self.video_surface, 1)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

        if vlc is None:
            self.last_error = "python-vlc could not be imported: %s" % VLC_IMPORT_ERROR
            self.video_surface.setToolTip(self.last_error)
            return

        self._initialize_vlc()

    def is_available(self) -> bool:
        return self.media_player is not None and self.instance is not None

    def _initialize_vlc(self) -> bool:
        attempts = [
            ["--avcodec-hw=none", "--no-video-title-show"],
            ["--no-video-title-show"],
            [],
        ]  # type: List[List[str]]

        plugin_path = self._default_vlc_plugin_path()
        if plugin_path:
            attempts.insert(0, ["--plugin-path=%s" % plugin_path, "--avcodec-hw=none", "--no-video-title-show"])

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

    def _default_vlc_plugin_path(self) -> Optional[str]:
        if not sys.platform.startswith("linux"):
            return None
        return _detect_linux_vlc_plugins(os.environ.get("PYTHON_VLC_LIB_PATH"))

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

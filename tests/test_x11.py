import unittest
from unittest.mock import Mock, patch

from video_event_logger.services import x11


class X11InitializationTest(unittest.TestCase):
    def tearDown(self) -> None:
        x11._xlib_handle = None

    def test_non_linux_platform_does_not_load_xlib(self) -> None:
        with patch("video_event_logger.services.x11.ctypes.CDLL") as loader:
            initialized = x11.initialize_x11_threads("darwin")

        self.assertTrue(initialized)
        loader.assert_not_called()

    def test_linux_initializes_xlib_threads(self) -> None:
        xlib = Mock()
        xlib.XInitThreads.return_value = 1
        with patch("video_event_logger.services.x11.ctypes.CDLL", return_value=xlib):
            initialized = x11.initialize_x11_threads("linux")

        self.assertTrue(initialized)
        xlib.XInitThreads.assert_called_once_with()

    def test_linux_reports_xlib_initialization_failure(self) -> None:
        with patch(
            "video_event_logger.services.x11.ctypes.CDLL",
            side_effect=OSError("missing Xlib"),
        ):
            initialized = x11.initialize_x11_threads("linux")

        self.assertFalse(initialized)


if __name__ == "__main__":
    unittest.main()

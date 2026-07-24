import unittest

from video_event_logger.ui.video_player import _vlc_initialization_attempts


class VideoPlayerConfigurationTest(unittest.TestCase):
    def test_linux_uses_vaapi_drm_and_embeddable_x11_output(self) -> None:
        attempts = _vlc_initialization_attempts(
            platform_name="linux",
        )

        self.assertIn("--ignore-config", attempts[0])
        self.assertIn("--avcodec-hw=vaapi_drm", attempts[0])
        self.assertIn("--vout=xcb_x11", attempts[0])
        self.assertIn("--no-osd", attempts[0])
        self.assertIn("--no-spu", attempts[0])
        self.assertFalse(any(option.startswith("--plugin-path=") for option in attempts[0]))

    def test_non_linux_does_not_force_the_x11_output(self) -> None:
        attempts = _vlc_initialization_attempts(platform_name="darwin")

        self.assertNotIn("--vout=xcb_x11", attempts[0])


if __name__ == "__main__":
    unittest.main()

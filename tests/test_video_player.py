import unittest
from pathlib import Path
from unittest.mock import Mock

from video_event_logger.ui.video_player import VideoPlayer, _vlc_initialization_attempts


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

    def test_decoder_buffers_are_independent_of_video_output_in_every_fallback(self):
        for platform in ("linux", "darwin", "win32"):
            for args in _vlc_initialization_attempts(platform):
                self.assertIn("--no-avcodec-dr", args)
                self.assertFalse(any(arg.startswith("--avcodec-threads") for arg in args))

    def test_loading_stops_previous_input_and_releases_creation_reference(self):
        player = Mock()
        player.is_available.return_value = True
        media = Mock()
        player._create_media.return_value = media
        calls = Mock()
        calls.attach_mock(player.media_player.stop, "stop")
        calls.attach_mock(player.media_player.set_media, "set_media")
        calls.attach_mock(media.release, "release")
        self.assertTrue(VideoPlayer.load_video(player, Path("clip.mp4")))
        self.assertEqual([call[0] for call in calls.mock_calls], ["stop", "set_media", "release"])


if __name__ == "__main__":
    unittest.main()

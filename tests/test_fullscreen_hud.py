import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QEvent, QPoint
from PySide6.QtWidgets import QApplication, QWidget

from video_event_logger.ui.fullscreen_hud import FullscreenHud


class FullscreenHudTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.application = QApplication.instance() or QApplication([])

    def make_hud(self) -> FullscreenHud:
        surface = QWidget()
        surface.resize(800, 450)
        surface.show()
        self.addCleanup(surface.close)
        hud = FullscreenHud(surface)
        hud.set_active(True)
        self.application.processEvents()
        return hud

    def test_hud_shows_progress_playback_speed_and_active_interval(self) -> None:
        hud = self.make_hud()

        hud.update_timeline(67.89, 255.0)
        hud.set_playback_active(True)
        hud.set_speed(4.0)
        hud.set_pending_interval_start(62.345)

        self.assertTrue(hud.bottom_bar.isVisible())
        self.assertTrue(hud.bottom_bar.isWindow())
        self.assertTrue(hud.interval_label.isWindow())
        self.assertEqual(hud.current_time_label.text(), "00:01:07.890")
        self.assertEqual(hud.duration_label.text(), "00:04:15.000")
        self.assertEqual(hud.playback_label.text(), "PLAYING")
        self.assertEqual(hud.speed_label.text(), "x4")
        self.assertIn("00:01:02.345", hud.interval_label.text())
        self.assertTrue(hud.interval_label.isVisible())

    def test_hud_is_compact_centered_and_inside_the_video_surface(self) -> None:
        hud = self.make_hud()
        hud.video_surface.resize(1920, 1080)
        hud.set_pending_interval_start(12.345)
        hud._layout_widgets()
        self.application.processEvents()

        surface_origin = hud.video_surface.mapToGlobal(QPoint(0, 0))
        surface_center_x = surface_origin.x() + hud.video_surface.width() // 2
        bar_geometry = hud.bottom_bar.geometry()
        label_geometry = hud.interval_label.geometry()

        self.assertLessEqual(bar_geometry.width(), hud.MAX_CONTROL_BAR_WIDTH)
        self.assertGreaterEqual(bar_geometry.left(), surface_origin.x())
        self.assertLessEqual(
            bar_geometry.right(),
            surface_origin.x() + hud.video_surface.width() - 1,
        )
        self.assertLessEqual(abs(bar_geometry.center().x() - surface_center_x), 1)
        self.assertLessEqual(abs(label_geometry.center().x() - surface_center_x), 1)

    def test_slider_previews_and_requests_exact_seek_position(self) -> None:
        hud = self.make_hud()
        previewed = []
        requested = []
        hud.seek_previewed.connect(previewed.append)
        hud.seek_requested.connect(requested.append)
        hud.update_timeline(0.0, 20.0)

        hud._begin_slider_drag()
        hud.timeline_slider.setValue(7250)
        hud._preview_slider_position(7250)
        hud._finish_slider_drag()

        self.assertEqual(previewed, [7.25])
        self.assertEqual(requested, [7.25])
        self.assertEqual(hud.current_time_label.text(), "00:00:07.250")

    def test_controls_auto_hide_and_user_activity_shows_them_again(self) -> None:
        hud = self.make_hud()

        hud._auto_hide_controls()

        self.assertFalse(hud.controls_visible)
        self.assertTrue(hud.bottom_bar.isHidden())

        hud.notify_user_activity()

        self.assertTrue(hud.controls_visible)
        self.assertFalse(hud.bottom_bar.isHidden())
        self.assertTrue(hud.controls_hide_timer.isActive())

    def test_duplicate_mouse_move_without_position_change_does_not_show_controls(self) -> None:
        hud = self.make_hud()
        hud._auto_hide_controls()

        hud.eventFilter(hud.video_surface, QEvent(QEvent.Type.MouseMove))

        self.assertFalse(hud.controls_visible)
        self.assertTrue(hud.bottom_bar.isHidden())

    def test_active_interval_badge_remains_when_controls_are_hidden(self) -> None:
        hud = self.make_hud()

        hud.set_pending_interval_start(12.345)
        hud._auto_hide_controls()

        self.assertTrue(hud.interval_indicator_persistent)
        self.assertFalse(hud.interval_label.isHidden())
        self.assertTrue(hud.bottom_bar.isHidden())

    def test_notifications_use_the_top_status_label_and_restore_active_interval(self) -> None:
        surface = QWidget()
        self.addCleanup(surface.close)
        hud = FullscreenHud(surface)

        hud.show_notification("Interval saved", "success")
        self.assertTrue(hud.interval_label.isHidden())

        hud.set_active(True)
        hud.set_pending_interval_start(12.345)
        hud.show_notification("Autosave failed", "error", persistent=True)

        self.assertFalse(hud.interval_label.isHidden())
        self.assertEqual(hud.interval_label.text(), "Autosave failed")
        self.assertFalse(hud.notification_timer.isActive())

        hud._hide_notification()

        self.assertIn("INTERVAL ACTIVE", hud.interval_label.text())
        self.assertFalse(hud.interval_label.isHidden())


if __name__ == "__main__":
    unittest.main()

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
        self.assertEqual(hud.play_button.text(), "❚❚ Pause")
        self.assertTrue(hud.speed_buttons[4.0].isChecked())
        self.assertIn("REC", hud.interval_label.text())
        self.assertIn("5.5 s", hud.interval_label.text())
        self.assertEqual(hud.speed_label.text(), "x4")
        self.assertIn("00:01:02.345", hud.interval_label.text())
        self.assertTrue(hud.interval_label.isVisible())

    def test_hud_seek_buttons_request_relative_seek(self) -> None:
        hud = self.make_hud()
        requested = []
        hud.seek_relative_requested.connect(requested.append)

        hud.seek_back_10_button.click()
        hud.seek_back_button.click()
        hud.seek_forward_button.click()
        hud.seek_forward_10_button.click()

        self.assertEqual(requested, [-10.0, -1.0, 1.0, 10.0])
        self.assertTrue(hud.seek_back_10_button.isVisible())

    def test_always_visible_controls_are_not_auto_hidden(self) -> None:
        hud = self.make_hud()

        hud.set_controls_always_visible(True)
        hud._auto_hide_controls()
        self.assertTrue(hud.bottom_bar.isVisible())

        hud.set_controls_always_visible(False)
        hud._auto_hide_controls()
        self.assertFalse(hud.bottom_bar.isVisible())

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

    def test_enter_event_without_pointer_movement_keeps_controls_hidden(self) -> None:
        hud = self.make_hud()
        hud._auto_hide_controls()

        # macOS sends Enter to the video when an overlay above it hides.
        hud.eventFilter(hud.video_surface, QEvent(QEvent.Type.Enter))

        self.assertFalse(hud.controls_visible)
        self.assertTrue(hud.bottom_bar.isHidden())

    def test_events_bar_floats_above_controls_and_hides_with_them(self) -> None:
        hud = self.make_hud()
        bar = QWidget()
        bar.setFixedHeight(120)
        toggled = []
        hud.events_bar_toggled.connect(toggled.append)

        hud.attach_events_bar(bar)
        self.application.processEvents()
        self.assertIs(bar.parentWidget(), hud.events_panel)
        self.assertTrue(hud.events_button.isChecked())
        self.assertFalse(hud.events_panel.isHidden())
        self.assertLess(hud.events_panel.geometry().bottom(), hud.bottom_bar.geometry().top())

        hud._auto_hide_controls()
        self.assertTrue(hud.events_panel.isHidden())

        hud.events_button.click()
        self.assertEqual(toggled, [False])
        self.assertIs(hud.detach_events_bar(), bar)
        self.assertFalse(hud.events_button.isChecked())

    def test_active_interval_badge_remains_when_controls_are_hidden(self) -> None:
        hud = self.make_hud()

        hud.set_pending_interval_start(12.345)
        hud._auto_hide_controls()

        self.assertTrue(hud.interval_indicator_persistent)
        self.assertFalse(hud.interval_label.isHidden())
        self.assertTrue(hud.bottom_bar.isHidden())

    def test_notifications_never_hide_the_recording_pill(self) -> None:
        surface = QWidget()
        self.addCleanup(surface.close)
        hud = FullscreenHud(surface)

        hud.show_notification("Interval saved", "success")
        self.assertTrue(hud.toast_label.isHidden())

        hud.set_active(True)
        hud.set_pending_interval_start(12.345)
        hud.show_notification("Autosave failed", "error", persistent=True)

        self.assertFalse(hud.toast_label.isHidden())
        self.assertEqual(hud.toast_label.text(), "Autosave failed")
        self.assertFalse(hud.interval_label.isHidden())
        self.assertIn("REC", hud.interval_label.text())
        self.assertFalse(hud.notification_timer.isActive())

        hud._hide_notification()
        self.assertTrue(hud.toast_label.isHidden())
        self.assertFalse(hud.interval_label.isHidden())

    def test_buttons_request_playback_and_interval_actions(self) -> None:
        hud = self.make_hud()
        calls = []
        hud.play_pause_requested.connect(lambda: calls.append("play"))
        hud.frame_step_requested.connect(lambda step: calls.append(("frame", step)))
        hud.speed_requested.connect(lambda speed: calls.append(("speed", speed)))
        hud.interval_start_requested.connect(lambda: calls.append("start"))
        hud.interval_end_requested.connect(lambda: calls.append("end"))
        hud.interval_cancel_requested.connect(lambda: calls.append("cancel"))

        self.assertTrue(hud.start_button.isVisibleTo(hud.bottom_bar))
        self.assertFalse(hud.end_button.isVisibleTo(hud.bottom_bar))
        hud.play_button.click()
        hud.frame_back_button.click()
        hud.speed_buttons[2.0].click()
        hud.start_button.click()
        hud.set_pending_interval_start(3.0)
        self.assertFalse(hud.start_button.isVisibleTo(hud.bottom_bar))
        hud.end_button.click()
        hud.cancel_button.click()

        self.assertEqual(calls, ["play", ("frame", -1), ("speed", 2.0), "start", "end", "cancel"])

    def test_seek_track_carries_interval_markers_and_recording_range(self) -> None:
        from types import SimpleNamespace
        hud = self.make_hud()
        hud.update_timeline(30.0, 120.0)
        hud.set_intervals([SimpleNamespace(start_time_seconds=4.0, end_time_seconds=9.0, event_type="fall")])
        hud.set_event_type("no_helmet")
        hud.set_pending_interval_start(31.0)
        hud.update_timeline(36.5, 120.0)

        self.assertEqual(len(hud.timeline_slider.segments), 1)
        self.assertEqual(hud.timeline_slider.pending, (31.0, 36.5))
        self.assertIn("no_helmet", hud.interval_label.text())
        self.assertIn("no_helmet", hud.type_label.text())
        hud.timeline_slider.repaint()


if __name__ == "__main__":
    unittest.main()

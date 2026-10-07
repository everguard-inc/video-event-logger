import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from PySide6.QtCore import QUrl
from PySide6.QtDBus import QDBusMessage

from video_event_logger.services import file_manager


class ShowFileInFolderTest(unittest.TestCase):
    def make_bus(self, reply_type: QDBusMessage.MessageType) -> Mock:
        bus = Mock()
        bus.isConnected.return_value = True
        bus.call.return_value.type.return_value = reply_type
        return bus

    @patch("video_event_logger.services.file_manager.QDesktopServices")
    @patch("video_event_logger.services.file_manager.QDBusConnection")
    def test_file_manager_selects_the_file(self, connection, desktop) -> None:
        bus = self.make_bus(QDBusMessage.MessageType.ReplyMessage)
        connection.sessionBus.return_value = bus

        file_manager.show_file_in_folder(Path("/data/results/video 1.json"))

        message = bus.call.call_args.args[0]
        self.assertEqual(message.member(), "ShowItems")
        self.assertEqual(
            message.arguments(),
            [["file:///data/results/video%201.json"], ""],
        )
        desktop.openUrl.assert_not_called()

    @patch("video_event_logger.services.file_manager.QDesktopServices")
    @patch("video_event_logger.services.file_manager.QDBusConnection")
    def test_falls_back_to_opening_the_folder(self, connection, desktop) -> None:
        connection.sessionBus.return_value = self.make_bus(
            QDBusMessage.MessageType.ErrorMessage
        )

        file_manager.show_file_in_folder(Path("/data/results/video.json"))

        desktop.openUrl.assert_called_once_with(QUrl.fromLocalFile("/data/results"))


if __name__ == "__main__":
    unittest.main()

from pathlib import Path

from PySide6.QtCore import QUrl
from PySide6.QtDBus import QDBus, QDBusConnection, QDBusMessage
from PySide6.QtGui import QDesktopServices

FILE_MANAGER_SERVICE = "org.freedesktop.FileManager1"
FILE_MANAGER_PATH = "/org/freedesktop/FileManager1"
SHOW_ITEMS_TIMEOUT_MS = 3000


def show_file_in_folder(path: Path) -> None:
    """Open the containing folder with ``path`` selected, or just the folder."""
    if not _select_with_file_manager(path):
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(path.parent)))


def _select_with_file_manager(path: Path) -> bool:
    # Nautilus, Dolphin, Nemo and Caja implement the freedesktop FileManager1
    # interface, which opens the folder and highlights the given items.
    bus = QDBusConnection.sessionBus()
    if not bus.isConnected():
        return False
    message = QDBusMessage.createMethodCall(
        FILE_MANAGER_SERVICE,
        FILE_MANAGER_PATH,
        FILE_MANAGER_SERVICE,
        "ShowItems",
    )
    uri = QUrl.fromLocalFile(str(path)).toString(QUrl.ComponentFormattingOption.FullyEncoded)
    message.setArguments([[uri], ""])
    reply = bus.call(message, QDBus.CallMode.Block, SHOW_ITEMS_TIMEOUT_MS)
    return reply.type() == QDBusMessage.MessageType.ReplyMessage

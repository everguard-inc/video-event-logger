from pathlib import Path

from PySide6.QtGui import QColor
from PySide6.QtCore import Signal, Qt
from PySide6.QtWidgets import (
    QCheckBox, QDialog, QDialogButtonBox, QFileDialog, QHBoxLayout, QLabel,
    QLineEdit, QListWidget, QListWidgetItem, QPushButton, QToolButton, QStyle, QVBoxLayout, QWidget,
)


class AnnotationSourceDialog(QDialog):
    """Optional annotation selection before activating the first chosen video."""
    def __init__(self, video_path: Path, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Open video and annotations")
        self.resize(540, 180)
        layout = QVBoxLayout(self)
        name = QLabel(video_path.name)
        name.setTextFormat(Qt.TextFormat.PlainText)
        name.setWordWrap(True)
        layout.addWidget(name)
        layout.addWidget(QLabel("Annotations (optional; leave empty to use saved work or start empty)"))
        row = QHBoxLayout()
        self.path_input = QLineEdit()
        self.path_input.setPlaceholderText("Default annotations")
        row.addWidget(self.path_input)
        browse = QPushButton("Choose JSON…")
        def choose():
            path, _ = QFileDialog.getOpenFileName(self, "Open Annotations", str(video_path.parent), "Annotations (*.json)")
            if path:
                self.path_input.setText(path)
        browse.clicked.connect(choose)
        row.addWidget(browse)
        layout.addLayout(row)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Open | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def annotation_path(self):
        value = self.path_input.text().strip()
        return Path(value).expanduser() if value else None


class PlaylistPanel(QWidget):
    close_requested = Signal()
    activated = Signal(int)
    add_videos = Signal()
    add_folder = Signal()
    open_annotations = Signal()
    previous = Signal()
    next_video = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.paths = []
        self.upload_states = {}
        self.current_path = None
        self.setMinimumWidth(240)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 0, 0, 0)
        header = QHBoxLayout()
        header.addWidget(QLabel("Playlist"))
        header.addStretch()
        self.close_button = QToolButton()
        self.close_button.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_TitleBarCloseButton))
        self.close_button.setToolTip("Hide playlist")
        self.close_button.setAccessibleName("Hide playlist")
        self.close_button.clicked.connect(self.close_requested.emit)
        header.addWidget(self.close_button)
        layout.addLayout(header)
        buttons = QHBoxLayout()
        for text, signal in (("+ Videos", self.add_videos), ("+ Folder", self.add_folder)):
            button = QPushButton(text)
            button.clicked.connect(signal.emit)
            buttons.addWidget(button)
        layout.addLayout(buttons)
        self.list = QListWidget()
        self.list.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.list.setTextElideMode(Qt.TextElideMode.ElideMiddle)
        self.list.setWordWrap(False)
        self.list.setUniformItemSizes(False)
        self.list.itemActivated.connect(lambda item: self.activated.emit(self.list.row(item)))
        layout.addWidget(self.list, 1)
        nav = QHBoxLayout()
        for text, signal in (("Previous", self.previous), ("Next", self.next_video)):
            button = QPushButton(text)
            button.clicked.connect(signal.emit)
            nav.addWidget(button)
        layout.addLayout(nav)
        self.auto_next = QCheckBox("Play next automatically")
        layout.addWidget(self.auto_next)
        annotations = QPushButton("Open Annotations…")
        annotations.clicked.connect(self.open_annotations.emit)
        layout.addWidget(annotations)
        self.annotation_label = QLabel("No video loaded")
        self.annotation_label.setTextFormat(Qt.TextFormat.PlainText)
        self.annotation_label.setWordWrap(True)
        layout.addWidget(self.annotation_label)

    STATUS_COLORS = {"success": "#3fb06e", "attention": "#d8a62e", "error": "#e0565b", "current": "#4f8ef7"}

    def add_paths(self, paths):
        if not hasattr(self, "upload_states"):
            self.upload_states, self.current_path = {}, None
        for path in paths:
            path = path.resolve()
            if path not in self.paths:
                self.paths.append(path)
                item = QListWidgetItem(path.name)
                item.setToolTip(str(path))
                self.list.addItem(item)
                self._render_item(len(self.paths) - 1)

    def set_current(self, path):
        if not hasattr(self, "upload_states"):
            self.upload_states, self.current_path = {}, None
        self.current_path = path
        if path in self.paths:
            self.list.setCurrentRow(self.paths.index(path))
        for index, item_path in enumerate(self.paths):
            item = self.list.item(index)
            font = item.font()
            font.setBold(item_path == path)
            item.setFont(font)
            self._render_item(index)

    def set_upload_state(self, path, outcome):
        """Remember the last submit answer for a video and show it as a status line."""
        if not hasattr(self, "upload_states"):
            self.upload_states, self.current_path = {}, None
        path = path.resolve() if hasattr(path, "resolve") else path
        self.upload_states[path] = outcome
        if path in self.paths:
            self._render_item(self.paths.index(path))

    def _render_item(self, index):
        path = self.paths[index]
        item = self.list.item(index)
        outcome = getattr(self, "upload_states", {}).get(path)
        if outcome is not None:
            status, tone = outcome.title, outcome.tone
            if tone == "success":
                status = "✓ " + status
            elif tone == "error":
                status = "✗ Submit failed — " + outcome.title
        elif path == getattr(self, "current_path", None):
            status, tone = "In progress", "current"
        else:
            status, tone = "", ""
        item.setText(path.name + ("\n" + status if status else ""))
        item.setToolTip(str(path) + ("\n" + status if status else ""))
        if tone in self.STATUS_COLORS:
            item.setData(Qt.ItemDataRole.UserRole, tone)
            item.setForeground(QColor(self.STATUS_COLORS[tone]) if tone != "current" else self.list.palette().text())
        else:
            item.setData(Qt.ItemDataRole.UserRole, None)
            item.setForeground(self.list.palette().text())

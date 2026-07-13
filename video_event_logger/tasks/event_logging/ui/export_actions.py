from PySide6.QtWidgets import QHBoxLayout, QPushButton, QWidget


class ExportActions(QWidget):
    def __init__(self) -> None:
        super().__init__()
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)
        self.finish_button = QPushButton("Finish & Save JSON")
        self.open_result_folder_button = QPushButton("Open result folder")
        layout.addWidget(self.finish_button)
        layout.addWidget(self.open_result_folder_button)
        layout.addStretch(1)

    def set_video_loaded(self, loaded: bool) -> None:
        self.finish_button.setEnabled(loaded)

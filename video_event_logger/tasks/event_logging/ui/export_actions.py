from PySide6.QtWidgets import QHBoxLayout, QPushButton, QWidget


class ExportActions(QWidget):
    def __init__(self) -> None:
        super().__init__()
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)
        self.save_now_button = QPushButton("Validate & Save JSON Now")
        self.save_now_button.setToolTip(
            "Validate the current annotations and immediately rewrite both JSON files."
        )
        self.open_result_folder_button = QPushButton("Open result folder")
        layout.addWidget(self.save_now_button)
        layout.addWidget(self.open_result_folder_button)
        layout.addStretch(1)

    def set_video_loaded(self, loaded: bool) -> None:
        self.save_now_button.setEnabled(loaded)

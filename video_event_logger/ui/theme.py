from PySide6.QtWidgets import QApplication


LIGHT_STYLE_SHEET = """
QWidget {
    color: #20262e;
    background-color: #f4f6f8;
}
QMainWindow, QDialog {
    background-color: #f4f6f8;
}
QFrame[frameShape="6"], QGroupBox {
    background-color: #ffffff;
    border: 1px solid #c8ced6;
    border-radius: 4px;
}
QGroupBox {
    margin-top: 8px;
    padding-top: 8px;
}
QGroupBox::title {
    subcontrol-origin: margin;
    left: 8px;
    padding: 0 3px;
}
QPushButton {
    background-color: #ffffff;
    border: 1px solid #aeb6c0;
    border-radius: 4px;
    padding: 3px 8px;
}
QPushButton:hover {
    background-color: #e9eef4;
    border-color: #7e8a98;
}
QPushButton:pressed {
    background-color: #dce4ec;
}
QPushButton:checked {
    color: #ffffff;
    background-color: #246fbd;
    border-color: #18558f;
    font-weight: 600;
}
QPushButton:disabled {
    color: #8d949c;
    background-color: #e9ecef;
    border-color: #cfd4d9;
}
QLineEdit, QTableWidget, QTextBrowser, QScrollArea {
    color: #20262e;
    background-color: #ffffff;
    border: 1px solid #b8c0ca;
    selection-background-color: #2878c8;
    selection-color: #ffffff;
}
QHeaderView::section {
    color: #20262e;
    background-color: #e7ebef;
    border: 0;
    border-right: 1px solid #c4cbd3;
    border-bottom: 1px solid #b8c0ca;
    padding: 4px;
}
QMenuBar, QMenu {
    color: #20262e;
    background-color: #f7f8fa;
}
QMenuBar::item:selected, QMenu::item:selected {
    background-color: #dce6f0;
}
QSlider::groove:horizontal {
    height: 5px;
    background: #c7cdd4;
    border-radius: 2px;
}
QSlider::handle:horizontal {
    width: 14px;
    margin: -5px 0;
    background: #246fbd;
    border: 1px solid #18558f;
    border-radius: 7px;
}
QSplitter::handle:vertical {
    background: #b8bfc7;
    margin: 2px 0;
}
QLabel#statusLabel {
    color: #555f6b;
}
QLabel#intervalStateLabel[feedbackState="ready"] {
    color: #626b75;
}
QLabel#intervalStateLabel[feedbackState="active"] {
    color: #5f4300;
    background: #fff3cd;
    border: 1px solid #d6a800;
    border-radius: 3px;
    padding: 2px 6px;
    font-weight: 600;
}
QPushButton[feedbackState="start-set"] {
    background: #fff3cd;
    color: #5f4300;
    border: 1px solid #d6a800;
    font-weight: 600;
}
QPushButton[feedbackState="finish-ready"] {
    background: #e4f4e9;
    color: #145c2e;
    border: 1px solid #62a978;
    font-weight: 600;
}
QPushButton[actionRole="play"] {
    background: #eaf4ee;
    color: #163b25;
    border-color: #9bb9a7;
}
QPushButton[actionRole="edit"] {
    background: #f3eee3;
    color: #4a3520;
    border-color: #b9aa92;
}
QPushButton[actionRole="delete"] {
    background: #f5eded;
    color: #5a1d1d;
    border-color: #c8a4a4;
}
QToolTip {
    color: #20262e;
    background-color: #fffbe6;
    border: 1px solid #8f969e;
}
"""


DARK_STYLE_SHEET = """
QWidget {
    color: #e6e9ed;
    background-color: #20252b;
}
QMainWindow, QDialog {
    background-color: #20252b;
}
QFrame[frameShape="6"], QGroupBox {
    background-color: #272d34;
    border: 1px solid #4b5561;
    border-radius: 4px;
}
QGroupBox {
    margin-top: 8px;
    padding-top: 8px;
}
QGroupBox::title {
    subcontrol-origin: margin;
    left: 8px;
    padding: 0 3px;
}
QPushButton {
    color: #e6e9ed;
    background-color: #323a43;
    border: 1px solid #5b6672;
    border-radius: 4px;
    padding: 3px 8px;
}
QPushButton:hover {
    background-color: #3d4752;
    border-color: #85919e;
}
QPushButton:pressed {
    background-color: #485563;
}
QPushButton:checked {
    color: #ffffff;
    background-color: #2f83d5;
    border-color: #79b8f2;
    font-weight: 600;
}
QPushButton:disabled {
    color: #818a94;
    background-color: #2a3037;
    border-color: #424a53;
}
QLineEdit, QTableWidget, QTextBrowser, QScrollArea {
    color: #e6e9ed;
    background-color: #181c21;
    border: 1px solid #535e69;
    selection-background-color: #2f83d5;
    selection-color: #ffffff;
}
QTableWidget {
    gridline-color: #3f4852;
    alternate-background-color: #222830;
}
QHeaderView::section {
    color: #e6e9ed;
    background-color: #303740;
    border: 0;
    border-right: 1px solid #4b5561;
    border-bottom: 1px solid #596470;
    padding: 4px;
}
QMenuBar, QMenu {
    color: #e6e9ed;
    background-color: #252b32;
}
QMenuBar::item:selected, QMenu::item:selected {
    background-color: #3a4550;
}
QSlider::groove:horizontal {
    height: 5px;
    background: #4a535d;
    border-radius: 2px;
}
QSlider::handle:horizontal {
    width: 14px;
    margin: -5px 0;
    background: #4b9ae8;
    border: 1px solid #8cc5ff;
    border-radius: 7px;
}
QSplitter::handle:vertical {
    background: #515b66;
    margin: 2px 0;
}
QLabel#statusLabel {
    color: #b6bec7;
}
QLabel#intervalStateLabel[feedbackState="ready"] {
    color: #aeb6bf;
}
QLabel#intervalStateLabel[feedbackState="active"] {
    color: #ffe3a3;
    background: #594716;
    border: 1px solid #d6a800;
    border-radius: 3px;
    padding: 2px 6px;
    font-weight: 600;
}
QPushButton[feedbackState="start-set"] {
    background: #594716;
    color: #ffe3a3;
    border: 1px solid #d6a800;
    font-weight: 600;
}
QPushButton[feedbackState="finish-ready"] {
    background: #234b32;
    color: #b9f1cb;
    border: 1px solid #62a978;
    font-weight: 600;
}
QPushButton[actionRole="play"] {
    background: #254535;
    color: #ccebd7;
    border-color: #5b9270;
}
QPushButton[actionRole="edit"] {
    background: #4b3e29;
    color: #f0dfbe;
    border-color: #917c5c;
}
QPushButton[actionRole="delete"] {
    background: #512f33;
    color: #f3c9cc;
    border-color: #9b6268;
}
QToolTip {
    color: #f2f3f5;
    background-color: #303740;
    border: 1px solid #727d89;
}
"""


def apply_theme(application: QApplication, dark_mode: bool) -> None:
    application.setStyleSheet(DARK_STYLE_SHEET if dark_mode else LIGHT_STYLE_SHEET)

"""Application look: one stylesheet template filled with dark or bright tokens.

Dark is the default (video review work); Bright stays available from
View → Appearance. Widgets opt into roles with objectName / dynamic
properties (primaryButton, tone, kind, actionRole, feedbackState…).
"""
from PySide6.QtWidgets import QApplication

DARK_TOKENS = {
    "bg": "#0f1115", "surface": "#161a21", "surface2": "#1d222b", "surface3": "#252b36",
    "border": "#2c323d", "border_strong": "#3a414d", "text": "#e6e8ec", "muted": "#9aa3b2",
    "subtle": "#7d8696", "input": "#0f1217", "accent": "#3b7bf6", "accent_hover": "#4a86f7",
    "accent_text": "#ffffff", "accent_soft": "#1f2a3d", "accent_soft_text": "#cfe0ff",
    "success_bg": "#16301f", "success_fg": "#7ee2a8", "success_border": "#2f8f55",
    "attention_bg": "#2b2412", "attention_fg": "#f5dfa6", "attention_border": "#6b5520",
    "error_bg": "#33161a", "error_fg": "#ffb3b6", "error_border": "#7a2a30",
    "unpack_bg": "#2a2238", "unpack_fg": "#d7b8ff",
    "rec": "#ff5a5f", "rec_bg": "#2a1215", "rec_fg": "#ffe1e2", "rec_dark": "#1a0507",
    "tooltip_bg": "#252b36",
}

LIGHT_TOKENS = {
    "bg": "#f4f6f8", "surface": "#ffffff", "surface2": "#f0f2f5", "surface3": "#e4e8ee",
    "border": "#d3d9e0", "border_strong": "#b8c0ca", "text": "#1d232b", "muted": "#59626e",
    "subtle": "#6d7682", "input": "#ffffff", "accent": "#2563d9", "accent_hover": "#1f56bf",
    "accent_text": "#ffffff", "accent_soft": "#e3ecfd", "accent_soft_text": "#173d82",
    "success_bg": "#e4f4e9", "success_fg": "#145c2e", "success_border": "#62a978",
    "attention_bg": "#fff3cd", "attention_fg": "#5f4300", "attention_border": "#d6a800",
    "error_bg": "#fbe9ea", "error_fg": "#8a1c24", "error_border": "#d66a73",
    "unpack_bg": "#efe6fb", "unpack_fg": "#5b2d91",
    "rec": "#d93a40", "rec_bg": "#fdecec", "rec_fg": "#7a1116", "rec_dark": "#ffffff",
    "tooltip_bg": "#fffbe6",
}

TEMPLATE = """
QWidget { color: {text}; background-color: {bg}; }
QMainWindow, QDialog { background-color: {bg}; }
QFrame[frameShape="6"], QGroupBox { background-color: {surface}; border: 1px solid {border}; border-radius: 8px; }
QGroupBox { margin-top: 8px; padding-top: 8px; }
QGroupBox::title { subcontrol-origin: margin; left: 8px; padding: 0 3px; }
QPushButton, QToolButton {
    color: {text}; background-color: {surface2}; border: 1px solid {border};
    border-radius: 7px; padding: 5px 11px;
}
QPushButton:hover, QToolButton:hover { background-color: {surface3}; border-color: {border_strong}; }
QPushButton:pressed { background-color: {surface3}; }
QPushButton:checked { color: {accent_text}; background-color: {accent}; border-color: {accent}; font-weight: 600; }
QPushButton:disabled { color: {subtle}; background-color: {surface}; border-color: {border}; }
QPushButton:default { border-color: {accent}; }
QPushButton#primaryButton, QPushButton#submitButton {
    color: {accent_text}; background-color: {accent}; border: 1px solid {accent}; font-weight: 600;
}
QPushButton#primaryButton:hover, QPushButton#submitButton:hover { background-color: {accent_hover}; }
QPushButton#primaryButton:disabled, QPushButton#submitButton:disabled { color: {subtle}; background-color: {surface2}; border-color: {border}; }
QPushButton#dangerButton { color: {error_fg}; }
QPushButton#typeChip { border-radius: 13px; padding: 3px 10px; }
QPushButton#typeChip:checked { color: {text}; background-color: {accent_soft}; border-color: {accent}; }
QLineEdit, QPlainTextEdit, QTextEdit, QDoubleSpinBox, QSpinBox, QTableWidget, QTextBrowser, QScrollArea, QListWidget {
    color: {text}; background-color: {input}; border: 1px solid {border}; border-radius: 6px;
    selection-background-color: {accent}; selection-color: {accent_text};
}
QLineEdit:focus, QPlainTextEdit:focus, QTextEdit:focus, QDoubleSpinBox:focus, QSpinBox:focus { border-color: {accent}; }
QTableWidget { gridline-color: {border}; alternate-background-color: {surface}; }
QTableWidget::item:selected, QListWidget::item:selected { background-color: {accent_soft}; color: {text}; }
QListWidget::item { padding: 5px 4px; }
QHeaderView::section {
    color: {muted}; background-color: {surface}; border: 0; border-bottom: 1px solid {border};
    padding: 5px; font-weight: 600;
}
QTabBar::tab { background: transparent; color: {muted}; padding: 8px 12px; border: 0; }
QTabBar::tab:selected { color: {text}; border-bottom: 2px solid {accent}; font-weight: 600; }
QMenuBar, QMenu { color: {text}; background-color: {surface}; }
QMenuBar::item:selected, QMenu::item:selected { background-color: {accent_soft}; }
QStatusBar { background-color: {surface}; border-top: 1px solid {border}; }
QStatusBar QLabel { background: transparent; }
QSlider { background: transparent; }
QSlider::groove:horizontal { height: 4px; background: {border_strong}; border-radius: 2px; }
QSlider::sub-page:horizontal { background: {accent}; border-radius: 2px; }
QSlider::handle:horizontal { width: 14px; margin: -5px 0; background: #ffffff; border: 1px solid {accent}; border-radius: 7px; }
QProgressBar { background-color: {input}; border: 0; border-radius: 3px; text-align: center; }
QProgressBar::chunk { background-color: {accent}; border-radius: 3px; }
QSplitter::handle { background: {bg}; }
QSplitter::handle:vertical { margin: 2px 0; }
QCheckBox { background: transparent; }
QToolTip { color: {text}; background-color: {tooltip_bg}; border: 1px solid {border_strong}; }

QFrame#headerBar { background-color: {surface}; border: 0; border-bottom: 1px solid {border}; border-radius: 0; }
QFrame#headerBar QLabel { background: transparent; }
QLabel#videoTitle { font-size: 15px; font-weight: 600; }
QLabel#videoSubtitle, QLabel#dialogHint, QLabel#statCaption, QLabel#shortcutStrip, QLabel#sectionCaption { color: {muted}; background: transparent; }
QLabel#shortcutStrip { font-size: 11px; }
QLabel#statusLabel { color: {muted}; }
QFrame#controlCard, QFrame#detailsCard { background-color: {surface}; border: 1px solid {border}; border-radius: 10px; }
QFrame#controlCard QLabel, QFrame#detailsCard QLabel { background: transparent; }
QFrame#segmented { background-color: {surface2}; border: 1px solid {border}; border-radius: 8px; }
QFrame#segmented QPushButton { border: 0; background: transparent; padding: 4px 9px; }
QFrame#segmented QPushButton:hover { background: {surface3}; }
QFrame#segmented QPushButton:checked { background: {accent}; color: {accent_text}; }
QLabel#emptyHint { color: {muted}; border: 1px dashed {border_strong}; border-radius: 10px; padding: 14px; background: transparent; }

QLabel#intervalStateLabel { background: transparent; }
QLabel#intervalStateLabel[feedbackState="ready"] { color: {muted}; }
QLabel#intervalStateLabel[feedbackState="active"] {
    color: {rec_fg}; background: {rec_bg}; border: 1px solid {rec}; border-radius: 6px; padding: 3px 8px; font-weight: 600;
}
QPushButton#startButton { color: {rec_fg}; background: {rec_bg}; border: 1px solid {rec}; font-weight: 600; padding: 7px 16px; }
QPushButton#startButton[feedbackState="start-set"] { color: {muted}; background: {surface2}; border-color: {border}; }
QPushButton#endButton { font-weight: 600; padding: 7px 16px; }
QPushButton#endButton[feedbackState="finish-ready"] { color: {rec_dark}; background: {rec}; border: 1px solid {rec}; }
QPushButton#cancelIntervalButton { padding: 7px 12px; }
QPushButton[actionRole="play"], QPushButton[actionRole="edit"], QPushButton[actionRole="delete"] {
    padding: 2px 0; border-radius: 6px; background: transparent; border: 1px solid transparent;
}
QPushButton[actionRole="play"]:hover, QPushButton[actionRole="edit"]:hover { background: {surface3}; border-color: {border}; }
QPushButton[actionRole="delete"]:hover { background: {error_bg}; color: {error_fg}; border-color: {error_border}; }

QLabel#dialogTitle { font-size: 17px; font-weight: 600; background: transparent; }
QLabel#dialogSubtitle { color: {muted}; font-family: Menlo, "DejaVu Sans Mono", monospace; background: transparent; }
QFrame#statTile { background-color: {surface2}; border: 0; border-radius: 10px; }
QLabel#statValue { font-size: 20px; font-weight: 600; background: transparent; }
QLabel#typeChip { background-color: {surface2}; border: 1px solid {border}; border-radius: 11px; padding: 3px 9px; }
QLabel#warningBox, QLabel#downloadMessage[tone="attention"] {
    color: {attention_fg}; background-color: {attention_bg}; border: 1px solid {attention_border}; border-radius: 8px; padding: 8px 10px;
}
QLabel#downloadMessage[tone="error"] {
    color: {error_fg}; background-color: {error_bg}; border: 1px solid {error_border}; border-radius: 8px; padding: 8px 10px;
}
QFrame#noEventsBox { background-color: {surface2}; border: 0; border-radius: 10px; }
QFrame#noEventsBox QLabel { background: transparent; }
QLabel#noEventsTitle { font-weight: 600; font-size: 15px; }
QLabel#resultIcon { border-radius: 22px; font-size: 20px; font-weight: 700; }
QLabel#resultIcon[tone="success"] { color: {success_fg}; background: {success_bg}; }
QLabel#resultIcon[tone="attention"] { color: {attention_fg}; background: {attention_bg}; }
QLabel#resultIcon[tone="error"] { color: {error_fg}; background: {error_bg}; }
QLabel#resultIcon[tone="canceled"] { color: {muted}; background: {surface2}; }
QLabel#resultLead { color: {text}; background: transparent; }
QLabel#messageBox {
    font-family: Menlo, "DejaVu Sans Mono", monospace; background-color: {input};
    border: 1px solid {border}; border-radius: 8px; padding: 9px 11px;
}

QFrame#downloadCard { background-color: {surface}; border: 1px solid {border}; border-radius: 12px; }
QFrame#downloadCard[tone="attention"] { border-color: {attention_border}; }
QFrame#downloadCard[tone="error"] { border-color: {error_border}; }
QFrame#downloadCard QLabel { background: transparent; }
QWidget#downloadCards { background: transparent; }
QLabel#downloadName { font-weight: 600; }
QLabel#downloadDetail { color: {muted}; font-family: Menlo, "DejaVu Sans Mono", monospace; }
QLabel#downloadIcon { border-radius: 8px; font-size: 15px; background: {accent_soft}; color: {accent_soft_text}; }
QLabel#downloadIcon[kind="archive"], QLabel#kindBadge[kind="archive"] { background: {unpack_bg}; color: {unpack_fg}; }
QLabel#kindBadge { font-size: 11px; font-weight: 600; border-radius: 4px; padding: 1px 6px; background: {accent_soft}; color: {accent_soft_text}; }
QLabel#kindBadge[kind="unknown"], QLabel#downloadIcon[kind="unknown"] { background: {surface3}; color: {muted}; }
QLabel#statePill { font-size: 12px; font-weight: 600; border-radius: 10px; padding: 3px 10px; background: {surface3}; color: {muted}; }
QLabel#statePill[tone="info"] { background: {accent_soft}; color: {accent_soft_text}; }
QLabel#statePill[tone="unpack"] { background: {unpack_bg}; color: {unpack_fg}; }
QLabel#statePill[tone="success"] { background: {success_bg}; color: {success_fg}; }
QLabel#statePill[tone="attention"] { background: {attention_bg}; color: {attention_fg}; }
QLabel#statePill[tone="error"] { background: {error_bg}; color: {error_fg}; }
QLabel#linkPreview { background-color: {surface2}; border-radius: 8px; padding: 8px 10px; }
"""


def build_style_sheet(tokens):
    sheet = TEMPLATE
    for key, value in tokens.items():
        sheet = sheet.replace("{%s}" % key, value)
    return sheet


DARK_STYLE_SHEET = build_style_sheet(DARK_TOKENS)
LIGHT_STYLE_SHEET = build_style_sheet(LIGHT_TOKENS)


def apply_theme(application: QApplication, dark_mode: bool) -> None:
    application.setStyleSheet(DARK_STYLE_SHEET if dark_mode else LIGHT_STYLE_SHEET)

from typing import Optional

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QIcon, QPainter, QPen, QPixmap
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QVBoxLayout,
    QWidget,
)

from video_event_logger.services.annotation_api import validate_api_settings


class ApiSettingsDialog(QDialog):
    def __init__(
        self,
        endpoint_url: str,
        token: str,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Connection Settings")
        self.setModal(True)
        self.setMinimumWidth(780)

        layout = QVBoxLayout(self)
        description = QLabel(
            "Configure the endpoint used to upload the current annotations JSON. "
            "These values are stored locally on this computer."
        )
        description.setWordWrap(True)
        layout.addWidget(description)

        form = QFormLayout()
        self.endpoint_input = QLineEdit(endpoint_url)
        self.endpoint_input.setPlaceholderText(
            "https://example.org/api/v1/annotations"
        )
        self.endpoint_input.setMaxLength(2048)
        self.endpoint_input.setMinimumWidth(620)
        self.endpoint_input.setClearButtonEnabled(True)
        form.addRow("Upload endpoint URL:", self.endpoint_input)

        self.token_input = QLineEdit(token)
        self.token_input.setEchoMode(QLineEdit.EchoMode.Password)
        self.token_input.setPlaceholderText("Access token")
        self.token_input.setClearButtonEnabled(True)
        self.token_visibility_action = self.token_input.addAction(
            self._visibility_icon(False),
            QLineEdit.ActionPosition.TrailingPosition,
        )
        self.token_visibility_action.triggered.connect(
            self._toggle_token_visibility
        )
        self._sync_token_visibility_action(False)
        form.addRow("Token:", self.token_input)
        layout.addLayout(form)

        auth_hint = QLabel("Authorization header: TokenAuth &lt;token&gt;")
        auth_hint.setStyleSheet("color: palette(mid);")
        layout.addWidget(auth_hint)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save
            | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def endpoint_url(self) -> str:
        return self.endpoint_input.text().strip()

    def token(self) -> str:
        return self.token_input.text().strip()

    def _toggle_token_visibility(self) -> None:
        visible = self.token_input.echoMode() != QLineEdit.EchoMode.Normal
        self.token_input.setEchoMode(
            QLineEdit.EchoMode.Normal
            if visible
            else QLineEdit.EchoMode.Password
        )
        self._sync_token_visibility_action(visible)

    def _sync_token_visibility_action(self, visible: bool) -> None:
        action_text = "Hide token" if visible else "Show token"
        self.token_visibility_action.setText(action_text)
        self.token_visibility_action.setToolTip(action_text)
        self.token_visibility_action.setIcon(self._visibility_icon(visible))

    def _visibility_icon(self, visible: bool) -> QIcon:
        pixel_ratio = self.devicePixelRatioF()
        pixmap = QPixmap(
            int(20 * pixel_ratio),
            int(20 * pixel_ratio),
        )
        pixmap.setDevicePixelRatio(pixel_ratio)
        pixmap.fill(Qt.GlobalColor.transparent)

        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        color = self.token_input.palette().color(
            self.token_input.foregroundRole()
        )
        color = QColor(color)
        color.setAlpha(210)
        pen = QPen(color, 1.6)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawEllipse(3, 6, 14, 8)
        painter.drawEllipse(8, 8, 4, 4)
        if visible:
            painter.drawLine(4, 16, 16, 4)
        painter.end()
        return QIcon(pixmap)

    def accept(self) -> None:
        validation_error = validate_api_settings(self.endpoint_url(), self.token())
        if validation_error is not None:
            QMessageBox.warning(self, "Invalid API settings", validation_error)
            return
        super().accept()

from PySide6.QtCore import QEvent, QSettings, QSignalBlocker, QTime
from PySide6.QtGui import QAction, QActionGroup, QKeySequence
from PySide6.QtWidgets import QApplication, QDialog, QLabel, QMainWindow

from video_event_logger.app_config import APP_NAME, APP_VERSION
from video_event_logger.tasks.event_logging.controller import EventLoggingController
from video_event_logger.tasks.event_logging.ui.workspace import EventLoggingWorkspace
from video_event_logger.ui.api_settings_dialog import ApiSettingsDialog
from video_event_logger.ui.theme import apply_theme


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.settings = QSettings("VideoEventLogger", APP_NAME)
        self.dark_mode_enabled = self._setting_is_true(
            self.settings.value("appearance/dark_mode", False)
        )
        self.show_popup_after_interval_enabled = self._setting_is_true(
            self.settings.value("annotation/show_popup_after_interval", True)
        )
        self.fullscreen_progress_bar_always_on = self._setting_is_true(
            self.settings.value("appearance/fullscreen_progress_bar_always_on", False)
        )
        self.api_endpoint_url = str(
            self.settings.value("api/endpoint_url", "") or ""
        ).strip()
        self.api_access_token = str(
            self.settings.value("api/access_token", "") or ""
        ).strip()
        self.video_fullscreen_enabled = False
        self.was_maximized_before_fullscreen = False
        self.setWindowTitle("%s v%s" % (APP_NAME, APP_VERSION))
        self.resize(1180, 820)

        self.workspace = EventLoggingWorkspace(self)
        self.setCentralWidget(self.workspace)
        self._build_status_bar()
        self.controller = EventLoggingController(self, self.workspace)
        self._build_menu_bar()
        self.workspace.video_player.fullscreen_toggle_requested.connect(self.toggle_fullscreen)
        self.set_show_popup_after_interval(self.show_popup_after_interval_enabled)
        self.set_fullscreen_progress_bar_always_on(self.fullscreen_progress_bar_always_on)
        self.set_dark_mode(self.dark_mode_enabled)
        self.set_video_fullscreen_available(False)
        self.set_file_actions_video_loaded(False)
        self.set_annotation_file_available(False)
        self.set_api_upload_available(False)
        self._sync_fullscreen_controls(False)

    def _build_menu_bar(self) -> None:
        self.file_menu = self.menuBar().addMenu("&File")
        self.open_video_action = QAction("Open Video…", self)
        self.open_video_action.setShortcut(QKeySequence.StandardKey.Open)
        self.open_video_action.setStatusTip("Open an MP4 or MKV video")
        self.open_video_action.triggered.connect(self.controller.open_video_file)
        self.file_menu.addAction(self.open_video_action)

        self.file_menu.addSeparator()
        self.validate_save_action = QAction("Validate & Save Annotations", self)
        self.validate_save_action.setShortcut(QKeySequence.StandardKey.Save)
        self.validate_save_action.setStatusTip(
            "Validate the annotations and retry the atomic JSON save"
        )
        self.validate_save_action.triggered.connect(self.controller.validate_and_save)
        self.file_menu.addAction(self.validate_save_action)

        self.show_annotation_file_action = QAction(
            "Show Annotation File in Folder",
            self,
        )
        self.show_annotation_file_action.setStatusTip(
            "Open the folder containing the annotation JSON"
        )
        self.show_annotation_file_action.triggered.connect(
            self.controller.show_annotation_file_in_folder
        )
        self.file_menu.addAction(self.show_annotation_file_action)

        self.file_menu.addSeparator()
        self.upload_annotations_action = QAction("Upload Annotations…", self)
        self.upload_annotations_action.setStatusTip(
            "Upload the current annotation JSON to the configured connection"
        )
        self.upload_annotations_action.triggered.connect(
            self.controller.upload_annotations
        )
        self.file_menu.addAction(self.upload_annotations_action)

        self.file_menu.addSeparator()
        self.quit_action = QAction("Quit", self)
        self.quit_action.setShortcut(QKeySequence.StandardKey.Quit)
        self.quit_action.triggered.connect(self.close)
        self.file_menu.addAction(self.quit_action)

        self.view_menu = self.menuBar().addMenu("&View")
        self.fullscreen_action = QAction("Video Full Screen", self)
        self.fullscreen_action.setCheckable(True)
        self.fullscreen_action.setShortcut(QKeySequence("F11"))
        self.fullscreen_action.setStatusTip("Show only the video in full-screen mode")
        self.fullscreen_action.toggled.connect(self.set_fullscreen)
        self.view_menu.addAction(self.fullscreen_action)

        self.fullscreen_progress_bar_action = QAction(
            "Fullscreen progress bar always ON", self
        )
        self.fullscreen_progress_bar_action.setCheckable(True)
        self.fullscreen_progress_bar_action.setStatusTip(
            "Keep the full screen control bar visible instead of hiding it after 3 seconds"
        )
        self.fullscreen_progress_bar_action.toggled.connect(
            self.set_fullscreen_progress_bar_always_on
        )
        self.view_menu.addAction(self.fullscreen_progress_bar_action)

        self.rotation_menu = self.view_menu.addMenu("Video rotation")
        self.rotation_action_group = QActionGroup(self)
        self.rotation_action_group.setExclusive(True)
        self.rotation_actions = {}
        for degrees in (0, 90, 180, 270):
            action = QAction("%d°" % degrees, self)
            action.setCheckable(True)
            action.triggered.connect(
                lambda checked=False, selected_degrees=degrees: self.controller.set_video_rotation(
                    selected_degrees
                )
            )
            self.rotation_action_group.addAction(action)
            self.rotation_menu.addAction(action)
            self.rotation_actions[degrees] = action
        self.video_rotation_menu_action = self.rotation_menu.menuAction()
        self.set_video_rotation_degrees(0)
        self.set_video_rotation_available(False)

        self.view_menu.addSeparator()

        self.interval_popup_action = QAction("Show Interval Details Popup", self)
        self.interval_popup_action.setCheckable(True)
        self.interval_popup_action.setStatusTip(
            "Confirm event_type and add a comment before saving each interval"
        )
        self.interval_popup_action.toggled.connect(self.set_show_popup_after_interval)
        self.view_menu.addAction(self.interval_popup_action)

        self.view_menu.addSeparator()

        self.view_mode_menu = self.view_menu.addMenu("View mode")
        self.view_mode_action_group = QActionGroup(self)
        self.view_mode_action_group.setExclusive(True)

        self.bright_mode_action = QAction("Bright", self)
        self.bright_mode_action.setCheckable(True)
        self.bright_mode_action.setStatusTip("Use the bright appearance")
        self.bright_mode_action.triggered.connect(
            lambda checked=False: self.set_dark_mode(False)
        )
        self.view_mode_action_group.addAction(self.bright_mode_action)
        self.view_mode_menu.addAction(self.bright_mode_action)

        self.dark_mode_action = QAction("Dark", self)
        self.dark_mode_action.setCheckable(True)
        self.dark_mode_action.setStatusTip("Use the dark appearance")
        self.dark_mode_action.triggered.connect(
            lambda checked=False: self.set_dark_mode(True)
        )
        self.view_mode_action_group.addAction(self.dark_mode_action)
        self.view_mode_menu.addAction(self.dark_mode_action)

        self.connection_menu = self.menuBar().addMenu("&Connection")
        self.connection_settings_action = QAction("Settings…", self)
        self.connection_settings_action.setStatusTip(
            "Configure the annotation upload endpoint and access token"
        )
        self.connection_settings_action.triggered.connect(
            self.show_connection_settings
        )
        self.connection_menu.addAction(self.connection_settings_action)

        self.help_menu = self.menuBar().addMenu("&Help")
        self.annotator_guide_action = self.help_menu.addAction("Annotator Guide")
        self.annotator_guide_action.setStatusTip(
            "Show keyboard shortcuts and annotation workflow"
        )
        self.annotator_guide_action.triggered.connect(self.controller.show_help)

    def _build_status_bar(self) -> None:
        self.save_state_label = QLabel()
        self.save_state_label.setObjectName("saveStateLabel")
        self.save_state_label.setMinimumWidth(170)
        self.statusBar().addPermanentWidget(self.save_state_label)
        self.set_save_state("missing")

    def set_fullscreen(self, enabled: bool) -> None:
        if enabled and not self.fullscreen_action.isEnabled():
            self._sync_fullscreen_controls(False)
            return
        if enabled == self.video_fullscreen_enabled:
            self._sync_fullscreen_controls(enabled)
            return
        self.video_fullscreen_enabled = enabled
        if enabled:
            self.was_maximized_before_fullscreen = self.isMaximized()
            self._set_video_only_chrome(True)
            self.showFullScreen()
        else:
            self._set_video_only_chrome(False)
            if self.was_maximized_before_fullscreen:
                self.showMaximized()
            else:
                self.showNormal()
        self._sync_fullscreen_controls(enabled)

    def toggle_fullscreen(self) -> None:
        self.set_fullscreen(not self.video_fullscreen_enabled)

    def set_video_fullscreen_available(self, available: bool) -> None:
        if hasattr(self, "fullscreen_action"):
            self.fullscreen_action.setEnabled(available)
        if not available and self.video_fullscreen_enabled:
            self.set_fullscreen(False)

    def set_file_actions_video_loaded(self, loaded: bool) -> None:
        if hasattr(self, "validate_save_action"):
            self.validate_save_action.setEnabled(loaded)

    def set_annotation_file_available(self, available: bool) -> None:
        if hasattr(self, "show_annotation_file_action"):
            self.show_annotation_file_action.setEnabled(available)

    def set_api_upload_available(self, available: bool) -> None:
        if hasattr(self, "upload_annotations_action"):
            self.upload_annotations_action.setEnabled(available)

    def api_connection_settings(self):  # type: ignore[no-untyped-def]
        return self.api_endpoint_url, self.api_access_token

    def show_connection_settings(self) -> None:
        dialog = ApiSettingsDialog(
            self.api_endpoint_url,
            self.api_access_token,
            self,
        )
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        self.api_endpoint_url = dialog.endpoint_url()
        self.api_access_token = dialog.token()
        self.settings.setValue("api/endpoint_url", self.api_endpoint_url)
        self.settings.setValue("api/access_token", self.api_access_token)
        self.settings.sync()
        self.show_status_message("API settings saved")

    def set_video_rotation_available(self, available: bool) -> None:
        if hasattr(self, "video_rotation_menu_action"):
            self.video_rotation_menu_action.setEnabled(available)

    def set_video_rotation_degrees(self, degrees: int) -> None:
        if not hasattr(self, "rotation_actions"):
            return
        normalized = degrees % 360
        action = self.rotation_actions.get(normalized)
        if action is not None:
            self._sync_checked_state(action, True)

    def set_dark_mode(self, enabled: bool) -> None:
        self.dark_mode_enabled = enabled
        application = QApplication.instance()
        if application is not None:
            apply_theme(application, enabled)
        self.settings.setValue("appearance/dark_mode", enabled)
        self._sync_checked_state(self.bright_mode_action, not enabled)
        self._sync_checked_state(self.dark_mode_action, enabled)

    def set_show_popup_after_interval(self, enabled: bool) -> None:
        self.show_popup_after_interval_enabled = enabled
        self.workspace.set_show_popup_after_interval(enabled)
        self.settings.setValue("annotation/show_popup_after_interval", enabled)
        if hasattr(self, "interval_popup_action"):
            self._sync_checked_state(self.interval_popup_action, enabled)

    def set_fullscreen_progress_bar_always_on(self, enabled: bool) -> None:
        self.fullscreen_progress_bar_always_on = enabled
        self.workspace.video_player.set_fullscreen_hud_controls_always_visible(enabled)
        self.settings.setValue("appearance/fullscreen_progress_bar_always_on", enabled)
        if hasattr(self, "fullscreen_progress_bar_action"):
            self._sync_checked_state(self.fullscreen_progress_bar_action, enabled)

    def set_save_state(self, state: str) -> None:
        appearances = {
            "missing": ("No video loaded", "#6d747c"),
            "dirty": ("Unsaved changes", "#9a6a00"),
            "saving": ("Saving…", "#9a6a00"),
            "failed": ("Save failed — use Ctrl/Cmd+S to retry", "#c62828"),
        }
        if state == "saved":
            text = "✓ Saved · %s" % QTime.currentTime().toString("HH:mm:ss")
            color = "#1c9c4a"
        else:
            text, color = appearances.get(state, appearances["missing"])
        self.save_state_label.setText(text)
        self.save_state_label.setToolTip(text)
        self.save_state_label.setStyleSheet(
            "font-weight: 600; padding: 0 6px; color: %s;" % color
        )

    def show_status_message(self, text: str) -> None:
        self.statusBar().showMessage(text.strip(), 4000)

    def changeEvent(self, event: QEvent) -> None:
        super().changeEvent(event)
        if event.type() == QEvent.Type.WindowStateChange and hasattr(self, "fullscreen_action"):
            if self.video_fullscreen_enabled and not self.isFullScreen():
                self.video_fullscreen_enabled = False
                self._set_video_only_chrome(False)
            self._sync_fullscreen_controls(self.video_fullscreen_enabled)

    def _set_video_only_chrome(self, enabled: bool) -> None:
        self.menuBar().setVisible(not enabled)
        self.statusBar().setVisible(not enabled)
        self.workspace.set_video_fullscreen(enabled)

    def _sync_fullscreen_controls(self, enabled: bool) -> None:
        self._sync_checked_state(self.fullscreen_action, enabled)

    @staticmethod
    def _sync_checked_state(control, enabled: bool) -> None:  # type: ignore[no-untyped-def]
        blocker = QSignalBlocker(control)
        control.setChecked(enabled)
        del blocker

    @staticmethod
    def _setting_is_true(value) -> bool:  # type: ignore[no-untyped-def]
        if isinstance(value, bool):
            return value
        return str(value).strip().lower() in ("1", "true", "yes", "on")

    def closeEvent(self, event) -> None:  # type: ignore[no-untyped-def]
        self.controller.close_event(event)

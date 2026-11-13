from pathlib import Path
import time

from PySide6.QtCore import Qt, QTimer, Signal, Slot
from PySide6.QtWidgets import (
    QCheckBox, QDialog, QFileDialog, QFrame, QHBoxLayout, QLabel, QLineEdit,
    QMessageBox, QPlainTextEdit, QProgressBar, QPushButton, QScrollArea, QSpinBox,
    QVBoxLayout, QWidget,
)

from video_event_logger.services.file_manager import show_file_in_folder
from video_event_logger.services.video_download import (
    DownloadError, link_format, link_kind, suggested_video_name, validate_download_url,
)


def format_bytes(value):
    for unit in ("B", "KiB", "MiB", "GiB", "TiB"):
        if value < 1024 or unit == "TiB":
            return "%.1f %s" % (value, unit)
        value /= 1024


def format_eta(seconds):
    seconds = int(max(0, seconds))
    if seconds < 60:
        return "%d s" % seconds
    if seconds < 3600:
        return "%d min" % round(seconds / 60)
    return "%d h %d min" % (seconds // 3600, seconds % 3600 // 60)


STATE_LABELS = {
    "queued": "Queued", "running": "Downloading", "waiting": "Waiting for network",
    "expired": "Link expired", "completed": "Ready", "failed": "Failed",
    "cancelled": "Cancelled", "cancelling": "Cancelling",
}


def _label(text="", name="", wrap=False):
    label = QLabel(text)
    label.setTextFormat(Qt.TextFormat.PlainText)
    if name:
        label.setObjectName(name)
    label.setWordWrap(wrap)
    return label


def _repolish(widget):
    widget.style().unpolish(widget)
    widget.style().polish(widget)


def kind_badge_text(kind, url_format=""):
    if kind == "archive":
        return "%s archive" % url_format if url_format and url_format not in ("MP4", "MKV") else "Archive"
    if kind == "video":
        return "%s video" % url_format if url_format in ("MP4", "MKV") else "Video"
    return "Unknown type"


class DownloadCard(QFrame):
    """One queued download: name, type, steps, progress, message and its actions."""

    def __init__(self, dialog):
        super().__init__()
        self.dialog = dialog
        self.job = None
        self.setObjectName("downloadCard")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 12, 14, 12)
        layout.setSpacing(8)

        head = QHBoxLayout()
        head.setSpacing(12)
        self.icon = _label("", "downloadIcon")
        self.icon.setFixedSize(36, 36)
        self.icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        head.addWidget(self.icon)
        texts = QVBoxLayout()
        texts.setSpacing(2)
        title_row = QHBoxLayout()
        self.name_label = _label("", "downloadName")
        self.kind_label = _label("", "kindBadge")
        title_row.addWidget(self.name_label, 1)
        title_row.addWidget(self.kind_label)
        texts.addLayout(title_row)
        self.steps_label = QLabel()
        self.steps_label.setObjectName("downloadSteps")
        self.steps_label.setTextFormat(Qt.TextFormat.RichText)
        texts.addWidget(self.steps_label)
        head.addLayout(texts, 1)
        self.state_label = _label("", "statePill")
        head.addWidget(self.state_label, 0, Qt.AlignmentFlag.AlignTop)
        layout.addLayout(head)

        self.progress_bar = QProgressBar()
        self.progress_bar.setObjectName("thinProgress")
        self.progress_bar.setRange(0, 1000)
        self.progress_bar.setTextVisible(False)
        self.progress_bar.setFixedHeight(6)
        layout.addWidget(self.progress_bar)

        row = QHBoxLayout()
        self.status_label = _label("", "downloadDetail", wrap=True)
        row.addWidget(self.status_label, 1)
        self.open_button = QPushButton("Open video")
        self.playlist_button = QPushButton("Add to playlist")
        self.folder_button = QPushButton("Show in folder")
        self.retry_button = QPushButton("Retry")
        self.retry_now_button = QPushButton("Retry now")
        self.cancel_button = QPushButton("Cancel")
        self.remove_button = QPushButton("Remove")
        for button in (self.cancel_button, self.remove_button, self.folder_button, self.playlist_button,
                       self.retry_button, self.retry_now_button, self.open_button):
            row.addWidget(button, 0, Qt.AlignmentFlag.AlignTop)
        for button in (self.open_button, self.retry_button, self.retry_now_button):
            button.setObjectName("primaryButton")
        layout.addLayout(row)

        self.message_label = _label("", "downloadMessage", wrap=True)
        layout.addWidget(self.message_label)
        self.link_row = QWidget()
        link_row = QHBoxLayout(self.link_row)
        link_row.setContentsMargins(0, 0, 0, 0)
        self.link_input = QLineEdit()
        self.link_input.setPlaceholderText("Paste a new link for this same file")
        self.continue_button = QPushButton("Continue")
        self.continue_button.setObjectName("primaryButton")
        link_row.addWidget(self.link_input, 1)
        link_row.addWidget(self.continue_button)
        layout.addWidget(self.link_row)

        self.open_button.clicked.connect(lambda: self.dialog.open_requested.emit(self.job.result_path))
        self.playlist_button.clicked.connect(self._add_to_playlist)
        self.folder_button.clicked.connect(lambda: show_file_in_folder(self.job.result_path))
        self.retry_button.clicked.connect(lambda: self.dialog.run_queue_action(self.dialog.queue.retry, self.job))
        self.retry_now_button.clicked.connect(lambda: self.dialog.queue.retry_now(self.job))
        self.cancel_button.clicked.connect(lambda: self.dialog.queue.cancel(self.job))
        self.remove_button.clicked.connect(lambda: self.dialog.queue.remove(self.job))
        self.continue_button.clicked.connect(self._continue_with_link)
        self.link_input.returnPressed.connect(self._continue_with_link)

    def _add_to_playlist(self):
        self.dialog.playlist_requested.emit(self.job.result_path)
        self.playlist_button.setEnabled(False)
        self.playlist_button.setText("In playlist")

    def _continue_with_link(self):
        url = self.link_input.text().strip()
        if self.dialog.run_queue_action(self.dialog.queue.continue_with_link, self.job, url):
            self.link_input.clear()

    def update_job(self, job):
        changed = job is not self.job
        self.job = job
        state = job.state
        self.name_label.setText((job.result_path or job.path).name)
        self.name_label.setToolTip(str(job.result_path or job.path))
        self.icon.setText("▤" if job.kind == "archive" else ("▶" if job.kind == "video" else "?"))
        self.icon.setProperty("kind", job.kind)
        self.kind_label.setText(kind_badge_text(job.kind, job.url_format))
        self.kind_label.setProperty("kind", job.kind)
        self.state_label.setText(STATE_LABELS.get(state, state.capitalize()))
        tone = {"completed": "success", "waiting": "attention", "expired": "attention",
                "failed": "error", "running": "info", "cancelling": "info"}.get(state, "neutral")
        if state == "running" and job.stage == "unpack":
            self.state_label.setText("Unpacking")
            tone = "unpack"
        self.state_label.setProperty("tone", tone)
        self.setProperty("tone", tone)
        for widget in (self.icon, self.kind_label, self.state_label, self):
            _repolish(widget)
        self.steps_label.setText(self._steps_html(job))

        ready = state == "completed"
        show_bar = state in ("running", "waiting", "expired", "cancelling") or (state == "failed" and job.kept_bytes)
        self.progress_bar.setVisible(bool(show_bar))
        self.progress_bar.setRange(0, 0 if state == "running" and not job.total else 1000)
        if job.total:
            self.progress_bar.setValue(min(1000, int(job.done * 1000 / job.total)))
        else:
            self.progress_bar.setValue(1000 if ready else 0)

        self.status_label.setText(self._detail(job))
        message = job.status if state in ("waiting", "expired", "failed") else ""
        self.message_label.setText(message or "")
        self.message_label.setVisible(bool(message))
        self.message_label.setProperty("tone", "error" if state == "failed" and not job.kept_bytes else "attention")
        _repolish(self.message_label)

        stopped_with_data = state in ("failed", "expired") and bool(job.kept_bytes)
        visible = {
            self.open_button: ready,
            self.playlist_button: ready,
            self.folder_button: ready,
            self.retry_button: job.can_retry,
            self.retry_now_button: state == "waiting",
            self.cancel_button: state in ("queued", "running", "waiting") or stopped_with_data,
            self.remove_button: state in ("completed", "cancelled") or (state in ("failed", "expired") and not job.kept_bytes),
        }
        for button, show in visible.items():
            button.setVisible(show)
        self.cancel_button.setEnabled(not self.dialog.queue.stopping)
        self.retry_button.setEnabled(not self.dialog.queue.stopping)
        self.link_row.setVisible(state == "expired" or (stopped_with_data and not job.url))
        if job.kept_bytes:
            self.continue_button.setText("Continue from %s" % format_bytes(job.kept_bytes))
        if changed and ready:
            self.playlist_button.setEnabled(True)
            self.playlist_button.setText("Add to playlist")

    @staticmethod
    def _steps_html(job):
        names = ["Download", "Ready"] if job.kind == "video" else ["Download", "Unpack", "Ready"]
        if job.state == "completed":
            current = len(names)
        elif job.state == "queued":
            current = -1
        elif job.stage == "unpack":
            current = 1
        else:
            current = 0
        parts = []
        for index, name in enumerate(names):
            if index < current:
                parts.append("<span style='color:#3fb06e'>✓ %s</span>" % name)
            elif index == current:
                color = {"waiting": "#d8a62e", "expired": "#d8a62e", "failed": "#e0565b"}.get(job.state, "#4f8ef7")
                parts.append("<b style='color:%s'>%s</b>" % (color, name))
            else:
                parts.append("<span style='color:#7d8696'>%s</span>" % name)
        return " &nbsp;›&nbsp; ".join(parts)

    @staticmethod
    def _detail(job):
        state = job.state
        if state == "queued":
            return "Waiting for the current download" + (" · %s kept" % format_bytes(job.kept_bytes) if job.kept_bytes else "")
        if state == "running":
            if job.stage == "unpack" or job.active_connections == 0 and job.total:
                return "%s · %s / %s" % (job.status, format_bytes(job.done), format_bytes(job.total)) if job.total else job.status
            if job.total:
                text = "%s / %s" % (format_bytes(job.done), format_bytes(job.total))
                if job.speed > 0:
                    text += " · %s/s" % format_bytes(job.speed)
                    if job.done < job.total:
                        text += " · about %s left" % format_eta((job.total - job.done) / job.speed)
                if job.active_connections:
                    text += " · %d connections" % job.active_connections
                return text
            return job.status
        if state == "waiting":
            kept = "%s of %s kept" % (format_bytes(job.done), format_bytes(job.total)) if job.total else "Partial data kept"
            remaining = job.retry_at - time.monotonic()
            return kept + (" · next try in %d s" % remaining if remaining > 1 else " · retrying…")
        if state in ("expired", "failed") and job.kept_bytes:
            return "%s of %s kept" % (format_bytes(job.kept_bytes), format_bytes(job.resume.total))
        if state == "completed":
            return "Saved to %s" % (job.result_path or job.path).parent
        if state == "failed":
            return "Nothing saved"
        return job.status


class VideoDownloadDialog(QDialog):
    open_requested = Signal(object)
    playlist_requested = Signal(object)

    def __init__(self, settings, queue, parent=None):
        super().__init__(parent)
        self.settings = settings
        self.queue = queue
        self.cards = []
        self.setObjectName("downloadsDialog")
        self.setWindowTitle("Downloads")
        self.setModal(False)
        self.resize(900, 720)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 16, 20, 14)
        layout.setSpacing(10)

        header = QHBoxLayout()
        header.addWidget(_label("Downloads", "dialogTitle"))
        self.headline_label = _label("", "dialogHint")
        header.addWidget(self.headline_label)
        header.addStretch()
        self.background_button = QPushButton("Hide · keeps downloading")
        self.background_button.clicked.connect(self.hide)
        header.addWidget(self.background_button)
        layout.addLayout(header)

        layout.addWidget(_label(
            "Paste download links — one per line. Videos (MP4, MKV) and archives (ZIP, TAR, TAR.GZ) "
            "are both fine; archives are unpacked automatically. You can keep annotating while "
            "this window is hidden.", "dialogHint", wrap=True))
        self.url_input = QPlainTextEdit()
        self.url_input.setPlaceholderText("https://…\nhttps://…")
        self.url_input.setMaximumHeight(84)
        self.url_input.textChanged.connect(self._update_preview)
        layout.addWidget(self.url_input)
        self.preview_label = QLabel()
        self.preview_label.setObjectName("linkPreview")
        self.preview_label.setTextFormat(Qt.TextFormat.RichText)
        self.preview_label.setWordWrap(True)
        layout.addWidget(self.preview_label)

        options = QHBoxLayout()
        options.addWidget(_label("Save to", "dialogHint"))
        self.path_input = QLineEdit(str(settings.value("downloads/directory", str(Path.home() / "Downloads"))))
        options.addWidget(self.path_input, 1)
        browse = QPushButton("Choose…")
        browse.clicked.connect(self._choose_directory)
        options.addWidget(browse)
        options.addWidget(_label("Connections", "dialogHint"))
        self.connections = QSpinBox()
        self.connections.setRange(1, 16)
        self.connections.setValue(8)
        self.connections.setToolTip("Parallel connections per file (advanced)")
        options.addWidget(self.connections)
        layout.addLayout(options)

        add_row = QHBoxLayout()
        self.auto_playlist = QCheckBox("Add to playlist when ready")
        self.auto_playlist.setChecked(auto_playlist_enabled(settings))
        self.auto_playlist.toggled.connect(lambda on: self.settings.setValue("downloads/auto_playlist", on))
        add_row.addWidget(self.auto_playlist)
        add_row.addStretch()
        self.start_button = QPushButton("Add to queue")
        self.start_button.setObjectName("primaryButton")
        self.start_button.clicked.connect(self.start_download)
        add_row.addWidget(self.start_button)
        layout.addLayout(add_row)

        self.cards_host = QWidget()
        self.cards_host.setObjectName("downloadCards")
        self.cards_layout = QVBoxLayout(self.cards_host)
        self.cards_layout.setContentsMargins(0, 0, 0, 0)
        self.cards_layout.setSpacing(8)
        self.empty_label = _label("No downloads yet. Paste links above.", "dialogHint")
        self.empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.cards_layout.addWidget(self.empty_label)
        self.cards_layout.addStretch()
        scroll = QScrollArea()
        scroll.setObjectName("downloadScroll")
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setWidget(self.cards_host)
        layout.addWidget(scroll, 1)

        self.awake_label = _label("", "dialogHint", wrap=True)
        layout.addWidget(self.awake_label)

        # The "next try in N s" countdown needs ticks between queue events.
        self.countdown_timer = QTimer(self)
        self.countdown_timer.setInterval(1000)
        self.countdown_timer.timeout.connect(self._tick_waiting)
        queue.changed.connect(self.refresh)
        self._update_preview()
        self.refresh()

    def _tick_waiting(self):
        for card in self.cards:
            if card.job is not None and card.job.state == "waiting":
                card.status_label.setText(card._detail(card.job))

    def _choose_directory(self):
        directory = QFileDialog.getExistingDirectory(self, "Save downloaded videos", self.path_input.text())
        if directory:
            self.path_input.setText(directory)

    def _links(self):
        return [line.strip() for line in self.url_input.toPlainText().splitlines() if line.strip()]

    def _update_preview(self):
        links = self._links()
        self.start_button.setText("Add %d to queue" % len(links) if len(links) > 1 else "Add to queue")
        if not links:
            self.preview_label.hide()
            return
        rows = []
        for url in links[:8]:
            try:
                validate_download_url(url)
            except DownloadError:
                rows.append("<span style='color:#e0565b'>✗ Not a complete HTTPS link</span>")
                continue
            kind, fmt = link_kind(url), link_format(url)
            name = suggested_video_name(url) if kind != "unknown" else "type is detected after download"
            note = {"archive": "will be unpacked → video", "video": "saved as is"}.get(kind, "")
            rows.append("<b>%s</b> &nbsp;%s%s" % (
                kind_badge_text(kind, fmt), name.replace("&", "&amp;").replace("<", "&lt;"),
                " &nbsp;<span style='color:#9aa3b2'>· %s</span>" % note if note else ""))
        if len(links) > 8:
            rows.append("<span style='color:#9aa3b2'>… and %d more</span>" % (len(links) - 8))
        self.preview_label.setText("<br>".join(rows))
        self.preview_label.show()

    def _available_path(self, directory, name):
        path = directory / name
        number = 2
        while any(p.exists() or p.is_symlink() for p in (path, path.with_suffix(".mp4"), path.with_suffix(".mkv"))) or self.queue.reserves_path(path):
            path = directory / (Path(name).stem + " (%d)" % number + Path(name).suffix)
            number += 1
        return path

    def start_download(self):
        links = self._links()
        try:
            if not links:
                raise DownloadError("Paste at least one download link.")
            if len(links) > 100 or any(len(url) > 32768 for url in links):
                raise DownloadError("Add up to 100 links at a time, each at most 32768 characters.")
            for url in links:
                validate_download_url(url)
            directory = Path(self.path_input.text().strip()).expanduser().absolute()
            if not self.path_input.text().strip() or not directory.is_dir():
                raise DownloadError("Choose an existing download folder.")
            for url in links:
                path = self._available_path(directory, suggested_video_name(url))
                self.queue.enqueue(url, path, self.connections.value())
            self.settings.setValue("downloads/directory", str(directory))
            self.url_input.clear()
        except (DownloadError, OSError) as exc:
            message = str(exc) if isinstance(exc, DownloadError) else "Cannot access the download folder."
            QMessageBox.warning(self, "Cannot add download", message)

    def run_queue_action(self, action, *args):
        try:
            action(*args)
            return True
        except (DownloadError, OSError) as exc:
            QMessageBox.warning(self, "Cannot continue download",
                                str(exc) if isinstance(exc, DownloadError) else "Cannot access the destination.")
            return False

    def card_for(self, job):
        return next((card for card in self.cards if card.job is job), None)

    @Slot()
    def refresh(self):
        self.start_button.setEnabled(not self.queue.stopping)
        jobs = list(reversed(self.queue.jobs))  # newest first
        while len(self.cards) < len(jobs):
            card = DownloadCard(self)
            self.cards_layout.insertWidget(len(self.cards), card)
            self.cards.append(card)
        while len(self.cards) > len(jobs):
            card = self.cards.pop()
            card.setParent(None)
            card.deleteLater()
        for card, job in zip(self.cards, jobs):
            card.update_job(job)
        self.empty_label.setVisible(not jobs)
        waiting = any(job.state == "waiting" for job in jobs)
        if waiting != self.countdown_timer.isActive():
            self.countdown_timer.start() if waiting else self.countdown_timer.stop()
        active = sum(job.state in ("queued", "running", "waiting", "cancelling") for job in self.queue.jobs)
        attention = sum(job.state in ("expired", "failed") for job in self.queue.jobs)
        headline = "%d in progress or queued" % active if active else ("All done" if jobs else "")
        if attention:
            headline += (" · " if headline else "") + "%d need%s attention" % (attention, "s" if attention == 1 else "")
        self.headline_label.setText(headline)
        if self.queue.keeps_awake:
            self.awake_label.setText(
                "Keeping the computer awake while downloading. Closing the lid still sleeps it — "
                "the download waits for the network and continues after wake.")
        else:
            self.awake_label.setText("Partial files are kept until the download finishes or you cancel it.")

    def reject(self):
        self.hide()

    def closeEvent(self, event):
        self.hide()
        event.ignore()


def auto_playlist_enabled(settings):
    # Off by default: completion never changes the playlist unless asked to.
    value = settings.value("downloads/auto_playlist", False)
    return value if isinstance(value, bool) else str(value).lower() in ("1", "true", "yes")

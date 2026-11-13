"""Bounded, persistent history of user-opened files (never a playlist)."""
import json
from pathlib import Path


class RecentFiles:
    KEY = "files/recent"
    LIMIT = 20  # Per kind.
    KINDS = ("video", "folder", "annotations")

    def __init__(self, settings):
        self.settings = settings
        self.entries = []
        try:
            entries = json.loads(settings.value(self.KEY, "[]"))
        except (ValueError, TypeError):
            entries = []
        if isinstance(entries, list):
            for entry in entries:
                if not isinstance(entry, dict) or entry.get("kind") not in self.KINDS:
                    continue
                kind, path = entry["kind"], entry.get("path")
                video = entry.get("video") if kind == "annotations" else None
                if not self._valid_path(path) or (kind == "annotations" and not self._valid_path(video)):
                    continue
                item = {"kind": kind, "path": path}
                if video:
                    item["video"] = video
                if item not in self.entries and len(self.items(kind)) < self.LIMIT:
                    self.entries.append(item)

    @staticmethod
    def _valid_path(value):
        return isinstance(value, str) and bool(value) and "\0" not in value and Path(value).is_absolute()

    def items(self, kind):
        return [dict(entry) for entry in self.entries if entry["kind"] == kind]

    def record(self, kind, path, video=None):
        if kind not in self.KINDS or (kind == "annotations" and video is None):
            raise ValueError("Unknown recent file kind or missing annotation video")
        entry = {"kind": kind, "path": str(Path(path).resolve())}
        if kind == "annotations":
            entry["video"] = str(Path(video).resolve())
        self.entries = [entry] + [item for item in self.entries if item != entry]
        counts = {}
        retained = []
        for item in self.entries:
            counts[item["kind"]] = counts.get(item["kind"], 0) + 1
            if counts[item["kind"]] <= self.LIMIT:
                retained.append(item)
        self.entries = retained
        self._save()

    def clear(self):
        self.entries = []
        self._save()

    def _save(self):
        self.settings.setValue(self.KEY, json.dumps(self.entries, ensure_ascii=False))

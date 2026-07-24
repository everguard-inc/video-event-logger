import json
import os
import tempfile
from json import JSONDecodeError
from pathlib import Path
from typing import Dict, List, Optional

from video_event_logger.models.annotation import AnnotationDocument
from video_event_logger.services.path_utils import (
    annotation_backup_path_for_video_name,
    annotation_path_for_video_name,
    legacy_autosave_path_for_video_name,
)


class CorruptedAnnotationError(Exception):
    def __init__(self, path: Path, backup_path: Path) -> None:
        super().__init__("Corrupted annotation file: %s" % path)
        self.path = path
        self.backup_path = backup_path


class AnnotationStore:
    def annotation_path_for_video_name(self, video_name: str) -> Path:
        return annotation_path_for_video_name(video_name)

    def backup_path_for_video_name(self, video_name: str) -> Path:
        return annotation_backup_path_for_video_name(video_name)

    def legacy_autosave_path_for_video_name(self, video_name: str) -> Path:
        return legacy_autosave_path_for_video_name(video_name)

    def existing_paths(self, video_name: str) -> Dict[str, Path]:
        annotation_path = self.annotation_path_for_video_name(video_name)
        backup_path = self.backup_path_for_video_name(video_name)
        legacy_autosave_path = self.legacy_autosave_path_for_video_name(video_name)
        paths = {}
        if annotation_path.exists():
            paths["annotation"] = annotation_path
        if backup_path.exists():
            paths["backup"] = backup_path
        if legacy_autosave_path.exists():
            paths["legacy_autosave"] = legacy_autosave_path
        return paths

    def load(self, path: Path) -> AnnotationDocument:
        try:
            with path.open("r", encoding="utf-8") as file_obj:
                data = json.load(file_obj)
        except JSONDecodeError:
            backup_path = self.backup_corrupted_file(path)
            raise CorruptedAnnotationError(path, backup_path)
        if not isinstance(data, dict):
            backup_path = self.backup_corrupted_file(path)
            raise CorruptedAnnotationError(path, backup_path)
        return AnnotationDocument.from_dict(data)

    def save(self, document: AnnotationDocument) -> Path:
        annotation_path = self.annotation_path_for_video_name(document.video_name)
        self._backup_existing_annotation(annotation_path)
        self._write_json(annotation_path, document.to_dict())
        legacy_autosave_path = self.legacy_autosave_path_for_video_name(
            document.video_name
        )
        if legacy_autosave_path.exists():
            try:
                legacy_autosave_path.unlink()
            except OSError:
                pass
        return annotation_path

    def delete_project(self, video_name: str) -> List[Path]:
        deleted = []
        paths = (
            self.annotation_path_for_video_name(video_name),
            self.backup_path_for_video_name(video_name),
            self.legacy_autosave_path_for_video_name(video_name),
        )
        for path in paths:
            if path.exists():
                path.unlink()
                deleted.append(path)
        return deleted

    def _backup_existing_annotation(self, annotation_path: Path) -> None:
        if not annotation_path.exists():
            return
        try:
            with annotation_path.open("r", encoding="utf-8") as file_obj:
                previous_data = json.load(file_obj)
        except (JSONDecodeError, OSError, UnicodeDecodeError):
            return
        if not isinstance(previous_data, dict):
            return
        backup_path = annotation_path.with_name("%s.bak" % annotation_path.name)
        self._write_json(backup_path, previous_data)

    def backup_corrupted_file(self, path: Path) -> Path:
        backup_path = path.with_name("%s_corrupted%s" % (path.stem, path.suffix))
        counter = 1
        while backup_path.exists():
            backup_path = path.with_name("%s_corrupted_%d%s" % (path.stem, counter, path.suffix))
            counter += 1
        path.rename(backup_path)
        return backup_path

    def _write_json(self, path: Path, data: Dict[str, object]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary_path = None  # type: Optional[Path]
        try:
            with tempfile.NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                dir=str(path.parent),
                prefix=".%s." % path.name,
                suffix=".tmp",
                delete=False,
            ) as file_obj:
                temporary_path = Path(file_obj.name)
                json.dump(data, file_obj, indent=2, ensure_ascii=False)
                file_obj.write("\n")
                file_obj.flush()
                os.fsync(file_obj.fileno())

            os.replace(temporary_path, path)
            temporary_path = None
        finally:
            if temporary_path is not None:
                try:
                    temporary_path.unlink()
                except FileNotFoundError:
                    pass

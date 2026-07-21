import json
import os
import tempfile
from json import JSONDecodeError
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from video_event_logger.models.annotation import AnnotationDocument
from video_event_logger.services.path_utils import annotation_paths_for_video_name


class CorruptedAnnotationError(Exception):
    def __init__(self, path: Path, backup_path: Path) -> None:
        super().__init__("Corrupted annotation file: %s" % path)
        self.path = path
        self.backup_path = backup_path


class AnnotationStore:
    def paths_for_video_name(self, video_name: str) -> Tuple[Path, Path]:
        return annotation_paths_for_video_name(video_name)

    def existing_paths(self, video_name: str) -> Dict[str, Path]:
        autosave_path, final_path = self.paths_for_video_name(video_name)
        paths = {}
        if autosave_path.exists():
            paths["autosave"] = autosave_path
        if final_path.exists():
            paths["final"] = final_path
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

    def save_autosave(self, document: AnnotationDocument) -> Path:
        autosave_path, _ = self.paths_for_video_name(document.video_name)
        self._write_json(autosave_path, document.to_dict(is_autosave=True))
        return autosave_path

    def save_final(self, document: AnnotationDocument) -> Path:
        _, final_path = self.paths_for_video_name(document.video_name)
        self._write_json(final_path, document.to_dict(is_autosave=False))
        return final_path

    def delete_project(self, video_name: str) -> List[Path]:
        deleted = []
        for path in self.paths_for_video_name(video_name):
            if path.exists():
                path.unlink()
                deleted.append(path)
        return deleted

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

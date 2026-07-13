from pathlib import Path
from typing import Dict, Optional, Tuple

from video_event_logger.models.annotation import AnnotationDocument
from video_event_logger.services.annotation_store import AnnotationStore
from video_event_logger.services.time_utils import seconds_to_hhmmss


class ProjectService:
    def __init__(self, store: Optional[AnnotationStore] = None) -> None:
        self.store = store or AnnotationStore()

    def create_empty_document(self, video_name: str) -> AnnotationDocument:
        return AnnotationDocument.empty(video_name)

    def existing_paths(self, video_name: str) -> Dict[str, Path]:
        return self.store.existing_paths(video_name)

    def paths_for_video_name(self, video_name: str) -> Tuple[Path, Path]:
        return self.store.paths_for_video_name(video_name)

    def choose_existing_source(self, paths: Dict[str, Path]) -> Optional[Path]:
        if "autosave" in paths:
            return paths["autosave"]
        if "final" in paths:
            return paths["final"]
        return None

    def load_document(self, path: Path, fallback_video_name: str) -> AnnotationDocument:
        document = self.store.load(path)
        if not document.video_name:
            document.video_name = fallback_video_name
        return document

    def delete_project(self, video_name: str):
        return self.store.delete_project(video_name)

    def update_runtime_state(
        self,
        document: AnnotationDocument,
        current_event_type: str,
        current_position_seconds: float,
        duration_seconds: Optional[float],
    ) -> None:
        document.current_event_type = current_event_type
        document.last_playback_position_seconds = current_position_seconds
        self.update_duration_metadata(document, duration_seconds)

    def update_duration_metadata(
        self,
        document: AnnotationDocument,
        duration_seconds: Optional[float],
    ) -> None:
        if duration_seconds is None:
            return
        document.video_metadata.duration_seconds = duration_seconds
        document.video_metadata.duration_hhmmss = seconds_to_hhmmss(duration_seconds)

    def save_autosave(self, document: AnnotationDocument) -> Path:
        return self.store.save_autosave(document)

    def save_final(self, document: AnnotationDocument) -> Path:
        return self.store.save_final(document)

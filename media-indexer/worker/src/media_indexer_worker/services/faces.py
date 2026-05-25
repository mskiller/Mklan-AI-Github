from __future__ import annotations

import logging
from pathlib import Path
from uuid import uuid4

import numpy as np
from PIL import Image
from huggingface_hub import hf_hub_download
from sqlalchemy import delete, select
from sqlalchemy.orm import Session, selectinload

from media_indexer_backend.core.config import get_settings
from media_indexer_backend.models.tables import Asset, FaceDetection, FacePerson
from media_indexer_backend.platform.runtime import get_people_runtime_settings


logger = logging.getLogger(__name__)


class FaceEnrichmentService:
    def __init__(self) -> None:
        self.settings = get_settings()
        self._cv2 = None
        self._detector = None
        self._recognizer = None
        self._load_failed = False

    def _download(self, repo_id: str, filename: str, *, local_only: bool) -> Path:
        return Path(
            hf_hub_download(
                repo_id=repo_id,
                filename=filename,
                cache_dir=str(self.settings.model_cache_root_path),
                local_files_only=local_only,
            )
        )

    def warm(self, *, local_only: bool = False) -> bool:
        if not get_people_runtime_settings().face_detection_enabled:
            return False
        if self._detector is not None and self._recognizer is not None and self._cv2 is not None:
            return True
        if self._load_failed and local_only:
            return False
        try:
            import cv2

            detector_path = self._download(
                self.settings.face_detector_model_id,
                "face_detection_yunet_2023mar.onnx",
                local_only=local_only,
            )
            recognizer_path = self._download(
                self.settings.face_embedder_model_id,
                "face_recognition_sface_2021dec.onnx",
                local_only=local_only,
            )
            self._cv2 = cv2
            self._detector = cv2.FaceDetectorYN_create(str(detector_path), "", (320, 320), 0.7, 0.3, 5000)
            self._recognizer = cv2.FaceRecognizerSF_create(str(recognizer_path), "")
            self._load_failed = False
            return True
        except Exception as exc:  # noqa: BLE001
            self._load_failed = True
            logger.warning("face enrichment models unavailable: %s", exc, exc_info=True)
            return False

    def _save_crop(self, asset_id, image_bgr) -> str:
        assert self._cv2 is not None
        relative_path = Path("faces") / str(asset_id) / f"{uuid4()}.webp"
        absolute_path = self.settings.preview_root_path / relative_path
        absolute_path.parent.mkdir(parents=True, exist_ok=True)
        rgb = self._cv2.cvtColor(image_bgr, self._cv2.COLOR_BGR2RGB)
        Image.fromarray(rgb).save(absolute_path, format="WEBP", quality=92)
        return relative_path.as_posix()

    def detect_faces(self, image_path: Path, asset_id) -> list[dict]:
        if not self.warm(local_only=False):
            return []
        assert self._cv2 is not None
        assert self._detector is not None
        assert self._recognizer is not None

        image = self._cv2.imread(str(image_path))
        if image is None:
            return []
        height, width = image.shape[:2]
        self._detector.setInputSize((width, height))
        _retval, faces = self._detector.detect(image)
        if faces is None or len(faces) == 0:
            return []

        detections: list[dict] = []
        for face in faces:
            x, y, w, h = [int(round(float(value))) for value in face[:4]]
            if min(w, h) < self.settings.face_min_size:
                continue
            x1 = max(0, x)
            y1 = max(0, y)
            x2 = min(width, x + max(1, w))
            y2 = min(height, y + max(1, h))
            if x2 <= x1 or y2 <= y1:
                continue
            aligned = self._recognizer.alignCrop(image, face)
            feature = self._recognizer.feature(aligned)
            vector = np.asarray(feature, dtype=np.float32).reshape(-1)
            norm = np.linalg.norm(vector)
            embedding = (vector / norm).astype(np.float32).tolist() if norm else None
            crop_path = self._save_crop(asset_id, aligned)
            detections.append(
                {
                    "bbox_x1": x1,
                    "bbox_y1": y1,
                    "bbox_x2": x2,
                    "bbox_y2": y2,
                    "det_score": float(face[-1]),
                    "embedding": embedding,
                    "crop_preview_path": crop_path,
                }
            )
        return detections

    def delete_asset_faces(self, session: Session, asset_id) -> None:
        existing = session.execute(
            select(FaceDetection).where(FaceDetection.asset_id == asset_id)
        ).scalars().all()
        for face in existing:
            if not face.crop_preview_path:
                continue
            crop_path = (self.settings.preview_root_path / face.crop_preview_path).resolve(strict=False)
            if crop_path.is_relative_to(self.settings.preview_root_path) and crop_path.exists():
                crop_path.unlink(missing_ok=True)
        session.execute(delete(FaceDetection).where(FaceDetection.asset_id == asset_id))
        session.flush()

    def _bbox_iou(self, left: dict | FaceDetection, right: dict | FaceDetection) -> float:
        left_x1 = int(left["bbox_x1"]) if isinstance(left, dict) else left.bbox_x1
        left_y1 = int(left["bbox_y1"]) if isinstance(left, dict) else left.bbox_y1
        left_x2 = int(left["bbox_x2"]) if isinstance(left, dict) else left.bbox_x2
        left_y2 = int(left["bbox_y2"]) if isinstance(left, dict) else left.bbox_y2
        right_x1 = int(right["bbox_x1"]) if isinstance(right, dict) else right.bbox_x1
        right_y1 = int(right["bbox_y1"]) if isinstance(right, dict) else right.bbox_y1
        right_x2 = int(right["bbox_x2"]) if isinstance(right, dict) else right.bbox_x2
        right_y2 = int(right["bbox_y2"]) if isinstance(right, dict) else right.bbox_y2
        inter_x1 = max(left_x1, right_x1)
        inter_y1 = max(left_y1, right_y1)
        inter_x2 = min(left_x2, right_x2)
        inter_y2 = min(left_y2, right_y2)
        inter_w = max(0, inter_x2 - inter_x1)
        inter_h = max(0, inter_y2 - inter_y1)
        inter = inter_w * inter_h
        left_area = max(1, (left_x2 - left_x1) * (left_y2 - left_y1))
        right_area = max(1, (right_x2 - right_x1) * (right_y2 - right_y1))
        return inter / float(left_area + right_area - inter)

    def _cosine_distance(self, left: list[float] | None, right: list[float] | None) -> float | None:
        if not left or not right:
            return None
        left_vec = np.asarray(left, dtype=np.float32)
        right_vec = np.asarray(right, dtype=np.float32)
        if left_vec.shape != right_vec.shape:
            return None
        left_norm = np.linalg.norm(left_vec)
        right_norm = np.linalg.norm(right_vec)
        if left_norm == 0 or right_norm == 0:
            return None
        return float(1.0 - float(np.dot(left_vec / left_norm, right_vec / right_norm)))

    def _carry_forward_identity(self, existing: list[FaceDetection], detections: list[dict]) -> None:
        used_indexes: set[int] = set()
        for old_face in existing:
            if old_face.person_id is None:
                continue
            best_index: int | None = None
            best_score: float | None = None
            for index, detection in enumerate(detections):
                if index in used_indexes or detection.get("person_id") is not None:
                    continue
                distance = self._cosine_distance(old_face.embedding, detection.get("embedding"))
                if distance is not None and distance <= self.settings.face_recognition_threshold:
                    score = 1.0 - distance
                else:
                    iou = self._bbox_iou(old_face, detection)
                    if iou < 0.2:
                        continue
                    score = iou
                if best_score is None or score > best_score:
                    best_index = index
                    best_score = score
            if best_index is None:
                continue
            used_indexes.add(best_index)
            detections[best_index]["person_id"] = old_face.person_id
            # Guard: old_face.person may be None if the FK is stale (person deleted without cascade)
            detections[best_index]["cover_person_id"] = (
                old_face.person_id
                if old_face.person is not None and old_face.person.cover_face_id == old_face.id
                else None
            )

    def refresh_asset_faces(self, session: Session, asset: Asset, image_path: Path) -> int:
        if not get_people_runtime_settings().face_detection_enabled:
            return 0
        existing = session.execute(
            select(FaceDetection)
            .where(FaceDetection.asset_id == asset.id)
            .options(selectinload(FaceDetection.person))
        ).scalars().all()
        detections = self.detect_faces(image_path, asset.id)
        if existing and detections:
            self._carry_forward_identity(existing, detections)
        old_crop_paths = [face.crop_preview_path for face in existing if face.crop_preview_path]
        session.execute(delete(FaceDetection).where(FaceDetection.asset_id == asset.id))
        session.flush()
        if detections:
            rows = [
                FaceDetection(
                    asset_id=asset.id,
                    person_id=item.get("person_id"),
                    bbox_x1=item["bbox_x1"],
                    bbox_y1=item["bbox_y1"],
                    bbox_x2=item["bbox_x2"],
                    bbox_y2=item["bbox_y2"],
                    det_score=item["det_score"],
                    embedding=item["embedding"],
                    crop_preview_path=item["crop_preview_path"],
                )
                for item in detections
            ]
            session.add_all(rows)
            session.flush()
            for row, item in zip(rows, detections, strict=False):
                if item.get("cover_person_id"):
                    person = session.get(FacePerson, item["cover_person_id"])
                    if person is not None:
                        person.cover_face_id = row.id
            session.flush()
        for crop_preview_path in old_crop_paths:
            crop_path = (self.settings.preview_root_path / crop_preview_path).resolve(strict=False)
            if crop_path.is_relative_to(self.settings.preview_root_path) and crop_path.exists():
                crop_path.unlink(missing_ok=True)
        return len(detections)

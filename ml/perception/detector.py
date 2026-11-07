from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

import numpy as np
from ultralytics import YOLO

from .severity import severity_proxy

RDD_CLASS_MAP = {
    "D00": "longitudinal_crack",
    "D10": "transverse_crack",
    "D20": "alligator_crack",
    "D40": "pothole",
    "longitudinal_crack": "longitudinal_crack",
    "transverse_crack": "transverse_crack",
    "alligator_crack": "alligator_crack",
    "pothole": "pothole",
}


@dataclass(frozen=True)
class Detection:
    defect_type: str
    confidence: float
    bbox_xyxy: tuple[float, float, float, float]
    severity_proxy: float


class RoadDamageDetector:
    def __init__(
        self,
        weights: str | Path,
        device: str = "cpu",
        imgsz: int = 640,
        confidence: float = 0.25,
        iou: float = 0.50,
    ) -> None:
        self.weights = Path(weights)
        if not self.weights.exists():
            raise FileNotFoundError(
                f"Road-damage weights not found: {self.weights}. "
                "Train M1 first or place a validated checkpoint in models/."
            )
        self.device = device
        self.imgsz = imgsz
        self.confidence = confidence
        self.iou = iou
        self.model = YOLO(str(self.weights))

    def _detections(self, frame: np.ndarray, result) -> list[Detection]:
        h, w = frame.shape[:2]
        frame_area = max(1.0, float(h * w))
        detections: list[Detection] = []
        if result.boxes is not None:
            names = result.names
            for box in result.boxes:
                cls_idx = int(box.cls.item())
                raw_name = str(names[cls_idx])
                defect_type = RDD_CLASS_MAP.get(raw_name, raw_name.lower().replace(" ", "_"))
                conf = float(box.conf.item())
                x1, y1, x2, y2 = map(float, box.xyxy[0].tolist())
                area_ratio = max(0.0, (x2 - x1) * (y2 - y1)) / frame_area
                detections.append(Detection(
                    defect_type=defect_type, confidence=round(conf, 5), bbox_xyxy=(x1, y1, x2, y2),
                    severity_proxy=severity_proxy(defect_type, area_ratio, conf),
                ))
        return detections

    def new_tracker(self, config: str = "bytetrack.yaml"):
        """Ultralytics' built-in ByteTrack, fed frame by frame (one tracker per video)."""
        from ultralytics.trackers.byte_tracker import BYTETracker
        from ultralytics.utils import YAML, IterableSimpleNamespace
        from ultralytics.utils.checks import check_yaml
        return BYTETracker(IterableSimpleNamespace(**YAML.load(check_yaml(config))))

    def detect_and_track(self, frame: np.ndarray, tracker) -> list[tuple[Detection, int | None]]:
        """Raw detections of one frame, each with its ByteTrack id (None if the tracker did not take it).
        Ids are read from every track updated on this frame, confirmed or not, so the first frame of a
        defect carries the same id as the next ones."""
        result = self.model.predict(source=frame, imgsz=self.imgsz, conf=self.confidence, iou=self.iou,
                                    device=self.device, verbose=False)[0]
        detections = self._detections(frame, result)
        tracker.update(result.boxes.cpu().numpy(), frame)  # also on empty frames: tracks age normally
        ids = {int(t.idx): int(t.track_id) for t in tracker.tracked_stracks
               if t.frame_id == tracker.frame_id and getattr(t, "idx", None) is not None}
        return [(d, ids.get(i)) for i, d in enumerate(detections)]

    def predict_batch(self, frames: list[np.ndarray]) -> list[list[Detection]]:
        if not frames:
            return []
        results = self.model.predict(
            source=frames,
            imgsz=self.imgsz,
            conf=self.confidence,
            iou=self.iou,
            device=self.device,
            verbose=False,
            stream=False,
        )
        return [self._detections(frame, result) for frame, result in zip(frames, results)]

"""Citizen image interpretation boundary.

The first production M1 uses the same validated road-damage detector for citizen
photos and vehicle frames. Text can be attached as metadata; a VLM is not placed
on the critical path until it has its own validation set.
"""
from pathlib import Path

from .detector import RoadDamageDetector


def interpret_citizen_report(image_path: str, detector: RoadDamageDetector, text_description: str = "") -> dict:
    import cv2

    image = cv2.imread(str(Path(image_path)))
    if image is None:
        raise ValueError(f"Cannot decode image: {image_path}")
    detections = detector.predict_batch([image])[0]
    return {
        "text_description": text_description,
        "detections": [
            {
                "defect_type": d.defect_type,
                "severity_proxy": d.severity_proxy,
                "confidence": d.confidence,
                "bbox_xyxy": list(d.bbox_xyxy),
            }
            for d in detections
        ],
    }

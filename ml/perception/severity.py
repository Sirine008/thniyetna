"""Visual severity proxy.

This is intentionally named a proxy: a monocular dashboard image cannot infer
engineering depth/width reliably without camera calibration or 3-D sensing.
"""
from math import sqrt

CLASS_PRIOR = {
    "longitudinal_crack": 0.38,
    "transverse_crack": 0.44,
    "alligator_crack": 0.62,
    "pothole": 0.72,
}


def severity_proxy(defect_type: str, bbox_area_ratio: float, confidence: float) -> float:
    prior = CLASS_PRIOR.get(defect_type, 0.5)
    area = max(0.0, min(1.0, bbox_area_ratio))
    # 15% of frame area already counts as visually large for a road defect.
    size_component = min(1.0, sqrt(area / 0.15)) if area > 0 else 0.0
    score = 0.55 * prior + 0.35 * size_component + 0.10 * max(0.0, min(1.0, confidence))
    return round(max(0.0, min(1.0, score)), 4)

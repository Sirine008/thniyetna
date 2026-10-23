"""Run the M1 detector on a local pilot folder and save annotated images.

Same code path as the worker (RoadDamageDetector.predict_batch, same thresholds).
Writes <out>/<name>.jpg (boxes + labels), pilot_results.json and pilot_results.csv.

    python -m perception.pilot --src /data/m1/pilot --out /data/m1/pilot_out
"""
from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path

import numpy as np

from .benchmark import list_images
from .config import settings

# BGR colours per defect class
COLORS = {
    "longitudinal_crack": (255, 170, 0),
    "transverse_crack": (0, 200, 255),
    "alligator_crack": (200, 0, 200),
    "pothole": (0, 0, 255),
}


def annotate(image: np.ndarray, detections) -> np.ndarray:
    import cv2

    out = image.copy()
    thick = max(2, round(min(out.shape[:2]) / 300))
    scale = max(0.5, min(out.shape[:2]) / 1000)
    for d in detections:
        x1, y1, x2, y2 = map(int, d.bbox_xyxy)
        color = COLORS.get(d.defect_type, (0, 255, 0))
        label = f"{d.defect_type} {d.confidence:.2f} sev {d.severity_proxy:.2f}"
        cv2.rectangle(out, (x1, y1), (x2, y2), color, thick)
        (tw, th), base = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, scale, thick)
        ty = max(th + base, y1)
        cv2.rectangle(out, (x1, ty - th - base), (x1 + tw, ty), color, -1)
        cv2.putText(out, label, (x1, ty - base), cv2.FONT_HERSHEY_SIMPLEX, scale, (255, 255, 255), thick)
    return out


def main():
    import cv2

    from .detector import RoadDamageDetector

    ap = argparse.ArgumentParser()
    ap.add_argument("--src", type=Path, default=Path("/data/m1/pilot"))
    ap.add_argument("--out", type=Path, default=Path("/data/m1/pilot_out"))
    args = ap.parse_args()

    detector = RoadDamageDetector(
        settings.weights, device=settings.device, imgsz=settings.imgsz,
        confidence=settings.confidence, iou=settings.iou,
    )
    args.out.mkdir(parents=True, exist_ok=True)
    results, rows = [], []
    for path in list_images(args.src):
        image = cv2.imread(str(path))
        if image is None:
            results.append({"image": path.name, "error": "cannot decode"})
            continue
        detections = detector.predict_batch([image])[0]
        cv2.imwrite(str(args.out / f"{path.stem}.jpg"), annotate(image, detections))
        dets = [{
            "defect_type": d.defect_type,
            "confidence": round(d.confidence, 3),
            "severity_proxy": d.severity_proxy,
            "bbox_xyxy": [round(v, 1) for v in d.bbox_xyxy],
        } for d in sorted(detections, key=lambda d: -d.confidence)]
        results.append({"image": path.name, "width": image.shape[1], "height": image.shape[0], "detections": dets})
        rows += [{"image": path.name, **{k: v for k, v in d.items() if k != "bbox_xyxy"},
                  "bbox_xyxy": " ".join(map(str, d["bbox_xyxy"]))} for d in dets] or [{"image": path.name}]

    meta = {
        "model_name": settings.model_name, "weights": settings.weights.name, "device": settings.device,
        "imgsz": settings.imgsz, "conf": settings.confidence, "iou": settings.iou,
    }
    (args.out / "pilot_results.json").write_text(
        json.dumps({"meta": meta, "images": results}, indent=2), encoding="utf-8")
    with (args.out / "pilot_results.csv").open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=["image", "defect_type", "confidence", "severity_proxy", "bbox_xyxy"])
        writer.writeheader()
        writer.writerows(rows)
    for r in results:
        dets = r.get("detections", [])
        summary = ", ".join(f"{d['defect_type']} {d['confidence']:.2f}/sev {d['severity_proxy']:.2f}" for d in dets)
        print(f"{r['image']}: {r.get('error') or summary or 'no detection'}")


if __name__ == "__main__":
    main()

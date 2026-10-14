"""Measure M1 accuracy/latency for a trained checkpoint."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from time import perf_counter

from ultralytics import YOLO


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--weights", required=True, type=Path)
    ap.add_argument("--data", required=True)
    ap.add_argument("--device", default="cpu")
    ap.add_argument("--imgsz", type=int, default=640)
    ap.add_argument("--source", default=None, help="Optional image/video source for real runtime timing")
    args = ap.parse_args()

    model = YOLO(str(args.weights))
    metrics = model.val(data=args.data, split="test", imgsz=args.imgsz, device=args.device, verbose=False)
    result = {
        "weights": str(args.weights),
        "weight_mb": round(args.weights.stat().st_size / 1024 / 1024, 2),
        "test_mAP50": float(metrics.box.map50),
        "test_mAP50_95": float(metrics.box.map),
        "test_precision": float(metrics.box.mp),
        "test_recall": float(metrics.box.mr),
        "val_speed_ms": dict(metrics.speed or {}),
    }
    if args.source:
        t0 = perf_counter()
        count = 0
        for r in model.predict(args.source, imgsz=args.imgsz, device=args.device, stream=True, verbose=False):
            count += 1
        elapsed = perf_counter() - t0
        result["runtime_items"] = count
        result["runtime_seconds"] = elapsed
        result["runtime_items_per_second"] = count / elapsed if elapsed else None

    out = args.weights.with_suffix(".benchmark.json")
    out.write_text(json.dumps(result, indent=2, default=float), encoding="utf-8")
    print(json.dumps(result, indent=2, default=float))


if __name__ == "__main__":
    main()

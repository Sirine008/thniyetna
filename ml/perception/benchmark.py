"""Measure M1 accuracy/latency for a checkpoint.

With --data: labelled test-split metrics (mAP, precision, recall).
With --source only: runtime latency on unlabelled images (e.g. the local pilot set).
"""
from __future__ import annotations

import argparse
import json
import platform
from pathlib import Path
from statistics import mean, median
from time import perf_counter

IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser()
    ap.add_argument("--weights", required=True, type=Path)
    ap.add_argument("--data", default=None, help="Dataset YAML for labelled test metrics (optional)")
    ap.add_argument("--device", default="cpu")
    ap.add_argument("--imgsz", type=int, default=640)
    ap.add_argument("--conf", type=float, default=0.25)
    ap.add_argument("--iou", type=float, default=0.50)
    ap.add_argument("--source", default=None, help="Image file or folder for real runtime timing")
    ap.add_argument("--out", type=Path, default=None, help="JSON output (default: <weights>.benchmark.json)")
    return ap


def list_images(source: str | Path) -> list[Path]:
    src = Path(source)
    if src.is_file():
        return [src]
    return sorted(p for p in src.iterdir() if p.suffix.lower() in IMAGE_SUFFIXES)


def percentile(values: list[float], q: float) -> float:
    ordered = sorted(values)
    k = (len(ordered) - 1) * q
    lo, hi = int(k), min(int(k) + 1, len(ordered) - 1)
    return ordered[lo] + (ordered[hi] - ordered[lo]) * (k - lo)


def runtime(model, images: list[Path], args) -> dict:
    """Per-image wall time of model.predict (decode + preprocess + inference + NMS), after one warm-up."""
    kwargs = dict(imgsz=args.imgsz, conf=args.conf, iou=args.iou, device=args.device, verbose=False)
    model.predict(str(images[0]), **kwargs)  # warm-up, not timed
    times_ms = []
    for path in images:
        t0 = perf_counter()
        model.predict(str(path), **kwargs)
        times_ms.append((perf_counter() - t0) * 1000)
    total_s = sum(times_ms) / 1000
    return {
        "runtime_items": len(images),
        "runtime_seconds": round(total_s, 3),
        "latency_ms_mean": round(mean(times_ms), 1),
        "latency_ms_p50": round(median(times_ms), 1),
        "latency_ms_p95": round(percentile(times_ms, 0.95), 1),
        "runtime_items_per_second": round(len(images) / total_s, 2) if total_s else None,
        "per_image_ms": {p.name: round(t, 1) for p, t in zip(images, times_ms)},
    }


def main():
    args = build_parser().parse_args()
    if not args.data and not args.source:
        raise SystemExit("Give --data (labelled metrics) and/or --source (runtime timing)")

    import torch
    from ultralytics import YOLO

    model = YOLO(str(args.weights))
    result = {
        "weights": str(args.weights),
        "weight_mb": round(args.weights.stat().st_size / 1024 / 1024, 2),
        "device": args.device,
        "imgsz": args.imgsz,
        "conf": args.conf,
        "iou": args.iou,
        "torch": torch.__version__,
        "torch_threads": torch.get_num_threads(),
        "machine": platform.machine(),
        "processor": platform.processor() or None,
    }
    if args.data:
        metrics = model.val(data=args.data, split="test", imgsz=args.imgsz, device=args.device, verbose=False)
        result.update({
            "test_mAP50": float(metrics.box.map50),
            "test_mAP50_95": float(metrics.box.map),
            "test_precision": float(metrics.box.mp),
            "test_recall": float(metrics.box.mr),
            "val_speed_ms": dict(metrics.speed or {}),
        })
    if args.source:
        images = list_images(args.source)
        if not images:
            raise SystemExit(f"No images in {args.source}")
        result.update(runtime(model, images, args))

    out = args.out or args.weights.with_suffix(".benchmark.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, indent=2, default=float), encoding="utf-8")
    print(json.dumps(result, indent=2, default=float))


if __name__ == "__main__":
    main()

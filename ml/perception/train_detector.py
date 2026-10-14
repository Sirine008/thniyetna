"""Train and compare compact road-damage detectors on RDD2022."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from ultralytics import YOLO

DEFAULT_MODELS = ["yolo26n.pt", "yolo26s.pt", "yolo11n.pt"]


def metric_summary(model: YOLO, data_yaml: str, imgsz: int, device: str) -> dict:
    metrics = model.val(data=data_yaml, split="val", imgsz=imgsz, device=device, verbose=False)
    box = metrics.box
    speed = getattr(metrics, "speed", {}) or {}
    return {
        "mAP50": float(box.map50),
        "mAP50_95": float(box.map),
        "precision": float(box.mp),
        "recall": float(box.mr),
        "preprocess_ms": float(speed.get("preprocess", 0.0)),
        "inference_ms": float(speed.get("inference", 0.0)),
        "postprocess_ms": float(speed.get("postprocess", 0.0)),
    }


def train_one(model_name: str, args) -> dict:
    model = YOLO(model_name)
    run_name = Path(model_name).stem
    model.train(
        data=args.data,
        epochs=args.epochs,
        imgsz=args.imgsz,
        batch=args.batch,
        device=args.device,
        workers=args.workers,
        project=str(args.project),
        name=run_name,
        patience=args.patience,
        optimizer="auto",
        amp=True,
        seed=args.seed,
        deterministic=True,
        close_mosaic=10,
        degrees=0.0,
        translate=0.10,
        scale=0.40,
        shear=0.0,
        perspective=0.0002,
        flipud=0.0,
        fliplr=0.5,
        hsv_h=0.015,
        hsv_s=0.6,
        hsv_v=0.4,
        mosaic=1.0,
        mixup=0.05,
        plots=True,
        save=True,
    )
    best = args.project / run_name / "weights" / "best.pt"
    trained = YOLO(str(best))
    metrics = metric_summary(trained, args.data, args.imgsz, args.device)
    metrics.update({
        "base_model": model_name,
        "best_weights": str(best),
        "weight_mb": round(best.stat().st_size / 1024 / 1024, 2),
    })
    return metrics


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", required=True, help="Path to dataset.yaml")
    ap.add_argument("--models", nargs="+", default=DEFAULT_MODELS)
    ap.add_argument("--epochs", type=int, default=100)
    ap.add_argument("--imgsz", type=int, default=640)
    ap.add_argument("--batch", type=int, default=16)
    ap.add_argument("--device", default="0", help="0 for first CUDA GPU, or cpu")
    ap.add_argument("--workers", type=int, default=8)
    ap.add_argument("--patience", type=int, default=20)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--project", type=Path, default=Path("runs/m1-rdd2022"))
    args = ap.parse_args()
    args.project.mkdir(parents=True, exist_ok=True)

    summaries = []
    for model_name in args.models:
        print(f"\n=== Training {model_name} ===")
        summaries.append(train_one(model_name, args))

    # Selection is explicit: accuracy first, then latency and size as deployment tie-breakers.
    summaries.sort(key=lambda x: (-x["mAP50_95"], x["inference_ms"], x["weight_mb"]))
    out = args.project / "comparison.json"
    out.write_text(json.dumps(summaries, indent=2), encoding="utf-8")
    print(json.dumps(summaries, indent=2))
    print(f"Comparison: {out}")


if __name__ == "__main__":
    main()

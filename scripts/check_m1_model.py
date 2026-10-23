"""Load an M1 checkpoint with ultralytics and check its classes against RDD_CLASS_MAP.

Runs inside the perception-worker image (ultralytics + CPU torch):
    docker compose ... --profile m1 run --rm -v ./scripts:/scripts:ro perception-worker \
        python /scripts/check_m1_model.py /models/road-damage-yolo26s.pt
"""
from __future__ import annotations

import sys
from pathlib import Path

import torch
from ultralytics import YOLO

from perception.detector import RDD_CLASS_MAP

EXPECTED_CLASSES = 4


def main() -> int:
    weights = Path(sys.argv[1] if len(sys.argv) > 1 else "/models/road-damage-yolo26s.pt")
    model = YOLO(str(weights))
    names = [str(n) for _, n in sorted(model.names.items())]
    print(f"weights : {weights}")
    print(f"task    : {model.task}")
    print(f"nc      : {len(names)}")
    print(f"names   : {names}")
    print(f"torch   : {torch.__version__} (cuda available: {torch.cuda.is_available()})")

    unknown = [n for n in names if n not in RDD_CLASS_MAP]
    if len(names) != EXPECTED_CLASSES or unknown:
        print(f"FAIL: expected {EXPECTED_CLASSES} classes in RDD_CLASS_MAP, unknown={unknown}")
        return 1
    print("OK: all class names are RDD_CLASS_MAP keys -> " + ", ".join(RDD_CLASS_MAP[n] for n in names))
    return 0


if __name__ == "__main__":
    sys.exit(main())

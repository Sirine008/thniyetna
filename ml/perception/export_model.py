from __future__ import annotations
import argparse
from ultralytics import YOLO


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--weights", required=True)
    ap.add_argument("--format", default="onnx", choices=["onnx", "openvino", "engine"])
    ap.add_argument("--imgsz", type=int, default=640)
    ap.add_argument("--half", action="store_true")
    args = ap.parse_args()
    model = YOLO(args.weights)
    path = model.export(format=args.format, imgsz=args.imgsz, half=args.half, simplify=True)
    print(path)


if __name__ == "__main__":
    main()

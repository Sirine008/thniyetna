from datetime import datetime, timedelta, timezone

from perception.gps import GpsSample, interpolate
from perception.severity import severity_proxy


def test_gps_interpolation_midpoint():
    t0 = datetime(2026, 1, 1, tzinfo=timezone.utc)
    samples = [
        GpsSample(t0, 37.0, 9.0),
        GpsSample(t0 + timedelta(seconds=10), 38.0, 10.0),
    ]
    lat, lon = interpolate(samples, t0 + timedelta(seconds=5))
    assert round(lat, 6) == 37.5
    assert round(lon, 6) == 9.5


def test_severity_proxy_is_bounded_and_size_sensitive():
    small = severity_proxy("pothole", 0.005, 0.9)
    large = severity_proxy("pothole", 0.15, 0.9)
    assert 0 <= small <= 1
    assert 0 <= large <= 1
    assert large > small


def _rdd_class_map():
    # detector.py imports ultralytics at module level; read the literal so this runs in any env.
    import ast
    from pathlib import Path

    src = (Path(__file__).resolve().parents[1] / "detector.py").read_text(encoding="utf-8")
    for node in ast.parse(src).body:
        if isinstance(node, ast.Assign) and getattr(node.targets[0], "id", None) == "RDD_CLASS_MAP":
            return ast.literal_eval(node.value)
    raise AssertionError("RDD_CLASS_MAP not found")


def test_class_map_covers_pretrained_yolo26s_names():
    # class names of models/road-damage-yolo26s.pt (HF dronefreak/rdd2022-yolo26s), in model order
    names = ["longitudinal_crack", "transverse_crack", "alligator_crack", "pothole"]
    mapping = _rdd_class_map()
    assert [mapping[n] for n in names] == names
    assert {mapping[k] for k in ("D00", "D10", "D20", "D40")} == set(names)


def test_benchmark_runtime_only_mode_needs_no_dataset():
    from perception.benchmark import build_parser, percentile

    args = build_parser().parse_args(["--weights", "w.pt", "--source", "pilot"])
    assert args.data is None and args.source == "pilot" and args.out is None
    assert (args.conf, args.iou, args.imgsz) == (0.25, 0.50, 640)
    assert percentile([10.0, 20.0, 30.0, 40.0], 0.5) == 25.0


def test_pilot_annotation_draws_boxes():
    import pytest

    pytest.importorskip("cv2")
    import numpy as np

    from perception.detector import Detection
    from perception.pilot import annotate

    image = np.zeros((200, 300, 3), dtype=np.uint8)
    out = annotate(image, [Detection("pothole", 0.8, (50.0, 60.0, 150.0, 160.0), 0.7)])
    assert out.shape == image.shape and out.any() and not image.any()

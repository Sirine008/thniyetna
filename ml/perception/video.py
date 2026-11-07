from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np


@dataclass(frozen=True)
class VideoFrame:
    frame_index: int
    time_s: float
    image: np.ndarray


def iter_sampled_frames(video_path: str | Path, target_fps: float = 5.0):
    """Yield frames at a time-based rate independent of source FPS."""
    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        raise ValueError(f"Cannot open video: {video_path}")
    source_fps = float(cap.get(cv2.CAP_PROP_FPS) or 0.0)
    if source_fps <= 0:
        source_fps = 30.0
    stride = max(1, int(round(source_fps / max(target_fps, 0.1))))
    i = 0
    try:
        while True:
            ok, frame = cap.read()
            if not ok:
                break
            if i % stride == 0:
                yield VideoFrame(i, i / source_fps, frame)
            i += 1
    finally:
        cap.release()


def video_info(video_path: str | Path) -> dict:
    """Source frame rate, frame count and duration (seconds) of a video file."""
    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        raise ValueError(f"Cannot open video: {video_path}")
    try:
        fps = float(cap.get(cv2.CAP_PROP_FPS) or 0.0) or 30.0
        count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
        fourcc = int(cap.get(cv2.CAP_PROP_FOURCC) or 0)
    finally:
        cap.release()
    codec = "".join(chr((fourcc >> 8 * i) & 0xFF) for i in range(4)).strip("\x00 ") or "inconnu"
    return {"fps": fps, "frames": count, "duration_s": count / fps if count else 0.0, "codec": codec}

"""Frame utilities retained as a thin compatibility layer."""
from .video import iter_sampled_frames


def extract_frames(video_path: str, target_fps: float = 5.0):
    return [item.image for item in iter_sampled_frames(video_path, target_fps=target_fps)]

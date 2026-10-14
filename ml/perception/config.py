from dataclasses import dataclass
import os
from pathlib import Path


@dataclass(frozen=True)
class Settings:
    database_url: str = os.getenv(
        "DATABASE_URL",
        "postgresql+psycopg://thniyetna:thniyetna_dev@localhost:5432/thniyetna",
    )
    media_root: Path = Path(os.getenv("MEDIA_ROOT", "/data/media")).resolve()
    weights: Path = Path(os.getenv("M1_MODEL_WEIGHTS", "/models/road-damage-yolo26n.pt"))
    model_name: str = os.getenv("M1_MODEL_NAME", "yolo26n-rdd2022")
    device: str = os.getenv("M1_DEVICE", "cpu")
    imgsz: int = int(os.getenv("M1_IMGSZ", "640"))
    confidence: float = float(os.getenv("M1_CONF", "0.25"))
    iou: float = float(os.getenv("M1_IOU", "0.50"))
    video_fps: float = float(os.getenv("M1_VIDEO_FPS", "5"))
    batch_size: int = int(os.getenv("M1_BATCH_SIZE", "8"))
    dedup_radius_m: float = float(os.getenv("M1_DEDUP_RADIUS_M", "20"))
    dedup_days: int = int(os.getenv("M1_DEDUP_DAYS", "14"))
    poll_seconds: float = float(os.getenv("M1_POLL_SECONDS", "1.0"))


settings = Settings()

"""Central configuration for the THNIYETNA API."""
import os
from pathlib import Path

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql+psycopg://thniyetna:thniyetna_dev@localhost:5432/thniyetna",
)
JWT_SECRET = os.getenv("JWT_SECRET", "change-me-in-.env")
JWT_ALGORITHM = "HS256"
MLFLOW_TRACKING_URI = os.getenv("MLFLOW_TRACKING_URI", "http://localhost:5000")
OSRM_URL = os.getenv("OSRM_URL", "http://localhost:5002")
MEDIA_ROOT = Path(os.getenv("MEDIA_ROOT", "/data/media")).resolve()
MEDIA_PUBLIC_PREFIX = os.getenv("MEDIA_PUBLIC_PREFIX", "/media/files").rstrip("/")

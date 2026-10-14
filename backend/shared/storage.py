"""Local persistent media storage.

The API stores binary media on a persistent Docker volume and only stores
relative keys/URLs in PostgreSQL. The storage boundary can be replaced later
without changing domain contracts.
"""
from __future__ import annotations

import shutil
import uuid
from pathlib import Path
from typing import BinaryIO

from .config import MEDIA_PUBLIC_PREFIX, MEDIA_ROOT

ALLOWED_KINDS = {"images", "videos", "frames", "exports"}


def ensure_media_dirs() -> None:
    for kind in ALLOWED_KINDS:
        (MEDIA_ROOT / kind).mkdir(parents=True, exist_ok=True)


def safe_extension(filename: str | None, fallback: str = "") -> str:
    suffix = Path(filename or "").suffix.lower()
    if len(suffix) > 10 or any(c not in ".abcdefghijklmnopqrstuvwxyz0123456789" for c in suffix):
        return fallback
    return suffix or fallback


def save_stream(stream: BinaryIO, kind: str, filename: str | None = None) -> tuple[str, Path, str]:
    if kind not in ALLOWED_KINDS:
        raise ValueError(f"Unsupported media kind: {kind}")
    ensure_media_dirs()
    ext = safe_extension(filename)
    key = f"{kind}/{uuid.uuid4().hex}{ext}"
    path = (MEDIA_ROOT / key).resolve()
    if MEDIA_ROOT not in path.parents:
        raise ValueError("Invalid media path")
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("wb") as dst:
        shutil.copyfileobj(stream, dst)
    return key, path, f"{MEDIA_PUBLIC_PREFIX}/{key}"


def resolve_media_key(key: str) -> Path:
    path = (MEDIA_ROOT / key).resolve()
    if path == MEDIA_ROOT or MEDIA_ROOT not in path.parents:
        raise ValueError("Invalid media key")
    return path

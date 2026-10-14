from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from bisect import bisect_left


@dataclass(frozen=True)
class GpsSample:
    timestamp: datetime
    latitude: float
    longitude: float


def interpolate(samples: list[GpsSample], timestamp: datetime) -> tuple[float, float] | None:
    """Linear interpolation between GPS samples; clamps at the ends."""
    if not samples:
        return None
    samples = sorted(samples, key=lambda s: s.timestamp)
    times = [s.timestamp for s in samples]
    i = bisect_left(times, timestamp)
    if i <= 0:
        return samples[0].latitude, samples[0].longitude
    if i >= len(samples):
        return samples[-1].latitude, samples[-1].longitude
    a, b = samples[i - 1], samples[i]
    span = (b.timestamp - a.timestamp).total_seconds()
    if span <= 0:
        return a.latitude, a.longitude
    alpha = (timestamp - a.timestamp).total_seconds() / span
    lat = a.latitude + alpha * (b.latitude - a.latitude)
    lon = a.longitude + alpha * (b.longitude - a.longitude)
    return lat, lon

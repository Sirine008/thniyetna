"""M1 inspection video: GPS alignment, tracked-defect aggregation and the geolocation rule.

Pure Python (no OpenCV / torch import), so it is unit-tested in ml/.venv. The worker (worker.py) feeds it:
  * the GPS track: a GPX file sent with the video (job options) or the session's heartbeat points;
  * the per-frame detections with the ByteTrack id of each box (None when the tracker did not match it).
Rules:
  * a frame is located only inside the GPS track (or within `max_gap_s` of its ends); otherwise it is unlocated;
  * one track = one physical defect, reported once with its best frame (highest confidence);
  * a box the tracker did not match becomes its own single-frame defect (tracking only merges, never drops);
  * an unlocated defect is stored as an observation but creates no road event.
"""
from __future__ import annotations

import xml.etree.ElementTree as ET
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

from .gps import GpsSample


# ------------------------------------------------------------------ GPX
def _tag(element) -> str:
    return element.tag.rsplit('}', 1)[-1]


def _parse_time(value: str) -> datetime:
    ts = datetime.fromisoformat(value.strip().replace('Z', '+00:00'))
    return ts if ts.tzinfo else ts.replace(tzinfo=timezone.utc)


MAX_GPX_BYTES = 5_000_000


def parse_gpx(text: str) -> list[GpsSample]:
    """Track points (trkpt) with a <time>, sorted by time. Route / waypoints without time are ignored.
    The GPX is uploaded by a user: documents with a DTD or entity declaration (never needed by GPX; the
    vector for XXE / entity-expansion attacks) and oversized files are refused before parsing."""
    if len(text.encode('utf-8')) > MAX_GPX_BYTES:
        raise ValueError('GPX file too large')
    head = text[:4096].upper()
    if '<!DOCTYPE' in head or '<!ENTITY' in text.upper():
        raise ValueError('GPX with DOCTYPE / ENTITY declarations is not accepted')
    root = ET.fromstring(text)
    samples = []
    for el in root.iter():
        if _tag(el) != 'trkpt':
            continue
        when = next((c.text for c in el if _tag(c) == 'time' and c.text), None)
        if when is None:
            continue
        samples.append(GpsSample(_parse_time(when), float(el.attrib['lat']), float(el.attrib['lon'])))
    samples.sort(key=lambda s: s.timestamp)
    return samples


def video_start(samples: list[GpsSample], explicit: str | None, offset_s: float) -> datetime:
    """Absolute time of the first video frame: the given start time, else the first GPX point; plus the offset.
    A positive offset means the video started after the first GPS point."""
    base = _parse_time(explicit) if explicit else samples[0].timestamp
    return base + timedelta(seconds=offset_s)


def locate(samples: list[GpsSample], when: datetime, max_gap_s: float = 10.0) -> tuple[float, float] | None:
    """Linear interpolation inside the track; None outside it (beyond max_gap_s of either end) or between two
    points more than max_gap_s * 6 apart (a GPS outage)."""
    if not samples:
        return None
    first, last = samples[0].timestamp, samples[-1].timestamp
    if when < first - timedelta(seconds=max_gap_s) or when > last + timedelta(seconds=max_gap_s):
        return None
    if when <= first:
        return samples[0].latitude, samples[0].longitude
    if when >= last:
        return samples[-1].latitude, samples[-1].longitude
    for a, b in zip(samples, samples[1:]):
        if a.timestamp <= when <= b.timestamp:
            span = (b.timestamp - a.timestamp).total_seconds()
            if span > max_gap_s * 6:
                return None
            alpha = 0.0 if span <= 0 else (when - a.timestamp).total_seconds() / span
            return a.latitude + alpha * (b.latitude - a.latitude), a.longitude + alpha * (b.longitude - a.longitude)
    return None


# ------------------------------------------------------------------ tracking aggregation
@dataclass(frozen=True)
class FrameDetection:
    frame_index: int
    time_s: float
    defect_type: str
    confidence: float
    bbox_xyxy: tuple[float, float, float, float]
    severity: float
    track_id: int | None


@dataclass
class TrackedDefect:
    key: str                          # "t<track id>" or "s<frame>-<n>" for a box the tracker did not match
    best: FrameDetection
    frames: int = 0
    first_s: float = 0.0
    last_s: float = 0.0
    classes: Counter = field(default_factory=Counter)

    @property
    def defect_type(self) -> str:
        return self.best.defect_type


def aggregate_tracks(detections: list[FrameDetection]) -> list[TrackedDefect]:
    """One TrackedDefect per track id (best = highest confidence; its class is the reported class);
    every untracked box is its own defect. Ordered by first appearance."""
    tracks: dict[str, TrackedDefect] = {}
    singles = Counter()
    for d in sorted(detections, key=lambda x: (x.frame_index, -x.confidence)):
        if d.track_id is None:
            singles[d.frame_index] += 1
            key = f's{d.frame_index}-{singles[d.frame_index]}'
        else:
            key = f't{d.track_id}'
        t = tracks.get(key)
        if t is None:
            t = tracks[key] = TrackedDefect(key=key, best=d, first_s=d.time_s, last_s=d.time_s)
        elif d.confidence > t.best.confidence:
            t.best = d
        t.frames += 1
        t.first_s = min(t.first_s, d.time_s)
        t.last_s = max(t.last_s, d.time_s)
        t.classes[d.defect_type] += 1
    return sorted(tracks.values(), key=lambda t: (t.first_s, t.key))


@dataclass(frozen=True)
class DefectRecord:
    defect: TrackedDefect
    captured_at: datetime
    latitude: float | None
    longitude: float | None

    @property
    def creates_road_event(self) -> bool:
        """No GPS position → observation only, never a road event."""
        return self.latitude is not None and self.longitude is not None


def geolocate(defects: list[TrackedDefect], samples: list[GpsSample], start: datetime | None, max_gap_s: float = 10.0) -> list[DefectRecord]:
    """Time and position of each defect at its best frame; unlocated when there is no GPS or no start time."""
    records = []
    for d in defects:
        when = (start or datetime.now(timezone.utc)) + timedelta(seconds=d.best.time_s)
        pos = locate(samples, when, max_gap_s) if samples and start is not None else None
        records.append(DefectRecord(d, when, *(pos if pos else (None, None))))
    return records


def per_class(items) -> dict[str, int]:
    return dict(sorted(Counter(i.defect_type for i in items).items()))

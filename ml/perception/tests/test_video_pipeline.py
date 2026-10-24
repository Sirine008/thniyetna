"""M1 inspection video: GPX alignment, tracking deduplication, « no GPS → no road event » (perception/video_pipeline.py)."""
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from perception.gps import GpsSample
from perception.video_pipeline import (
    FrameDetection, aggregate_tracks, geolocate, locate, parse_gpx, per_class, video_start,
)

T0 = datetime(2026, 10, 24, 9, 0, 0, tzinfo=timezone.utc)
GPX = """<?xml version="1.0" encoding="UTF-8"?>
<gpx version="1.1" creator="test" xmlns="http://www.topografix.com/GPX/1/1">
  <wpt lat="1" lon="1"><name>ignored waypoint</name></wpt>
  <trk><trkseg>
    <trkpt lat="37.2700" lon="9.8600"><time>2026-10-24T09:00:10Z</time></trkpt>
    <trkpt lat="37.2600" lon="9.8500"><time>2026-10-24T09:00:00Z</time></trkpt>
    <trkpt lat="37.2800" lon="9.8700"><time>2026-10-24T09:00:20+00:00</time></trkpt>
    <trkpt lat="37.2900" lon="9.8800"></trkpt>
  </trkseg></trk>
</gpx>"""


def det(frame, t, conf, track, kind='pothole', box=(0, 0, 10, 10)):
    return FrameDetection(frame, t, kind, conf, box, round(conf * 0.5, 3), track)


# ------------------------------------------------------------------ GPX
def test_gpx_track_points_sorted_by_time_without_waypoints_or_untimed_points():
    s = parse_gpx(GPX)
    assert [(p.latitude, p.longitude) for p in s] == [(37.26, 9.85), (37.27, 9.86), (37.28, 9.87)]
    assert s[0].timestamp == T0 and s[-1].timestamp == T0 + timedelta(seconds=20)


def test_gpx_with_doctype_or_entities_is_refused():
    evil = '<?xml version="1.0"?><!DOCTYPE gpx [<!ENTITY x "y">]><gpx><trk><trkseg><trkpt lat="1" lon="1"><time>&x;</time></trkpt></trkseg></trk></gpx>'
    with pytest.raises(ValueError):
        parse_gpx(evil)


def test_video_time_aligned_on_the_first_gpx_point_plus_offset():
    s = parse_gpx(GPX)
    assert video_start(s, None, 0) == T0
    assert video_start(s, None, 4.5) == T0 + timedelta(seconds=4.5)          # video started 4.5 s after the first point
    assert video_start(s, '2026-10-24T09:00:05Z', -2) == T0 + timedelta(seconds=3)


def test_frame_position_interpolated_along_the_track():
    s = parse_gpx(GPX)
    lat, lon = locate(s, T0 + timedelta(seconds=5))
    assert lat == pytest.approx(37.265) and lon == pytest.approx(9.855)
    lat, lon = locate(s, T0 + timedelta(seconds=15))
    assert lat == pytest.approx(37.275) and lon == pytest.approx(9.865)


def test_frames_outside_the_track_or_in_a_gps_outage_are_unlocated():
    s = parse_gpx(GPX)
    assert locate(s, T0 - timedelta(seconds=11), max_gap_s=10) is None
    assert locate(s, T0 + timedelta(seconds=31), max_gap_s=10) is None
    assert locate(s, T0 + timedelta(seconds=25), max_gap_s=10) == (37.28, 9.87)          # within the end tolerance
    outage = [GpsSample(T0, 37.0, 9.0), GpsSample(T0 + timedelta(seconds=120), 37.1, 9.1)]
    assert locate(outage, T0 + timedelta(seconds=60), max_gap_s=10) is None               # 120 s gap > 6 x 10 s
    assert locate([], T0) is None


# ------------------------------------------------------------------ tracking deduplication
def test_one_physical_defect_tracked_over_frames_is_reported_once_with_its_best_frame():
    raw = [det(3, 1.0, 0.31, 7), det(6, 2.0, 0.62, 7, box=(5, 5, 40, 40)), det(9, 3.0, 0.48, 7),
           det(6, 2.0, 0.40, 8, 'longitudinal_crack'), det(9, 3.0, 0.45, 8, 'longitudinal_crack')]
    defects = aggregate_tracks(raw)
    assert len(raw) == 5 and len(defects) == 2
    pothole = next(d for d in defects if d.key == 't7')
    assert pothole.best.confidence == 0.62 and pothole.best.frame_index == 6 and pothole.best.bbox_xyxy == (5, 5, 40, 40)
    assert (pothole.frames, pothole.first_s, pothole.last_s) == (3, 1.0, 3.0)
    assert per_class(raw) == {'longitudinal_crack': 2, 'pothole': 3}
    assert per_class(defects) == {'longitudinal_crack': 1, 'pothole': 1}


def test_a_track_whose_class_changes_reports_the_class_of_its_best_frame():
    defects = aggregate_tracks([det(1, 0.3, 0.30, 4, 'longitudinal_crack'), det(2, 0.6, 0.55, 4, 'alligator_crack')])
    assert len(defects) == 1 and defects[0].defect_type == 'alligator_crack'
    assert dict(defects[0].classes) == {'longitudinal_crack': 1, 'alligator_crack': 1}


def test_untracked_boxes_are_kept_as_single_frame_defects():
    defects = aggregate_tracks([det(5, 1.6, 0.27, None), det(5, 1.6, 0.26, None), det(8, 2.6, 0.30, None)])
    assert len(defects) == 3 and all(d.frames == 1 for d in defects)
    assert aggregate_tracks([]) == []


# ------------------------------------------------------------------ no GPS → no road event
def test_no_gps_means_observations_without_road_events():
    defects = aggregate_tracks([det(3, 1.0, 0.5, 1), det(6, 2.0, 0.6, 2)])
    unlocated = geolocate(defects, [], None)
    assert all(r.latitude is None and r.longitude is None and not r.creates_road_event for r in unlocated)
    s = parse_gpx(GPX)
    located = geolocate(defects, s, T0 + timedelta(seconds=4))     # best frames at 5 s and 6 s of the track
    assert all(r.creates_road_event for r in located)
    assert located[0].captured_at == T0 + timedelta(seconds=5)
    late = geolocate(defects, s, T0 + timedelta(seconds=60))       # video starts after the track ended
    assert not any(r.creates_road_event for r in late)


def test_worker_creates_road_events_only_for_located_observations():
    """The DB writer only looks for / creates a road event inside the « position known » branch."""
    src = (Path(__file__).resolve().parents[1] / 'worker.py').read_text(encoding='utf-8')
    body = src[src.index('def _upsert_observation'):src.index('def _process_image')]
    guard = body.index('if latitude is not None and longitude is not None:')
    assert guard < body.index('INSERT INTO road_events') and guard < body.index('SELECT id::text FROM road_events')
    video = src[src.index('def _process_video'):src.index('def main')]
    assert 'latitude=rec.latitude, longitude=rec.longitude' in video

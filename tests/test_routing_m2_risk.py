"""M3 must use M2 segment risk, not only segments that already hold an M1 event."""
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
pytest.importorskip("fastapi")
sys.path.insert(0, str(ROOT / "backend"))
from routing import router as R  # noqa: E402

DIRECT = [[37.270, 9.850], [37.270, 9.865], [37.270, 9.880]]
NORTH = [[37.270, 9.850], [37.280, 9.850], [37.280, 9.880], [37.270, 9.880]]


class FakeResult:
    def __init__(self, rows):
        self.rows = rows

    def mappings(self):
        return self

    def all(self):
        return self.rows


class FakeDB:
    """Returns M2 segment scores by polyline: high on DIRECT, low on NORTH."""

    def execute(self, stmt, params):
        if "9.865" in params["wkt"]:
            return FakeResult([{"overlap_m": 2600.0, "risk_score": 0.8}])
        return FakeResult([{"overlap_m": 2400.0, "risk_score": 0.01},
                           {"overlap_m": 900.0, "risk_score": 0.03}])

    def rollback(self):
        pass


def osrm(points, duration):
    return {"geometry": {"coordinates": [[lon, lat] for lat, lon in points]},
            "distance": 3000.0, "duration": duration}


def test_segment_risk_blends_peak_and_weighted_mean():
    risk, n = R._segment_risk(FakeDB(), NORTH)
    assert n == 2
    mean = (0.01 * 2400 + 0.03 * 900) / 3300
    assert risk == round(0.72 * 0.03 + 0.28 * mean, 3)


def test_segment_risk_without_db_or_geometry_is_zero():
    assert R._segment_risk(None, DIRECT) == (0.0, 0)
    assert R._segment_risk(FakeDB(), DIRECT[:1]) == (0.0, 0)


def test_m2_segment_risk_triggers_reroute_without_any_point_hazard(monkeypatch):
    monkeypatch.setattr(R, "_risk_points", lambda db: [])
    monkeypatch.setattr(R, "_fetch_osrm", lambda coords, alternatives=0:
                        [osrm(DIRECT, 300), osrm(NORTH, 420)] if len(coords) == 2 else [])
    req = R.RouteRequest(current_lat=37.27, current_lon=9.85, destination_lat=37.27, destination_lon=9.88)
    res = R.get_route(req, FakeDB())
    assert res.reroute_needed
    assert res.fastest_segment_risk == 0.8
    assert res.polyline == NORTH
    assert "M2" in res.reason


def test_event_hazard_is_not_masked_by_a_small_m2_score():
    sql = (ROOT / "backend/routing/router.py").read_text()
    assert "GREATEST(coalesce(rs.risk_score,0),coalesce(e.severity,0.3))" in sql

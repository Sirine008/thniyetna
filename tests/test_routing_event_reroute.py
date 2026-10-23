"""M3 reroute driven by an M1 event (point hazard), as checked live on 2026-10-23 (docs/STATUS.md).

Thresholds are the production ones (reroute if the fastest risk >= 0.42 and an alternative is at
least 0.12 safer); these tests do not change them.
"""
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
pytest.importorskip("fastapi")
sys.path.insert(0, str(ROOT / "backend"))
from routing import router as R  # noqa: E402
from shared.utils import haversine_m  # noqa: E402

# fastest route: dense vertices (~90 m) along 37.270, from 9.850 to 9.880
DIRECT = [[37.270, round(9.850 + i * 0.001, 3)] for i in range(31)]
# a real way around, ~1.1 km north
NORTH = [[37.270, 9.850], [37.280, 9.850], [37.280, 9.880], [37.270, 9.880]]
EVENT = {"lat": 37.270, "lon": 9.865, "risk": 0.9, "event_type": "pothole"}  # severity 0.9, on DIRECT


def osrm(points, duration):
    return {"geometry": {"coordinates": [[lon, lat] for lat, lon in points]}, "distance": 3000.0, "duration": duration}


class FakeDB:
    def commit(self):
        pass

    def rollback(self):
        pass


@pytest.fixture
def m3(monkeypatch):
    """Point hazards only (no M2 segment score), OSRM stubbed, alerts captured."""
    published = []
    monkeypatch.setattr(R, "_segment_risk", lambda db, line: (0.0, 0))
    monkeypatch.setattr(R, "publish", lambda db, topic, payload, recipient=None:
                        published.append({"topic": topic, "payload": payload, "recipient": recipient}))

    def setup(hazards, routes, detours=()):
        monkeypatch.setattr(R, "_risk_points", lambda db: hazards)
        monkeypatch.setattr(R, "_fetch_osrm", lambda coords, alternatives=0:
                            list(routes) if len(coords) == 2 else list(detours))
        return published
    return setup


REQ = R.RouteRequest(vehicle_id="DEMO-BUS-01", current_lat=37.270, current_lon=9.850,
                     destination_lat=37.270, destination_lon=9.880, alternatives=3)
DRIVER = {"sub": "demo.driver1", "role": "bus_driver"}


def min_distance_m(line, point):
    return min(haversine_m(p[0], p[1], point["lat"], point["lon"]) for p in line)


def test_severe_event_on_fastest_route_reroutes_around_it_and_alerts_the_driver(m3):
    published = m3([EVENT], [osrm(DIRECT, 300), osrm(NORTH, 420)])
    res = R.driver_next_best(REQ, FakeDB(), DRIVER)
    assert res.fastest_risk >= 0.42 and res.risk + 0.12 < res.fastest_risk
    assert res.reroute_needed and res.status == "rerouted"
    assert res.polyline == NORTH and res.fastest_polyline == DIRECT
    assert min_distance_m(res.polyline, EVENT) > 105         # the alternative avoids the event
    assert min_distance_m(res.fastest_polyline, EVENT) < 1   # the fastest route goes through it
    assert [p["topic"] for p in published] == ["driver.reroute.alert"]
    alert = published[0]
    assert alert["recipient"] == "demo.driver1" and alert["payload"]["vehicle_id"] == "DEMO-BUS-01"
    assert alert["payload"]["risk"] == res.fastest_risk and "danger" in alert["payload"]["reason"]


def test_no_alert_when_every_alternative_crosses_the_same_event(m3):
    # NORTH_VIA_EVENT goes north but comes back through the event: not 0.12 safer -> keep the route
    via = [[37.270, 9.850], [37.280, 9.850], [37.280, 9.865], [37.270, 9.865], [37.270, 9.880]]
    published = m3([EVENT], [osrm(DIRECT, 300), osrm(via, 420)], detours=[osrm(via, 420)])
    res = R.driver_next_best(REQ, FakeDB(), DRIVER)
    assert res.fastest_risk >= 0.42
    assert not res.reroute_needed and res.polyline == DIRECT
    assert published == []


def test_alternative_crossing_the_event_between_sparse_vertices_is_not_safer(m3):
    # regression (2026-10-23): distance used to be measured to sampled vertices only
    # straight stretch 9.855 -> 9.875 with no vertex near the event at 9.865 (~890 m each side)
    sparse = [[37.270, 9.850], [37.285, 9.850], [37.285, 9.855], [37.270, 9.855],
              [37.270, 9.875], [37.285, 9.875], [37.285, 9.880], [37.270, 9.880]]
    assert min_distance_m(sparse, EVENT) > 105  # what vertex sampling sees, although the line passes 0 m away
    published = m3([EVENT], [osrm(DIRECT, 300), osrm(sparse, 480)])
    res = R.driver_next_best(REQ, FakeDB(), DRIVER)
    assert not res.reroute_needed and published == []


def test_hazard_distance_is_measured_to_the_route_line_in_postgis():
    sql = str(R._HAZARD_DISTANCE_SQL)
    assert "ST_Distance(r.g,h.p)" in sql and "::geography" in sql and "ST_DWithin(r.g,h.p,:radius)" in sql
    # fallback without PostGIS: exact point-to-segment distance, a vertex ~890 m away does not matter
    line = [[37.270, 9.855], [37.270, 9.875]]
    assert R._hazard_distances(line, [EVENT]) == {0: pytest.approx(0.0, abs=0.5)}
    assert R._hazard_distances(line, [{**EVENT, "lat": 37.2715}]) == {}  # ~166 m north: outside 105 m

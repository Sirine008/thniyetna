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


class FakeResult:
    def __init__(self, rows):
        self.rows = rows

    def mappings(self):
        return self

    def all(self):
        return self.rows


class FakeDB:
    """In-memory notification_outbox for the driver-alert queries; anything else raises (PostGIS fallback)."""

    def __init__(self):
        self.outbox = []

    def execute(self, stmt, params):
        sql = str(stmt).lstrip()
        if sql.startswith("SELECT") and "FROM notification_outbox" in sql:
            rows = [r for r in self.outbox if r["recipient"] == params["u"] and r["topic"] in R.DRIVER_ALERT_TOPICS
                    and r["status"] == "pending" and r["payload"].get("line_key") == params["k"]
                    and not r["payload"].get("superseded")]
            rows.sort(key=lambda r: -r["seq"])
            return FakeResult([{"id": r["id"], "topic": r["topic"], "hazard_key": r["payload"].get("hazard_key")}
                               for r in rows])
        if sql.startswith("UPDATE notification_outbox") and "confirmations" in sql:
            row = next(r for r in self.outbox if r["id"] == params["id"])
            row["payload"].update(confirmations=row["payload"].get("confirmations", 1) + 1, last_confirmed_at="now",
                                  risk=params["risk"], reason=params["reason"])
            return FakeResult([])
        if sql.startswith("UPDATE notification_outbox") and "superseded" in sql:
            for r in self.outbox:
                if r["id"] in params["ids"]:
                    r["payload"].update(superseded=True, superseded_note=params["note"])
            return FakeResult([])
        raise NotImplementedError(sql[:40])

    def commit(self):
        pass

    def rollback(self):
        pass

    def active(self):
        return [r for r in self.outbox if r["status"] == "pending" and not r["payload"].get("superseded")]


@pytest.fixture
def m3(monkeypatch):
    """Point hazards only (no M2 segment score), OSRM stubbed, alerts captured (and stored in a FakeDB)."""
    published = []
    monkeypatch.setattr(R, "_segment_risk", lambda db, line: (0.0, 0))

    def publish(db, topic, payload, recipient=None):
        published.append({"topic": topic, "payload": payload, "recipient": recipient})
        if isinstance(db, FakeDB):
            db.outbox.append({"id": f"a{len(db.outbox)}", "seq": len(db.outbox), "topic": topic,
                              "recipient": recipient, "payload": dict(payload), "status": "pending"})
    monkeypatch.setattr(R, "publish", publish)

    def setup(hazards, routes, detours=()):
        monkeypatch.setattr(R, "_risk_points", lambda db: hazards)
        monkeypatch.setattr(R, "_fetch_osrm", lambda coords, alternatives=0:
                            list(routes) if len(coords) == 2 else list(detours))
        published.clear()
        return published
    return setup


REQ = R.RouteRequest(vehicle_id="DEMO-BUS-01", current_lat=37.270, current_lon=9.850,
                     destination_lat=37.270, destination_lon=9.880, alternatives=3)
DRIVER = {"sub": "demo.driver1", "role": "bus_driver"}


def min_distance_m(line, point):
    """True distance from the point to the polyline (not to its vertices)."""
    return min(R._point_segment_m(point["lat"], point["lon"], line[i], line[i + 1]) for i in range(len(line) - 1))


def min_vertex_distance_m(line, point):
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
    assert alert["payload"]["risk"] == res.fastest_risk
    # consistent counts: the alternative avoids the event, the initial route has it
    assert res.reason.startswith("1 danger(s) sur le trajet initial, 0 sur l'alternative ; risque ")
    assert alert["payload"]["hazards_on_initial"] == 1 and alert["payload"]["hazards_on_alternative"] == 0
    assert alert["payload"]["logic_version"] == "m3-v2"


def test_warning_without_reroute_when_every_alternative_crosses_the_event(m3):
    # the alternative goes north but comes back through the event: no eligible alternative
    via = [[37.270, 9.850], [37.280, 9.850], [37.280, 9.865], [37.270, 9.865], [37.270, 9.880]]
    published = m3([EVENT], [osrm(DIRECT, 300), osrm(via, 420)], detours=[osrm(via, 420)])
    res = R.driver_next_best(REQ, FakeDB(), DRIVER)
    assert res.fastest_risk >= 0.42
    assert not res.reroute_needed and res.polyline == DIRECT
    assert res.warning and res.status == "warning"
    assert [(h.type, h.latitude, h.longitude, h.risk) for h in res.hazards] == [("pothole", 37.270, 9.865, 0.9)]
    assert [p["topic"] for p in published] == ["driver.route.warning"]
    warning = published[0]
    assert warning["recipient"] == "demo.driver1"
    assert warning["payload"]["title"] == "Danger sur l'itinéraire — aucune alternative sûre"
    assert warning["payload"]["reason"].startswith("Danger sur l'itinéraire — aucune alternative sûre : 1 danger(s)")
    assert warning["payload"]["hazards"][0]["type"] == "pothole" and warning["payload"]["hazards"][0]["distance_m"] < 1


def test_no_alert_below_042(m3):
    weak = {**EVENT, "risk": 0.3}
    published = m3([weak], [osrm(DIRECT, 300), osrm(NORTH, 420)])
    res = R.driver_next_best(REQ, FakeDB(), DRIVER)
    assert res.fastest_risk < 0.42 and not res.reroute_needed and not res.warning
    assert res.status == "normal_route" and published == []


def test_alternative_crossing_the_event_between_sparse_vertices_is_not_safer(m3):
    # regression (2026-10-23): distance used to be measured to sampled vertices only
    # straight stretch 9.855 -> 9.875 with no vertex near the event at 9.865 (~890 m each side)
    sparse = [[37.270, 9.850], [37.285, 9.850], [37.285, 9.855], [37.270, 9.855],
              [37.270, 9.875], [37.285, 9.875], [37.285, 9.880], [37.270, 9.880]]
    assert min_vertex_distance_m(sparse, EVENT) > 105  # what vertex sampling sees, although the line passes 0 m away
    published = m3([EVENT], [osrm(DIRECT, 300), osrm(sparse, 480)])
    res = R.driver_next_best(REQ, FakeDB(), DRIVER)
    assert not res.reroute_needed
    assert [p["topic"] for p in published] == ["driver.route.warning"]  # not a reroute alert


def test_hazard_distance_is_measured_to_the_route_line_in_postgis():
    sql = str(R._HAZARD_DISTANCE_SQL)
    assert "ST_Distance(r.g,h.p)" in sql and "::geography" in sql and "ST_DWithin(r.g,h.p,:radius)" in sql
    # fallback without PostGIS: exact point-to-segment distance, a vertex ~890 m away does not matter
    line = [[37.270, 9.855], [37.270, 9.875]]
    assert R._hazard_distances(line, [EVENT]) == {0: pytest.approx(0.0, abs=0.5)}
    assert R._hazard_distances(line, [{**EVENT, "lat": 37.2715}]) == {}  # ~166 m north: outside 105 m


def test_alternative_must_avoid_every_triggering_hazard(m3):
    # two 0.9 events on the fastest route; ALT avoids the second one but still crosses EVENT.
    # Overall ALT is 0.12 safer (0.774 vs 0.9) — the old rule rerouted onto it.
    second = {**EVENT, "lon": 9.875}
    alt = [[37.270, 9.850], [37.270, 9.869], [37.280, 9.869], [37.280, 9.880], [37.270, 9.880]]
    published = m3([EVENT, second], [osrm(DIRECT, 300), osrm(alt, 420)], detours=[osrm(alt, 420)])
    res = R.get_route(REQ, None)
    alt_candidate = next(c for c in res.alternatives if c.polyline == alt)
    assert alt_candidate.risk + R.REROUTE_MIN_GAIN < res.fastest_risk      # safer overall …
    assert min_distance_m(alt, EVENT) < 105                                 # … but crosses a triggering hazard
    assert not res.reroute_needed and res.polyline == DIRECT
    assert published == []


def test_triggering_hazards_are_each_hazard_that_alone_exceeds_042_else_all():
    strong, weak = {"risk": 0.9}, {"risk": 0.3}
    assert R._triggering_hazards([strong, weak], {0: 0.0, 1: 0.0}) == {0}       # the weak one is not needed
    assert R._triggering_hazards([strong, strong], {0: 0.0, 1: 20.0}) == {0, 1}  # order-independent
    many = [{"risk": 0.4}] * 6                                                   # 0.344 alone, 0.568 together
    assert R._exposure_risk([0.4]) < R.REROUTE_MIN_RISK
    assert R._triggering_hazards(many, {i: 0.0 for i in range(6)}) == set(range(6))
    assert R._triggering_hazards([weak], {0: 0.0}) == set()                      # below 0.42: nothing triggers


def test_detour_is_searched_around_a_hazard_far_from_the_trip_midpoint(monkeypatch, m3):
    # the hazard is near the start (lon 9.853); the trip midpoint is at lon 9.865
    near_start = {**EVENT, "lon": 9.853}
    around = [[37.270, 9.850], [37.275, 9.850], [37.275, 9.857], [37.270, 9.857], [37.270, 9.880]]
    through = [[37.270, 9.850], [37.270, 9.853], [37.280, 9.860], [37.280, 9.880], [37.270, 9.880]]

    def fake_osrm(coords, alternatives=0):
        if len(coords) == 2:
            return [osrm(DIRECT, 300)]
        w = coords[1]  # only a waypoint beside the hazard, north side, leads around it
        return [osrm(around, 420)] if abs(w[1] - 9.853) < 0.002 and w[0] > 37.2705 else [osrm(through, 420)]

    published = m3([near_start], [])
    monkeypatch.setattr(R, "_fetch_osrm", fake_osrm)
    res = R.driver_next_best(REQ, FakeDB(), DRIVER)
    assert res.reroute_needed and res.polyline == around
    assert min_distance_m(res.polyline, near_start) > 105
    assert [p["topic"] for p in published] == ["driver.reroute.alert"]

    # the midpoint search alone (previous behaviour) only finds routes through the hazard
    monkeypatch.setattr(R, "_hazard_detours", lambda req, line, hazards: [])
    assert not R.get_route(REQ, None).reroute_needed


def test_grid_different_enough_matches_the_brute_force_definition():
    import random

    def brute(a, b):  # the previous implementation, kept as the reference
        bs = b[::max(1, len(b) // 120)]; aa = a[::max(1, len(a) // 120)]
        near = sum(1 for p in aa if min(haversine_m(p[0], p[1], q[0], q[1]) for q in bs) < 45)
        return near / max(1, len(aa)) < .78

    rng = random.Random(7)
    for _ in range(300):
        base = [[37.27 + i * 0.0004, 9.85 + rng.uniform(-0.0003, 0.0003)] for i in range(rng.randint(5, 300))]
        shift = rng.choice([0.0, 0.0002, 0.0004, 0.0006, 0.002])
        other = [[lat + rng.uniform(-shift, shift), lon + rng.uniform(-shift, shift)] for lat, lon in base]
        assert R._different_enough(base, other) == brute(base, other)


def test_response_reports_eligible_alternatives(m3):
    via = [[37.270, 9.850], [37.280, 9.850], [37.280, 9.865], [37.270, 9.865], [37.270, 9.880]]
    m3([EVENT], [osrm(DIRECT, 300), osrm(via, 420)], detours=[osrm(via, 420)])
    res = R.get_route(REQ, None)
    assert res.eligible_alternatives == 0 and res.best_eligible_risk is None
    m3([EVENT], [osrm(DIRECT, 300), osrm(NORTH, 420)])
    res = R.get_route(REQ, None)
    assert res.eligible_alternatives == 1 and res.best_eligible_risk == res.risk == 0.0


VIA = [[37.270, 9.850], [37.280, 9.850], [37.280, 9.865], [37.270, 9.865], [37.270, 9.880]]  # crosses EVENT


def test_same_decision_and_hazards_refresh_the_active_alert(m3):
    db = FakeDB()
    published = m3([EVENT], [osrm(DIRECT, 300), osrm(VIA, 420)], detours=[osrm(VIA, 420)])
    first = R.driver_next_best(REQ, db, DRIVER)
    second = R.driver_next_best(REQ, db, DRIVER)
    assert (first.alert_state, second.alert_state) == ("new", "refreshed")
    assert [p["topic"] for p in published] == ["driver.route.warning"]  # published once
    assert len(db.active()) == 1 and db.active()[0]["payload"]["confirmations"] == 2


def test_new_alert_when_hazards_change_and_the_old_one_is_superseded(m3):
    db = FakeDB()
    m3([EVENT], [osrm(DIRECT, 300), osrm(VIA, 420)], detours=[osrm(VIA, 420)])
    R.driver_next_best(REQ, db, DRIVER)
    published = m3([EVENT, {**EVENT, "lon": 9.875}], [osrm(DIRECT, 300), osrm(VIA, 420)], detours=[osrm(VIA, 420)])
    res = R.driver_next_best(REQ, db, DRIVER)
    assert res.alert_state == "new" and len(published) == 1
    assert [r["payload"].get("superseded", False) for r in db.outbox] == [True, False]


def test_new_alert_when_the_decision_changes(m3):
    db = FakeDB()
    m3([EVENT], [osrm(DIRECT, 300), osrm(VIA, 420)], detours=[osrm(VIA, 420)])
    assert R.driver_next_best(REQ, db, DRIVER).alert_state == "new"          # warning
    m3([EVENT], [osrm(DIRECT, 300), osrm(NORTH, 420)])
    res = R.driver_next_best(REQ, db, DRIVER)                                # same hazard, now a detour
    assert res.reroute_needed and res.alert_state == "new"
    assert [r["topic"] for r in db.active()] == ["driver.reroute.alert"]


def test_alert_is_resolved_when_the_route_becomes_normal(m3):
    db = FakeDB()
    m3([EVENT], [osrm(DIRECT, 300), osrm(VIA, 420)], detours=[osrm(VIA, 420)])
    R.driver_next_best(REQ, db, DRIVER)
    published = m3([], [osrm(DIRECT, 300)])
    res = R.driver_next_best(REQ, db, DRIVER)
    assert res.alert_state == "resolved" and published == [] and db.active() == []
    assert db.outbox[0]["payload"]["superseded_note"] == "Itinéraire redevenu normal"


def test_acknowledged_alert_is_not_refreshed_and_other_lines_are_separate(m3):
    db = FakeDB()
    published = m3([EVENT], [osrm(DIRECT, 300), osrm(VIA, 420)], detours=[osrm(VIA, 420)])
    R.driver_next_best(REQ, db, DRIVER)
    db.outbox[0]["status"] = "delivered"                                  # the driver acknowledged it
    assert R.driver_next_best(REQ, db, DRIVER).alert_state == "new"
    other_line = REQ.model_copy(update={"vehicle_id": "DEMO-BUS-02"})
    assert R.driver_next_best(other_line, db, DRIVER).alert_state == "new"
    assert len(published) == 3


def test_alert_action_rules():
    a = [{"id": "x", "topic": "driver.route.warning", "hazard_key": "k"},
         {"id": "y", "topic": "driver.route.warning", "hazard_key": "k"}]
    assert R._alert_action(a, "driver.route.warning", "k") == ("refresh", ["x"])
    assert R._alert_action(a, "driver.route.warning", "k2") == ("new", ["x", "y"])
    assert R._alert_action(a, "driver.reroute.alert", "k") == ("new", ["x", "y"])
    assert R._alert_action(a, None, "") == ("resolve", ["x", "y"])
    assert R._alert_action([], None, "") == ("none", [])

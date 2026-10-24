"""GET /platform/driver-alerts: read-only list of the drivers' M3 alerts for the transport supervisor."""
import inspect
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
pytest.importorskip("fastapi")
sys.path.insert(0, str(ROOT / "backend"))
from fastapi import HTTPException  # noqa: E402
from platform_app import router as P  # noqa: E402


def checker():
    return inspect.signature(P.driver_alerts).parameters["user"].default.dependency


@pytest.mark.parametrize("role", ["citizen", "bus_driver", "inspection_vehicle", "equipment_supervisor"])
def test_only_the_transport_supervisor_can_list_driver_alerts(role):
    with pytest.raises(HTTPException) as err:
        checker()(user={"sub": "x", "role": role})
    assert err.value.status_code == 403
    assert checker()(user={"sub": "transport.supervisor", "role": "transport_supervisor"})["role"] == "transport_supervisor"


class FakeResult:
    def __init__(self, rows):
        self.rows = rows

    def mappings(self):
        return iter(self.rows)


class FakeDB:
    def __init__(self, rows):
        self.rows, self.calls = rows, []

    def execute(self, stmt, params):
        self.calls.append((str(stmt), params))
        return FakeResult(self.rows)


def row(topic, status="pending", superseded=False, confirmations=1):
    return {"id": "a", "topic": topic, "status": status, "created_at": datetime(2026, 10, 24, tzinfo=timezone.utc), "delivered_at": None,
            "driver": "demo.driver1", "vehicle_code": "DEMO-BUS-01", "superseded": superseded, "superseded_note": None,
            "confirmations": confirmations, "last_confirmed_at": None, "risk": 0.73, "alternative_risk": 0.02, "reason": "r",
            "hazards_on_initial": 2, "demo": True, "route_code": "DEMO-L1", "route_name": "DÉMO — L1"}


def test_kind_acknowledged_and_active_are_derived_from_the_stored_alert():
    db = FakeDB([row("driver.reroute.alert"), row("driver.route.warning", status="delivered"),
                 row("driver.route.warning", superseded=True, confirmations=3)])
    out = P.driver_alerts(limit=50, db=db, user={"role": "transport_supervisor"})
    assert [(r["kind"], r["acknowledged"], r["active"]) for r in out] == [
        ("reroute", False, True), ("warning", True, False), ("warning", False, False)]
    assert out[2]["confirmations"] == 3 and out[0]["route_code"] == "DEMO-L1"
    assert db.calls[0][1] == {"limit": 50}


def test_query_is_read_only_and_limited_to_driver_alerts():
    sql = str(P.DRIVER_ALERTS_SQL)
    assert "topic IN ('driver.reroute.alert', 'driver.route.warning')" in sql
    assert not any(word in sql.upper() for word in ("UPDATE ", "INSERT ", "DELETE "))


def test_query_runs_on_the_database():
    """Runs only when the stack database is reachable (DATABASE_URL or the default host port)."""
    sqlalchemy = pytest.importorskip("sqlalchemy")
    url = os.getenv("DATABASE_URL", "postgresql+psycopg://thniyetna:thniyetna_dev@localhost:5433/thniyetna")
    try:
        engine = sqlalchemy.create_engine(url, connect_args={"connect_timeout": 3})
        with engine.connect() as conn:
            rows = conn.execute(P.DRIVER_ALERTS_SQL, {"limit": 500}).mappings().all()
    except sqlalchemy.exc.OperationalError:
        pytest.skip("database not reachable")
    assert all(r["topic"] in ("driver.reroute.alert", "driver.route.warning") for r in rows)

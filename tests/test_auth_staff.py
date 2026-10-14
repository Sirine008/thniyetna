"""Staff account management: per-ministry permission map, citizen-only self-registration,
no password in any response. Router functions are called directly with a fake session."""
import sys
import typing
from datetime import datetime, timezone
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
pytest.importorskip("fastapi")
sys.path.insert(0, str(ROOT / "backend"))
from fastapi import HTTPException  # noqa: E402
from pydantic import BaseModel  # noqa: E402

from auth import router as R  # noqa: E402
from auth.schemas import (CitizenRegisterRequest, StaffActiveUpdate, StaffCreateRequest,  # noqa: E402
                          StaffOut, StaffPasswordReset)
from shared import auth as A  # noqa: E402

TRANSPORT = {"sub": "transport.supervisor", "role": "transport_supervisor"}
EQUIPMENT = {"sub": "equipment.supervisor", "role": "equipment_supervisor"}
CITIZEN = {"sub": "some.citizen", "role": "citizen"}
NOW = datetime(2026, 10, 14, tzinfo=timezone.utc)


def staff_row(username, role, active=True):
    return {"username": username, "display_name": username, "role": role, "organization": "SRTB",
            "active": active, "created_at": NOW}


class _Result:
    def __init__(self, value):
        self.value = value

    def mappings(self):
        return self

    def one(self):
        return self.value

    def first(self):
        return self.value

    def scalar(self):
        return self.value

    def __iter__(self):
        return iter(self.value or [])


class FakeDB:
    """Returns the queued results in order and records every (sql, params)."""

    def __init__(self, *results):
        self.results, self.calls, self.committed = list(results), [], False

    def execute(self, sql, params=None):
        self.calls.append((str(sql), params or {}))
        return _Result(self.results.pop(0) if self.results else None)

    def commit(self):
        self.committed = True

    def rollback(self):
        pass


def _staff(role, username="new.account"):
    return StaffCreateRequest(username=username, password="s3cret-pass", display_name="New Account", role=role)


# ------------------------------------------------------------------ permission map
@pytest.mark.parametrize("user, role", [(TRANSPORT, "inspection_vehicle"), (TRANSPORT, "equipment_supervisor"),
                                        (EQUIPMENT, "bus_driver"), (EQUIPMENT, "transport_supervisor")])
def test_ministry_cannot_create_roles_of_the_other_ministry(user, role):
    db = FakeDB()
    with pytest.raises(HTTPException) as exc:
        R.create_staff(_staff(role), db=db, user=user)
    assert exc.value.status_code == 403
    assert db.calls == []  # refused before touching the database


@pytest.mark.parametrize("role", ["bus_driver", "inspection_vehicle", "equipment_supervisor"])
def test_citizen_gets_403_on_every_staff_endpoint(role):
    db = FakeDB()
    for call in (lambda: R.create_staff(_staff(role), db=db, user=CITIZEN),
                 lambda: R.list_staff(db=db, user=CITIZEN),
                 lambda: R.set_staff_active("driver.srtb", StaffActiveUpdate(active=False), db=db, user=CITIZEN),
                 lambda: R.reset_staff_password("driver.srtb", StaffPasswordReset(password="s3cret-pass"), db=db, user=CITIZEN)):
        with pytest.raises(HTTPException) as exc:
            call()
        assert exc.value.status_code == 403
    assert db.calls == []


def test_permission_map_is_the_single_source():
    assert R.MANAGEABLE_ROLES == {"transport_supervisor": {"bus_driver", "transport_supervisor"},
                                  "equipment_supervisor": {"inspection_vehicle", "equipment_supervisor"}}
    assert set(R.DEFAULT_ORG) == set().union(*R.MANAGEABLE_ROLES.values())


def test_allowed_create_hashes_password_lowercases_and_publishes_without_password():
    db = FakeDB(staff_row("driver.new", "bus_driver"), {"id": "x", "created_at": NOW})
    out = R.create_staff(_staff("bus_driver", username="Driver.New"), db=db, user=TRANSPORT)
    insert_sql, params = db.calls[0]
    assert "crypt(:password,gen_salt('bf'))" in insert_sql and "lower(:username)" in insert_sql
    assert params["organization"] == "SRTB" and params["role"] == "bus_driver"
    publish_sql, publish_params = db.calls[1]
    assert "notification_outbox" in publish_sql and publish_params["recipient"] == "transport_supervisor"
    assert "s3cret-pass" not in publish_params["payload"] and "password" not in publish_params["payload"]
    assert db.committed and out["username"] == "driver.new"


def test_list_only_returns_the_ministry_roles_and_never_the_hash():
    db = FakeDB([staff_row("inspection.vehicle", "inspection_vehicle")])
    R.list_staff(db=db, user=EQUIPMENT)
    sql, params = db.calls[0]
    assert params["roles"] == ["equipment_supervisor", "inspection_vehicle"]
    assert "password_hash" not in sql


def test_other_ministry_account_is_not_found():
    db = FakeDB(staff_row("driver.srtb", "bus_driver"))
    with pytest.raises(HTTPException) as exc:
        R.set_staff_active("driver.srtb", StaffActiveUpdate(active=False), db=db, user=EQUIPMENT)
    assert exc.value.status_code == 404


def test_supervisor_cannot_deactivate_himself():
    db = FakeDB(staff_row("transport.supervisor", "transport_supervisor"))
    with pytest.raises(HTTPException) as exc:
        R.set_staff_active("Transport.Supervisor", StaffActiveUpdate(active=False), db=db, user=TRANSPORT)
    assert exc.value.status_code == 422
    assert not db.committed


def test_peer_supervisor_password_reset_is_refused_driver_reset_allowed():
    db = FakeDB(staff_row("other.supervisor", "transport_supervisor"))
    with pytest.raises(HTTPException) as exc:
        R.reset_staff_password("other.supervisor", StaffPasswordReset(password="s3cret-pass"), db=db, user=TRANSPORT)
    assert exc.value.status_code == 403
    db = FakeDB(staff_row("driver.srtb", "bus_driver"), None)
    assert R.reset_staff_password("driver.srtb", StaffPasswordReset(password="s3cret-pass"), db=db,
                                  user=TRANSPORT) == {"status": "password_reset", "username": "driver.srtb"}
    assert "crypt(:password,gen_salt('bf'))" in db.calls[1][0]


# ------------------------------------------------------------------ public registration unchanged
def test_register_still_only_creates_citizens():
    assert "role" not in CitizenRegisterRequest.model_fields
    req = CitizenRegisterRequest.model_validate({"username": "Someone", "password": "s3cret-pass",
                                                 "display_name": "Someone", "role": "equipment_supervisor"})
    db = FakeDB({"username": "someone", "display_name": "Someone", "role": "citizen", "organization": "Public"})
    R.register_citizen(req, db=db)
    sql, params = db.calls[0]
    assert "'citizen'" in sql and "role" not in params


# ------------------------------------------------------------------ deactivation is immediate
def test_token_of_a_deactivated_account_is_refused():
    token = A.create_access_token(username="driver.test", role="bus_driver", display_name="D", organization="SRTB")
    assert A.get_current_user(token, db=FakeDB(True))["sub"] == "driver.test"
    for state in (False, None):  # deactivated, or deleted
        with pytest.raises(HTTPException) as exc:
            A.get_current_user(token, db=FakeDB(state))
        assert exc.value.status_code == 401


# ------------------------------------------------------------------ no password in any response
def _models(tp):
    if isinstance(tp, type) and issubclass(tp, BaseModel):
        yield tp
        for field in tp.model_fields.values():
            yield from _models(field.annotation)
    for arg in typing.get_args(tp):
        yield from _models(arg)


def test_no_password_field_in_any_auth_response_schema():
    models = {m for route in R.router.routes if getattr(route, "response_model", None) for m in _models(route.response_model)}
    assert StaffOut in models
    for model in models:
        leaked = [name for name in model.model_fields if "password" in name.lower()]
        assert not leaked, f"{model.__name__} exposes {leaked}"

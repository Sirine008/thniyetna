"""Equipment agent actions, human in the loop (propose → confirm → execute).

The fake session keeps agent_actions in memory and records every statement, so the tests check that:
proposals never write to business tables; a confirmation executes the existing code once, as the logged-in user;
a second confirmation, an expired proposal and a rejected proposal are refused; a wrong role gets 403.
The executors are the real ones (platform_app / perception / shared.realtime code) running on the fake session."""
import inspect
import json
import sys
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
pytest.importorskip("fastapi")
sys.path.insert(0, str(ROOT / "backend"))
from fastapi import HTTPException  # noqa: E402

from agent import actions as A  # noqa: E402
from agent import loop as L  # noqa: E402
from agent import router as R  # noqa: E402
from agent import tools as T  # noqa: E402

EQUIPMENT = {"sub": "equipment.supervisor", "role": "equipment_supervisor"}
TRANSPORT = {"sub": "transport.supervisor", "role": "transport_supervisor"}
SEGMENT = {"id": "11111111-1111-1111-1111-111111111111", "segment_code": "OSM-125567491",
           "name": "Route Nationale Bizerte - Babouch", "road_class": "primary"}
EVENT_ID = "22222222-2222-2222-2222-222222222222"
COMPLAINTS = [{"id": "c-1", "status": "open", "category": "road_damage", "description": "Nid-de-poule", "demo": True},
              {"id": "c-2", "status": "under_review", "category": "road_damage", "description": "Trou", "demo": False}]
BUSINESS = ("UPDATE COMPLAINTS", "COMPLAINT_STATUS_HISTORY", "NOTIFICATION_OUTBOX", "UPDATE ROAD_EVENTS")


class Res:
    def __init__(self, rows=None, scalars=None):
        self.rows = rows or []
        self._scalars = scalars

    def mappings(self):
        return self

    def all(self):
        return self.rows

    def first(self):
        return self.rows[0] if self.rows else None

    def one(self):
        return self.rows[0]

    def scalars(self):
        return Res(self._scalars if self._scalars is not None else [list(r.values())[0] for r in self.rows])

    def scalar(self):
        return list(self.rows[0].values())[0] if self.rows else None

    @property
    def rowcount(self):
        return len(self.rows)


class FakeDb:
    """agent_actions in memory; business tables answered by SQL keyword and recorded."""

    def __init__(self, event_status="observed", complaints=None):
        self.calls, self.actions, self.commits, self.event_status = [], {}, 0, event_status
        self.complaints = COMPLAINTS if complaints is None else complaints

    def business_writes(self):
        return [sql for sql, _ in self.calls if any(k in sql.upper() for k in BUSINESS)]

    def _row(self, a, expired=False):
        return {**a, "expired": expired}

    def execute(self, stmt, params=None):
        sql, p = str(stmt), params or {}
        self.calls.append((sql, p))
        now = datetime.now(timezone.utc)
        if "FROM road_segments WHERE segment_code" in sql:
            return Res([SEGMENT] if p["c"] == SEGMENT["segment_code"] else [])
        if "INSERT INTO agent_actions" in sql:
            aid = str(uuid.uuid4())
            self.actions[aid] = {"id": aid, "run_id": p["run"], "type": p["t"], "arguments": json.loads(p["a"]),
                                 "proposal": json.loads(p["p"]), "status": "proposed", "proposed_by": p["u"],
                                 "proposed_at": now, "decided_by": None, "decided_at": None, "result": None}
            return Res([{"id": aid, "status": "proposed", "proposed_at": now, "expires_at": now + timedelta(minutes=30)}])
        if "FROM agent_actions WHERE id = CAST" in sql:
            a = self.actions.get(p["id"])
            return Res([self._row(a, a["proposed_at"] < now - timedelta(minutes=30))] if a else [])
        if "UPDATE agent_actions SET status = 'expired'" in sql and "id" in p:
            if self.actions[p["id"]]["status"] == "proposed":
                self.actions[p["id"]]["status"] = "expired"
            return Res()
        if "UPDATE agent_actions SET status = 'expired'" in sql:            # expire_stale (list read)
            stale = [a for a in self.actions.values()
                     if a["status"] == "proposed" and a["proposed_at"] < now - timedelta(minutes=30)]
            for a in stale:
                a["status"] = "expired"
            return Res([{"id": a["id"]} for a in stale])
        if "FROM agent_actions WHERE id = ANY" in sql:
            return Res([{**a, "expires_at": a["proposed_at"] + timedelta(minutes=30)}
                        for a in self.actions.values() if a["id"] in p["ids"]])
        if "SELECT EXISTS (SELECT 1 FROM road_events e WHERE e.segment_id" in sql:   # _segment_demo
            return Res([{"exists": True}])
        if "UPDATE agent_actions SET status = CAST(:st" in sql:            # the atomic claim
            a = self.actions.get(p["id"])
            if a and a["status"] == "proposed" and a["proposed_at"] >= now - timedelta(minutes=30):
                a.update(status=p["st"], decided_by=p["u"], decided_at=now)
                return Res([dict(a)])
            return Res()
        if "UPDATE agent_actions SET status = 'failed'" in sql:
            self.actions[p["id"]]["status"] = "failed"
            return Res()
        if "UPDATE agent_actions SET result" in sql:
            self.actions[p["id"]]["result"] = json.loads(p["r"])
            return Res()
        if "FROM complaints c, road_segments s" in sql:
            open_ = [c for c in self.complaints if c["status"] not in ("resolved", "rejected", "planned")]
            return Res(open_, scalars=[c["id"] for c in open_])
        if "SELECT status,actor_ref FROM complaints" in sql:
            c = next(c for c in COMPLAINTS if c["id"] == p["id"])
            return Res([{"status": c["status"], "actor_ref": "citizen.demo"}])
        if "INSERT INTO notification_outbox" in sql:
            return Res([{"id": f"n-{len(self.calls)}", "created_at": now}])
        if "FROM road_events e LEFT JOIN road_segments" in sql:
            return Res([{"id": EVENT_ID, "event_type": "pothole", "severity": 0.71, "confidence": 0.83,
                         "status": self.event_status, "source": "inspection_vehicle", "observed_at": now,
                         "media_uri": "/media/files/frames/ev.jpg", "segment_code": SEGMENT["segment_code"],
                         "segment_name": SEGMENT["name"], "demo": True}] if p["id"] == EVENT_ID else [])
        if "FROM road_observations" in sql:
            return Res([{"media_uri": "/media/files/frames/best.jpg", "confidence": 0.83, "frame_time_s": 12.4,
                         "bbox_xyxy": [10, 20, 110, 90]}])
        if "UPDATE road_events" in sql:
            return Res([{"id": p["id"], "event_type": "pothole"}])
        return Res()

    def commit(self):
        self.commits += 1
        self.calls.append(("COMMIT", None))

    def rollback(self):
        self.calls.append(("ROLLBACK", None))


def stored(db, proposal):
    return A.store_proposal(db, str(uuid.uuid4()), EQUIPMENT, proposal)


def scripted(*messages):
    queue = list(messages)

    def chat(msgs, tools, model=None, options=None):
        chat.seen.append([dict(m) for m in msgs])
        chat.tools_seen.append(tools)
        return queue.pop(0) if queue else {"role": "assistant", "content": "", "tool_calls": []}
    chat.seen, chat.tools_seen = [], []
    return chat


# ---------------------------------------------------------------- proposals

def test_proposals_never_write_to_business_tables():
    db = FakeDb()
    calls = [{"function": {"name": n, "arguments": a}} for n, a in [
        ("plan_intervention", {"segment_code": "OSM-125567491", "note": "Équipe B lundi"}),
        ("notify_transport", {"segment_code": "OSM-125567491", "message": "Chantier lundi, voie réduite."}),
        ("generate_full_sheet", {"segment_code": "OSM-125567491"}),
        ("propose_validation", {"event_id": EVENT_ID})]]
    chat = scripted({"role": "assistant", "content": "", "tool_calls": calls},
                    {"role": "assistant", "content": "4 actions proposées, à confirmer.", "tool_calls": []})
    run_id = str(uuid.uuid4())
    out = L.run_agent(db, "Planifie et préviens le Transport", chat=chat,
                      propose=lambda p: A.store_proposal(db, run_id, EQUIPMENT, p))
    assert [a["type"] for a in out["actions"]] == ["plan_intervention", "notify_transport", "generate_full_sheet",
                                                   "propose_validation"]
    assert all(a["status"] == "proposed" and a["id"] for a in out["actions"])
    assert db.business_writes() == []                                         # nothing executed
    writes = [sql for sql, _ in db.calls if sql.lstrip().upper().startswith(("INSERT", "UPDATE", "DELETE"))]
    assert len(writes) == 4 and all("INSERT INTO agent_actions" in w for w in writes)
    told = [json.loads(m["content"]) for m in chat.seen[1] if m["role"] == "tool"]
    assert all(t["statut"] == "en attente de confirmation humaine" and "Rien n'a été exécuté" in t["important"] for t in told)
    assert all(s["result_summary"].startswith("Action proposée, à confirmer") for s in out["steps"])
    plan, validation = out["actions"][0], out["actions"][3]
    assert plan["demo"] is True and "DÉMO" in out["steps"][0]["result_summary"]          # a demo complaint is included
    assert "2 signalement(s) citoyen(s) passeront au statut « Intervention planifiée »" in plan["changes"][0]
    ev = validation["evidence"]
    assert ev["event"]["confidence"] == 0.83 and ev["frame"]["media_uri"] == "/media/files/frames/best.jpg"
    assert validation["demo"] is True and "Vérifiez d'abord la photo" in validation["changes"][1]


def test_without_a_store_proposals_are_returned_but_stored_nowhere():
    db = FakeDb()
    chat = scripted({"role": "assistant", "content": "", "tool_calls": [
        {"function": {"name": "generate_full_sheet", "arguments": {"segment_code": "OSM-125567491"}}}]},
        {"role": "assistant", "content": "Proposée.", "tool_calls": []})
    out = L.run_agent(db, "Fiche complète ?", chat=chat)                     # evaluation / tests: no propose callback
    assert out["actions"][0]["id"] is None and out["actions"][0]["status"] == "non enregistrée"
    # The model may present a proposal as done (live, 07/11): a fixed warning always says nothing ran.
    assert any("rien n'a été exécuté" in w for w in out["warnings"])
    assert not any("agent_actions" in sql for sql, _ in db.calls)


def test_bad_action_arguments_go_back_to_the_model():
    db = FakeDb(event_status="validated")
    with pytest.raises(T.ToolError, match="identifiant de détection invalide|Identifiant de détection invalide"):
        A.propose_validation(db, "OSM-1")
    with pytest.raises(T.ToolError, match="n'est pas à valider"):
        A.propose_validation(db, EVENT_ID)
    with pytest.raises(T.ToolError, match="Segment inconnu"):
        A.notify_transport(db, "OSM-12345", "message")
    with pytest.raises(T.ToolError, match="doit faire entre 3 et 500"):
        T.validate("notify_transport", {"segment_code": "OSM-125567491", "message": "x"})
    assert db.business_writes() == []


# ---------------------------------------------------------------- confirm / reject

def test_confirm_executes_once_with_the_existing_code_and_a_second_confirm_is_refused():
    db = FakeDb()
    action = stored(db, A.plan_intervention(db, "OSM-125567491", "Équipe B lundi"))
    out = R.confirm_action(action["id"], db=db, user=EQUIPMENT)
    assert out["status"] == "confirmed" and out["decided_by"] == "equipment.supervisor"
    assert out["result"]["planned_complaints"] == ["c-1", "c-2"] and out["result"]["note"] == "Équipe B lundi"
    writes = db.business_writes()
    assert sum("UPDATE complaints SET status" in w for w in writes) == 2                 # update_complaint, reused
    assert sum("complaint_status_history" in w for w in writes) == 2
    history = [p for sql, p in db.calls if "complaint_status_history" in sql]
    assert all(h["n"] == "planned" and h["u"] == "equipment.supervisor" for h in history)   # the user is the actor
    with pytest.raises(HTTPException) as exc:
        R.confirm_action(action["id"], db=db, user=EQUIPMENT)
    assert exc.value.status_code == 409 and "déjà confirmée" in exc.value.detail
    assert db.business_writes() == writes                                                # nothing ran twice
    assert db.actions[action["id"]]["result"]["count"] == 2


def test_expired_proposal_is_refused_and_marked_expired():
    db = FakeDb()
    action = stored(db, A.notify_transport(db, "OSM-125567491", "Voie réduite lundi."))
    db.actions[action["id"]]["proposed_at"] -= timedelta(minutes=31)
    with pytest.raises(HTTPException) as exc:
        R.confirm_action(action["id"], db=db, user=EQUIPMENT)
    assert exc.value.status_code == 410 and "expirée" in exc.value.detail
    assert db.actions[action["id"]]["status"] == "expired" and db.business_writes() == []


def test_rejected_action_never_runs():
    db = FakeDb()
    action = stored(db, A.propose_validation(db, EVENT_ID))
    out = R.reject_action(action["id"], db=db, user=EQUIPMENT)
    assert out["status"] == "rejected" and out["decided_by"] == "equipment.supervisor"
    with pytest.raises(HTTPException) as exc:
        R.confirm_action(action["id"], db=db, user=EQUIPMENT)
    assert exc.value.status_code == 409 and "ignorée" in exc.value.detail
    with pytest.raises(HTTPException):
        R.reject_action(action["id"], db=db, user=EQUIPMENT)
    assert db.business_writes() == []


@pytest.fixture
def backend_perception():
    """`perception` is both backend/perception (API router) and ml/perception (worker, on pytest's pythonpath).
    When the ML tests ran first, sys.modules holds the ML package; point the name at the backend package for this
    test, then restore the ML modules (the API container only has the backend one)."""
    saved = {k: v for k, v in sys.modules.items() if k == "perception" or k.startswith("perception.")}
    for k in saved:
        del sys.modules[k]
    sys.path.insert(0, str(ROOT / "backend"))
    try:
        import perception.router  # noqa: F401  (backend package)
        yield
    finally:
        sys.path.remove(str(ROOT / "backend"))
        for k in [k for k in sys.modules if k == "perception" or k.startswith("perception.")]:
            del sys.modules[k]
        sys.modules.update(saved)


def test_notify_and_validation_execute_as_the_user(backend_perception):
    db = FakeDb()
    notice = R.confirm_action(stored(db, A.notify_transport(db, "OSM-125567491", "Voie réduite lundi."))["id"],
                              db=db, user=EQUIPMENT)
    outbox = [p for sql, p in db.calls if "INSERT INTO notification_outbox" in sql]
    assert outbox, notice                                           # shows the stored result if nothing was sent
    sent = outbox[0]
    assert sent["recipient"] == "transport_supervisor" and sent["topic"] == A.NOTICE_TOPIC
    assert json.loads(sent["payload"])["sent_by"] == "equipment.supervisor" and notice["status"] == "confirmed"
    validated = R.confirm_action(stored(db, A.propose_validation(db, EVENT_ID))["id"], db=db, user=EQUIPMENT)
    update = [p for sql, p in db.calls if "UPDATE road_events" in sql][0]
    assert update == {"id": EVENT_ID, "u": "equipment.supervisor"} and validated["result"]["status"] == "validated"


def test_a_failed_execution_is_recorded_and_not_retried(monkeypatch):
    def boom(db, args, user):
        raise RuntimeError("OSRM down")
    monkeypatch.setitem(A.EXECUTORS, "generate_full_sheet", boom)
    db = FakeDb()
    action = stored(db, A.generate_full_sheet(db, "OSM-125567491"))
    out = R.confirm_action(action["id"], db=db, user=EQUIPMENT)
    assert out["status"] == "failed" and "OSRM down" in out["result"]["error"]
    assert db.actions[action["id"]]["status"] == "failed"
    with pytest.raises(HTTPException) as exc:
        R.confirm_action(action["id"], db=db, user=EQUIPMENT)
    assert exc.value.status_code == 409


def test_unknown_action_is_404():
    for bad in ("pas-un-uuid", str(uuid.uuid4())):
        with pytest.raises(HTTPException) as exc:
            R.confirm_action(bad, db=FakeDb(), user=EQUIPMENT)
        assert exc.value.status_code == 404


def test_only_the_equipment_supervisor_can_confirm_or_reject():
    for endpoint in (R.confirm_action, R.reject_action, R.agent):
        checker = inspect.signature(endpoint).parameters["user"].default.dependency
        with pytest.raises(HTTPException) as exc:
            checker(user=TRANSPORT)
        assert exc.value.status_code == 403
        assert checker(user=EQUIPMENT) == EQUIPMENT


def test_reading_the_list_marks_old_proposals_expired():
    db = FakeDb()
    old = stored(db, A.notify_transport(db, "OSM-125567491", "Ancienne proposition."))
    fresh = stored(db, A.generate_full_sheet(db, "OSM-125567491"))
    db.actions[old["id"]]["proposed_at"] -= timedelta(minutes=45)
    rows = R.list_agent_actions(ids=f"{old['id']},{fresh['id']},pas-un-id", db=db, user=EQUIPMENT)
    assert {r["id"]: r["status"] for r in rows} == {old["id"]: "expired", fresh["id"]: "proposed"}
    assert all(r["expires_at"] for r in rows) and db.business_writes() == []
    with pytest.raises(HTTPException) as exc:                 # an expired proposal can no longer be confirmed
        R.confirm_action(old["id"], db=db, user=EQUIPMENT)
    assert exc.value.status_code == 409 and "expirée" in exc.value.detail


def test_plan_intervention_is_all_or_nothing(monkeypatch):
    import platform_app.router as P
    db = FakeDb()
    ok = R.confirm_action(stored(db, A.plan_intervention(db, "OSM-125567491", "Lot A"))["id"], db=db, user=EQUIPMENT)
    log = [sql for sql, _ in db.calls]
    first_update = next(i for i, sql in enumerate(log) if "UPDATE complaints SET status" in sql)
    last_publish = max(i for i, sql in enumerate(log) if "INSERT INTO notification_outbox" in sql)
    assert ok["status"] == "confirmed" and ok["result"]["count"] == 2
    assert "COMMIT" not in log[first_update:last_publish]       # no commit between the two complaints
    assert log[last_publish + 1] == "COMMIT"                    # one commit for all of them

    real, seen = P.apply_complaint_status, []

    def second_fails(db_, cid, status, note, user):
        seen.append(cid)
        if len(seen) == 2:
            raise RuntimeError("complaint c-2 locked")
        return real(db_, cid, status, note, user)
    monkeypatch.setattr(P, "apply_complaint_status", second_fails)
    db = FakeDb()
    action = stored(db, A.plan_intervention(db, "OSM-125567491", "Lot B"))
    claim_commit = None
    out = R.confirm_action(action["id"], db=db, user=EQUIPMENT)
    log = [sql for sql, _ in db.calls]
    claim_commit = next(i for i, sql in enumerate(log) if "SET status = CAST(:st" in sql) + 1
    first_update = next(i for i, sql in enumerate(log) if "UPDATE complaints SET status" in sql)
    rollback = log.index("ROLLBACK")
    assert out["status"] == "failed" and "complaint c-2 locked" in out["result"]["error"]
    assert log[claim_commit] == "COMMIT" and claim_commit < first_update < rollback
    assert "COMMIT" not in log[first_update:rollback]           # c-1 was never committed: rolled back with c-2


# ---------------------------------------------------------------- invented codes never become proposals

@pytest.mark.parametrize("name, args, message", [
    ("get_segment_facts", {"segment_code": "OSM-12345"}, "Segment inconnu"),
    ("get_intervention_sheet", {"segment_code": "OSM-123456"}, "Segment inconnu"),
    ("plan_intervention", {"segment_code": "RN1234"}, "Segment inconnu"),
    ("notify_transport", {"segment_code": "OSM-1", "message": "Travaux lundi."}, "Segment inconnu"),
    ("generate_full_sheet", {"segment_code": "OSM-999"}, "Segment inconnu"),
    ("propose_validation", {"event_id": "33333333-3333-3333-3333-333333333333"}, "Détection inconnue"),
    ("propose_validation", {"event_id": "OSM-125567491-pothole-0001-xxxxxxxxx"}, "Identifiant de détection invalide"),
])
def test_unknown_codes_go_back_to_the_model_and_are_never_proposed(monkeypatch, name, args, message):
    from rag import intervention
    real = intervention.gather_facts
    monkeypatch.setattr(intervention, "gather_facts",
                        lambda db, code: real(db, code) if code == SEGMENT["segment_code"] else None)
    db = FakeDb()
    chat = scripted({"role": "assistant", "content": "", "tool_calls": [{"function": {"name": name, "arguments": args}}]},
                    {"role": "assistant", "content": "Code inconnu.", "tool_calls": []})
    run_id = str(uuid.uuid4())
    out = L.run_agent(db, "Planifie et valide ce qu'il faut traiter", chat=chat,
                      propose=lambda p: A.store_proposal(db, run_id, EQUIPMENT, p))
    step = out["steps"][0]
    assert step["ok"] is False and message in step["error"]
    assert out["actions"] == [] and not any("agent_actions" in sql for sql, _ in db.calls)
    assert db.business_writes() == []
    told = json.loads([m for m in chat.seen[1] if m["role"] == "tool"][0]["content"])
    assert message in told["erreur"]                                          # sent back to the model


def test_actions_are_refused_when_the_state_does_not_allow_them():
    with pytest.raises(T.ToolError, match="rien à planifier"):          # no open complaint within 100 m
        A.plan_intervention(FakeDb(complaints=[{**COMPLAINTS[0], "status": "planned"}]), "OSM-125567491")
    for status in ("validated", "closed"):
        with pytest.raises(T.ToolError, match="n'est pas à valider"):
            A.propose_validation(FakeDb(event_status=status), EVENT_ID)


# ---------------------------------------------------------------- action tools only for action questions

@pytest.mark.parametrize("question, expected", [
    ("Planifie une intervention sur le segment OSM-713546524.", "actions"),
    ("Préviens le superviseur Transport des travaux.", "actions"),
    ("Alerte le transport : chantier lundi.", "actions"),
    ("Propose la VALIDATION de cette détection.", "actions"),
    ("Génère la fiche complète.", "actions"),
    ("Quels segments dois-je traiter en priorité ?", "actions"),           # « traiter » is in the rule
    ("À quelle température minimale peut-on poser un enrobé chaud ?", "lecture"),
    ("Donne-moi les 5 segments les plus prioritaires.", "lecture"),
    ("Quel est le segment le plus prioritaire et quels défauts y sont enregistrés ?", "lecture"),
    ("Un attrait particulier sur cette route ?", "lecture"),              # word start only: « attrait » ≠ « trait »
])
def test_action_tools_are_offered_only_for_action_questions(question, expected):
    tool_set, offered = T.tools_for(question)
    assert tool_set == expected
    assert offered == (list(T.TOOLS) if expected == "actions" else T.READ_TOOLS)


def test_read_question_gets_five_tools_and_an_action_call_is_refused():
    db = FakeDb()
    chat = scripted({"role": "assistant", "content": "", "tool_calls": [
        {"function": {"name": "notify_transport", "arguments": {"segment_code": "OSM-125567491", "message": "x" * 10}}}]},
        {"role": "assistant", "content": "Les guides disent…", "tool_calls": []})
    out = L.run_agent(db, "Comment signaler un chantier sur une route nationale ?", chat=chat,
                      propose=lambda p: A.store_proposal(db, str(uuid.uuid4()), EQUIPMENT, p))
    assert out["tool_set"] == "lecture" and out["offered_tools"] == T.READ_TOOLS
    assert [t["function"]["name"] for t in chat.tools_seen[0]] == T.READ_TOOLS              # only 5 schemas sent
    assert out["steps"][0]["ok"] is False and "Outil non proposé pour cette question" in out["steps"][0]["error"]
    assert out["actions"] == [] and not any("agent_actions" in sql for sql, _ in db.calls)

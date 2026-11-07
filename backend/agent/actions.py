"""Acting tools of the equipment agent, with a human in the loop: propose → confirm → execute.

During the agent loop an action tool NEVER writes to a business table. It reads what it needs, checks that the
action makes sense, and returns a *proposal* (type, arguments, French summary, what will change, evidence to check).
The proposal is stored in `agent_actions` (status 'proposed', Alembic 0008). Only POST
/assistant/agent/actions/{id}/confirm executes it, once, with the existing code and the logged-in supervisor as
actor. Proposals expire after EXPIRY_MINUTES.
"""
import json
import re

from rag import intervention

from .errors import ToolError

EXPIRY_MINUTES = 30
DEMO_LABEL = intervention.DEMO_LABEL
NOTICE_TOPIC = "equipment.segment.notice"           # publish() topic for notify_transport
_UUID = re.compile(r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$")
ACTION_TYPES = ("plan_intervention", "notify_transport", "generate_full_sheet", "propose_validation")


class ActionRefused(Exception):
    """Confirm / reject refused (already decided, expired, unknown): HTTP 404 / 409 / 410 in the router."""

    def __init__(self, status_code: int, message: str):
        super().__init__(message)
        self.status_code = status_code


# ---------------------------------------------------------------- proposals (read-only)

def _segment(db, segment_code: str) -> dict:
    from sqlalchemy import text
    seg = db.execute(text("SELECT id::text id, segment_code, name, road_class FROM road_segments "
                          "WHERE segment_code = CAST(:c AS text)"), {"c": segment_code}).mappings().first()
    if not seg:
        raise ToolError(f"Segment inconnu : {segment_code}. Utilisez un code renvoyé par un outil.")
    return dict(seg)


def _segment_demo(db, seg: dict) -> bool:
    """True when the segment carries open demo data (demo M1 event on it, demo complaint within 100 m): the action
    is then a demo action (« DÉMO — données fictives »), and seed_demo.py --reset removes its traces."""
    from sqlalchemy import text
    return bool(db.execute(text("""
        SELECT EXISTS (SELECT 1 FROM road_events e WHERE e.segment_id = CAST(:s AS uuid) AND e.status <> 'closed'
                         AND coalesce((e.payload->>'demo')::boolean, false))
            OR EXISTS (SELECT 1 FROM complaints c, road_segments s WHERE s.id = CAST(:s AS uuid)
                         AND c.status NOT IN ('resolved', 'rejected') AND coalesce((c.payload->>'demo')::boolean, false)
                         AND ST_DWithin(c.geom::geography, s.geom::geography, :r))"""),
        {"s": seg["id"], "r": intervention.COMPLAINT_RADIUS_M}).scalar())


def _name(seg: dict) -> str:
    return f"{seg['name'] or 'segment sans nom'} ({seg['segment_code']})"


def plan_intervention(db, segment_code: str, note: str = "") -> dict:
    """Proposal: open complaints within 100 m of the segment → « Intervention planifiée »."""
    from sqlalchemy import text
    seg = _segment(db, segment_code)
    rows = db.execute(text("""
        SELECT c.id::text id, c.status, c.payload->>'category' category, left(c.description, 120) description,
               coalesce((c.payload->>'demo')::boolean, false) demo
        FROM complaints c, road_segments s
        WHERE s.id = CAST(:s AS uuid) AND c.status NOT IN ('resolved', 'rejected', 'planned')
          AND ST_DWithin(c.geom::geography, s.geom::geography, :r)
        ORDER BY c.created_at"""), {"s": seg["id"], "r": intervention.COMPLAINT_RADIUS_M}).mappings().all()
    if not rows:
        raise ToolError(f"Aucun signalement ouvert à moins de {intervention.COMPLAINT_RADIUS_M} m de {segment_code} : "
                        "rien à planifier.")
    complaints = [dict(r) for r in rows]
    return {"type": "plan_intervention", "arguments": {"segment_code": segment_code, "note": note},
            "demo": any(c["demo"] for c in complaints),
            "summary": f"Planifier une intervention sur {_name(seg)}.",
            "changes": [f"{len(complaints)} signalement(s) citoyen(s) passeront au statut « Intervention planifiée » "
                        "(historique du statut enregistré, notification au citoyen).",
                        f"Note enregistrée : « {note or 'aucune'} »."],
            "evidence": {"complaints": complaints}}


def notify_transport(db, segment_code: str, message: str) -> dict:
    """Proposal: one notification to the transport supervisors about a segment."""
    seg = _segment(db, segment_code)
    return {"type": "notify_transport", "arguments": {"segment_code": segment_code, "message": message},
            "demo": _segment_demo(db, seg), "summary": f"Prévenir le superviseur Transport au sujet de {_name(seg)}.",
            "changes": ["Une notification sera envoyée au rôle « Superviseur transport » "
                        f"(sujet {NOTICE_TOPIC}) avec ce message : « {message} »."],
            "evidence": {}}


def generate_full_sheet(db, segment_code: str) -> dict:
    """Proposal: the full intervention sheet (guides' advice by the LLM, about 100 s)."""
    seg = _segment(db, segment_code)
    return {"type": "generate_full_sheet", "arguments": {"segment_code": segment_code},
            "demo": _segment_demo(db, seg), "summary": f"Générer la fiche d'intervention complète de {_name(seg)}.",
            "changes": ["Aucune donnée métier modifiée : la fiche est générée par le modèle de langage (environ 100 s) "
                        "et une ligne est ajoutée au journal des questions (rag_queries)."],
            "evidence": {}}


def propose_validation(db, event_id: str) -> dict:
    """Proposal: validate one M1 detection. The photo / evidence frame and the confidence are attached so the
    supervisor checks them first."""
    from sqlalchemy import text
    if not _UUID.match(event_id or ""):
        raise ToolError(f"Identifiant de détection invalide : {event_id}. Utilisez un « id » renvoyé par get_segment_facts.")
    ev = db.execute(text("""
        SELECT e.id::text id, e.event_type, e.severity, e.confidence, e.status, e.source, e.observed_at, e.media_uri,
               s.segment_code, s.name segment_name, coalesce((e.payload->>'demo')::boolean, false) demo
        FROM road_events e LEFT JOIN road_segments s ON s.id = e.segment_id
        WHERE e.id = CAST(:id AS uuid)"""), {"id": event_id}).mappings().first()
    if not ev:
        raise ToolError(f"Détection inconnue : {event_id}.")
    if ev["status"] != "observed":
        raise ToolError(f"La détection {event_id} n'est pas à valider (statut {ev['status']}).")
    frame = db.execute(text("""
        SELECT media_uri, confidence, frame_time_s, bbox_xyxy FROM road_observations
        WHERE event_id = CAST(:id AS uuid) AND media_uri IS NOT NULL
        ORDER BY confidence DESC LIMIT 1"""), {"id": event_id}).mappings().first()
    ev = intervention._jsonable(dict(ev))
    label = intervention.DEFECT_LABELS.get(ev["event_type"], ev["event_type"])
    return {"type": "propose_validation", "arguments": {"event_id": event_id}, "demo": ev["demo"],
            "summary": f"Valider la détection « {label} » sur "
                       f"{ev['segment_name'] or 'segment sans nom'} ({ev['segment_code'] or 'hors segment'}).",
            "changes": ["La détection passera au statut « Validée » (validée par vous) et une notification "
                        "road.event.validated sera publiée.",
                        "Vérifiez d'abord la photo et la confiance ci-dessous."],
            "evidence": {"event": ev, "frame": intervention._jsonable(dict(frame)) if frame else None}}


ACTION_TOOLS = {"plan_intervention": plan_intervention, "notify_transport": notify_transport,
                "generate_full_sheet": generate_full_sheet, "propose_validation": propose_validation}


def store_proposal(db, run_id: str, user: dict, proposal: dict) -> dict:
    """INSERT into agent_actions only (no business table). -> the stored proposal with id / expiry."""
    from sqlalchemy import text
    row = db.execute(text(f"""
        INSERT INTO agent_actions (run_id, type, arguments, proposal, proposed_by)
        VALUES (CAST(:run AS uuid), CAST(:t AS text), CAST(:a AS jsonb), CAST(:p AS jsonb), CAST(:u AS text))
        RETURNING id::text id, status, proposed_at, proposed_at + interval '{EXPIRY_MINUTES} minutes' expires_at"""),
        {"run": run_id, "t": proposal["type"], "a": json.dumps(proposal["arguments"], ensure_ascii=False),
         "p": json.dumps({k: proposal[k] for k in ("summary", "changes", "evidence", "demo")}, ensure_ascii=False,
                         default=str),
         "u": user.get("sub")}).mappings().one()
    return {**proposal, **intervention._jsonable(dict(row))}


def for_model(stored: dict) -> dict:
    """What the model is told: proposed, NOT executed, a human must confirm."""
    return {"action_proposee": stored["type"], "id": stored.get("id"), "statut": "en attente de confirmation humaine",
            "resume": stored["summary"], "changements": stored["changes"],
            "important": "Rien n'a été exécuté. Dis au superviseur qu'il doit confirmer ou ignorer cette action."}


# ---------------------------------------------------------------- decision (confirm / reject)

_ACTION_COLUMNS = ("id::text id, run_id::text run_id, type, arguments, proposal, status, proposed_by, proposed_at, "
                   "decided_by, decided_at, result")


def _load(db, action_id: str) -> dict:
    from sqlalchemy import text
    if not _UUID.match(action_id or ""):
        raise ActionRefused(404, "Action inconnue.")
    row = db.execute(text(f"SELECT {_ACTION_COLUMNS}, proposed_at < now() - interval '{EXPIRY_MINUTES} minutes' expired "
                          "FROM agent_actions WHERE id = CAST(:id AS uuid)"), {"id": action_id}).mappings().first()
    if not row:
        raise ActionRefused(404, "Action inconnue.")
    return dict(row)


def expire_stale(db) -> int:
    """Mark every proposal older than EXPIRY_MINUTES as 'expired' (no background job: done when the list is read)."""
    from sqlalchemy import text
    return db.execute(text(f"""UPDATE agent_actions SET status = 'expired'
        WHERE status = 'proposed' AND proposed_at < now() - interval '{EXPIRY_MINUTES} minutes'""")).rowcount


def list_actions(db, ids: list[str]) -> list[dict]:
    """Current state of the given proposals (the UI refreshes its cards), after marking stale ones expired."""
    from sqlalchemy import text
    ids = [i for i in ids if _UUID.match(i or "")][:50]
    expire_stale(db)
    db.commit()
    if not ids:
        return []
    rows = db.execute(text(f"""SELECT {_ACTION_COLUMNS}, proposed_at + interval '{EXPIRY_MINUTES} minutes' expires_at
        FROM agent_actions WHERE id = ANY(CAST(:ids AS uuid[])) ORDER BY proposed_at"""), {"ids": ids}).mappings().all()
    return [intervention._jsonable(dict(r)) for r in rows]


STATUS_FR = {"confirmed": "déjà confirmée et exécutée", "rejected": "ignorée", "expired": "expirée", "failed": "en échec"}


def _claim(db, action_id: str, user: dict, new_status: str) -> dict:
    """Atomic: proposed (and not expired) → new_status. Refuses a second decision, and expires old proposals."""
    from sqlalchemy import text
    current = _load(db, action_id)
    if current["status"] == "proposed" and current["expired"]:
        db.execute(text("UPDATE agent_actions SET status = 'expired' WHERE id = CAST(:id AS uuid) AND status = 'proposed'"),
                   {"id": action_id})
        db.commit()
        raise ActionRefused(410, f"Proposition expirée (plus de {EXPIRY_MINUTES} min) : relancez l'agent.")
    row = db.execute(text(f"""
        UPDATE agent_actions SET status = CAST(:st AS text), decided_by = CAST(:u AS text), decided_at = now()
        WHERE id = CAST(:id AS uuid) AND status = 'proposed'
          AND proposed_at >= now() - interval '{EXPIRY_MINUTES} minutes'
        RETURNING {_ACTION_COLUMNS}"""), {"st": new_status, "u": user.get("sub"), "id": action_id}).mappings().first()
    if not row:
        raise ActionRefused(409, f"Action {STATUS_FR.get(current['status'], current['status'])} : elle ne peut pas "
                                 "être décidée une seconde fois.")
    return dict(row)


def reject(db, action_id: str, user: dict) -> dict:
    row = _claim(db, action_id, user, "rejected")
    db.commit()
    return intervention._jsonable(row)


def confirm(db, action_id: str, user: dict) -> dict:
    """Execute once. The claim (status → confirmed) is committed BEFORE execution, so a second confirm (or a
    concurrent one, blocked on the row lock until then) finds status != proposed and is refused. The existing
    functions commit on their own; a failure is recorded as status 'failed' with the error, never retried."""
    from sqlalchemy import text
    row = _claim(db, action_id, user, "confirmed")
    db.commit()
    try:
        result = EXECUTORS[row["type"]](db, row["arguments"] or {}, user)
        status = "confirmed"
    except Exception as exc:  # recorded, never retried automatically
        db.rollback()
        result, status = {"error": f"{type(exc).__name__}: {getattr(exc, 'detail', None) or exc}"[:500]}, "failed"
        db.execute(text("UPDATE agent_actions SET status = 'failed', decided_by = CAST(:u AS text), decided_at = now() "
                        "WHERE id = CAST(:id AS uuid)"), {"u": user.get("sub"), "id": action_id})
    db.execute(text("UPDATE agent_actions SET result = CAST(:r AS jsonb) WHERE id = CAST(:id AS uuid)"),
               {"r": json.dumps(result, ensure_ascii=False, default=str), "id": action_id})
    db.commit()
    return {**intervention._jsonable(row), "status": status, "result": result}


# ---------------------------------------------------------------- executors (existing code, user = actor)

def _exec_plan_intervention(db, args: dict, user: dict) -> dict:
    """Same code as PATCH /platform/complaints/{id}/status (platform_app.router.apply_complaint_status: status +
    history + citizen notification), for every complaint in ONE transaction: one commit at the end, and any error
    rolls everything back (confirm() then records the action as failed)."""
    from platform_app.router import apply_complaint_status
    from sqlalchemy import text
    seg = _segment(db, args["segment_code"])
    ids = db.execute(text("""
        SELECT c.id::text FROM complaints c, road_segments s
        WHERE s.id = CAST(:s AS uuid) AND c.status NOT IN ('resolved', 'rejected', 'planned')
          AND ST_DWithin(c.geom::geography, s.geom::geography, :r)"""),
        {"s": seg["id"], "r": intervention.COMPLAINT_RADIUS_M}).scalars().all()
    note = (args.get("note") or "").strip() or f"Intervention planifiée sur {seg['segment_code']} (agent, confirmée)"
    done = [apply_complaint_status(db, cid, "planned", note, user) for cid in ids]   # no commit inside
    db.commit()
    return {"planned_complaints": [d["id"] for d in done], "previous_status": {d["id"]: d["old_status"] for d in done},
            "count": len(done), "note": note}


def _exec_notify_transport(db, args: dict, user: dict) -> dict:
    from shared.realtime import publish
    seg = _segment(db, args["segment_code"])
    sent = publish(db, NOTICE_TOPIC, {"segment_code": seg["segment_code"], "segment_name": seg["name"],
                                      "message": args["message"], "sent_by": user.get("sub"),
                                      "demo": _segment_demo(db, seg)}, "transport_supervisor")
    db.commit()
    return {"notification_id": sent["id"], "recipient": "transport_supervisor", "topic": NOTICE_TOPIC}


def _exec_generate_full_sheet(db, args: dict, user: dict) -> dict:
    from rag.router import intervention_sheet
    sheet = intervention_sheet(args["segment_code"], db=db, user=user)
    return {"sheet": sheet}


def _exec_propose_validation(db, args: dict, user: dict) -> dict:
    """Same function as PATCH /perception/events/{id}/validate."""
    from perception.router import validate_event
    return dict(validate_event(args["event_id"], db=db, user=user))


EXECUTORS = {"plan_intervention": _exec_plan_intervention, "notify_transport": _exec_notify_transport,
             "generate_full_sheet": _exec_generate_full_sheet, "propose_validation": _exec_propose_validation}

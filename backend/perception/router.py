"""M1 perception contracts.

Heavy computer vision runs in the dedicated M1 worker. The API owns durable job
submission, GPS capture, observability and the stable RoadEvent contract.
"""
import json
from typing import List

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import text
from sqlalchemy.orm import Session

from .schemas import (
    InspectionSessionOut,
    InspectionStart,
    ObservationOut,
    PerceptionJobCreate,
    PerceptionJobOut,
    RoadEventIn,
    RoadEventOut,
    VehicleHeartbeat,
)
from shared.auth import get_current_user, require_role
from shared.db import get_db
from shared.realtime import publish
from shared.storage import resolve_media_key

router = APIRouter()


@router.post("/inspections/start", response_model=InspectionSessionOut)
def start_inspection(
    req: InspectionStart,
    db: Session = Depends(get_db),
    user=Depends(require_role("inspection_vehicle", "equipment_supervisor")),
):
    if req.video_storage_key:
        try:
            resolve_media_key(req.video_storage_key)
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc

    row = db.execute(text("""
      INSERT INTO inspection_sessions(vehicle_id,video_uri,video_storage_key,metadata)
      SELECT id,:video,:storage_key,
             jsonb_build_object('mode',CAST(:mode AS text),'started_by',CAST(:user AS text))
      FROM vehicles WHERE vehicle_code=:code
      RETURNING id::text,status,started_at,video_uri,video_storage_key
    """), {
        "video": req.video_uri,
        "storage_key": req.video_storage_key,
        "mode": req.mode,
        "user": user["sub"],
        "code": req.vehicle_code,
    }).mappings().first()
    if not row:
        raise HTTPException(404, "Vehicle not found")
    db.commit()
    return {**row, "vehicle_code": req.vehicle_code}


@router.post("/inspections/{session_id}/heartbeat")
def heartbeat(
    session_id: str,
    req: VehicleHeartbeat,
    db: Session = Depends(get_db),
    user=Depends(require_role("inspection_vehicle", "equipment_supervisor")),
):
    row = db.execute(text("""
      UPDATE inspection_sessions
      SET last_position=ST_SetSRID(ST_MakePoint(:lon,:lat),4326),
          metadata=metadata||jsonb_build_object('last_heartbeat',CAST(:ts AS text))
      WHERE id=:id
      RETURNING id::text
    """), {
        "id": session_id,
        "lat": req.latitude,
        "lon": req.longitude,
        "ts": req.timestamp.isoformat(),
    }).first()
    if not row:
        raise HTTPException(404, "Inspection session not found")

    db.execute(text("""
      INSERT INTO inspection_positions(
        session_id,captured_at,geom,speed_kmh,heading_deg,accuracy_m
      ) VALUES(
        :session,:ts,ST_SetSRID(ST_MakePoint(:lon,:lat),4326),:speed,:heading,:accuracy
      )
      ON CONFLICT(session_id,captured_at) DO UPDATE SET
        geom=excluded.geom,
        speed_kmh=excluded.speed_kmh,
        heading_deg=excluded.heading_deg,
        accuracy_m=excluded.accuracy_m
    """), {
        "session": session_id,
        "ts": req.timestamp,
        "lat": req.latitude,
        "lon": req.longitude,
        "speed": req.speed_kmh,
        "heading": req.heading_deg,
        "accuracy": req.accuracy_m,
    })
    publish(db, "vehicle.position", {
        "session_id": session_id,
        "latitude": req.latitude,
        "longitude": req.longitude,
        "timestamp": req.timestamp.isoformat(),
    })
    db.commit()
    return {"status": "ok", "session_id": session_id}


@router.post("/inspections/{session_id}/stop")
def stop_inspection(
    session_id: str,
    db: Session = Depends(get_db),
    user=Depends(require_role("inspection_vehicle", "equipment_supervisor")),
):
    row = db.execute(
        text("UPDATE inspection_sessions SET status='completed',ended_at=now() WHERE id=:id RETURNING id::text"),
        {"id": session_id},
    ).first()
    if not row:
        raise HTTPException(404, "Inspection session not found")
    db.commit()
    return {"status": "completed", "session_id": session_id}


@router.get("/inspections")
def list_inspections(
    limit: int = Query(default=100, ge=1, le=500),
    db: Session = Depends(get_db),
    user=Depends(require_role("equipment_supervisor")),
):
    return list(db.execute(text("""
      SELECT i.id::text, i.status, i.started_at, i.ended_at, i.video_uri,
             i.video_storage_key, v.vehicle_code, v.label AS vehicle_label,
             ST_Y(i.last_position) AS latitude, ST_X(i.last_position) AS longitude
      FROM inspection_sessions i
      LEFT JOIN vehicles v ON v.id=i.vehicle_id
      ORDER BY i.started_at DESC LIMIT :limit
    """), {"limit": limit}).mappings())


@router.post("/jobs", response_model=PerceptionJobOut)
def create_job(
    req: PerceptionJobCreate,
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
):
    if user["role"] not in {"citizen", "inspection_vehicle", "equipment_supervisor"}:
        raise HTTPException(403, "This actor cannot submit perception jobs")
    try:
        path = resolve_media_key(req.storage_key)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    if not path.exists():
        raise HTTPException(404, "Media file not found in local storage")

    source = "citizen" if user["role"] == "citizen" else "inspection_vehicle"
    options = dict(req.options)
    if req.latitude is not None:
        options["latitude"] = req.latitude
        options["longitude"] = req.longitude
    if req.captured_at is not None:
        options["captured_at"] = req.captured_at.isoformat()

    row = db.execute(text("""
      INSERT INTO perception_jobs(
        job_type,source,storage_key,media_uri,session_id,options,created_by
      ) VALUES(
        :job_type,:source,:storage_key,:media_uri,:session_id,
        CAST(:options AS jsonb),:created_by
      )
      RETURNING id::text,job_type,source,storage_key,media_uri,session_id::text,
                status,progress,model_name,model_version,result,error,created_at,updated_at
    """), {
        "job_type": req.job_type,
        "source": source,
        "storage_key": req.storage_key,
        "media_uri": req.media_uri,
        "session_id": req.session_id,
        "options": json.dumps(options),
        "created_by": user["sub"],
    }).mappings().one()
    publish(db, "perception.job.queued", {"job_id": row["id"], "job_type": req.job_type})
    db.commit()
    return dict(row)


@router.get("/jobs/{job_id}", response_model=PerceptionJobOut)
def get_job(job_id: str, db: Session = Depends(get_db), user=Depends(get_current_user)):
    row = db.execute(text("""
      SELECT id::text,job_type,source,storage_key,media_uri,session_id::text,
             status,progress,model_name,model_version,result,error,created_at,updated_at
      FROM perception_jobs WHERE id=:id
    """), {"id": job_id}).mappings().first()
    if not row:
        raise HTTPException(404, "Perception job not found")
    return dict(row)


@router.get("/observations", response_model=List[ObservationOut])
def list_observations(
    session_id: str | None = None,
    limit: int = Query(default=100, ge=1, le=500),
    db: Session = Depends(get_db),
    user=Depends(require_role("equipment_supervisor", "inspection_vehicle")),
):
    rows = db.execute(text("""
      SELECT id::text,event_id::text,session_id::text,source,defect_type,confidence,
             severity_proxy,ST_Y(geom) latitude,ST_X(geom) longitude,captured_at,
             frame_index,frame_time_s,bbox_xyxy,media_uri,model_name,model_version,
             coalesce((metadata->>'demo')::boolean,false) demo
      FROM road_observations
      WHERE (CAST(:session AS text) IS NULL OR session_id::text=CAST(:session AS text))
      ORDER BY captured_at DESC
      LIMIT :limit
    """), {"session": session_id, "limit": limit}).mappings().all()
    return [dict(row) for row in rows]


@router.post("/events", response_model=RoadEventOut)
def submit_event(
    event: RoadEventIn,
    db: Session = Depends(get_db),
    user=Depends(require_role("inspection_vehicle", "equipment_supervisor")),
):
    row = db.execute(text("""
      WITH p AS (
        SELECT ST_SetSRID(ST_MakePoint(:lon,:lat),4326) AS g
      ), nearest AS (
        SELECT id FROM road_segments,p
        WHERE ST_DWithin(road_segments.geom::geography,p.g::geography,120)
        ORDER BY ST_Distance(road_segments.geom::geography,p.g::geography)
        LIMIT 1
      )
      INSERT INTO road_events(
        segment_id,event_type,source,severity,confidence,geom,observed_at,media_uri,payload,status
      )
      SELECT (SELECT id FROM nearest),:typ,:src,:sev,:conf,p.g,:ts,:media,
             jsonb_build_object('video_ref',CAST(:video AS text),'description',CAST(:descr AS text),'session_id',CAST(:session AS text)),
             'observed'
      FROM p
      RETURNING id::text,segment_id::text,event_type,severity,confidence,
                ST_Y(geom) latitude,ST_X(geom) longitude,source,observed_at,media_uri,status
    """), {
        "lon": event.longitude,
        "lat": event.latitude,
        "typ": event.defect_type,
        "src": event.source,
        "sev": event.severity,
        "conf": event.confidence,
        "ts": event.timestamp,
        "media": event.image_url,
        "video": event.video_ref,
        "descr": event.text_description,
        "session": event.session_id,
    }).mappings().one()
    payload = {
        "id": row["id"],
        "segment_id": row["segment_id"],
        "defect_type": row["event_type"],
        "severity": row["severity"],
        "confidence": row["confidence"],
        "latitude": row["latitude"],
        "longitude": row["longitude"],
        "source": row["source"],
    }
    publish(db, "road.event.created", payload)
    db.commit()
    return {
        **payload,
        "timestamp": row["observed_at"],
        "validated": row["status"] in ("validated", "closed"),
        "media_uri": row["media_uri"],
    }


@router.get("/events", response_model=List[RoadEventOut])
def list_events(limit: int = 100, db: Session = Depends(get_db)):
    rows = db.execute(text("""
      SELECT id::text,segment_id::text,event_type defect_type,severity,confidence,
             ST_Y(geom) latitude,ST_X(geom) longitude,source,
             observed_at timestamp,media_uri,status,coalesce((payload->>'demo')::boolean,false) demo
      FROM road_events ORDER BY observed_at DESC LIMIT :lim
    """), {"lim": min(limit, 500)}).mappings()
    return [{**r, "validated": r["status"] in ("validated", "closed")} for r in rows]


@router.patch("/events/{event_id}/validate")
def validate_event(
    event_id: str,
    db: Session = Depends(get_db),
    user=Depends(require_role("equipment_supervisor")),
):
    row = db.execute(text("""
      UPDATE road_events
      SET status='validated',updated_at=now(),
          payload=payload||jsonb_build_object('validated_by',CAST(:u AS text))
      WHERE id=:id
      RETURNING id::text,event_type
    """), {"id": event_id, "u": user["sub"]}).mappings().first()
    if not row:
        raise HTTPException(404, "Road event not found")
    publish(db, "road.event.validated", dict(row))
    db.commit()
    return {"status": "validated", **row}

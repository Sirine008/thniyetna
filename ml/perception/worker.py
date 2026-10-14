from __future__ import annotations

import json
import logging
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

from sqlalchemy import create_engine, text

from .config import settings
from .detector import RoadDamageDetector
from .gps import GpsSample, interpolate
from .video import iter_sampled_frames

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("thniyetna.m1")
engine = create_engine(settings.database_url, pool_pre_ping=True)


def _claim_job():
    with engine.begin() as conn:
        row = conn.execute(text("""
          WITH candidate AS (
            SELECT id FROM perception_jobs
            WHERE status='queued'
            ORDER BY created_at
            FOR UPDATE SKIP LOCKED
            LIMIT 1
          )
          UPDATE perception_jobs j
          SET status='running',attempts=attempts+1,claimed_at=now(),updated_at=now(),progress=0.01
          FROM candidate c
          WHERE j.id=c.id
          RETURNING j.id::text,j.job_type,j.source,j.storage_key,j.media_uri,
                    j.session_id::text,j.options,j.created_by
        """)).mappings().first()
        return dict(row) if row else None


def _fail(job_id: str, exc: Exception):
    log.exception("M1 job %s failed", job_id)
    with engine.begin() as conn:
        conn.execute(text("""
          UPDATE perception_jobs
          SET status='failed',error=:error,updated_at=now(),completed_at=now()
          WHERE id=:id
        """), {"id": job_id, "error": str(exc)[:4000]})
        conn.execute(text("""
          INSERT INTO notification_outbox(topic,payload)
          VALUES('perception.job.failed',CAST(:payload AS jsonb))
        """), {"payload": json.dumps({"job_id": job_id, "error": str(exc)[:500]})})


def _complete(job_id: str, result: dict):
    with engine.begin() as conn:
        conn.execute(text("""
          UPDATE perception_jobs
          SET status='completed',progress=1,result=CAST(:result AS jsonb),error=NULL,
              model_name=:model_name,model_version=:model_version,
              updated_at=now(),completed_at=now()
          WHERE id=:id
        """), {
            "id": job_id,
            "result": json.dumps(result),
            "model_name": settings.model_name,
            "model_version": settings.weights.name,
        })
        conn.execute(text("""
          INSERT INTO notification_outbox(topic,payload)
          VALUES('perception.job.completed',CAST(:payload AS jsonb))
        """), {"payload": json.dumps({"job_id": job_id, **result})})


def _media_path(storage_key: str) -> Path:
    path = (settings.media_root / storage_key).resolve()
    if settings.media_root not in path.parents:
        raise ValueError("Invalid media key")
    if not path.exists():
        raise FileNotFoundError(path)
    return path


def _gps_samples(session_id: str) -> list[GpsSample]:
    with engine.connect() as conn:
        rows = conn.execute(text("""
          SELECT captured_at,ST_Y(geom) latitude,ST_X(geom) longitude
          FROM inspection_positions
          WHERE session_id=:session
          ORDER BY captured_at
        """), {"session": session_id}).mappings().all()
    return [GpsSample(r["captured_at"], float(r["latitude"]), float(r["longitude"])) for r in rows]


def _session_started_at(session_id: str) -> datetime:
    with engine.connect() as conn:
        ts = conn.execute(text("SELECT started_at FROM inspection_sessions WHERE id=:id"), {"id": session_id}).scalar()
    if ts is None:
        raise ValueError("Inspection session not found")
    return ts


def _upsert_observation(
    *, job: dict, defect_type: str, confidence: float, severity: float,
    captured_at: datetime, latitude: float | None, longitude: float | None,
    bbox: tuple[float,float,float,float], frame_index: int | None,
    frame_time_s: float | None,
) -> str | None:
    """Persist one model observation and link it to a deduplicated RoadEvent."""
    with engine.begin() as conn:
        event_id = None
        segment_id = None
        if latitude is not None and longitude is not None:
            segment_id = conn.execute(text("""
              WITH p AS (SELECT ST_SetSRID(ST_MakePoint(:lon,:lat),4326) g)
              SELECT id FROM road_segments,p
              WHERE ST_DWithin(geom::geography,p.g::geography,120)
              ORDER BY ST_Distance(geom::geography,p.g::geography)
              LIMIT 1
            """), {"lat": latitude, "lon": longitude}).scalar()

            existing = conn.execute(text("""
              SELECT id::text FROM road_events
              WHERE event_type=:typ
                AND observed_at > :captured_at - (:days * interval '1 day')
                AND ST_DWithin(
                    geom::geography,
                    ST_SetSRID(ST_MakePoint(:lon,:lat),4326)::geography,
                    :radius
                )
              ORDER BY ST_Distance(
                    geom::geography,
                    ST_SetSRID(ST_MakePoint(:lon,:lat),4326)::geography
              ), observed_at DESC
              LIMIT 1
            """), {
                "typ": defect_type,
                "captured_at": captured_at,
                "days": settings.dedup_days,
                "lat": latitude,
                "lon": longitude,
                "radius": settings.dedup_radius_m,
            }).scalar()

            if existing:
                event_id = existing
                conn.execute(text("""
                  UPDATE road_events
                  SET severity=GREATEST(COALESCE(severity,0),:sev),
                      confidence=GREATEST(COALESCE(confidence,0),:conf),
                      observed_at=GREATEST(observed_at,:captured),
                      updated_at=now(),
                      payload=payload || jsonb_build_object(
                        'last_model',:model,
                        'observation_count',COALESCE((payload->>'observation_count')::int,0)+1
                      )
                  WHERE id=:id
                """), {
                    "id": event_id, "sev": severity, "conf": confidence,
                    "captured": captured_at, "model": settings.model_name,
                })
            else:
                event_id = conn.execute(text("""
                  INSERT INTO road_events(
                    segment_id,event_type,source,severity,confidence,geom,observed_at,
                    media_uri,payload,status
                  ) VALUES(
                    :segment,:typ,:source,:sev,:conf,
                    ST_SetSRID(ST_MakePoint(:lon,:lat),4326),:captured,:media,
                    jsonb_build_object('model',CAST(:model AS text),'observation_count',1,'job_id',CAST(:job_id AS text)),
                    'observed'
                  ) RETURNING id::text
                """), {
                    "segment": segment_id, "typ": defect_type, "source": job["source"],
                    "sev": severity, "conf": confidence, "lon": longitude, "lat": latitude,
                    "captured": captured_at, "media": job.get("media_uri"),
                    "model": settings.model_name, "job_id": job["id"],
                }).scalar_one()
                conn.execute(text("""
                  INSERT INTO notification_outbox(topic,payload)
                  VALUES('road.event.created',CAST(:payload AS jsonb))
                """), {"payload": json.dumps({
                    "id": event_id, "defect_type": defect_type,
                    "severity": severity, "confidence": confidence,
                    "latitude": latitude, "longitude": longitude,
                    "source": job["source"],
                })})

        conn.execute(text("""
          INSERT INTO road_observations(
            event_id,session_id,source,defect_type,confidence,severity_proxy,geom,
            captured_at,frame_index,frame_time_s,bbox_xyxy,media_uri,model_name,
            model_version,metadata
          ) VALUES(
            :event,:session,:source,:typ,:conf,:sev,
            CASE WHEN CAST(:lat AS double precision) IS NULL THEN NULL ELSE ST_SetSRID(ST_MakePoint(:lon,:lat),4326) END,
            :captured,:frame_index,:frame_time,CAST(:bbox AS jsonb),:media,:model,:version,
            jsonb_build_object('job_id',CAST(:job_id AS text))
          )
        """), {
            "event": event_id, "session": job.get("session_id"), "source": job["source"],
            "typ": defect_type, "conf": confidence, "sev": severity,
            "lat": latitude, "lon": longitude, "captured": captured_at,
            "frame_index": frame_index, "frame_time": frame_time_s,
            "bbox": json.dumps(list(map(float, bbox))), "media": job.get("media_uri"),
            "model": settings.model_name, "version": settings.weights.name,
            "job_id": job["id"],
        })
        return event_id


def _process_image(job: dict, detector: RoadDamageDetector) -> dict:
    import cv2

    path = _media_path(job["storage_key"])
    image = cv2.imread(str(path))
    if image is None:
        raise ValueError(f"Cannot decode image: {path}")
    options = job.get("options") or {}
    lat = options.get("latitude")
    lon = options.get("longitude")
    captured_at_raw = options.get("captured_at")
    captured_at = datetime.fromisoformat(captured_at_raw) if captured_at_raw else datetime.now(timezone.utc)
    detections = detector.predict_batch([image])[0]
    event_ids = []
    for d in detections:
        event_id = _upsert_observation(
            job=job, defect_type=d.defect_type, confidence=d.confidence,
            severity=d.severity_proxy, captured_at=captured_at,
            latitude=lat, longitude=lon, bbox=d.bbox_xyxy,
            frame_index=None, frame_time_s=None,
        )
        if event_id:
            event_ids.append(event_id)
    return {"detections": len(detections), "events": len(set(event_ids))}


def _process_video(job: dict, detector: RoadDamageDetector) -> dict:
    path = _media_path(job["storage_key"])
    session_id = job.get("session_id")
    if not session_id:
        raise ValueError("Video job requires session_id")
    gps = _gps_samples(session_id)
    if not gps:
        raise ValueError("No GPS samples found for video session")
    start = _session_started_at(session_id)

    sampled = list(iter_sampled_frames(path, target_fps=settings.video_fps))
    detections_total = 0
    event_ids: list[str] = []
    total = max(1, len(sampled))

    for offset in range(0, len(sampled), settings.batch_size):
        batch = sampled[offset: offset + settings.batch_size]
        predictions = detector.predict_batch([f.image for f in batch])
        for frame, detections in zip(batch, predictions):
            captured_at = start + timedelta(seconds=frame.time_s)
            loc = interpolate(gps, captured_at)
            lat, lon = loc if loc is not None else (None, None)
            for d in detections:
                detections_total += 1
                event_id = _upsert_observation(
                    job=job, defect_type=d.defect_type, confidence=d.confidence,
                    severity=d.severity_proxy, captured_at=captured_at,
                    latitude=lat, longitude=lon, bbox=d.bbox_xyxy,
                    frame_index=frame.frame_index, frame_time_s=frame.time_s,
                )
                if event_id:
                    event_ids.append(event_id)
        progress = min(0.99, (offset + len(batch)) / total)
        with engine.begin() as conn:
            conn.execute(text("UPDATE perception_jobs SET progress=:p,updated_at=now() WHERE id=:id"), {
                "p": progress, "id": job["id"],
            })

    return {
        "sampled_frames": len(sampled),
        "detections": detections_total,
        "events": len(set(event_ids)),
        "target_fps": settings.video_fps,
    }


def main():
    detector = None
    while True:
        job = _claim_job()
        if not job:
            time.sleep(settings.poll_seconds)
            continue
        try:
            if detector is None:
                detector = RoadDamageDetector(
                    settings.weights,
                    device=settings.device,
                    imgsz=settings.imgsz,
                    confidence=settings.confidence,
                    iou=settings.iou,
                )
            log.info("Processing M1 job %s (%s)", job["id"], job["job_type"])
            if job["job_type"] == "image":
                result = _process_image(job, detector)
            elif job["job_type"] == "video":
                result = _process_video(job, detector)
            else:
                raise ValueError(f"Unsupported job type: {job['job_type']}")
            _complete(job["id"], result)
            log.info("Completed M1 job %s: %s", job["id"], result)
        except Exception as exc:
            _fail(job["id"], exc)
            # If model loading failed, retry loading on a future job after weights are mounted.
            if isinstance(exc, FileNotFoundError):
                detector = None


if __name__ == "__main__":
    main()

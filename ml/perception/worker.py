from __future__ import annotations

import json
import logging
import time
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

from sqlalchemy import create_engine, text

from .config import settings
from .detector import RoadDamageDetector
from .gps import GpsSample, interpolate
from .video import iter_sampled_frames, video_info
from .video_pipeline import FrameDetection, aggregate_tracks, geolocate, parse_gpx, per_class, video_start

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
    frame_time_s: float | None, media_uri: str | None = None, extra: dict | None = None,
) -> str | None:
    """Persist one model observation and link it to a deduplicated RoadEvent.
    No position → observation only (no road event). `media_uri` overrides the job media (video evidence frame);
    `extra` is merged into the event payload and the observation metadata (video context, demo tag)."""
    media = media_uri or job.get("media_uri")
    extra = extra or {}
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
                        'last_model',CAST(:model AS text),
                        'observation_count',COALESCE((payload->>'observation_count')::int,0)+1
                      )
                  WHERE id=:id
                """), {
                    "id": event_id, "sev": severity, "conf": confidence,
                    "captured": captured_at, "model": settings.model_name,
                })
                if extra.get("source_kind") == "video" and confidence >= float(conn.execute(
                        text("SELECT COALESCE(confidence,0) FROM road_events WHERE id=:id"), {"id": event_id}).scalar() or 0):
                    # the best video evidence becomes the event image
                    conn.execute(text("UPDATE road_events SET media_uri=:m WHERE id=:id"), {"m": media, "id": event_id})
            else:
                event_id = conn.execute(text("""
                  INSERT INTO road_events(
                    segment_id,event_type,source,severity,confidence,geom,observed_at,
                    media_uri,payload,status
                  ) VALUES(
                    :segment,:typ,:source,:sev,:conf,
                    ST_SetSRID(ST_MakePoint(:lon,:lat),4326),:captured,:media,
                    jsonb_build_object('model',CAST(:model AS text),'observation_count',1,'job_id',CAST(:job_id AS text))
                      || CAST(:extra AS jsonb),
                    'observed'
                  ) RETURNING id::text
                """), {
                    "segment": segment_id, "typ": defect_type, "source": job["source"],
                    "sev": severity, "conf": confidence, "lon": longitude, "lat": latitude,
                    "captured": captured_at, "media": media,
                    "model": settings.model_name, "job_id": job["id"], "extra": json.dumps(extra),
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
            jsonb_build_object('job_id',CAST(:job_id AS text)) || CAST(:extra AS jsonb)
          )
        """), {
            "event": event_id, "session": job.get("session_id"), "source": job["source"],
            "typ": defect_type, "conf": confidence, "sev": severity,
            "lat": latitude, "lon": longitude, "captured": captured_at,
            "frame_index": frame_index, "frame_time": frame_time_s,
            "bbox": json.dumps(list(map(float, bbox))), "media": media,
            "model": settings.model_name, "version": settings.weights.name,
            "job_id": job["id"], "extra": json.dumps(extra),
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


DEMO_LABEL = "DÉMO — données fictives"


def _save_evidence(image, detection: FrameDetection) -> str:
    """Best frame of a tracked defect with its box and label drawn, saved under frames/ (public media URL)."""
    import cv2

    img = image.copy()
    h, w = img.shape[:2]
    x1, y1, x2, y2 = (int(round(v)) for v in detection.bbox_xyxy)
    thick = max(2, w // 400)
    red = (40, 40, 198)  # BGR
    cv2.rectangle(img, (x1, y1), (x2, y2), red, thick)
    label = f"{detection.defect_type} {detection.confidence:.0%}"
    scale = max(0.5, w / 1600)
    (tw, th), base = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, scale, max(1, thick // 2))
    ty = max(th + base + 4, y1)
    cv2.rectangle(img, (x1, ty - th - base - 4), (x1 + tw + 8, ty), red, -1)
    cv2.putText(img, label, (x1 + 4, ty - base - 2), cv2.FONT_HERSHEY_SIMPLEX, scale, (255, 255, 255), max(1, thick // 2), cv2.LINE_AA)
    key = f"frames/{uuid.uuid4().hex}.jpg"
    path = (settings.media_root / key).resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    if not cv2.imwrite(str(path), img, [cv2.IMWRITE_JPEG_QUALITY, 88]):
        raise IOError(f"Cannot write evidence frame {path}")
    return f"{settings.media_public_prefix}/{key}"


def _video_gps(job: dict) -> tuple[list[GpsSample], datetime | None, str]:
    """GPS track and absolute time of the first frame: GPX sent with the video (job options), else the
    session's heartbeat points; ([], None, 'none') when no GPS is available (the video is then unlocated)."""
    options = job.get("options") or {}
    offset = float(options.get("gps_offset_s", settings.gps_offset_s) or 0)
    if options.get("gpx"):
        samples = parse_gpx(options["gpx"])
        if samples:
            return samples, video_start(samples, options.get("video_started_at"), offset), "gpx"
        return [], None, "none"
    session_id = job.get("session_id")
    if session_id:
        samples = _gps_samples(session_id)
        if samples:
            explicit = options.get("video_started_at")
            base = video_start(samples, explicit, 0) if explicit else _session_started_at(session_id)
            return samples, base + timedelta(seconds=offset), "session"
    return [], None, "none"


def _process_video(job: dict, detector: RoadDamageDetector) -> dict:
    """Sampled frames → ByteTrack → one defect per track (best frame as evidence) → nearest segment / road event.
    Unlocated defects (no GPS) are kept as observations without a road event."""
    t0 = time.monotonic()
    path = _media_path(job["storage_key"])
    options = job.get("options") or {}
    demo = bool(options.get("demo"))
    samples, start, gps_source = _video_gps(job)
    info = video_info(path)
    expected = max(1, int(info["duration_s"] * settings.video_fps) + 1)

    tracker = detector.new_tracker(settings.tracker)
    raw: list[FrameDetection] = []
    best_image: dict = {}       # track id (or ("frame", index) for untracked boxes) -> image of the best frame
    best_conf: dict = {}
    frames = 0
    for frame in iter_sampled_frames(path, target_fps=settings.video_fps):
        frames += 1
        for det, track_id in detector.detect_and_track(frame.image, tracker):
            fd = FrameDetection(frame.frame_index, round(frame.time_s, 3), det.defect_type, det.confidence,
                                det.bbox_xyxy, det.severity_proxy, track_id)
            raw.append(fd)
            key = track_id if track_id is not None else ("frame", frame.frame_index)
            if det.confidence > best_conf.get(key, -1):
                best_conf[key], best_image[key] = det.confidence, frame.image
        if frames % 10 == 0:
            with engine.begin() as conn:
                conn.execute(text("UPDATE perception_jobs SET progress=:p,updated_at=now() WHERE id=:id"),
                             {"p": min(0.95, frames / expected), "id": job["id"]})

    defects = aggregate_tracks(raw)
    records = geolocate(defects, samples, start, settings.gps_max_gap_s)
    event_ids: list[str] = []
    located = 0
    for rec in records:
        d = rec.defect
        key = d.best.track_id if d.best.track_id is not None else ("frame", d.best.frame_index)
        evidence = _save_evidence(best_image[key], d.best)
        extra = {"source_kind": "video", "video_media_uri": job.get("media_uri"), "track": d.key,
                 "track_frames": d.frames, "track_first_s": d.first_s, "track_last_s": d.last_s,
                 "frame_time_s": d.best.time_s, "session_id": job.get("session_id"), "located": rec.creates_road_event}
        if demo:
            extra.update({"demo": True, "demo_label": DEMO_LABEL})
        event_id = _upsert_observation(
            job=job, defect_type=d.defect_type, confidence=d.best.confidence, severity=d.best.severity,
            captured_at=rec.captured_at, latitude=rec.latitude, longitude=rec.longitude, bbox=d.best.bbox_xyxy,
            frame_index=d.best.frame_index, frame_time_s=d.best.time_s, media_uri=evidence, extra=extra,
        )
        located += rec.creates_road_event
        if event_id:
            event_ids.append(event_id)

    return {
        "video_duration_s": round(info["duration_s"], 2),
        "source_fps": round(info["fps"], 2),
        "sample_fps": settings.video_fps,
        "frames_processed": frames,
        "processing_time_s": round(time.monotonic() - t0, 1),
        "detections_before_tracking": len(raw),
        "detections_before_tracking_per_class": per_class(raw),
        "defects_after_tracking": len(defects),
        "defects_after_tracking_per_class": per_class(defects),
        "untracked_single_frame": sum(1 for d in defects if d.best.track_id is None),
        "gps_source": gps_source,
        "located_defects": located,
        "unlocated": gps_source == "none" or located < len(defects),
        "events": len(set(event_ids)),
        "tracker": settings.tracker,
        "demo": demo,
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

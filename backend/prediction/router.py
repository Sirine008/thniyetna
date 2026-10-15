"""M2 Risk API.

Served values come from the M2 model batch written by the `m2-worker`
(ml/prediction/jobs/score.py) into `risk_scores` / `governorate_risk_forecasts`.
The API stays light: it never loads scikit-learn / XGBoost.

When no fresh model score exists for a segment (worker not running yet, new
segment), the transparent contextual-v1 engine below is used as a fallback and
the response says so (`source = "contextual-fallback"`).
"""
import json
import os
from datetime import date
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import text
from sqlalchemy.orm import Session

from shared.auth import require_role
from shared.db import get_db
from shared.realtime import publish
from shared.utils import category

from .schemas import GovernorateForecast, RiskRequest, RiskResponse, WeatherIn

router = APIRouter()
M2_MODEL_DIR = Path(os.getenv("M2_MODEL_DIR", "/models/m2"))

_LATEST_MODEL_SCORE = """
    SELECT r.segment_id::text segment_id, s.segment_code, r.risk_score, r.risk_category, r.risk_level,
           r.predicted_condition, r.maintenance_priority, r.horizon_days, r.components, r.top_factors,
           r.model_version, r.created_at computed_at, r.valid_until
    FROM risk_scores r JOIN road_segments s ON s.id = r.segment_id
    WHERE r.risk_level IS NOT NULL AND (r.valid_until IS NULL OR r.valid_until > now())
      AND (s.id::text = :id OR s.segment_code = :id)
    ORDER BY r.created_at DESC LIMIT 1
"""


def _model_response(row) -> RiskResponse:
    factors = row["top_factors"] or []
    return RiskResponse(
        segment_id=row["segment_id"], segment_code=row["segment_code"], risk_score=row["risk_score"],
        risk_category=row["risk_category"], risk_level=row["risk_level"],
        predicted_condition=row["predicted_condition"], maintenance_priority=row["maintenance_priority"],
        horizon_days=row["horizon_days"], components=row["components"], top_factors=factors,
        exposure_percentile=(row["components"] or {}).get("exposure_percentile"),
        contributing_factors=[f"{f['feature']} ({f['contribution']:+.2f})" for f in factors],
        model_version=row["model_version"], source="m2-model",
        computed_at=row["computed_at"], valid_until=row["valid_until"],
    )


# ----------------------------------------------------------------- contextual-v1 fallback (unchanged logic)
def _score(db, segment_id: str, horizon: int):
    seg = db.execute(text("SELECT id::text,segment_code,name FROM road_segments WHERE id::text=:id OR segment_code=:id"), {"id": segment_id}).mappings().first()
    if not seg:
        raise HTTPException(404, "Road segment not found")
    f = db.execute(text("""
      WITH s AS (SELECT id,geom FROM road_segments WHERE id::text=:id OR segment_code=:id),
      ev AS (SELECT count(*) n,coalesce(max(severity),0) maxsev FROM road_events,s WHERE segment_id=s.id AND observed_at>now()-interval '180 days'),
      cl AS (SELECT count(*) n FROM complaints,s WHERE ST_DWithin(complaints.geom::geography,ST_LineInterpolatePoint(s.geom,0.5)::geography,250) AND created_at>now()-interval '365 days'),
      w AS (SELECT precipitation_mm,coalesce(precipitation_probability,0) pp,coalesce(wind_kmh,0) wind,weather_code FROM weather_observations WHERE area_code='BIZERTE' ORDER BY observed_at DESC LIMIT 1)
      SELECT ev.n event_count,ev.maxsev,cl.n complaint_count,coalesce(w.precipitation_mm,0) rain,coalesce(w.pp,0) rain_probability,coalesce(w.wind,0) wind,coalesce(w.weather_code,'unknown') weather_code FROM ev,cl LEFT JOIN w ON true
    """), {"id": segment_id}).mappings().one()
    factors = []
    event_component = min(0.45, float(f["maxsev"]) * 0.30 + min(int(f["event_count"]), 5) * 0.03)
    history_component = min(0.20, int(f["complaint_count"]) * 0.06)
    weather_component = min(0.35, float(f["rain"]) / 60 * 0.25 + float(f["rain_probability"]) * 0.08 + max(0, float(f["wind"]) - 25) / 100 * 0.08)
    if f["event_count"]:
        factors.append(f"{f['event_count']} recent/historical road event(s)")
    if f["complaint_count"]:
        factors.append(f"{f['complaint_count']} nearby historical/current complaint(s)")
    if float(f["rain"]) >= 10:
        factors.append(f"heavy rainfall context ({float(f['rain']):.1f} mm)")
    if float(f["rain_probability"]) >= 0.6:
        factors.append(f"high precipitation probability ({float(f['rain_probability']) * 100:.0f}%)")
    score = max(0, min(1, 0.08 + event_component + history_component + weather_component))
    return seg, f, round(score, 3), factors


def _fallback(db, segment_id: str, horizon_hours: int) -> RiskResponse:
    seg, f, score, factors = _score(db, segment_id, horizon_hours)
    cat = category(score)
    db.execute(text("INSERT INTO risk_scores(segment_id,risk_score,risk_category,model_version,features) VALUES(:sid,:s,:c,'contextual-v1',jsonb_build_object('event_count',:e,'complaint_count',:cl,'rain_mm',:r,'wind_kmh',:w))"),
               {"sid": seg["id"], "s": score, "c": cat, "e": f["event_count"], "cl": f["complaint_count"], "r": f["rain"], "w": f["wind"]})
    db.execute(text("INSERT INTO risk_forecasts(segment_id,horizon_hours,risk_score,risk_category,contributing_factors) VALUES(:sid,:h,:s,:c,CAST(:f AS jsonb))"),
               {"sid": seg["id"], "h": horizon_hours, "s": score, "c": cat, "f": json.dumps(factors)})
    publish(db, "risk.updated", {"segment_id": seg["id"], "segment_code": seg["segment_code"], "risk_score": score, "risk_category": cat, "factors": factors, "source": "contextual-fallback"})
    db.commit()
    cond = "likely disrupted/fragile" if cat == "high" else "watch" if cat == "medium" else "normal"
    return RiskResponse(segment_id=seg["id"], segment_code=seg["segment_code"], risk_score=score, risk_category=cat,
                        predicted_condition=cond, contributing_factors=factors)


# ----------------------------------------------------------------- endpoints
@router.post("/risk", response_model=RiskResponse)
def predict_risk(req: RiskRequest, db: Session = Depends(get_db)):
    row = db.execute(text(_LATEST_MODEL_SCORE), {"id": req.segment_id}).mappings().first()
    if row:
        return _model_response(row)
    return _fallback(db, req.segment_id, req.horizon_hours)


@router.get("/risk/{segment_id}", response_model=RiskResponse)
def get_risk(segment_id: str, db: Session = Depends(get_db)):
    row = db.execute(text(_LATEST_MODEL_SCORE), {"id": segment_id}).mappings().first()
    if row:
        return _model_response(row)
    return _fallback(db, segment_id, 6)


@router.get("/risk/{segment_id}/contract")
def get_risk_contract(segment_id: str, db: Session = Depends(get_db)):
    """Exact RiskScore 1.1.0 record (data/schemas/risk_score.schema.json) for M3/M4."""
    rec = db.execute(text("""
        SELECT r.features FROM risk_scores r JOIN road_segments s ON s.id = r.segment_id
        WHERE r.risk_level IS NOT NULL AND (s.id::text = :id OR s.segment_code = :id)
        ORDER BY r.created_at DESC LIMIT 1"""), {"id": segment_id}).scalar()
    if rec is None:
        raise HTTPException(404, "No M2 model score for this segment yet")
    return rec


@router.get("/segments", response_model=list[RiskResponse])
def segment_risks(min_level: str | None = Query(default=None, pattern="^(low|medium|high|critical)$"),
                  top: float | None = Query(default=None, gt=0, le=1),
                  db: Session = Depends(get_db)):
    """Latest score of every segment. Model scores are read, never recomputed; only
    segments without a fresh model score go through the contextual fallback.
    `top=0.05` keeps the 5 % most exposed segments of their governorate (exposure_percentile)."""
    rows = db.execute(text("""
        SELECT DISTINCT ON (r.segment_id) r.segment_id::text segment_id, s.segment_code, r.risk_score,
               r.risk_category, r.risk_level, r.predicted_condition, r.maintenance_priority, r.horizon_days,
               r.components, r.top_factors, r.model_version, r.created_at computed_at, r.valid_until
        FROM risk_scores r JOIN road_segments s ON s.id = r.segment_id
        WHERE r.risk_level IS NOT NULL AND (r.valid_until IS NULL OR r.valid_until > now())
        ORDER BY r.segment_id, r.created_at DESC""")).mappings().all()
    out = [_model_response(r) for r in rows]
    scored = {r.segment_id for r in out}
    for sid in db.execute(text("SELECT id::text FROM road_segments ORDER BY segment_code")).scalars():
        if sid not in scored:
            out.append(_fallback(db, sid, 6))
    if min_level:
        order = ["low", "medium", "high", "critical"]
        keep = order[order.index(min_level):]
        out = [r for r in out if (r.risk_level or r.risk_category) in keep]
    if top is not None:
        out = [r for r in out if r.exposure_percentile is not None and r.exposure_percentile >= 1 - top]
        return sorted(out, key=lambda r: (r.exposure_percentile, r.risk_score), reverse=True)
    return sorted(out, key=lambda r: r.risk_score, reverse=True)


@router.get("/governorates", response_model=list[GovernorateForecast])
def governorate_forecasts(day: date | None = None, gov_code: str | None = None, db: Session = Depends(get_db)):
    """Daily accident-risk forecast per governorate (latest model version)."""
    rows = db.execute(text("""
        SELECT DISTINCT ON (f.gov_code, f.forecast_date) f.gov_code, a.name governorate, f.forecast_date,
               f.p_accident, f.alert, f.expected_accidents, f.p_fatal_accident, f.top_factors,
               f.history_staleness_days, f.model_version
        FROM governorate_risk_forecasts f LEFT JOIN admin_areas a ON a.code = f.gov_code
        WHERE f.forecast_date = coalesce(CAST(:d AS date), f.forecast_date)
          AND f.forecast_date >= CASE WHEN CAST(:d AS date) IS NULL THEN current_date ELSE f.forecast_date END
          AND f.gov_code = coalesce(:g, f.gov_code)
        ORDER BY f.gov_code, f.forecast_date, f.created_at DESC"""), {"d": day, "g": gov_code}).mappings().all()
    return [GovernorateForecast(**r) for r in rows]


@router.get("/model")
def model_info():
    """Current M2 model (models/m2/current.json, mounted read-only into the API)."""
    pointer = M2_MODEL_DIR / "current.json"
    if not pointer.exists():
        return {"status": "no-model", "fallback": "contextual-v1"}
    info = json.loads(pointer.read_text())
    card = M2_MODEL_DIR / "model_card.json"
    if card.exists():
        info["card"] = json.loads(card.read_text())
    return {"status": "ok", **info}


# ----------------------------------------------------------------- weather (unchanged)
@router.post("/weather")
def ingest_weather(req: WeatherIn, db: Session = Depends(get_db), user=Depends(require_role("equipment_supervisor", "transport_supervisor"))):
    row = db.execute(text("""INSERT INTO weather_observations(area_code,observed_at,precipitation_mm,precipitation_probability,wind_kmh,temperature_c,weather_code,source) VALUES(:a,:t,:p,:pp,:w,:tc,:wc,:src) RETURNING id::text"""),
                     {"a": req.area_code, "t": req.observed_at, "p": req.precipitation_mm, "pp": req.precipitation_probability, "w": req.wind_kmh, "tc": req.temperature_c, "wc": req.weather_code, "src": req.source}).mappings().one()
    publish(db, "weather.updated", {"id": row["id"], **req.model_dump(mode='json')})
    db.commit()
    return {"status": "accepted", **row}


@router.get("/weather/latest")
def latest_weather(db: Session = Depends(get_db)):
    r = db.execute(text("SELECT area_code,observed_at,precipitation_mm,precipitation_probability,wind_kmh,temperature_c,weather_code,source FROM weather_observations WHERE coalesce(payload->>'granularity','') <> 'daily' ORDER BY observed_at DESC LIMIT 1")).mappings().first()
    return r or {}


@router.post("/weather/refresh")
def refresh_bizerte_weather(db:Session=Depends(get_db),user=Depends(require_role("equipment_supervisor","transport_supervisor"))):
    """Fetch current Bizerte context from Open-Meteo; the service keeps a database fallback."""
    import urllib.parse,urllib.request,json
    params=urllib.parse.urlencode({
      "latitude":37.2744,"longitude":9.8739,
      "current":"temperature_2m,precipitation,precipitation_probability,weather_code,wind_speed_10m",
      "timezone":"Africa/Tunis"
    })
    try:
        with urllib.request.urlopen("https://api.open-meteo.com/v1/forecast?"+params,timeout=8) as r: body=json.load(r)
        cur=body.get("current",{})
        row=db.execute(text("""INSERT INTO weather_observations(area_code,observed_at,precipitation_mm,precipitation_probability,wind_kmh,temperature_c,weather_code,source,payload) VALUES('BIZERTE',:t,:p,:pp,:w,:tc,:wc,'open-meteo',CAST(:payload AS jsonb)) RETURNING id::text"""),{
          "t":cur.get("time"),"p":cur.get("precipitation",0),"pp":None if cur.get("precipitation_probability") is None else cur.get("precipitation_probability")/100.0,
          "w":cur.get("wind_speed_10m"),"tc":cur.get("temperature_2m"),"wc":str(cur.get("weather_code")),"payload":json.dumps(body)
        }).mappings().one()
        publish(db,"weather.updated",{"id":row["id"],"source":"open-meteo","current":cur});db.commit()
        return {"status":"updated","source":"open-meteo","current":cur}
    except Exception as exc:
        latest=latest_weather(db)
        return {"status":"fallback","reason":str(exc),"latest":latest}

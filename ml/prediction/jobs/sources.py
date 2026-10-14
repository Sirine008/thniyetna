"""Input/output adapters for the M2 scoring job.

FileSource  -> raw files + OSM parquet (offline, Mode A, no database)
DbSource    -> PostGIS tables of the THNIYETNA stack (production, Mode A + B)

Both return the same DataFrame schemas, so jobs/score.py does not know where
the data comes from. This is what allows M1 events to be plugged in later
without changing the M2 architecture.
"""
from __future__ import annotations

import json
import os
from datetime import datetime

import numpy as np
import pandas as pd

from ..config import PROCESSED_DIR, SEGMENT
from ..io_accidents import load_accidents
from ..io_osm import load_road_stats
from ..io_weather import load_weather


class FileSource:
    def __init__(self, gov_codes: list[str] | None = None, classes=("motorway", "national", "regional", "local")):
        self.gov_codes, self.classes = gov_codes, list(classes)

    def accidents(self) -> pd.DataFrame:
        return load_accidents()

    def weather(self) -> pd.DataFrame:
        return load_weather()

    def road_stats(self) -> pd.DataFrame:
        return load_road_stats()

    def segments(self) -> pd.DataFrame:
        filters = [("gov_code", "in", self.gov_codes)] if self.gov_codes else None
        roads = pd.read_parquet(PROCESSED_DIR / "osm_roads.parquet", filters=filters,
                                columns=["osm_id", "road_class", "length_m", "gov_code", "name"])
        roads = roads[roads["road_class"].isin(self.classes)]
        return pd.DataFrame({"segment_id": roads["osm_id"].astype(str),
                             "segment_code": "OSM-" + roads["osm_id"].astype(str),
                             "gov_code": roads["gov_code"], "road_class": roads["road_class"],
                             "length_m": roads["length_m"], "name": roads["name"]}).reset_index(drop=True)

    def events(self) -> pd.DataFrame | None:
        return None

    def complaints(self) -> pd.Series | None:
        return None

    def write(self, gov_rows: pd.DataFrame, records: list[dict]) -> dict:
        return {"governorate_rows": len(gov_rows), "segment_rows": len(records), "written": False}


# ----------------------------------------------------------------------------- database
VALIDATED_STATUSES = ("validated", "confirmed", "in_progress", "scheduled")


def legacy_category(level: str) -> str:
    """3-level value for the existing risk_category column read by M3/M4 (critical -> high)."""
    return {"critical": "high"}.get(level, level)


class DbSource:
    def __init__(self, database_url: str | None = None, weather_area: str | None = None):
        from sqlalchemy import create_engine
        url = database_url or os.environ["DATABASE_URL"]
        self.engine = create_engine(url, pool_pre_ping=True)
        self.weather_area = weather_area or os.getenv("M2_WEATHER_AREA")  # None -> per-governorate if present

    # -- inputs ---------------------------------------------------------------
    def accidents(self) -> pd.DataFrame:
        q = """SELECT accident_id, occurred_on AS date, gov_code, delegation, place, road_class,
                      cause_group, killed, injured
               FROM accident_records"""
        df = pd.read_sql(q, self.engine, parse_dates=["date"])
        if df.empty:
            raise RuntimeError("accident_records is empty — run `python -m prediction.jobs.ingest accidents`")
        df["fatal"] = (df["killed"] > 0).astype(int)
        return df

    def weather(self) -> pd.DataFrame:
        """Daily rows written by `ingest weather` (payload.granularity = 'daily')."""
        q = """SELECT area_code, (observed_at AT TIME ZONE 'Africa/Tunis')::date AS date,
                      (payload->>'tavg')::float AS tavg, (payload->>'tmin')::float AS tmin,
                      (payload->>'tmax')::float AS tmax, precipitation_mm AS prcp,
                      wind_kmh AS wspd, (payload->>'pres')::float AS pres
               FROM weather_observations WHERE payload->>'granularity' = 'daily'"""
        df = pd.read_sql(q, self.engine, parse_dates=["date"])
        if df.empty:
            return load_weather()  # fall back to the configured file
        df = df.sort_values("date").drop_duplicates(["area_code", "date"], keep="last")
        per_gov = df[df["area_code"].str.startswith("TN-")]
        if self.weather_area:
            one = df[df["area_code"] == self.weather_area].drop(columns="area_code")
            return _regular(one)
        if per_gov["area_code"].nunique() >= 24:
            return pd.concat([_regular(d.drop(columns="area_code")).assign(gov_code=g)
                              for g, d in per_gov.groupby("area_code")], ignore_index=True)
        ref = df[~df["area_code"].str.startswith("TN-")]
        return _regular(ref.drop(columns="area_code").drop_duplicates("date", keep="last"))

    def road_stats(self) -> pd.DataFrame:
        return load_road_stats()

    def segments(self) -> pd.DataFrame:
        q = """SELECT s.id::text AS segment_id, s.segment_code, s.name,
                      coalesce(s.properties->>'m2_road_class', s.road_class) AS road_class_raw,
                      ST_Length(s.geom::geography) AS length_m,
                      coalesce(s.properties->>'gov_code', a.code) AS gov_code
               FROM road_segments s
               LEFT JOIN LATERAL (SELECT code FROM admin_areas a
                                  WHERE a.level = 'governorate'
                                    AND ST_Intersects(a.geom, ST_LineInterpolatePoint(s.geom, 0.5))
                                  LIMIT 1) a ON true"""
        df = pd.read_sql(q, self.engine)
        df["road_class"] = df["road_class_raw"].map(_road_class)
        return df.dropna(subset=["gov_code"]).drop(columns="road_class_raw")

    def events(self) -> pd.DataFrame:
        q = f"""SELECT segment_id::text AS segment_id, event_type, severity, confidence, observed_at, status,
                       (status IN {VALIDATED_STATUSES} OR coalesce((payload->>'validated')::boolean, false)) AS validated
                FROM road_events
                WHERE segment_id IS NOT NULL AND observed_at > now() - interval '365 days'"""
        return pd.read_sql(q, self.engine)

    def complaints(self) -> pd.Series:
        q = """SELECT s.id::text AS segment_id, count(c.id) AS n
               FROM road_segments s
               JOIN complaints c ON c.status NOT IN ('resolved', 'closed', 'rejected')
                AND ST_DWithin(c.geom::geography, s.geom::geography, :r)
                AND c.created_at > now() - interval '365 days'
               GROUP BY s.id"""
        from sqlalchemy import text
        with self.engine.connect() as cx:
            df = pd.read_sql(text(q), cx, params={"r": SEGMENT.complaint_radius_m})
        return df.set_index("segment_id")["n"]

    # -- outputs --------------------------------------------------------------
    def write(self, gov_rows: pd.DataFrame, records: list[dict]) -> dict:
        from sqlalchemy import text
        with self.engine.begin() as cx:
            for r in gov_rows.to_dict("records"):
                cx.execute(text("""
                    INSERT INTO governorate_risk_forecasts
                      (gov_code, forecast_date, p_accident, alert, expected_accidents, p_fatal_accident,
                       top_factors, history_staleness_days, model_version)
                    VALUES (:g, :d, :p, :a, :e, :pf, CAST(:tf AS jsonb), :hs, :mv)
                    ON CONFLICT (gov_code, forecast_date, model_version) DO UPDATE SET
                      p_accident = EXCLUDED.p_accident, alert = EXCLUDED.alert,
                      expected_accidents = EXCLUDED.expected_accidents,
                      p_fatal_accident = EXCLUDED.p_fatal_accident, top_factors = EXCLUDED.top_factors,
                      history_staleness_days = EXCLUDED.history_staleness_days, created_at = now()"""),
                    {"g": r["gov_code"], "d": r["date"].date(), "p": float(r["p_accident"]), "a": bool(r["alert"]),
                     "e": float(r["expected_accidents"]), "pf": _f(r.get("p_fatal_accident")),
                     "tf": json.dumps(r["top_factors"], ensure_ascii=False),
                     "hs": int(r["history_staleness_days"]), "mv": r["model_version"]})
            for rec in records:
                params = {
                    "sid": rec["segment_id"], "s": rec["risk_score"], "cat": legacy_category(rec["risk_level"]),
                    "lvl": rec["risk_level"], "h": rec["horizon_days"], "mv": rec["model"]["version"],
                    "run": rec["model"]["mlflow_run_id"], "comp": json.dumps(rec["components"]),
                    "tf": json.dumps(rec["top_factors"], ensure_ascii=False), "vu": rec["valid_until"],
                    "prio": rec["maintenance_priority"], "cond": rec["predicted_condition"],
                    "feat": json.dumps(rec, ensure_ascii=False, default=str),
                }
                cx.execute(text("""
                    INSERT INTO risk_scores (segment_id, risk_score, risk_category, model_version, features,
                        risk_level, horizon_days, components, top_factors, valid_until, mlflow_run_id,
                        maintenance_priority, predicted_condition)
                    VALUES (CAST(:sid AS uuid), :s, :cat, :mv, CAST(:feat AS jsonb), :lvl, :h,
                        CAST(:comp AS jsonb), CAST(:tf AS jsonb), CAST(:vu AS timestamptz), :run, :prio, :cond)"""), params)
                cx.execute(text("""
                    INSERT INTO risk_forecasts (segment_id, horizon_hours, risk_score, risk_category,
                        contributing_factors, model_version)
                    VALUES (CAST(:sid AS uuid), :hh, :s, :cat, CAST(:tf AS jsonb), :mv)"""),
                    {**params, "hh": rec["horizon_days"] * 24})
            summary = {
                "model_version": records[0]["model"]["version"] if records else None,
                "segments": len(records),
                "by_level": pd.Series([r["risk_level"] for r in records]).value_counts().to_dict() if records else {},
                "computed_at": datetime.utcnow().isoformat(timespec="seconds") + "Z",
            }
            cx.execute(text("INSERT INTO notification_outbox(topic, payload) VALUES ('risk.batch_updated', CAST(:p AS jsonb))"),
                       {"p": json.dumps(summary)})
        return {"governorate_rows": len(gov_rows), "segment_rows": len(records), "written": True}


def _f(v):
    return None if v is None or (isinstance(v, float) and np.isnan(v)) else float(v)


def _regular(df: pd.DataFrame) -> pd.DataFrame:
    df = df.sort_values("date").set_index("date")
    full = pd.date_range(df.index.min(), df.index.max(), freq="D")
    df = df.reindex(full)
    df.index.name = "date"
    df["prcp_missing"] = df["prcp"].isna().astype(int)
    for c in ("tavg", "tmin", "tmax", "wspd", "pres"):
        df[c] = df[c].interpolate(limit=3, limit_direction="both")
    return df.reset_index()


_OSM_TO_CLASS = {
    "motorway": "motorway", "motorway_link": "motorway", "trunk": "national", "trunk_link": "national",
    "primary": "national", "primary_link": "national", "secondary": "regional", "secondary_link": "regional",
    "tertiary": "local", "tertiary_link": "local", "unclassified": "local",
    "residential": "urban", "living_street": "urban",
}
_M2_CLASSES = {"motorway", "national", "regional", "local", "urban"}


def _road_class(raw) -> str:
    """road_segments.road_class may hold an OSM highway tag or an M2 class; default 'local'."""
    if raw is None or (isinstance(raw, float) and np.isnan(raw)):
        return "local"
    r = str(raw).strip().lower()
    return r if r in _M2_CLASSES else _OSM_TO_CLASS.get(r, "local")

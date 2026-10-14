"""Load M2 reference data into PostGIS (idempotent; safe to re-run).

    python -m prediction.jobs.ingest admin-areas               # governorate polygons (from OSM extract)
    python -m prediction.jobs.ingest accidents                 # accident export -> accident_records
    python -m prediction.jobs.ingest weather [--area TN_REF]   # daily weather file -> weather_observations
    python -m prediction.jobs.ingest segments --gov Bizerte --classes motorway,national,regional
                                                               # OSM ways -> road_segments (only missing codes)
    python -m prediction.jobs.ingest all --gov Bizerte

Requires DATABASE_URL and the Alembic migration 0003_m2_risk_model.
"""
from __future__ import annotations

import argparse
import json
import os

import pandas as pd
from sqlalchemy import create_engine, text

from ..config import PROCESSED_DIR, gov_code
from ..io_accidents import load_accidents
from ..io_weather import load_weather

BATCH = 2000


def _engine():
    return create_engine(os.environ["DATABASE_URL"], pool_pre_ping=True)


def _chunks(rows, n=BATCH):
    for i in range(0, len(rows), n):
        yield rows[i:i + n]


def admin_areas(engine) -> int:
    g = pd.read_parquet(PROCESSED_DIR / "governorates.parquet")
    with engine.begin() as cx:
        for r in g.itertuples():
            cx.execute(text("""
                INSERT INTO admin_areas(code, name, level, geom)
                VALUES (:c, :n, 'governorate', ST_Multi(ST_GeomFromText(:w, 4326)))
                ON CONFLICT (code) DO UPDATE SET name = EXCLUDED.name, geom = EXCLUDED.geom"""),
                {"c": r.gov_code, "n": r.name, "w": r.wkt})
    return len(g)


def accidents(engine) -> int:
    df = load_accidents()
    rows = [{
        "id": str(r.accident_id), "d": r.date.date(), "h": None if pd.isna(r.hour) else int(r.hour),
        "g": r.gov_code, "del": None if pd.isna(r.delegation) else str(r.delegation),
        "p": None if pd.isna(r.place) else str(r.place), "rc": r.road_class, "cg": r.cause_group,
        "k": int(r.killed), "i": int(r.injured),
    } for r in df.itertuples()]
    sql = text("""
        INSERT INTO accident_records(accident_id, occurred_on, hour, gov_code, delegation, place,
                                     road_class, cause_group, killed, injured, source)
        VALUES (:id, :d, :h, :g, :del, :p, :rc, :cg, :k, :i, 'open-data-onsr')
        ON CONFLICT (accident_id) DO UPDATE SET
          occurred_on = EXCLUDED.occurred_on, hour = EXCLUDED.hour, gov_code = EXCLUDED.gov_code,
          delegation = EXCLUDED.delegation, place = EXCLUDED.place, road_class = EXCLUDED.road_class,
          cause_group = EXCLUDED.cause_group, killed = EXCLUDED.killed, injured = EXCLUDED.injured""")
    with engine.begin() as cx:
        for chunk in _chunks(rows):
            cx.execute(sql, chunk)
    return len(rows)


def weather(engine, area: str = "TN_REF") -> int:
    w = load_weather()
    if "gov_code" not in w.columns:
        w = w.assign(gov_code=area)
    rows = []
    for r in w.itertuples():
        payload = {"granularity": "daily", "tavg": _n(r.tavg), "tmin": _n(r.tmin), "tmax": _n(r.tmax),
                   "pres": _n(r.pres)}
        rows.append({"a": r.gov_code, "t": f"{r.date.date()}T12:00:00+01:00", "p": _n(r.prcp) or 0.0,
                     "w": _n(r.wspd), "tc": _n(r.tavg), "pl": json.dumps(payload)})
    with engine.begin() as cx:
        cx.execute(text("DELETE FROM weather_observations WHERE payload->>'granularity' = 'daily' AND area_code = ANY(:a)"),
                   {"a": sorted({r["a"] for r in rows})})
        for chunk in _chunks(rows):
            cx.execute(text("""
                INSERT INTO weather_observations(area_code, observed_at, precipitation_mm, wind_kmh,
                                                 temperature_c, source, payload)
                VALUES (:a, CAST(:t AS timestamptz), :p, :w, :tc, 'm2-daily-import', CAST(:pl AS jsonb))"""), chunk)
    return len(rows)


def segments(engine, govs: list[str], classes: list[str]) -> int:
    roads = pd.read_parquet(PROCESSED_DIR / "osm_roads.parquet", filters=[("gov_code", "in", govs)])
    roads = roads[roads["road_class"].isin(classes)]
    rows = [{"code": f"OSM-{r.osm_id}", "name": _s(r.name), "rc": r.highway, "w": r.wkt,
             "props": json.dumps({"gov_code": r.gov_code, "m2_road_class": r.road_class, "osm_id": int(r.osm_id),
                                  "ref": _s(r.ref), "surface": _s(r.surface), "lit": bool(r.lit)},
                                 ensure_ascii=False)}
            for r in roads.itertuples()]
    with engine.begin() as cx:
        for chunk in _chunks(rows):
            cx.execute(text("""
                INSERT INTO road_segments(segment_code, name, road_class, geom, properties)
                VALUES (:code, :name, :rc, ST_GeomFromText(:w, 4326), CAST(:props AS jsonb))
                ON CONFLICT (segment_code) DO NOTHING"""), chunk)
    return len(rows)


def _s(v):
    return None if v is None or (isinstance(v, float) and pd.isna(v)) else str(v)


def _n(v):
    return None if v is None or pd.isna(v) else float(v)


def main(argv=None):
    ap = argparse.ArgumentParser(description="M2 ingestion into PostGIS")
    ap.add_argument("what", choices=["admin-areas", "accidents", "weather", "segments", "all"])
    ap.add_argument("--gov", default="Bizerte")
    ap.add_argument("--classes", default="motorway,national,regional")
    ap.add_argument("--area", default="TN_REF", help="area_code for a single-station weather file")
    args = ap.parse_args(argv)
    eng = _engine()
    if args.what in ("admin-areas", "all"):
        print(f"[ingest] admin_areas: {admin_areas(eng)}")
    if args.what in ("accidents", "all"):
        print(f"[ingest] accident_records: {accidents(eng):,}")
    if args.what in ("weather", "all"):
        print(f"[ingest] weather_observations (daily): {weather(eng, args.area):,}")
    if args.what in ("segments", "all"):
        govs = [gov_code(g) for g in args.gov.split(",")]
        print(f"[ingest] road_segments candidates: {segments(eng, govs, args.classes.split(',')):,}")


if __name__ == "__main__":
    main()

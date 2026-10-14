"""M2 command-line inference (file-based, no database needed).

Governorate forecast (Mode A):
    python -m prediction.predict governorate --gov Bizerte --date 2026-10-12 --days 7

Segment RiskScores for a governorate, OSM ways as segments, optional M1 events (Mode B):
    python -m prediction.predict segments --gov Bizerte --horizon 30 \
        --classes motorway,national,regional,local --events m1_events.json --out bizerte.geojson
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

from .config import GOV_CODES, GOV_NAME_FR, PROCESSED_DIR, SEGMENT, gov_code
from .contract import validate_many
from .explain import contributions, top_factors
from .features import build_inference_frame
from .io_accidents import load_accidents
from .io_osm import load_road_stats
from .io_weather import load_weather
from .registry import load_bundle
from .segment_risk import governorate_forecasts, score_segments


def _resolve_gov(label: str) -> str:
    code = gov_code(label)
    if code is None:
        raise SystemExit(f"Unknown governorate '{label}'. Known: {', '.join(GOV_NAME_FR.values())}")
    return code


def forecast_governorates(gov_codes: list[str], dates, bundle=None, acc=None, wx=None, rs=None) -> pd.DataFrame:
    bundle = bundle or load_bundle()
    acc = acc if acc is not None else load_accidents()
    wx = wx if wx is not None else load_weather()
    rs = rs if rs is not None else load_road_stats()
    feats, _ = build_inference_frame(gov_codes, dates, acc, wx, rs)
    feats = feats.reset_index(drop=True)
    out = feats[["gov_code", "date", "history_staleness_days", "weather_staleness_days"]].copy()
    out["governorate"] = out["gov_code"].map(GOV_NAME_FR)
    out["p_accident"] = bundle.predict_proba(feats)
    out["alert"] = out["p_accident"] >= bundle.threshold
    out["expected_accidents"] = bundle.predict_count(feats)
    pf = bundle.predict_fatal_proba(feats)
    if pf is not None:
        out["p_fatal_accident"] = pf
    c, _, _ = contributions(bundle.classifier, feats[bundle.features].astype(float))
    out["top_factors"] = [top_factors(c.loc[i], feats.loc[i, bundle.features], k=3) for i in feats.index]
    return out


def load_osm_segments(gov: str, classes: list[str], path: Path | None = None) -> pd.DataFrame:
    path = path or PROCESSED_DIR / "osm_roads.parquet"
    roads = pd.read_parquet(path, filters=[("gov_code", "==", gov)])
    roads = roads[roads["road_class"].isin(classes)].copy()
    roads["segment_id"] = roads["osm_id"].astype(str)
    roads["segment_code"] = "OSM-" + roads["segment_id"]
    return roads.reset_index(drop=True)


def snap_events(events: pd.DataFrame, segments: pd.DataFrame, max_dist_m: float = 30.0) -> pd.DataFrame:
    """Attach M1 events given as lat/lon to the nearest segment (<= max_dist_m)."""
    import shapely
    if "segment_id" in events.columns and events["segment_id"].notna().all():
        return events
    geoms = shapely.from_wkt(segments["wkt"].to_numpy())
    tree = shapely.STRtree(geoms)
    pts = shapely.points(events["longitude"].to_numpy(), events["latitude"].to_numpy())
    deg = max_dist_m / 111_000
    idx_pts, idx_geo = tree.query_nearest(pts, max_distance=deg, all_matches=False)
    ev = events.copy()
    ev["segment_id"] = None
    ev.loc[ev.index[idx_pts], "segment_id"] = segments["segment_id"].to_numpy()[idx_geo]
    return ev.dropna(subset=["segment_id"])


def read_events(path: str | Path) -> pd.DataFrame:
    """Accepts the RoadEvent contract (data/schemas/road_event.schema.json) as a JSON list."""
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    ev = pd.DataFrame(raw if isinstance(raw, list) else raw.get("events", []))
    ev = ev.rename(columns={"timestamp": "observed_at", "defect_type": "event_type"})
    if "location" in ev.columns:  # road_event.example.json variant
        ev["latitude"] = ev["location"].map(lambda d: d["lat"])
        ev["longitude"] = ev["location"].map(lambda d: d["lon"])
    return ev


def to_geojson(records: list[dict], segments: pd.DataFrame) -> dict:
    import shapely
    geom = dict(zip(segments["segment_id"], segments["wkt"]))
    feats = []
    for r in records:
        g = shapely.from_wkt(geom[r["segment_id"]])
        props = {k: v for k, v in r.items() if k not in ("components", "model", "top_factors")}
        props.update({f"component_{k}": v for k, v in r["components"].items()})
        props["model_version"] = r["model"]["version"]
        props["top_factors"] = json.dumps(r["top_factors"], ensure_ascii=False)
        feats.append({"type": "Feature", "geometry": shapely.geometry.mapping(g), "properties": props})
    return {"type": "FeatureCollection", "features": feats}


def main(argv=None):
    ap = argparse.ArgumentParser(description="M2 inference")
    sub = ap.add_subparsers(dest="cmd", required=True)
    g = sub.add_parser("governorate", help="daily accident-risk forecast for governorates")
    g.add_argument("--gov", default="all", help="name/code, comma-separated, or 'all'")
    g.add_argument("--date", default=None, help="first forecast day (default: tomorrow)")
    g.add_argument("--days", type=int, default=1)
    g.add_argument("--json", action="store_true")
    s = sub.add_parser("segments", help="RiskScore per road segment (OSM ways)")
    s.add_argument("--gov", required=True)
    s.add_argument("--horizon", type=int, default=SEGMENT.horizon_days)
    s.add_argument("--classes", default="motorway,national,regional,local")
    s.add_argument("--events", default=None, help="M1 RoadEvent JSON list (lat/lon or segment_id)")
    s.add_argument("--as-of", default=None, help="scoring date (default: today)")
    s.add_argument("--out", default=None, help=".geojson or .json output path")
    args = ap.parse_args(argv)

    if args.cmd == "governorate":
        govs = GOV_CODES if args.gov == "all" else [_resolve_gov(x) for x in args.gov.split(",")]
        start = pd.Timestamp(args.date) if args.date else pd.Timestamp.today().normalize() + pd.Timedelta(days=1)
        res = forecast_governorates(govs, pd.date_range(start, periods=args.days, freq="D"))
        if args.json:
            print(res.assign(date=res["date"].dt.strftime("%Y-%m-%d")).to_json(orient="records", force_ascii=False, indent=2))
            return
        cols = ["date", "governorate", "p_accident", "alert", "expected_accidents", "p_fatal_accident", "history_staleness_days"]
        print(res[[c for c in cols if c in res.columns]].round(3).to_string(index=False))
        if (res["history_staleness_days"] > 0).any():
            print(f"\nnote: accident history ends {res['history_staleness_days'].max()} day(s) before the "
                  "forecast reference day — history features use the last observed day.")
        return

    gov = _resolve_gov(args.gov)
    as_of = pd.Timestamp(args.as_of) if args.as_of else pd.Timestamp.today().normalize()
    bundle = load_bundle()
    acc, wx, rs = load_accidents(), load_weather(), load_road_stats()
    dates = pd.date_range(as_of + pd.Timedelta(days=1), periods=args.horizon, freq="D")
    feats, _ = build_inference_frame([gov], dates, acc, wx, rs)
    fc = governorate_forecasts(bundle, feats.reset_index(drop=True))
    segs = load_osm_segments(gov, args.classes.split(","))
    events = None
    if args.events:
        events = snap_events(read_events(args.events), segs)
        print(f"[events] {len(events)} M1 event(s) snapped to segments")
    rain30 = float(wx.set_index("date")["prcp"].fillna(0).loc[:as_of].tail(30).sum())
    recs = score_segments(bundle, segs, fc, rs, events=events, rain30_by_gov={gov: rain30},
                          as_of=datetime(as_of.year, as_of.month, as_of.day, tzinfo=timezone.utc),
                          horizon_days=args.horizon)
    validate_many(recs)
    df = pd.DataFrame(recs)
    print(f"[segments] {len(df):,} segments scored for {GOV_NAME_FR[gov]} | horizon {args.horizon} d | "
          f"governorate E[accidents]={fc[gov].expected_accidents:.1f}")
    print(df["risk_level"].value_counts().to_string())
    top = df.sort_values("risk_score", ascending=False).head(10)
    print(top[["segment_code", "risk_score", "risk_level", "predicted_condition", "maintenance_priority"]].to_string(index=False))
    if args.out:
        out = Path(args.out)
        payload = to_geojson(recs, segs) if out.suffix == ".geojson" else recs
        out.write_text(json.dumps(payload, ensure_ascii=False))
        print(f"[out] {out}")


if __name__ == "__main__":
    main()

"""M2 scoring job (phases 13-15): governorate forecasts + segment RiskScores.

    python -m prediction.jobs.score --source db --once            # one batch into PostGIS
    python -m prediction.jobs.score --source db                   # worker loop (M2_SCORE_INTERVAL_S)
    python -m prediction.jobs.score --source file --gov Bizerte --once --out bizerte.json

The worker runs as the `m2-worker` Compose service (profile `m2`), isolated from
the API exactly like the M1 perception worker.
"""
from __future__ import annotations

import argparse
import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from ..config import GOV_CODES, SEGMENT, gov_code
from ..contract import validate_many
from ..explain import contributions, top_factors
from ..features import build_inference_frame
from ..registry import load_bundle
from ..segment_risk import exposure_percentiles, governorate_forecasts, score_segments


def segment_cutoff(as_of: pd.Timestamp | None, now: datetime | None = None) -> datetime:
    """Cut-off for M1 events in the segment condition part.

    Without --as-of it is the scoring moment, so an event observed (or validated) today counts in
    today's pass; the governorate day grid still starts at midnight. With --as-of it is that day's
    midnight UTC, so a replayed date stays reproducible.
    """
    if as_of is None:
        return now or datetime.now(timezone.utc)
    return datetime(as_of.year, as_of.month, as_of.day, tzinfo=timezone.utc)


def run_once(source, horizon_days: int | None = None, as_of: pd.Timestamp | None = None,
             gov_codes: list[str] | None = None, forecast_days: int = 7) -> dict:
    t0 = time.time()
    horizon_days = horizon_days or SEGMENT.horizon_days
    cutoff = segment_cutoff(as_of)
    as_of = (as_of or pd.Timestamp.now(tz="Africa/Tunis").tz_localize(None)).normalize()
    bundle = load_bundle()
    acc, wx, rs = source.accidents(), source.weather(), source.road_stats()
    govs = gov_codes or GOV_CODES
    dates = pd.date_range(as_of + pd.Timedelta(days=1), periods=horizon_days, freq="D")
    feats, _ = build_inference_frame(govs, dates, acc, wx, rs)
    feats = feats.reset_index(drop=True)

    # governorate x day table (first `forecast_days` days are published)
    near = feats[feats["date"] < dates[0] + pd.Timedelta(days=forecast_days)].reset_index(drop=True)
    X = near[bundle.features].astype(float)
    c, _, _ = contributions(bundle.classifier, X)
    gov_rows = near[["gov_code", "date", "history_staleness_days"]].copy()
    gov_rows["p_accident"] = bundle.predict_proba(near)
    gov_rows["alert"] = gov_rows["p_accident"] >= bundle.threshold
    gov_rows["expected_accidents"] = bundle.predict_count(near)
    pf = bundle.predict_fatal_proba(near)
    gov_rows["p_fatal_accident"] = pf if pf is not None else None
    gov_rows["top_factors"] = [top_factors(c.loc[i], X.loc[i], k=3) for i in near.index]
    gov_rows["model_version"] = bundle.version

    # segments
    fc = governorate_forecasts(bundle, feats)
    segs = source.segments()
    segs = segs[segs["gov_code"].isin(govs)].reset_index(drop=True)
    wxs = wx.copy()
    if "gov_code" in wxs.columns:
        rain30 = {g: float(d.set_index("date")["prcp"].fillna(0).loc[:as_of].tail(30).sum()) for g, d in wxs.groupby("gov_code")}
    else:
        r = float(wxs.set_index("date")["prcp"].fillna(0).loc[:as_of].tail(30).sum())
        rain30 = {g: r for g in govs}
    from ..condition_model import load as load_condition_model
    cond_model = load_condition_model()
    records = score_segments(bundle, segs, fc, rs, events=source.events(), complaints=source.complaints(),
                             rain30_by_gov=rain30, horizon_days=horizon_days, condition_model=cond_model,
                             as_of=cutoff) if len(segs) else []
    validate_many(records)
    written = source.write(gov_rows, records, exposure=exposure_percentiles(records))
    stale = int(feats["history_staleness_days"].max())
    return {"as_of": str(as_of.date()), "model_version": bundle.version, "horizon_days": horizon_days,
            "condition_model": cond_model.version if cond_model else "rule-prior",
            "governorates": len(govs), "history_staleness_days": stale,
            "levels": pd.Series([r["risk_level"] for r in records]).value_counts().to_dict() if records else {},
            "elapsed_s": round(time.time() - t0, 1), **written,
            "_gov_rows": gov_rows, "_records": records}


def main(argv=None):
    ap = argparse.ArgumentParser(description="M2 scoring job")
    ap.add_argument("--source", choices=["db", "file"], default=os.getenv("M2_SOURCE", "db"))
    ap.add_argument("--gov", default=None, help="restrict to governorates (comma-separated)")
    ap.add_argument("--horizon", type=int, default=SEGMENT.horizon_days)
    ap.add_argument("--as-of", default=None)
    ap.add_argument("--once", action="store_true")
    ap.add_argument("--out", default=None, help="file mode: write RiskScores JSON here")
    args = ap.parse_args(argv)
    govs = [gov_code(g) for g in args.gov.split(",")] if args.gov else None

    from .sources import DbSource, FileSource
    interval = int(os.getenv("M2_SCORE_INTERVAL_S", "86400"))
    while True:
        source = DbSource() if args.source == "db" else FileSource(gov_codes=govs)
        try:
            res = run_once(source, args.horizon, pd.Timestamp(args.as_of) if args.as_of else None, govs)
            recs = res.pop("_records")
            res.pop("_gov_rows")
            print(json.dumps(res, ensure_ascii=False), flush=True)
            if args.out:
                Path(args.out).write_text(json.dumps(recs, ensure_ascii=False, indent=1))
        except Exception as exc:  # keep the worker alive; next cycle retries
            print(json.dumps({"status": "error", "error": repr(exc)}), flush=True)
            if args.once:
                raise
        if args.once:
            return
        time.sleep(interval)


if __name__ == "__main__":
    main()

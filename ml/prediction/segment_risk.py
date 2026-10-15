"""From governorate-day forecasts (Mode A) + M1 road events (Mode B) to per-segment RiskScore.

risk_score = 1 - (1 - P_accident) * (1 - P_condition)

P_accident (trained, data-driven)
    The governorate model gives E[#accidents] for each day of the horizon. The
    expected count is thinned onto a segment proportionally to its share of the
    governorate's *exposure*, where exposure = length x road-class weight and the
    class weights are the accident rate per km by class learned from the
    accident records (train period). P = 1 - exp(-lambda_segment).

P_condition (M1-driven, rule-based prior until labelled history exists)
    Each M1 RoadEvent on the segment is a hazard: confidence x validation weight x
    exponential age decay x P(defect is or becomes severity >= 4 within horizon).
    Hazards combine as independent: P = 1 - prod(1 - h_i). Nearby open citizen
    complaints add a small hazard each. When enough labelled history exists,
    condition_model.py trains a replacement (same output, same contract).

condition_model.py (Mode B) replaces the prior once it passes its quality gate.
Without M1 events P_condition = 0 and the score is the accident component only:
the architecture is identical in Mode A and Mode B, only the inputs change.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

import numpy as np
import pandas as pd

from .config import CONTRACT_VERSION, MODEL_NAME, RISK_LEVELS, SEGMENT
from .explain import contributions

ROAD_IMPORTANCE = {"motorway": 1.0, "national": 0.9, "regional": 0.7, "local": 0.5, "urban": 0.4}
CLOSED_STATUSES = {"repaired", "resolved", "closed", "rejected", "false_positive"}


def _logit(p):
    p = np.clip(np.asarray(p, dtype=float), 1e-6, 1 - 1e-6)
    return np.log(p / (1 - p))


# ---------------------------------------------------------------- accident part
@dataclass
class GovernorateForecast:
    gov_code: str
    expected_accidents: float          # sum over horizon of E[#accidents/day]
    p_any_accident_day_mean: float     # mean calibrated P(>=1 accident) per day
    top_factors: list[dict]            # governorate model drivers (log-odds, averaged over horizon)
    history_staleness_days: int
    weather_staleness_days: int


def governorate_forecasts(bundle, features: pd.DataFrame, k: int = 3) -> dict[str, GovernorateForecast]:
    """features: output of build_inference_frame for all days of the horizon."""
    X = features[bundle.features].astype(float)
    p = bundle.predict_proba(features)
    lam = bundle.predict_count(features)
    contrib, _, _ = contributions(bundle.classifier, X)
    out = {}
    for g, idx in features.groupby("gov_code").groups.items():
        c = contrib.loc[idx].mean()
        v = X.loc[idx].mean()
        order = c.abs().sort_values(ascending=False).index[:k]
        out[g] = GovernorateForecast(
            gov_code=g,
            expected_accidents=float(lam[features.index.get_indexer(idx)].sum()),
            p_any_accident_day_mean=float(p[features.index.get_indexer(idx)].mean()),
            top_factors=[{"feature": f"gov:{f}", "contribution": round(float(c[f]), 4),
                          "value": None if pd.isna(v[f]) else round(float(v[f]), 3)} for f in order],
            history_staleness_days=int(features.loc[idx, "history_staleness_days"].max()),
            weather_staleness_days=int(features.loc[idx, "weather_staleness_days"].max()),
        )
    return out


def exposure_denominator(road_stats: pd.DataFrame, weights: dict[str, float]) -> dict[str, float]:
    """Sum over the whole governorate network of km x class weight."""
    out = {}
    for _, r in road_stats.iterrows():
        out[r["gov_code"]] = float(sum(r.get(f"road_km_{c}", 0.0) * w for c, w in weights.items()))
    return out


def accident_component(segments: pd.DataFrame, gov_fc: dict[str, GovernorateForecast],
                       denom: dict[str, float], weights: dict[str, float]) -> pd.DataFrame:
    w = segments["road_class"].map(weights).fillna(1.0)
    km = segments["length_m"].fillna(0) / 1000.0
    lam_g = segments["gov_code"].map(lambda g: gov_fc[g].expected_accidents if g in gov_fc else np.nan)
    den = segments["gov_code"].map(denom)
    lam_s = lam_g * (w * km) / den
    return pd.DataFrame({"class_weight": w, "lambda_segment": lam_s,
                         "p_accident": 1 - np.exp(-lam_s.fillna(0))}, index=segments.index)


# ---------------------------------------------------------------- condition part
def _p_severe(severity, horizon_days, rain30_mm):
    """P(defect is or becomes severity >= threshold within the horizon). Rule-based prior."""
    growth_per_month = 0.05 * (1 + np.clip(np.asarray(rain30_mm, dtype=float) / 50.0, 0.0, 1.0))  # wet periods accelerate decay
    projected = np.asarray(severity, dtype=float) + growth_per_month * horizon_days / 30.0
    return 1 / (1 + np.exp(-12 * (projected - SEGMENT.severe_defect_threshold)))


def condition_component(segments: pd.DataFrame, events: pd.DataFrame | None, as_of: pd.Timestamp,
                        rain30_mm: float = 0.0, complaints: pd.Series | None = None,
                        horizon_days: int | None = None, condition_model=None) -> pd.DataFrame:
    horizon_days = horizon_days or SEGMENT.horizon_days
    out = pd.DataFrame({"p_condition": 0.0, "n_events": 0, "max_effective_severity": 0.0}, index=segments.index)
    if events is not None and len(events):
        ev = events.copy()
        ev = ev[~ev.get("status", pd.Series("observed", index=ev.index)).isin(CLOSED_STATUSES)]
        ev["observed_at"] = pd.to_datetime(ev["observed_at"], utc=True).dt.tz_localize(None)
        ev = ev[ev["observed_at"] <= as_of]
        age = (as_of - ev["observed_at"]).dt.total_seconds() / 86400
        ev["decay"] = 0.5 ** (age / SEGMENT.event_half_life_days)
        validated = ev.get("validated", pd.Series(False, index=ev.index)).fillna(False).astype(bool)
        ev["v"] = np.where(validated, 1.0, SEGMENT.unvalidated_weight)
        ev["sev"] = ev["severity"].fillna(0.5).clip(0, 1)
        ev["conf"] = ev["confidence"].fillna(0.5).clip(0, 1)
        ev["h"] = ev["conf"] * ev["v"] * ev["decay"] * _p_severe(ev["sev"], horizon_days, rain30_mm)
        ev["eff_sev"] = ev["sev"] * ev["decay"]
        g = ev.groupby("segment_id")
        surv = g["h"].apply(lambda h: float(np.prod(1 - h.clip(0, 0.999))))
        sid = segments["segment_id"]
        out["p_condition"] = (1 - sid.map(surv)).fillna(0.0).to_numpy()
        out["n_events"] = sid.map(g.size()).fillna(0).astype(int).to_numpy()
        out["max_effective_severity"] = sid.map(g["eff_sev"].max()).fillna(0.0).to_numpy()
        if condition_model is not None:  # Mode B learned model replaces the prior
            out["p_condition"] = condition_model.predict(segments, events, as_of, rain30_mm)
    if complaints is not None:
        n = segments["segment_id"].map(complaints).fillna(0).to_numpy()
        pc = 1 - (1 - SEGMENT.complaint_hazard) ** n
        out["p_condition"] = 1 - (1 - out["p_condition"]) * (1 - pc)
        out["n_complaints"] = n.astype(int)
    else:
        out["n_complaints"] = 0
    return out


def predicted_condition(eff_sev: float, n_events: int) -> str:
    if n_events == 0:
        return "no_observed_defect"
    if eff_sev >= 0.75:
        return "critical"
    if eff_sev >= 0.5:
        return "poor"
    if eff_sev >= 0.25:
        return "fair"
    return "good"


def maintenance_priority(p_condition: float, road_class: str, p_acc_pct: float) -> tuple[str, float]:
    imp = ROAD_IMPORTANCE.get(road_class, 0.5)
    s = 0.75 * p_condition * imp + 0.25 * p_acc_pct
    level = "P1" if s >= 0.6 else "P2" if s >= 0.35 else "P3" if s >= 0.15 else "P4"
    return level, round(float(s), 4)


# ---------------------------------------------------------------- full scoring
def score_segments(bundle, segments: pd.DataFrame, gov_fc: dict[str, GovernorateForecast],
                   road_stats: pd.DataFrame, events: pd.DataFrame | None = None,
                   complaints: pd.Series | None = None, rain30_by_gov: dict[str, float] | None = None,
                   as_of: datetime | None = None, horizon_days: int | None = None,
                   condition_model=None) -> list[dict]:
    """segments needs: segment_id, gov_code, road_class, length_m (segment_code optional)."""
    horizon_days = horizon_days or SEGMENT.horizon_days
    now = as_of or datetime.now(timezone.utc)
    as_of_ts = pd.Timestamp(now).tz_localize(None) if pd.Timestamp(now).tzinfo else pd.Timestamp(now)
    weights = bundle.road_class_weights or {}
    seg = segments.reset_index(drop=True)
    acc = accident_component(seg, gov_fc, exposure_denominator(road_stats, weights), weights)

    cond_parts = []
    for g, part in seg.groupby("gov_code"):
        ev = events[events["segment_id"].isin(part["segment_id"])] if events is not None and len(events) else None
        cond_parts.append(condition_component(part, ev, as_of_ts, (rain30_by_gov or {}).get(g, 0.0),
                                              complaints, horizon_days, condition_model))
    cond = pd.concat(cond_parts).reindex(seg.index)

    risk = 1 - (1 - acc["p_accident"]) * (1 - cond["p_condition"])
    acc_pct = acc["p_accident"].rank(pct=True).fillna(0)
    computed_at = now.astimezone(timezone.utc) if now.tzinfo else now.replace(tzinfo=timezone.utc)
    results = []
    for i, s in seg.iterrows():
        r = float(np.clip(risk[i], 0, 1))
        factors = []
        if cond.at[i, "p_condition"] > 0:
            factors.append({"feature": "m1:road_condition",
                            "contribution": round(float(_logit(r) - _logit(acc.at[i, "p_accident"])), 4),
                            "value": int(cond.at[i, "n_events"] + cond.at[i, "n_complaints"])})
        factors.append({"feature": f"segment:road_class={s['road_class']}",
                        "contribution": round(float(np.log(max(acc.at[i, 'class_weight'], 1e-6))), 4),
                        "value": round(float(acc.at[i, "class_weight"]), 3)})
        fc = gov_fc.get(s["gov_code"])
        if fc:
            factors.extend(fc.top_factors)
        factors = sorted(factors, key=lambda f: abs(f["contribution"]), reverse=True)[:5]
        prio, prio_score = maintenance_priority(float(cond.at[i, "p_condition"]), s["road_class"], float(acc_pct[i]))
        results.append({
            "segment_id": str(s["segment_id"]),
            "segment_code": s.get("segment_code"),
            "governorate": s["gov_code"],
            "risk_score": round(r, 6),
            "risk_level": RISK_LEVELS.level(r),
            "horizon_days": int(horizon_days),
            "components": {
                "accident": round(float(acc.at[i, "p_accident"]), 6),
                "condition": round(float(cond.at[i, "p_condition"]), 6),
                "expected_accidents": round(float(acc.at[i, "lambda_segment"]) if pd.notna(acc.at[i, "lambda_segment"]) else 0.0, 6),
            },
            "predicted_condition": predicted_condition(float(cond.at[i, "max_effective_severity"]), int(cond.at[i, "n_events"])),
            "maintenance_priority": prio,
            "maintenance_priority_score": prio_score,
            "top_factors": factors,
            "computed_at": computed_at.isoformat(timespec="seconds"),
            "valid_until": (computed_at + timedelta(days=1)).isoformat(timespec="seconds"),
            "model": {"name": MODEL_NAME, "version": bundle.version, "mlflow_run_id": bundle.mlflow_run_id},
            "contract_version": CONTRACT_VERSION,
        })
    return results


def exposure_percentiles(records: list[dict]) -> dict[str, float]:
    """Display-only ranking: percentile of risk_score within the segment's governorate.

    0 = least exposed, 1 = most exposed; ties share the lower rank. Not a probability and
    not part of the RiskScore contract (stored next to it in risk_scores.components)."""
    if not records:
        return {}
    df = pd.DataFrame({"sid": [r["segment_id"] for r in records], "gov": [r["governorate"] for r in records],
                       "score": [r["risk_score"] for r in records]})
    rank = df.groupby("gov")["score"].rank(method="min")
    n = df.groupby("gov")["score"].transform("size")
    pct = ((rank - 1) / (n - 1)).where(n > 1, 1.0)
    return dict(zip(df["sid"], pct.round(4).astype(float)))

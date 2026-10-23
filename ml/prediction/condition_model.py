"""Mode B: trainable replacement for the rule-based condition prior.

Once M1 has produced enough RoadEvents, this learns
    P(a severity >= 4 defect (>= 0.75 on the 0..1 M1 scale) is observed on the
      segment within the next H days | segment state at reference day r)
from the event history itself — no manual labels needed beyond M1 + validation
by the equipment agents.

Panel: segment x reference day (every `step_days`), features from events
observed <= r only, label from events in (r, r+H]. Temporal split on r.

    python -m prediction.condition_model train --source db   # needs DATABASE_URL
    python -m prediction.condition_model train --events events.csv --segments segments.csv

The model is used by the scorer automatically when models/m2/condition-current.joblib
exists and passed its quality gate; otherwise the prior in segment_risk.py is used.
"""
from __future__ import annotations

import argparse
import json
import time
from dataclasses import dataclass, field

import joblib
import numpy as np
import pandas as pd

from .config import MODEL_DIR, SEGMENT
from .evaluation import classification_metrics, best_f1_threshold

MIN_POSITIVES = 50          # quality gate: below this the prior is kept
MIN_PR_AUC_GAIN = 0.02      # the learned model must beat the prior on the test period
ROAD_CLASSES = ["motorway", "national", "regional", "local", "urban"]

# Demo rows (scripts/seed_demo.py) carry payload.demo = true. They feed the live scoring, so the demo
# shows real M2 output, but never a training set: excluded in SQL here and again in build_panel.
TRAINING_EVENTS_SQL = """SELECT segment_id::text segment_id, severity, confidence, observed_at, status,
                                status IN ('validated','confirmed','in_progress','scheduled') validated
                         FROM road_events
                         WHERE segment_id IS NOT NULL AND NOT coalesce((payload->>'demo')::boolean, false)"""


def drop_demo(events: pd.DataFrame) -> pd.DataFrame:
    """Remove demo events (column `demo` truthy) from a training input; no-op without the column."""
    if "demo" not in events.columns:
        return events
    demo = events["demo"].map(lambda v: str(v).strip().lower() in {"true", "1", "yes"})
    return events[~demo].drop(columns="demo")


def _features(segments: pd.DataFrame, ev: pd.DataFrame, r: pd.Timestamp, rain30: float) -> pd.DataFrame:
    past = ev[ev["observed_at"] <= r]
    age = (r - past["observed_at"]).dt.days
    past = past.assign(age=age, decay=0.5 ** (age / SEGMENT.event_half_life_days))
    g = past.groupby("segment_id")
    f = pd.DataFrame(index=segments["segment_id"])
    for w in (30, 90, 180):
        f[f"n_events_{w}"] = past[past["age"] <= w].groupby("segment_id").size()
    f["max_sev_decayed"] = (past["severity"] * past["decay"]).groupby(past["segment_id"]).max()
    f["max_sev_90"] = past[past["age"] <= 90].groupby("segment_id")["severity"].max()
    f["mean_conf_90"] = past[past["age"] <= 90].groupby("segment_id")["confidence"].mean()
    f["n_validated_180"] = past[(past["age"] <= 180) & past["validated"]].groupby("segment_id").size()
    f["days_since_last"] = g["age"].min()
    f["n_repaired_180"] = past[(past["age"] <= 180) & past["status"].isin(["repaired", "resolved"])].groupby("segment_id").size()
    f = f.reindex(segments["segment_id"]).fillna({"days_since_last": 999}).fillna(0)
    f["rain30_mm"] = rain30
    f["length_km"] = segments.set_index("segment_id")["length_m"].reindex(f.index).fillna(0).to_numpy() / 1000
    for c in ROAD_CLASSES:
        f[f"class_{c}"] = (segments.set_index("segment_id")["road_class"].reindex(f.index) == c).astype(int).to_numpy()
    return f


def build_panel(segments: pd.DataFrame, events: pd.DataFrame, rain: pd.Series | None = None,
                horizon_days: int | None = None, step_days: int = 14) -> pd.DataFrame:
    H = horizon_days or SEGMENT.horizon_days
    ev = drop_demo(events).copy()
    ev["observed_at"] = pd.to_datetime(ev["observed_at"], utc=True).dt.tz_localize(None)
    ev["validated"] = ev.get("validated", False)
    ev["validated"] = ev["validated"].fillna(False).astype(bool)
    ev["status"] = ev.get("status", "observed")
    start = ev["observed_at"].min().normalize() + pd.Timedelta(days=90)
    end = ev["observed_at"].max().normalize() - pd.Timedelta(days=H)
    rows = []
    for r in pd.date_range(start, end, freq=f"{step_days}D"):
        rain30 = float(rain.loc[:r].tail(30).sum()) if rain is not None else 0.0
        f = _features(segments, ev, r, rain30)
        fut = ev[(ev["observed_at"] > r) & (ev["observed_at"] <= r + pd.Timedelta(days=H))
                 & (ev["severity"] >= SEGMENT.severe_defect_threshold)]
        f["label"] = f.index.isin(fut["segment_id"]).astype(int)
        f["ref_date"] = r
        rows.append(f.reset_index().rename(columns={"index": "segment_id"}))
    return pd.concat(rows, ignore_index=True) if rows else pd.DataFrame()


@dataclass
class ConditionModel:
    version: str
    features: list[str]
    model: object
    threshold: float
    metrics: dict = field(default_factory=dict)

    def predict(self, segments: pd.DataFrame, events: pd.DataFrame, as_of: pd.Timestamp, rain30: float) -> np.ndarray:
        ev = events.copy()
        ev["observed_at"] = pd.to_datetime(ev["observed_at"], utc=True).dt.tz_localize(None)
        ev["validated"] = ev.get("validated", False)
        ev["validated"] = ev["validated"].fillna(False).astype(bool)
        ev["status"] = ev.get("status", "observed")
        f = _features(segments, ev, as_of, rain30)
        return self.model.predict_proba(f[self.features])[:, 1]


def _prior_score(panel: pd.DataFrame) -> np.ndarray:
    """The rule-based prior evaluated on the same panel (for the quality gate)."""
    from .segment_risk import _p_severe
    p = _p_severe(panel["max_sev_decayed"].to_numpy(), SEGMENT.horizon_days, panel["rain30_mm"].to_numpy())
    return np.where(panel["n_events_180"].to_numpy() > 0, p, 0.0)


def train(panel: pd.DataFrame, test_fraction: float = 0.3) -> tuple[ConditionModel | None, dict]:
    from .models import logreg, xgboost_clf
    if panel.empty or panel["label"].sum() < MIN_POSITIVES:
        return None, {"status": "insufficient_labels", "positives": int(panel["label"].sum()) if len(panel) else 0,
                      "required": MIN_POSITIVES}
    dates = np.sort(panel["ref_date"].unique())
    cut = dates[int(len(dates) * (1 - test_fraction))]
    tr, te = panel[panel["ref_date"] < cut], panel[panel["ref_date"] >= cut]
    feats = [c for c in panel.columns if c not in ("segment_id", "label", "ref_date")]
    cands = {"logreg": logreg().fit(tr[feats], tr["label"])}
    try:
        n_val = max(1, int(len(tr) * 0.2))
        x = xgboost_clf(max_depth=3, min_child_weight=5)
        x.fit(tr[feats].iloc[:-n_val], tr["label"].iloc[:-n_val],
              eval_set=[(tr[feats].iloc[-n_val:], tr["label"].iloc[-n_val:])], verbose=False)
        cands["xgboost"] = x
    except Exception:
        pass
    res = {}
    for k, m in cands.items():
        p = m.predict_proba(te[feats])[:, 1]
        res[k] = classification_metrics(te["label"], p, best_f1_threshold(te["label"], p))
    prior = classification_metrics(te["label"], _prior_score(te), 0.5)
    best = max(res, key=lambda k: res[k]["pr_auc"])
    report = {"status": "trained", "candidates": res, "prior": prior, "chosen": best,
              "positives": int(panel["label"].sum()), "test_from": str(pd.Timestamp(cut).date())}
    if res[best]["pr_auc"] - prior["pr_auc"] < MIN_PR_AUC_GAIN:
        report["status"] = "prior_kept"
        return None, report
    p_tr = cands[best].predict_proba(tr[feats])[:, 1]
    cm = ConditionModel(version=time.strftime("%Y.%m.%d-%H%M"), features=feats, model=cands[best],
                        threshold=best_f1_threshold(tr["label"], p_tr), metrics=res[best])
    return cm, report


def save(cm: ConditionModel) -> None:
    MODEL_DIR.mkdir(parents=True, exist_ok=True)
    joblib.dump(cm, MODEL_DIR / "condition-current.joblib", compress=3)


def load() -> ConditionModel | None:
    p = MODEL_DIR / "condition-current.joblib"
    return joblib.load(p) if p.exists() else None


def main(argv=None):
    ap = argparse.ArgumentParser(description="Train the Mode B condition model from M1 event history")
    ap.add_argument("command", choices=["train"])
    ap.add_argument("--source", choices=["db", "file"], default="db")
    ap.add_argument("--events", help="CSV/JSON with segment_id, severity, confidence, observed_at, status, validated")
    ap.add_argument("--segments", help="CSV with segment_id, road_class, length_m")
    args = ap.parse_args(argv)
    if args.source == "db":
        from .jobs.sources import DbSource
        src = DbSource()
        segs = src.segments()
        import sqlalchemy as sa
        ev = pd.read_sql(sa.text(TRAINING_EVENTS_SQL), src.engine)
        wx = src.weather()
        rain = wx.set_index("date")["prcp"].fillna(0) if "gov_code" not in wx.columns else None
    else:
        read = (lambda p: pd.read_json(p)) if str(args.events).endswith(".json") else pd.read_csv
        ev, segs, rain = read(args.events), pd.read_csv(args.segments), None
    panel = build_panel(segs, ev, rain)
    cm, report = train(panel)
    if cm:
        save(cm)
    print(json.dumps(report, indent=2, default=str))


if __name__ == "__main__":
    main()

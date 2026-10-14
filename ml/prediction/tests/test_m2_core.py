import json
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from prediction.calendar_tn import calendar_features
from prediction.config import GOV_CODES, RISK_LEVELS, gov_code
from prediction.contract import validate, validate_many
from prediction.features import build_inference_frame, build_training_panel, temporal_split
from prediction.io_accidents import road_class_from_place
from prediction.segment_risk import governorate_forecasts, score_segments

ROOT = Path(__file__).resolve().parents[3]


# ------------------------------------------------------------------ reference data
@pytest.mark.parametrize("label,code", [
    ("تونس", "TN-11"), ("تونس ", "TN-11"), ("بنعروس", "TN-13"), ("ولاية بن عروس", "TN-13"),
    ("اريانة", "TN-12"), ("ولاية أريانة", "TN-12"), ("سيدي بوزيد", "TN-43"), ("بنزرت", "TN-23"),
    ("Gouvernorat Bizerte", "TN-23"), ("Gouvernorat Kébili", "TN-73"), ("Gouvernorat La Manouba", "TN-14"),
    ("Béja", "TN-31"), ("gabes", "TN-81"), ("TN-61", "TN-61"),
])
def test_governorate_mapping(label, code):
    assert gov_code(label) == code


def test_all_governorates_unique():
    assert len(set(GOV_CODES)) == 24


@pytest.mark.parametrize("place,cls", [
    ("الطريق السيارة أ1", "motorway"), ("الوطنية1", "national"), ("وطنية 8", "national"),
    ("الطريق الجهوية 21", "regional"), ("محلية غير مرقمة", "local"), ("شارع بورقيبة", "urban"),
    ("مواطن عمران ", "urban"), ("طريق المرسى", "road_other"), ("", "unknown"),
])
def test_road_class_from_place(place, cls):
    assert road_class_from_place(place) == cls


def test_calendar_known_dates():
    cal = calendar_features(pd.Series(pd.to_datetime(["2026-03-20", "2026-02-25", "2026-03-21"])))
    assert cal["is_fixed_holiday"].tolist() == [1, 0, 0]
    assert cal["is_ramadan"].iloc[1] == 1


# ------------------------------------------------------------------ leakage
def test_features_do_not_see_target_day(accidents, weather, road_stats):
    """Changing the accidents/weather of day t must not change the features of day t."""
    t = pd.Timestamp("2021-06-15")
    base, fs = build_training_panel(accidents, weather, road_stats, "2021-06-10", "2021-06-20")
    acc2 = pd.concat([accidents, pd.DataFrame([{
        "accident_id": f"extra-{i}", "date": t, "gov_code": "TN-23", "killed": 1, "injured": 3,
        "road_class": "urban", "fatal": 1, "delegation": None, "place": "x", "hour": 1, "cause_group": "x"}
        for i in range(50)])], ignore_index=True)
    wx2 = weather.copy()
    wx2.loc[wx2["date"] == t, "prcp"] = 500.0
    mod, _ = build_training_panel(acc2, wx2, road_stats, "2021-06-10", "2021-06-20")
    key = (base["date"] == t) & (base["gov_code"] == "TN-23")
    pd.testing.assert_frame_equal(base.loc[key, fs.all].reset_index(drop=True),
                                  mod.loc[key, fs.all].reset_index(drop=True))
    # ...but the target of day t and the features of day t+1 do change
    assert mod.loc[key, "accident_count"].iloc[0] == base.loc[key, "accident_count"].iloc[0] + 50
    nxt = (base["date"] == t + pd.Timedelta(days=1)) & (base["gov_code"] == "TN-23")
    assert mod.loc[nxt, "hist_acc_lag1"].iloc[0] == base.loc[nxt, "hist_acc_lag1"].iloc[0] + 50
    assert mod.loc[nxt, "wx_prcp_lag1"].iloc[0] == 500.0


def test_temporal_split_is_ordered(accidents, weather, road_stats):
    panel, _ = build_training_panel(accidents, weather, road_stats, "2021-01-01", "2021-12-31")
    tr, va, te = temporal_split(panel, "2021-06-30", "2021-09-30")
    assert tr["date"].max() < va["date"].min() and va["date"].max() < te["date"].min()


def test_inference_beyond_data_reports_staleness(accidents, weather, road_stats):
    feats, fs = build_inference_frame(["TN-23"], pd.date_range("2022-01-10", periods=3), accidents, weather, road_stats)
    assert (feats["history_staleness_days"] > 0).all()
    assert feats[fs.all].notna().all().all()


# ------------------------------------------------------------------ segment scoring + contract
@pytest.fixture
def segments():
    return pd.DataFrame({"segment_id": ["a", "b", "c"], "segment_code": ["S-A", "S-B", "S-C"],
                         "gov_code": ["TN-23"] * 3, "road_class": ["motorway", "local", "urban"],
                         "length_m": [2000.0, 2000.0, 500.0]})


def _forecast(bundle, accidents, weather, road_stats):
    feats, _ = build_inference_frame(["TN-23"], pd.date_range("2022-01-01", periods=30), accidents, weather, road_stats)
    return governorate_forecasts(bundle, feats.reset_index(drop=True))


def test_scores_respect_contract(bundle, accidents, weather, road_stats, segments):
    fc = _forecast(bundle, accidents, weather, road_stats)
    recs = score_segments(bundle, segments, fc, road_stats, as_of=datetime(2021, 12, 31, tzinfo=timezone.utc))
    assert validate_many(recs) == 3
    for r in recs:
        assert 0 <= r["risk_score"] <= 1
        assert r["risk_level"] == RISK_LEVELS.level(r["risk_score"])
        assert len(r["top_factors"]) <= 5
    by = {r["segment_id"]: r for r in recs}
    # same length, higher-risk class -> higher accident component
    assert by["a"]["components"]["accident"] > by["b"]["components"]["accident"]


def test_m1_events_raise_risk_and_closed_events_are_ignored(bundle, accidents, weather, road_stats, segments):
    fc = _forecast(bundle, accidents, weather, road_stats)
    as_of = datetime(2021, 12, 31, tzinfo=timezone.utc)
    ev = pd.DataFrame({"segment_id": ["b", "c"], "event_type": ["pothole", "pothole"], "severity": [0.85, 0.85],
                       "confidence": [0.9, 0.9], "observed_at": ["2021-12-28T10:00:00Z"] * 2,
                       "status": ["validated", "repaired"], "validated": [True, True]})
    base = {r["segment_id"]: r for r in score_segments(bundle, segments, fc, road_stats, as_of=as_of)}
    withev = {r["segment_id"]: r for r in score_segments(bundle, segments, fc, road_stats, events=ev, as_of=as_of)}
    assert withev["b"]["risk_score"] > base["b"]["risk_score"] + 0.3
    assert withev["b"]["predicted_condition"] == "critical"
    assert withev["c"]["risk_score"] == pytest.approx(base["c"]["risk_score"])  # repaired -> ignored
    assert withev["a"]["risk_score"] == pytest.approx(base["a"]["risk_score"])


def test_contract_rejects_bad_records():
    with pytest.raises(ValueError):
        validate({"segment_id": "x", "risk_score": 1.5, "risk_level": "low", "horizon_days": 30,
                  "computed_at": "2026-10-11T00:00:00+00:00", "model": {"name": "m", "version": "v"}})


def test_schema_and_migration_chain():
    schema = json.loads((ROOT / "data/schemas/risk_score.schema.json").read_text())
    assert schema["properties"]["segment_id"]["type"] == "string"
    mig = (ROOT / "backend/alembic/versions/0003_m2_risk_model.py").read_text()
    assert 'down_revision = "0002_bootstrap_accounts"' in mig


# ------------------------------------------------------------------ Mode B condition model
def test_condition_model_learns_from_event_history(bundle, accidents, weather, road_stats):
    from prediction.condition_model import build_panel, train
    rng = np.random.default_rng(3)
    n = 120
    segs = pd.DataFrame({"segment_id": [f"s{i}" for i in range(n)], "road_class": ["national"] * n,
                         "length_m": 1000.0, "gov_code": "TN-23"})
    rows = []
    for d in pd.date_range("2024-01-01", "2025-12-31", freq="7D"):
        for i in rng.choice(n, 6, replace=False):
            # 'fragile' segments (first third) degrade to severe defects
            sev = rng.uniform(0.6, 0.95) if i < n // 3 else rng.uniform(0.1, 0.5)
            rows.append({"segment_id": f"s{i}", "severity": sev, "confidence": 0.9,
                         "observed_at": d.isoformat() + "Z", "status": "observed", "validated": True})
    ev = pd.DataFrame(rows)
    panel = build_panel(segs, ev, horizon_days=30, step_days=14)
    assert {"label", "ref_date", "n_events_90"} <= set(panel.columns)
    assert panel["label"].sum() >= 50
    cm, report = train(panel)
    assert report["status"] in ("trained", "prior_kept")
    if cm is not None:
        fc = _forecast(bundle, accidents, weather, road_stats)
        recs = score_segments(bundle, segs.head(5), fc, road_stats, events=ev,
                              as_of=datetime(2026, 1, 1, tzinfo=timezone.utc), condition_model=cm)
        assert validate_many(recs) == 5

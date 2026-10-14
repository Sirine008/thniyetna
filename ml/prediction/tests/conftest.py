"""Small synthetic fixtures so the M2 tests run in CI without the raw data.

These fixtures only exercise code paths (shapes, leakage, contract). They are
never used to report model performance.
"""
import numpy as np
import pandas as pd
import pytest

from prediction.config import GOV_CODES
from prediction.io_osm import ROAD_CLASSES


@pytest.fixture(scope="session")
def accidents():
    rng = np.random.default_rng(0)
    days = pd.date_range("2019-01-01", "2021-12-31", freq="D")
    rows = []
    for g_i, g in enumerate(GOV_CODES):
        lam = 0.2 + 0.05 * g_i
        n = rng.poisson(lam, len(days))
        for d, k in zip(days, n):
            for _ in range(k):
                rows.append({"accident_id": f"{g}-{d:%Y%m%d}-{len(rows)}", "date": d, "gov_code": g,
                             "killed": int(rng.random() < 0.1), "injured": 1,
                             "road_class": rng.choice(ROAD_CLASSES), "delegation": None, "place": "x",
                             "hour": 12, "cause_group": "other"})
    df = pd.DataFrame(rows)
    df["fatal"] = (df["killed"] > 0).astype(int)
    return df


@pytest.fixture(scope="session")
def weather():
    rng = np.random.default_rng(1)
    days = pd.date_range("2020-06-01", "2021-12-31", freq="D")
    return pd.DataFrame({"date": days, "tavg": 20 + 5 * np.sin(np.arange(len(days)) / 58), "tmin": 15.0,
                         "tmax": 25.0, "prcp": rng.gamma(0.3, 4, len(days)), "wspd": 15.0, "pres": 1013.0,
                         "prcp_missing": 0})


@pytest.fixture(scope="session")
def road_stats():
    rows = []
    for i, g in enumerate(GOV_CODES):
        km = {f"road_km_{c}": 100.0 * (j + 1) + i for j, c in enumerate(ROAD_CLASSES)}
        total = sum(km.values())
        row = {"gov_code": g, **km, "road_km_total": total, "area_km2": 1000.0 + i,
               "road_density_km_per_km2": total / (1000.0 + i), "road_share_lit": 0.01,
               "road_share_unpaved_tagged": 0.03}
        row.update({f"road_share_{c}": km[f"road_km_{c}"] / total for c in ROAD_CLASSES})
        rows.append(row)
    return pd.DataFrame(rows)


@pytest.fixture(scope="session")
def bundle(accidents, weather, road_stats):
    from prediction.features import build_training_panel
    from prediction.models import RollingMeanBaseline, logreg
    from prediction.registry import ModelBundle, PlattCalibrator

    panel, fs = build_training_panel(accidents, weather, road_stats, start="2021-01-01", end="2021-12-31")
    X = panel[fs.all]
    clf = logreg().fit(X, panel["accident_flag"])
    cal = PlattCalibrator().fit(clf.predict_proba(X)[:, 1], panel["accident_flag"])
    cnt = RollingMeanBaseline().fit(X, panel["accident_count"])
    return ModelBundle(version="test", features=fs.all, feature_groups=fs.groups(), classifier=clf,
                       classifier_name="logreg", calibrator=cal, threshold=0.4, count_model=cnt,
                       count_model_name="naive_rolling_mean",
                       road_class_weights={"motorway": 4.0, "national": 2.6, "regional": 2.3,
                                           "local": 0.33, "urban": 1.1})

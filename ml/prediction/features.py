"""Governorate x day feature panel (Mode A) — leakage-safe by construction.

Every feature for target day t is computed from a *reference day* r <= t-1:
  * training:  r = t - 1
  * inference: r = min(t - 1, last day for which the source is actually observed)
so the model never sees the target day's accidents or weather. Calendar
features describe day t itself (they are known in advance).
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from .calendar_tn import calendar_features
from .config import FEATURES, GOV_CODES
from .io_accidents import daily_counts

TARGETS = ["accident_flag", "accident_count", "fatal_flag"]


# --------------------------------------------------------------------------
# Building blocks indexed by reference day
# --------------------------------------------------------------------------
def history_table(acc: pd.DataFrame, end: pd.Timestamp, observed_until: pd.Timestamp | None = None) -> pd.DataFrame:
    """Rolling accident history per governorate, value at day r includes day r.

    Days after `observed_until` are unknown (not zero) and are left out.
    """
    observed_until = observed_until or acc["date"].max()
    start = acc["date"].min()
    days = pd.date_range(start, min(end, observed_until), freq="D")
    daily = daily_counts(acc)
    idx = pd.MultiIndex.from_product([GOV_CODES, days], names=["gov_code", "date"])
    d = daily.set_index(["gov_code", "date"]).reindex(idx, fill_value=0)
    out = pd.DataFrame(index=idx)
    g_acc = d.groupby(level="gov_code")["accident_count"]
    g_fat = d.groupby(level="gov_code")["fatal_count"]
    out["hist_acc_lag1"] = d["accident_count"]
    for w in FEATURES.history_windows:
        out[f"hist_acc_sum_{w}"] = g_acc.transform(lambda s, w=w: s.rolling(w, min_periods=1).sum())
    for w in (30, 365):
        out[f"hist_fatal_sum_{w}"] = g_fat.transform(lambda s, w=w: s.rolling(w, min_periods=1).sum())
    out["hist_acc_trend_7_90"] = (out["hist_acc_sum_7"] / 7) / (out["hist_acc_sum_90"] / 90 + 1e-3)
    out["hist_fatal_ratio_365"] = out["hist_fatal_sum_365"] / (out["hist_acc_sum_365"] + 1)

    # days since last accident (capped at 365)
    def _since(s: pd.Series) -> pd.Series:
        pos = np.arange(len(s))
        last = np.where(s.to_numpy() > 0, pos, -10**9)
        last = np.maximum.accumulate(last)
        return pd.Series(np.minimum(pos - last, 365), index=s.index)
    out["hist_days_since_acc"] = g_acc.transform(_since)

    nat = d.groupby(level="date")["accident_count"].sum()
    nat7 = nat.rolling(7, min_periods=1).sum()
    nat30 = nat.rolling(30, min_periods=1).sum()
    out["nat_acc_sum_7"] = nat7.reindex(out.index.get_level_values("date")).to_numpy()
    out["nat_acc_sum_30"] = nat30.reindex(out.index.get_level_values("date")).to_numpy()
    # Mask the warm-up year: windows not yet full would look like "low history".
    warm = out.index.get_level_values("date") < start + pd.Timedelta(days=364)
    out.loc[warm, :] = np.nan
    return out


def weather_table(weather: pd.DataFrame) -> pd.DataFrame:
    """Rolling weather features at reference day r (includes r).

    Index: date (reference station) or (gov_code, date) (per-governorate weather).
    """
    if "gov_code" in weather.columns:
        parts = {g: _weather_one(d.drop(columns="gov_code")) for g, d in weather.groupby("gov_code")}
        out = pd.concat(parts, names=["gov_code", "date"])
        return out
    return _weather_one(weather)


def _weather_one(weather: pd.DataFrame) -> pd.DataFrame:
    w = weather.set_index("date").sort_index()
    p = w["prcp"].fillna(0.0)
    out = pd.DataFrame(index=w.index)
    out["wx_prcp_lag1"] = w["prcp"]
    for k in FEATURES.weather_windows:
        if k == 1:
            continue
        out[f"wx_prcp_sum_{k}"] = p.rolling(k, min_periods=1).sum()
    out["wx_rain_days_7"] = (p >= 1).rolling(7, min_periods=1).sum()
    out["wx_rain_days_30"] = (p >= 1).rolling(30, min_periods=1).sum()
    prior = p.shift(1).rolling(FEATURES.dry_spell_days, min_periods=1).sum()
    out["wx_first_rain_after_dry"] = ((p >= FEATURES.first_rain_mm) & (prior < FEATURES.first_rain_mm)).astype(int)
    out["wx_tavg_lag1"] = w["tavg"]
    out["wx_tmax_lag1"] = w["tmax"]
    out["wx_tmin_lag1"] = w["tmin"]
    out["wx_tavg_mean_7"] = w["tavg"].rolling(7, min_periods=1).mean()
    out["wx_tavg_mean_30"] = w["tavg"].rolling(30, min_periods=1).mean()
    out["wx_tavg_anom_30"] = w["tavg"] - out["wx_tavg_mean_30"]
    out["wx_wspd_lag1"] = w["wspd"]
    out["wx_wspd_max_7"] = w["wspd"].rolling(7, min_periods=1).max()
    out["wx_pres_lag1"] = w["pres"]
    out["wx_pres_change_3"] = w["pres"] - w["pres"].shift(3)
    out.index.name = "date"
    return out


ROAD_FEATURES = [
    "road_km_total", "road_density_km_per_km2", "road_share_motorway", "road_share_national",
    "road_share_regional", "road_share_local", "road_share_urban", "road_share_lit",
    "road_share_unpaved_tagged",
]


@dataclass
class FeatureSet:
    calendar: list[str]
    weather: list[str]
    history: list[str]
    road: list[str]

    @property
    def all(self) -> list[str]:
        return self.calendar + self.weather + self.history + self.road

    def groups(self) -> dict[str, list[str]]:
        return {"calendar": self.calendar, "weather": self.weather, "history": self.history, "road": self.road}


def _assemble(rows: pd.DataFrame, hist: pd.DataFrame, wx: pd.DataFrame, road_stats: pd.DataFrame) -> tuple[pd.DataFrame, FeatureSet]:
    """rows: gov_code, date, hist_ref, wx_ref -> features joined on reference days."""
    h = hist.reset_index().rename(columns={"date": "hist_ref"})
    w = wx.reset_index().rename(columns={"date": "wx_ref"})
    wkeys = ["gov_code", "wx_ref"] if "gov_code" in w.columns else ["wx_ref"]
    df = rows.merge(h, on=["gov_code", "hist_ref"], how="left").merge(w, on=wkeys, how="left")
    cal = calendar_features(df["date"])
    df = pd.concat([df, cal], axis=1)
    rs = road_stats.set_index("gov_code")[ROAD_FEATURES].reset_index()
    df = df.merge(rs, on="gov_code", how="left")
    fs = FeatureSet(
        calendar=list(cal.columns),
        weather=[c for c in wx.columns],
        history=[c for c in hist.columns],
        road=ROAD_FEATURES,
    )
    return df, fs


def build_training_panel(acc: pd.DataFrame, weather: pd.DataFrame, road_stats: pd.DataFrame,
                         start: str | pd.Timestamp, end: str | pd.Timestamp | None = None) -> tuple[pd.DataFrame, FeatureSet]:
    """Full governorate x day panel with targets, restricted to [start, end]."""
    start = pd.Timestamp(start)
    last_acc = acc["date"].max()
    last_wx = weather["date"].max()
    end = pd.Timestamp(end) if end is not None else min(last_acc, last_wx + pd.Timedelta(days=1))
    days = pd.date_range(start, end, freq="D")
    rows = pd.MultiIndex.from_product([GOV_CODES, days], names=["gov_code", "date"]).to_frame(index=False)
    rows["hist_ref"] = rows["date"] - pd.Timedelta(days=1)
    rows["wx_ref"] = rows["date"] - pd.Timedelta(days=1)

    hist = history_table(acc, end=end)
    wx = weather_table(weather)
    df, fs = _assemble(rows, hist, wx, road_stats)

    daily = daily_counts(acc)
    df = df.merge(daily[["gov_code", "date", "accident_count", "fatal_count"]], on=["gov_code", "date"], how="left")
    df["accident_count"] = df["accident_count"].fillna(0).astype(int)
    df["accident_flag"] = (df["accident_count"] > 0).astype(int)
    df["fatal_flag"] = (df["fatal_count"].fillna(0) > 0).astype(int)
    df = df.drop(columns=["fatal_count"])
    # Rows whose weather reference is outside the station record are dropped
    df = df.dropna(subset=["wx_tavg_lag1"]).reset_index(drop=True)
    df.attrs["panel_end"] = str(end.date())
    return df, fs


def build_inference_frame(gov_codes: list[str], dates: list[pd.Timestamp] | pd.DatetimeIndex,
                          acc: pd.DataFrame, weather: pd.DataFrame, road_stats: pd.DataFrame,
                          acc_observed_until: pd.Timestamp | None = None) -> tuple[pd.DataFrame, FeatureSet]:
    """Feature rows for arbitrary (governorate, date) pairs, including future dates."""
    acc_until = pd.Timestamp(acc_observed_until) if acc_observed_until is not None else acc["date"].max()
    wx_until = weather["date"].max()
    dates = pd.DatetimeIndex(pd.to_datetime(list(dates))).normalize()
    rows = pd.MultiIndex.from_product([gov_codes, dates], names=["gov_code", "date"]).to_frame(index=False)
    rows["hist_ref"] = (rows["date"] - pd.Timedelta(days=1)).clip(upper=acc_until)
    if "gov_code" in weather.columns:
        last = weather.groupby("gov_code")["date"].max()
        rows["wx_ref"] = (rows["date"] - pd.Timedelta(days=1)).clip(upper=rows["gov_code"].map(last))
    else:
        rows["wx_ref"] = (rows["date"] - pd.Timedelta(days=1)).clip(upper=wx_until)
    rows["history_staleness_days"] = (rows["date"] - pd.Timedelta(days=1) - rows["hist_ref"]).dt.days
    rows["weather_staleness_days"] = (rows["date"] - pd.Timedelta(days=1) - rows["wx_ref"]).dt.days
    hist = history_table(acc, end=acc_until, observed_until=acc_until)
    wx = weather_table(weather)
    return _assemble(rows, hist, wx, road_stats)


def temporal_split(df: pd.DataFrame, train_end: str, val_end: str, test_end: str | None = None):
    train = df[df["date"] <= train_end]
    val = df[(df["date"] > train_end) & (df["date"] <= val_end)]
    test = df[df["date"] > val_end]
    if test_end:
        test = test[test["date"] <= test_end]
    return train.reset_index(drop=True), val.reset_index(drop=True), test.reset_index(drop=True)

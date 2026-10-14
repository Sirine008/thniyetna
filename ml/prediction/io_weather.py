"""Daily weather loader.

Two layouts are accepted:
  * one reference station (columns date, tavg, ...) -> same weather for every governorate
  * long format with a `gov_code` column -> one series per governorate
    (see fetch_weather.py, which builds it from Open-Meteo for each governorate centroid)


Training uses a Meteostat daily export (date, tavg, tmin, tmax, prcp, wspd, pres,
...) from one Tunisian reference station. The same columns are produced at
inference time from the `weather_observations` table (see jobs/db.py), so the
model never sees a different schema in production.
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd

from .config import RAW_DIR, WEATHER_FILE

WEATHER_COLUMNS = ["tavg", "tmin", "tmax", "prcp", "wspd", "pres"]


def load_weather(path: str | Path | None = None) -> pd.DataFrame:
    path = Path(path) if path else RAW_DIR / WEATHER_FILE
    if path.suffix.lower() in (".xlsx", ".xls"):
        raw = pd.read_excel(path)
    else:
        raw = pd.read_csv(path)
    raw.columns = [str(c).strip().lower() for c in raw.columns]
    if "date" not in raw.columns:
        raise ValueError("Weather file needs a 'date' column")
    df = pd.DataFrame({"date": pd.to_datetime(raw["date"]).dt.normalize()})
    for col in WEATHER_COLUMNS:
        df[col] = pd.to_numeric(raw[col], errors="coerce") if col in raw.columns else float("nan")
    if "gov_code" in raw.columns:  # long format: one series per governorate
        df["gov_code"] = raw["gov_code"].astype(str)
        parts = [_regularise(d.drop(columns="gov_code")).assign(gov_code=g) for g, d in df.groupby("gov_code")]
        out = pd.concat(parts, ignore_index=True)
        out.attrs["source_file"] = str(path)
        return out
    out = _regularise(df)
    out.attrs["source_file"] = str(path)
    return out


def _regularise(df: pd.DataFrame) -> pd.DataFrame:
    df = df.drop_duplicates("date").sort_values("date").set_index("date")
    # Regular daily index; short gaps (<= 3 days) are interpolated for temperature,
    # pressure and wind. Missing precipitation is NOT invented: it stays NaN and
    # the feature builder treats it as "unknown" (0 for sums, flagged separately).
    full = pd.date_range(df.index.min(), df.index.max(), freq="D")
    df = df.reindex(full)
    df.index.name = "date"
    df["prcp_missing"] = df["prcp"].isna().astype(int)
    for col in ("tavg", "tmin", "tmax", "wspd", "pres"):
        df[col] = df[col].interpolate(limit=3, limit_direction="both")
    return df.reset_index()

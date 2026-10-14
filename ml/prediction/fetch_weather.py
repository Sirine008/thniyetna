"""Build a per-governorate daily weather file from the Open-Meteo archive (ERA5-based).

Why: with a single reference station the weather features add nothing in the
ablation (one station cannot describe 24 governorates). This produces the long
format accepted by io_weather.load_weather (date, gov_code, tavg, tmin, tmax,
prcp, wspd, pres), one point per governorate (representative point of the OSM
polygon).

    python -m prediction.fetch_weather --start 2022-04-01 --end 2026-10-10 \
        --out ../data/external/m2/weather_governorates.csv
    M2_WEATHER_FILE=weather_governorates.csv python -m prediction.train train

Requires internet access to archive-api.open-meteo.com (free, no key).
"""
from __future__ import annotations

import argparse
import json
import time
import urllib.parse
import urllib.request
from pathlib import Path

import pandas as pd

from .config import PROCESSED_DIR

ARCHIVE = "https://archive-api.open-meteo.com/v1/archive"


def governorate_points(path: Path | None = None) -> pd.DataFrame:
    import shapely
    g = pd.read_parquet(path or PROCESSED_DIR / "governorates.parquet")
    pts = [shapely.from_wkt(w).representative_point() for w in g["wkt"]]
    return pd.DataFrame({"gov_code": g["gov_code"], "lat": [p.y for p in pts], "lon": [p.x for p in pts]})


def fetch_one(lat: float, lon: float, start: str, end: str, retries: int = 4) -> pd.DataFrame:
    params = urllib.parse.urlencode({
        "latitude": round(lat, 4), "longitude": round(lon, 4), "start_date": start, "end_date": end,
        "daily": "temperature_2m_mean,temperature_2m_min,temperature_2m_max,precipitation_sum",
        "hourly": "wind_speed_10m,pressure_msl", "timezone": "Africa/Tunis",
    })
    for attempt in range(retries):
        try:
            with urllib.request.urlopen(f"{ARCHIVE}?{params}", timeout=60) as r:
                body = json.load(r)
            break
        except Exception:
            if attempt == retries - 1:
                raise
            time.sleep(5 * (attempt + 1))
    d = pd.DataFrame(body["daily"]).rename(columns={
        "time": "date", "temperature_2m_mean": "tavg", "temperature_2m_min": "tmin",
        "temperature_2m_max": "tmax", "precipitation_sum": "prcp"})
    h = pd.DataFrame(body["hourly"])
    h["date"] = pd.to_datetime(h["time"]).dt.strftime("%Y-%m-%d")
    hd = h.groupby("date").agg(wspd=("wind_speed_10m", "mean"), pres=("pressure_msl", "mean")).reset_index()
    return d.merge(hd, on="date", how="left")


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--start", default="2021-01-01")
    ap.add_argument("--end", default=pd.Timestamp.today().strftime("%Y-%m-%d"))
    ap.add_argument("--out", required=True)
    args = ap.parse_args(argv)
    frames = []
    for _, r in governorate_points().iterrows():
        print(f"[open-meteo] {r.gov_code} ({r.lat:.3f}, {r.lon:.3f})")
        frames.append(fetch_one(r.lat, r.lon, args.start, args.end).assign(gov_code=r.gov_code))
        time.sleep(1.0)  # be polite with the free API
    out = pd.concat(frames, ignore_index=True)
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    out.to_csv(args.out, index=False)
    print(f"[open-meteo] {len(out):,} rows -> {args.out}")


if __name__ == "__main__":
    main()

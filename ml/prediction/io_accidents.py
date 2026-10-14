"""Load and normalise the Tunisian road-accident open-data export.

The export (JSON, Arabic keys, one record per accident, 2015 -> 2026) has no GPS
coordinates. Location is known at governorate level for every record and at
delegation level from 2021 onwards. The free-text location is mapped to a coarse
road class so the segment layer can weight road types (see segment_risk.py).
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import pandas as pd

from .config import RAW_DIR, ACCIDENTS_FILE, gov_code

COLUMNS = {
    "رقم الحادث": "accident_id",
    "تاريخ_كامل": "date_raw",
    "الولاية": "governorate_raw",
    "المعتمدية": "delegation",
    "مكان الحادث": "place",
    "كلم": "km_marker",
    "نوع الحادث": "collision_type",
    "الاسباب": "cause",
    "الساعة": "hour",
    "قتلى": "killed",
    "جرحى": "injured",
    "مرجع نظر": "authority",
}

# Order matters: the first matching pattern wins.
ROAD_CLASS_PATTERNS: list[tuple[str, str]] = [
    ("motorway", r"سيار|السريعة|محول"),
    ("national", r"وطني|^ط\s*و|^ر\s*و|\bرو\s*\d"),
    ("regional", r"جهوي|^ط\s*ج|^ر\s*ج"),
    ("local", r"محلي|غير مرقمة"),
    ("urban", r"شارع|نهج|مواطن عمران|زنقة|ساحة|^حي\s|العمران|المدينة"),
    ("road_other", r"^طريق|مفترق"),
]

AUTHORITY = {"شرطة": "police", "حرس": "garde_nationale"}

CAUSE_GROUPS = {
    "inattention": ["السهو", "اهمال", "تعب"],
    "speed": ["السرعة"],
    "pedestrian": ["شق الطريق"],
    "priority": ["الاولوية", "علامة قف", "الضوء الاحمر", "المداهمة"],
    "manoeuvre": ["اليمين", "تغيير اتجاه", "الوراء", "المجاوزة", "اتجاه محجر", "فتح باب", "صعود"],
    "alcohol": ["سكر"],
    "vehicle_or_road": ["عجلة", "انزلاق", "خلل", "انارة"],
}


def road_class_from_place(place: str | None) -> str:
    p = (place or "").strip()
    for cls, pattern in ROAD_CLASS_PATTERNS:
        if re.search(pattern, p):
            return cls
    return "unknown"


def cause_group(cause: str | None) -> str:
    c = (cause or "").strip()
    for grp, keys in CAUSE_GROUPS.items():
        if any(k in c for k in keys):
            return grp
    return "other"


def load_accidents(path: str | Path | None = None) -> pd.DataFrame:
    """Return one clean row per accident.

    Columns: accident_id, date, hour, gov_code, delegation, place, road_class,
    km_marker, collision_type, cause, cause_group, killed, injured, fatal, authority.
    """
    path = Path(path) if path else RAW_DIR / ACCIDENTS_FILE
    with open(path, encoding="utf-8") as fh:
        payload = json.load(fh)
    records = payload["data"] if isinstance(payload, dict) and "data" in payload else payload
    raw = pd.DataFrame.from_records(records)
    missing = [k for k in COLUMNS if k not in raw.columns]
    if missing:
        raise ValueError(f"Accident export is missing expected columns: {missing}")
    df = raw[list(COLUMNS)].rename(columns=COLUMNS)

    df["date"] = pd.to_datetime(df["date_raw"], format="%d/%m/%Y %H:%M:%S", errors="coerce").dt.normalize()
    df["gov_code"] = df["governorate_raw"].map(gov_code)
    for col in ("hour", "killed", "injured", "km_marker"):
        df[col] = pd.to_numeric(df[col], errors="coerce")
    df["killed"] = df["killed"].fillna(0).astype(int)
    df["injured"] = df["injured"].fillna(0).astype(int)
    df["fatal"] = (df["killed"] > 0).astype(int)
    df["km_marker"] = df["km_marker"].where(df["km_marker"] >= 0)  # -1 means "not given"
    df["delegation"] = df["delegation"].astype("string").str.strip().replace("", pd.NA)
    df["place"] = df["place"].astype("string").str.strip()
    df["road_class"] = df["place"].map(road_class_from_place)
    df["cause"] = df["cause"].astype("string").str.strip()
    df["cause_group"] = df["cause"].map(cause_group)
    df["authority"] = df["authority"].map(AUTHORITY).fillna("unknown")

    bad_date = df["date"].isna().sum()
    bad_gov = df["gov_code"].isna().sum()
    df = df.dropna(subset=["date", "gov_code"]).drop(columns=["date_raw", "governorate_raw"])
    df = df.drop_duplicates(subset="accident_id").sort_values(["date", "accident_id"]).reset_index(drop=True)
    df.attrs["dropped_bad_date"] = int(bad_date)
    df.attrs["dropped_bad_governorate"] = int(bad_gov)
    df.attrs["source_file"] = str(path)
    return df


def daily_counts(acc: pd.DataFrame) -> pd.DataFrame:
    """Aggregate to governorate x day (only days with >= 1 accident appear)."""
    g = acc.groupby(["gov_code", "date"])
    out = g.agg(
        accident_count=("accident_id", "size"),
        fatal_count=("fatal", "sum"),
        killed=("killed", "sum"),
        injured=("injured", "sum"),
    ).reset_index()
    return out

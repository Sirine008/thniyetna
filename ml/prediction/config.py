"""M2 configuration: paths, governorate reference table, splits and thresholds.

Every value can be overridden through environment variables so the same code
runs on a laptop, in CI and inside the m2-worker container.
"""
from __future__ import annotations

import os
import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]


def _path(env: str, default: Path) -> Path:
    return Path(os.getenv(env, str(default))).expanduser().resolve()


# Raw data stays outside Git (see data/external/m2/README.md).
RAW_DIR = _path("M2_RAW_DIR", REPO_ROOT / "data" / "external" / "m2")
PROCESSED_DIR = _path("M2_PROCESSED_DIR", REPO_ROOT / "data" / "processed" / "m2")
MODEL_DIR = _path("M2_MODEL_DIR", REPO_ROOT / "models" / "m2")
REPORT_DIR = _path("M2_REPORT_DIR", REPO_ROOT / "reports" / "m2")

ACCIDENTS_FILE = os.getenv("M2_ACCIDENTS_FILE", "accidents_tn.json")
WEATHER_FILE = os.getenv("M2_WEATHER_FILE", "weather_reference.xlsx")
OSM_FILE = os.getenv("M2_OSM_FILE", "tunisia-latest.osm.pbf")

MLFLOW_TRACKING_URI = os.getenv("MLFLOW_TRACKING_URI", "")  # empty -> local ./mlruns
MLFLOW_EXPERIMENT = os.getenv("M2_MLFLOW_EXPERIMENT", "m2-risk-prediction")

RANDOM_STATE = int(os.getenv("M2_SEED", "42"))

# --------------------------------------------------------------------------
# Governorates: ISO 3166-2:TN codes, French name, normalised Arabic key.
# --------------------------------------------------------------------------
GOVERNORATES: list[tuple[str, str, str]] = [
    ("TN-11", "Tunis", "تونس"),
    ("TN-12", "Ariana", "اريانة"),
    ("TN-13", "Ben Arous", "بنعروس"),
    ("TN-14", "Manouba", "منوبة"),
    ("TN-21", "Nabeul", "نابل"),
    ("TN-22", "Zaghouan", "زغوان"),
    ("TN-23", "Bizerte", "بنزرت"),
    ("TN-31", "Béja", "باجة"),
    ("TN-32", "Jendouba", "جندوبة"),
    ("TN-33", "Le Kef", "الكاف"),
    ("TN-34", "Siliana", "سليانة"),
    ("TN-41", "Kairouan", "القيروان"),
    ("TN-42", "Kasserine", "القصرين"),
    ("TN-43", "Sidi Bouzid", "سيديبوزيد"),
    ("TN-51", "Sousse", "سوسة"),
    ("TN-52", "Monastir", "المنستير"),
    ("TN-53", "Mahdia", "المهدية"),
    ("TN-61", "Sfax", "صفاقس"),
    ("TN-71", "Gafsa", "قفصة"),
    ("TN-72", "Tozeur", "توزر"),
    ("TN-73", "Kébili", "قبلي"),
    ("TN-81", "Gabès", "قابس"),
    ("TN-82", "Médenine", "مدنين"),
    ("TN-83", "Tataouine", "تطاوين"),
]
GOV_CODES = [g[0] for g in GOVERNORATES]
GOV_NAME_FR = {g[0]: g[1] for g in GOVERNORATES}

_AR_MAP = str.maketrans({"أ": "ا", "إ": "ا", "آ": "ا", "ة": "ة", "ى": "ي"})


def normalize_ar(text: str | None) -> str:
    """Normalise an Arabic/French governorate label to a comparison key."""
    if text is None:
        return ""
    t = unicodedata.normalize("NFKC", str(text)).strip()
    t = re.sub(r"^(ولاية|gouvernorat( de| d')?)\s*", "", t, flags=re.IGNORECASE)
    t = t.translate(_AR_MAP)
    t = re.sub(r"[\s\u200f\u200e\-']+", "", t)
    return t.lower()


_LOOKUP: dict[str, str] = {}
for _code, _fr, _ar in GOVERNORATES:
    _LOOKUP[normalize_ar(_ar)] = _code
    _LOOKUP[normalize_ar(_fr)] = _code
    _LOOKUP[normalize_ar(_code)] = _code
# French spelling variants seen in OSM / user input
for _alias, _code in {
    "lamanouba": "TN-14", "kef": "TN-33", "beja": "TN-31", "kebili": "TN-73",
    "gabes": "TN-81", "medenine": "TN-82", "benarous": "TN-13", "sidibouzid": "TN-43",
}.items():
    _LOOKUP[_alias] = _code


def gov_code(label: str | None) -> str | None:
    """Return the ISO code for any governorate label (Arabic, French or code)."""
    key = normalize_ar(label)
    if key in _LOOKUP:
        return _LOOKUP[key]
    stripped = unicodedata.normalize("NFKD", key).encode("ascii", "ignore").decode()
    return _LOOKUP.get(stripped)


# --------------------------------------------------------------------------
# Temporal protocol (no random split anywhere in M2).
# --------------------------------------------------------------------------
@dataclass(frozen=True)
class SplitConfig:
    panel_start: str = os.getenv("M2_PANEL_START", "2022-04-01")  # first day with weather
    train_end: str = os.getenv("M2_TRAIN_END", "2023-12-31")
    val_end: str = os.getenv("M2_VAL_END", "2024-12-31")
    test_end: str | None = os.getenv("M2_TEST_END") or None  # None -> last observed day


@dataclass(frozen=True)
class FeatureConfig:
    weather_windows: tuple[int, ...] = (1, 3, 7, 14, 30)
    history_windows: tuple[int, ...] = (7, 30, 90, 365)
    dry_spell_days: int = 14
    first_rain_mm: float = 1.0


@dataclass(frozen=True)
class RiskLevelConfig:
    """Bucketing agreed in data/schemas/risk_score.schema.json (versioned with the model)."""
    medium: float = 0.25
    high: float = 0.50
    critical: float = 0.75

    def level(self, score: float) -> str:
        if score >= self.critical:
            return "critical"
        if score >= self.high:
            return "high"
        if score >= self.medium:
            return "medium"
        return "low"


@dataclass(frozen=True)
class SegmentConfig:
    horizon_days: int = int(os.getenv("M2_HORIZON_DAYS", "30"))
    # Half-life (days) of an M1 road event's influence on the condition score.
    event_half_life_days: float = float(os.getenv("M2_EVENT_HALF_LIFE", "45"))
    # Severity on the 0..1 M1 scale that corresponds to "severity >= 4" on 1..5.
    severe_defect_threshold: float = 0.75
    # Weight of an unvalidated (citizen / model-only) event vs a validated one.
    unvalidated_weight: float = 0.6
    complaint_radius_m: float = 250.0
    complaint_hazard: float = 0.04


SPLITS = SplitConfig()
FEATURES = FeatureConfig()
RISK_LEVELS = RiskLevelConfig()
SEGMENT = SegmentConfig()

MODEL_NAME = "m2-risk"
CONTRACT_VERSION = "1.1.0"


def ensure_dirs() -> None:
    for d in (PROCESSED_DIR, MODEL_DIR, REPORT_DIR):
        d.mkdir(parents=True, exist_ok=True)


__all__ = [
    "REPO_ROOT", "RAW_DIR", "PROCESSED_DIR", "MODEL_DIR", "REPORT_DIR",
    "GOVERNORATES", "GOV_CODES", "GOV_NAME_FR", "gov_code", "normalize_ar",
    "SPLITS", "FEATURES", "RISK_LEVELS", "SEGMENT", "SplitConfig", "FeatureConfig",
    "MODEL_NAME", "CONTRACT_VERSION", "ensure_dirs",
]

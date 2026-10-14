"""Tunisian calendar: fixed public holidays, Ramadan and Eid periods.

Lunar dates are the officially announced Tunisian dates where known; they can
drift by +/- 1 day from astronomical predictions, which is negligible at the
daily-panel level. Extend RAMADAN_START / EID_ADHA when new years are needed.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

FIXED_HOLIDAYS = {  # (month, day)
    (1, 1), (1, 14), (3, 20), (4, 9), (5, 1), (7, 25), (8, 13), (10, 15), (12, 17),
}

RAMADAN_START = {
    2015: "2015-06-18", 2016: "2016-06-06", 2017: "2017-05-27", 2018: "2018-05-17",
    2019: "2019-05-06", 2020: "2020-04-24", 2021: "2021-04-13", 2022: "2022-04-02",
    2023: "2023-03-23", 2024: "2024-03-11", 2025: "2025-03-01", 2026: "2026-02-18",
    2027: "2027-02-08", 2028: "2028-01-28",
}
EID_ADHA = {
    2015: "2015-09-24", 2016: "2016-09-12", 2017: "2017-09-01", 2018: "2018-08-21",
    2019: "2019-08-11", 2020: "2020-07-31", 2021: "2021-07-20", 2022: "2022-07-09",
    2023: "2023-06-28", 2024: "2024-06-16", 2025: "2025-06-06", 2026: "2026-05-27",
    2027: "2027-05-16", 2028: "2028-05-05",
}


def _ramadan_days() -> set[pd.Timestamp]:
    out = set()
    for start in RAMADAN_START.values():
        out.update(pd.date_range(start, periods=29, freq="D"))
    return out


def _eid_days() -> set[pd.Timestamp]:
    out = set()
    for start in RAMADAN_START.values():
        out.update(pd.date_range(pd.Timestamp(start) + pd.Timedelta(days=29), periods=3, freq="D"))
    for d in EID_ADHA.values():
        out.update(pd.date_range(d, periods=3, freq="D"))
    return out


_RAMADAN = _ramadan_days()
_EID = _eid_days()


def calendar_features(dates: pd.Series) -> pd.DataFrame:
    d = pd.to_datetime(dates).dt.normalize()
    dow = d.dt.dayofweek  # Monday=0
    doy = d.dt.dayofyear
    out = pd.DataFrame(index=dates.index)
    out["dow_sin"] = np.sin(2 * np.pi * dow / 7)
    out["dow_cos"] = np.cos(2 * np.pi * dow / 7)
    out["doy_sin"] = np.sin(2 * np.pi * doy / 365.25)
    out["doy_cos"] = np.cos(2 * np.pi * doy / 365.25)
    out["is_saturday"] = (dow == 5).astype(int)
    out["is_sunday"] = (dow == 6).astype(int)
    out["is_fixed_holiday"] = [int((x.month, x.day) in FIXED_HOLIDAYS) for x in d]
    out["is_ramadan"] = d.isin(_RAMADAN).astype(int)
    out["is_eid"] = d.isin(_EID).astype(int)
    out["is_summer_peak"] = d.dt.month.isin([7, 8]).astype(int)
    known = set(RAMADAN_START)
    out["lunar_calendar_known"] = d.dt.year.isin(known).astype(int)
    return out

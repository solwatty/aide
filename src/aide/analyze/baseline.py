"""Per-day baselines for heart rate and HRV.

The stress signal we care about is *deviation from your own normal*, not absolute
BPM. So for each day we compute a resting baseline and compare meetings to it.
"""
from __future__ import annotations

from collections import defaultdict
from datetime import date
from statistics import median
from typing import Optional

from ..ingest.apple_health import HealthData
from ..models import HRSample, HRVSample


def _percentile(values: list[float], pct: float) -> float:
    """Simple nearest-rank percentile (pct in 0..100)."""
    if not values:
        raise ValueError("no values")
    s = sorted(values)
    k = max(0, min(len(s) - 1, round(pct / 100.0 * (len(s) - 1))))
    return s[k]


class Baselines:
    def __init__(self, hr_by_day: dict, hrv_by_day: dict, global_hrv: Optional[float]):
        self._hr = hr_by_day
        self._hrv = hrv_by_day
        self._global_hrv = global_hrv

    def resting_hr(self, day: date) -> Optional[float]:
        return self._hr.get(day)

    def hrv(self, day: date) -> Optional[float]:
        return self._hrv.get(day, self._global_hrv)


def compute_baselines(health: HealthData) -> Baselines:
    """Resting HR per day: prefer Apple's own RestingHeartRate; otherwise use the
    10th percentile of that day's readings as a robust resting proxy.

    HRV baseline per day: the day's median SDNN, falling back to the global median
    (HRV is sparse — often only a handful of readings per day, mostly overnight).
    """
    # group readings by calendar day
    hr_day: dict[date, list[float]] = defaultdict(list)
    for s in health.hr:
        hr_day[s.ts.date()].append(s.bpm)

    hrv_day: dict[date, list[float]] = defaultdict(list)
    for s in health.hrv:
        hrv_day[s.ts.date()].append(s.sdnn_ms)

    hr_baseline: dict[date, float] = {}
    for day, vals in hr_day.items():
        if day in health.resting_hr:
            hr_baseline[day] = health.resting_hr[day]
        elif vals:
            hr_baseline[day] = _percentile(vals, 10)
    # carry Apple resting-HR days that had no raw HR samples
    for day, bpm in health.resting_hr.items():
        hr_baseline.setdefault(day, bpm)

    hrv_baseline = {day: median(vals) for day, vals in hrv_day.items() if vals}
    global_hrv = median(hrv_baseline.values()) if hrv_baseline else None

    return Baselines(hr_baseline, hrv_baseline, global_hrv)

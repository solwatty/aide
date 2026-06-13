"""Score each meeting for physiological stress relative to your daily baseline.

Signal per meeting:
  * hr_elevation = mean HR during the meeting minus that day's resting HR (bpm)
  * hrv_drop     = that day's baseline HRV minus mean HRV during the meeting (ms)

We then z-score each signal across all scored meetings and combine them into one
``stress_score`` (higher = more physiologically activated). HR is the backbone;
HRV nudges it (config ``hrv_weight``) when readings exist in the window.
"""
from __future__ import annotations

import bisect
from datetime import timedelta
from statistics import mean, pstdev
from typing import Optional

from ..config import Config
from ..ingest.apple_health import HealthData
from ..models import Meeting, MeetingStress
from .baseline import Baselines


def _window_values(times: list, values: list, lo, hi) -> list[float]:
    """Values whose timestamp falls in [lo, hi], via binary search on sorted times."""
    left = bisect.bisect_left(times, lo)
    right = bisect.bisect_right(times, hi)
    return values[left:right]


def score_meetings(
    meetings: list[Meeting],
    health: HealthData,
    baselines: Baselines,
    config: Config,
) -> list[MeetingStress]:
    a = config.analysis
    hr_times = [s.ts for s in health.hr]
    hr_vals = [s.bpm for s in health.hr]
    hrv_times = [s.ts for s in health.hrv]
    hrv_vals = [s.sdnn_ms for s in health.hrv]

    results: list[MeetingStress] = []
    for m in meetings:
        lo = m.start - timedelta(minutes=a.pre_meeting_minutes)
        hi = m.end + timedelta(minutes=a.post_meeting_minutes)

        window_hr = _window_values(hr_times, hr_vals, lo, hi)
        baseline_hr = baselines.resting_hr(m.start.date())

        res = MeetingStress(
            meeting=m,
            n_hr_samples=len(window_hr),
            mean_hr=mean(window_hr) if window_hr else None,
            max_hr=max(window_hr) if window_hr else None,
            baseline_hr=baseline_hr,
        )

        if len(window_hr) >= a.min_hr_samples and baseline_hr is not None:
            res.hr_elevation = res.mean_hr - baseline_hr
            res.has_data = True

        window_hrv = _window_values(hrv_times, hrv_vals, lo, hi)
        if window_hrv:
            res.mean_hrv = mean(window_hrv)
            base_hrv = baselines.hrv(m.start.date())
            res.baseline_hrv = base_hrv
            if base_hrv is not None:
                res.hrv_drop = base_hrv - res.mean_hrv

        results.append(res)

    _assign_composite_scores(results, a.hrv_weight)
    return results


def _standardizer(values: list[float]):
    """Return f(x)->z over the given distribution, or None if it can't be built."""
    if len(values) < 2:
        return None
    mu, sd = mean(values), pstdev(values)
    if sd == 0:
        return lambda x: 0.0
    return lambda x: (x - mu) / sd


def _assign_composite_scores(results: list[MeetingStress], hrv_weight: float) -> None:
    scored = [r for r in results if r.has_data]
    hr_z = _standardizer([r.hr_elevation for r in scored])
    if hr_z is None:
        # Not enough meetings to standardize — fall back to raw elevation.
        for r in scored:
            r.stress_score = r.hr_elevation
        return

    hrv_z = _standardizer([r.hrv_drop for r in scored if r.hrv_drop is not None])

    for r in scored:
        z_hr = hr_z(r.hr_elevation)
        if hrv_z is not None and r.hrv_drop is not None:
            r.stress_score = (1 - hrv_weight) * z_hr + hrv_weight * hrv_z(r.hrv_drop)
        else:
            r.stress_score = z_hr

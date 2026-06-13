"""Parse Apple Health data into heart-rate and HRV time series.

Two input shapes are supported:

1. The official ``export.xml`` produced by the Health app
   (Profile -> Export All Health Data -> unzip -> ``apple_health_export/export.xml``).
   We stream it with ``iterparse`` so multi-GB files don't blow up memory.

2. A CSV fallback (e.g. from the "Health Auto Export" app), with a timestamp
   column and a value column. Heart rate and HRV live in separate files or in
   one file with a ``type``/``name`` column.

Both return plain lists of ``HRSample`` / ``HRVSample`` sorted by time.
"""
from __future__ import annotations

import csv
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, Optional
from xml.etree import ElementTree as ET

from ..models import HRSample, HRVSample

HR_TYPE = "HKQuantityTypeIdentifierHeartRate"
HRV_TYPE = "HKQuantityTypeIdentifierHeartRateVariabilitySDNN"
RESTING_HR_TYPE = "HKQuantityTypeIdentifierRestingHeartRate"

# Apple stamps dates like "2026-06-01 09:30:00 +1000".
_APPLE_DATE = re.compile(r"^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2} [+-]\d{4}$")


def parse_health_datetime(value: str) -> Optional[datetime]:
    """Parse the date formats Apple Health and common exporters emit."""
    if not value:
        return None
    value = value.strip()
    if _APPLE_DATE.match(value):
        return datetime.strptime(value, "%Y-%m-%d %H:%M:%S %z")
    # ISO 8601, with or without trailing Z.
    iso = value.replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(iso)
    except ValueError:
        pass
    for fmt in ("%Y-%m-%d %H:%M:%S", "%d/%m/%Y %H:%M:%S", "%m/%d/%Y %H:%M"):
        try:
            return datetime.strptime(value, fmt)
        except ValueError:
            continue
    return None


class HealthData:
    """Container for the health signals we extracted."""

    def __init__(
        self,
        hr: list[HRSample],
        hrv: list[HRVSample],
        resting_hr: dict,  # date -> bpm (Apple's own resting HR, when present)
    ):
        self.hr = sorted(hr, key=lambda s: s.ts)
        self.hrv = sorted(hrv, key=lambda s: s.ts)
        self.resting_hr = resting_hr

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return (
            f"HealthData(hr={len(self.hr)} samples, hrv={len(self.hrv)} samples, "
            f"resting_days={len(self.resting_hr)})"
        )


def _localize(dt: Optional[datetime], tz) -> Optional[datetime]:
    """Attach `tz` to a naive datetime so it can be compared with meeting times."""
    if dt is not None and dt.tzinfo is None and tz is not None:
        return dt.replace(tzinfo=tz)
    return dt


def load_apple_health(path: str | Path, assume_tz=None) -> HealthData:
    """Dispatch on file extension: .xml -> Apple export, .csv -> CSV (wide or long).

    `assume_tz` (a tzinfo) is applied to any naive timestamps — needed for the
    wide CSV export, which records local time with no offset.
    """
    p = Path(path)
    if p.suffix.lower() == ".csv":
        return _load_csv(p, assume_tz)
    return _load_xml(p, assume_tz)


def _load_xml(path: Path, assume_tz=None) -> HealthData:
    hr: list[HRSample] = []
    hrv: list[HRVSample] = []
    resting: dict = {}

    # iterparse keeps memory flat; we clear each element after reading it.
    for _event, elem in ET.iterparse(str(path), events=("end",)):
        if elem.tag != "Record":
            continue
        rtype = elem.get("type")
        if rtype in (HR_TYPE, HRV_TYPE, RESTING_HR_TYPE):
            ts = _localize(parse_health_datetime(elem.get("startDate", "")), assume_tz)
            raw = elem.get("value")
            if ts is not None and raw is not None:
                try:
                    val = float(raw)
                except ValueError:
                    val = None
                if val is not None:
                    if rtype == HR_TYPE:
                        hr.append(HRSample(ts, val))
                    elif rtype == HRV_TYPE:
                        hrv.append(HRVSample(ts, val))
                    else:  # resting HR: one value per day
                        resting[ts.date()] = val
        elem.clear()

    return HealthData(hr, hrv, resting)


def _load_csv(path: Path, assume_tz=None) -> HealthData:
    """CSV loader supporting two shapes.

    Wide (Apple "Health Auto Export" daily/by-minute): a single Date column plus
    one column per metric, e.g. ``Heart rate(count/min)``, ``Resting heart
    rate(count/min)``, ``Heart rate variability(ms)``. Detected when a
    heart-rate-named column exists alongside the timestamp.

    Long: a timestamp column, a value column, and (optionally) a type column.
    """
    with path.open(newline="") as fh:
        reader = csv.DictReader(fh)
        if not reader.fieldnames:
            return HealthData([], [], {})
        cols = {c.lower().strip(): c for c in reader.fieldnames}
        ts_col = _first(cols, ["timestamp", "datetime", "date", "start", "startdate"])
        if ts_col is None:
            raise ValueError(f"CSV {path} has no recognizable timestamp column: {reader.fieldnames}")

        hr_col = _match(cols, lambda c: "heart rate" in c and not any(
            x in c for x in ("resting", "walking", "variability", "recovery")))
        if hr_col:
            return _read_wide(reader, ts_col, cols, assume_tz)
        return _read_long(reader, ts_col, cols, path.stem.lower(), assume_tz)


def _read_wide(reader, ts_col, cols, assume_tz) -> HealthData:
    hr: list[HRSample] = []
    hrv: list[HRVSample] = []
    resting: dict = {}
    hr_col = _match(cols, lambda c: "heart rate" in c and not any(
        x in c for x in ("resting", "walking", "variability", "recovery")))
    resting_col = _match(cols, lambda c: "resting heart rate" in c)
    hrv_col = _match(cols, lambda c: "variability" in c or "sdnn" in c)

    for row in reader:
        ts = _localize(parse_health_datetime(row.get(ts_col, "")), assume_tz)
        if ts is None:
            continue
        hr_v = _f(row.get(hr_col)) if hr_col else None
        if hr_v is not None:
            hr.append(HRSample(ts, hr_v))
        hrv_v = _f(row.get(hrv_col)) if hrv_col else None
        if hrv_v is not None:
            hrv.append(HRVSample(ts, hrv_v))
        rest_v = _f(row.get(resting_col)) if resting_col else None
        if rest_v is not None:
            resting[ts.date()] = rest_v  # one resting value per day (repeated in source)
    return HealthData(hr, hrv, resting)


def _read_long(reader, ts_col, cols, name_hint, assume_tz) -> HealthData:
    hr: list[HRSample] = []
    hrv: list[HRVSample] = []
    val_col = _first(cols, ["value", "bpm", "heart_rate", "hr", "sdnn", "hrv", "qty"])
    type_col = _first(cols, ["type", "name", "metric"])
    if val_col is None:
        raise ValueError(f"long-format CSV needs a value column; got {list(cols.values())}")

    for row in reader:
        ts = _localize(parse_health_datetime(row.get(ts_col, "")), assume_tz)
        val = _f(row.get(val_col))
        if ts is None or val is None:
            continue
        kind = (row.get(type_col, "") if type_col else "").lower()
        is_hrv = (
            "hrv" in kind or "sdnn" in kind or "variability" in kind
            or (not kind and ("hrv" in name_hint or "sdnn" in name_hint
                              or val_col.lower() in ("sdnn", "hrv")))
        )
        (hrv if is_hrv else hr).append(
            HRVSample(ts, val) if is_hrv else HRSample(ts, val)
        )
    return HealthData(hr, hrv, {})


def _f(v) -> Optional[float]:
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _first(cols: dict, candidates: Iterable[str]) -> Optional[str]:
    for c in candidates:
        if c in cols:
            return cols[c]
    return None


def _match(cols: dict, pred) -> Optional[str]:
    for low, original in cols.items():
        if pred(low):
            return original
    return None

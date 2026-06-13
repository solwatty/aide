"""Tests for Apple Health ingestion (XML, wide CSV, long CSV)."""
from datetime import datetime, timezone, timedelta

from aide.ingest.apple_health import load_apple_health, parse_health_datetime

SYD = timezone(timedelta(hours=10))


def test_parse_apple_datetime():
    dt = parse_health_datetime("2026-06-01 09:30:00 +1000")
    assert dt == datetime(2026, 6, 1, 9, 30, tzinfo=SYD)


def test_parse_iso_datetime():
    dt = parse_health_datetime("2026-06-01T09:30:00+10:00")
    assert dt.hour == 9 and dt.tzinfo is not None


def test_load_xml(tmp_path):
    xml = tmp_path / "export.xml"
    xml.write_text(
        '<?xml version="1.0"?><HealthData>'
        '<Record type="HKQuantityTypeIdentifierHeartRate" unit="count/min" '
        'startDate="2026-06-01 09:30:00 +1000" value="88"/>'
        '<Record type="HKQuantityTypeIdentifierRestingHeartRate" unit="count/min" '
        'startDate="2026-06-01 06:00:00 +1000" value="55"/>'
        '<Record type="HKQuantityTypeIdentifierHeartRateVariabilitySDNN" unit="ms" '
        'startDate="2026-06-01 03:00:00 +1000" value="60"/>'
        "</HealthData>"
    )
    h = load_apple_health(xml)
    assert len(h.hr) == 1 and h.hr[0].bpm == 88
    assert len(h.hrv) == 1 and h.hrv[0].sdnn_ms == 60
    assert h.resting_hr[datetime(2026, 6, 1).date()] == 55


def test_load_wide_csv_localizes_naive_timestamps(tmp_path):
    csv = tmp_path / "Export.csv"
    csv.write_text(
        "Date,Heart rate(count/min),Resting heart rate(count/min),Walking heart rate average(count/min)\n"
        "2026-06-01 09:30:00,88.0,55.0,90.0\n"
        "2026-06-01 09:31:00,,55.0,\n"        # blank HR row is skipped
        "2026-06-01 09:32:00,92.0,55.0,\n"
    )
    h = load_apple_health(csv, assume_tz=SYD)
    assert len(h.hr) == 2                       # only rows with a HR value
    assert h.hr[0].ts.tzinfo is not None        # naive timestamps got localized
    assert h.hr[0].ts.utcoffset() == timedelta(hours=10)
    assert h.resting_hr[datetime(2026, 6, 1).date()] == 55.0


def test_load_long_csv(tmp_path):
    csv = tmp_path / "hr.csv"
    csv.write_text(
        "timestamp,type,value\n"
        "2026-06-01T09:30:00+10:00,HeartRate,88\n"
        "2026-06-01T09:31:00+10:00,HRV,61\n"
    )
    h = load_apple_health(csv)
    assert len(h.hr) == 1 and len(h.hrv) == 1

"""End-to-end style tests on the synthetic sample data.

The sample generator bakes in a known villain (Jordan Blake) and a stressful
client (Globex); these tests assert the pipeline recovers them.
"""
import subprocess
import sys
from datetime import datetime, timedelta, timezone

import pytest

from aide.analyze.attribution import attribute_clients, attribute_people, clients_for_meeting
from aide.analyze.baseline import compute_baselines
from aide.analyze.keywords import stress_keywords
from aide.analyze.stress import score_meetings
from aide.config import Config
from aide.ingest.apple_health import HealthData, load_apple_health
from aide.ingest.meetings import filter_meetings, load_calendar, load_granola, merge
from aide.models import Attendee, HRSample, Meeting

SYD = timezone(timedelta(hours=10))
ROOT = __import__("pathlib").Path(__file__).resolve().parent.parent
SAMPLE = ROOT / "sample_data"


@pytest.fixture(scope="module")
def sample_built():
    # Ensure sample data exists (generated deterministically).
    if not (SAMPLE / "apple_health_export.xml").exists():
        subprocess.run([sys.executable, str(ROOT / "scripts" / "make_sample_data.py")], check=True)
    config = Config.load(SAMPLE / "sample_config.json")
    health = load_apple_health(SAMPLE / "apple_health_export.xml", assume_tz=SYD)
    calendar = load_calendar(SAMPLE / "calendar_events.json", config)
    granola = load_granola(SAMPLE / "granola_meetings.json", config)
    meetings = filter_meetings(merge(calendar, granola), config)
    baselines = compute_baselines(health)
    stresses = score_meetings(meetings, health, baselines, config)
    return config, stresses


def test_meetings_get_scored(sample_built):
    _, stresses = sample_built
    scored = [s for s in stresses if s.has_data]
    assert len(scored) > 20


def test_villain_tops_people_leaderboard(sample_built):
    config, stresses = sample_built
    people = attribute_people(stresses, config)
    assert people, "expected a non-empty people leaderboard"
    assert people[0].label == "Jordan Blake"
    # the calming colleague should rank below the villain
    scores = {t.label: t.mean_score for t in people}
    assert scores["Jordan Blake"] > scores.get("Lena Fischer", -99)


def test_stressful_client_is_globex(sample_built):
    config, stresses = sample_built
    clients = attribute_clients(stresses, config)
    assert clients[0].label == "Globex"


def test_keywords_surface_villain_or_client(sample_built):
    config, stresses = sample_built
    kws = {t.label for t in stress_keywords(stresses, config)}
    assert "globex" in kws or "jordan" in kws


def test_dashboard_data_and_html(sample_built):
    import json
    import re

    from aide.report.dashboard import render_dashboard
    from aide.report.data_export import build_dashboard_data

    config, stresses = sample_built
    data = build_dashboard_data(stresses, config)
    assert data["meetings"], "expected meetings in dashboard data"
    scored = [m for m in data["meetings"] if m["hasData"]]
    assert scored and all("stress" in m and "people" in m for m in scored)

    html = render_dashboard(data)
    # the embedded JSON must survive escaping and re-parse cleanly
    payload = re.search(
        r'<script id="aide-data" type="application/json">(.*?)</script>', html, re.S
    ).group(1)
    assert "</script>" not in payload
    parsed = json.loads(payload.replace("<\\/", "</"))
    assert len(parsed["meetings"]) == len(data["meetings"])


def test_rooms_excluded_from_people():
    """Attendees matching exclude patterns never reach the leaderboard."""
    config = Config.from_dict({
        "self_emails": ["me@acme.example"],
        "internal_domains": ["acme.example"],
        "exclude_attendee_patterns": ["boardroom"],
        "analysis": {"min_meetings_for_leaderboard": 1, "min_hr_samples": 1, "min_meeting_minutes": 1},
    })
    start = datetime(2026, 6, 1, 9, 0, tzinfo=SYD)
    m = Meeting(
        uid="1", title="standup", start=start, end=start + timedelta(minutes=30),
        attendees=[
            Attendee("me@acme.example", is_self=True),
            Attendee("real.person@acme.example", "Real Person", is_internal=True),
            Attendee("big.boardroom@acme.example", "Big Boardroom", is_internal=True),
        ],
    )
    health = HealthData(
        [HRSample(start + timedelta(minutes=i * 5), 90) for i in range(5)], [], {start.date(): 60}
    )
    stresses = score_meetings([m], health, compute_baselines(health), config)
    labels = {t.label for t in attribute_people(stresses, config)}
    assert "Real Person" in labels
    assert "Big Boardroom" not in labels

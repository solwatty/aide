"""Serialize scored meetings into a compact structure the dashboard can filter
and re-aggregate entirely client-side (no server needed)."""
from __future__ import annotations

from datetime import datetime

from ..analyze.attribution import clients_for_meeting
from ..analyze.keywords import _STOP, _tokens
from ..config import Config
from ..models import MeetingStress


def build_dashboard_data(stresses: list[MeetingStress], config: Config) -> dict:
    stop = _STOP | config.stopwords_extra
    meetings = []
    for s in stresses:
        m = s.meeting
        people = [
            {"key": a.email, "label": a.display, "internal": a.is_internal}
            for a in m.others()
            if a.email and config.is_person(a.email, a.name)
        ]
        clients = sorted(clients_for_meeting(m, config))
        keywords = sorted(_tokens(m.text, stop)) if s.has_data else []
        meetings.append(
            {
                "title": m.title,
                "start": m.start.isoformat(),
                "date": m.start.strftime("%Y-%m-%d"),
                "weekday": m.start.weekday(),            # 0 = Monday
                "hour": m.start.hour,
                "durationMin": round(m.duration_minutes),
                "source": m.source,
                "hasData": s.has_data,
                "deltaHR": round(s.hr_elevation, 1) if s.hr_elevation is not None else None,
                "meanHR": round(s.mean_hr, 1) if s.mean_hr is not None else None,
                "maxHR": round(s.max_hr, 1) if s.max_hr is not None else None,
                "baselineHR": round(s.baseline_hr, 1) if s.baseline_hr is not None else None,
                "stress": round(s.stress_score, 3) if s.stress_score is not None else None,
                "people": people,
                "clients": clients,
                "keywords": keywords,
            }
        )
    meetings.sort(key=lambda x: x["start"])
    return {
        "generated": datetime.now().astimezone().isoformat(timespec="minutes"),
        "timezone": config.timezone,
        "minMeetingsDefault": config.analysis.min_meetings_for_leaderboard,
        "meetings": meetings,
    }

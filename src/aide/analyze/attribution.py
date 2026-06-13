"""Attribute meeting stress to the people and clients present.

For every scored meeting we credit its ``stress_score`` to each non-self attendee
and to each client the meeting maps to. We then aggregate so you can see *who*
and *which account* you're most physiologically activated around — controlling a
little for sample size so a single fluke meeting doesn't top the chart.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from statistics import mean, median
from typing import Optional

from ..config import Config
from ..models import MeetingStress


@dataclass
class Tally:
    key: str
    label: str
    scores: list[float] = field(default_factory=list)
    hr_elevations: list[float] = field(default_factory=list)
    meeting_titles: list[str] = field(default_factory=list)
    internal: Optional[bool] = None

    @property
    def n(self) -> int:
        return len(self.scores)

    @property
    def mean_score(self) -> float:
        return mean(self.scores) if self.scores else 0.0

    @property
    def median_score(self) -> float:
        return median(self.scores) if self.scores else 0.0

    @property
    def mean_hr_elevation(self) -> float:
        return mean(self.hr_elevations) if self.hr_elevations else 0.0

    @property
    def total_score(self) -> float:
        return sum(self.scores)


def _rank(tallies: list[Tally], min_n: int) -> list[Tally]:
    eligible = [t for t in tallies if t.n >= min_n]
    eligible.sort(key=lambda t: t.mean_score, reverse=True)
    return eligible


def attribute_people(stresses: list[MeetingStress], config: Config) -> list[Tally]:
    tallies: dict[str, Tally] = {}
    for s in stresses:
        if not s.has_data:
            continue
        for a in s.meeting.others():
            if not a.email or not config.is_person(a.email, a.name):
                continue
            t = tallies.setdefault(a.email, Tally(a.email, a.display, internal=a.is_internal))
            if a.name and (not t.label or "@" in t.label):
                t.label = a.name
            t.scores.append(s.stress_score)
            t.hr_elevations.append(s.hr_elevation)
            t.meeting_titles.append(s.meeting.title)
    return _rank(list(tallies.values()), config.analysis.min_meetings_for_leaderboard)


def clients_for_meeting(meeting, config: Config) -> set[str]:
    """A meeting maps to a client via (a) external attendee domains and
    (b) keywords in its title/notes. Returns a set of client labels."""
    clients: set[str] = set()
    for a in meeting.attendees:
        if a.is_self or a.is_internal:
            continue
        named = config.client_for_domain(a.email)
        if named:
            clients.add(named)
    text = meeting.text.lower()
    for kw, label in config.client_keyword_map.items():
        if kw in text:
            clients.add(label)
    return clients


def attribute_clients(stresses: list[MeetingStress], config: Config) -> list[Tally]:
    tallies: dict[str, Tally] = {}
    for s in stresses:
        if not s.has_data:
            continue
        for client in clients_for_meeting(s.meeting, config):
            t = tallies.setdefault(client, Tally(client, client))
            t.scores.append(s.stress_score)
            t.hr_elevations.append(s.hr_elevation)
            t.meeting_titles.append(s.meeting.title)
    return _rank(list(tallies.values()), config.analysis.min_meetings_for_leaderboard)

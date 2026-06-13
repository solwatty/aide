"""Find the words/topics that co-occur with your most stressful meetings.

For every keyword that appears in at least ``min_meetings`` scored meetings, we
compare the average stress of meetings that contain it against the overall
average. The gap ("lift") is how much that topic moves your needle.
"""
from __future__ import annotations

import re
from statistics import mean

from ..config import Config
from ..models import MeetingStress
from .attribution import Tally

# A compact English stoplist — enough to keep meeting titles signal-rich.
_STOP = {
    "the", "a", "an", "and", "or", "but", "of", "to", "in", "on", "for", "with",
    "at", "by", "from", "up", "about", "into", "over", "after", "is", "are", "was",
    "were", "be", "been", "being", "this", "that", "these", "those", "it", "its",
    "as", "if", "then", "so", "than", "too", "very", "can", "will", "just", "vs",
    "via", "amp", "x", "no", "title", "untitled", "re", "&", "-", "—", "1", "2", "3",
}

_TOKEN = re.compile(r"[a-z][a-z'&-]+")


def _tokens(text: str, stop: set[str]) -> set[str]:
    out = set()
    for tok in _TOKEN.findall(text.lower()):
        tok = tok.strip("'&-")
        if len(tok) >= 3 and tok not in stop:
            out.add(tok)
    return out


def stress_keywords(stresses: list[MeetingStress], config: Config, top: int = 25) -> list[Tally]:
    scored = [s for s in stresses if s.has_data]
    if not scored:
        return []
    stop = _STOP | config.stopwords_extra
    overall = mean(s.stress_score for s in scored)

    tallies: dict[str, Tally] = {}
    for s in scored:
        for kw in _tokens(s.meeting.text, stop):
            t = tallies.setdefault(kw, Tally(kw, kw))
            t.scores.append(s.stress_score)
            t.hr_elevations.append(s.hr_elevation)
            t.meeting_titles.append(s.meeting.title)

    min_n = config.analysis.min_meetings_for_leaderboard
    ranked = [t for t in tallies.values() if t.n >= min_n]
    # rank by lift over the overall mean (most stress-associated topics first)
    ranked.sort(key=lambda t: t.mean_score - overall, reverse=True)
    return ranked[:top]


def overall_mean_score(stresses: list[MeetingStress]) -> float:
    scored = [s.stress_score for s in stresses if s.has_data]
    return mean(scored) if scored else 0.0

"""Core data structures shared across ingestion, analysis and reporting."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional


@dataclass(frozen=True)
class HRSample:
    """A single heart-rate reading (beats per minute)."""
    ts: datetime
    bpm: float


@dataclass(frozen=True)
class HRVSample:
    """A heart-rate-variability reading (SDNN, milliseconds). Higher = calmer."""
    ts: datetime
    sdnn_ms: float


@dataclass
class Attendee:
    email: str
    name: str = ""
    response_status: str = ""
    is_self: bool = False
    is_internal: bool = False

    @property
    def display(self) -> str:
        return self.name or self.email


@dataclass
class Meeting:
    """A normalized meeting: precise time + attendees from calendar, content from Granola."""
    uid: str
    title: str
    start: datetime
    end: datetime
    attendees: list[Attendee] = field(default_factory=list)
    source: str = "calendar"          # calendar | granola | merged
    all_day: bool = False
    notes: str = ""                   # Granola summary / private notes
    granola_id: Optional[str] = None

    @property
    def duration_minutes(self) -> float:
        return (self.end - self.start).total_seconds() / 60.0

    def others(self) -> list[Attendee]:
        """Attendees who are not me."""
        return [a for a in self.attendees if not a.is_self]

    @property
    def text(self) -> str:
        """All free text associated with the meeting, for keyword mining."""
        return f"{self.title}\n{self.notes}".strip()


@dataclass
class MeetingStress:
    """The result of scoring one meeting against the heart-rate baseline."""
    meeting: Meeting
    n_hr_samples: int
    mean_hr: Optional[float]
    max_hr: Optional[float]
    baseline_hr: Optional[float]
    hr_elevation: Optional[float] = None   # mean_hr - baseline_hr (bpm)
    mean_hrv: Optional[float] = None
    baseline_hrv: Optional[float] = None
    hrv_drop: Optional[float] = None       # baseline_hrv - mean_hrv (ms); +ve = stress
    stress_score: Optional[float] = None   # composite z-score; +ve = more stressed
    has_data: bool = False

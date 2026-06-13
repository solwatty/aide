"""Configuration loading and identity helpers."""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path
from typing import Optional


@dataclass
class AnalysisConfig:
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    pre_meeting_minutes: int = 0
    post_meeting_minutes: int = 5
    min_hr_samples: int = 3
    min_meetings_for_leaderboard: int = 3
    min_meeting_minutes: int = 10
    drop_all_day_events: bool = True
    # How much the HRV-drop signal contributes to the composite score (0..1).
    # 0 = heart-rate only; the rest is weighted onto HR elevation.
    hrv_weight: float = 0.35

    @staticmethod
    def from_dict(d: dict) -> "AnalysisConfig":
        def _date(v):
            return date.fromisoformat(v) if v else None

        base = AnalysisConfig()
        return AnalysisConfig(
            start_date=_date(d.get("start_date")),
            end_date=_date(d.get("end_date")),
            pre_meeting_minutes=int(d.get("pre_meeting_minutes", base.pre_meeting_minutes)),
            post_meeting_minutes=int(d.get("post_meeting_minutes", base.post_meeting_minutes)),
            min_hr_samples=int(d.get("min_hr_samples", base.min_hr_samples)),
            min_meetings_for_leaderboard=int(
                d.get("min_meetings_for_leaderboard", base.min_meetings_for_leaderboard)
            ),
            min_meeting_minutes=int(d.get("min_meeting_minutes", base.min_meeting_minutes)),
            drop_all_day_events=bool(d.get("drop_all_day_events", base.drop_all_day_events)),
            hrv_weight=float(d.get("hrv_weight", base.hrv_weight)),
        )


@dataclass
class Config:
    timezone: str = "Australia/Sydney"
    self_emails: set[str] = field(default_factory=set)
    internal_domains: set[str] = field(default_factory=set)
    client_domain_map: dict[str, str] = field(default_factory=dict)
    client_keyword_map: dict[str, str] = field(default_factory=dict)
    stopwords_extra: set[str] = field(default_factory=set)
    # Substrings identifying non-people (meeting rooms, distribution lists, resources)
    # to keep out of the colleague leaderboard.
    exclude_attendee_patterns: set[str] = field(default_factory=set)
    analysis: AnalysisConfig = field(default_factory=AnalysisConfig)

    @staticmethod
    def load(path: str | Path) -> "Config":
        raw = json.loads(Path(path).read_text())
        return Config.from_dict(raw)

    @staticmethod
    def from_dict(raw: dict) -> "Config":
        return Config(
            timezone=raw.get("timezone", "Australia/Sydney"),
            self_emails={e.lower() for e in raw.get("self_emails", [])},
            internal_domains={d.lower() for d in raw.get("internal_domains", [])},
            client_domain_map={k.lower(): v for k, v in raw.get("client_domain_map", {}).items()},
            client_keyword_map={k.lower(): v for k, v in raw.get("client_keyword_map", {}).items()},
            stopwords_extra={w.lower() for w in raw.get("stopwords_extra", [])},
            exclude_attendee_patterns={p.lower() for p in raw.get("exclude_attendee_patterns", [])},
            analysis=AnalysisConfig.from_dict(raw.get("analysis", {})),
        )

    # --- identity helpers -------------------------------------------------
    def is_self(self, email: str) -> bool:
        return bool(email) and email.lower() in self.self_emails

    def domain_of(self, email: str) -> str:
        return email.rsplit("@", 1)[-1].lower() if email and "@" in email else ""

    def is_internal(self, email: str) -> bool:
        return self.domain_of(email) in self.internal_domains

    def client_for_domain(self, email: str) -> Optional[str]:
        return self.client_domain_map.get(self.domain_of(email))

    def is_person(self, email: str, name: str = "") -> bool:
        """False for meeting rooms, distribution lists and other non-human invitees."""
        if not email:
            return False
        low = f"{email} {name}".lower()
        return not any(p in low for p in self.exclude_attendee_patterns)

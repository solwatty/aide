"""Load Calendar + Granola snapshots and normalize them into ``Meeting`` objects.

The snapshot formats mirror what the connected Calendar / Granola tools return,
so refreshing them is essentially a passthrough (see docs/SCHEMA.md). Both loaders
are intentionally lenient about shape.
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

try:
    from zoneinfo import ZoneInfo
except ImportError:  # pragma: no cover - py<3.9
    ZoneInfo = None  # type: ignore

from ..config import Config
from ..models import Attendee, Meeting


def _tz(config: Config):
    if ZoneInfo is None:
        return None
    try:
        return ZoneInfo(config.timezone)
    except Exception:  # pragma: no cover - bad tz name
        return None


def _parse_dt(value: str, tz) -> Optional[datetime]:
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if dt.tzinfo is None and tz is not None:
        dt = dt.replace(tzinfo=tz)
    return dt


def _make_attendee(config: Config, email: str, name: str = "", status: str = "", is_self=None) -> Attendee:
    email = (email or "").lower()
    return Attendee(
        email=email,
        name=name or "",
        response_status=status or "",
        is_self=config.is_self(email) if is_self is None else is_self,
        is_internal=config.is_internal(email),
    )


# --------------------------------------------------------------------------
# Calendar
# --------------------------------------------------------------------------
def load_calendar(path: str | Path, config: Config) -> list[Meeting]:
    raw = json.loads(Path(path).read_text())
    events = raw.get("events", raw) if isinstance(raw, dict) else raw
    tz = _tz(config)
    meetings: list[Meeting] = []

    for ev in events:
        if ev.get("status") == "cancelled":
            continue
        start_block, end_block = ev.get("start", {}), ev.get("end", {})
        all_day = "date" in start_block and "dateTime" not in start_block

        if all_day:
            start = _parse_dt(start_block.get("date", "") + "T00:00:00", tz)
            end = _parse_dt(end_block.get("date", "") + "T00:00:00", tz)
        else:
            start = _parse_dt(start_block.get("dateTime", ""), tz)
            end = _parse_dt(end_block.get("dateTime", ""), tz)
        if start is None:
            continue
        if end is None:
            end = start + timedelta(minutes=30)

        attendees = []
        for a in ev.get("attendees", []) or []:
            attendees.append(
                _make_attendee(
                    config,
                    a.get("email", ""),
                    a.get("displayName", ""),
                    a.get("responseStatus", ""),
                    is_self=a.get("self", None),
                )
            )

        meetings.append(
            Meeting(
                uid=ev.get("id", f"cal-{len(meetings)}"),
                title=(ev.get("summary") or "(no title)").strip(),
                start=start,
                end=end,
                attendees=attendees,
                source="calendar",
                all_day=all_day,
            )
        )
    return meetings


# --------------------------------------------------------------------------
# Granola
# --------------------------------------------------------------------------
def load_granola(path: str | Path, config: Config) -> list[Meeting]:
    raw = json.loads(Path(path).read_text())
    items = raw.get("meetings", raw) if isinstance(raw, dict) else raw
    tz = _tz(config)
    meetings: list[Meeting] = []

    for m in items:
        start = (
            _parse_dt(m.get("date") or m.get("created_at") or m.get("start") or "", tz)
        )
        if start is None:
            continue
        end = _parse_dt(m.get("end") or "", tz) or (start + timedelta(minutes=30))

        attendees = []
        for a in m.get("attendees", []) or []:
            if isinstance(a, str):
                attendees.append(_make_attendee(config, a))
            else:
                attendees.append(
                    _make_attendee(config, a.get("email", ""), a.get("name", ""))
                )

        notes = "\n".join(
            str(m.get(k, "")) for k in ("summary", "notes", "overview", "transcript") if m.get(k)
        )

        meetings.append(
            Meeting(
                uid=f"granola-{m.get('id', len(meetings))}",
                title=(m.get("title") or "(untitled note)").strip(),
                start=start,
                end=end,
                attendees=attendees,
                source="granola",
                notes=notes,
                granola_id=m.get("id"),
            )
        )
    return meetings


# --------------------------------------------------------------------------
# Merge
# --------------------------------------------------------------------------
def merge(
    calendar: list[Meeting],
    granola: list[Meeting],
    tolerance_minutes: int = 45,
) -> list[Meeting]:
    """Attach Granola notes to the calendar meeting they overlap in time.

    Calendar meetings are the canonical stress unit (reliable times + attendees).
    Granola notes that don't match any calendar event are kept as standalone
    meetings so their topics still feed the keyword/client analysis.
    """
    tol = timedelta(minutes=tolerance_minutes)
    used: set[int] = set()

    for cal in calendar:
        best_i, best_gap = None, tol
        for i, g in enumerate(granola):
            if i in used:
                continue
            gap = abs(g.start - cal.start)
            if gap <= best_gap:
                best_gap, best_i = gap, i
        if best_i is not None:
            g = granola[best_i]
            used.add(best_i)
            cal.notes = (cal.notes + "\n" + g.notes).strip() if cal.notes else g.notes
            cal.granola_id = g.granola_id
            cal.source = "merged"
            # Granola sometimes knows external attendees the invite missed.
            known = {a.email for a in cal.attendees}
            for a in g.attendees:
                if a.email and a.email not in known:
                    cal.attendees.append(a)

    leftovers = [g for i, g in enumerate(granola) if i not in used]
    return calendar + leftovers


def filter_meetings(meetings: list[Meeting], config: Config) -> list[Meeting]:
    """Drop all-day/OOO blocks and too-short slots per config."""
    a = config.analysis
    out = []
    for m in meetings:
        if config.analysis.drop_all_day_events and m.all_day:
            continue
        if m.duration_minutes < a.min_meeting_minutes:
            continue
        if a.start_date and m.start.date() < a.start_date:
            continue
        if a.end_date and m.start.date() > a.end_date:
            continue
        out.append(m)
    return out

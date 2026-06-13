"""Generate synthetic but realistic sample data so `aide` runs out of the box.

We invent a small office with a known "villain" colleague and a stressful client,
bake that into the heart-rate stream, and emit the three input files. Running the
analyzer on this data should surface the villain at the top — a built-in sanity
check for the whole pipeline. All names are fictional.

Usage:  python scripts/make_sample_data.py [output_dir]
"""
from __future__ import annotations

import json
import random
import sys
from datetime import datetime, time, timedelta, timezone
from pathlib import Path

SYD = timezone(timedelta(hours=10))
RNG = random.Random(42)

SELF = {"email": "you@acme.example", "self": True}
INTERNAL = "acme.example"

# colleague -> how many bpm they add to a meeting (the signal we want recovered)
COLLEAGUES = {
    "Jordan Blake": 17,    # the villain
    "Priya Nair": 9,
    "Sam Okafor": 2,
    "Lena Fischer": -3,    # calming presence
    "Marcus Reed": 6,
}
# client -> (email domain, bpm bump, title keyword)
CLIENTS = {
    "Globex": ("globex.example", 11, "Globex budget review"),
    "Initech": ("initech.example", 4, "Initech roadmap"),
    "Umbrella": ("umbrella.example", 1, "Umbrella creative"),
}
CALM_TITLES = ["Team coffee", "1:1 catch-up", "Run club", "Design crit"]

BASE_RESTING = 57
BASE_MEETING = 74


def workdays(start: datetime, n: int):
    d, made = start, 0
    while made < n:
        if d.weekday() < 5:
            yield d
            made += 1
        d += timedelta(days=1)


def gen():
    start = datetime(2026, 5, 18, tzinfo=SYD)
    hr_records, hrv_records, resting_records = [], [], []
    events, granola = [], []
    uid = 0

    for day in workdays(start, 15):
        resting = BASE_RESTING + RNG.randint(-3, 3)
        resting_records.append((day.replace(hour=6, minute=0), resting))
        # overnight HRV baseline (calmer = higher)
        for h in (2, 4, 23):
            hrv_records.append((day.replace(hour=h), 60 + RNG.randint(-12, 12)))

        # background waking HR every 15 min
        for minutes in range(8 * 60, 18 * 60, 15):
            ts = day + timedelta(minutes=minutes)
            hr_records.append((ts, resting + 12 + RNG.randint(-6, 8)))

        # 3-4 meetings/day at 9:30, 11:00, 14:00, 16:00
        slots = [(9, 30), (11, 0), (14, 0), (16, 0)]
        RNG.shuffle(slots)
        for (h, m) in slots[: RNG.randint(3, 4)]:
            uid += 1
            mstart = day.replace(hour=h, minute=m)
            mend = mstart + timedelta(minutes=RNG.choice([30, 45, 60]))

            colleague = RNG.choice(list(COLLEAGUES))
            bump = COLLEAGUES[colleague]
            attendees = [SELF, _person(colleague)]

            # half the meetings are client meetings
            title = f"Sync with {colleague.split()[0]}"
            notes = ""
            if RNG.random() < 0.5:
                client = RNG.choice(list(CLIENTS))
                domain, cbump, ctitle = CLIENTS[client]
                bump += cbump
                title = ctitle
                attendees.append({"email": f"contact@{domain}"})
                notes = f"Discussion with {client} about deliverables and budget."
            elif RNG.random() < 0.4:
                title = RNG.choice(CALM_TITLES)
                bump -= 4

            # heart-rate samples during the meeting (every 5 min), elevated by bump
            t = mstart
            while t <= mend:
                hr = resting + (BASE_MEETING - BASE_RESTING) + bump + RNG.randint(-5, 6)
                hr_records.append((t, max(50, hr)))
                t += timedelta(minutes=5)
            # stressful meetings depress HRV a little
            hrv_records.append((mstart, max(15, 55 - bump + RNG.randint(-6, 6))))

            events.append(_event(uid, title, mstart, mend, attendees))
            granola.append(_granola(uid, title, mstart, notes))

    _write_xml(hr_records, hrv_records, resting_records)
    _write_json("calendar_events.json", {"events": events})
    _write_json("granola_meetings.json", {"meetings": granola})


def _person(name: str) -> dict:
    handle = name.lower().replace(" ", ".")
    return {"email": f"{handle}@{INTERNAL}", "displayName": name, "responseStatus": "accepted"}


def _event(uid, title, start, end, attendees) -> dict:
    return {
        "id": f"evt{uid}",
        "summary": title,
        "start": {"dateTime": start.isoformat()},
        "end": {"dateTime": end.isoformat()},
        "attendees": attendees,
        "status": "confirmed",
    }


def _granola(uid, title, start, notes) -> dict:
    return {"id": f"gr{uid}", "title": title, "date": start.isoformat(), "summary": notes}


def _apple_dt(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%d %H:%M:%S %z")


def _write_xml(hr, hrv, resting):
    lines = ['<?xml version="1.0" encoding="UTF-8"?>', '<HealthData locale="en_AU">']
    for ts, v in hr:
        lines.append(
            f'<Record type="HKQuantityTypeIdentifierHeartRate" unit="count/min" '
            f'startDate="{_apple_dt(ts)}" endDate="{_apple_dt(ts)}" value="{v}"/>'
        )
    for ts, v in hrv:
        lines.append(
            f'<Record type="HKQuantityTypeIdentifierHeartRateVariabilitySDNN" unit="ms" '
            f'startDate="{_apple_dt(ts)}" endDate="{_apple_dt(ts)}" value="{v}"/>'
        )
    for ts, v in resting:
        lines.append(
            f'<Record type="HKQuantityTypeIdentifierRestingHeartRate" unit="count/min" '
            f'startDate="{_apple_dt(ts)}" endDate="{_apple_dt(ts)}" value="{v}"/>'
        )
    lines.append("</HealthData>")
    (OUT / "apple_health_export.xml").write_text("\n".join(lines))


def _write_json(name, obj):
    (OUT / name).write_text(json.dumps(obj, indent=2))


OUT = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).resolve().parent.parent / "sample_data"

if __name__ == "__main__":
    OUT.mkdir(parents=True, exist_ok=True)
    gen()
    print(f"Wrote sample data to {OUT}/")

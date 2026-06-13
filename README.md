# aide — stress correlation analyzer 🫀

Your own version of [the WHOOP-meets-calendar hack](https://www.techradar.com/health-fitness/fitness-trackers/someone-hacked-his-whoop-to-see-which-of-his-colleagues-raised-his-stress-levels-the-most-and-i-need-this-immediately):
correlate your **Apple Health heart-rate data** with your **calendar + Granola
meetings** to see *which colleagues, clients and topics spike your stress the most*.

It joins three sources, scores every meeting for physiological activation
relative to your own daily resting baseline, then ranks the people, accounts and
keywords that travel with your most elevated meetings.

```
## Colleagues — who raises your stress most
 #  name                       mtgs  stress    ΔHR  type
 1  Caitlin Nicolatsopoulos       6   +0.96  28.1  internal
 2  Emily Eliot                   4   +0.59  25.0  external
 3  Iris Yuan                     6   +0.49  24.1  internal
 ...
```

## How it works

1. **Ingest** — parse Apple Health (`export.xml` *or* a wide/long CSV) into a
   heart-rate (and HRV, if present) time series. Parse a Calendar snapshot
   (precise times + attendees) and an optional Granola snapshot (titles, notes,
   topics). Merge Granola notes onto the calendar meeting they overlap in time.
2. **Baseline** — for each day, take your resting HR (Apple's own value, or the
   10th-percentile of the day's readings) and HRV median.
3. **Score** — for each meeting, average the heart rate during it and subtract
   that day's resting HR → **ΔHR** (bpm above resting). Z-score ΔHR across all
   meetings → **stress score** (0 = your average meeting, +1 = one SD higher).
   HRV depression nudges the score when readings exist (`hrv_weight`).
4. **Attribute** — credit each meeting's score to every (non-room) attendee, to
   the client(s) it maps to (external email domain + title keywords), and to the
   words in its title/notes. Aggregate and rank.
5. **Report** — Markdown + a self-contained HTML report, with PNG charts if
   `matplotlib` is installed.

## Install

```bash
pip install -e .            # core runs on the stdlib alone
pip install matplotlib      # optional: enables charts in the report
```

## Quick start (sample data)

The repo ships deterministic **synthetic** data (no real people) so you can see
it work immediately. The generator bakes in a known "villain" colleague — the
analyzer should surface them at #1:

```bash
python scripts/make_sample_data.py
aide analyze \
  --config sample_data/sample_config.json \
  --health sample_data/apple_health_export.xml \
  --calendar sample_data/calendar_events.json \
  --granola sample_data/granola_meetings.json \
  --out out
open out/report.html
```

## Running it on your data

1. **Export Apple Health.** Either:
   - Health app → your profile → *Export All Health Data* → unzip →
     `apple_health_export/export.xml`, **or**
   - a CSV with a `Date`/timestamp column and a `Heart rate(...)` column
     (e.g. the *Health Auto Export* app). Wide (one column per metric) and long
     (`timestamp,type,value`) layouts are both supported.
2. **Snapshot your meetings** into `data/calendar_events.json` (and optionally
   `data/granola_meetings.json`). The formats mirror the Google Calendar / Granola
   APIs — see [`docs/SCHEMA.md`](docs/SCHEMA.md). (In an assistant session with
   Calendar/Granola connected, these can be generated for you.)
3. **Configure** — copy `config.example.json` → `config.json` and set your own
   emails, internal domains, client map and room/list exclusions.
4. **Run:**

```bash
aide analyze --config config.json \
  --health data/export.xml \
  --calendar data/calendar_events.json \
  --granola data/granola_meetings.json \
  --out out
```

Everything under `data/` and your `config.json` are **git-ignored** — real
health and meeting data never get committed.

## Reading the numbers

- **ΔHR** — average bpm above your resting rate during those meetings. The most
  tangible figure.
- **stress** — the z-scored composite (HR + optional HRV). Comparable across
  people/clients/topics within your own data.
- **mtgs** — how many scored meetings back the number. Items below
  `min_meetings_for_leaderboard` are hidden so one fluke can't top the chart.

### Important caveat

This is **correlation, not causation**. Heart rate rises for many reasons that
ride along with meetings: back-to-back days, the walk to the room, the coffee
beforehand, presenting vs. listening, deadlines. An 8am calendar item can read
as "stressful" when it's really your commute or a workout. Treat the leaderboard
as a prompt for reflection, not a verdict on a person.

## Configuration reference

| key | meaning |
|---|---|
| `self_emails` | your addresses, excluded from attribution |
| `internal_domains` | domains treated as colleagues (vs. external clients) |
| `client_domain_map` | external email domain → client name |
| `client_keyword_map` | keyword in a title/notes → client name |
| `exclude_attendee_patterns` | substrings (email or name) for rooms/lists to drop |
| `stopwords_extra` | extra words to ignore in keyword mining |
| `analysis.post_meeting_minutes` | minutes after a meeting still counted (spillover) |
| `analysis.min_hr_samples` | min HR readings in-window to score a meeting |
| `analysis.min_meetings_for_leaderboard` | min meetings to appear on a leaderboard |
| `analysis.min_meeting_minutes` | drop slots shorter than this |
| `analysis.hrv_weight` | 0–1 weight of HRV drop in the composite (0 = HR only) |

## Tests

```bash
pytest -q
```

## Layout

```
src/aide/ingest/     apple_health.py · meetings.py
src/aide/analyze/    baseline.py · stress.py · attribution.py · keywords.py
src/aide/report/     leaderboard.py · charts.py · html.py
src/aide/cli.py      `aide analyze`
scripts/             make_sample_data.py
sample_data/         synthetic, runnable out of the box
```

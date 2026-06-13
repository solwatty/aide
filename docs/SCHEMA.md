# Input snapshot schemas

`aide` reads two JSON snapshots for meetings. Both loaders are lenient — extra
fields are ignored, so you can dump the raw API responses with minimal trimming.
Real snapshots live under `data/` (git-ignored); synthetic examples are in
`sample_data/`.

## `calendar_events.json`

Mirrors the Google Calendar `events.list` response. Either a bare list of
events, or `{ "events": [ ... ] }`.

```json
{
  "events": [
    {
      "id": "evt123",
      "summary": "SBS x Poem weekly",
      "status": "confirmed",
      "start": { "dateTime": "2026-05-18T11:00:00+10:00" },
      "end":   { "dateTime": "2026-05-18T12:00:00+10:00" },
      "attendees": [
        { "email": "alex.watts@poemgroup.com.au", "self": true, "responseStatus": "accepted" },
        { "email": "mel@sbs.com.au", "displayName": "Mel D", "responseStatus": "accepted" }
      ]
    }
  ]
}
```

Notes:
- All-day events use `"start": { "date": "2026-05-19" }` and are dropped by
  default (`analysis.drop_all_day_events`).
- `status: "cancelled"` events are skipped.
- Only `id`, `summary`, `start`, `end`, `status`, `attendees[].{email,
  displayName, responseStatus, self}` are used — strip the rest to keep the file
  small.

## `granola_meetings.json` (optional)

Either a bare list or `{ "meetings": [ ... ] }`.

```json
{
  "meetings": [
    {
      "id": "uuid-or-string",
      "title": "World Cup campaign — media coverage and content performance",
      "date": "2026-06-09T13:01:00+10:00",
      "summary": "Discussed creator partnerships and launch coordination…",
      "attendees": [ { "email": "alex@solw.at", "name": "Alex" } ]
    }
  ]
}
```

Notes:
- `date` may also be `created_at` or `start` (ISO 8601).
- `summary`/`notes`/`overview`/`transcript` are concatenated into the meeting's
  notes for keyword + client mining.
- Granola notes are matched to the calendar meeting they start within ±45 min of,
  and merged. Unmatched notes are kept as standalone meetings (they still feed
  keyword/client analysis; attendee attribution needs calendar data).

## Refreshing snapshots

If you're running inside an assistant session with Calendar and Granola
connected, the snapshots can be generated for you: list calendar events for the
window (trim to the fields above) and list Granola meetings, then write the two
JSON files into `data/`. Otherwise export them from the Google Calendar API and
Granola yourself in the shapes above.

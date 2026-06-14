"""Render leaderboards and a stats summary as plain text / Markdown."""
from __future__ import annotations

from statistics import mean

from ..analyze.attribution import Tally
from ..models import MeetingStress


def _fmt(x: float, n: int = 2) -> str:
    return f"{x:+.{n}f}"


def render_table(tallies: list[Tally], title: str, limit: int = 15, show_internal=False) -> str:
    lines = [f"## {title}", ""]
    if not tallies:
        lines.append("_Not enough data yet (need more scored meetings per item)._")
        return "\n".join(lines) + "\n"

    header = f"{'#':>2}  {'name':<34} {'mtgs':>4} {'stress':>7} {'ΔHR':>6}"
    if show_internal:
        header += "  type"
    lines.append("```")
    lines.append(header)
    lines.append("-" * len(header))
    for i, t in enumerate(tallies[:limit], 1):
        row = (
            f"{i:>2}  {t.label[:34]:<34} {t.n:>4} "
            f"{_fmt(t.mean_score):>7} {t.mean_hr_elevation:>5.1f}"
        )
        if show_internal:
            row += f"  {'internal' if t.internal else 'external'}"
        lines.append(row)
    lines.append("```")
    return "\n".join(lines) + "\n"


def render_summary(stresses: list[MeetingStress]) -> str:
    scored = [s for s in stresses if s.has_data]
    total = len(stresses)
    lines = ["## Summary", ""]
    if not scored:
        lines.append(
            f"- Meetings considered: **{total}**\n"
            "- Scored against heart-rate data: **0** — no heart-rate samples overlapped "
            "your meetings. Check the date ranges of your health export vs. your calendar."
        )
        return "\n".join(lines) + "\n"

    elev = [s.hr_elevation for s in scored]
    busiest = max(scored, key=lambda s: s.hr_elevation)
    lines += [
        f"- Meetings considered: **{total}**",
        f"- Scored against heart rate: **{len(scored)}**",
        f"- Mean HR elevation in meetings: **{mean(elev):.1f} bpm** above resting",
        f"- Single most activating meeting: **{busiest.meeting.title[:60]}** "
        f"({busiest.hr_elevation:+.0f} bpm, {busiest.meeting.start:%a %d %b %H:%M})",
        "",
        "_Stress score is a z-score across your meetings: 0 = your average meeting, "
        "+1 = one standard deviation more activated than usual._",
    ]
    return "\n".join(lines) + "\n"


def render_report(
    summary: str,
    people: list[Tally],
    clients: list[Tally],
    keywords: list[Tally],
    themes: list[Tally] | None = None,
) -> str:
    parts = [
        "# Stress Correlation Report",
        "",
        summary,
        render_table(people, "Colleagues — who raises your stress most", show_internal=True),
        render_table(clients, "Clients / accounts — most stressful"),
    ]
    if themes:
        parts.append(render_table(themes, "Themes — meeting types most stress-associated"))
    parts += [
        render_table(keywords, "Keywords — individual words most stress-associated"),
        "---",
        "_ΔHR = average heart-rate elevation (bpm) above your daily resting rate during "
        "those meetings. Correlation, not causation — a packed calendar, deadlines and "
        "back-to-back days all ride along with the people in the room._",
    ]
    return "\n".join(parts) + "\n"

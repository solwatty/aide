"""Command-line entry point: ``aide analyze ...``.

Pipeline: load health + meetings -> baselines -> per-meeting stress ->
attribution (people / clients) + keyword lift -> text + HTML report.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .analyze.attribution import attribute_clients, attribute_people
from .analyze.baseline import compute_baselines
from .analyze.keywords import stress_keywords
from .analyze.stress import score_meetings
from .config import Config
from .ingest.apple_health import load_apple_health
from .ingest.meetings import _tz, filter_meetings, load_calendar, load_granola, merge
from .report import charts, html, leaderboard
from .report.dashboard import render_dashboard
from .report.data_export import build_dashboard_data


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="aide", description=__doc__)
    sub = p.add_subparsers(dest="command", required=True)

    a = sub.add_parser("analyze", help="Run the full stress-correlation analysis.")
    a.add_argument("--config", default="config.json", help="Path to config JSON.")
    a.add_argument("--health", required=True, help="Apple Health export.xml or a CSV.")
    a.add_argument("--calendar", required=True, help="Calendar events snapshot (JSON).")
    a.add_argument("--granola", help="Granola meetings snapshot (JSON). Optional.")
    a.add_argument("--out", default="out", help="Output directory (default: out/).")
    a.add_argument("--top", type=int, default=15, help="Rows per leaderboard.")
    a.add_argument("--no-charts", action="store_true", help="Skip PNG charts.")
    return p


def run_analyze(args) -> int:
    config = Config.load(args.config) if Path(args.config).exists() else Config.from_dict({})
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    print(f"• Loading health data from {args.health} …", file=sys.stderr)
    health = load_apple_health(args.health, assume_tz=_tz(config))
    print(f"  {len(health.hr)} HR samples, {len(health.hrv)} HRV samples", file=sys.stderr)

    calendar = load_calendar(args.calendar, config)
    granola = load_granola(args.granola, config) if args.granola else []
    meetings = filter_meetings(merge(calendar, granola), config)
    print(f"• {len(meetings)} meetings after merge+filter", file=sys.stderr)

    baselines = compute_baselines(health)
    stresses = score_meetings(meetings, health, baselines, config)
    scored_n = sum(1 for s in stresses if s.has_data)
    print(f"• {scored_n} meetings scored against heart rate", file=sys.stderr)

    people = attribute_people(stresses, config)
    clients = attribute_clients(stresses, config)
    keywords = stress_keywords(stresses, config, top=args.top)

    summary = leaderboard.render_summary(stresses)
    report_md = leaderboard.render_report(summary, people, clients, keywords)
    (out / "report.md").write_text(report_md)
    print("\n" + report_md)

    people_png = clients_png = None
    if not args.no_charts:
        if charts.HAVE_MPL:
            people_png = out / "people.png"
            clients_png = out / "clients.png"
            charts.bar_chart(people, "Colleagues by mean stress", people_png)
            charts.bar_chart(clients, "Clients by mean stress", clients_png)
        else:
            print("(matplotlib not installed — skipping charts)", file=sys.stderr)

    (out / "report.html").write_text(
        html.render_html(summary, people, clients, keywords, people_png, clients_png)
    )

    dashboard = render_dashboard(build_dashboard_data(stresses, config))
    (out / "dashboard.html").write_text(dashboard)
    print(
        f"• Wrote {out/'report.md'}, {out/'report.html'} and {out/'dashboard.html'}",
        file=sys.stderr,
    )
    return 0


def main(argv=None) -> int:
    args = _build_parser().parse_args(argv)
    if args.command == "analyze":
        return run_analyze(args)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())

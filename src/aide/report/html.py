"""Render a self-contained HTML report (optionally embedding chart PNGs)."""
from __future__ import annotations

import base64
import html
from pathlib import Path
from typing import Optional

from ..analyze.attribution import Tally

_CSS = """
body{font:15px/1.5 -apple-system,Segoe UI,Roboto,sans-serif;max-width:920px;margin:40px auto;padding:0 20px;color:#1d1d1f}
h1{font-size:28px} h2{margin-top:40px;border-bottom:2px solid #eee;padding-bottom:6px}
table{border-collapse:collapse;width:100%;margin:12px 0}
th,td{text-align:left;padding:8px 10px;border-bottom:1px solid #eee}
th{font-size:12px;text-transform:uppercase;letter-spacing:.04em;color:#888}
td.num{text-align:right;font-variant-numeric:tabular-nums}
.pos{color:#d1495b;font-weight:600}.neg{color:#3a86ff}
.tag{font-size:11px;padding:2px 7px;border-radius:10px;background:#f0f0f2;color:#555}
.muted{color:#888}.note{background:#fafafa;border-left:3px solid #ddd;padding:10px 14px;margin:16px 0;font-size:14px}
img{max-width:100%;margin:10px 0;border:1px solid #eee;border-radius:8px}
"""


def _rows(tallies: list[Tally], show_type: bool) -> str:
    if not tallies:
        return '<tr><td colspan="5" class="muted">Not enough data yet.</td></tr>'
    out = []
    for i, t in enumerate(tallies, 1):
        cls = "pos" if t.mean_score >= 0 else "neg"
        typ = ""
        if show_type:
            label = "internal" if t.internal else "external"
            typ = f'<td><span class="tag">{label}</span></td>'
        out.append(
            f"<tr><td class='num'>{i}</td><td>{html.escape(t.label)}</td>"
            f"<td class='num'>{t.n}</td>"
            f"<td class='num {cls}'>{t.mean_score:+.2f}</td>"
            f"<td class='num'>{t.mean_hr_elevation:+.1f}</td>{typ}</tr>"
        )
    return "\n".join(out)


def _table(title: str, tallies: list[Tally], show_type=False, limit=15) -> str:
    extra = "<th>type</th>" if show_type else ""
    return f"""
<h2>{html.escape(title)}</h2>
<table>
<tr><th>#</th><th>name</th><th>mtgs</th><th>stress</th><th>ΔHR bpm</th>{extra}</tr>
{_rows(tallies[:limit], show_type)}
</table>"""


def _img(path: Optional[Path]) -> str:
    if not path or not path.exists():
        return ""
    data = base64.b64encode(path.read_bytes()).decode()
    return f'<img src="data:image/png;base64,{data}"/>'


def render_html(
    summary_md: str,
    people: list[Tally],
    clients: list[Tally],
    keywords: list[Tally],
    people_chart: Optional[Path] = None,
    clients_chart: Optional[Path] = None,
) -> str:
    summary_html = html.escape(summary_md).replace("\n", "<br>")
    return f"""<!doctype html><html><head><meta charset="utf-8">
<title>Stress Correlation Report</title><style>{_CSS}</style></head><body>
<h1>🫀 Stress Correlation Report</h1>
<div class="note">{summary_html}</div>
{_table("Colleagues — who raises your stress most", people, show_type=True)}
{_img(people_chart)}
{_table("Clients / accounts — most stressful", clients)}
{_img(clients_chart)}
{_table("Topics & keywords — most stress-associated", keywords)}
<div class="note muted">ΔHR = average heart-rate elevation above your daily resting rate during
those meetings. This is correlation, not causation — workload, deadlines and back-to-back
days travel with the people in the room. Stress score is a z-score across your own meetings.</div>
</body></html>"""

"""Optional matplotlib charts. Degrades gracefully if matplotlib isn't installed."""
from __future__ import annotations

from pathlib import Path

from ..analyze.attribution import Tally

try:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    HAVE_MPL = True
except Exception:  # pragma: no cover - optional dep
    HAVE_MPL = False


def bar_chart(tallies: list[Tally], title: str, path: Path, limit: int = 12) -> bool:
    """Horizontal bar chart of mean stress score. Returns True if written."""
    if not HAVE_MPL or not tallies:
        return False
    items = tallies[:limit][::-1]
    labels = [t.label[:30] for t in items]
    values = [t.mean_score for t in items]
    colors = ["#d1495b" if v >= 0 else "#3a86ff" for v in values]

    fig, ax = plt.subplots(figsize=(8, max(2.5, 0.45 * len(items))))
    ax.barh(labels, values, color=colors)
    ax.axvline(0, color="#333", linewidth=0.8)
    ax.set_xlabel("mean stress score (z)")
    ax.set_title(title)
    fig.tight_layout()
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=120)
    plt.close(fig)
    return True

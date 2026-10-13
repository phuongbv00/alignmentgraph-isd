"""Shared plotting: colour identity, style helpers, and the pdf+png pair.

Every figure ships as BOTH a vector .pdf (what the manuscript includes) and a
.png (what a reader previews); `audit artifacts` fails a figure missing either
half, so producing them together is the only way that check stays honest.

An agent keeps one colour, one marker and one line style across every figure,
so a reader who learns the legend once can read the rest without re-reading it.
"""

from __future__ import annotations

import math
import sys
from pathlib import Path

from .config import AGENT_DISPLAY, AGENT_ORDER
from .config import current as current_config
from .latex import model_display, size_display, size_of_label

try:
    import matplotlib
    matplotlib.use("Agg")          # no display, and no DISPLAY requirement
    import matplotlib.pyplot as plt
    from matplotlib.lines import Line2D
    from matplotlib.patches import Patch
except ImportError:  # pragma: no cover - the message is the useful part
    from .paths import EXP_ROOT, pip as _pip
    print(f"matplotlib is required for figures:  {_pip()} install -e {EXP_ROOT}",
          file=sys.stderr)
    raise


plt.rcParams.update({
    "font.size": 8,
    "axes.titlesize": 8.5,
    "axes.labelsize": 8,
    "legend.fontsize": 7.5,
    "xtick.labelsize": 7.5,
    "ytick.labelsize": 7.5,
    "axes.spines.top": False,
    "axes.spines.right": False,
    "axes.grid": True,
    "grid.color": "#dddddd",
    "grid.linewidth": 0.5,
    "axes.axisbelow": True,
    "figure.dpi": 110,
    "savefig.bbox": "tight",
})


#: The proposed system, emphasised in every figure so it can never be mistaken
#: for a comparison line.
PROPOSED = "alignmentgraph-isd"





# Rainbow-ordered (spectral) 7-hue categorical palette, fixed per agent
# (never cycled). Spectral ordering means the perceptually-closest hues are
# validated as adjacent pairs; the set passes the lightness band, chroma
# floor and normal-vision floor, with one adjacent pair (olive/orange) in
# the CVD 6-8 band — covered by a secondary encoding (olive is dashed, see
# AGENT_LINESTYLE). Line charts draw baselines as plain lines (no markers);
# only the proposed agent carries a marker + heavier width, so it can never
# be confused with a comparison line.
AGENT_COLOR = {
    "baseline": "#C42D00",            # red
    "eduplanner": "#EF9E0B",          # orange
    "addie-agent": "#8F9900",         # olive   (dashed — CVD pair w/ orange)
    "rpisd-agent": "#007A3D",         # green
    "dick-carey-agent": "#00B0D5",    # cyan
    "alignmentgraph-isd": "#0048B0",  # blue    (proposed — emphasized)
    "react-isd": "#E8438F",           # magenta
}
AGENT_LINESTYLE = {
    "addie-agent": (0, (4, 1.8)),     # secondary encoding for the olive/orange CVD pair
}


def point_marker(agent: str) -> str:
    """Marker for point/scatter figures: uniform circles, diamond = proposed.

    Per-agent marker shapes were dropped everywhere — identity is carried by
    hue (+ the olive dash on lines); shape only singles out the proposed."""
    return "D" if agent == PROPOSED else "o"
def _nan(v) -> float:
    return float(v) if isinstance(v, (int, float)) and not isinstance(v, bool) else float("nan")


def agents_in(pooled: dict) -> list[str]:
    present = {a for m in pooled["models"] for a in m.get("agents", {})}
    return [a for a in AGENT_ORDER if a in present]


def line_kw(agent: str) -> dict:
    """Series style: proposed = heavy line + diamond marker; baselines =
    plain lines, no markers (identity carried by hue + the one dash)."""
    proposed = agent == PROPOSED
    return {
        "color": AGENT_COLOR.get(agent, "#666666"),
        "marker": "D" if proposed else "",
        "linestyle": AGENT_LINESTYLE.get(agent, "-"),
        "linewidth": 2.6 if proposed else 1.4,
        "markersize": 5.5,
        "zorder": 5 if proposed else 3,
        "markeredgecolor": "white",
        "markeredgewidth": 0.6,
    }


def agent_legend(fig, agents: list[str], **kw) -> None:
    handles = [
        Line2D([], [], label=AGENT_DISPLAY.get(a, a), **{
            k: v for k, v in line_kw(a).items() if k != "zorder"})
        for a in agents
    ]
    kw.setdefault("loc", "upper center")
    kw.setdefault("bbox_to_anchor", (0.5, 0.0))
    kw.setdefault("ncol", 4)
    kw.setdefault("frameon", False)
    fig.legend(handles=handles, **kw)


def bar_legend(fig, agents: list[str], labels: dict[str, str] | None = None, **kw) -> None:
    """Legend for BAR charts: filled patches, matching the drawn encoding.

    agent_legend() builds Line2D handles (dashes, markers) that appear nowhere
    in a bar chart, so bars get their own key."""
    handles = [
        Patch(facecolor=AGENT_COLOR.get(a, "#666666"),
              label=(labels or {}).get(a, AGENT_DISPLAY.get(a, a)))
        for a in agents
    ]
    kw.setdefault("loc", "upper center")
    kw.setdefault("bbox_to_anchor", (0.5, 0.0))
    kw.setdefault("ncol", 4)
    kw.setdefault("frameon", False)
    fig.legend(handles=handles, **kw)


def thin_coverage_n(summary: dict, model: dict) -> int | None:
    """Scored-scenario n when it is < half the scenario union, else None.

    Under failure = 0 the cell's mean covers every scenario, but where more than
    half of them scored 0 because the system left no scorable output it is
    mostly a failure count; drawn identically to a mean of real scores it reads
    as comparable, so callers mark it."""
    n = summary.get("n_scenarios_complete")
    union = model.get("n_scenarios_union") or 0
    if isinstance(n, (int, float)) and not isinstance(n, bool) and union and n < 0.5 * union:
        return int(n)
    return None


def edge_annot_kw(x: float, sizes: list[float], dy: int = -11) -> dict:
    """Offset/alignment for an annotation, kept clear of the axis spines.

    At the leftmost x a centred label straddles the y-axis spine and collides
    with the tick labels, so edge points get pushed inward."""
    if x == sizes[0]:
        return {"xytext": (6, dy), "ha": "left"}
    if x == sizes[-1]:
        return {"xytext": (-6, dy), "ha": "right"}
    return {"xytext": (0, dy), "ha": "center"}


def median(xs: list[float]) -> float:
    ys = sorted(v for v in xs if not math.isnan(v))
    if not ys:
        return float("nan")
    mid = len(ys) // 2
    return ys[mid] if len(ys) % 2 else 0.5 * (ys[mid - 1] + ys[mid])


def sized_axis(ax, sizes: list[float], labels: list[str]) -> None:
    ax.set_xscale("log")
    ax.set_xticks(sizes)
    ax.set_xticklabels([model_display(lb) for lb in labels])
    ax.minorticks_off()
    ax.set_xlabel("Model size")




def save(fig, outdir: Path, name: str, written: list[Path] | None = None) -> list[Path]:
    """Write one figure as a .pdf/.png pair.

    Both, always: the manuscript includes the vector form and `audit artifacts`
    check F fails a figure that ships only one of them.
    """
    outdir.mkdir(parents=True, exist_ok=True)
    out = []
    for ext in ("pdf", "png"):
        path = outdir / f"{name}.{ext}"
        fig.savefig(path, bbox_inches="tight", dpi=200 if ext == "png" else None)
        out.append(path)
        if written is not None:
            written.append(path)
    plt.close(fig)
    return out

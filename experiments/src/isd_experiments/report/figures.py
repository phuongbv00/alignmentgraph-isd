"""Figures for the manuscript.

Every figure is written as a .pdf/.png pair by ``plots.save``. Colour, marker
and line-style identity per agent lives in ``plots`` so a reader who learns the
legend on one figure can read the rest.
"""

from __future__ import annotations

import math
import random
from pathlib import Path

from .. import paths
from ..alignment.protocol import ALIGNMENT_SIGNALS
from ..config import AGENT_DISPLAY, AGENT_ORDER, LLM_JUDGE_LEAD
from ..pool.panel import SUMMARY_SIGNAL
from ..plots import (
    AGENT_COLOR,
    AGENT_LINESTYLE,
    PROPOSED,
    Line2D,
    Patch,
    _nan,
    agent_legend,
    agents_in,
    bar_legend,
    edge_annot_kw,
    line_kw,
    median,
    plt,
    point_marker,
    save,
    size_display,
    sized_axis,
    thin_coverage_n,
)
from ..latex import model_display, size_of_label
from ..runs import extract_alignment_metrics, group_by_glob, load_run
from ..stats import spearman_rho

#: Each plotted mean with the SD of its OWN signal. The bare `run_to_run_sd` is
#: a total_score statistic; drawing it under an ADDIE or Trajectory mean once
#: overstated spread by a factor of sixteen.
#:
#: These are SDs across SCENARIOS, drawn as SEM: one run per cell
#: means a run-to-run SD has a single value and does not exist. Both ladder
#: figures use this convention, so their error bars mean the same thing.
LLM_JUDGE_SD_FIELD = {
    "mean_addie": "sd_addie_across_scenarios",
    "mean_traj": "sd_traj_across_scenarios",
    "mean_total": "sd_total_across_scenarios",
}
#: The lead signal's key in `comparisons.by_score`, and the field holding its
#: mean in an agent summary row. Two different spellings of the same signal,
#: and confusing them silently indexes the wrong dict -- so both are named.
LLM_JUDGE_LEAD_FIELD = "mean_addie"        # agents[<id>]["mean_addie"]

PRODUCER = "isd-exp report figures"

#: The panel, and only the panel — mirror alignment.ALIGNMENT_SIGNALS.
PANEL_COMPONENTS = [
    ("objective_assessment_similarity", "Obj→Asm"),
    ("objective_activity_similarity", "Obj→Act"),
    ("activity_assessment_similarity", "Act→Asm"),
    ("objective_cognitive_congruence", "Cognitive"),
    ("porter_mean", "Porter"),
    ("webb_bloom_consistency", "Webb"),
]

#: Number of leading PANEL_COMPONENTS entries belonging to instrument family A
#: (textual correspondence). The rest are family B (cognitive demand). A
#: separator is drawn at this boundary so the single colourbar cannot be read
#: as one construct across both families.
PANEL_FAMILY_A_N = 3

#: In-figure disclosure for the panel heatmaps. Figures get read detached from
#: their LaTeX caption, so every caveat a reader needs to not over-read a cell
#: has to live inside the image: the two instrument families, the flat-panel
#: status, and why some cells carry an n. No non-directionality note any more —
#: the one non-directional signal left the panel.
PANEL_FOOTNOTE = (
    "Flat panel of 6 alignment signals, no primary endpoint. Family A = the three edges of the "
    "constructive-alignment triad (textual correspondence, rectified cosine "
    "max(0, cos) on [0,1]): Obj→Asm, Obj→Act, Act→Asm.  "
    "Family B (cognitive demand, Bloom-derived, no similarity): Cognitive congruence, "
    "Porter (mean of 3 pairwise indices), Webb.\n"
    "Cell values omit the leading zero. A red n marks a cell where fewer than half the "
    "scenarios produced a scorable output — a survivorship mean, not comparable with "
    "full-coverage cells."
)



# ── figure builders ──────────────────────────────────────────────────────────

def fig_llm_judge_ladder(pooled: dict, outdir: Path, written: list[Path]) -> None:
    models = pooled["models"]
    agents = agents_in(pooled)
    sizes = [size_of_label(m["label"]) for m in models]
    labels = [m["label"] for m in models]

    sd_field = LLM_JUDGE_SD_FIELD[LLM_JUDGE_LEAD_FIELD]
    union = models[0].get("n_scenarios_union") if models else None

    fig, ax = plt.subplots(figsize=(5.0, 3.4))
    thin_seen = False
    for a in agents:
        summaries = [m["agents"].get(a, {}) for m in models]
        ys = [_nan(s.get(LLM_JUDGE_LEAD_FIELD)) for s in summaries]
        # SD must belong to the plotted signal; if 07 did not emit the
        # per-signal field, draw no error bars rather than a foreign SD.
        # Plotted as SEM = SD / sqrt(n): the SD is spread across scenarios, and
        # what the error bar should show is the precision of the cell's mean.
        errs = []
        for st in summaries:
            sd = _nan(st.get(sd_field))
            n = st.get("n_scenarios_complete") or 0
            errs.append(sd / math.sqrt(n) if n and not math.isnan(sd) else float("nan"))
        have_sd = any(not math.isnan(e) for e in errs)
        errs = [0.0 if math.isnan(e) else e for e in errs]
        ax.errorbar(sizes, ys, yerr=errs if have_sd else None,
                    capsize=2, elinewidth=0.8, **line_kw(a))
        # thin complete-case support: open marker + n, so a survivorship mean
        # cannot be read as comparable with a full-coverage point
        for x, y, s, m in zip(sizes, ys, summaries, models):
            n = thin_coverage_n(s, m)
            if n is None or math.isnan(y):
                continue
            thin_seen = True
            ax.plot([x], [y], marker="o", markersize=6.0, markerfacecolor="white",
                    markeredgecolor=AGENT_COLOR.get(a, "#666666"),
                    markeredgewidth=1.3, linestyle="", zorder=7)
            ax.annotate(f"n={n}", xy=(x, y), textcoords="offset points",
                        fontsize=6, color=AGENT_COLOR.get(a, "#666666"),
                        **edge_annot_kw(x, sizes, dy=-12))
    # direct label on the proposed agent (secondary encoding beside the legend)
    prop_y = _nan(models[-1]["agents"].get(PROPOSED, {}).get(LLM_JUDGE_LEAD_FIELD))
    if not math.isnan(prop_y):
        ax.annotate(AGENT_DISPLAY[PROPOSED], xy=(sizes[-1], prop_y),
                    xytext=(6, 0), textcoords="offset points",
                    va="center", fontsize=7.5, color=AGENT_COLOR[PROPOSED],
                    fontweight="bold")
        ax.set_xlim(right=sizes[-1] * 2.4)
    sized_axis(ax, sizes, labels)
    ax.set_ylabel("ADDIE rubric (/100)")
    ax.grid(axis="x", visible=False)
    note = "error bars: ±SEM across scenarios"
    if thin_seen:
        note += ("\nopen marker + n: complete-case mean over\n"
                 f"fewer than half of {union} scenarios (agent failures)")
    ax.text(0.98, 0.02, note, transform=ax.transAxes, ha="right", va="bottom",
            multialignment="right", fontsize=6.5, color="#666666", zorder=8)
    agent_legend(fig, agents, bbox_to_anchor=(0.5, -0.02))
    save(fig, outdir, "fig_llm_judge_ladder", written)


def fig_llm_judge_delta(pooled: dict, outdir: Path, written: list[Path]) -> None:
    models = pooled["models"]
    baselines = pooled["config"]["baselines"]
    sizes = [size_of_label(m["label"]) for m in models]
    labels = [m["label"] for m in models]
    inter = {r["baseline"]: r for r in pooled.get("interaction", {}).get("per_baseline", [])}

    fig, axes = plt.subplots(2, 3, figsize=(7.0, 4.2), sharex=True, sharey=True)
    for ax, b in zip(axes.flat, baselines):
        rows_by_size = []
        for m in models:
            rows = m["comparisons"]["by_score"][LLM_JUDGE_LEAD]["policies"]["complete_case"]
            rows_by_size.append(next((r for r in rows if r.get("baseline") == b), {}))
        ys = [_nan(r.get("mean_diff")) for r in rows_by_size]
        los = [_nan((r.get("ci95") or [None, None])[0]) for r in rows_by_size]
        his = [_nan((r.get("ci95") or [None, None])[1]) for r in rows_by_size]
        sig = [_nan(r.get("p_holm")) < 0.05 for r in rows_by_size]

        ax.axhline(0, color="#999999", linewidth=0.8, zorder=1)
        ax.fill_between(sizes, los, his, color=AGENT_COLOR[PROPOSED], alpha=0.15, linewidth=0, zorder=2)
        ax.plot(sizes, ys, color=AGENT_COLOR[PROPOSED], linewidth=1.4, zorder=3)
        for x, y, s, r, m in zip(sizes, ys, sig, rows_by_size, models):
            ax.plot([x], [y], marker="D", markersize=4.5,
                    markerfacecolor=AGENT_COLOR[PROPOSED] if s else "white",
                    markeredgecolor=AGENT_COLOR[PROPOSED], markeredgewidth=1.0, zorder=4)
            # flag points backed by few complete-case pairs (heavy agent failure)
            n = r.get("n")
            if n is not None and n < 0.5 * (m.get("n_scenarios_union") or n):
                ax.annotate(f"n={n}", xy=(x, y), textcoords="offset points",
                            fontsize=6, color="#666666",
                            **edge_annot_kw(x, sizes))
        row = inter.get(b)
        if row:
            # The slope rests on the scenarios common to every size; with a
            # handful of them the bootstrap CI collapses to zero width and
            # would read as infinite precision, so print n and drop the
            # interval when the support is too thin to bound anything.
            n_common = row.get("trend_n_common_scenarios")
            ci = row.get("trend_slope_ci95")
            slope = f"slope/step {row['trend_ols_slope_per_size_step']:+.2f}"
            if isinstance(n_common, int) and n_common < 10:
                stat = f"{slope} (n={n_common} common scen.)"
            elif ci:
                stat = f"{slope} [{ci[0]:+.2f}, {ci[1]:+.2f}]"
                stat += f", n={n_common}" if isinstance(n_common, int) else ""
            else:
                stat = slope
            ax.set_title(f"vs {AGENT_DISPLAY.get(b, b)}\n{stat}", fontsize=7.0)
        else:
            ax.set_title(f"vs {AGENT_DISPLAY.get(b, b)}", fontsize=7.5)
        sized_axis(ax, sizes, labels)
        ax.grid(axis="x", visible=False)
    for ax in axes[0]:
        ax.set_xlabel("")
    # one figure-level y label: the 30-char label is longer than a single row's
    # axis is tall, so per-axes labels butt into each other
    fig.supylabel("Δ ADDIE (proposed − baseline)", fontsize=8)
    fig.suptitle(
        "Paired per-scenario delta with bootstrap 95% CI "
        "(filled marker: Holm-adjusted p < 0.05)", fontsize=8.5)
    fig.tight_layout(rect=(0.02, 0, 1, 0.97))
    save(fig, outdir, "fig_llm_judge_delta", written)


def fig_llm_judge_components(pooled: dict, outdir: Path, written: list[Path]) -> None:
    models = pooled["models"]
    agents = agents_in(pooled)
    sizes = [size_of_label(m["label"]) for m in models]
    labels = [m["label"] for m in models]

    fig, axes = plt.subplots(1, 3, figsize=(10.0, 2.9), sharex=True)
    for ax, (field, title) in zip(axes, [("mean_addie", "ADDIE (rubric, /100)"),
                                         ("mean_traj", "Trajectory (/100)"),
                                         ("mean_total", "Total (0.7 ADDIE + 0.3 Traj, /100)")]):
        for a in agents:
            ys = [_nan(m["agents"].get(a, {}).get(field)) for m in models]
            ax.plot(sizes, ys, **line_kw(a))
        sized_axis(ax, sizes, labels)
        ax.set_title(title)
        ax.grid(axis="x", visible=False)
    axes[0].set_ylabel("Component mean")
    agent_legend(fig, agents, bbox_to_anchor=(0.5, -0.04))
    fig.tight_layout()
    save(fig, outdir, "fig_llm_judge_components", written)


def fig_alignment_ladder(pooled: dict, outdir: Path, written: list[Path]) -> bool:
    align = pooled.get("alignment") or {}
    if not align.get("models"):
        return False
    models = [m for m in pooled["models"] if m["label"] in align["models"]]
    agents = agents_in(pooled)
    sizes = [size_of_label(m["label"]) for m in models]
    labels = [m["label"] for m in models]

    fig, ax = plt.subplots(figsize=(4.8, 3.2))
    for a in agents:
        ys, errs = [], []
        for m in models:
            cell = align["models"][m["label"]].get(a, {}).get("objective_assessment_similarity", {})
            ys.append(_nan(cell.get("mean")))
            n = cell.get("n_scenarios") or 0
            sd = _nan(cell.get("sd_across_scenarios"))
            errs.append(sd / math.sqrt(n) if n and not math.isnan(sd) else 0.0)
        ax.errorbar(sizes, ys, yerr=errs, capsize=2, elinewidth=0.8, **line_kw(a))
    sized_axis(ax, sizes, labels)
    ax.set_ylabel("Objective$\\to$assessment similarity (0–1)")
    ax.grid(axis="x", visible=False)
    ax.text(0.02, 0.02, "error bars: ±SEM across scenarios",
            transform=ax.transAxes, fontsize=6.5, color="#666666")
    agent_legend(fig, agents, bbox_to_anchor=(0.5, -0.02))
    save(fig, outdir, "fig_alignment_ladder", written)
    return True


def fig_alignment_components(pooled: dict, outdir: Path, written: list[Path]) -> bool:
    align = pooled.get("alignment") or {}
    if not align.get("models"):
        return False
    models = [m for m in pooled["models"] if m["label"] in align["models"]]
    agents = agents_in(pooled)
    comp_keys = [k for k, _ in PANEL_COMPONENTS]
    comp_names = [n for _, n in PANEL_COMPONENTS]

    # wide enough that a 3-glyph value fits inside a column without touching
    # its neighbour (the 6 panel signals are narrow by construction)
    fig, axes = plt.subplots(1, len(models),
                             figsize=(3.05 * len(models) + 1.6, 2.4 + 0.34 * len(agents)),
                             sharey=True)
    axes = [axes] if len(models) == 1 else list(axes)
    cmap = plt.get_cmap("Blues")
    last_im = None
    for ax, m in zip(axes, models):
        cells = [[align["models"][m["label"]].get(a, {}).get(k, {}) or {}
                  for k in comp_keys] for a in agents]
        grid = [[_nan(c.get("mean")) for c in row] for row in cells]
        ns = [n for row in cells for c in row
              if isinstance(n := c.get("n_scenarios"), int)]
        n_max = max(ns) if ns else 0
        last_im = ax.imshow(grid, cmap=cmap, vmin=0.0, vmax=1.0, aspect="auto")
        for i, row in enumerate(grid):
            for j, v in enumerate(row):
                if math.isnan(v):
                    continue
                txt = f"{v:.2f}"
                dark = v > 0.55
                ax.text(j, i, txt[1:] if 0 <= v < 1 else txt,
                        ha="center", va="center", fontsize=6.5,
                        color="white" if dark else "#333333")
                n = cells[i][j].get("n_scenarios")
                if isinstance(n, int) and n_max and n < 0.5 * n_max:
                    ax.text(j, i + 0.30, f"n={n}", ha="center", va="center",
                            fontsize=5.5,
                            color="#FFC4C4" if dark else "#8B0000")
        # separator between the two instrument families (A | B)
        ax.axvline(PANEL_FAMILY_A_N - 0.5, color="white", linewidth=2.0, zorder=4)
        ax.set_title(model_display(m['label']))
        ax.set_xticks(range(len(comp_names)))
        ax.set_xticklabels(comp_names, rotation=35, ha="right", fontsize=7.5)
        ax.grid(visible=False)
        ax.tick_params(length=0)
        for spine in ax.spines.values():
            spine.set_visible(False)
    axes[0].set_yticks(range(len(agents)))
    axes[0].set_yticklabels([AGENT_DISPLAY.get(a, a) for a in agents], fontsize=8)
    cbar = fig.colorbar(last_im, ax=axes, fraction=0.02, pad=0.02)
    cbar.ax.tick_params(labelsize=6.5)
    cbar.set_label("Panel signal mean (0–1)", fontsize=7)
    fig.text(0.5, -0.05, PANEL_FOOTNOTE, ha="center", va="top",
             fontsize=6.5, color="#555555", linespacing=1.5)
    save(fig, outdir, "fig_alignment_components", written)
    return True


#: Baseline the alignment forest plot is drawn against: the strongest overall rival,
#: matching the comparison the results narrative leads with.
RQ2_FOREST_BASELINE = "react-isd"


def fig_alignment_forest(pooled: dict, outdir: Path, written: list[Path]) -> bool:
    """Forest plot of paired panel-signal deltas (proposed - RQ2_FOREST_BASELINE).

    Primary failure=0 layer, one facet per size, 6 signals per facet in panel
    order with the family A|B separator; filled marker = within-signal
    Holm-adjusted p < 0.05. This is the significance view the heatmap
    deliberately does not carry.
    """
    align = pooled.get("alignment") or {}
    stats = (align.get("stats") or {}).get("per_model") or []
    if not stats:
        return False
    comp_keys = [k for k, _ in PANEL_COMPONENTS]
    comp_names = [n for _, n in PANEL_COMPONENTS]
    ys = list(range(len(comp_keys)))[::-1]  # top-down in panel order

    fig, axes = plt.subplots(1, len(stats), figsize=(1.85 * len(stats) + 1.2, 2.9),
                             sharey=True, sharex=True)
    axes = [axes] if len(stats) == 1 else list(axes)
    color = AGENT_COLOR[PROPOSED]
    for ax, m in zip(axes, stats):
        panel = m.get("panel") or {}
        for y, key in zip(ys, comp_keys):
            rows = (panel.get(key) or {}).get("comparisons_failure_zero") or []
            r = next((r for r in rows if r.get("baseline") == RQ2_FOREST_BASELINE), {})
            d = _nan(r.get("mean_diff"))
            lo, hi = (r.get("ci95") or [float("nan"), float("nan")])
            if math.isnan(d):
                continue
            sig = _nan(r.get("p_holm")) < 0.05
            ax.plot([lo, hi], [y, y], color=color, linewidth=1.1, zorder=2)
            ax.plot([d], [y], marker="D", markersize=4.0,
                    markerfacecolor=color if sig else "white",
                    markeredgecolor=color, markeredgewidth=1.0, zorder=3)
        ax.axvline(0, color="#999999", linewidth=0.8, zorder=1)
        # family A | B separator, same convention as the heatmap
        ax.axhline(len(comp_keys) - PANEL_FAMILY_A_N - 0.5, color="#CCCCCC",
                   linewidth=0.8, linestyle=":", zorder=1)
        ax.set_title(model_display(m['label']), fontsize=8)
        ax.grid(axis="y", visible=False)
    axes[0].set_yticks(ys)
    axes[0].set_yticklabels(comp_names, fontsize=7.5)
    fig.supxlabel(
        f"Δ score (proposed − {AGENT_DISPLAY.get(RQ2_FOREST_BASELINE, RQ2_FOREST_BASELINE)}), "
        "failure=0 layer", fontsize=8)
    fig.text(0.5, -0.06,
             "Paired per-scenario delta with bootstrap 95% CI; filled marker: "
             "within-signal Holm-adjusted p < 0.05. † Asm→Obj is non-directional "
             "and excluded from the directional count.",
             ha="center", va="top", fontsize=6.5, color="#555555")
    fig.tight_layout()
    save(fig, outdir, "fig_alignment_forest", written)
    return True


def collect_scenario_pairs(pattern: str, agents: list[str]) -> dict[str, dict[str, list[tuple[float, float]]]]:
    """label -> agent -> [(total_mean, align_mean)] per scenario (mean of runs)."""
    out: dict[str, dict[str, list[tuple[float, float]]]] = {}
    for label, dirs in group_by_glob(pattern).items():
        acc: dict[str, dict[str, dict[str, list[float]]]] = {}
        for d in dirs:
            for sid, payload in load_run(d).items():
                doc = payload.get("alignment")
                align = extract_alignment_metrics(doc, agents) if doc else {}
                for a in agents:
                    r = payload["rankings"].get(a) or {}
                    t, c = r.get(LLM_JUDGE_LEAD), align.get(a, {}).get("objective_assessment_similarity")
                    if isinstance(t, (int, float)) and isinstance(c, (int, float)):
                        slot = acc.setdefault(a, {}).setdefault(sid, {"t": [], "c": []})
                        slot["t"].append(float(t))
                        slot["c"].append(float(c))
        out[label] = {
            a: [(sum(v["t"]) / len(v["t"]), sum(v["c"]) / len(v["c"]))
                for v in by_sid.values()]
            for a, by_sid in acc.items()
        }
    return out


def fig_alignment_vs_llm_judge_scatter(pairs: dict, agents: list[str], outdir: Path,
                           written: list[Path]) -> bool:
    labels = sorted(pairs, key=size_of_label)
    labels = [lb for lb in labels if any(pairs[lb].get(a) for a in agents)]
    if not labels:
        return False
    fig, axes = plt.subplots(1, len(labels), figsize=(7.0, 2.4),
                             sharex=True, sharey=True)
    axes = [axes] if len(labels) == 1 else list(axes)
    for ax, lb in zip(axes, labels):
        all_t, all_c, within = [], [], []
        for a in agents:
            pts = pairs[lb].get(a, [])
            if not pts:
                continue
            ts, cs = zip(*pts)
            all_t += list(ts)
            all_c += list(cs)
            if len(pts) >= 10:
                within.append(spearman_rho(list(ts), list(cs)))
            ax.scatter(ts, cs, s=7, alpha=0.45, linewidths=0,
                       color=AGENT_COLOR.get(a, "#666666"),
                       marker=point_marker(a),
                       zorder=5 if a == PROPOSED else 3)
        # The pooled rho mixes within- and between-agent variation and is
        # dominated by the latter (the agent clusters sit apart), so its scope
        # is named and the within-agent view is printed beside it.
        rho = spearman_rho(all_t, all_c)
        med = median(within)
        txt = (f"pooled $\\rho_s$ = {rho:.2f}\n"
               f"n = {len(all_t)} (agent-scen.)")
        if not math.isnan(med):
            txt += f"\nwithin-agent med. = {med:.2f}"
        ax.set_title(model_display(lb), fontsize=8)
        ax.text(0.04, 0.97, txt, transform=ax.transAxes, va="top",
                fontsize=6.0, color="#333333", zorder=8)
        ax.set_xlabel("ADDIE rubric (LLM judge, /100)")
        ax.grid(axis="x", visible=False)
    axes[0].set_ylabel("Objective$\\to$assessment similarity")
    agent_legend(fig, agents, bbox_to_anchor=(0.5, -0.06))
    fig.text(0.5, -0.30,
             "Pooled $\\rho_s$ is a between-agent correlation: every agent forms its own "
             "cluster, so it is not a per-scenario convergent-validity estimate.\n"
             "\"within-agent med.\" = median of the per-agent Spearman "
             f"$\\rho_s$ ({len(agents)} agents), the per-scenario view.",
             ha="center", va="top", fontsize=6.5, color="#555555")
    fig.tight_layout()
    save(fig, outdir, "fig_alignment_vs_llm_judge_scatter", written)
    return True


def fig_failure_rate(pooled: dict, outdir: Path, written: list[Path]) -> None:
    models = pooled["models"]
    agents = agents_in(pooled)
    n_agents = len(agents)
    width = 0.8 / n_agents

    fig, ax = plt.subplots(figsize=(7.0, 2.8))
    zero_everywhere: dict[str, bool] = {}
    for ai, a in enumerate(agents):
        xs, ys, err_lo, err_hi = [], [], [], []
        for mi, m in enumerate(models):
            denom = m.get("n_scenarios_union") or 1
            rates = [100.0 * info["missing_by_agent"].get(a, 0) / denom
                     for info in m["per_run"]]
            mean = sum(rates) / len(rates) if rates else 0.0
            xs.append(mi + (ai - (n_agents - 1) / 2) * width)
            ys.append(mean)
            err_lo.append(mean - min(rates, default=0.0))
            err_hi.append(max(rates, default=0.0) - mean)
        zero_everywhere[a] = all(y == 0 for y in ys) and all(h == 0 for h in err_hi)
        bars = ax.bar(xs, ys, width=width * 0.92, color=AGENT_COLOR.get(a, "#666666"),
                      yerr=[err_lo, err_hi], error_kw={"elinewidth": 0.7, "capsize": 1.5},
                      zorder=3)
        for rect, y, hi in zip(bars, ys, err_hi):
            if y > 0:
                ax.annotate(f"{y:.1f}", xy=(rect.get_x() + rect.get_width() / 2, y + hi),
                            xytext=(0, 3), textcoords="offset points",
                            ha="center", fontsize=6, color="#333333")
    ax.set_xticks(range(len(models)))
    ax.set_xticklabels([model_display(m['label']) for m in models])
    ax.set_ylabel("Failed scenarios (%)")
    ax.set_ylim(bottom=0)
    ax.grid(axis="x", visible=False)
    ax.set_title("Scenarios with no scorable output "
                 "(mean of runs; whiskers: min–max across runs)", fontsize=8)
    # bar chart ⇒ patch handles: the shared line legend would advertise dashes
    # and markers that appear nowhere in the plot
    bar_legend(fig, agents,
               labels={a: f"{AGENT_DISPLAY.get(a, a)} (0% at every size)"
                       for a, z in zero_everywhere.items() if z},
               bbox_to_anchor=(0.5, -0.04))
    save(fig, outdir, "fig_failure_rate", written)


def fig_cost_quality(pooled: dict, outdir: Path, written: list[Path]) -> bool:
    tok = pooled.get("token_usage") or {}
    if not tok.get("models"):
        return False
    models = [m for m in pooled["models"] if m["label"] in tok["models"]]
    agents = agents_in(pooled)
    size_ms = [3.5, 5, 6.5, 8.5]  # marker size grows with model size

    # Tokens only: execution time reflects serving load/API latency, not the
    # method, so it is deliberately not plotted.
    fig, ax = plt.subplots(figsize=(4.6, 3.2))
    partial_seen = False
    for a in agents:
        xs, ys, notes = [], [], []
        for m in models:
            cell = tok["models"][m["label"]].get(a, {}).get("total_tokens", {})
            summary = m["agents"].get(a, {})
            xs.append(_nan(cell.get("mean")))
            ys.append(_nan(summary.get(LLM_JUDGE_LEAD_FIELD)))
            # the two coordinates are averaged over different scenario sets
            # (tokens over runs with metadata, ADDIE over the complete-case
            # set); flag the markers where they diverge badly
            n_tok, n_add = cell.get("n_scenarios"), summary.get("n_scenarios_complete")
            union = m.get("n_scenarios_union") or 0
            thin = (union and isinstance(n_tok, int) and isinstance(n_add, int)
                    and min(n_tok, n_add) < 0.5 * union)
            notes.append(f"n={n_add}/{n_tok}" if thin else None)
        kw = line_kw(a)
        ax.plot(xs, ys, alpha=0.9, color=kw["color"], marker="",
                linewidth=0.9 if a != PROPOSED else 1.6, zorder=kw["zorder"])
        for x, y, ms, note in zip(xs, ys, size_ms, notes):
            ax.plot([x], [y], marker=point_marker(a), markersize=ms,
                    color=kw["color"] if note is None else "white",
                    markerfacecolor=kw["color"] if note is None else "white",
                    markeredgecolor="white" if note is None else kw["color"],
                    markeredgewidth=0.6 if note is None else 1.2,
                    zorder=kw["zorder"] + 1)
            if note:
                partial_seen = True
                # to the side, not below: these points sit on the axis floor
                ax.annotate(note, xy=(x, y), xytext=(7, -5),
                            textcoords="offset points", ha="left", va="center",
                            fontsize=5.5, color=kw["color"])
    ax.set_xscale("log")
    ax.set_xlabel("Mean total tokens per scenario")
    ax.grid(axis="x", visible=False)
    ax.set_ylabel("ADDIE rubric (/100)")
    if partial_seen:
        # below the legend: the data area has no free corner at the small sizes,
        # which is exactly where the flagged markers are
        fig.text(0.5, -0.20,
                 "Hollow marker: the two coordinates are averaged over different "
                 "partial scenario sets\n(n = ADDIE complete-case / scenarios with "
                 "token metadata), so the point is not a property\nof one common "
                 "scenario set.",
                 ha="center", va="top", fontsize=6.5, color="#555555")
    fig.suptitle("Quality vs token cost — marker size grows with model size "
                 f"({', '.join(size_display(m['label']) for m in models)})", fontsize=8)
    agent_legend(fig, agents, bbox_to_anchor=(0.5, -0.04))
    fig.tight_layout(rect=(0, 0, 1, 0.96))
    save(fig, outdir, "fig_cost_quality", written)
    return True


def run(*, pooled_path: Path | None = None, outdir: Path | None = None,
        runs_glob: str | None = None, quiet: bool = False) -> list[Path]:
    """Draw every figure. Returns the paths written.

    A figure whose input layer is absent is SKIPPED with a message naming what
    was missing, never drawn from nothing: an empty axis in a paper reads as a
    result rather than as an unrun step.
    """
    from .. import schema

    src = pooled_path or (paths.results_root() / "pooled_comparison.json")
    pooled = schema.load(src)
    out = outdir or paths.figures_dir()
    out.mkdir(parents=True, exist_ok=True)

    agents = agents_in(pooled)
    written: list[Path] = []

    fig_llm_judge_ladder(pooled, out, written)
    fig_llm_judge_delta(pooled, out, written)
    fig_llm_judge_components(pooled, out, written)

    for builder, layer in ((fig_alignment_ladder, "alignment data"),
                           (fig_alignment_components, "alignment data"),
                           (fig_alignment_forest, "alignment stats")):
        if not builder(pooled, out, written) and not quiet:
            print(f"! no {layer} in the pooled JSON — skipped {builder.__name__}")

    # The scatter is per-SCENARIO, so it needs the run dirs rather than the
    # pooled summary; without them it is skipped rather than approximated.
    if runs_glob:
        pairs = collect_scenario_pairs(runs_glob, agents)
        if not fig_alignment_vs_llm_judge_scatter(pairs, agents, out, written) and not quiet:
            print("! no per-scenario alignment data under the run glob — skipped scatter")
    elif not quiet:
        print("- fig_alignment_vs_llm_judge_scatter skipped (pass a run glob to enable)")

    fig_failure_rate(pooled, out, written)
    if not fig_cost_quality(pooled, out, written) and not quiet:
        print("! no token_usage in the pooled JSON — skipped fig_cost_quality")

    if not quiet:
        for path in written:
            print(f"wrote {path}")
    return written

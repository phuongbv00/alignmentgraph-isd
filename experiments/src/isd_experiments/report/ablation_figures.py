"""Figures for the 2x2 ablation.

Every value drawn is descriptive: a cell mean per arm (failure = 0) or a
factorial effect with its bootstrap interval. The ablation's tests are the
registered ones, reported in ``tab_ablation``; no figure marks significance.
"""

from __future__ import annotations

import math
from pathlib import Path

from .. import paths
from ..latex import model_display, size_of_label
from ..plots import _nan, plt, save, sized_axis
from .figures import PANEL_COMPONENTS, PANEL_FAMILY_A_N

PRODUCER = "isd-exp report ablation-figures"

# All four arms (A0 included), in legend order.
ARM_ORDER = [
    "alignmentgraph-isd",
    "alignmentgraph-isd-single-graph",
    "alignmentgraph-isd-multi-prose",
    "alignmentgraph-isd-single-prose",
]
#: Same arm names as ``ablation_tables.ARM_DISPLAY`` — figure legends
#: and table rows come from the same pooled file and must read alike.
ARM_DISPLAY_FULL = {
    "alignmentgraph-isd": "A0 — Multi-agent, graph context",
    "alignmentgraph-isd-single-prose": "A1 — Single-agent, prose context",
    "alignmentgraph-isd-single-graph": "A2 — Single-agent, graph context",
    "alignmentgraph-isd-multi-prose": "A3 — Multi-agent, prose context",
}
ARM_COLOR_FULL = {
    "alignmentgraph-isd": "#0048B0",           # blue (full — emphasized)
    "alignmentgraph-isd-single-graph": "#d62728",
    "alignmentgraph-isd-multi-prose": "#1f77b4",
    "alignmentgraph-isd-single-prose": "#7f7f7f",
}
ARM_LS_FULL = {
    "alignmentgraph-isd": "-",
    "alignmentgraph-isd-single-graph": "-",
    "alignmentgraph-isd-multi-prose": "--",
    "alignmentgraph-isd-single-prose": ":",
}


def _panel_cells(pooled: dict, signal: str) -> dict[str, dict]:
    """label -> {"n": scenarios, "means": {arm: mean}} for one factorial measure.

    The per-arm means are the factorial's cell means: failure = 0, over the
    scenarios on which all four arms were scored, so the arms of one size are
    always compared on the same scenarios."""
    fact = pooled.get("factorial") or {}
    blk = (fact.get("measures") or {}).get(signal) or {}
    cells = fact.get("cells") or {}
    out = {}
    for e in blk.get("per_model") or []:
        means = e.get("cell_means") or {}
        if not e.get("n_scenarios") or not means:
            continue
        out[e["label"]] = {"n": e["n_scenarios"],
                           "means": {agent: means.get(key) for key, agent in cells.items()}}
    return out


def _ordered_labels(pooled: dict, by_label: dict) -> list[str]:
    return [m["label"] for m in pooled["models"] if m["label"] in by_label]


def fig_ablation_align_ladder(pooled: dict, outdir: Path, written: list[Path]) -> bool:
    """Objective->assessment similarity per arm vs size —
    the ablation analogue of fig_alignment_ladder."""
    signal = "objective_assessment_similarity"
    by_label = _panel_cells(pooled, signal)
    labels = _ordered_labels(pooled, by_label)
    if not labels:
        return False
    sizes = [size_of_label(lb) for lb in labels]
    fig, ax = plt.subplots(figsize=(5.9, 3.2))
    for arm in ARM_ORDER:
        ys = [_nan(by_label[lb]["means"].get(arm)) for lb in labels]
        proposed = arm == "alignmentgraph-isd"
        ax.plot(sizes, ys, color=ARM_COLOR_FULL[arm],
                linestyle=ARM_LS_FULL[arm],
                linewidth=2.4 if proposed else 1.5,
                marker="D" if proposed else "o", markersize=5.5 if proposed else 4.5,
                markeredgecolor="white", markeredgewidth=0.6,
                zorder=5 if proposed else 3, label=ARM_DISPLAY_FULL[arm])
    sized_axis(ax, sizes, labels)
    ax.set_ylabel("Objective$\\to$assessment similarity (0–1)")
    ax.set_title("Ablation: objective$\\to$assessment similarity per arm across model sizes",
                 fontsize=8.5)
    # outside the data area: loc="best" dropped the key onto the A2/A3 series,
    # which were then drawn through the labels
    ax.legend(loc="upper left", bbox_to_anchor=(1.01, 1.0), frameon=False, fontsize=7)
    fig.text(0.5, -0.03, f"Mean over scenarios, failure = 0 ({_n_text(by_label)}); "
             "descriptive.", ha="center", va="top", fontsize=6.5, color="#555555")
    save(fig, outdir, "fig_ablation_ladder", written)
    return True


def _n_text(by_label: dict) -> str:
    """'n = 30 scenarios per size', read from the data, never typed."""
    ns = sorted({v["n"] for v in by_label.values() if isinstance(v.get("n"), int)})
    if not ns:
        return "n per size: see pooled JSON"
    if len(ns) == 1:
        return f"n = {ns[0]} scenarios per size"
    return f"n = {ns[0]}–{ns[-1]} scenarios per size"


#: In-figure disclosure for the ablation panel heatmap: the two instrument
#: families and what a cell is, since a figure gets read detached from its
#: caption.
ABL_PANEL_FOOTNOTE = (
    "Flat panel of 6 alignment signals, no primary endpoint. Family A = the three edges of the "
    "constructive-alignment triad (textual correspondence, rectified cosine "
    "max(0, cos) on [0,1]): Obj→Asm, Obj→Act, Act→Asm.  "
    "Family B (cognitive demand, Bloom-derived, no similarity): Cognitive congruence, "
    "Porter (mean of 3 pairwise indices), Webb.\n"
    "Cell = mean over the scenarios on which all four arms were scored, failure = 0 "
    "({n}); leading zero omitted. Descriptive."
)


def fig_ablation_components(pooled: dict, outdir: Path, written: list[Path]) -> bool:
    """Per-signal heatmap (arm x panel signal) per model size — the ablation
    analogue of fig_alignment_components."""
    comp_keys = [k for k, _ in PANEL_COMPONENTS]
    comp_names = [n for _, n in PANEL_COMPONENTS]
    per_signal = {k: _panel_cells(pooled, k) for k in comp_keys}
    labels = [lb for lb in _ordered_labels(pooled, per_signal[comp_keys[0]])
              if any(lb in per_signal[k] for k in comp_keys)]
    if not labels:
        return False
    n_arm = len(ARM_ORDER)
    # figure width per panel matches fig_alignment_components: narrow columns
    # need the room, otherwise the cell values merge into one digit run
    fig, axes = plt.subplots(
        1, len(labels),
        figsize=(3.05 * len(labels) + 1.6, 1.9 + 0.38 * n_arm), sharey=True)
    axes = [axes] if len(labels) == 1 else list(axes)
    cmap = plt.get_cmap("Blues")
    last_im = None
    for ax, lb in zip(axes, labels):
        grid = [[_nan(((per_signal[k].get(lb) or {}).get("means") or {}).get(arm))
                 for k in comp_keys] for arm in ARM_ORDER]
        last_im = ax.imshow(grid, cmap=cmap, vmin=0.0, vmax=1.0, aspect="auto")
        for i, r in enumerate(grid):
            for j, v in enumerate(r):
                if math.isnan(v):
                    continue
                txt = f"{v:.2f}"
                ax.text(j, i, txt[1:] if 0 <= v < 1 else txt,
                        ha="center", va="center", fontsize=6.5,
                        color="white" if v > 0.55 else "#333333")
        ax.axvline(PANEL_FAMILY_A_N - 0.5, color="white", linewidth=2.0, zorder=4)
        ax.set_title(model_display(lb))
        ax.set_xticks(range(len(comp_names)))
        ax.set_xticklabels(comp_names, rotation=35, ha="right", fontsize=7.5)
        ax.grid(visible=False)
        ax.tick_params(length=0)
        for sp in ax.spines.values():
            sp.set_visible(False)
    axes[0].set_yticks(range(n_arm))
    axes[0].set_yticklabels(
        [ARM_DISPLAY_FULL[a] for a in ARM_ORDER], fontsize=8)
    cbar = fig.colorbar(last_im, ax=axes, fraction=0.02, pad=0.02)
    cbar.ax.tick_params(labelsize=6.5)
    cbar.set_label("Panel signal mean (0–1)", fontsize=7)
    fig.text(0.5, -0.07, ABL_PANEL_FOOTNOTE.format(n=_n_text(per_signal[comp_keys[0]])),
             ha="center", va="top", fontsize=6.5, color="#555555", linespacing=1.5)
    save(fig, outdir, "fig_ablation_components", written)
    return True


#: Signal the factorial figure leads on (see ``ablation_tables.FACT_LEAD``).
FACT_LEAD = "objective_assessment_similarity"

#: (effect key, condition label) pairs per panel — each panel shows ONE
#: mechanism's effect under both states of the other mechanism.
FACT_PANELS = [
    ("Decomposition", [("decomposition_effect_given_context_graph", "context = graph", "#0048B0"),
                       ("decomposition_effect_given_context_prose", "context = prose", "#C42D00")]),
    ("Context representation", [("context_effect_given_decomposition_multi", "decomposition = multi", "#0048B0"),
                                ("context_effect_given_decomposition_single", "decomposition = single", "#C42D00")]),
]


def fig_ablation_factorial(pooled: dict, outdir: Path, written: list[Path]) -> bool:
    """Each mechanism's effect under both states of the other one.

    Two lines per panel, one per state of the other mechanism; the gap between
    them IS the interaction, whatever the sign of either effect.
    Descriptive, with the bootstrap interval of each effect.
    """
    fact = pooled.get("factorial") or {}
    if "skipped" in fact or FACT_LEAD not in (fact.get("measures") or {}):
        return False
    per_model = [e for e in fact["measures"][FACT_LEAD]["per_model"] if e.get("n_scenarios")]
    if not per_model:
        return False
    labels = [e["label"] for e in per_model]
    sizes = [size_of_label(lb) for lb in labels]

    fig, axes = plt.subplots(1, 2, figsize=(6.2, 3.5), sharey=True)
    for ax, (mech, series) in zip(axes, FACT_PANELS):
        ax.axhline(0.0, color="#444444", linewidth=0.8, zorder=2)
        for key, cond, color in series:
            xs, ys, lo_err, hi_err = [], [], [], []
            for e, size in zip(per_model, sizes):
                d = e.get(key) or {}
                if not d.get("n"):
                    continue
                xs.append(size)
                ys.append(d["mean_diff"])
                lo_err.append(d["mean_diff"] - d["ci95"][0])
                hi_err.append(d["ci95"][1] - d["mean_diff"])
            if not xs:
                continue
            ax.errorbar(xs, ys, yerr=[lo_err, hi_err], color=color,
                        linewidth=1.8, capsize=2.5, elinewidth=0.9,
                        marker="o", markersize=5.0, markeredgecolor=color,
                        zorder=4, label=cond)
        sized_axis(ax, sizes, labels)
        ax.set_title(f"Effect of {mech}", fontsize=8.5)
        ax.legend(loc="best", frameon=False, fontsize=7)
    axes[0].set_ylabel("Δ objective→assessment similarity\n(paired per scenario)")
    # Short, wrapped, centred: a one-line footnote wider than the axes sets the
    # tight bounding box and halves the panels once the figure is scaled to a
    # paper column. n is read from the data, never typed.
    by_label = {e["label"]: {"n": e.get("n_scenarios")} for e in per_model}
    fig.text(
        0.5, -0.03,
        "Error bar = bootstrap 95% CI; failure = 0; descriptive, no test\n"
        f"(the registered tests are in tab_ablation; {_n_text(by_label)}).",
        ha="center", va="top", fontsize=6.5, color="#555555",
    )
    fig.tight_layout()
    save(fig, outdir, "fig_ablation_factorial", written)
    return True


def fig_ablation(pooled: dict, outdir: Path, written: list[Path]) -> bool:
    """Each arm's mean ADDIE per size (failure = 0), the figure form of the
    cell block of ``tab_ablation``. Error bar = SEM across scenarios."""
    models = pooled["models"]
    a0 = pooled["config"]["reference"]
    labels = [m["label"] for m in models]
    sizes = [size_of_label(lb) for lb in labels]
    order = [a for a in ARM_ORDER if a in {a0, *pooled["config"]["arms"]}]

    fig, ax = plt.subplots(figsize=(5.4, 3.0))
    drawn = False
    for arm in order:
        xs, ys, errs = [], [], []
        for m, size in zip(models, sizes):
            s = m["agents"].get(arm) or {}
            mean, sd, n = s.get("mean_addie"), s.get("sd_addie_across_scenarios"), \
                s.get("n_scenarios")
            if math.isnan(_nan(mean)):
                continue
            xs.append(size)
            ys.append(mean)
            errs.append(sd / math.sqrt(n) if isinstance(sd, (int, float))
                        and isinstance(n, int) and n > 0 else 0.0)
        if not xs:
            continue
        drawn = True
        proposed = arm == a0
        ax.errorbar(xs, ys, yerr=errs, color=ARM_COLOR_FULL.get(arm, "#666666"),
                    linestyle=ARM_LS_FULL.get(arm, "-"),
                    linewidth=2.2 if proposed else 1.5, capsize=2.5, elinewidth=0.9,
                    marker="D" if proposed else "o", markersize=5.5 if proposed else 4.5,
                    markeredgecolor="white", markeredgewidth=0.6,
                    zorder=5 if proposed else 3, label=ARM_DISPLAY_FULL.get(arm, arm))
    if not drawn:
        plt.close(fig)
        return False
    sized_axis(ax, sizes, labels)
    ax.set_ylabel("Mean ADDIE (/100), failure = 0")
    ax.set_title("Ablation: mean ADDIE per arm across model sizes", fontsize=8.5)
    ax.legend(loc="upper left", bbox_to_anchor=(1.01, 1.0), frameon=False, fontsize=7)
    fig.text(
        0.5, -0.04,
        "Error bar = SEM across scenarios; a scenario with no scorable output counts 0.\n"
        "Descriptive; the registered tests (H-D, H-S) are in tab_ablation.",
        ha="center", va="top", fontsize=6.5, color="#555555",
    )
    save(fig, outdir, "fig_ablation", written)
    return True


def run(*, pooled_path: Path | None = None, outdir: Path | None = None,
        quiet: bool = False) -> list[Path]:
    from .. import schema

    src = pooled_path or (paths.results_root() / "pooled_ablation.json")
    if not src.exists():
        if not quiet:
            print(f"- no {src.name} — skipped. Produce it with:  {paths.cli()} pool ablation")
        return []
    pooled = schema.load(src)
    out = outdir or paths.figures_dir()
    out.mkdir(parents=True, exist_ok=True)

    written: list[Path] = []
    for builder, layer in ((fig_ablation, "arm means"),
                           (fig_ablation_factorial, "factorial layer"),
                           (fig_ablation_align_ladder, "alignment data in the factorial"),
                           (fig_ablation_components, "alignment data in the factorial")):
        if not builder(pooled, out, written) and not quiet:
            print(f"! no {layer} in the pooled JSON — skipped {builder.__name__}")
    if not quiet:
        for path in written:
            print(f"wrote {path}")
    return written

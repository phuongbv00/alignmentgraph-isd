"""Tables for the 2x2 ablation.

Two sign conventions live here and are labelled at every use, because they are
opposites and a reader who mixes them reads every result backwards:

* **arm - reference**: how much worse an ablated arm is.
* **component ON - OFF**: what a mechanism contributes.
"""

from __future__ import annotations

import json
import math
from datetime import datetime
from pathlib import Path

from .. import paths
from ..config import LLM_JUDGE_SCORES
from ..config import current as current_config
from ..latex import fmt_num, fmt_p, header_comment, model_display, size_display, size_of_label, size_word

PRODUCER = "isd-exp report ablation-tables"




def _size_word(label: str, index: int) -> str:
    return size_word(label, index, current_config().macro_words)



ARM_DISPLAY = {
    "alignmentgraph-isd": "A0 — Multi-agent, graph context",
    "alignmentgraph-isd-single-prose": "A1 — Single-agent, prose context",
    "alignmentgraph-isd-single-graph": "A2 — Single-agent, graph context",
    "alignmentgraph-isd-multi-prose": "A3 — Multi-agent, prose context",
}
# digit-free macro words per arm (LaTeX macro names cannot contain digits)
ARM_WORDS = {
    "alignmentgraph-isd-single-prose": "SingleProse",
    "alignmentgraph-isd-single-graph": "SingleGraph",
    "alignmentgraph-isd-multi-prose": "MultiProse",
}
SIZE_WORDS = {0.8: "ZeroEightB", 2.0: "TwoB", 4.0: "FourB", 9.0: "NineB"}
FALLBACK_WORDS = ["SizeA", "SizeB", "SizeC", "SizeD", "SizeE", "SizeF"]


# ── formatting (same conventions as tables.py) ───────────────────────────────











def stars(p: float) -> str:
    if p is None or (isinstance(p, float) and math.isnan(p)):
        return ""
    if p < 0.001:
        return "$^{***}$"
    if p < 0.01:
        return "$^{**}$"
    if p < 0.05:
        return "$^{*}$"
    return ""


#: Star legend, emitted as a table footnote so captions stay short.
STAR_LEGEND = "$^{*}p<0.05$; $^{**}p<0.01$; $^{***}p<0.001$"


def n_clause(entries: list[dict]) -> str:
    """'n=90' when every entry shares one scenario count, else a pointer.

    Never hard-code the sample size in a caption: if a scenario ever became
    unscorable the cells would move while a typed caption silently lied.
    """
    ns = {e.get("n_scenarios") for e in entries if e.get("n_scenarios")}
    if len(ns) == 1:
        return f"n={ns.pop()}"
    return "$n$ per size in stats\\_ablation.md"




# ── helpers over the pooled structure ────────────────────────────────────────

def comparison_row(model: dict, arm: str) -> dict:
    """complete_case comparison row (A0 − arm) for one arm, or {}."""
    for row in (model.get("comparisons", {}).get("by_score", {})
                .get("addie_median", {}).get("policies", {})
                .get("complete_case", [])):
        if row.get("baseline") == arm:
            return row
    return {}


def arm_delta(model: dict, arm: str) -> dict:
    """Delta in TABLE direction: arm − A0 (negative = removal hurts)."""
    row = comparison_row(model, arm)
    if not row.get("n"):
        return {}
    return {
        "n": row["n"],
        "delta": -row["mean_diff"],
        "ci95": [-row["ci95"][1], -row["ci95"][0]],
        "p_holm": row.get("p_holm"),
        "rank_biserial_r": row.get("rank_biserial_r"),
    }


# ── outputs ──────────────────────────────────────────────────────────────────

def gen_tab_ablation(pooled: dict) -> str:
    models = pooled["models"]
    a0 = pooled["config"]["reference"]
    arms = pooled["config"]["arms"]

    colspec = "@{}l" + "r@{\\hskip 4pt}r" * len(models) + "@{}"
    lines = [header_comment(pooled, "tab_ablation.tex — ablation arms x model sizes")]
    lines.append("\\begin{table*}[t]")
    lines.append(
        "  \\caption{Ablation across model sizes. Each cell: mean ADDIE"
        " (/100, complete-case) and $\\Delta$ = arm $-$ A0 (negative = removal"
        " lowered ADDIE, positive = raised it). Wilcoxon, Holm over the"
        f" {len(arms)} arms per size.}}")
    lines.append("  \\label{tab:ablation}")
    lines.append("  \\small")
    lines.append(f"  \\begin{{tabular}}{{{colspec}}}")
    lines.append("    \\toprule")
    heads = " & ".join(
        f"\\multicolumn{{2}}{{c}}{{{model_display(m['label'])}}}" for m in models)
    lines.append(f"    & {heads} \\\\")
    cmids = "".join(
        f"\\cmidrule(lr){{{2 + 2 * i}-{3 + 2 * i}}}" for i in range(len(models)))
    lines.append(f"    {cmids}")
    subs = " & ".join(["ADDIE", "$\\Delta$ vs A0"] * len(models))
    lines.append(f"    Arm & {subs} \\\\")
    lines.append("    \\midrule")
    for arm in [a0] + arms:
        name = ARM_DISPLAY.get(arm, arm)
        if arm == a0:
            name = f"\\textbf{{{name}}}"
        cells = []
        for m in models:
            s = m["agents"].get(arm)
            if not s or s.get("mean_addie") is None or math.isnan(s["mean_addie"]):
                cells += ["--", "--"]
                continue
            total = fmt_num(s["mean_addie"])
            if arm == a0:
                cells += [f"\\textbf{{{total}}}", "--"]
                continue
            d = arm_delta(m, arm)
            if not d:
                cells += [total, "--"]
                continue
            cells += [total, f"{fmt_num(d['delta']).replace('-', '$-$')}{stars(d['p_holm'])}"]
        lines.append(f"    {name} & " + " & ".join(cells) + " \\\\")
    lines.append("    \\bottomrule")
    lines.append("  \\end{tabular}")
    lines.append(
        f"  \\par\\smallskip\\footnotesize {STAR_LEGEND} (Holm-corrected)."
        " Bootstrap 95\\% CI and per-scenario $n$ for every $\\Delta$:"
        " see stats\\_ablation.md, generated together with this table.")
    lines.append("\\end{table*}")
    return "\n".join(lines) + "\n"


#: Signal the factorial table leads on: the decomposition/context effects are
#: expected as alignment effects, not LLM judge effects (on ADDIE nothing may
#: reach significance), so the table is built on the alignment signal and
#: ADDIE is reported beside it.
FACT_LEAD = "objective_assessment_similarity"


def _fx(model_entry: dict, key: str) -> dict:
    return model_entry.get(key) or {}


def gen_tab_factorial(pooled: dict) -> str:
    """The 2x2 read: simple effects of each mechanism + their interaction.

    The arm-vs-A0 table answers "what does removing this cost?", which is a
    main-effects question. It cannot show that a mechanism is idle only because
    the other one already did the work — that is an interaction, and the four
    arms are a complete 2x2, so it is directly estimable.
    """
    fact = pooled.get("factorial") or {}
    if "skipped" in fact or not fact.get("measures"):
        return (header_comment(pooled, "tab_ablation_factorial.tex — placeholder")
                + "% No factorial layer in pooled_ablation.json (arms missing).\n")
    per_model = fact["measures"][FACT_LEAD]["per_model"]

    lines = [header_comment(pooled, "tab_ablation_factorial.tex — 2x2 simple effects + interaction")]
    lines.append("\\begin{table}[t]")
    lines.append(
        "  \\caption{$2\\times2$ read (decomposition $\\times$ context"
        " representation) on \\texttt{objective\\_assessment\\_similarity}."
        " Each cell: paired difference, multi-agent $-$ single-agent"
        f" decomposition ({n_clause(per_model)}); positive favours the"
        " multi-agent 5-Designer pipeline. Interaction = col.~1 $-$ col.~2."
        " Wilcoxon, uncorrected.}")
    lines.append("  \\label{tab:ablation-factorial}")
    lines.append("  \\small")
    lines.append("  \\begin{tabular}{@{}lrrr@{}}")
    lines.append("    \\toprule")
    lines.append("    Size & Decomp $|$ ctx=graph & Decomp $|$ ctx=prose"
                 " & Interaction \\\\")
    lines.append("    \\midrule")
    for e in per_model:
        cells = []
        for key in ("decomposition_effect_given_context_graph",
                    "decomposition_effect_given_context_prose", "interaction"):
            d = _fx(e, key)
            if not d.get("n"):
                cells.append("--")
                continue
            cells.append(f"{fmt_num(d['mean_diff'], 3).replace('-', '$-$')}"
                         f"{stars(d.get('p_raw'))}")
        lines.append(f"    {size_display(e['label'])} & " + " & ".join(cells) + " \\\\")
    lines.append("    \\bottomrule")
    lines.append("  \\end{tabular}")
    lines.append(
        f"  \\par\\smallskip\\footnotesize {STAR_LEGEND}, \\emph{{uncorrected}}"
        " --- unlike the Holm-corrected stars of Table~\\ref{tab:ablation}."
        " Bootstrap 95\\% CI of every cell: see stats\\_ablation.md.")
    lines.append("\\end{table}")
    return "\n".join(lines) + "\n"


#: Short display names for the factorial appendix table. Same labels as
#: tables.py uses: the dagger marks the non-directional signal, and
#: porter_mean is the MEAN of the three pairwise Porter indices, not one index.
FACT_SIGNAL_DISPLAY = {
    "addie_median": "ADDIE",
    "trajectory_score": "Trajectory",
    "total_score": "Total (composite)",
    "objective_assessment_similarity": "Obj$\\to$Asm sim.",
    "objective_activity_similarity": "Obj$\\to$Act sim.",
    "activity_assessment_similarity": "Act$\\to$Asm sim.",
    "objective_cognitive_congruence": "Cognitive congruence",
    "porter_mean": "Mean Porter index",
    "webb_bloom_consistency": "Webb consistency",
}

SCALE_BLOCKS = (
    ("LLM judge scores (rubric points out of 100)", True),
    ("Alignment signals (0--1)", False),
)


def gen_tab_factorial_full(pooled: dict) -> str:
    """Every signal x every size — the appendix version of the 2x2 read.

    The main-text table leads on one signal because a slide or a results
    paragraph cannot carry ten. The claim being made (that the two mechanisms
    substitute for each other) is a claim about the design, so it has to be
    checkable on every signal the study reports, not on the one that shows it
    most cleanly. This table is that check.

    The two row blocks are on different scales (rubric points vs [0,1]) and are
    labelled as such: nothing in this table licenses comparing the magnitude of
    an LLM judge cell with the magnitude of a panel cell.
    """
    fact = pooled.get("factorial") or {}
    if "skipped" in fact or not fact.get("measures"):
        return (header_comment(pooled, "tab_ablation_factorial_full.tex — placeholder")
                + "% No factorial layer in pooled_ablation.json (arms missing).\n")
    signals = fact["measures"]
    labels = [e["label"] for e in next(iter(signals.values()))["per_model"]]
    all_entries = [e for blk in signals.values() for e in blk["per_model"]]

    lines = [header_comment(
        pooled, "tab_ablation_factorial_full.tex — 2x2 read on every reported signal")]
    lines.append("\\begin{table*}[t]")
    lines.append(
        "  \\caption{$2\\times2$ read on every reported signal. Each cell:"
        f" paired difference, multi-agent $-$ single-agent decomposition"
        f" ({n_clause(all_entries)}); D$|$ctx = decomposition effect with"
        " context representation graph/prose, $\\times$ = col.~1 $-$ col.~2."
        " Row blocks differ in scale; magnitudes are not comparable across"
        " them.}")
    lines.append("  \\label{tab:ablation-factorial-full}")
    lines.append("  \\scriptsize")
    colspec = "@{}l" + "rrr" * len(labels) + "@{}"
    lines.append(f"  \\begin{{tabular}}{{{colspec}}}")
    lines.append("    \\toprule")
    heads = " & ".join(
        f"\\multicolumn{{3}}{{c}}{{{model_display(lb)}}}" for lb in labels)
    lines.append(f"    & {heads} \\\\")
    cmids = "".join(f"\\cmidrule(lr){{{2 + 3 * i}-{4 + 3 * i}}}" for i in range(len(labels)))
    lines.append(f"    {cmids}")
    subs = " & ".join(["D$|$ctx=graph", "D$|$ctx=prose", "$\\times$"] * len(labels))
    lines.append(f"    Signal & {subs} \\\\")
    lines.append("    \\midrule")
    ncols = 1 + 3 * len(labels)
    for block_i, (block_name, is_judge) in enumerate(SCALE_BLOCKS):
        block_sigs = [s for s in signals if (s in LLM_JUDGE_SCORES) == is_judge]
        if not block_sigs:
            continue
        if block_i:
            lines.append("    \\addlinespace")
        lines.append(f"    \\multicolumn{{{ncols}}}{{@{{}}l}}"
                     f"{{\\emph{{{block_name}}}}} \\\\")
        for sig in block_sigs:
            per = {e["label"]: e for e in signals[sig]["per_model"]}
            cells = []
            for lb in labels:
                e = per.get(lb, {})
                for key in ("decomposition_effect_given_context_graph",
                            "decomposition_effect_given_context_prose", "interaction"):
                    d = e.get(key) or {}
                    cells.append("--" if not d.get("n") else
                                 f"{fmt_num(d['mean_diff'], 3).replace('-', '$-$')}"
                                 f"{stars(d.get('p_raw'))}")
            name = FACT_SIGNAL_DISPLAY.get(sig, sig.replace("_", "\\_"))
            lines.append(f"    {name} & " + " & ".join(cells) + " \\\\")
    lines.append("    \\bottomrule")
    lines.append("  \\end{tabular}")
    lines.append(
        f"  \\par\\smallskip\\footnotesize {STAR_LEGEND}, \\emph{{uncorrected}}."
        " $^{\\dagger}$ = non-directional diagnostic."
        " $\\times$ is computed at full precision, so it need not equal the"
        " difference of the two rounded cells beside it."
        " A negative $\\times$ means the two mechanisms substitute for each"
        " other only where both simple effects carry the beneficial sign; where"
        " they are negative (Trajectory, Total) read $\\times$ as multi-agent"
        " decomposition costing less when graph context is on. Column"
        " D$|$ctx=graph is the A0-vs-A2 contrast, whose Holm-corrected $p$ is"
        " in stats\\_ablation.md.")
    lines.append("\\end{table*}")
    return "\n".join(lines) + "\n"


def factorial_macros(pooled: dict, newcmd) -> None:
    fact = pooled.get("factorial") or {}
    if "skipped" in fact or not fact.get("measures"):
        return
    for i, e in enumerate(fact["measures"][FACT_LEAD]["per_model"]):
        w = _size_word(e["label"], i)
        for key, tag in (("decomposition_effect_given_context_graph", "DecompCtxGraph"),
                         ("decomposition_effect_given_context_prose", "DecompCtxProse"),
                         ("interaction", "Interaction")):
            d = _fx(e, key)
            if not d.get("n"):
                continue
            what = ("difference of the two simple effects (ctx=graph minus ctx=prose)"
                    if key == "interaction"
                    else "multi-agent minus single-agent decomposition")
            sign = ("POSITIVE = the decomposition effect is larger when context "
                    "is graph" if key == "interaction"
                    else "POSITIVE = the multi-agent pipeline scores higher")
            newcmd(f"abl{tag}{w}", fmt_num(d["mean_diff"], 3),
                   f"{key} = {what} on {FACT_LEAD} @ {e['label']} "
                   f"(paired per-scenario, n={d['n']}; {sign}; OPPOSITE sign "
                   "convention to \\ablDelta*, which is arm minus A0)")
            newcmd(f"abl{tag}P{w}", fmt_p(d["p_raw"]),
                   f"Wilcoxon p (uncorrected) for {key} on {FACT_LEAD} @ "
                   f"{e['label']}")
    act = pooled.get("self_validation_activity") or []
    for i, e in enumerate(act):
        w = _size_word(e["label"], i)
        for arm, tag in (("alignmentgraph-isd", "AZero"),
                         ("alignmentgraph-isd-multi-prose", "MultiProse")):
            v = (e.get("arms") or {}).get(arm)
            if not v:
                continue
            newcmd(f"ablRepairs{tag}{w}", fmt_num(v["repair_events_mean"], 2),
                   f"mean self-validation repairs per scenario, {arm} @ {e['label']}")


def gen_macros(pooled: dict) -> str:
    models = pooled["models"]
    a0 = pooled["config"]["reference"]
    arms = pooled["config"]["arms"]
    out = [header_comment(
        pooled, "abl_macros.tex — headline ablation numbers (separate from stats_macros.tex)")]

    def newcmd(name: str, value: str, comment: str) -> None:
        out.append(f"\\newcommand{{\\{name}}}{{{value}}}  % {comment}")

    for i, m in enumerate(models):
        w = _size_word(m["label"], i)
        s0 = m["agents"].get(a0, {})
        if s0.get("mean_addie") is not None:
            newcmd(f"ablAZeroAddie{w}", fmt_num(s0["mean_addie"]),
                   f"A0 ({a0}) mean addie_median @ {m['label']}, as re-run "
                   "inside the ablation; all four arms share each scenario's LLM "
                   "LLM judge session")
        for arm in arms:
            word = ARM_WORDS.get(arm)
            if word is None:
                continue
            d = arm_delta(m, arm)
            if not d:
                continue
            sig_note = ("on addie_median (ADDIE rubric /100, complete-case; "
                        "NEGATIVE = removing the component lowered ADDIE)")
            newcmd(f"ablDelta{word}{w}", fmt_num(d["delta"]),
                   f"{arm} minus A0 {sig_note} @ {m['label']} "
                   f"(paired per-scenario, n={d['n']})")
            newcmd(f"ablDelta{word}CILo{w}", fmt_num(d["ci95"][0]),
                   f"bootstrap CI95 lower, {arm} minus A0 {sig_note} @ {m['label']}")
            newcmd(f"ablDelta{word}CIHi{w}", fmt_num(d["ci95"][1]),
                   f"bootstrap CI95 upper, {arm} minus A0 {sig_note} @ {m['label']}")
            newcmd(f"ablP{word}{w}", fmt_p(d["p_holm"]),
                   f"Holm-corrected p on addie_median ({arm} vs A0; family = "
                   f"{len(arms)} arms within the size) @ {m['label']}")
    factorial_macros(pooled, newcmd)

    return "\n".join(out) + "\n"


def gen_stats_md(pooled: dict) -> str:
    models = pooled["models"]
    a0 = pooled["config"]["reference"]
    arms = pooled["config"]["arms"]
    L: list[str] = []
    L.append("# stats_ablation.md — ablation study, full numbers")
    L.append("")
    L.append(f"AUTO-GENERATED by `{paths.cli()} report ablation-tables` at "
             f"{datetime.now().isoformat(timespec='seconds')} from "
             f"pooled_ablation.json (generated_at {pooled.get('generated_at')}). "
             f"Do not edit by hand.")
    L.append("")
    L.append(f"- Design: {pooled['config'].get('design')}")
    L.append("- Axes: decomposition (multi-agent 5-Designer pipeline vs a "
             "single monolithic agent) x context representation (structured "
             "graph injection vs narrative prose). Self-validation is always "
             "on in both `agent_mode` values, so it is not an ablated axis.")
    L.append("- Arms: A0 = multi + graph (full pipeline), "
             "A1 = single + prose (both axes changed), "
             "A2 = single + graph (decomposition only), "
             "A3 = multi + prose (context only).")
    L.append("- **Two sign conventions are in play, so every section below "
             "states its own direction.** The arm-vs-A0 sections use "
             "**arm − A0** (flipped from the pooled JSON, which stores "
             "A0 − arm); the 2x2 factorial section uses "
             "**multi-agent − single-agent** / **graph − prose** (unflipped).")
    L.append(f"- Primary policy: {pooled['config'].get('primary_failure_policy')}; "
             f"Holm family: {pooled['config'].get('holm_family')}.")
    L.append("")

    L.append("## Per-size means and paired deltas (ADDIE, complete-case)")
    L.append("")
    L.append("Direction in this section: **arm − A0** on `addie_median` "
             "(negative = removing the component lowered ADDIE, positive = "
             "raised it). `r_rb` is the rank-biserial effect size, flipped to "
             "the same direction.")
    L.append("")
    for m in models:
        L.append(f"### {m['label']}  (runs={m['n_runs']}, scenario union="
                 f"{m['n_scenarios_union']})")
        L.append("")
        L.append("| Arm | mean ADDIE | nCC | missing | Δ vs A0 | CI95 | p_holm | r_rb |")
        L.append("|---|---|---|---|---|---|---|---|")
        for arm in [a0] + arms:
            s = m["agents"].get(arm, {})
            mt = s.get("mean_addie")
            mt_txt = f"{mt:.2f}" if isinstance(mt, (int, float)) and not math.isnan(mt) else "--"
            ncc = s.get("n_scenarios_complete", "--")
            miss = s.get("n_scenarios_any_missing", "--")
            if arm == a0:
                L.append(f"| {ARM_DISPLAY.get(arm, arm)} | {mt_txt} | {ncc} | {miss} "
                         f"| -- | -- | -- | -- |")
                continue
            d = arm_delta(m, arm)
            if d:
                # rank_biserial stored in A0−arm direction; flip with the delta
                r_rb = d.get("rank_biserial_r")
                r_txt = f"{-r_rb:+.2f}" if isinstance(r_rb, (int, float)) else "--"
                L.append(
                    f"| {ARM_DISPLAY.get(arm, arm)} | {mt_txt} | {ncc} | {miss} "
                    f"| {d['delta']:+.2f} (n={d['n']}) "
                    f"| [{d['ci95'][0]:+.2f}, {d['ci95'][1]:+.2f}] "
                    f"| {d['p_holm']:.3g} | {r_txt} |")
            else:
                L.append(f"| {ARM_DISPLAY.get(arm, arm)} | {mt_txt} | {ncc} | {miss} "
                         f"| (no shared scenarios) | -- | -- | -- |")
        L.append("")

    L.append("## A0 consistency check (pooling invariant, on total_score)")
    L.append("")
    cons = pooled.get("reference_drift", {})
    if cons.get("per_model"):
        L.append(cons.get("definition", ""))
        L.append("")
        L.append("**This check runs on `total_score` (the benchmark composite), "
                 "not on the `addie_median` series the rest of this file "
                 "reports** — so the A0 numbers here are deliberately different "
                 "from the mean-ADDIE column in the per-size tables above. A0's "
                 "ADDIE means are those per-size tables; this section bounds how "
                 "much of an arm delta could be session effect, by putting the ablation's "
                 "own A0 next to the comparison experiment's. It is not an arm comparison and must not "
                 "be written up as one.")
        L.append("")
        L.append("| Size | A0 Total (the ablation) | A0 Total (the comparison experiment ladder) "
                 "| Δ Total | ladder run-to-run SD (Total) | within 2×SD |")
        L.append("|---|---|---|---|---|---|")
        for row in cons["per_model"]:
            if "delta" not in row:
                L.append(f"| {row['label']} | -- | -- | {row.get('note', '')} | -- | -- |")
                continue
            sd = row.get("ladder_run_to_run_sd")
            sd_txt = f"{sd:.2f}" if isinstance(sd, (int, float)) else "--"
            L.append(f"| {row['label']} | {row['a0_mean_total_ablation_session']:.2f} "
                     f"| {row['a0_mean_total_ladder_pooled']:.2f} "
                     f"| {row['delta']:+.2f} | {sd_txt} "
                     f"| {row.get('within_2x_ladder_run_sd')} |")
    else:
        L.append(f"Skipped: {cons.get('note') or cons.get('error') or 'no data'}")
    L.append("")

    L.append("## Arm flag check (metadata.run_config vs agent id)")
    L.append("")
    for label, agents_map in pooled.get("flag_check", {}).items():
        for agent, status in agents_map.items():
            L.append(f"- {label} / {agent}: {status}")
    L.append("")

    align = pooled.get("alignment")
    L.append("## Alignment panel (paired, every score)")
    L.append("")
    if align and align.get("stats", {}).get("per_model"):
        L.append("Direction in this section: **arm − A0** (negative = removing "
                 "the component lowered the signal, positive = raised it); "
                 "flipped from the pooled JSON, which stores A0 − arm.")
        L.append("")
        L.append("A FLAT PANEL of signals, no primary endpoint and no "
                 "composite: every score is reported win or lose. The three "
                 "textual-correspondence signals are mean-max RECTIFIED cosine, "
                 "max(0, cos) on [0,1] — a scale choice, not a matching cutoff; "
                 "there is no similarity threshold anywhere in the protocol. "
                 "The three cognitive-demand "
                 "signals involve no similarity, and `porter_mean` is the MEAN "
                 "of the three pairwise Porter indices over those same three "
                 "triad edges, not a single index.")
        L.append("")
        L.append("Per-arm means come from the `align_descriptive` layer "
                 "(per-agent mean over per-scenario values), so their difference "
                 "need not equal the paired Δ to the last digit. Δ, CI and p are "
                 "the paired complete-case `comparisons` layer: Wilcoxon "
                 "two-sided, bootstrap 95% CI (10000 resamples, seed 42). "
                 "Multiplicity is reported twice: `p_holm` = Holm within one "
                 "signal (across the arms), `p_holm_panel` = Holm over the whole "
                 "panel × arm family for that size. Complete-case is over "
                 "AVAILABLE outputs, never unconditional.")
        L.append("")
        n_fail = sum(len(pm.get("align_failures") or {})
                     for pm in align["stats"]["per_model"])
        if n_fail:
            L.append(f"`align_failures` is non-empty ({n_fail} size(s) with a "
                     "missing output): the failure=0 rows therefore differ from "
                     "the complete-case rows below — read "
                     "`comparisons_failure_zero` in pooled_ablation.json.")
        else:
            L.append("`align_failures` is empty at every size (no arm is missing "
                     "an output), so the failure=0 pass "
                     "(`comparisons_failure_zero`) reproduces the complete-case "
                     "rows below exactly. The `conditional_align` and "
                     "`interaction_align` layers are not printed here — see "
                     "pooled_ablation.json.")
        L.append("")
        L.append("| Size | Signal | Arm | mean A0 | mean arm | Δ | CI95 "
                 "| p_holm | p_holm_panel | n |")
        L.append("|---|---|---|---|---|---|---|---|---|---|")
        for pm in align["stats"]["per_model"]:
            for signal, layers in (pm.get("panel") or {}).items():
                desc = layers.get("align_descriptive") or {}
                sig_txt = signal if layers.get("directional", True) \
                    else f"{signal} (non-directional)"
                for row in layers.get("comparisons") or []:
                    base = row.get("baseline")
                    arm = ARM_DISPLAY.get(base, base or "?")
                    m0 = (desc.get(a0) or {}).get("mean")
                    ma = (desc.get(base) or {}).get("mean")
                    m0_txt = f"{m0:.3f}" if isinstance(m0, (int, float)) else "--"
                    ma_txt = f"{ma:.3f}" if isinstance(ma, (int, float)) else "--"
                    if not row.get("n"):
                        L.append(f"| {pm['label']} | {sig_txt} | {arm} | {m0_txt} "
                                 f"| {ma_txt} | (no shared scenarios) | -- | -- "
                                 f"| -- | 0 |")
                        continue
                    pp = row.get("p_holm_panel")
                    pp_txt = f"{pp:.3g}" if isinstance(pp, (int, float)) else "--"
                    L.append(
                        f"| {pm['label']} | {sig_txt} | {arm} | {m0_txt} | {ma_txt} "
                        f"| {-row['mean_diff']:+.3f} "
                        f"| [{-row['ci95'][1]:+.3f}, {-row['ci95'][0]:+.3f}] "
                        f"| {row.get('p_holm', float('nan')):.3g} | {pp_txt} "
                        f"| {row['n']} |")
    else:
        L.append(f"Absent — run `{paths.cli()} judge alignment` on each ablation run "
                 f"dir, then re-run `{paths.cli()} pool ablation` and "
                 f"`{paths.cli()} report ablation-tables`.")
    L.append("")
    inter = pooled.get("interaction") or {}
    L.append("")
    L.append("## H2 / capacity interaction (DiD, largest size − smallest size)")
    L.append("")
    if inter.get("per_baseline"):
        L.append("Direction in this section: delta = **A0 − arm** per scenario (the full "
                 "architecture's advantage over that ablated cell); DiD = delta(largest) − "
                 "delta(smallest). **H2 predicts NEGATIVE DiD** — the advantage is largest "
                 "at the smallest model and shrinks as capacity grows. Near-zero DiD with "
                 "uniformly positive per-size deltas means the axis helps at every size "
                 "equally (decomposition/context helps, but not BECAUSE models are small); "
                 "near-zero DiD with near-zero deltas means the axis does not matter at "
                 "any size. Same machinery as the ladder pool's interaction layer "
                 "(Wilcoxon two-sided on per-scenario DiD, bootstrap 95% CI, complete-case); "
                 "per-signal versions in `interaction_by_score`.")
        L.append("")
        L.append("| Arm | Δ(smallest) | Δ(largest) | DiD | CI95 | p | n | trend by size |")
        L.append("|---|---|---|---|---|---|---|---|")
        for r in inter["per_baseline"]:
            lo, hi = r["did_ci95"]
            trend = " → ".join(f"{v:+.2f}" for v in r.get("trend_delta_by_size", {}).values())
            L.append(f"| {ARM_DISPLAY.get(r['baseline'], r['baseline'])} "
                     f"| {r['delta_smallest_mean']:+.2f} | {r['delta_largest_mean']:+.2f} "
                     f"| {r['did_mean']:+.2f} | [{lo:+.2f}, {hi:+.2f}] "
                     f"| {r['did_wilcoxon_p']:.3g} | {r['n_paired_scenarios']} | {trend} |")
    else:
        L.append(f"Skipped: {inter.get('note', 'no interaction layer in pooled_ablation.json — re-run ablation/08 (needs >= 2 model sizes)')}")
    L.append("")

    fact = pooled.get("factorial") or {}
    L.append("")
    L.append("## 2x2 factorial (decomposition x context representation)")
    L.append("")
    if "skipped" in fact or not fact.get("measures"):
        L.append(fact.get("skipped", "absent"))
    else:
        L.append("Direction in this section: **multi-agent − single-agent** / "
                 "**graph − prose** (positive = the richer setting scores "
                 "higher). These signs are NOT flipped, i.e. they are the "
                 "OPPOSITE of the arm − A0 direction used in the two sections "
                 "above: `decomp | ctx=graph` here is A0 − A2, the same "
                 "quantity the per-size table prints as A2 − A0.")
        L.append("")
        L.append("`interaction` = (decomposition effect given ctx=graph) − "
                 "(decomposition effect given ctx=prose). A negative "
                 "interaction means the two mechanisms substitute for each "
                 "other ONLY where both simple effects carry the beneficial "
                 "sign; where both are negative (`trajectory_score`, "
                 "`total_score`, on which multi-agent decomposition lowers the "
                 "score) read it as a magnitude statement — multi-agent "
                 "decomposition costs less when graph context is on — and "
                 "where the two simple effects have opposite signs it is a "
                 "crossover, neither substitution nor complementarity.")
        L.append("")
        L.append("p-values here are uncorrected. Note that the `decomp | "
                 "ctx=graph` and `ctx | decomp=multi` columns are the A0-vs-A2 "
                 "and A0-vs-A3 comparisons, which the sections above report "
                 "Holm-corrected within their family; only the `| ... =prose` "
                 "/ `| ... =single` columns and `interaction` are contrasts "
                 "unique to this section.")
        L.append("")
        L.append("Signals in this section are on two scales: `addie_median`, "
                 "`trajectory_score` and `total_score` are rubric points out of "
                 "100; the alignment signals are on [0,1]. Magnitudes are not "
                 "comparable across the two groups.")
        for sig, blk in fact["measures"].items():
            L.append("")
            scale = "rubric points /100" if sig in LLM_JUDGE_SCORES else "[0,1]"
            L.append(f"### {sig} ({scale})")
            L.append("")
            L.append("| Size | n | decomp \\| ctx=graph | decomp \\| ctx=prose "
                     "| ctx \\| decomp=multi | ctx \\| decomp=single | interaction |")
            L.append("|---|---|---|---|---|---|---|")
            for e in blk["per_model"]:
                cells = []
                for key in ("decomposition_effect_given_context_graph",
                            "decomposition_effect_given_context_prose",
                            "context_effect_given_decomposition_multi",
                            "context_effect_given_decomposition_single",
                            "interaction"):
                    d = e.get(key) or {}
                    cells.append("--" if not d.get("n") else
                                 f"{d['mean_diff']:+.3f} [{d['ci95'][0]:+.3f},"
                                 f"{d['ci95'][1]:+.3f}] p={d['p_raw']:.1e}")
                L.append(f"| {e['label']} | {e.get('n_scenarios', 0)} | "
                         + " | ".join(cells) + " |")
    act = pooled.get("self_validation_activity") or []
    if act:
        L.append("")
        L.append("## Self-validation activity (mechanism context, from trajectories)")
        L.append("")
        L.append("Self-validation is always on (not one of the two ablated "
                 "axes), so this section is context for reading the "
                 "decomposition effect above, not mechanism evidence for an "
                 "on/off switch.")
        L.append("")
        L.append("| Size | Arm | scenario-runs | verifier events/scen | repairs/scen | % runs with a repair |")
        L.append("|---|---|---|---|---|---|")
        for e in act:
            for arm, v in (e.get("arms") or {}).items():
                L.append(f"| {e['label']} | {arm} | {v['n_scenario_runs']} | "
                         f"{v['verifier_events_mean']:.2f} | {v['repair_events_mean']:.2f} | "
                         f"{v['pct_scenario_runs_with_repair']:.0f}% |")

    L += mechanism_md(pooled)
    return "\n".join(L) + "\n"



# ── the mechanism readout (what each arm DID) ────────────────────────────────

#: Columns of the mechanism table, per size: (header, reader over one arm's
#: summary, format). A reader returning None prints "--"; that is the prose
#: arms' coverage column by construction, since a prose run builds no graph.
MECHANISM_COLUMNS = (
    ("Ctx$\\times$", lambda a: (a.get("autonomy") or {}).get("context_growth_first_to_last"),
     lambda v: f"{v:.1f}"),
    ("Cut\\,\\%", lambda a: (a.get("autonomy") or {}).get("pct_stages_via_budget_exhaustion"),
     lambda v: f"{v:.0f}"),
    ("Core", lambda a: (a.get("relation_coverage") or {}).get("core_coverage_mean"),
     lambda v: f"{v:.2f}"),
    ("Open", lambda a: ((a.get("ledger") or {}).get("open_per_run") or {}).get("mean"),
     lambda v: f"{v:.1f}"),
)


def _mechanism_by_label(pooled: dict) -> dict[str, dict]:
    return {e["label"]: e.get("arms") or {} for e in pooled.get("mechanism") or []}


def gen_tab_mechanism(pooled: dict) -> str:
    """What each arm did, beside what it scored: the ablation's mechanism readout.

    The factorial says whether an axis moved a score; this says whether the axis
    did what it is defined as doing (context grows by stage in ``single``),
    whether an arm was CUT by its turn ceiling (a ceiling inside the delta), how
    much of the core triad it established, and how many findings it left open.
    """
    by_label = _mechanism_by_label(pooled)
    if not any(by_label.values()):
        return (header_comment(pooled, "tab_ablation_mechanism.tex — placeholder")
                + "% No mechanism layer in pooled_ablation.json.\n")
    models = pooled["models"]
    a0 = pooled["config"]["reference"]
    arms = pooled["config"]["arms"]
    k = len(MECHANISM_COLUMNS)
    colspec = "@{}l" + ("r" * k) * len(models) + "@{}"
    lines = [header_comment(pooled, "tab_ablation_mechanism.tex — what each arm did")]
    lines.append("\\begin{table*}[t]")
    lines.append(
        "  \\caption{What each ablation arm did, per model size. Ctx$\\times$: mean"
        " prompt length of the last stage over the first; Cut: \\% of stages ended"
        " by the turn ceiling; Core: mean coverage of the relations C2--C4"
        " (graph arms only); Open: findings left open per run.}")
    lines.append("  \\label{tab:ablation-mechanism}")
    lines.append("  \\small")
    lines.append(f"  \\begin{{tabular}}{{{colspec}}}")
    lines.append("    \\toprule")
    heads = " & ".join(
        f"\\multicolumn{{{k}}}{{c}}{{{model_display(m['label'])}}}" for m in models)
    lines.append(f"    & {heads} \\\\")
    cmids = "".join(
        f"\\cmidrule(lr){{{2 + k * i}-{1 + k * (i + 1)}}}" for i in range(len(models)))
    lines.append(f"    {cmids}")
    subs = " & ".join([h for h, _r, _f in MECHANISM_COLUMNS] * len(models))
    lines.append(f"    Arm & {subs} \\\\")
    lines.append("    \\midrule")
    for arm in [a0] + arms:
        name = ARM_DISPLAY.get(arm, arm)
        cells = []
        for m in models:
            summary = by_label.get(m["label"], {}).get(arm) or {}
            for _h, read, fmt in MECHANISM_COLUMNS:
                v = read(summary)
                cells.append("--" if not isinstance(v, (int, float)) or math.isnan(v)
                             else fmt(v))
        lines.append(f"    {name} & " + " & ".join(cells) + " \\\\")
    lines.append("    \\bottomrule")
    lines.append("  \\end{tabular}")
    lines.append(
        "  \\par\\smallskip\\footnotesize Open findings are not comparable across"
        " context representations: the prose arms run only the within-artifact"
        " checks. Per-stage series, per-relation coverage and open reasons:"
        " stats\\_ablation.md.")
    lines.append("\\end{table*}")
    return "\n".join(lines) + "\n"


def _fmt(v, spec: str = ".2f") -> str:
    return format(v, spec) if isinstance(v, (int, float)) and not (
        isinstance(v, float) and math.isnan(v)) else "--"


def mechanism_md(pooled: dict) -> list[str]:
    """The mechanism layer in full, for stats_ablation.md."""
    L = ["", "## Mechanism (what each arm did, from the harness's own records)", ""]
    entries = pooled.get("mechanism") or []
    if not any(e.get("arms") for e in entries):
        L.append("Absent — no `mechanism` layer in pooled_ablation.json.")
        return L
    L.append("Read from `*_trajectory.json` (`metadata.autonomy`), `*_graph.json` "
             "(relation coverage; graph arms only) and `*_violations.json` (the "
             "ledger). `cut` = % of stage runs ended by the turn ceiling "
             "(`via_budget_exhaustion`): a stage that was cut has the ceiling inside "
             "its delta. Ledger counts are NOT comparable across context "
             "representations: the prose arms run only the within-artifact checks.")
    for e in entries:
        for arm, a in (e.get("arms") or {}).items():
            L += ["", f"### {e['label']} / {ARM_DISPLAY.get(arm, arm)}", ""]
            h = a.get("health") or {}
            L.append(f"runs {h.get('n_runs')}, stopped {_fmt(h.get('pct_stopped'), '.0f')}%, "
                     f"with errors {_fmt(h.get('pct_with_errors'), '.0f')}%, "
                     f"ready_to_aggregate {_fmt(h.get('pct_ready_to_aggregate'), '.0f')}%")
            au = a.get("autonomy")
            if au:
                L += ["", "| Stage | turns mean | turns max | context_len mean "
                      "| history_dropped | compactions | gave up % | cut % |",
                      "|---|---|---|---|---|---|---|---|"]
                for stage, st in au["by_stage"].items():
                    def m(f, key="mean"):
                        return (st.get(f) or {}).get(key)
                    L.append(f"| {stage} | {_fmt(m('turns_used'), '.1f')} "
                             f"| {_fmt(m('turns_used', 'max'), '.0f')} "
                             f"| {_fmt(m('context_len'), '.0f')} "
                             f"| {_fmt(m('history_dropped'), '.1f')} "
                             f"| {_fmt(m('compactions'), '.2f')} "
                             f"| {_fmt(st.get('pct_gave_up'), '.0f')} "
                             f"| {_fmt(st.get('pct_via_budget_exhaustion'), '.0f')} |")
                L.append("")
                L.append(f"context growth last/first {_fmt(au.get('context_growth_first_to_last'))}"
                         f", peak {_fmt(au.get('peak_context_len'), '.0f')}")
            cov = a.get("relation_coverage")
            if cov:
                rels = cov.get("relation_coverage_mean") or {}
                L.append("")
                L.append(f"coverage (n={cov['n_with_graph']}): core C2–C4 "
                         f"{_fmt(cov.get('core_coverage_mean'))}, objectives aligned "
                         f"{_fmt(cov.get('objectives_aligned_mean'))}, runs with the core "
                         f"complete {_fmt(cov.get('pct_runs_core_complete'), '.0f')}%; "
                         + ", ".join(f"{r} {_fmt(v)}" for r, v in rels.items()))
            lg = a.get("ledger")
            if lg:
                pct = lg.get("pct_of_findings") or {}
                why = lg.get("pct_of_open_by_reason") or {}
                L.append("")
                L.append(f"ledger (n={lg['n_with_ledger']}): findings/run "
                         f"{_fmt((lg.get('findings_per_run') or {}).get('mean'), '.1f')}, "
                         f"open/run {_fmt((lg.get('open_per_run') or {}).get('mean'), '.1f')}; "
                         + ", ".join(f"{o} {_fmt(v, '.0f')}%" for o, v in pct.items())
                         + "; open because " + ", ".join(
                             f"{r} {_fmt(v, '.0f')}%" for r, v in why.items() if v)
                         + f"; shown to an agent {_fmt(lg.get('pct_shown_to_agent'), '.0f')}%")
                top = list((lg.get("open_by_type") or {}).items())[:8]
                if top:
                    L.append("open by type: " + ", ".join(f"{t} {n}" for t, n in top))
    return L



def build(pooled: dict) -> dict[str, str]:
    """Every ablation table, as {filename: content}."""
    return {
        "tab_ablation.tex": gen_tab_ablation(pooled),
        "tab_ablation_factorial.tex": gen_tab_factorial(pooled),
        "tab_ablation_factorial_full.tex": gen_tab_factorial_full(pooled),
        "tab_ablation_mechanism.tex": gen_tab_mechanism(pooled),
        "abl_macros.tex": gen_macros(pooled),
        "stats_ablation.md": gen_stats_md(pooled),
    }


def run(*, pooled_path: Path | None = None, outdir: Path | None = None,
        quiet: bool = False) -> list[Path]:
    from .. import schema

    src = pooled_path or (paths.results_root() / "pooled_ablation.json")
    if not src.exists():
        if not quiet:
            print(f"- no {src.name} — skipped. Produce it with:  {paths.cli()} pool ablation")
        return []
    pooled = schema.load(src)
    out = outdir or paths.generated_dir()
    out.mkdir(parents=True, exist_ok=True)
    written = []
    for name, content in build(pooled).items():
        path = out / name
        path.write_text(content, encoding="utf-8")
        written.append(path)
        if not quiet:
            print(f"wrote {path}")
    return written

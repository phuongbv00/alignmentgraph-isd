"""Tables for the 2x2 ablation.

One sign convention throughout, the one the pooled JSON stores: every effect
reads the richer setting minus the plainer one, **multi - single**
(decomposition) and **graph - prose** (substrate). The ablation concludes only
from its registered tests (``registered``: H-D, H-S per size, H-C per axis);
every factorial effect beside them is a descriptive mean difference with its
bootstrap interval, and is labelled as such wherever it is printed.
"""

from __future__ import annotations

import math
from datetime import datetime
from pathlib import Path

from .. import paths
from ..config import LLM_JUDGE_SCORES
from ..config import current as current_config
from ..latex import (
    fmt_num,
    fmt_p,
    header_comment,
    model_display,
    size_display,
    size_word,
)
from ..pool.diagnostics import TRIAD_REFERENCE_FIELDS
from ..pool.registered import REGISTERED_TESTS

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
    "alignmentgraph-isd": "AZero",
    "alignmentgraph-isd-single-prose": "SingleProse",
    "alignmentgraph-isd-single-graph": "SingleGraph",
    "alignmentgraph-isd-multi-prose": "MultiProse",
}

#: What each registered axis compares and what it is measured on, for display.
AXIS_DIRECTION = {"decomposition": "multi $-$ single", "substrate": "graph $-$ prose"}
AXIS_DIRECTION_MD = {"decomposition": "multi − single", "substrate": "graph − prose"}
AXIS_WORDS = {"decomposition": "Decomp", "substrate": "Substrate"}
MEASURE_DISPLAY = {"addie_median": "ADDIE", "objectives_closed_triad": "closed triads"}
#: Decimal places per registered measure: rubric points vs a [0,1] share.
MEASURE_ND = {"addie_median": 2, "objectives_closed_triad": 3}


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

def _tex_num(v, nd: int = 2) -> str:
    """A number for a text-mode cell, with a typeset minus."""
    return fmt_num(v, nd).replace("-", "$-$")


def _tex_ci(row: dict, nd: int = 2) -> str:
    lo, hi = row["ci95"]
    return f"[{_tex_num(lo, nd)}, {_tex_num(hi, nd)}]"


def _finite(v) -> bool:
    return isinstance(v, (int, float)) and not (isinstance(v, float) and math.isnan(v))


def registered_by_size(pooled: dict) -> dict[str, dict[str, dict]]:
    """size label -> axis -> the registered H-D / H-S row at that size."""
    out: dict[str, dict[str, dict]] = {}
    for row in (pooled.get("registered") or {}).get("family") or []:
        if row.get("size"):
            out.setdefault(row["size"], {})[row["axis"]] = row
    return out


def registered_cross_size(pooled: dict) -> dict[str, dict]:
    """axis -> the registered H-C row (effect at the smallest size minus at the largest)."""
    return {row["axis"]: row for row in (pooled.get("registered") or {}).get("family") or []
            if not row.get("size")}


def _n_tested(pooled: dict) -> int:
    return sum(1 for r in (pooled.get("registered") or {}).get("family") or [] if "p_holm" in r)


def _zero_scored(pooled: dict) -> list[tuple[str, str, int]]:
    """(size, arm, k) for every arm that left k scenarios with no scorable output."""
    a0 = pooled["config"]["reference"]
    out = []
    for m in pooled["models"]:
        for arm in [a0] + pooled["config"]["arms"]:
            k = (m["agents"].get(arm) or {}).get("n_scenarios_any_missing")
            if isinstance(k, int) and k:
                out.append((m["label"], arm, k))
    return out


def _zero_clause_tex(pooled: dict) -> str:
    zeros = _zero_scored(pooled)
    if not zeros:
        return "Every arm left a scorable output on every scenario."
    parts = [f"{ARM_DISPLAY.get(arm, arm).split(' ')[0]} at {size_display(lb)}: {k}"
             for lb, arm, k in zeros]
    return ("Scenarios with no scorable output count 0 (" + "; ".join(parts) + ").")


def _cell_key_by_arm(pooled: dict) -> dict[str, str]:
    """agent id -> its factorial cell key (``agentmode_<m>__contextmode_<c>``)."""
    cells = (pooled.get("factorial") or {}).get("cells") or {}
    return {agent: key for key, agent in cells.items()}


# ── outputs ──────────────────────────────────────────────────────────────────

def _md_test_row(r: dict, nd: int = 3) -> str:
    lo, hi = r["ci95"]
    return (f"{r['mean_diff']:+.{nd}f} | [{lo:+.{nd}f}, {hi:+.{nd}f}] "
            f"| {fmt_num(r.get('rank_biserial_r'), 2)} | {r['n']} "
            f"| {r.get('p_holm', float('nan')):.3g} | {r['verdict']}")


def registered_section(pooled: dict) -> list[str]:
    """The tests the ablation concludes from, as registered (benchmark_guides §5.5)."""
    reg = pooled.get("registered") or {}
    if not reg.get("family"):
        return []
    L = ["## Registered tests", "",
         "Direction: **multi − single** (decomposition) and **graph − prose** "
         "(substrate), main effect over the other axis; H-C = effect at the "
         "smallest size − at the largest. Failure = 0, scenario as the unit. "
         f"Holm over the {_n_tested(pooled)} of these that could be run, and no "
         "others. Verdict: supported = p_holm < 0.05 with the predicted (positive) "
         "sign; contrary = p_holm < 0.05, negative; otherwise not detected.", "",
         "| Test | Measure | Δ | CI95 | r_rb | n | p_holm | Verdict |",
         "|---|---|---|---|---|---|---|---|"]
    if not reg.get("complete"):
        L[4:4] = ["**Incomplete: not every registered test could be run on these run "
                  "dirs, so these verdicts are not the registered analysis.**", ""]
    for r in reg["family"]:
        if not r.get("n"):
            L.append(f"| {r['test']} | {r['measure']} | — | — | — | 0 | — | {r['verdict']} |")
            continue
        L.append(f"| {r['test']} | {r['measure']} | {_md_test_row(r)} |")
    L.append("")

    secondary = reg.get("secondary") or {}
    if not secondary:
        return L
    L += ["### Complete-case (sensitivity)", "",
          "The same H-D / H-S tests with a run that left no scorable output left "
          "out instead of scored 0; Holm over the pair at each size, verdict on the "
          "same rule.", "",
          "| Size | Test | Δ | CI95 | r_rb | n | p_holm | Verdict |",
          "|---|---|---|---|---|---|---|---|"]
    for size, sec in secondary.items():
        for r in sec.get("complete_case") or []:
            if not r.get("n"):
                L.append(f"| {size} | {r['test']} | — | — | — | 0 | — | {r.get('verdict', '')} |")
                continue
            L.append(f"| {size} | {r['test']} | {_md_test_row(r)} |")
    L += ["", "### Decomposition × substrate interaction (pre-specified, uncorrected)", "",
          "Interaction = (multi − single | graph) − (multi − single | prose) on each "
          "axis's measure, failure = 0. Positive = decomposition gains more on the "
          "graph substrate. p_raw is **uncorrected**: these contrasts are outside "
          "the Holm family.", "",
          "| Size | Measure | Δ | CI95 | r_rb | n | p_raw (uncorrected) |",
          "|---|---|---|---|---|---|---|"]
    for size, sec in secondary.items():
        for measure, r in (sec.get("interaction") or {}).items():
            if not r or not r.get("n"):
                L.append(f"| {size} | {measure} | — | — | — | 0 | — |")
                continue
            lo, hi = r["ci95"]
            L.append(f"| {size} | {measure} | {r['mean_diff']:+.3f} | [{lo:+.3f}, {hi:+.3f}] "
                     f"| {fmt_num(r.get('rank_biserial_r'), 2)} | {r['n']} | {r['p_raw']:.3g} |")
    L += ["", "### Descriptive readings (mean and BCa interval, no test)", "",
          "The substrate effect (graph − prose) on the triad closed by references "
          "the model wrote itself (the repair net's references taken out), and the "
          "slope of the multi − single ADDIE gap over the five ADDIE phases "
          "(positive = the single arm falls further behind the later the phase).", "",
          "| Size | Reading | Δ | CI95 | n |",
          "|---|---|---|---|---|"]
    for size, sec in secondary.items():
        for name, row in (("substrate, model-written triad", sec.get("substrate|model_written")),
                          ("phase slope (per phase)", (sec.get("phase_slope") or {}).get("slope"))):
            if not row or not row.get("n"):
                L.append(f"| {size} | {name} | — | — | 0 |")
                continue
            lo, hi = row["ci95"]
            L.append(f"| {size} | {name} | {row['mean_diff']:+.3f} "
                     f"| [{lo:+.3f}, {hi:+.3f}] | {row['n']} |")
    gaps = [(size, (sec.get("phase_slope") or {}).get("gap_by_phase") or {})
            for size, sec in secondary.items()]
    if any(g for _s, g in gaps):
        L += ["", "Multi − single ADDIE gap by phase (mean over scenarios, complete-case "
              "per phase):", "",
              "| Size | " + " | ".join(next(g for _s, g in gaps if g)) + " |",
              "|---|" + "---|" * len(next(g for _s, g in gaps if g))]
        for size, g in gaps:
            L.append(f"| {size} | " + " | ".join(
                f"{v:+.2f}" if _finite(v) else "--" for v in g.values()) + " |")
    L.append("")
    return L


def gen_tab_ablation(pooled: dict) -> str:
    """The 2x2 cell table: each arm's mean ADDIE per size, and the registered
    H-D / H-S result at that size beneath it."""
    models = pooled["models"]
    a0 = pooled["config"]["reference"]
    arms = pooled["config"]["arms"]
    by_size = registered_by_size(pooled)
    cross = registered_cross_size(pooled)
    ncols = 1 + len(models)
    env = "table*" if len(models) > 2 else "table"

    lines = [header_comment(PRODUCER, "tab_ablation.tex — 2x2 cell means and registered tests",
                            pooled)]
    lines.append(f"\\begin{{{env}}}[t]")
    lines.append(
        "  \\caption{Ablation per model size. Top: each arm's mean ADDIE (/100,"
        " failure = 0); bold marks the reference arm (A0). Bottom: the registered"
        " main effects of decomposition (H-D) and substrate (H-S), with bootstrap"
        " 95\\% CI, Holm-adjusted $p$ and verdict.}")
    lines.append("  \\label{tab:ablation}")
    lines.append("  \\small")
    lines.append(f"  \\begin{{tabular}}{{@{{}}l{'r' * len(models)}@{{}}}}")
    lines.append("    \\toprule")
    lines.append("    & " + " & ".join(model_display(m["label"]) for m in models) + " \\\\")
    lines.append("    \\midrule")
    lines.append(f"    \\multicolumn{{{ncols}}}{{@{{}}l}}"
                 "{\\emph{Mean ADDIE (/100), failure = 0}} \\\\")
    for arm in [a0] + arms:
        name = ARM_DISPLAY.get(arm, arm)
        if arm == a0:
            name = f"\\textbf{{{name}}}"
        cells = []
        for m in models:
            v = (m["agents"].get(arm) or {}).get("mean_addie")
            if not _finite(v):
                cells.append("--")
                continue
            cells.append(f"\\textbf{{{fmt_num(v)}}}" if arm == a0 else fmt_num(v))
        lines.append(f"    {name} & " + " & ".join(cells) + " \\\\")
    if by_size:
        lines.append("    \\addlinespace")
        lines.append(f"    \\multicolumn{{{ncols}}}{{@{{}}l}}"
                     "{\\emph{Registered tests (main effect over the other axis)}} \\\\")
        for axis, hyp in (("decomposition", "H-D"), ("substrate", "H-S")):
            rows = [by_size.get(m["label"], {}).get(axis) or {} for m in models]
            measure = next((r.get("measure") for r in rows if r.get("measure")), "")
            nd = MEASURE_ND.get(measure, 3)
            lines.append(f"    {hyp}: $\\Delta$ {MEASURE_DISPLAY.get(measure, measure)},"
                         f" {AXIS_DIRECTION[axis]} & "
                         + " & ".join(_tex_num(r["mean_diff"], nd) if r.get("n") else "--"
                                      for r in rows) + " \\\\")
            lines.append("    \\quad 95\\% CI & "
                         + " & ".join(_tex_ci(r, nd) if r.get("n") else "--"
                                      for r in rows) + " \\\\")
            lines.append("    \\quad $p_{\\mathrm{Holm}}$, verdict & "
                         + " & ".join(f"${fmt_p(r.get('p_holm'))}$, {r['verdict']}"
                                      if r.get("n") else "--" for r in rows) + " \\\\")
        if len(models) >= 2:
            for axis in ("decomposition", "substrate"):
                r = cross.get(axis) or {}
                if not r.get("n"):
                    continue
                measure = r.get("measure")
                nd = MEASURE_ND.get(measure, 3)
                lines.append(
                    f"    H-C: $\\Delta$ {MEASURE_DISPLAY.get(measure, measure)},"
                    f" {AXIS_DIRECTION[axis]}, smallest $-$ largest size & "
                    f"\\multicolumn{{{len(models)}}}{{c}}{{{_tex_num(r['mean_diff'], nd)}"
                    f" {_tex_ci(r, nd)}, $p_{{\\mathrm{{Holm}}}}={fmt_p(r.get('p_holm'))}$,"
                    f" {r['verdict']}}} \\\\")
    lines.append("    \\bottomrule")
    lines.append("  \\end{tabular}")
    reg = pooled.get("registered") or {}
    foot = ("  \\par\\smallskip\\footnotesize $\\Delta$ = per-scenario main effect,"
            " averaged over the other axis; closed triads = share of objectives whose"
            " references close the triad.")
    if by_size and not reg.get("complete"):
        foot += (f" Holm over the {_n_tested(pooled)} of the {REGISTERED_TESTS} registered"
                 " tests that could be run on these runs, so this is not the full"
                 " registered analysis.")
    elif by_size:
        foot += f" Holm over the {REGISTERED_TESTS} registered tests."
    foot += (f" {_zero_clause_tex(pooled)} Complete-case sensitivity and secondary"
             " readings: stats\\_ablation.md.")
    lines.append(foot)
    lines.append(f"\\end{{{env}}}")
    return "\n".join(lines) + "\n"


#: Signal the factorial table leads on: the decomposition/context effects are
#: expected as alignment effects, not LLM judge effects, so the main-text table
#: is built on the alignment signal and ADDIE is reported in the appendix one.
FACT_LEAD = "objective_assessment_similarity"


def _fx(model_entry: dict, key: str) -> dict:
    return model_entry.get(key) or {}


def _has_factorial(pooled: dict, signal: str | None = None) -> bool:
    fact = pooled.get("factorial") or {}
    if "skipped" in fact or not fact.get("measures"):
        return False
    return signal is None or signal in fact["measures"]


def gen_tab_factorial(pooled: dict) -> str:
    """The 2x2 read: simple effects of decomposition under each context
    representation, and their difference (the interaction). Descriptive: the
    ablation's tests are the registered ones."""
    if not _has_factorial(pooled, FACT_LEAD):
        return (header_comment(PRODUCER, "tab_ablation_factorial.tex — placeholder", pooled)
                + "% No factorial layer in pooled_ablation.json (arms missing).\n")
    per_model = pooled["factorial"]["measures"][FACT_LEAD]["per_model"]

    lines = [header_comment(
        PRODUCER, "tab_ablation_factorial.tex — 2x2 simple effects + interaction", pooled)]
    lines.append("\\begin{table}[t]")
    lines.append(
        "  \\caption{$2\\times2$ read on \\texttt{objective\\_assessment\\_similarity}."
        " Each cell: mean paired difference, multi-agent $-$ single-agent"
        f" ({n_clause(per_model)}, failure = 0); interaction = col.~1 $-$ col.~2."
        " Descriptive, no test.}")
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
            cells.append(_tex_num(d["mean_diff"], 3) if d.get("n") else "--")
        lines.append(f"    {size_display(e['label'])} & " + " & ".join(cells) + " \\\\")
    lines.append("    \\bottomrule")
    lines.append("  \\end{tabular}")
    lines.append(
        "  \\par\\smallskip\\footnotesize Positive = the multi-agent pipeline scores"
        " higher. The ablation's tests are the registered ones"
        " (Table~\\ref{tab:ablation}); bootstrap 95\\% CI of every cell:"
        " stats\\_ablation.md.")
    lines.append("\\end{table}")
    return "\n".join(lines) + "\n"


#: Short display names for the factorial appendix table. Same labels as
#: tables.py uses: porter_mean is the MEAN of the three pairwise Porter
#: indices, not one index.
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

    The main-text table leads on one signal; a claim about how the two
    mechanisms combine is a claim about the design, so it has to be checkable
    on every signal the study reports. The two row blocks are on different
    scales (rubric points vs [0,1]) and are labelled as such: nothing in this
    table licenses comparing the magnitude of an LLM judge cell with the
    magnitude of a panel cell.
    """
    if not _has_factorial(pooled):
        return (header_comment(PRODUCER, "tab_ablation_factorial_full.tex — placeholder", pooled)
                + "% No factorial layer in pooled_ablation.json (arms missing).\n")
    signals = pooled["factorial"]["measures"]
    labels = [e["label"] for e in next(iter(signals.values()))["per_model"]]
    all_entries = [e for blk in signals.values() for e in blk["per_model"]]

    lines = [header_comment(
        PRODUCER, "tab_ablation_factorial_full.tex — 2x2 read on every reported signal", pooled)]
    lines.append("\\begin{table*}[t]")
    lines.append(
        "  \\caption{$2\\times2$ read on every reported signal. Each cell: mean"
        " paired difference, multi-agent $-$ single-agent decomposition"
        f" ({n_clause(all_entries)}, failure = 0); D$|$ctx = decomposition effect"
        " with context graph/prose, $\\times$ = col.~1 $-$ col.~2. Descriptive.}")
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
                    cells.append(_tex_num(d["mean_diff"], 3) if d.get("n") else "--")
            name = FACT_SIGNAL_DISPLAY.get(sig, sig.replace("_", "\\_"))
            lines.append(f"    {name} & " + " & ".join(cells) + " \\\\")
    lines.append("    \\bottomrule")
    lines.append("  \\end{tabular}")
    lines.append(
        "  \\par\\smallskip\\footnotesize Row blocks differ in scale; magnitudes are"
        " not comparable across them. Descriptive, no test: the ablation's tests are"
        " the registered ones (Table~\\ref{tab:ablation}); bootstrap 95\\% CI of"
        " every cell: stats\\_ablation.md."
        " $\\times$ is computed at full precision, so it need not equal the"
        " difference of the two rounded cells beside it."
        " A negative $\\times$ means the decomposition effect is lower under graph"
        " than under prose, whatever its sign; it reads as substitution only where"
        " both simple effects are positive.")
    lines.append("\\end{table*}")
    return "\n".join(lines) + "\n"


def factorial_macros(pooled: dict, newcmd) -> None:
    if _has_factorial(pooled, FACT_LEAD):
        for i, e in enumerate(pooled["factorial"]["measures"][FACT_LEAD]["per_model"]):
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
                       f"(paired per-scenario, n={d['n']}, failure = 0; {sign}; "
                       "descriptive, no test)")
                newcmd(f"abl{tag}CILo{w}", fmt_num(d["ci95"][0], 3),
                       f"bootstrap CI95 lower, {key} on {FACT_LEAD} @ {e['label']}")
                newcmd(f"abl{tag}CIHi{w}", fmt_num(d["ci95"][1], 3),
                       f"bootstrap CI95 upper, {key} on {FACT_LEAD} @ {e['label']}")
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


def registered_macros(pooled: dict, newcmd) -> None:
    """The registered H-D / H-S result per size and H-C per axis."""
    models = pooled["models"]
    by_size = registered_by_size(pooled)
    for i, m in enumerate(models):
        w = _size_word(m["label"], i)
        for axis, row in by_size.get(m["label"], {}).items():
            if not row.get("n"):
                continue
            tag = f"ablReg{AXIS_WORDS[axis]}"
            nd = MEASURE_ND.get(row["measure"], 3)
            what = (f"registered {row['test']}: main effect {AXIS_DIRECTION_MD[axis]} on "
                    f"{row['measure']}, failure = 0")
            newcmd(f"{tag}{w}", fmt_num(row["mean_diff"], nd),
                   f"{what} (paired per-scenario, n={row['n']})")
            newcmd(f"{tag}CILo{w}", fmt_num(row["ci95"][0], nd), f"bootstrap CI95 lower, {what}")
            newcmd(f"{tag}CIHi{w}", fmt_num(row["ci95"][1], nd), f"bootstrap CI95 upper, {what}")
            newcmd(f"{tag}P{w}", fmt_p(row.get("p_holm")),
                   f"Holm-adjusted p (math mode), {what}; Holm over the "
                   f"{_n_tested(pooled)} registered tests run")
            newcmd(f"{tag}Verdict{w}", row["verdict"], f"verdict, {what}")
    for axis, row in registered_cross_size(pooled).items():
        if not row.get("n"):
            continue
        tag = f"ablRegCross{AXIS_WORDS[axis]}"
        nd = MEASURE_ND.get(row["measure"], 3)
        what = (f"registered {row['test']}: {axis} effect at {row['smallest']} minus at "
                f"{row['largest']} on {row['measure']}, failure = 0")
        newcmd(tag, fmt_num(row["mean_diff"], nd), f"{what} (n={row['n']})")
        newcmd(f"{tag}CILo", fmt_num(row["ci95"][0], nd), f"bootstrap CI95 lower, {what}")
        newcmd(f"{tag}CIHi", fmt_num(row["ci95"][1], nd), f"bootstrap CI95 upper, {what}")
        newcmd(f"{tag}P", fmt_p(row.get("p_holm")), f"Holm-adjusted p (math mode), {what}")
        newcmd(f"{tag}Verdict", row["verdict"], f"verdict, {what}")


def gen_macros(pooled: dict) -> str:
    models = pooled["models"]
    a0 = pooled["config"]["reference"]
    arms = pooled["config"]["arms"]
    out = [header_comment(
        PRODUCER, "abl_macros.tex — headline ablation numbers (separate from stats_macros.tex)",
        pooled)]

    def newcmd(name: str, value: str, comment: str) -> None:
        out.append(f"\\newcommand{{\\{name}}}{{{value}}}  % {comment}")

    for i, m in enumerate(models):
        w = _size_word(m["label"], i)
        for arm in [a0] + arms:
            word = ARM_WORDS.get(arm)
            s = m["agents"].get(arm) or {}
            if word is None or not _finite(s.get("mean_addie")):
                continue
            newcmd(f"abl{word}Addie{w}", fmt_num(s["mean_addie"]),
                   f"{arm} mean addie_median @ {m['label']} over "
                   f"{s.get('n_scenarios')} scenarios, failure = 0; all four arms "
                   "share each scenario's LLM judge session")
    registered_macros(pooled, newcmd)
    factorial_macros(pooled, newcmd)

    return "\n".join(out) + "\n"


def _md_num(v, spec: str = ".2f") -> str:
    return format(v, spec) if _finite(v) else "--"


def gen_stats_md(pooled: dict) -> str:
    models = pooled["models"]
    a0 = pooled["config"]["reference"]
    arms = pooled["config"]["arms"]
    flags = pooled["config"].get("expected_flags") or {}
    L: list[str] = []
    L.append("# stats_ablation.md — ablation study, full numbers")
    L.append("")
    L.append(f"AUTO-GENERATED by `{paths.cli()} report ablation-tables` at "
             f"{datetime.now().isoformat(timespec='seconds')} from "
             f"pooled_ablation.json (generated_at {pooled.get('generated_at')}). "
             f"Do not edit by hand.")
    L.append("")
    L.append(f"- Design: {pooled['config'].get('design')}")
    L.append("- Axes: decomposition (multi-agent pipeline vs a single agent) x "
             "context representation (structured graph vs narrative prose). "
             "Self-validation is always on in both `agent_mode` values, so it is "
             "not an ablated axis.")
    L.append("- Arms: A0 = multi + graph (full pipeline), "
             "A1 = single + prose (both axes changed), "
             "A2 = single + graph (decomposition only), "
             "A3 = multi + prose (context only).")
    L.append(f"- Direction: {pooled['config'].get('direction')}. Every section "
             "below uses it.")
    L.append(f"- Primary policy: failure = 0 ({pooled['config'].get('primary_failure_policy')}); "
             f"Holm family: {pooled['config'].get('holm_family')}. Everything outside "
             "the registered tests is descriptive or labelled uncorrected.")
    L.append("")

    L.extend(registered_section(pooled))

    L.append("## Per-size cell means (failure = 0)")
    L.append("")
    L.append("Each arm's mean over scenarios, a scenario where the arm left no "
             "scorable output counting 0; `scored 0` is how many such scenarios "
             "there were. The complete-case column (sensitivity) leaves them out. "
             "SD is across scenarios.")
    L.append("")
    for m in models:
        L.append(f"### {m['label']}  (runs={m['n_runs']}, scenario union="
                 f"{m['n_scenarios_union']})")
        L.append("")
        L.append("| Arm | agent_mode | context_mode | n | scored 0 | mean ADDIE | SD "
                 "| mean Traj | mean Total | mean ADDIE complete-case |")
        L.append("|---|---|---|---|---|---|---|---|---|---|")
        for arm in [a0] + arms:
            s = m["agents"].get(arm) or {}
            f = flags.get(arm) or {}
            L.append(f"| {ARM_DISPLAY.get(arm, arm)} | {f.get('agent_mode', '--')} "
                     f"| {f.get('context_mode', '--')} | {s.get('n_scenarios', '--')} "
                     f"| {s.get('n_scenarios_any_missing', '--')} "
                     f"| {_md_num(s.get('mean_addie'))} "
                     f"| {_md_num(s.get('sd_addie_across_scenarios'))} "
                     f"| {_md_num(s.get('mean_traj'))} | {_md_num(s.get('mean_total'))} "
                     f"| {_md_num(s.get('mean_addie_complete_case'))} |")
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
                 "from the mean-ADDIE column in the per-size tables above. It "
                 "bounds how much of an effect could be session effect, by putting "
                 "the ablation's own A0 next to the comparison experiment's. It is "
                 "not an arm comparison and must not be written up as one.")
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

    fact = pooled.get("factorial") or {}
    L.append("## 2x2 factorial (decomposition x context representation)")
    L.append("")
    if not _has_factorial(pooled):
        L.append(fact.get("skipped", "absent"))
    else:
        cell_of = _cell_key_by_arm(pooled)
        cell_order = [cell_of.get(arm) for arm in [a0] + arms]
        cell_names = "/".join(ARM_DISPLAY.get(arm, arm).split(" ")[0] for arm in [a0] + arms)
        L.append("Descriptive: each effect is a mean of per-scenario differences "
                 "with its BCa bootstrap 95% interval and no test — the ablation's "
                 "tests are the registered ones above. Failure = 0, over the "
                 "scenarios all four cells scored (`n`). Direction **multi − single** "
                 "/ **graph − prose** (positive = the richer setting scores higher). "
                 f"Cell means are {cell_names}, in that order.")
        L.append("")
        L.append("`interaction` = (decomposition effect given ctx=graph) − "
                 "(decomposition effect given ctx=prose). Negative means the "
                 "decomposition effect is lower under graph than under prose, "
                 "whatever its sign: where both simple effects are positive the two "
                 "mechanisms substitute for each other, where both are negative "
                 "multi-agent decomposition costs MORE under graph, and where the "
                 "two simple effects have opposite signs it is a crossover.")
        L.append("")
        L.append("Signals in this section are on two scales: `addie_median`, "
                 "`trajectory_score` and `total_score` are rubric points out of "
                 "100; the alignment signals are on [0,1]. Magnitudes are not "
                 "comparable across the two groups.")
        for sig, blk in fact["measures"].items():
            L.append("")
            scale = "rubric points /100" if sig in LLM_JUDGE_SCORES else "[0,1]"
            nd = 2 if sig in LLM_JUDGE_SCORES else 3
            L.append(f"### {sig} ({scale})")
            L.append("")
            L.append(f"| Size | n | cell means {cell_names} | decomp \\| ctx=graph "
                     "| decomp \\| ctx=prose | ctx \\| decomp=multi | ctx \\| decomp=single "
                     "| interaction |")
            L.append("|---|---|---|---|---|---|---|---|")
            for e in blk["per_model"]:
                if not e.get("n_scenarios"):
                    L.append(f"| {e['label']} | 0 | {e.get('note', '--')} "
                             "| -- | -- | -- | -- | -- |")
                    continue
                means = e.get("cell_means") or {}
                cm = " / ".join(_md_num(means.get(k), f".{nd}f") for k in cell_order)
                cells = []
                for key in ("decomposition_effect_given_context_graph",
                            "decomposition_effect_given_context_prose",
                            "context_effect_given_decomposition_multi",
                            "context_effect_given_decomposition_single",
                            "interaction"):
                    d = e.get(key) or {}
                    cells.append("--" if not d.get("n") else
                                 f"{d['mean_diff']:+.{nd}f} [{d['ci95'][0]:+.{nd}f}, "
                                 f"{d['ci95'][1]:+.{nd}f}]")
                L.append(f"| {e['label']} | {e['n_scenarios']} | {cm} | "
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

    L += process_md(pooled)
    return "\n".join(L) + "\n"


# ── the process measures (what each arm DID) ─────────────────────────────────

#: Columns of the process table, per size: (header, reader over one arm's
#: summary, format). A reader returning None prints "--"; that is the prose
#: arms' coverage column by construction, since a prose run builds no graph.
PROCESS_COLUMNS = (
    ("Ctx$\\times$", lambda a: (a.get("autonomy") or {}).get("context_growth_first_to_last"),
     lambda v: f"{v:.1f}"),
    ("Cut\\,\\%", lambda a: (a.get("autonomy") or {}).get("pct_stages_via_budget_exhaustion"),
     lambda v: f"{v:.0f}"),
    ("Core", lambda a: (a.get("relation_coverage") or {}).get("core_coverage_mean"),
     lambda v: f"{v:.2f}"),
    ("Triad", lambda a: (a.get("triad_references") or {}).get("objectives_closed_triad"),
     lambda v: f"{v:.2f}"),
    ("Open", lambda a: ((a.get("ledger") or {}).get("open_per_run") or {}).get("mean"),
     lambda v: f"{v:.1f}"),
)


def _process_by_label(pooled: dict) -> dict[str, dict]:
    return {e["label"]: e.get("arms") or {} for e in pooled.get("process") or []}


def gen_tab_process(pooled: dict) -> str:
    """What each arm did, beside what it scored: the ablation's process measures.

    The factorial says whether an axis moved a score; this says whether the axis
    did what it is defined as doing (context grows by stage in ``single``),
    whether an arm was CUT by its turn ceiling (a ceiling inside the delta), how
    much of the core triad it established, and how many findings it left open.
    """
    by_label = _process_by_label(pooled)
    if not any(by_label.values()):
        return (header_comment(PRODUCER, "tab_ablation_process.tex — placeholder", pooled)
                + "% No process layer in pooled_ablation.json.\n")
    models = pooled["models"]
    a0 = pooled["config"]["reference"]
    arms = pooled["config"]["arms"]
    k = len(PROCESS_COLUMNS)
    colspec = "@{}l" + ("r" * k) * len(models) + "@{}"
    lines = [header_comment(PRODUCER, "tab_ablation_process.tex — what each arm did", pooled)]
    lines.append("\\begin{table*}[t]")
    lines.append(
        "  \\caption{What each ablation arm did, per size. Ctx$\\times$: mean"
        " last-stage over first-stage prompt length; Cut: \\% of stages cut by"
        " the turn ceiling; Core: mean C2--C4 coverage (graph arms); Triad: share"
        " of objectives closing the triad; Open: open findings per run.}")
    lines.append("  \\label{tab:ablation-process}")
    lines.append("  \\small")
    lines.append(f"  \\begin{{tabular}}{{{colspec}}}")
    lines.append("    \\toprule")
    heads = " & ".join(
        f"\\multicolumn{{{k}}}{{c}}{{{model_display(m['label'])}}}" for m in models)
    lines.append(f"    & {heads} \\\\")
    cmids = "".join(
        f"\\cmidrule(lr){{{2 + k * i}-{1 + k * (i + 1)}}}" for i in range(len(models)))
    lines.append(f"    {cmids}")
    subs = " & ".join([h for h, _r, _f in PROCESS_COLUMNS] * len(models))
    lines.append(f"    Arm & {subs} \\\\")
    lines.append("    \\midrule")
    for arm in [a0] + arms:
        name = ARM_DISPLAY.get(arm, arm)
        cells = []
        for m in models:
            summary = by_label.get(m["label"], {}).get(arm) or {}
            for _h, read, fmt in PROCESS_COLUMNS:
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


def process_md(pooled: dict) -> list[str]:
    """The process layer in full, for stats_ablation.md."""
    L = ["", "## Process measures (what each arm did, from the harness's own records)", ""]
    entries = pooled.get("process") or []
    if not any(e.get("arms") for e in entries):
        L.append("Absent — no `process` layer in pooled_ablation.json.")
        return L
    L.append("Read from `*_trajectory.json` (`metadata.autonomy`), `*_graph.json` "
             "(relation coverage; graph arms only), `*_output.json` (triad "
             "references; every arm) and `*_violations.json` (the "
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
            tri = a.get("triad_references")
            if tri:
                L.append("")
                L.append(f"triad references (n={tri['n_runs']}): "
                         + ", ".join(f"{f} {_fmt(tri.get(f))}"
                                     for f in (*TRIAD_REFERENCE_FIELDS, "activities_repaired")))
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
        "tab_ablation_process.tex": gen_tab_process(pooled),
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

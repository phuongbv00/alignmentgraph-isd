"""LaTeX tables and the prose macro file.

The LLM judge tables lead on ADDIE because it measures instructional-design content
quality -- the construct the study asks about -- while trajectory_score measures
process conformance and total_score's weights come from the benchmark rather
than from this study. All three are reported side by side; none is an endpoint.

The alignment tables carry the whole flat panel. Naming one signal primary
would be an implicit composite.
"""

from __future__ import annotations

import math
from datetime import datetime

from pathlib import Path

from .. import paths
from ..alignment.protocol import ALIGNMENT_SIGNALS
from ..config import AGENT_DISPLAY, AGENT_ORDER, LLM_JUDGE_LEAD, LLM_JUDGE_SD_FIELD
from ..config import current as current_config
from ..latex import fmt_num, fmt_p, header_comment, model_display, size_display, size_of_label, size_word
from ..pool.panel import SUMMARY_SIGNAL

PRODUCER = "isd-exp report tables"






def _size_word(label: str, index: int) -> str:
    return size_word(label, index, current_config().macro_words)


def gen_tab_llm_judge(pooled: dict, field: str = "mean_addie",
                label: str = "ADDIE", tag: str = "llm-judge-ladder",
                caption_metric: str = (
                    "mean per-scenario ADDIE rubric score (/100)")) -> str:
    models = pooled["models"]
    demo = pooled.get("_demo", False)
    agents_present = [a for a in AGENT_ORDER
                      if any(a in m["agents"] for m in models)]
    proposed = pooled["config"]["proposed"]

    # best per size column, for bolding
    best_by_model = {}
    for m in models:
        vals = {a: m["agents"][a][field] for a in agents_present if a in m["agents"]}
        vals = {a: v for a, v in vals.items() if v is not None and not math.isnan(v)}
        best_by_model[m["label"]] = max(vals, key=vals.get) if vals else None

    colspec = "@{}l" + "r@{\\hskip 3pt}r" * len(models) + "@{}"
    demo_note = " [TBD-DEMO: synthetic values, awaiting real ladder runs]" if demo else ""
    lines = [header_comment(
        pooled, f"tab_{tag.replace('-', '_')}.tex — LLM judge ladder table on {label}")]
    lines.append("\\begin{table*}[t]")
    lines.append(
        f"  \\caption{{LLM judge score ({label}) on the model size ladder. Cell: {caption_metric},"
        " with the SD across scenarios in parentheses; $n$ = scenarios scored"
        " in every run of the cell. \\textbf{Bold} = column maximum, not a"
        " significance claim." + demo_note + "}")
    lines.append(f"  \\label{{tab:{tag}}}")
    lines.append("  \\small")
    lines.append(f"  \\begin{{tabular}}{{{colspec}}}")
    lines.append("    \\toprule")
    heads = " & ".join(
        f"\\multicolumn{{2}}{{c}}{{{model_display(m['label'])}}}" for m in models)
    lines.append(f"    & {heads} \\\\")
    cmids = "".join(
        f"\\cmidrule(lr){{{2 + 2 * i}-{3 + 2 * i}}}" for i in range(len(models)))
    lines.append(f"    {cmids}")
    subs = " & ".join([label + " {\\scriptsize(SD)}", "$n$"] * len(models))
    lines.append(f"    Agent & {subs} \\\\")
    lines.append("    \\midrule")
    for a in agents_present:
        name = AGENT_DISPLAY.get(a, a)
        if a == proposed:
            name = f"\\textbf{{{name}}}"
        cells = []
        for m in models:
            s = m["agents"].get(a)
            if not s or s[field] is None or math.isnan(s[field]):
                cells += ["--", "--"]
                continue
            val = fmt_num(s[field])
            if best_by_model.get(m["label"]) == a:
                val = f"\\textbf{{{val}}}"
            sd = s.get(LLM_JUDGE_SD_FIELD[field])
            # `is not None` alone is not enough: a single-run cell carries
            # None here, and an archived pooled file carries nan.
            sd_txt = ("~{\\scriptsize(" + fmt_num(sd, 2) + ")}"
                      if isinstance(sd, float) and not math.isnan(sd) else "")
            n = s["n_scenarios_complete"]
            miss = s.get("n_scenarios_any_missing", 0)
            n_txt = f"{n}" if not miss else f"{n}\\textsuperscript{{*}}"
            cells += [val + sd_txt, n_txt]
        lines.append(f"    {name} & " + " & ".join(cells) + " \\\\")
    lines.append("    \\bottomrule")
    lines.append("  \\end{tabular}")
    lines.append(
        "  \\par\\smallskip\\footnotesize\\textsuperscript{*}$n<$ total scenarios:"
        " the agent failed or produced no output in at least one run"
        " (complete-case; see stats\\_summary.md).")
    lines.append("\\end{table*}")
    return "\n".join(lines) + "\n"


def instrument_note(align: dict) -> str:
    """Which arm of the sensitivity star produced these numbers.

    The pooled file also carries four other arms, so a panel table that names no
    instrument cannot be matched to the sensitivity analysis that supports it.

    Kept out of the caption and put in the table footnote: it is provenance, not
    a description of what a cell holds, and the caption has a length budget.
    """
    enc = align.get("encoder_label", "?")
    bloom = align.get("bloom_classifier", "?")
    return (f"Instrument: primary arm --- encoder \\texttt{{{enc}}}, Bloom"
            f" classifier \\texttt{{{bloom}}}. The other sensitivity-star arms"
            " are reported separately.")


def gen_tab_alignment(pooled: dict) -> str:
    align = pooled.get("alignment")
    demo = pooled.get("_demo", False)
    if not align or not align.get("models"):
        return (header_comment(pooled, "tab_alignment.tex — placeholder")
                + "% No alignment_scores.json data was present in the pooled input.\n"
                  "% Re-run isd-exp comparison pool after the alignment metric\n"
                  "% (alignment scoring) lands in the scenario dirs, then regenerate this file.\n"
                  "% This file intentionally renders nothing.\n")

    model_labels = [m["label"] for m in pooled["models"] if m["label"] in align["models"]]
    # One column per size, for the ONE signal that fits an agents x sizes
    # table. This is a layout constraint, not a hierarchy: the other six panel
    # signals are in tab_alignment_panel.tex, the component figure, and
    # stats_summary.md, all reported with the same statistics.
    agents_present = [a for a in AGENT_ORDER
                      if any(a in align["models"][lb] for lb in model_labels)]

    demo_note = " [TBD-DEMO: synthetic values]" if demo else ""
    # n per cell, mirroring tab_llm_judge's two-column-per-size layout. Without it,
    # cells averaged over as few as 17 scenarios printed identically to
    # full-coverage cells and read as comparable.
    n_union = {m["label"]: m["n_scenarios_union"] for m in pooled["models"]}
    colspec = "@{}l" + "r@{\\hskip 3pt}r" * len(model_labels) + "@{}"
    lines = [header_comment(pooled, "tab_alignment.tex — objective->assessment similarity x model sizes")]
    lines.append("\\begin{table}[t]")
    lines.append(
        "  \\caption{Objective$\\to$assessment similarity, the"
        " \\emph{measures} leg of \\textit{aligned(o)}. Each cell: mean"
        " per-scenario mean-max rectified cosine (SD), pooled mean-of-runs;"
        " $n$ = scenarios with at least one scored run. Remaining"
        f" {len(ALIGNMENT_SIGNALS) - 1} panel"
        " signals: \\Cref{tab:alignment-panel}." + demo_note + "}")
    lines.append("  \\label{tab:alignment}")
    lines.append("  \\small")
    lines.append(f"  \\begin{{tabular}}{{{colspec}}}")
    lines.append("    \\toprule")
    heads = " & ".join(
        f"\\multicolumn{{2}}{{c}}{{{model_display(lb)}}}" for lb in model_labels)
    lines.append(f"    & {heads} \\\\")
    lines.append("    " + "".join(
        f"\\cmidrule(lr){{{2 + 2 * i}-{3 + 2 * i}}}" for i in range(len(model_labels))))
    subs = " & ".join(["Sim. (SD)", "$n$"] * len(model_labels))
    lines.append(f"    Agent & {subs} \\\\")
    lines.append("    \\midrule")
    thin = False
    for a in agents_present:
        name = AGENT_DISPLAY.get(a, a)
        if a == pooled["config"]["proposed"]:
            name = f"\\textbf{{{name}}}"
        cells = []
        for lb in model_labels:
            entry = align["models"][lb].get(a, {}).get("objective_assessment_similarity", {})
            mean, sd = entry.get("mean"), entry.get("sd_across_scenarios")
            n = entry.get("n_scenarios")
            if mean is None:
                cells += ["--", "--"]
                continue
            cells.append(fmt_num(mean, 3) if sd is None
                         else f"{fmt_num(mean, 3)} ({fmt_num(sd, 2)})")
            if n is None:
                cells.append("--")
            elif n < n_union.get(lb, n):
                thin = True
                cells.append(f"{n}\\textsuperscript{{*}}")
            else:
                cells.append(str(n))
        lines.append(f"    {name} & " + " & ".join(cells) + " \\\\")
    lines.append("    \\bottomrule")
    lines.append("  \\end{tabular}")
    note = instrument_note(align)
    if thin:
        note = ("\\textsuperscript{*}$n<$ total scenarios: the agent produced no"
                " scorable output for the rest, or none on which this signal was"
                " defined, so the cell is conditioned on the"
                " scenarios it survived and is not comparable to a full-coverage"
                " cell. $n$ counts scenarios with \\emph{at least one} scored run,"
                " a weaker condition than the all-3-runs complete case used in the"
                " LLM judge score tables. " + note)
    lines.append("  \\par\\smallskip\\footnotesize " + note)
    lines.append("\\end{table}")
    return "\n".join(lines) + "\n"


#: Short LaTeX labels for the panel signals, in ALIGNMENT_SIGNALS order.
PANEL_DISPLAY = {
    "objective_assessment_similarity": "Obj$\\to$Asm sim.",
    "objective_activity_similarity": "Obj$\\to$Act sim.",
    "activity_assessment_similarity": "Act$\\to$Asm sim.",
    "objective_cognitive_congruence": "Cognitive congruence",
    # porter_mean is the MEAN of the three pairwise Porter indices, computed
    # over the same three triad edges family A measures, not a single index.
    "porter_mean": "Mean Porter index",
    "webb_bloom_consistency": "Webb consistency",
}

FAMILY_DISPLAY = {
    "correspondence": "Textual correspondence (encoder)",
    "cognitive": "Cognitive demand (Bloom)",
}


def gen_tab_alignment_panel(pooled: dict) -> str:
    """The whole panel: every signal x every agent, at every model size.

    Deliberately exhaustive. The panel design's defence against selective
    reporting is that every signal is shown for every comparison, so the table
    that backs it cannot be a selection.
    """
    align = pooled.get("alignment")
    demo = pooled.get("_demo", False)
    if not align or not align.get("models"):
        return (header_comment(pooled, "tab_alignment_panel.tex — placeholder")
                + "% No alignment_scores.json data was present in the pooled input.\n"
                  "% This file intentionally renders nothing.\n")

    model_labels = [m["label"] for m in pooled["models"] if m["label"] in align["models"]]
    agents_present = [a for a in AGENT_ORDER
                      if any(a in align["models"][lb] for lb in model_labels)]
    proposed = pooled["config"]["proposed"]
    demo_note = " [TBD-DEMO: synthetic values]" if demo else ""
    n_union = {m["label"]: m["n_scenarios_union"] for m in pooled["models"]}
    thin_cells: list[tuple[str, str, str, int]] = []
    n_cells = len(ALIGNMENT_SIGNALS) * len(model_labels) * len(agents_present)

    colspec = "@{}ll" + "r" * len(agents_present) + "@{}"
    lines = [header_comment(pooled, "tab_alignment_panel.tex — the full alignment-score panel")]
    lines.append("\\begin{table*}[t]")
    lines.append(
        "  \\caption{The full alignment-score panel. Cell: mean per-scenario value,"
        " pooled mean-of-runs. No score is primary; every score is reported for"
        " every comparison."
        " $^{*}$ = fewer scenarios than the full set (see note)."
        + demo_note + "}")
    lines.append("  \\label{tab:alignment-panel}")
    lines.append("  \\small")
    lines.append(f"  \\begin{{tabular}}{{{colspec}}}")
    lines.append("    \\toprule")
    heads = " & ".join(
        f"\\textbf{{{AGENT_DISPLAY.get(a, a)}}}" if a == proposed
        else AGENT_DISPLAY.get(a, a)
        for a in agents_present)
    lines.append(f"    Signal & Size & {heads} \\\\")
    for family in ("correspondence", "cognitive"):
        signals = [s for s, f in ALIGNMENT_SIGNALS if f == family]
        if not signals:
            continue
        lines.append("    \\midrule")
        span = len(agents_present) + 2
        lines.append(f"    \\multicolumn{{{span}}}{{@{{}}l}}{{\\itshape "
                     f"{FAMILY_DISPLAY[family]}}} \\\\")
        for signal in signals:
            for i, lb in enumerate(model_labels):
                head = PANEL_DISPLAY.get(signal, signal) if i == 0 else ""
                cells = []
                for a in agents_present:
                    entry = align["models"][lb].get(a, {}).get(signal, {})
                    mean, n = entry.get("mean"), entry.get("n_scenarios")
                    if mean is None:
                        cells.append("--")
                        continue
                    # 196 cells cannot each carry an n column, so thin coverage is
                    # flagged and the roster lives in stats_summary.md. Unflagged
                    # would mean a 17-scenario cell reads like a 90-scenario one.
                    txt = fmt_num(mean, 3)
                    if n is not None and n < n_union.get(lb, n):
                        thin_cells.append((signal, lb, a, n))
                        txt += "\\textsuperscript{*}"
                    cells.append(txt)
                lines.append(f"    {head} & {size_display(lb)} & "
                             + " & ".join(cells) + " \\\\")
    lines.append("    \\bottomrule")
    lines.append("  \\end{tabular}")
    note = instrument_note(align)
    if thin_cells:
        worst = min(thin_cells, key=lambda t: t[3])
        # Two different events thin a cell and the footnote must not assert
        # only one: the agent produced no scorable output, OR it produced
        # output on which this particular signal was undefined (no
        # Bloom-classifiable text, for the cognitive-demand signals). n is
        # per-signal, so the two are indistinguishable in the cell.
        note = ("\\textsuperscript{*}The agent either produced no scorable output"
                " for the remaining scenarios or produced output on which this"
                " signal was undefined, so the cell is conditioned on those it"
                f" survived ({len(thin_cells)} of {n_cells} cells; smallest"
                f" $n={worst[3]}$ at {AGENT_DISPLAY.get(worst[2], worst[2])} /"
                f" {size_display(worst[1])}). Per-cell $n$ is in"
                " stats\\_summary.md. $n$ counts scenarios with at least one"
                " scored run, a weaker condition than the all-3-runs complete"
                " case used in the LLM judge score tables. " + note)
    lines.append("  \\par\\smallskip\\footnotesize " + note)
    lines.append("\\end{table*}")
    return "\n".join(lines) + "\n"


def gen_macros(pooled: dict) -> tuple[str, str]:
    """Returns (stats_macros.tex, stats_summary.md)."""
    models = pooled["models"]
    proposed = pooled["config"]["proposed"]
    demo = pooled.get("_demo", False)
    words = [_size_word(m["label"], i) for i, m in enumerate(models)]

    tex: list[str] = [header_comment(pooled, "stats_macros.tex — headline numbers for prose")]
    md: list[str] = [
        "# Ladder statistics summary",
        "",
        f"Generated: {datetime.now().isoformat(timespec='seconds')}"
        + ("  \n**TBD-DEMO: every value below is a fake placeholder.**" if demo else ""),
        "",
        f"- Proposed agent: `{proposed}`",
        f"- Size order: {', '.join(m['label'] for m in models)}",
        f"- Pooling: mean of {models[0]['n_runs']} runs per scenario; primary policy complete-case",
        f"- Bootstrap: {pooled['config'].get('n_boot', 10000)} resamples, seed "
        f"{pooled['config'].get('bootstrap_seed', 42)}",
        "- Holm family: 6 comparisons (proposed vs each baseline) per model size",
        "",
    ]

    def newcmd(name: str, value: str, desc: str) -> None:
        tex.append(f"% {desc}")
        tex.append(f"\\newcommand{{\\{name}}}{{{value}}}")

    newcmd("ladderNumModels", str(len(models)), "number of model sizes in the ladder")
    newcmd("ladderNumRunsPerModel", str(models[0]["n_runs"]),
           "independent runs per model size")
    n_scen = max(m["n_scenarios_union"] for m in models)
    newcmd("ladderNumScenarios", str(n_scen), "scenarios per run (test_90)")
    newcmd("ladderNumAgents", str(len(pooled["config"]["baselines"]) + 1),
           "agents compared (6 baselines + proposed)")

    all_p_holm: list[float] = []
    for m, w in zip(models, words):
        agents = m["agents"]
        rows = m["comparisons"]["by_score"][LLM_JUDGE_LEAD]["policies"]["complete_case"]
        rows_p = [r for r in rows if "p_holm" in r]
        harness = agents.get(proposed, {})
        base_vals = {a: s["mean_addie"] for a, s in agents.items()
                     if a != proposed and s["mean_addie"] is not None
                     and not math.isnan(s["mean_addie"])}
        best_b = max(base_vals, key=base_vals.get) if base_vals else None

        md += [f"## {m['label']} (macro suffix: {w})", ""]
        newcmd(f"llmJudgeHarnessAddie{w}", fmt_num(harness.get("mean_addie", float("nan"))),
               f"{proposed} pooled mean ADDIE (lead LLM judge score) at {m['label']}")
        newcmd(f"llmJudgeHarnessTraj{w}", fmt_num(harness.get("mean_traj", float("nan"))),
               f"{proposed} pooled mean Trajectory at {m['label']}")
        newcmd(f"llmJudgeHarnessTotal{w}", fmt_num(harness.get("mean_total", float("nan"))),
               f"{proposed} pooled mean Total (benchmark composite) at {m['label']}")
        # Across-scenario SD, not run-to-run: with one deterministic run per
        # cell there are no run-level means to take an SD of. Emitted only when
        # it exists, so a cell without it leaves the macro undefined and LaTeX
        # says so, rather than the prose quoting a silent "nan".
        sd_addie = harness.get("sd_addie_across_scenarios")
        if isinstance(sd_addie, float) and not math.isnan(sd_addie):
            newcmd(f"llmJudgeHarnessSDAddie{w}", fmt_num(sd_addie),
                   f"{proposed} SD across scenarios of ADDIE at {m['label']} "
                   f"(ADDIE, matching the lead signal — NOT the Total SD, and "
                   f"NOT a run-to-run SD)")
        if best_b:
            newcmd(f"llmJudgeBestBaselineAddie{w}", fmt_num(base_vals[best_b]),
                   f"best baseline ({best_b}) pooled mean ADDIE at {m['label']}")
            newcmd(f"llmJudgeBestBaselineName{w}", AGENT_DISPLAY.get(best_b, best_b),
                   f"name of the best baseline at {m['label']}")
            # Total of the SAME baseline the lead signal named, not the best
            # Total on the ladder: the prose quotes this right next to
            # \llmJudgeBestBaselineName, and re-picking the argmax per signal would
            # name one baseline while reporting a different one's number.
            newcmd(f"llmJudgeBestBaselineTotal{w}",
                   fmt_num(agents[best_b].get("mean_total")),
                   f"that same baseline ({best_b}) pooled mean Total "
                   f"(benchmark composite) at {m['label']}")
            row = next((r for r in rows_p if r["baseline"] == best_b), None)
            if row:
                # Every delta/CI/p macro here is ADDIE. The names carry no signal
                # suffix, so the comment must: the file also emits Total macros,
                # and prose that quotes a Total level beside an unlabelled "delta"
                # silently attributes an ADDIE difference to Total.
                newcmd(f"llmJudgeDeltaBestAddie{w}", fmt_num(row["mean_diff"]),
                       f"ADDIE mean paired delta {proposed} - {best_b} at "
                       f"{m['label']} (n={row['n']})")
                newcmd(f"llmJudgeDeltaBestAddieCILo{w}", fmt_num(row["ci95"][0]),
                       "bootstrap 95% CI lower bound of that ADDIE delta")
                newcmd(f"llmJudgeDeltaBestAddieCIHi{w}", fmt_num(row["ci95"][1]),
                       "bootstrap 95% CI upper bound of that ADDIE delta")
                newcmd(f"llmJudgeDeltaBestAddieN{w}", str(row["n"]),
                       "paired scenarios backing that ADDIE delta")
        if rows_p:
            pmax = max(r["p_holm"] for r in rows_p)
            all_p_holm.append(pmax)
            newcmd(f"llmJudgePHolmMax{w}", fmt_p(pmax),
                   f"max Holm-adjusted p over the 6 ADDIE comparisons at {m['label']}")

        # Lead signal first: the paired table printed below is computed on ADDIE,
        # so leading this bullet with Total made the note headline one signal and
        # tabulate another, with the lead value appearing nowhere.
        def _sd_txt(key: str) -> str:
            v = harness.get(key)
            return f"{v:.4f}" if isinstance(v, float) and not math.isnan(v) else "n/a"

        md.append(
            f"- {proposed}: ADDIE={harness.get('mean_addie'):.4f} (LEAD signal, "
            f"sdScen={_sd_txt('sd_addie_across_scenarios')}), "
            f"Traj={harness.get('mean_traj'):.4f} "
            f"(sdScen={_sd_txt('sd_traj_across_scenarios')}), "
            f"Total={harness.get('mean_total'):.4f} "
            f"(sdScen={_sd_txt('sd_total_across_scenarios')}), "
            f"nCC={harness.get('n_scenarios_complete')}, "
            f"missing={harness.get('n_scenarios_any_missing')}")
        md.append("  Each sdScen is the SD across scenarios of that signal; they "
                  "are not interchangeable, and none of them is a run-to-run SD "
                  "— with one run per cell that quantity does not exist. "
                  f"Run-to-run SD of Total: {_sd_txt('run_to_run_sd_total')}.")
        md.append("")
        md.append("| baseline | n | mean diff | 95% CI | W+ | r_rb | p | p_holm |")
        md.append("|---|---|---|---|---|---|---|---|")
        for r in rows:
            if "p_raw" not in r:
                md.append(f"| {r['baseline']} | 0 | -- | -- | -- | -- | -- | -- |")
                continue
            md.append(
                f"| {r['baseline']} | {r['n']} | {r['mean_diff']:+.4f} "
                f"| [{r['ci95'][0]:+.4f}, {r['ci95'][1]:+.4f}] "
                f"| {r['wilcoxon_w_plus']:.1f} | {r['rank_biserial_r']:+.3f} "
                f"| {r['p_raw']:.3e} | {r['p_holm']:.3e} |")
        md.append("")
        md.append("Sensitivity (mean diff under imputation policies):")
        for policy in ("zero", "min_score"):
            vals = ", ".join(
                f"{r['baseline']}={r['mean_diff']:+.2f}"
                for r in m["comparisons"]["by_score"][LLM_JUDGE_LEAD]["policies"][policy]
                if "mean_diff" in r)
            md.append(f"- {policy}: {vals}")
        md.append("")

    if all_p_holm:
        newcmd("llmJudgePHolmMaxAll", fmt_p(max(all_p_holm)),
               "max Holm-adjusted p across ALL sizes x baselines (complete-case)")

    # scale drop of the proposed agent: Total(largest) - Total(smallest)
    h_small = models[0]["agents"].get(proposed, {}).get("mean_total", float("nan"))
    h_large = models[-1]["agents"].get(proposed, {}).get("mean_total", float("nan"))
    newcmd("llmJudgeHarnessTotalGainLargestOverSmallest", fmt_num(h_large - h_small),
           f"{proposed} mean TOTAL (benchmark composite, not the lead signal) at "
           f"{models[-1]['label']} minus {models[0]['label']}; positive = the "
           f"larger model scores higher")

    inter = pooled.get("interaction", {})
    md += ["## Interaction (method x model size, DiD largest - smallest)", "",
           inter.get("definition", ""), ""]
    # NOT the agent literally named `baseline`. That agent is the degenerate
    # single-prompt one: it fails most scenarios at the small end, so its DiD
    # rested on 5 paired scenarios and its OLS slope on 1, while the macro was
    # quoted in prose as if it characterised the ladder. The comparison is taken
    # against the STRONGEST baseline at the largest size instead — a pre-statable
    # rule, the most conservative contrast, and adequately covered. Every macro
    # here carries its n so prose cannot quote the estimate without the support.
    did_ref = None
    if models:
        last = models[-1]["agents"]
        cand = {a: s["mean_addie"] for a, s in last.items()
                if a != proposed and s.get("mean_addie") is not None
                and not math.isnan(s["mean_addie"])}
        if cand:
            did_ref = max(cand, key=cand.get)
    row = next((r for r in inter.get("per_baseline", []) if r["baseline"] == did_ref),
               None)
    if row:
        newcmd("llmJudgeDiDBaselineName", AGENT_DISPLAY.get(did_ref, did_ref),
               "baseline the DiD is taken against: strongest baseline by ADDIE at "
               "the largest size")
        newcmd("llmJudgeDiDVsBestBaseline", fmt_num(row["did_mean"]),
               f"DiD of delta(proposed - {did_ref}) on ADDIE: largest minus "
               f"smallest size (n={row['n_paired_scenarios']} paired scenarios)")
        newcmd("llmJudgeDiDVsBestBaselineCILo", fmt_num(row["did_ci95"][0]),
               "bootstrap 95% CI lower bound of that DiD")
        newcmd("llmJudgeDiDVsBestBaselineCIHi", fmt_num(row["did_ci95"][1]),
               "bootstrap 95% CI upper bound of that DiD")
        newcmd("llmJudgeDiDVsBestBaselineP", fmt_p(row["did_wilcoxon_p"]),
               "Wilcoxon p of the per-scenario DiD values vs 0")
        newcmd("llmJudgeDiDVsBestBaselineN", str(row["n_paired_scenarios"]),
               "paired scenarios backing that DiD")
        newcmd("llmJudgeTrendSlopeVsBaseline", fmt_num(row["trend_ols_slope_per_size_step"]),
               f"OLS slope of delta(proposed - {did_ref}) per size step over "
               f"{len(models)} sizes (n={row.get('trend_n_common_scenarios')} "
               "scenarios common to all sizes)")
        newcmd("llmJudgeTrendSlopeVsBaselineN", str(row.get("trend_n_common_scenarios")),
               "scenarios common to all sizes backing that slope")
    for r in inter.get("per_baseline", []):
        md.append(
            f"- vs {r['baseline']}: n={r['n_paired_scenarios']}, "
            f"DiD={r['did_mean']:+.4f} CI[{r['did_ci95'][0]:+.4f}, {r['did_ci95'][1]:+.4f}] "
            f"p={r['did_wilcoxon_p']:.3e}; trend "
            + " ".join(f"{k}:{v:+.2f}" for k, v in r["trend_delta_by_size"].items())
            + f"; slope/step={r['trend_ols_slope_per_size_step']:+.4f} "
              f"CI[{r['trend_slope_ci95'][0]:+.4f}, {r['trend_slope_ci95'][1]:+.4f}]")
    md.append("")

    align = pooled.get("alignment")
    md.append("## Alignment metrics")
    if align and align.get("models"):
        for lb, agents_metrics in align["models"].items():
            md.append(f"### {lb}")
            for agent, metrics in agents_metrics.items():
                parts = ", ".join(f"{mt}={v['mean']:.4f} (SD {v['sd_across_scenarios']:.4f}, "
                                  f"n={v['n_scenarios']})" for mt, v in metrics.items())
                md.append(f"- {agent}: {parts}")
    else:
        md.append("No alignment_scores.json data in the pooled input — skipped.")
    md.append("")

    if align and align.get("stats", {}).get("per_model"):
        md.append("## Alignment panel (every score, descriptive + paired, proposed vs baselines)")
        md.append("")
        md.append("No score is primary: each is reported for every comparison, "
                  "win or lose. `p_holm` corrects within one signal (6 "
                  "comparisons); `p_panel` corrects over the whole panel x "
                  "baseline family for that size.")
        md.append("")
        all_align_p: list[float] = []
        all_panel_p: list[float] = []
        for m, w in zip(models, words):
            per = next((s for s in align["stats"]["per_model"]
                        if s["label"] == m["label"]), None)
            if not per:
                continue
            md.append(f"### {m['label']}")
            # The failure roster belongs next to the numbers it conditions: every
            # complete-case mean below is over available outputs only, so without
            # this a survivorship mean reads like a full-coverage one.
            fails = per.get("align_failures") or {}
            if fails:
                md.append("**Missing outputs (complete-case layer is conditioned on these):** "
                          + ", ".join(
                              f"`{a}` {v['n_scenarios_affected']} scenario(s), "
                              f"{v['n_agent_run_cells_missing']} agent-run cell(s)"
                              for a, v in sorted(fails.items())))
                md.append("")
            for signal, layers in (per.get("panel") or {}).items():
                rows = layers.get("comparisons") or []
                desc = layers.get("align_descriptive", {})
                is_lead = signal == SUMMARY_SIGNAL
                harness_desc = desc.get(proposed)
                if harness_desc and is_lead:
                    newcmd(f"alignmentHarnessSim{w}", fmt_num(harness_desc["mean"], 3),
                           f"{proposed} mean {SUMMARY_SIGNAL} at {m['label']} "
                           f"(1 of the {len(ALIGNMENT_SIGNALS)} alignment signals; the "
                           "panel has no primary endpoint, so this is not a "
                           "summary of the panel — see tab_alignment_panel.tex for all "
                           f"{len(ALIGNMENT_SIGNALS)})")
                    newcmd(f"alignmentHarnessSimCILo{w}", fmt_num(harness_desc["ci95"][0], 3),
                           "bootstrap 95% CI lower bound of that mean")
                    newcmd(f"alignmentHarnessSimCIHi{w}", fmt_num(harness_desc["ci95"][1], 3),
                           "bootstrap 95% CI upper bound of that mean")
                rows_p = [r for r in rows if "p_holm" in r]
                if rows_p and is_lead:
                    pmax = max(r["p_holm"] for r in rows_p)
                    all_align_p.append(pmax)
                    newcmd(f"alignmentSimPHolmMax{w}", fmt_p(pmax),
                           f"max Holm-adjusted p over the {SUMMARY_SIGNAL} "
                           f"comparisons at {m['label']}")
                all_panel_p += [r["p_holm_panel"] for r in rows if "p_holm_panel" in r]

                flag = "" if layers.get("directional", True) else \
                    " — diagnostic, direction not one-way-good"
                md.append(f"#### {signal} [{layers.get('family')}]{flag}")
                if desc:
                    md.append("mean [bootstrap CI95] per agent: " + ", ".join(
                        f"{a}={v['mean']:.3f} [{v['ci95'][0]:.3f}, {v['ci95'][1]:.3f}] (n={v['n']})"
                        for a, v in desc.items()))
                cond = layers.get("conditional_align", {})
                if cond:
                    md.append("conditional (>=1 objective): " + ", ".join(
                        f"{a}={v['mean']:.3f} (n={v['n']})" for a, v in cond.items()))
                md.append("")
                md.append("complete-case (over AVAILABLE outputs, not unconditional):")
                md.append("")
                md.append("| baseline | n | mean diff | 95% CI | p_holm | p_panel |")
                md.append("|---|---|---|---|---|---|")
                for r in rows:
                    if "p_raw" not in r:
                        md.append(f"| {r['baseline']} | 0 | -- | -- | -- | -- |")
                        continue
                    panel_p = r.get("p_holm_panel")
                    md.append(
                        f"| {r['baseline']} | {r['n']} | {r['mean_diff']:+.4f} "
                        f"| [{r['ci95'][0]:+.4f}, {r['ci95'][1]:+.4f}] "
                        f"| {r['p_holm']:.3e} "
                        f"| {'--' if panel_p is None else f'{panel_p:.3e}'} |")
                md.append("")
                # The mandated second pass: a missing output scores 0 rather than
                # dropping out, so the two layers bracket the survivorship effect.
                fz_rows = layers.get("comparisons_failure_zero") or []
                fz_desc = layers.get("failure_zero_descriptive") or {}
                if fz_desc:
                    md.append("failure=0 mean per agent: " + ", ".join(
                        f"{a}={v['mean']:.3f} (n={v['n']})"
                        for a, v in sorted(fz_desc.items())))
                if fz_rows:
                    md.append("")
                    md.append("failure=0 (missing output scored 0):")
                    md.append("")
                    md.append("| baseline | n | mean diff | 95% CI | p_holm |")
                    md.append("|---|---|---|---|---|")
                    for r in fz_rows:
                        if "p_raw" not in r:
                            md.append(f"| {r['baseline']} | 0 | -- | -- | -- |")
                            continue
                        md.append(
                            f"| {r['baseline']} | {r['n']} | {r['mean_diff']:+.4f} "
                            f"| [{r['ci95'][0]:+.4f}, {r['ci95'][1]:+.4f}] "
                            f"| {r['p_holm']:.3e} |")
                    md.append("")
        if all_align_p:
            newcmd("alignmentSimPHolmMaxAll", fmt_p(max(all_align_p)),
                   f"max Holm-adjusted p across ALL sizes for {SUMMARY_SIGNAL} ONLY "
                   f"— 1 of the {len(ALIGNMENT_SIGNALS)} alignment signals, corrected "
                   "within that signal (6 comparisons). For the whole-panel "
                   "family use alignmentPanelPHolmMaxAll; prose must not present "
                   "this as a panel-wide result")
        if all_panel_p:
            newcmd("alignmentPanelPHolmMaxAll", fmt_p(max(all_panel_p)),
                   "max p across ALL sizes and ALL alignment signals under the "
                   "conservative whole-panel Holm correction")

        inter = align["stats"].get("interaction_align")
        if inter:
            md.append(f"### Interaction (objective->assessment similarity DiD, "
                      f"{inter['largest']} - {inter['smallest']})")
            md.append(inter.get("definition", ""))
            for r in inter.get("per_baseline", []):
                if not r.get("n_paired_scenarios"):
                    md.append(f"- vs {r['baseline']}: no paired scenarios")
                    continue
                md.append(
                    f"- vs {r['baseline']}: n={r['n_paired_scenarios']}, "
                    f"DiD={r['did_mean']:+.4f} "
                    f"CI[{r['did_ci95'][0]:+.4f}, {r['did_ci95'][1]:+.4f}] "
                    f"p={r['did_wilcoxon_p']:.3e}")
                # Same fix as the LLM judge DiD block: not the degenerate agent named
                # `baseline`, whose pairing collapses at the small end.
                if r["baseline"] == did_ref:
                    newcmd("alignmentSimDiDVsBaseline", fmt_num(r["did_mean"], 3),
                           f"objective->assessment similarity DiD (largest - "
                           f"smallest size) of delta(proposed - {did_ref}), "
                           f"n={r['n_paired_scenarios']} paired scenarios")
                    newcmd("alignmentSimDiDVsBaselineCILo", fmt_num(r["did_ci95"][0], 3),
                           "bootstrap 95% CI lower bound of that similarity DiD")
                    newcmd("alignmentSimDiDVsBaselineCIHi", fmt_num(r["did_ci95"][1], 3),
                           "bootstrap 95% CI upper bound of that similarity DiD")
                    newcmd("alignmentSimDiDVsBaselineP", fmt_p(r["did_wilcoxon_p"]),
                           "Wilcoxon p of the per-scenario similarity DiD values vs 0")
                    newcmd("alignmentSimDiDVsBaselineN", str(r["n_paired_scenarios"]),
                           "paired scenarios backing that similarity DiD")
            md.append("")

    if demo:
        newcmd("ladderDataIsDemo", "TBD-DEMO",
               "sentinel: nonempty means the generated numbers are placeholders")
    return "\n".join(tex) + "\n", "\n".join(md) + "\n"


#: Artifact name -> how it is produced. Names are semantic: the two measurement
#: families are `llm_judge` and `alignment`, so a reader of a filename knows what
#: is in it without consulting a numbering scheme.
def build(pooled: dict) -> dict[str, str]:
    """Every table this command writes, as {filename: content}."""
    macros_tex, summary_md = gen_macros(pooled)
    return {
        "tab_llm_judge_addie.tex": gen_tab_llm_judge(pooled),
        # The benchmark composite, reported in full rather than dropped: it is
        # the benchmark's own canonical number, so comparability needs it.
        "tab_llm_judge_total.tex": gen_tab_llm_judge(
            pooled, field="mean_total", label="Total", tag="llm-judge-ladder-total",
            caption_metric=(
                "mean per-scenario \\texttt{total\\_score}"
                " ($0.7\\,$ADDIE$+0.3\\,$Traj), the benchmark's own composite")),
        "tab_llm_judge_trajectory.tex": gen_tab_llm_judge(
            pooled, field="mean_traj", label="Traj", tag="llm-judge-ladder-traj",
            caption_metric="mean per-scenario Trajectory score (BFCL tool-use, /100)"),
        "tab_alignment.tex": gen_tab_alignment(pooled),
        "tab_alignment_panel.tex": gen_tab_alignment_panel(pooled),
        "stats_macros.tex": macros_tex,
        "stats_summary.md": summary_md,
    }


def run(*, pooled_path: Path | None = None, outdir: Path | None = None,
        quiet: bool = False) -> list[Path]:
    """Read the pooled file, write every table. Returns the paths written."""
    from .. import schema

    src = pooled_path or (paths.results_root() / "pooled_comparison.json")
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

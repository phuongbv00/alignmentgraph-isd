"""One file holding every summary number, under an explicit reading contract.

Exists because the numbers are spread across several macro files and stats
notes, each with its own sign convention, and a reader (or an author drafting
prose) reconciling them by hand is how a sign gets flipped in a sentence. The
reading contract at the top says how to read each block before any number
appears.
"""

from __future__ import annotations

import json
import math
import re
from datetime import datetime
from pathlib import Path

from .. import paths
from ..alignment.protocol import ALIGNMENT_SIGNALS
from ..config import AGENT_DISPLAY, LLM_JUDGE_LEAD, LLM_JUDGE_SCORES
from ..plots import PROPOSED

PRODUCER = "isd-exp report facts"





ARM_LABELS = {
    "alignmentgraph-isd-single-prose": "A1 - single-agent, prose context",
    "alignmentgraph-isd-single-graph": "A2 - single-agent, graph context",
    "alignmentgraph-isd-multi-prose": "A3 - multi-agent, prose context",
}

MACRO_FILES = ("stats_macros.tex", "abl_macros.tex", "cost_macros.tex", "sens_macros.tex")
MACRO_RE = re.compile(r"\\newcommand\{\\([A-Za-z]+)\}\{(.*?)\}\s*(?:%(.*))?$")

SIG_ALPHA = 0.05


# ── formatting ─────────────────────────────────────────────────────────────────
# Decimal POINT everywhere, English throughout (repo convention: generated
# artifacts are English and render 87.77, never 87,77).

def num(value, digits=3):
    if value is None:
        return "--"
    if isinstance(value, bool):
        return str(value)
    try:
        return f"{float(value):.{digits}f}"
    except (TypeError, ValueError):
        return str(value)


def signed(value, digits=3):
    if value is None:
        return "--"
    return f"{float(value):+.{digits}f}"


def pval(value):
    if value is None:
        return "--"
    v = float(value)
    if v == 0:
        return "0"
    return f"{v:.3g}"


def ci(pair, digits=3):
    if not pair or len(pair) != 2:
        return "--"
    return f"[{float(pair[0]):+.{digits}f}, {float(pair[1]):+.{digits}f}]"


def verdict(p, alpha=SIG_ALPHA):
    if p is None:
        return "n/a"
    return "SIG" if float(p) < alpha else "n.s."


# ── data access helpers ────────────────────────────────────────────────────────

def llm_judge_comparisons(model_block, score, policy=None):
    """LLM judge comparison rows for one score under one failure policy.

    ``policy`` defaults to the block's own primary policy (failure = 0).
    Direction as stored: mean_diff = proposed - baseline (positive favours the
    proposed harness).
    """
    comp = model_block.get("comparisons") or {}
    by_score = comp.get("by_score") or {}
    sig = by_score.get(score) or {}
    rows = (sig.get("policies") or {}).get(policy or comp.get("primary_policy")) or []
    return rows if isinstance(rows, list) else []


def panel_blocks(pooled):
    """[(size_label, {signal: block})] from the alignment panel."""
    stats = ((pooled.get("alignment") or {}).get("stats") or {})
    out = []
    for per_model in stats.get("per_model") or []:
        out.append((per_model.get("label", "?"), per_model.get("panel") or {}))
    return out


def panel_signal_names(pooled):
    """Signal names in panel order.

    ``panel_signals`` carries dicts ({signal, family, directional}), not bare
    strings — normalise so every caller gets names.
    """
    stats = ((pooled.get("alignment") or {}).get("stats") or {})
    names = []
    for entry in stats.get("panel_signals") or []:
        names.append(entry.get("signal") if isinstance(entry, dict) else str(entry))
    names = [n for n in names if n]
    if names:
        return names
    for _, panel in panel_blocks(pooled):
        return list(panel)
    return []


# ── section 0: the reading contract ────────────────────────────────────────────

def sec_reading_contract(lad, abl):
    L = []
    L.append("## 0. Reading contract - READ BEFORE QUOTING ANY NUMBER\n")
    L.append("**There are two measurement families in this file. They are measured by mechanically "
             "different instruments, they are on different scales, and they can DISAGREE. "
             "Never quote a number without naming its family.**\n")
    L.append("| Family | Measures | Scale | Instrument |")
    L.append("|---|---|---|---|")
    L.append(f"| LLM JUDGE (`llm_judge`) | `{'`, `'.join(LLM_JUDGE_SCORES)}` | rubric points /100 | LLM judge rubric |")
    L.append(f"| PANEL (alignment) | `{'`, `'.join(panel_signal_names(lad))}` | [0, 1] | deterministic, no LLM |")
    L.append("")
    L.append(f"`{LLM_JUDGE_LEAD}` LEADS the LLM judge narrative because it matches the construct the research "
             "question is about, but it is NOT an endpoint: all three LLM judge scores are reported "
             "side by side. The panel has NO primary endpoint at all - it is flat by design, so "
             "calling any one panel signal 'primary' reintroduces the composite the protocol removes.\n")
    L.append("### Sign conventions\n")
    L.append("Each table below restates its own direction in its header.\n")
    L.append("- **LLM judge / panel comparisons**: `mean_diff = proposed - baseline`. Positive favours "
             "the proposed harness.")
    L.append(f"- **Ablation** (registered tests and the 2x2 factorial): "
             f"{(abl.get('config') or {}).get('direction') or 'richer setting minus plainer one: multi - single, graph - prose'}. "
             "Positive = the richer setting scores higher.\n")
    L.append("### Tests and multiplicity\n")
    L.append("- Every comparison is a paired Wilcoxon test (exact null) with a BCa bootstrap CI "
             "and a rank-biserial r.")
    L.append("- `p_holm` = Holm within one measure - one LLM judge score or one alignment "
             "signal - over the baselines of one size. There is no panel-wide correction.")
    L.append("- Ablation: the ONLY tests are the registered ones (H-D, H-S per size, H-C per axis), "
             "Holm over exactly that family. The 2x2 factorial is DESCRIPTIVE (mean and CI, no p). "
             "The secondary interaction contrasts are pre-specified and UNCORRECTED.")
    L.append("- The scale-interaction (DiD, method x model size) Wilcoxon p values are "
             "UNCORRECTED - outside every Holm family - and carry no significance verdict.\n")
    L.append("### Failure policies\n")
    L.append("Failure = 0 carries every claim: a scenario where a system left no scorable output "
             "in a run counts 0 there, so every mean covers every scenario. Complete-case "
             "(sensitivity) drops those scenarios and is over AVAILABLE outputs - never describe "
             "it as unconditional. Failure rates are descriptive counts.\n")
    L.append("### NOT in this file\n")
    L.append("- Cost ratios and token/quality economics -> `stats_cost.md`, `cost_macros.tex` "
             "(computed from run dirs, not from the pooled JSONs).")
    L.append("- Bloom classifier validity evidence -> `bloom_validation.md`, "
             "`bloom_objectives_validation.md`, `bloom_questions_validation.md`.")
    L.append("- Per-scenario values. Everything here is aggregated to (size, agent, measure).")
    L.append("- Figures. See `results/generated/figures/`.\n")
    return L


# ── section 1: provenance ──────────────────────────────────────────────────────

def sec_provenance(lad, abl):
    L = ["## 1. Provenance and coverage\n"]
    align = lad.get("alignment") or {}
    cfg = lad.get("config") or {}
    L.append("| Field | Value |")
    L.append("|---|---|")
    L.append(f"| pooled_comparison.json generated_at | {lad.get('generated_at', '?')} |")
    L.append(f"| pooled_ablation.json generated_at | {abl.get('generated_at', '?')} |")
    L.append(f"| proposed agent | `{cfg.get('proposed', PROPOSED)}` |")
    L.append(f"| baselines | {', '.join('`%s`' % b for b in cfg.get('baselines', []))} |")
    L.append(f"| model sizes | {', '.join(cfg.get('size_order', []))} |")
    L.append(f"| pooling | {cfg.get('pooling', '?')} |")
    L.append(f"| primary failure policy | {cfg.get('primary_failure_policy', '?')} |")
    L.append(f"| sensitivity failure policy | {cfg.get('sensitivity_failure_policy', '?')} |")
    L.append(f"| bootstrap | {cfg.get('bootstrap_method', '?')}, n={cfg.get('n_boot', '?')}, "
             f"seed={cfg.get('bootstrap_seed', '?')} |")
    L.append(f"| encoder (primary) | {align.get('encoder_label', '?')} |")
    L.append(f"| encoder revision pinned | {align.get('encoder_revision_pinned', '?')} "
             f"({align.get('encoder_revision', '?')}) |")
    L.append(f"| Bloom classifier | {align.get('bloom_classifier', '?')} |")
    L.append(f"| alignment scenario files | {align.get('n_scenario_files', '?')} / "
             f"{align.get('n_scenario_files_expected', '?')} "
             f"(complete: {align.get('coverage_complete', '?')}) |")
    L.append("")
    L.append("Per size: runs and scenario union.\n")
    L.append("| Size | n_runs | n_scenarios_union |")
    L.append("|---|---|---|")
    for m in lad.get("models") or []:
        L.append(f"| {m.get('label','?')} | {m.get('n_runs','?')} | {m.get('n_scenarios_union','?')} |")
    L.append("")
    flag = abl.get("flag_check") or {}
    bad = [f"{size}/{agent}={state}"
           for size, agents in flag.items()
           for agent, state in (agents or {}).items() if state != "ok"]
    L.append(f"**Ablation arm flag check**: {'ALL OK' if not bad else 'PROBLEM -> ' + ', '.join(bad)} "
             "(verifies `metadata.run_config` matches the agent id each arm was registered under).\n")
    cons = (abl.get("reference_drift") or {}).get("per_model") or []
    if cons:
        L.append("**A0 pooling invariant** (ablation vs ladder, on `total_score`; must be ~0 - this "
                 "checks both poolings read the same data, it is NOT a drift measurement, and "
                 "these A0 numbers are deliberately on a different LLM judge score from the ADDIE means "
                 "reported everywhere else):\n")
        L.append("| Size | A0 (ablation) | A0 (ladder) | delta | ladder run-to-run SD | within 2xSD |")
        L.append("|---|---|---|---|---|---|")
        for row in cons:
            L.append(f"| {row.get('label','?')} | "
                     f"{num(row.get('a0_mean_total_ablation_session'), 2)} | "
                     f"{num(row.get('a0_mean_total_ladder_pooled'), 2)} | "
                     f"{signed(row.get('delta'), 4)} | "
                     f"{num(row.get('ladder_run_to_run_sd'))} | "
                     f"{row.get('within_2x_ladder_run_sd', '--')} |")
        L.append("")
    return L


# ── section 2: roll-ups ────────────────────────────────────────────────────────

def rollup_llm_judge(lad):
    """For each baseline x LLM judge score: how many sizes the proposed agent wins
    significantly, and the delta range. Pre-computed so nobody counts by eye."""
    L = ["### 2.1 LLM judge scores - proposed vs each baseline\n",
         "Direction: `proposed - baseline`, failure = 0. "
         "`sizes SIG+` counts sizes with p_holm < 0.05 AND a positive delta; "
         "`sizes SIG-` counts sizes significant in the baseline's favour.\n",
         "| Signal | Baseline | sizes SIG+ | sizes SIG- | sizes n.s. | delta range |",
         "|---|---|---|---|---|---|"]
    models = lad.get("models") or []
    for signal in LLM_JUDGE_SCORES:
        per_baseline = {}
        for m in models:
            for row in llm_judge_comparisons(m, signal):
                per_baseline.setdefault(row.get("baseline"), []).append(row)
        for baseline, rows in sorted(per_baseline.items()):
            pos = sum(1 for r in rows if r.get("p_holm") is not None
                      and r["p_holm"] < SIG_ALPHA and r.get("mean_diff", 0) > 0)
            neg = sum(1 for r in rows if r.get("p_holm") is not None
                      and r["p_holm"] < SIG_ALPHA and r.get("mean_diff", 0) < 0)
            ns = len(rows) - pos - neg
            diffs = [r.get("mean_diff") for r in rows if r.get("mean_diff") is not None]
            rng = f"{signed(min(diffs), 2)} .. {signed(max(diffs), 2)}" if diffs else "--"
            L.append(f"| `{signal}` | `{baseline}` | {pos}/{len(rows)} | {neg}/{len(rows)} | "
                     f"{ns}/{len(rows)} | {rng} |")
    L.append("")
    return L


def rollup_panel(lad):
    L = ["### 2.2 alignment panel - proposed vs each baseline\n",
         "Direction: `proposed - baseline`, failure = 0. Verdict uses `p_holm` "
         "(Holm within the signal).\n",
         "| Signal | Baseline | sizes SIG+ | sizes SIG- | sizes n.s. | delta range |",
         "|---|---|---|---|---|---|"]
    blocks = panel_blocks(lad)
    for signal in panel_signal_names(lad):
        per_baseline = {}
        for _, panel in blocks:
            block = panel.get(signal) or {}
            for row in block.get("comparisons") or []:
                per_baseline.setdefault(row.get("baseline"), []).append(row)
        for baseline, rows in sorted(per_baseline.items()):
            pos = sum(1 for r in rows if r.get("p_holm") is not None
                      and r["p_holm"] < SIG_ALPHA and r.get("mean_diff", 0) > 0)
            neg = sum(1 for r in rows if r.get("p_holm") is not None
                      and r["p_holm"] < SIG_ALPHA and r.get("mean_diff", 0) < 0)
            ns = len(rows) - pos - neg
            diffs = [r.get("mean_diff") for r in rows if r.get("mean_diff") is not None]
            rng = f"{signed(min(diffs))} .. {signed(max(diffs))}" if diffs else "--"
            L.append(f"| `{signal}` | `{baseline}` | {pos}/{len(rows)} | {neg}/{len(rows)} | "
                     f"{ns}/{len(rows)} | {rng} |")
    L.append("")
    return L


#: The four simple effects and the interaction of one factorial row, as
#: (key, short label). Every effect reads richer minus plainer.
FACTORIAL_EFFECTS = (
    ("decomposition_effect_given_context_graph", "decomp | ctx=graph"),
    ("decomposition_effect_given_context_prose", "decomp | ctx=prose"),
    ("context_effect_given_decomposition_multi", "ctx | decomp=multi"),
    ("context_effect_given_decomposition_single", "ctx | decomp=single"),
    ("interaction", "interaction"),
)

#: Each main effect is the mean of its two simple effects (both are taken over
#: the same scenarios, the ones with all four cells).
MAIN_EFFECTS = {
    "decomposition": ("decomposition_effect_given_context_graph",
                      "decomposition_effect_given_context_prose"),
    "substrate": ("context_effect_given_decomposition_multi",
                  "context_effect_given_decomposition_single"),
}


def factorial_rows(abl, measure):
    """[row] per size for one factorial measure, rows without a 2x2 dropped."""
    block = ((abl.get("factorial") or {}).get("measures") or {}).get(measure) or {}
    return [r for r in block.get("per_model") or [] if r.get("cell_means")]


def main_effect(row, axis):
    """Descriptive main effect of one axis on one factorial row, or None."""
    vals = [(row.get(k) or {}).get("mean_diff") for k in MAIN_EFFECTS[axis]]
    if any(v is None for v in vals):
        return None
    return sum(vals) / 2


def rollup_ablation(abl, lad):
    """The registered tests: the only inferential claims the ablation makes."""
    reg = abl.get("registered") or {}
    family = reg.get("family") or []
    L = ["### 2.3 Ablation - the registered tests\n",
         "Direction: the richer setting minus the plainer one (`multi - single`, "
         "`graph - prose`); H-C = effect at the smallest size minus at the largest. "
         f"Failure = {reg.get('failure_policy', 'zero')}. Holm over exactly these tests. "
         "Verdict: supported (p_holm < 0.05, positive), contrary (p_holm < 0.05, negative), "
         "else not detected. Nothing else in the ablation is a test.\n"]
    if not family:
        L.append("_No `registered` block in pooled_ablation.json._\n")
        return L
    if not reg.get("complete"):
        L.append("**INCOMPLETE: not every registered test could be run, so these verdicts "
                 "are not the registered analysis.**\n")
    L.append("| Test | Measure | n | delta | CI95 | p_holm | r_rb | verdict |")
    L.append("|---|---|---|---|---|---|---|---|")
    for r in family:
        if not r.get("n"):
            L.append(f"| {r.get('test')} | `{r.get('measure')}` | 0 | -- | -- | -- | -- | "
                     f"{r.get('note') or r.get('verdict', 'not tested')} |")
            continue
        digits = 2 if r.get("measure") in LLM_JUDGE_SCORES else 3
        L.append(f"| {r.get('test')} | `{r.get('measure')}` | {r.get('n')} | "
                 f"{signed(r.get('mean_diff'), digits)} | {ci(r.get('ci95'), digits)} | "
                 f"{pval(r.get('p_holm'))} | {num(r.get('rank_biserial_r'))} | "
                 f"{r.get('verdict')} |")
    L.append("")
    tally = {}
    for r in family:
        tally[r.get("verdict", "not tested")] = tally.get(r.get("verdict", "not tested"), 0) + 1
    L.append("Verdicts: " + ", ".join(f"{v}: {c}" for v, c in sorted(tally.items()))
             + f" (of {len(family)}).\n")
    return L


def rollup_scale_gradient(abl, lad):
    """Which size carries the largest |effect|. Exists to stop 'strongest at the
    small model' style claims that the per-measure argmax does not support."""
    L = ["### 2.4 Scale gradient check - where does the largest effect actually sit?\n",
         "For each factorial measure x main effect, the size with the largest |effect| "
         "(descriptive; the scale TEST is the registered H-C). **If the argmax size is "
         "scattered across sizes, there is NO monotone scale gradient and a sentence like "
         "'strongest at the smallest model' is unsupported.**\n"]
    measures = list(((abl.get("factorial") or {}).get("measures") or {}))
    if len({r.get("label") for m in measures for r in factorial_rows(abl, m)}) < 2:
        L.append("_Fewer than two sizes with a complete 2x2 - no gradient to read._\n")
        return L
    L.append("| Main effect | Measure | argmax size | |effect| there | effect by size |")
    L.append("|---|---|---|---|---|")
    tally = {}
    for axis in MAIN_EFFECTS:
        for measure in measures:
            entries = [(r.get("label", "?"), main_effect(r, axis))
                       for r in factorial_rows(abl, measure)]
            entries = [(s, d) for s, d in entries if d is not None]
            if not entries:
                continue
            digits = 2 if measure in LLM_JUDGE_SCORES else 3
            top = max(entries, key=lambda t: abs(t[1]))
            tally.setdefault(axis, {}).setdefault(top[0], 0)
            tally[axis][top[0]] += 1
            by_size = ", ".join(f"{s}={signed(d, digits)}" for s, d in entries)
            L.append(f"| {axis} | `{measure}` | **{top[0]}** | "
                     f"{num(abs(top[1]), digits)} | {by_size} |")
    L.append("")
    for axis, counts in tally.items():
        spread = ", ".join(f"{s}: {c}" for s, c in sorted(counts.items()))
        note = ("CONCENTRATED - a scale claim may be defensible" if len(counts) == 1
                else "SCATTERED - do NOT claim a scale gradient")
        L.append(f"- {axis} argmax distribution: {spread} -> **{note}**")
    L.append("")
    return L


def rollup_family_disagreement(abl, lad):
    """Where the LLM judge and the panel point opposite ways — the finding itself."""
    L = ["### 2.5 Cross-family disagreement (LLM judge vs panel)\n",
         "Same main effect, same size, opposite sign between the two families (descriptive "
         "factorial effects, richer minus plainer). **Every row marked OPPOSITE is a place "
         "where quoting one family alone would misrepresent the result.**\n",
         "| Main effect | Size | LLM JUDGE lead (`%s`) | PANEL (n signals neg / total) | disagreement |"
         % LLM_JUDGE_LEAD,
         "|---|---|---|---|---|"]
    panel_names = panel_signal_names(abl) or panel_signal_names(lad)
    lead = {r.get("label"): r for r in factorial_rows(abl, LLM_JUDGE_LEAD)}
    panel = {s: {r.get("label"): r for r in factorial_rows(abl, s)} for s in panel_names}
    for axis in MAIN_EFFECTS:
        for size, row in lead.items():
            jd = main_effect(row, axis)
            if jd is None:
                continue
            effects = [main_effect(panel[s][size], axis) for s in panel_names
                       if size in panel[s]]
            effects = [d for d in effects if d is not None]
            if not effects:
                continue
            pneg = sum(1 for d in effects if d < 0)
            ptot = len(effects)
            panel_dir = -1 if pneg > ptot / 2 else (1 if pneg < ptot / 2 else 0)
            llm_judge_dir = -1 if jd < 0 else (1 if jd > 0 else 0)
            flag = "**OPPOSITE**" if llm_judge_dir * panel_dir < 0 else "same direction"
            L.append(f"| {axis} | {size} | {signed(jd, 2)} | "
                     f"{pneg}/{ptot} negative | {flag} |")
    L.append("")
    L.append("Reading rule that follows from this table: a sentence about a mechanism must name "
             "its family. A mechanism can lower the alignment signals without lowering the LLM "
             "judge score, and both statements belong in the same paragraph.\n")
    return L


# ── sections 3-5: full tables ──────────────────────────────────────────────────

def _paired_table(rows, digits):
    """Rows of one paired comparison, direction proposed - baseline."""
    L = ["| Baseline | n | mean_diff | CI95 | p_raw | p_holm | r_rb | verdict |",
         "|---|---|---|---|---|---|---|---|"]
    for r in rows:
        L.append(f"| `{r.get('baseline')}` | {r.get('n','--')} | "
                 f"{signed(r.get('mean_diff'), digits)} | {ci(r.get('ci95'), digits)} | "
                 f"{pval(r.get('p_raw'))} | {pval(r.get('p_holm'))} | "
                 f"{num(r.get('rank_biserial_r'))} | {verdict(r.get('p_holm'))} |")
    L.append("")
    return L


def sec_llm_judge_tables(lad):
    L = ["## 3. LLM judge scores - full tables\n",
         "Per-agent descriptive means come from the pooled per-agent block, under failure = 0 "
         "over every scenario. **A mean and its SD must come from the same signal** - the "
         "columns below are already paired correctly (`mean_addie` with "
         "`sd_addie_across_scenarios`, etc.). The SD is ACROSS SCENARIOS, not across runs: the "
         "comparison experiment generates one run per cell, so a run-to-run SD has a single "
         "value and does not exist. It is descriptive spread, not a precision estimate. "
         "`counted 0` = scenarios with no scorable output in at least one run.\n"]
    for m in lad.get("models") or []:
        L.append(f"### {m.get('label','?')}\n")
        L.append("| Agent | n | counted 0 | ADDIE | SD scen | Traj | SD scen | Total | SD scen "
                 "| ADDIE complete-case |")
        L.append("|---|---|---|---|---|---|---|---|---|---|")
        for agent, a in sorted((m.get("agents") or {}).items()):
            L.append(f"| `{agent}` | {a.get('n_scenarios','--')} | "
                     f"{a.get('n_scenarios_any_missing','--')} | "
                     f"{num(a.get('mean_addie'), 2)} | {num(a.get('sd_addie_across_scenarios'), 2)} | "
                     f"{num(a.get('mean_traj'), 2)} | {num(a.get('sd_traj_across_scenarios'), 2)} | "
                     f"{num(a.get('mean_total'), 2)} | {num(a.get('sd_total_across_scenarios'), 2)} | "
                     f"{num(a.get('mean_addie_complete_case'), 2)} |")
        L.append("")
        sensitivity = (m.get("comparisons") or {}).get("sensitivity_policy")
        for signal in LLM_JUDGE_SCORES:
            rows = llm_judge_comparisons(m, signal)
            if rows:
                L.append(f"Paired vs baselines - `{signal}`, failure = 0, "
                         "direction `proposed - baseline`:\n")
                L += _paired_table(rows, 2)
            cc = llm_judge_comparisons(m, signal, sensitivity) if sensitivity else []
            if cc:
                L.append(f"`{signal}`, complete-case (sensitivity):\n")
                L += _paired_table(cc, 2)
    return L


def sec_panel_tables(lad):
    L = ["## 4. alignment panel - full tables\n",
         "Flat panel, no primary endpoint. Continuous signals are mean-max RECTIFIED cosine "
         "(`max(0, cos)` on [0,1]) - a scale choice, not a matching cutoff. There is no "
         "similarity threshold anywhere in the protocol. Means and paired rows are under "
         "failure = 0; the complete-case rows are the sensitivity.\n"]
    for size, panel in panel_blocks(lad):
        L.append(f"### {size}\n")
        for signal, block in panel.items():
            L.append(f"#### `{signal}` [{block.get('family', '?')}]\n")
            desc = block.get("align_descriptive") or {}
            cc_desc = block.get("complete_case_descriptive") or {}
            if desc:
                L.append("| Agent | n | mean | CI95 | complete-case mean (n) |")
                L.append("|---|---|---|---|---|")
                for agent, d in sorted(desc.items()):
                    cc = cc_desc.get(agent) or {}
                    cc_txt = f"{num(cc.get('mean'))} ({cc.get('n', '--')})" if cc else "--"
                    L.append(f"| `{agent}` | {d.get('n', '--')} | {num(d.get('mean'))} | "
                             f"{ci(d.get('ci95'))} | {cc_txt} |")
                L.append("")
            rows = block.get("comparisons") or []
            if rows:
                L.append("Paired, failure = 0, direction `proposed - baseline`:\n")
                L += _paired_table(rows, 3)
            cc_rows = block.get("comparisons_complete_case") or []
            if cc_rows:
                L.append("Paired, complete-case (sensitivity):\n")
                L += _paired_table(cc_rows, 3)
    L += sec_panel_validity(lad)
    return L


#: Validity evidence the scorer records per agent: it measures the instrument
#: on each agent's output, never the agent, and is no panel signal.
PANEL_VALIDITY = (
    ("details.validation.objective_item_lexical_overlap",
     "content-word Jaccard of each objective and its best-matching item "
     "(high = the item shares the objective's wording, which every encoder reads "
     "as correspondence)"),
    ("details.validation.declared_link_agreement",
     "share of the agent's declared item->objective links that similarity matching reproduces"),
)


def sec_panel_validity(lad):
    models = (lad.get("alignment") or {}).get("models") or {}
    present = [(key, what) for key, what in PANEL_VALIDITY
               if any(key in metrics for agents in models.values() for metrics in agents.values())]
    if not present:
        return []
    L = ["### Validity evidence per agent (not panel signals)\n"]
    for key, what in present:
        L.append(f"- `{key.rsplit('.', 1)[-1]}`: {what}.")
    L.append("")
    L.append("| Size | Agent | " + " | ".join(f"`{k.rsplit('.', 1)[-1]}`" for k, _ in present) + " |")
    L.append("|---|---|" + "---|" * len(present))
    for size, agents in models.items():
        for agent, metrics in sorted(agents.items()):
            cells = [num((metrics.get(key) or {}).get("mean")) for key, _ in present]
            L.append(f"| {size} | `{agent}` | " + " | ".join(cells) + " |")
    L.append("")
    return L


def sec_ablation_tables(abl, lad):
    cfg = abl.get("config") or {}
    L = ["## 5. Ablation - full tables\n",
         f"**Direction: {cfg.get('direction') or 'richer setting minus plainer one'}.** "
         "Cell means are under failure = 0 and descriptive; the only tests are the "
         "registered ones (2.3, with their secondary readings in 5.3).\n"]
    reference = cfg.get("reference") or PROPOSED

    def arm_label(agent):
        return "A0 - full pipeline" if agent == reference else ARM_LABELS.get(agent, agent)

    L.append("### 5.1 JUDGE family - cell means per arm\n")
    for m in abl.get("models") or []:
        L.append(f"#### {m.get('label','?')}\n")
        L.append("| Arm | n | counted 0 | ADDIE | Traj | Total |")
        L.append("|---|---|---|---|---|---|")
        for agent, a in sorted((m.get("agents") or {}).items(), key=lambda t: arm_label(t[0])):
            L.append(f"| {arm_label(agent)} | {a.get('n_scenarios', '--')} | "
                     f"{a.get('n_scenarios_any_missing', '--')} | "
                     f"{num(a.get('mean_addie'), 2)} | "
                     f"{num(a.get('mean_traj'), 2)} | {num(a.get('mean_total'), 2)} |")
        L.append("")

    fac = abl.get("factorial") or {}
    cells = fac.get("cells") or {}
    measures = fac.get("measures") or {}
    panel_names = panel_signal_names(abl) or panel_signal_names(lad)
    if any(s in measures for s in panel_names) and cells:
        L.append("### 5.2 PANEL family - cell means per arm (scenarios with all four cells)\n")
        keys = list(cells)
        L.append("| Size | Signal | n | " + " | ".join(arm_label(cells[k]) for k in keys) + " |")
        L.append("|---|---|---|" + "---|" * len(keys))
        for signal in panel_names:
            for row in factorial_rows(abl, signal):
                means = row.get("cell_means") or {}
                L.append(f"| {row.get('label','?')} | `{signal}` | {row.get('n_scenarios','--')} | "
                         + " | ".join(num(means.get(k)) for k in keys) + " |")
        L.append("")

    reg = abl.get("registered") or {}
    if reg.get("family"):
        L.append("### 5.3 Registered tests - secondary readings\n")
        L.append("The family itself is in 2.3. Per size: the same tests over complete cases "
                 "(sensitivity, their own Holm), the pre-specified decomposition x substrate "
                 "interaction (UNCORRECTED), the model-written triad (descriptive) and the "
                 "phase slope of the decomposition gap (descriptive).\n")
        for size, sec in (reg.get("secondary") or {}).items():
            L.append(f"#### {size}\n")
            L.append("| Reading | n | delta | CI95 | p | verdict |")
            L.append("|---|---|---|---|---|---|")
            for r in sec.get("complete_case") or []:
                L.append(f"| {r.get('test')} | {r.get('n', '--')} | {signed(r.get('mean_diff'))} | "
                         f"{ci(r.get('ci95'))} | p_holm={pval(r.get('p_holm'))} | "
                         f"{r.get('verdict', '--')} |")
            for measure, r in (sec.get("interaction") or {}).items():
                L.append(f"| interaction on `{measure}` | {r.get('n', '--')} | "
                         f"{signed(r.get('mean_diff'))} | {ci(r.get('ci95'))} | "
                         f"p_raw={pval(r.get('p_raw'))} (uncorrected) | -- |")
            mw = sec.get("substrate|model_written") or {}
            if mw.get("n"):
                L.append(f"| H-S on the model-written triad | {mw['n']} | "
                         f"{signed(mw.get('mean_diff'))} | {ci(mw.get('ci95'))} | "
                         "descriptive | -- |")
            slope = (sec.get("phase_slope") or {}).get("slope") or {}
            if slope.get("n"):
                L.append(f"| H-D gap slope per ADDIE phase | {slope['n']} | "
                         f"{signed(slope.get('mean_diff'))} | {ci(slope.get('ci95'))} | "
                         "descriptive | -- |")
            L.append("")

    if measures:
        L.append("### 5.4 2x2 factorial (decomposition x context representation)\n")
        L.append("**Direction: `multi-agent - single-agent` / `graph - prose`.** Positive = the "
                 "richer setting scores higher. Each effect is a mean with its bootstrap CI - "
                 "DESCRIPTIVE; the tests are the registered ones.\n")
        L.append("`interaction` = (decomposition effect given ctx=graph) - (decomposition "
                 "effect given ctx=prose). Negative means the decomposition effect is lower "
                 "under graph than under prose, whatever its sign: where both simple effects "
                 "are positive the two mechanisms SUBSTITUTE for each other, where both are "
                 "negative multi-agent decomposition costs MORE under graph, and where the "
                 "signs differ it is a crossover.\n")
        for signal, block in measures.items():
            L.append(f"#### `{signal}`\n")
            L.append("| Size | n | " + " | ".join(lbl.replace("|", "\\|")
                                                    for _, lbl in FACTORIAL_EFFECTS) + " |")
            L.append("|---|---|" + "---|" * len(FACTORIAL_EFFECTS))
            digits = 2 if signal in LLM_JUDGE_SCORES else 3
            for row in block.get("per_model") or []:
                def cell(key):
                    e = row.get(key) or {}
                    if e.get("mean_diff") is None:
                        return "--"
                    return f"{signed(e['mean_diff'], digits)} {ci(e.get('ci95'), digits)}"
                L.append(f"| {row.get('label','?')} | {row.get('n_scenarios', row.get('n', '--'))} | "
                         + " | ".join(cell(k) for k, _ in FACTORIAL_EFFECTS) + " |")
            L.append("")

    va = abl.get("self_validation_activity") or []
    if va:
        L.append("### 5.5 Self-validation activity (repairs actually performed)\n")
        L.append("Operational counts, not a scored signal. Self-validation is always on (not "
                 "one of the two ablated axes), so this is context for the decomposition/context "
                 "effects above, not mechanism evidence for an on/off switch.\n")
        L.append("| Size | Arm | n scenario-runs | verifier events (mean) | repair events (mean) "
                 "| % runs with a repair |")
        L.append("|---|---|---|---|---|---|")
        for row in va:
            for arm, d in (row.get("arms") or {}).items():
                L.append(f"| {row.get('label','?')} | {arm_label(arm)} | "
                         f"{(d or {}).get('n_scenario_runs','--')} | "
                         f"{num((d or {}).get('verifier_events_mean'), 2)} | "
                         f"{num((d or {}).get('repair_events_mean'), 2)} | "
                         f"{num((d or {}).get('pct_scenario_runs_with_repair'), 1)} |")
        L.append("")
    return L


# ── sections 6-9 ───────────────────────────────────────────────────────────────

def sec_interaction(lad):
    L = ["## 6. Scale interaction (DiD, largest size - smallest size)\n",
         "Under failure = 0. Direction: delta(proposed - baseline) at the largest size minus at "
         "the smallest; positive = the advantage grows with size. The p column is the "
         "Wilcoxon p of the per-scenario DiD values, UNCORRECTED (outside every Holm "
         "family); no significance verdict is given.\n"]
    for signal, block in (lad.get("interaction_by_score") or {}).items():
        L.append(f"### `{signal}`\n")
        defn = block.get("definition")
        if defn:
            L.append(f"> {defn}\n")
        L.append("| Baseline | n | DiD | CI95 | p (uncorrected) |")
        L.append("|---|---|---|---|---|")
        for row in block.get("per_baseline") or []:
            L.append(f"| `{row.get('baseline')}` | {row.get('n_paired_scenarios', '--')} | "
                     f"{signed(row.get('did_mean'), 2)} | "
                     f"{ci(row.get('did_ci95'), 2)} | {pval(row.get('did_wilcoxon_p'))} |")
        L.append("")
    ia = ((lad.get("alignment") or {}).get("stats") or {}).get("interaction_align") or {}
    if ia:
        L.append("### Panel DiD (`interaction_align`)\n")
        if ia.get("definition"):
            L.append(f"> {ia['definition']}\n")
        rows = ia.get("per_baseline") or []
        if rows:
            L.append("| Baseline | n | DiD | CI95 | p (uncorrected) |")
            L.append("|---|---|---|---|---|")
            for row in rows:
                L.append(f"| `{row.get('baseline')}` | {row.get('n_paired_scenarios', '--')} | "
                         f"{signed(row.get('did_mean'))} | "
                         f"{ci(row.get('did_ci95'))} | {pval(row.get('did_wilcoxon_p'))} |")
            L.append("")
    return L


def sec_failures(lad):
    L = ["## 7. Output failure rates\n"]
    fr = lad.get("failure_rates") or {}
    if fr.get("definition"):
        L.append(f"> {fr['definition']}\n")
    L.append("Descriptive counts on the same scenarios, no test: under failure = 0 every failure "
             "already scores 0 in the paired comparisons.\n")
    for block in fr.get("per_model") or []:
        rows = block.get("rows") or []
        if not rows:
            continue
        L.append(f"### {block.get('label','?')}\n")
        L.append("| Baseline | proposed failed | baseline failed | both failed | only proposed | "
                 "only baseline | n | baseline run-level |")
        L.append("|---|---|---|---|---|---|---|---|")
        for r in rows:
            L.append(f"| `{r.get('baseline')}` | {r.get('proposed_failed_scenarios','--')} | "
                     f"{r.get('baseline_failed_scenarios','--')} | "
                     f"{r.get('both_failed_scenarios','--')} | "
                     f"{r.get('only_proposed_failed','--')} | {r.get('only_baseline_failed','--')} | "
                     f"{r.get('n_scenarios','--')} | {r.get('baseline_failed_run_level','--')} |")
        L.append("")
    return L


def sec_tokens(lad):
    L = ["## 8. Token usage (operational metadata)\n"]
    tu = lad.get("token_usage") or {}
    if tu.get("source"):
        L.append(f"> {tu['source']}\n")
    L.append("Cost RATIOS and token/quality economics are NOT here - see `stats_cost.md`. "
             "Two artifact traps that apply to these fields: `metadata.cost_usd` is wrong "
             "(commercial API prices applied to a self-hosted pod), and wall-clock is "
             "QUEUED THROUGHPUT, not latency - never call it latency.\n")
    fields = ("prompt_tokens", "completion_tokens", "total_tokens", "llm_calls",
              "execution_time_seconds")
    for size, block in (tu.get("models") or {}).items():
        L.append(f"### {size}\n")
        L.append("| Agent | " + " | ".join(f"{f} (mean +- SD)" for f in fields) + " |")
        L.append("|---" * (len(fields) + 1) + "|")
        for agent, d in sorted(block.items()):
            cells = []
            for f in fields:
                e = (d or {}).get(f) or {}
                digits = 1 if f in ("llm_calls", "execution_time_seconds") else 0
                cells.append(f"{num(e.get('mean'), digits)} +- "
                             f"{num(e.get('sd_across_scenarios'), digits)}")
            L.append(f"| `{agent}` | " + " | ".join(cells) + " |")
        L.append("")
    return L


def sec_sensitivity(lad):
    L = ["## 9. Instrument sensitivity star\n"]
    sens = lad.get("alignment_sensitivity") or {}
    if not sens:
        L.append("_No `alignment_sensitivity` block in the pooled file._\n")
        return L
    if sens.get("definition"):
        L.append(f"> {sens['definition']}\n")
    summary = sens.get("summary") or {}
    if summary:
        L.append("| Field | Value |")
        L.append("|---|---|")
        for k, v in summary.items():
            L.append(f"| {k} | {num(v, 4) if isinstance(v, float) else v} |")
        L.append("")
    L.append("The star is NOT a grid: each arm deviates from the primary configuration on "
             "exactly ONE axis (encoder, baseline correction, or Bloom classifier). An encoder "
             "swap cannot move a Bloom level and a Bloom swap cannot move a cosine, so read each "
             "arm's own `axis` and `agreement_metric`. The baseline-corrected arm reports "
             "own-scenario minus foreign-scenario similarity, on [-1, 1].\n")
    return L


def sec_macros(outdir):
    L = ["## 10. Macro index - every value the paper can \\input\n",
         "Parsed from the generated `*_macros.tex`. If a number appears in the paper, it should "
         "appear here; a paper number that is NOT in this table was typed by hand and violates "
         "the repo rule that all reported numbers are generated.\n"]
    total = 0
    for name in MACRO_FILES:
        path = outdir / name
        if not path.exists():
            L.append(f"_`{name}` not found - skipped._\n")
            continue
        entries = []
        # a macro's comment is on its own line or on the line just above it
        above = ""
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            m = MACRO_RE.match(line)
            if m:
                entries.append((m.group(1), m.group(2),
                                (m.group(3) or "").strip() or above))
                above = ""
            else:
                above = line[1:].strip() if line.startswith("%") else ""
        total += len(entries)
        L.append(f"### `{name}` ({len(entries)} macros)\n")
        L.append("| Macro | Value | Comment |")
        L.append("|---|---|---|")
        for macro, value, comment in entries:
            L.append(f"| `\\{macro}` | {value} | {comment} |")
        L.append("")
    L.insert(2, f"**{total} macros total.**\n")
    return L


# ── main ───────────────────────────────────────────────────────────────────────

def build(lad, abl, outdir, brief=False):
    L = ["# Facts sheet - every aggregate number in one file\n"]
    L.append(f"AUTO-GENERATED by `{paths.cli()} report facts`. "
             "Do not edit by hand.\n")
    L.append("This file exists so that a reader (human or model) can quote a number without "
             "opening six artifacts with three different sign conventions. Section 0 is the "
             "reading contract; section 2 pre-computes the roll-ups so nobody has to count "
             "cells by eye.\n")
    if brief:
        L.append("**BRIEF MODE** - sections 0-2 only (contract + provenance + roll-ups). "
                 "Every roll-up here is computed from the same pooled files as the full sheet; "
                 "run without `--brief` for the per-cell tables behind these counts.\n")
    L += sec_reading_contract(lad, abl)
    L += sec_provenance(lad, abl)
    L.append("## 2. Roll-ups - pre-computed, do not hand-count\n")
    L += rollup_llm_judge(lad)
    L += rollup_panel(lad)
    L += rollup_ablation(abl, lad)
    L += rollup_scale_gradient(abl, lad)
    L += rollup_family_disagreement(abl, lad)
    if brief:
        L.append("_Sections 3-10 (full per-cell tables, DiD, failure rates, token usage, "
                 "sensitivity, macro index) omitted in brief mode._\n")
        return "\n".join(L) + "\n"
    L += sec_llm_judge_tables(lad)
    L += sec_panel_tables(lad)
    L += sec_ablation_tables(abl, lad)
    L += sec_interaction(lad)
    L += sec_failures(lad)
    L += sec_tokens(lad)
    L += sec_sensitivity(lad)
    L += sec_macros(outdir)
    return "\n".join(L) + "\n"


def run(*, comparison_pooled: Path | None = None, ablation_pooled: Path | None = None,
        outdir: Path | None = None, out: Path | None = None,
        brief: bool = False, quiet: bool = False) -> Path | None:
    """Consolidate every summary number into one file.

    Reads the other generators' macro files, so it must run AFTER them -- a
    dependency that lived only in a comment and is now enforced by the order
    `report all` uses.
    """
    from .. import schema

    cmp_path = comparison_pooled or (paths.results_root() / "pooled_comparison.json")
    abl_path = ablation_pooled or (paths.results_root() / "pooled_ablation.json")
    missing = [p for p in (cmp_path, abl_path) if not p.exists()]
    if missing:
        if not quiet:
            print("- facts sheet skipped, missing: "
                  + ", ".join(p.name for p in missing)
                  + f"\n  Produce them with:  {paths.cli()} pool comparison"
                  + f" ; {paths.cli()} pool ablation")
        return None

    lad = schema.load(cmp_path)
    abl = schema.load(abl_path)
    directory = outdir or paths.generated_dir()
    target = out or (directory / ("facts_brief.md" if brief else "facts.md"))
    target.parent.mkdir(parents=True, exist_ok=True)
    text = build(lad, abl, directory, brief=brief)
    target.write_text(text, encoding="utf-8")
    if not quiet:
        print(f"wrote {target}  ({len(text) // 1024} KB, {text.count(chr(10))} lines)")
    return target

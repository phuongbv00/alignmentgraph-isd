"""Pooling the LLM judge scores across runs and comparing agents.

One model size at a time: every comparison is PAIRED WITHIN a size, because a
scenario is the unit of analysis and the same scenario must be on both sides of
a difference. Uncertainty comes from resampling scenarios (bootstrap CI, paired
Wilcoxon), not from repeating runs -- with one deterministic run per cell there
is no run-to-run spread to resample.
"""

from __future__ import annotations

import math
from pathlib import Path
from typing import Optional

from ..config import LLM_JUDGE_LEAD, LLM_JUDGE_SCORE_LABEL, LLM_JUDGE_SCORES
from ..runs import load_run
from ..stats import (
    bootstrap_ci,
    holm_correct,
    rank_biserial,
    wilcoxon_signed_rank,
)
from ..util import mean as _mean
from ..util import sd as _sd

def pool_model(label: str, run_dirs: list[Path], agents: list[str]) -> dict:
    """Pool one model size across its runs."""
    runs = [load_run(d) for d in run_dirs]
    all_scenarios = sorted({sid for run in runs for sid in run})

    per_run_info = []
    for d, run in zip(run_dirs, runs):
        missing_by_agent = {
            a: sorted(
                sid for sid in all_scenarios
                if sid not in run or a not in run[sid]["rankings"]
                or run[sid]["rankings"][a].get("total_score") is None
            )
            for a in agents
        }
        per_run_info.append({
            "dir": str(d),
            "n_scenarios_scored": len(run),
            "missing_by_agent": {a: len(v) for a, v in missing_by_agent.items()},
            "missing_scenarios_by_agent": {a: v for a, v in missing_by_agent.items() if v},
        })

    # scores[agent][scenario] = [per-run total_score or None]
    def collect(field: str) -> dict[str, dict[str, list[Optional[float]]]]:
        out: dict[str, dict[str, list[Optional[float]]]] = {a: {} for a in agents}
        for a in agents:
            for sid in all_scenarios:
                vals: list[Optional[float]] = []
                for run in runs:
                    r = run.get(sid, {}).get("rankings", {}).get(a)
                    v = r.get(field) if r else None
                    vals.append(float(v) if isinstance(v, (int, float)) else None)
                out[a][sid] = vals
        return out

    totals = collect("total_score")
    addies = collect("addie_median")
    trajs = collect("trajectory_score")

    agents_summary: dict[str, dict] = {}
    for a in agents:
        # The complete-case set is defined by total_score availability and then
        # reused for the ADDIE and Trajectory means. That is only sound because
        # the three arrive together: over all 10,347 scored agent-run cells in the
        # 12 ladder runs there is no cell with total_score but a missing
        # addie_median or trajectory_score. If a future evaluator can emit one
        # without the others, this has to become a per-score complete-case set.
        complete = {sid: v for sid, v in totals[a].items() if all(x is not None for x in v)}
        scen_means = [_mean([x for x in v]) for v in complete.values()]  # type: ignore[list-item]
        # Within-scenario spread across runs. Empty with one run per cell, which
        # is the default — hence the None below rather than a mean over
        # nothing.
        scen_sds = [_sd([x for x in v]) for v in complete.values() if len(v) >= 2]  # type: ignore[arg-type]
        within_sds = [x for x in scen_sds if x is not None]
        # Run-level mean -> SD across runs, over the SAME complete-case set that
        # mean_total uses. Averaging each run over whatever scenarios that run
        # happens to have makes the run means incomparable: their spread would
        # mix run-to-run variability with differences in scenario composition,
        # which is exactly the wrong thing to print as "mean_total ± SD" (and it
        # understates the SD precisely for the agents that fail most).
        # Every LLM judge score gets its OWN run-to-run SD over that same set. A single
        # shared SD was a real defect: it is a total_score statistic, and printing
        # it next to an ADDIE or Trajectory mean overstated run-to-run spread by up
        # to 16x on Trajectory, which is far more stable across runs than Total.
        def run_level_sd(series: dict[str, list[Optional[float]]]) -> tuple[list[float], float]:
            per_run = []
            for ri in range(len(runs)):
                vals = [v[ri] for sid, v in series.items()
                        if sid in complete and v[ri] is not None]
                per_run.append(_mean(vals) if vals else float("nan"))
            return per_run, _sd([m for m in per_run if not math.isnan(m)])
        # NOTE: with one run per cell every run-to-run SD below is None. That is
        # the designed state, not a defect: uncertainty is carried by the paired
        # per-scenario analyses, which resample SCENARIOS. Cells covered by a
        # targeted repeat have two or three runs and do get a number.

        run_means, sd_run_total = run_level_sd(totals[a])
        _, sd_run_addie = run_level_sd(addies[a])
        _, sd_run_traj = run_level_sd(trajs[a])
        addie_means = [
            _mean([x for x in addies[a][sid] if x is not None])
            for sid in complete if any(x is not None for x in addies[a][sid])
        ]
        traj_means = [
            _mean([x for x in trajs[a][sid] if x is not None])
            for sid in complete if any(x is not None for x in trajs[a][sid])
        ]
        agents_summary[a] = {
            "n_scenarios_complete": len(complete),
            "n_scenarios_any_missing": len(all_scenarios) - len(complete),
            "mean_total": _mean(scen_means),
            # Spread ACROSS SCENARIOS, per score. Defined with a single run, and
            # it is the spread the bootstrap resamples over, so this is what the
            # descriptive tables show now that run-to-run SD is usually absent.
            "sd_total_across_scenarios": _sd(scen_means),
            "sd_addie_across_scenarios": _sd(addie_means),
            "sd_traj_across_scenarios": _sd(traj_means),
            "mean_within_scenario_run_sd": _mean(within_sds) if within_sds else None,
            "mean_addie": _mean(addie_means),
            "mean_traj": _mean(traj_means),
            "run_means_total": run_means,
            # CONSUMERS: pick the field matching the score you display. The bare
            # `run_to_run_sd` is Total and is kept only because the ablation
            # pooling (08) checks A0 drift on total_score; never pair it with an
            # ADDIE or Trajectory mean. All four are None unless this cell has
            # two or more runs — do not print them without a None check.
            "run_to_run_sd": sd_run_total,
            "run_to_run_sd_total": sd_run_total,
            "run_to_run_sd_addie": sd_run_addie,
            "run_to_run_sd_traj": sd_run_traj,
        }

    return {
        "label": label,
        "run_dirs": [str(d) for d in run_dirs],
        "n_runs": len(runs),
        "n_scenarios_union": len(all_scenarios),
        "per_run": per_run_info,
        "agents": agents_summary,
        # Per-scenario series for every LLM judge score, so the inferential layer is
        # not locked to the composite. Stripped before the JSON dump.
        "_scores": {"addie_median": addies, "total_score": totals,
                    "trajectory_score": trajs},
    }

def scenario_mean_map(totals: dict[str, dict[str, list[Optional[float]]]],
                     agent: str, policy: str, floor: float) -> dict[str, float]:
    """scenario -> pooled score under a failure policy.

    complete_case: only scenarios with ALL runs present.
    zero / min_score: missing run-values imputed with 0 / the model-size min.
    """
    out: dict[str, float] = {}
    for sid, vals in totals[agent].items():
        if policy == "complete_case":
            if all(x is not None for x in vals):
                out[sid] = _mean(vals)  # type: ignore[arg-type]
        else:
            imput = 0.0 if policy == "zero" else floor
            if any(x is not None for x in vals):  # scenario attempted at least once
                out[sid] = _mean([x if x is not None else imput for x in vals])
            else:
                out[sid] = imput
    return out

def compare_model(model: dict, proposed: str, baselines: list[str]) -> dict:
    """Paired stats for every LLM judge score, each with the three failure policies.

    Every score in :data:`LLM_JUDGE_SCORES` gets identical treatment — the lead
    score is a narrative choice recorded in ``lead_score``, not a different
    statistical standard. Holm families stay per (score, policy): the scores
    measure different constructs, so pooling them into one family would trade
    power for a correction nobody asked for.
    """
    by_score: dict[str, dict] = {}
    for metric in LLM_JUDGE_SCORES:
        series = model["_scores"][metric]
        observed = [x for a in series.values() for v in a.values() for x in v
                    if x is not None]
        floor = min(observed) if observed else 0.0
        policies = {}
        for policy in ("complete_case", "zero", "min_score"):
            rows = []
            for b in baselines:
                pmap = scenario_mean_map(series, proposed, policy, floor)
                bmap = scenario_mean_map(series, b, policy, floor)
                shared = sorted(set(pmap) & set(bmap))
                diffs = [pmap[s] - bmap[s] for s in shared]
                if not diffs:
                    rows.append({"baseline": b, "n": 0})
                    continue
                w, p, n_eff = wilcoxon_signed_rank(diffs)
                lo, hi = bootstrap_ci(diffs)
                rows.append({
                    "baseline": b,
                    "n": len(diffs),
                    "n_effective_nonzero": n_eff,
                    "mean_diff": _mean(diffs),
                    "ci95": [lo, hi],
                    "wilcoxon_w_plus": w,
                    "p_raw": p,
                    "rank_biserial_r": rank_biserial(diffs),
                })
            with_p = [r for r in rows if "p_raw" in r]
            holm = holm_correct([r["p_raw"] for r in with_p])
            for r, ph in zip(with_p, holm):
                r["p_holm"] = ph
            policies[policy] = rows
        by_score[metric] = {
            "label": LLM_JUDGE_SCORE_LABEL[metric],
            "min_score_floor": floor,
            "policies": policies,
        }
    return {
        "holm_family": (
            f"{len(baselines)} comparisons ({proposed} vs each baseline) "
            f"within model size '{model['label']}'; Holm applied per "
            "(score, policy)."
        ),
        "lead_score": LLM_JUDGE_LEAD,
        "scores": list(LLM_JUDGE_SCORES),
        "primary_policy": "complete_case",
        "by_score": by_score,
    }

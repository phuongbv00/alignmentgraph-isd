"""Pooling the LLM judge scores across runs and comparing agents.

One model size at a time: every comparison is PAIRED WITHIN a size, because a
scenario is the unit of analysis and the same scenario must be on both sides of
a difference. Uncertainty comes from resampling scenarios (bootstrap CI, paired
Wilcoxon), not from repeating runs -- with one run per cell there
is no run-to-run spread to resample.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from ..config import (
    FAILURE_POLICIES,
    FAILURE_POLICY,
    LLM_JUDGE_LEAD,
    LLM_JUDGE_SCORE_LABEL,
    LLM_JUDGE_SCORES,
    SENSITIVITY_POLICY,
)
from ..runs import load_run
from ..stats import holm_correct, paired
from . import attempts
from ..util import mean as _mean
from ..util import sd as _sd


class _NotRun:
    """A run in which the agent was not attempted on that scenario."""

    def __repr__(self) -> str:
        return "NOT_RUN"


#: Marks a (scenario, run) the agent was not attempted in: not a failure, and
#: not part of its series. ``None`` is a failure; a float is a score.
NOT_RUN = _NotRun()


def ran(vals: list) -> list[Optional[float]]:
    """The entries of a per-run series the agent was attempted in."""
    return [v for v in vals if v is not NOT_RUN]


def pool_model(label: str, run_dirs: list[Path], agents: list[str]) -> dict:
    """Pool one model size across its runs.

    A failure is an attempt that left no scorable output (``attempts``): it
    scores 0 under failure = 0. A run the agent was not attempted in is left out
    of its series, so a targeted repeat of a few agents costs the others
    nothing."""
    reports = [load_run(d) for d in run_dirs]
    held = [attempts.scenarios(d) for d in run_dirs]
    all_scenarios = sorted({sid for scen in held for sid in scen})

    # series[agent][scenario] = [per-run score, None (failed) or NOT_RUN]
    def collect(field: str) -> dict[str, dict[str, list]]:
        out: dict[str, dict[str, list]] = {a: {} for a in agents}
        for a in agents:
            for sid in all_scenarios:
                vals: list = []
                for d, report, scen in zip(run_dirs, reports, held):
                    if sid not in scen or not attempts.attempted(d, sid, a):
                        vals.append(NOT_RUN)
                        continue
                    r = report.get(sid, {}).get("rankings", {}).get(a)
                    v = r.get(field) if r else None
                    vals.append(float(v) if isinstance(v, (int, float)) else None)
                out[a][sid] = vals
        return out

    totals = collect("total_score")
    addies = collect("addie_median")
    trajs = collect("trajectory_score")

    per_run_info = []
    for ri, (d, report) in enumerate(zip(run_dirs, reports)):
        missing_by_agent = {a: sorted(sid for sid, v in totals[a].items() if v[ri] is None)
                            for a in agents}
        per_run_info.append({
            "dir": str(d),
            "n_scenarios_scored": len(report),
            "missing_by_agent": {a: len(v) for a, v in missing_by_agent.items()},
            "missing_scenarios_by_agent": {a: v for a, v in missing_by_agent.items() if v},
        })

    agents_summary: dict[str, dict] = {}
    for a in agents:
        # The scenarios this agent was attempted in, and of those the ones it
        # scored in every attempted run. The complete-case set is defined by
        # total_score and reused for ADDIE and Trajectory, which is sound
        # because the three arrive together: over all 10,347 scored agent-run
        # cells in the 12 ladder runs no cell has total_score but a missing
        # addie_median or trajectory_score.
        tried = [sid for sid, v in totals[a].items() if ran(v)]
        complete = [sid for sid in tried if all(x is not None for x in ran(totals[a][sid]))]
        # Within-scenario spread across runs. Empty with one run per cell, which
        # is the default — hence the None below rather than a mean over
        # nothing.
        scen_sds = [_sd(ran(totals[a][sid])) for sid in complete
                    if len(ran(totals[a][sid])) >= 2]
        within_sds = [x for x in scen_sds if x is not None]
        # Run-level mean -> SD across runs, under failure = 0 over the
        # scenarios the agent was attempted in, so each run mean covers what
        # the primary mean it is printed beside covers. Every LLM judge score
        # gets its OWN run-to-run SD; a Total SD printed beside a Trajectory
        # mean overstates its spread up to 16x.
        def run_level_sd(series: dict[str, list]) -> tuple[list[float], Optional[float]]:
            per_run = []
            for ri in range(len(run_dirs)):
                vals = [0.0 if v[ri] is None else v[ri] for v in series.values()
                        if v[ri] is not NOT_RUN]
                if vals:
                    per_run.append(_mean(vals))
            return per_run, _sd(per_run)
        # NOTE: with one run per cell every run-to-run SD below is None. That is
        # the designed state, not a defect: uncertainty is carried by the paired
        # per-scenario analyses, which resample SCENARIOS. Cells covered by a
        # targeted repeat have two or three runs and do get a number.

        run_means, sd_run_total = run_level_sd(totals[a])
        _, sd_run_addie = run_level_sd(addies[a])
        _, sd_run_traj = run_level_sd(trajs[a])

        # The primary means are under failure = 0, over every scenario the
        # agent was attempted in: the same values the paired tests are run on.
        def primary(series: dict[str, dict[str, list]]) -> list[float]:
            return list(scenario_mean_map(series, a, FAILURE_POLICY).values())

        def complete_case(series: dict[str, dict[str, list]]) -> list[float]:
            return list(scenario_mean_map(series, a, SENSITIVITY_POLICY).values())
        total_p, addie_p, traj_p = primary(totals), primary(addies), primary(trajs)
        agents_summary[a] = {
            "n_scenarios": len(tried),
            "n_scenarios_complete": len(complete),
            "n_scenarios_any_missing": len(tried) - len(complete),
            # failure = 0, over the scenarios the agent was attempted in. The SD is ACROSS SCENARIOS, per
            # score: defined with a single run, and the spread the bootstrap
            # resamples over.
            "mean_total": _mean(total_p),
            "mean_addie": _mean(addie_p),
            "mean_traj": _mean(traj_p),
            "sd_total_across_scenarios": _sd(total_p),
            "sd_addie_across_scenarios": _sd(addie_p),
            "sd_traj_across_scenarios": _sd(traj_p),
            # The sensitivity: over the scenarios this agent scored in every run.
            "mean_total_complete_case": _mean(complete_case(totals)),
            "mean_addie_complete_case": _mean(complete_case(addies)),
            "mean_traj_complete_case": _mean(complete_case(trajs)),
            "mean_within_scenario_run_sd": _mean(within_sds) if within_sds else None,
            "run_means_total": run_means,
            # CONSUMERS: pick the field matching the score you display. The bare
            # `run_to_run_sd` is Total and is kept for the ablation's A0 drift
            # gauge; never pair it with an ADDIE or Trajectory mean. All four are
            # None unless this cell has two or more runs.
            "run_to_run_sd": sd_run_total,
            "run_to_run_sd_total": sd_run_total,
            "run_to_run_sd_addie": sd_run_addie,
            "run_to_run_sd_traj": sd_run_traj,
        }

    return {
        "label": label,
        "run_dirs": [str(d) for d in run_dirs],
        "n_runs": len(run_dirs),
        "n_scenarios_union": len(all_scenarios),
        "per_run": per_run_info,
        "agents": agents_summary,
        # Per-scenario series for every LLM judge score, so the inferential layer is
        # not locked to the composite. Stripped before the JSON dump.
        "_scores": {"addie_median": addies, "total_score": totals,
                    "trajectory_score": trajs},
    }

def scenario_mean_map(series: dict[str, dict[str, list]],
                      agent: str, policy: str) -> dict[str, float]:
    """scenario -> the agent's score on it, mean over the runs it was attempted
    in, under a failure policy.

    zero: a failed run counts 0; every scenario the agent was attempted in is
    present. complete_case: only scenarios it scored in every attempted run.
    """
    out: dict[str, float] = {}
    for sid, vals in series[agent].items():
        tried = ran(vals)
        if not tried:
            continue
        if policy == FAILURE_POLICY:
            out[sid] = _mean([x if x is not None else 0.0 for x in tried])
        elif policy == SENSITIVITY_POLICY:
            if all(x is not None for x in tried):
                out[sid] = _mean(tried)  # type: ignore[arg-type]
        else:
            raise ValueError(f"unknown failure policy {policy!r}")
    return out


def compare_model(model: dict, proposed: str, baselines: list[str]) -> dict:
    """Paired stats for every LLM judge score, under the failure policy and its
    sensitivity.

    Every score in :data:`LLM_JUDGE_SCORES` gets identical treatment — the lead
    score is a narrative choice recorded in ``lead_score``, not a different
    statistical standard. Holm runs per (score, policy) over the baselines: the
    scores measure different constructs, and the sensitivity layer carries its
    own Holm so its verdicts read on the same rule as the primary's.
    """
    by_score: dict[str, dict] = {}
    for metric in LLM_JUDGE_SCORES:
        series = model["_scores"][metric]
        policies = {}
        for policy in FAILURE_POLICIES:
            rows = []
            for b in baselines:
                pmap = scenario_mean_map(series, proposed, policy)
                bmap = scenario_mean_map(series, b, policy)
                shared = sorted(set(pmap) & set(bmap))
                diffs = [pmap[s] - bmap[s] for s in shared]
                if not diffs:
                    rows.append({"baseline": b, "n": 0})
                    continue
                rows.append({"baseline": b, **paired(diffs)})
            with_p = [r for r in rows if "p_raw" in r]
            for r, ph in zip(with_p, holm_correct([r["p_raw"] for r in with_p])):
                r["p_holm"] = ph
                # A comparison with no shared scenario cannot be tested, so it
                # leaves the family; the size actually corrected over is stated.
                r["holm_family_size"] = len(with_p)
            policies[policy] = rows
        by_score[metric] = {
            "label": LLM_JUDGE_SCORE_LABEL[metric],
            "policies": policies,
        }
    return {
        "holm_family": (
            f"{len(baselines)} comparisons ({proposed} vs each baseline) "
            f"within model size '{model['label']}'; Holm applied per "
            "(score, policy) over the comparisons that could be run "
            "(holm_family_size on each row)."
        ),
        "lead_score": LLM_JUDGE_LEAD,
        "scores": list(LLM_JUDGE_SCORES),
        "primary_policy": FAILURE_POLICY,
        "sensitivity_policy": SENSITIVITY_POLICY,
        "by_score": by_score,
    }

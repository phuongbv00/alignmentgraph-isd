"""Tests that read across model sizes, and tests about failure itself.

`interaction_tests` asks whether an advantage CHANGES with model scale --
a difference-in-differences over the size axis, which is the question the
ladder exists to answer. A single difference at a single size says nothing
about a trend, so the DiD is computed explicitly rather than inferred by
eye from two numbers.

`failure_tests` treats producing no scorable output as an outcome in its own
right. Dropping those cells silently would let the worst outputs leave the
denominator, which flatters exactly the configurations that fail most -- and
failure rate rises as the model shrinks, so the missingness tracks the
ladder's own independent variable.
"""

from __future__ import annotations

import random

from ..config import LLM_JUDGE_LEAD
from ..stats import (
    BOOT_SEED,
    N_BOOT,
    bootstrap_ci,
    fisher_exact_2x2,
    holm_correct,
    wilcoxon_signed_rank,
)
from ..util import mean as _mean
from .llm_judge import scenario_mean_map

def interaction_tests(models: list[dict], proposed: str, baselines: list[str],
                      n_boot: int = N_BOOT, seed: int = BOOT_SEED,
                      metric: str = LLM_JUDGE_LEAD) -> dict:
    """Method x model-size interaction (reviewer Q11).

    DiD = mean_i[ delta_i(largest) - delta_i(smallest) ] where
    delta_i(size) = proposed_i - baseline_i on scenario i (complete-case
    mean-of-runs), paired by scenario across sizes. Bootstrap CI resamples
    scenarios. Also reports the per-size delta trend + OLS slope on size rank.
    """
    if len(models) < 2:
        return {"note": "needs >= 2 model sizes", "per_baseline": []}
    small, large = models[0], models[-1]
    results = []
    for b in baselines:
        deltas_by_size = []
        for m in models:
            series = m["_scores"][metric]
            pmap = scenario_mean_map(series, proposed, "complete_case", 0.0)
            bmap = scenario_mean_map(series, b, "complete_case", 0.0)
            deltas_by_size.append({s: pmap[s] - bmap[s] for s in set(pmap) & set(bmap)})
        d_small, d_large = deltas_by_size[0], deltas_by_size[-1]
        shared = sorted(set(d_small) & set(d_large))
        did_vals = [d_large[s] - d_small[s] for s in shared]
        lo, hi = bootstrap_ci(did_vals, n_boot=n_boot, seed=seed)
        _, p, _ = wilcoxon_signed_rank(did_vals)

        # trend: scenarios present at every size; OLS slope of delta on size rank
        common = set(deltas_by_size[0])
        for d in deltas_by_size[1:]:
            common &= set(d)
        common = sorted(common)
        trend_means = [_mean([d[s] for s in common]) for d in deltas_by_size]
        slope, slope_lo, slope_hi = float("nan"), float("nan"), float("nan")
        if common and len(models) >= 2:
            k = len(models)
            xbar = (k - 1) / 2
            denom = sum((x - xbar) ** 2 for x in range(k))

            def ols_slope(scen_subset: list[str]) -> float:
                ms = [_mean([d[s] for s in scen_subset]) for d in deltas_by_size]
                return sum((x - xbar) * m for x, m in zip(range(k), ms)) / denom

            slope = ols_slope(common)
            rng = random.Random(seed)
            boots = sorted(
                ols_slope([common[rng.randrange(len(common))] for _ in common])
                for _ in range(n_boot)
            )
            slope_lo = boots[int(0.025 * n_boot)]
            slope_hi = boots[int(0.975 * n_boot) - 1]

        results.append({
            "baseline": b,
            "smallest": small["label"],
            "largest": large["label"],
            "n_paired_scenarios": len(shared),
            "delta_smallest_mean": _mean(list(d_small.values())),
            "delta_largest_mean": _mean(list(d_large.values())),
            "did_mean": _mean(did_vals),
            "did_ci95": [lo, hi],
            "did_wilcoxon_p": p,
            "trend_delta_by_size": {
                m["label"]: t for m, t in zip(models, trend_means)
            },
            "trend_n_common_scenarios": len(common),
            "trend_ols_slope_per_size_step": slope,
            "trend_slope_ci95": [slope_lo, slope_hi],
        })
    return {
        "metric": metric,
        "definition": (
            f"DiD on {metric} = mean over scenarios of [delta(largest size) - "
            "delta(smallest size)], delta = proposed - baseline per scenario "
            "(mean of runs, complete-case); bootstrap CI (10k, seed 42) "
            "resamples scenarios; positive DiD means the proposed method's "
            "advantage GROWS with model size, negative means it shrinks (i.e. "
            "the method helps small models more)."
        ),
        "per_baseline": results,
    }

def failure_tests(models: list[dict], proposed: str, baselines: list[str]) -> dict:
    """Scenario-level output-failure comparison (proposed vs each baseline).

    Unit = scenario (union across the size's runs); "failed" = the agent has no
    scorable output in at least one run (n_scenarios_any_missing). Fisher exact
    two-sided on the 2x2 [failed, ok] x [proposed, baseline]. This is the
    robustness face of the "harness compensates for small models" claim — it
    stays valid where tiny complete-case n makes the score comparison
    untestable. Run-level totals are reported descriptively only (runs of the
    same scenario are not independent)."""
    out = []
    for model in models:
        n_union = model["n_scenarios_union"]
        n_runs = model["n_runs"]
        summ = model["agents"]
        rows = []
        miss_p = summ[proposed]["n_scenarios_any_missing"]
        for b in baselines:
            miss_b = summ[b]["n_scenarios_any_missing"]
            p = fisher_exact_2x2(miss_p, n_union - miss_p, miss_b, n_union - miss_b)
            run_level_b = sum(info["missing_by_agent"].get(b, 0) for info in model["per_run"])
            rows.append({
                "baseline": b,
                "proposed_failed_scenarios": miss_p,
                "baseline_failed_scenarios": miss_b,
                "n_scenarios": n_union,
                "baseline_failed_run_level": f"{run_level_b}/{n_runs * n_union}",
                "fisher_p_two_sided": p,
            })
        holm = holm_correct([r["fisher_p_two_sided"] for r in rows])
        for r, ph in zip(rows, holm):
            r["p_holm"] = ph
        out.append({"label": model["label"], "rows": rows})
    return {
        "definition": (
            "Scenario-level failure = agent missing a scorable output in >=1 of the "
            "size's runs (n_scenarios_any_missing). Fisher exact two-sided, Holm over "
            f"{len(baselines)} comparisons per size. Run-level counts descriptive only."
        ),
        "per_model": out,
    }

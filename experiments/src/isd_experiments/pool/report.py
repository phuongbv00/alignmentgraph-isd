"""Console report for a pooled result.

Printed as well as written, because the JSON is for generators and this is for
the person who just spent money on a run and needs to see whether it worked.
"""

from __future__ import annotations

from pathlib import Path

from .. import paths
from ..config import LLM_JUDGE_LEAD

def print_report(pooled: dict, proposed: str, baselines: list[str]) -> None:
    print("\n" + "=" * 78)
    print("POOLED MODEL LADDER — LLM judge scores reported separately; "
          f"lead = {LLM_JUDGE_LEAD}")
    print("=" * 78)
    for model in pooled["models"]:
        print(f"\n## {model['label']}  ({model['n_runs']} runs, "
              f"{model['n_scenarios_union']} scenarios in union)")
        for info in model["per_run"]:
            miss = {a: n for a, n in info["missing_by_agent"].items() if n}
            print(f"  run {Path(info['dir']).name}: {info['n_scenarios_scored']} scenarios scored"
                  + (f", missing {miss}" if miss else ""))
        print(f"  {'agent':20s} {'nCC':>4s} {'miss':>4s} {'ADDIE':>7s} {'Traj':>7s} "
              f"{'Total':>7s} {'sdScen':>7s} {'runSD':>7s}")
        def _sd_cell(value: object) -> str:
            return f"{value:7.2f}" if isinstance(value, float) else f"{'--':>7s}"

        for a, s in model["agents"].items():
            # runSD is None on a single-run cell; sdScen (across scenarios) is
            # always defined and is the one to read here.
            print(f"  {a:20s} {s['n_scenarios_complete']:4d} {s['n_scenarios_any_missing']:4d} "
                  f"{s['mean_addie']:7.2f} {s['mean_traj']:7.2f} "
                  f"{s['mean_total']:7.2f} "
                  f"{_sd_cell(s.get('sd_total_across_scenarios'))} "
                  f"{_sd_cell(s.get('run_to_run_sd'))}")
        comp = model["comparisons"]
        for metric in comp["scores"]:
            block = comp["by_score"][metric]
            lead = "  <-- LEAD (answers the RQ)" if metric == comp["lead_score"] else ""
            print(f"\n  Paired stats on {metric} — {block['label']}{lead}")
            print(f"  ({proposed} - baseline), Holm family = {len(baselines)} "
                  "comparisons per policy in this model size:")
            for policy in ("complete_case", "zero", "min_score"):
                label = {"complete_case": "complete-case",
                         "zero": "sensitivity: failure=0",
                         "min_score":
                             f"sensitivity: failure=min ({block['min_score_floor']:.2f})"}[policy]
                print(f"  [{label}]")
                for r in block["policies"][policy]:
                    if r.get("n", 0) == 0 or "p_raw" not in r:
                        print(f"    {r['baseline']:20s} (no paired scenarios)")
                        continue
                    lo, hi = r["ci95"]
                    print(f"    {r['baseline']:20s} n={r['n']:3d} d={r['mean_diff']:+7.2f} "
                          f"CI95[{lo:+6.2f},{hi:+6.2f}] r_rb={r['rank_biserial_r']:+.2f} "
                          f"p={r['p_raw']:.2e} p_holm={r['p_holm']:.2e}")

    inter = pooled["interaction"]
    print(f"\n## Method x model-size interaction (DiD, largest - smallest) "
          f"on {inter.get('metric')}")
    print(f"  {inter.get('definition', '')}")
    for r in inter.get("per_baseline", []):
        lo, hi = r["did_ci95"]
        trend = "  ".join(f"{k}:{v:+.2f}" for k, v in r["trend_delta_by_size"].items())
        print(f"  vs {r['baseline']:20s} n={r['n_paired_scenarios']:3d} "
              f"DiD={r['did_mean']:+6.2f} CI95[{lo:+6.2f},{hi:+6.2f}] p={r['did_wilcoxon_p']:.2e}")
        print(f"      trend: {trend}  slope/step={r['trend_ols_slope_per_size_step']:+.2f} "
              f"CI95[{r['trend_slope_ci95'][0]:+.2f},{r['trend_slope_ci95'][1]:+.2f}]")

    if pooled.get("token_usage"):
        print("\n## Token usage / runtime (operational metadata, mean per scenario)")
        for label, agents_tok in pooled["token_usage"]["models"].items():
            print(f"  [{label}]")
            for agent, fields in agents_tok.items():
                tt = fields.get("total_tokens", {}).get("mean", float("nan"))
                calls = fields.get("llm_calls", {}).get("mean", float("nan"))
                secs = fields.get("execution_time_seconds", {}).get("mean", float("nan"))
                print(f"    {agent:20s} total_tokens={tt:10.0f}  llm_calls={calls:6.1f}  exec_s={secs:7.1f}")

    if pooled.get("failure_rates"):
        print("\n## Output-failure rates (scenario-level, Fisher exact vs proposed)")
        print(f"  {pooled['failure_rates']['definition']}")
        for entry in pooled["failure_rates"]["per_model"]:
            print(f"  [{entry['label']}]")
            for r in entry["rows"]:
                print(f"    vs {r['baseline']:20s} failed {r['proposed_failed_scenarios']:2d} vs "
                      f"{r['baseline_failed_scenarios']:2d} /{r['n_scenarios']} scenarios "
                      f"(run-level {r['baseline_failed_run_level']:>8s})  "
                      f"p={r['fisher_p_two_sided']:.2e} p_holm={r['p_holm']:.2e}")

    if pooled.get("alignment"):
        print("\n## Alignment metrics (alignment panel, pooled from alignment_scores.json)")
        align = pooled["alignment"]
        print(f"  encoder = {align.get('encoder_label')} "
              f"@ revision {align.get('encoder_revision') or 'UNPINNED'}")
        if not align.get("coverage_complete", True):
            got = align.get("n_scenario_files")
            want = align.get("n_scenario_files_expected")
            pct = 100.0 * got / want if want else float("nan")
            print(f"  WARNING: partial coverage — {got}/{want} (run x scenario) "
                  f"score files found ({pct:.0f}%). The numbers below are pooled "
                  "over what was scored, NOT over the full design; a low per-agent "
                  "n= here is indistinguishable from agent failure. Finish scoring "
                  f"(`{paths.cli()} score`) and re-pool before using these for "
                  f"the paper — `{paths.cli()} audit postrun` lists which run "
                  "dirs are short.")
        if not align.get("encoder_revision_pinned"):
            print("  NOTE: no encoder_revision in the score files — reproducibility "
                  "rests on the embedding cache only. Set `revision` on the "
                  "encoder arm (or --embed-revision-for SLOT=...) and re-score "
                  "to pin the weights.")
        for label, agents_metrics in pooled["alignment"]["models"].items():
            print(f"  {label}:")
            for agent, metrics in agents_metrics.items():
                parts = ", ".join(f"{m}={v['mean']:.3f}(n={v['n_scenarios']})"
                                  for m, v in metrics.items())
                print(f"    {agent:20s} {parts}")
        stats = pooled["alignment"].get("stats")
        if stats:
            print("\n## Alignment panel — paired stats + descriptive, every signal")
            print(f"  {stats['definition']}")
            for entry in stats["per_model"]:
                print(f"  [{entry['label']}]")
                fails = entry.get("align_failures")
                for signal, layers in (entry.get("panel") or {}).items():
                    flag = "" if layers.get("directional", True) else "  (diagnostic, no good direction)"
                    print(f"   -- {signal} [{layers.get('family')}]{flag}")
                    for r in layers.get("comparisons") or []:
                        if r.get("n", 0) == 0 or "p_raw" not in r:
                            print(f"      vs {r['baseline']:20s} (no paired scenarios)")
                            continue
                        lo, hi = r["ci95"]
                        print(f"      vs {r['baseline']:20s} n={r['n']:3d} "
                              f"d={r['mean_diff']:+7.3f} "
                              f"CI95[{lo:+6.3f},{hi:+6.3f}] r_rb={r['rank_biserial_r']:+.2f} "
                              f"p={r['p_raw']:.2e} p_holm={r['p_holm']:.2e} "
                              f"p_panel={r.get('p_holm_panel', float('nan')):.2e}")
                    desc = ", ".join(
                        f"{a}={v['mean']:.3f}[{v['ci95'][0]:.3f},{v['ci95'][1]:.3f}]"
                        for a, v in layers.get("align_descriptive", {}).items())
                    if desc:
                        print(f"      mean [CI95]: {desc}")
                    cond = ", ".join(f"{a}={v['mean']:.3f}(n={v['n']})"
                                     for a, v in layers.get("conditional_align", {}).items())
                    if cond:
                        print(f"      conditional (>=1 objective): {cond}")
                    if fails:
                        for r in layers.get("comparisons_failure_zero") or []:
                            if r.get("n", 0) == 0 or "p_raw" not in r:
                                continue
                            lo, hi = r["ci95"]
                            print(f"        [failure=0] vs {r['baseline']:20s} "
                                  f"n={r['n']:3d} d={r['mean_diff']:+7.3f} "
                                  f"CI95[{lo:+6.3f},{hi:+6.3f}] "
                                  f"p_holm={r['p_holm']:.2e}")
                if fails:
                    fail_desc = ", ".join(
                        f"{a}={v['n_agent_run_cells_missing']} cell(s)/"
                        f"{v['n_scenarios_affected']} scen"
                        for a, v in fails.items())
                    print(f"    missing outputs (excluded from complete-case): {fail_desc}")
                else:
                    print("    missing outputs: none — complete-case == "
                          "failure=0 for this size")
            inter = stats.get("interaction_align")
            if inter:
                print(f"  [interaction {inter['largest']} - {inter['smallest']}]")
                for r in inter["per_baseline"]:
                    if not r.get("n_paired_scenarios"):
                        print(f"    vs {r['baseline']:20s} (no paired scenarios)")
                        continue
                    lo, hi = r["did_ci95"]
                    print(f"    vs {r['baseline']:20s} n={r['n_paired_scenarios']:3d} "
                          f"DiD={r['did_mean']:+7.3f} CI95[{lo:+6.3f},{hi:+6.3f}] "
                          f"p={r['did_wilcoxon_p']:.2e}")
    else:
        print("\n## Alignment metrics: no alignment_scores.json found — skipped (the panel "
              "not yet computed; re-run pooling after it lands).")

    sens = pooled.get("alignment_sensitivity")
    if sens:
        print("\n## Instrument sensitivity (panel robustness — encoder + Bloom axes)")
        print(f"  primary = {sens['primary_encoder']} (alignment_scores.json), "
              f"metric = {sens['metric']} (encoder axis) / "
              f"{sens.get('metric_bloom_axis')} (Bloom axis)")
        for entry in sens["encoders"]:
            if "skipped" in entry:
                print(f"  [{entry['key']}] SKIPPED — {entry['skipped']}")
                continue
            covd = entry.get("coverage") or {}
            cov, want = covd.get("n_scenario_files"), covd.get("n_scenario_files_expected")
            short = "" if covd.get("complete", True) else "  <-- PARTIAL, finish scoring"
            print(f"  [{entry['key']} / {entry.get('encoder_label')}]  "
                  f"axis={entry.get('axis')} on {entry.get('agreement_metric')}  "
                  f"coverage {cov}/{want} scenario file(s){short}")
            for row in entry["agreement_with_primary"].get("per_model") or []:
                if "note" in row:
                    print(f"    {row['label']:14s} {row['note']}")
                    continue
                p_exact = row.get("spearman_p_exact")
                worst = max(
                    (r.get("p_holm", 0.0)
                     for m in (entry.get("stats") or {}).get("per_model") or []
                     if m.get("label") == row["label"]
                     for r in ((m.get("panel") or {}).get(
                         entry.get("agreement_metric") or sens["metric"])
                               or {}).get("comparisons") or []),
                    default=float("nan"))
                top1 = "=" if row["top1_agent_here"] == row["top1_agent_primary"] else "DIFFERS"
                print(f"    {row['label']:14s} rho={row['spearman_rho_agent_means']:.3f} "
                      f"(p_exact={p_exact if p_exact is None else f'{p_exact:.2e}'}) "
                      f"tau_b={row['kendall_tau_b_agent_means']:.3f}  "
                      f"top1={row['top1_agent_here']} ({top1})  "
                      f"rank_prop={row['proposed_rank_here']}  worst p_holm={worst:.2e}")
        s = sens["summary"]
        rho_min = s.get("min_spearman_rho_any_encoder_any_size")
        print(f"  HEADLINE: min rho over {s['n_encoders']} encoder(s) x sizes = "
              f"{'n/a' if rho_min is None else f'{rho_min:.3f}'} ; "
              f"{proposed} ranks first in {s['n_cells_proposed_ranks_first']}/{s['n_cells']} cells")

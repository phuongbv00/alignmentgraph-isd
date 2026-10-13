"""Pooling the alignment panel, and the sensitivity star over its instruments.

The panel is FLAT: six signals, no primary endpoint, no composite. Naming one
signal primary would be an implicit composite, and combining them would assert
a weighting nothing in the study establishes.

Every signal is tested the same way, under failure = 0, with Holm within the
signal over the baselines; complete-case is the sensitivity.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

from .. import paths
from ..alignment.presets import current as arm_registry
from ..alignment.protocol import ALIGNMENT_SIGNALS
from ..config import FAILURE_POLICY, SENSITIVITY_POLICY
from ..runs import extract_alignment_metrics, load_run
from ..stats import (
    BOOT_METHOD,
    BOOT_SEED,
    EXACT_WILCOXON_N_MAX,
    N_BOOT,
    bootstrap_ci,
    holm_correct,
    kendall_tau_b,
    paired,
    spearman_rho,
    wilcoxon_signed_rank,
)
from ..util import mean as _mean
from ..util import sd as _sd
from . import attempts

#: Which single series the one-dimensional summaries plot (the scale/DiD
#: narrative, and the default sensitivity agreement).
#:
#: NOT a primary endpoint. The panel is flat and every signal gets identical
#: inferential treatment; this only picks which one a summary that can show
#: exactly one series will show. Overridable with --sensitivity-metric.
SUMMARY_SIGNAL = "objective_assessment_similarity"

#: Agreement on the Bloom axis must be read on a family-B signal. Swapping the
#: Bloom classifier cannot move a family-A signal at all -- those come from
#: encoder vectors alone -- so scoring that axis on SUMMARY_SIGNAL would report
#: rho = 1.000 as a tautology and call it instrument independence.
BLOOM_SUMMARY_SIGNAL = "objective_cognitive_congruence"

def pool_alignment(models: list[dict], run_dirs_by_model: dict[str, list[Path]],
                   agents: list[str], proposed: str, baselines: list[str],
                   scores_filename: str = "alignment_scores.json",
                   return_scenario_maps: bool = False,
                   lead_metric: str = SUMMARY_SIGNAL) -> Optional[dict]:
    """Pool alignment_scores.json metrics if any exist (the alignment panel). Graceful skip.

    **The inferential layer runs over the whole panel, not one endpoint.**
    Every signal in :data:`PANEL` gets the same treatment under
    ``per_model[].panel[<signal>]``; no signal is hoisted to the top level,
    because a structural hierarchy is exactly the implicit composite the panel
    design removes. Per signal:

      * 'comparisons': proposed vs each baseline, paired by scenario on the
        mean of runs under failure = 0 -- a run that left no output to score
        (the scorer's 'missing_outputs' roster) counts 0.0, the floor of every
        signal. Wilcoxon (exact null) + BCa CI + rank-biserial, Holm within the
        signal over the baselines;
      * 'comparisons_complete_case': the same over the scenarios both agents
        were scored on -- the sensitivity, never called unconditional;
      * 'align_descriptive': per-agent mean + BCa 95% CI under failure = 0;
      * 'complete_case_descriptive': per-agent mean over scored scenarios;
      * 'conditional_align': restricted to scenarios whose output yielded
        >=1 objective in every scored run -- isolates signal quality from
        parse failure.

    Signal-independent, at 'per_model[]' level: 'align_failures' (the missing
    -output roster) and, top-level under stats, 'interaction_align' -- the
    method x model-size DiD on the paired delta of ``lead_metric``.
    """
    PANEL = [signal for signal, _family in ALIGNMENT_SIGNALS]
    out_models = {}
    stats_models = []
    align_maps_by_label: dict[str, dict[str, dict[str, float]]] = {}
    # metric -> label -> agent -> {scenario: value}. Kept for EVERY panel
    # signal, not just the lead one: the sensitivity layer judges each axis on
    # a signal that axis can actually move, so it cannot be locked to one.
    maps_by_metric: dict[str, dict[str, dict[str, dict[str, float]]]] = {}
    found_any = False
    n_scenario_files = 0
    encoder_label: Optional[str] = None
    encoder_revision: Optional[str] = None
    bloom_classifier: Optional[str] = None
    # (encoder, revision, bloom) -> one example file, to hard-fail on a mixed
    # pool. The Bloom arm belongs in this key for the same reason the encoder
    # does: averaging lexicon-scored and BERT-scored cells is not a measurement.
    configs: dict[tuple[Optional[str], Optional[str], Optional[str]], str] = {}
    for model in models:
        label = model["label"]
        runs = [load_run(d, scores_filename) for d in run_dirs_by_model[label]]
        # metric_vals[agent][metric][scenario] = [per-run values]
        metric_vals: dict[str, dict[str, dict[str, list[float]]]] = {}
        # miss_counts[agent][scenario] = #runs where the agent produced no
        # scoreable output (the other half of the roster; see failure policies).
        miss_counts: dict[str, dict[str, int]] = {}
        for run_dir, run in zip(run_dirs_by_model[label], runs):
            held = attempts.scenarios(run_dir)
            for sid in sorted(set(run) | set(held)):
                doc = (run.get(sid) or {}).get("alignment")
                if doc is None and sid not in run and sid in held:
                    # A scenario in which every agent failed has no report to
                    # list it; its artifact, if the scorer wrote one, is read
                    # directly.
                    doc = _read_json(held[sid] / scores_filename)
                if doc is None:
                    # No artifact: an agent attempted here that left no output
                    # still failed. (An output left unscored is refused by the
                    # pool's guard before this point.)
                    for agent in agents:
                        if (attempts.attempted(run_dir, sid, agent)
                                and not attempts.produced(run_dir, sid, agent)):
                            per = miss_counts.setdefault(agent, {})
                            per[sid] = per.get(sid, 0) + 1
                    continue
                found_any = True
                n_scenario_files += 1
                if isinstance(doc, dict):
                    configs.setdefault(
                        (doc.get("encoder"), doc.get("encoder_revision"),
                         doc.get("bloom_classifier")),
                        f"{label}/{sid}",
                    )
                    if encoder_label is None:
                        encoder_label = doc.get("encoder")
                        encoder_revision = doc.get("encoder_revision")
                        bloom_classifier = doc.get("bloom_classifier")
                    for agent, reason in (doc.get("missing_outputs") or {}).items():
                        if agent in agents and reason:
                            per = miss_counts.setdefault(agent, {})
                            per[sid] = per.get(sid, 0) + 1
                for agent, metrics in extract_alignment_metrics(doc, agents).items():
                    for metric, val in metrics.items():
                        metric_vals.setdefault(agent, {}).setdefault(metric, {}) \
                            .setdefault(sid, []).append(val)
        if not metric_vals and not miss_counts:
            continue
        # complete-case: the scenarios the agent left an output for in every
        # run (none on the missing-output roster), the same definition the LLM
        # judge pool uses.
        def per_scenario(metric: str) -> dict[str, dict[str, float]]:
            return {
                agent: {sid: _mean(v) for sid, v in metrics.get(metric, {}).items()
                        if not miss_counts.get(agent, {}).get(sid)}
                for agent, metrics in metric_vals.items()
            }

        # failure = 0: an (agent, scenario, run) cell on the missing-output
        # roster counts 0.0 -- the floor of every signal, and the value a
        # parseable but objective-less output already scores.
        def failure_zero(metric: str) -> dict[str, dict[str, float]]:
            out: dict[str, dict[str, float]] = {}
            for agent in sorted(set(metric_vals) | set(miss_counts)):
                per_scen = metric_vals.get(agent, {}).get(metric, {})
                row: dict[str, float] = {}
                # Sorted: the bootstrap resamples by position, so a set's hash
                # order would move the interval from one pool to the next.
                for sid in sorted(set(per_scen) | set(miss_counts.get(agent, {}))):
                    vals = list(per_scen.get(sid, []))
                    denom = len(vals) + miss_counts.get(agent, {}).get(sid, 0)
                    row[sid] = (sum(vals) / denom) if denom else 0.0
                if row:
                    out[agent] = row
            return out

        # Every panel signal, so a size where every agent failed still carries
        # its zeros; plus whatever else the artifacts report (counts, details).
        metrics_seen = sorted(set(PANEL) | {m for metrics in metric_vals.values()
                                            for m in metrics})
        zero_by_metric = {m: failure_zero(m) for m in metrics_seen}
        out_models[label] = {
            agent: {
                metric: {
                    "n_scenarios": len(zero_by_metric[metric][agent]),
                    "mean": _mean(list(zero_by_metric[metric][agent].values())),
                    "sd_across_scenarios": _sd(list(zero_by_metric[metric][agent].values())),
                }
                for metric in metrics_seen if zero_by_metric[metric].get(agent)
            }
            # An agent that failed everywhere is on the roster only; it is kept,
            # at 0.0, so the agent vectors the sensitivity layer ranks stay whole.
            for agent in sorted(set(metric_vals) | set(miss_counts))
        }

        def paired_rows(metric_map: dict[str, dict[str, float]]) -> list[dict]:
            rows = []
            for b in baselines:
                pmap, bmap = metric_map.get(proposed, {}), metric_map.get(b, {})
                shared = sorted(set(pmap) & set(bmap))
                diffs = [pmap[s] - bmap[s] for s in shared]
                rows.append({"baseline": b, **paired(diffs)})
            with_p = [r for r in rows if "p_raw" in r]
            for r, ph in zip(with_p, holm_correct([r["p_raw"] for r in with_p])):
                r["p_holm"] = ph
                r["holm_family_size"] = len(with_p)
            return rows

        # Conditional-on-parseable-output: the documented criterion is ">=1
        # objective", so read the objective COUNT, not the incidental
        # definedness of porter_mean (which is also None when the objectives
        # carry no Bloom-classifiable verb — a scenario that has objectives and
        # belongs in the conditional set). Require it in every scored run, so a
        # mean-of-runs is never half parse-failure.
        def conditional(metric_map: dict[str, dict[str, float]]) -> dict:
            return {
                agent: {
                    sid: val
                    for sid, val in metric_map[agent].items()
                    if min(metric_vals[agent].get("counts.objectives", {})
                           .get(sid, [0])) >= 1
                }
                for agent in metric_map
            }

        panel: dict[str, dict] = {}
        absent_signals: list[str] = []
        for signal in PANEL:
            cc_map = per_scenario(signal)
            if metric_vals and not any(signal in m for m in metric_vals.values()):
                # Skipping here keeps the pool usable, but the run is NOT
                # reportable: the panel's defence against selective reporting is
                # that every signal is reported for every comparison. Collected
                # and raised after the loop so the message names all of them.
                absent_signals.append(signal)
                continue
            zero_map = zero_by_metric[signal]
            maps_by_metric.setdefault(signal, {})[label] = zero_map
            if signal == lead_metric:
                align_maps_by_label[label] = zero_map
            panel[signal] = {
                "family": dict(ALIGNMENT_SIGNALS)[signal],
                "align_descriptive": {
                    agent: {
                        "n": len(vals),
                        "mean": _mean(list(vals.values())),
                        "ci95": list(bootstrap_ci(list(vals.values()))),
                    }
                    for agent, vals in sorted(zero_map.items()) if vals
                },
                "complete_case_descriptive": {
                    agent: {"n": len(vals), "mean": _mean(list(vals.values()))}
                    for agent, vals in sorted(cc_map.items()) if vals
                },
                "conditional_align": {
                    agent: {"n": len(vals), "mean": _mean(list(vals.values()))}
                    for agent, vals in sorted(conditional(cc_map).items()) if vals
                },
                "comparisons": paired_rows(zero_map),
                "comparisons_complete_case": paired_rows(cc_map),
            }

        if absent_signals:
            raise SystemExit(
                f"[{label}] panel incomplete: {absent_signals} defined on no "
                f"scenario, so the pooled panel would carry "
                f"{len(panel)}/{len(PANEL)} signals. Re-score these run dirs with "
                f"`{paths.cli()} judge alignment --overwrite` (a signal added since the "
                f"artifacts were written is absent from them, and the cached "
                f"artifacts are otherwise valid so a plain re-run reuses them)."
            )

        stats_models.append({
            "label": label,
            "panel": panel,
            "n_panel_signals": len(panel),
            "align_failures": {
                agent: {
                    "n_scenarios_affected": len(sids),
                    "n_agent_run_cells_missing": sum(sids.values()),
                    "scenarios": sorted(sids),
                }
                for agent, sids in sorted(miss_counts.items()) if sids
            },
        })
    if not found_any:
        return None

    # One pool = one protocol configuration. Mixing encoders (or two weight
    # revisions of one encoder) across run dirs produces a mean that measures
    # nothing, and it is invisible when only the first file's metadata is
    # kept. Fail loudly instead.
    if len(configs) > 1:
        detail = "; ".join(
            f"{enc!r} @ revision {rev!r} + bloom {bloom!r} (e.g. {where})"
            for (enc, rev, bloom), where in sorted(configs.items(), key=lambda kv: kv[1])
        )
        raise SystemExit(
            f"[{scores_filename}] the pooled run dirs were scored with "
            f"{len(configs)} different protocol configurations: {detail}. "
            f"Re-score every run dir with one configuration "
            f"(`{paths.cli()} judge alignment --overwrite`) before pooling — a mean over "
            "two instruments is not an alignment measurement."
        )

    # Method x model-size interaction on the lead metric (largest -
    # smallest size), mirroring interaction_tests()'s convention for LLM judge Total.
    interaction_align = None
    labels_with = [m["label"] for m in models if m["label"] in align_maps_by_label]
    if len(labels_with) >= 2:
        small, large = labels_with[0], labels_with[-1]
        per_baseline = []
        for b in baselines:
            def delta_map(label: str) -> dict[str, float]:
                pmap = align_maps_by_label[label].get(proposed, {})
                bmap = align_maps_by_label[label].get(b, {})
                return {s: pmap[s] - bmap[s] for s in set(pmap) & set(bmap)}

            d_small, d_large = delta_map(small), delta_map(large)
            shared = sorted(set(d_small) & set(d_large))
            if not shared:
                per_baseline.append({"baseline": b, "n_paired_scenarios": 0})
                continue
            did_vals = [d_large[s] - d_small[s] for s in shared]
            lo, hi = bootstrap_ci(did_vals)
            _, p, _ = wilcoxon_signed_rank(did_vals)
            per_baseline.append({
                "baseline": b,
                "n_paired_scenarios": len(shared),
                "did_mean": _mean(did_vals),
                "did_ci95": [lo, hi],
                "did_wilcoxon_p": p,
            })
        interaction_align = {
            "definition": (
                f"DiD on the paired {lead_metric} delta (proposed - "
                f"baseline): value at the largest size ({large}) minus the "
                f"smallest ({small}), per scenario; negative = the gap narrows "
                "as the model grows (i.e. widens toward small models). "
                f"{BOOT_METHOD} bootstrap CI ({N_BOOT}, seed {BOOT_SEED}) + Wilcoxon p on the "
                "per-scenario DiD values."
            ),
            "smallest": small,
            "largest": large,
            "per_baseline": per_baseline,
        }

    # Coverage: how many (run x scenario) cells SHOULD carry a score file vs how
    # many were found. A half-scored sweep pools as if it were the whole thing —
    # and the per-agent n= in the report cannot distinguish "the agent failed
    # here" (real data, handled by the failure policy) from "this scenario was
    # never scored" (operator error). isd-exp audit postrun flags this per run dir;
    # this is the second line of defence, at the point the numbers are made.
    n_expected = sum(m["n_scenarios_union"] * m["n_runs"] for m in models)
    coverage_complete = n_scenario_files >= n_expected

    result = {
        "source": f"{scores_filename} per scenario dir (pooled mean across runs, then across scenarios)",
        "encoder_label": encoder_label,
        "encoder_revision": encoder_revision,
        "encoder_revision_pinned": encoder_revision is not None,
        "bloom_classifier": bloom_classifier,
        "n_scenario_files": n_scenario_files,
        "n_scenario_files_expected": n_expected,
        "coverage_complete": coverage_complete,
        "models": out_models,
        "stats": {
            "definition": (
                "A PANEL of %d signals, no primary endpoint and no composite: "
                "per_model[].panel[<signal>] carries the same layers for every "
                "signal, reported win or lose. Continuous signals are mean-max "
                "RECTIFIED cosine (max(0,cos) on [0,1]; no matching threshold). "
                "'comparisons' = paired diffs (proposed - baseline) per "
                "scenario, mean of runs under %s: a run that left no output to "
                "score counts 0.0, the floor of every signal. Wilcoxon two-sided "
                "(exact null for n<=%d), %s bootstrap CI (%d, seed %d), "
                "rank-biserial r; p_holm = Holm within one signal (%d "
                "comparisons). 'comparisons_complete_case' = the same over the "
                "scenarios both agents were scored on (%s, the sensitivity). "
                "align_descriptive = per-agent mean + BCa 95%% CI under %s; "
                "complete_case_descriptive = the mean over scored scenarios. "
                "align_failures counts the missing-output cells. "
                "conditional_align = over scenarios whose output yielded >=1 "
                "objective in every scored run (isolates signal quality from "
                "parse failure). interaction_align = method x model-size DiD on "
                "the paired delta of %s (%s)."
                % (len(PANEL), FAILURE_POLICY, EXACT_WILCOXON_N_MAX, BOOT_METHOD,
                   N_BOOT, BOOT_SEED, len(baselines), SENSITIVITY_POLICY,
                   FAILURE_POLICY, lead_metric, FAILURE_POLICY)
            ),
            "panel_signals": [
                {"signal": signal, "family": family}
                for signal, family in ALIGNMENT_SIGNALS
            ],
            "lead_metric": lead_metric,
            "per_model": stats_models,
            "interaction_align": interaction_align,
        },
    }
    if return_scenario_maps:
        # Per-scenario values, keyed metric -> label -> agent -> scenario. Every
        # panel signal is kept, because the sensitivity layer judges each axis
        # on a signal that axis can move. Only that layer needs these; main()
        # pops the key before the JSON dump.
        result["_align_maps"] = maps_by_metric
    return result

def _read_json(path: Path) -> Optional[dict]:
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None
    return doc if isinstance(doc, dict) else None


def _sign(x: float) -> int:
    return (x > 0) - (x < 0)


def _rank_of(agent: str, means: dict[str, float]) -> Optional[int]:
    """1-based rank of ``agent`` by descending mean (1 = best)."""
    if agent not in means:
        return None
    order = sorted(means, key=lambda a: -means[a])
    return order.index(agent) + 1

def _agreement(primary: dict, arm: dict, primary_maps: dict, arm_maps: dict,
               models: list[dict], agents: list[str], proposed: str,
               baselines: list[str], metric: str) -> dict:
    """Cross-encoder agreement between one sweep arm and the primary encoder.

    The headline is a rank correlation over the AGENT VECTOR, per model size:
    that is literally the claim the paper makes ("the ranking of agents is the
    same under a different encoder"). Spearman and Kendall tau-b are both
    reported, descriptively -- at n = 7 agents Spearman is noisy and tau-b is
    the one to quote; neither is tested.

    A high rho can still coexist with a flipped conclusion, so three non-rank
    corroborations travel with it: top-1 agreement, the proposed agent's rank,
    and whether the six paired deltas keep their sign and their Holm verdict.
    A fourth, scenario-level Spearman for the proposed agent (n ~ 90), answers
    the different question of whether the encoders agree about WHICH scenarios
    are well aligned — and unlike the agent vector it is not small-n.
    """
    per_model = []
    for model in models:
        label = model["label"]
        p_agents = (primary.get("models") or {}).get(label) or {}
        a_agents = (arm.get("models") or {}).get(label) or {}
        common = [
            a for a in agents
            if (p_agents.get(a, {}).get(metric, {}).get("mean") is not None
                and a_agents.get(a, {}).get(metric, {}).get("mean") is not None)
        ]
        if len(common) < 3:
            per_model.append({"label": label, "n_agents": len(common),
                              "note": "too few shared agents for a rank correlation"})
            continue
        p_means = {a: p_agents[a][metric]["mean"] for a in common}
        a_means = {a: a_agents[a][metric]["mean"] for a in common}
        xs = [p_means[a] for a in common]
        ys = [a_means[a] for a in common]

        # scenario-level, proposed agent only (n ~ 90, not small-n)
        p_scen = ((primary_maps.get(metric) or {}).get(label) or {}).get(proposed, {})
        a_scen = ((arm_maps.get(metric) or {}).get(label) or {}).get(proposed, {})
        shared = sorted(set(p_scen) & set(a_scen))
        scen_rho = (spearman_rho([p_scen[s] for s in shared],
                                 [a_scen[s] for s in shared])
                    if len(shared) >= 3 else None)

        # do the paired verdicts survive the encoder swap?
        def rows_of(pooled: dict) -> dict[str, dict]:
            for entry in (pooled.get("stats") or {}).get("per_model") or []:
                if entry.get("label") == label:
                    layers = (entry.get("panel") or {}).get(metric) or {}
                    return {r["baseline"]: r for r in layers.get("comparisons") or []}
            return {}

        p_rows, a_rows = rows_of(primary), rows_of(arm)
        same_sign = same_verdict = n_cmp = 0
        for b in baselines:
            pr, ar = p_rows.get(b), a_rows.get(b)
            if not pr or not ar or "mean_diff" not in pr or "mean_diff" not in ar:
                continue
            n_cmp += 1
            if _sign(pr["mean_diff"]) == _sign(ar["mean_diff"]):
                same_sign += 1
            if (pr.get("p_holm", 1.0) < 0.05) == (ar.get("p_holm", 1.0) < 0.05):
                same_verdict += 1

        per_model.append({
            "label": label,
            "n_agents": len(common),
            "spearman_rho_agent_means": spearman_rho(xs, ys),
            "kendall_tau_b_agent_means": kendall_tau_b(xs, ys),
            "mean_abs_diff_agent_means": _mean([abs(a - b) for a, b in zip(xs, ys)]),
            "top1_agent_primary": max(p_means, key=lambda a: p_means[a]),
            "top1_agent_here": max(a_means, key=lambda a: a_means[a]),
            "proposed_rank_primary": _rank_of(proposed, p_means),
            "proposed_rank_here": _rank_of(proposed, a_means),
            "n_scenarios_paired_proposed": len(shared),
            "spearman_rho_scenario_level_proposed": scen_rho,
            "sign_agreement_vs_baselines": {
                "n": n_cmp, "n_same_sign": same_sign,
                "n_same_holm_verdict_at_05": same_verdict,
            },
        })

    rhos = [r["spearman_rho_agent_means"] for r in per_model
            if isinstance(r.get("spearman_rho_agent_means"), float)
            and r["spearman_rho_agent_means"] == r["spearman_rho_agent_means"]]
    taus = [r["kendall_tau_b_agent_means"] for r in per_model
            if isinstance(r.get("kendall_tau_b_agent_means"), float)
            and r["kendall_tau_b_agent_means"] == r["kendall_tau_b_agent_means"]]
    return {
        "per_model": per_model,
        "pooled_over_sizes": {
            "n_sizes": len(per_model),
            "min_spearman_rho": min(rhos) if rhos else None,
            "mean_spearman_rho": _mean(rhos) if rhos else None,
            "min_kendall_tau_b": min(taus) if taus else None,
            "n_sizes_top1_agrees": sum(
                1 for r in per_model
                if r.get("top1_agent_here") and r["top1_agent_here"] == r.get("top1_agent_primary")),
            "n_sizes_proposed_rank_one": sum(
                1 for r in per_model if r.get("proposed_rank_here") == 1),
        },
    }

def pool_alignment_sensitivity(models: list[dict],
                               run_dirs_by_model: dict[str, list[Path]],
                               agents: list[str], proposed: str,
                               baselines: list[str], arms: list[tuple[str, str]],
                               primary_pooled: Optional[dict], primary_key: str,
                               metric: str,
                               bloom_metric: str = BLOOM_SUMMARY_SIGNAL) -> Optional[dict]:
    """Pool the sweep arms and score each one's agreement with the primary.

    An instrument is swept exactly like model size: the SAME runs are re-scored
    with a different encoder (family A) or a different Bloom classifier (family
    B), so every arm reuses pool_alignment() unchanged and only differs in
    which ``alignment_scores.<suffix>.json`` it reads. An arm with no artifacts
    on disk is recorded as skipped rather than dropped, so a half-finished
    sweep is visible in the JSON instead of looking complete.
    """
    if not arms:
        return None
    registry = arm_registry()
    bloom_keys, baseline_keys = set(registry.bloom), set(registry.baseline)
    primary_maps = (primary_pooled or {}).get("_align_maps") or {}
    encoders = []
    for key, suffix in arms:
        scores_filename = f"alignment_scores.{suffix}.json" if suffix else "alignment_scores.json"
        axis = ("bloom" if key in bloom_keys
                else "baseline" if key in baseline_keys else "encoder")
        # Each axis is judged on a signal it can actually move (see
        # BLOOM_SUMMARY_SIGNAL).
        arm_metric = bloom_metric if axis == "bloom" else metric
        pooled = pool_alignment(models, run_dirs_by_model, agents, proposed,
                                baselines, scores_filename=scores_filename,
                                return_scenario_maps=True, lead_metric=arm_metric)
        if pooled is None:
            encoders.append({"key": key, "axis": axis, "suffix": suffix,
                             "scores_filename": scores_filename,
                             "agreement_metric": arm_metric,
                             "skipped": f"no {scores_filename} found under any run dir"})
            continue
        arm_maps = pooled.pop("_align_maps", {})
        entry = {
            "key": key,
            "axis": axis,
            "agreement_metric": arm_metric,
            "suffix": suffix,
            "scores_filename": scores_filename,
            "encoder_label": pooled.get("encoder_label"),
            "encoder_revision": pooled.get("encoder_revision"),
            "bloom_classifier": pooled.get("bloom_classifier"),
            "coverage": {
                "n_scenario_files": pooled.get("n_scenario_files"),
                "n_scenario_files_expected": pooled.get("n_scenario_files_expected"),
                "complete": pooled.get("coverage_complete"),
            },
            "models": pooled.get("models"),
            "stats": pooled.get("stats"),
        }
        entry["agreement_with_primary"] = (
            _agreement(primary_pooled, pooled, primary_maps, arm_maps, models,
                       agents, proposed, baselines, arm_metric)
            if primary_pooled else
            {"note": f"no primary ({primary_key}) alignment_scores.json pooled — "
                     "agreement undefined", "per_model": [], "pooled_over_sizes": {}}
        )
        encoders.append(entry)

    scored = [e for e in encoders if "skipped" not in e]
    rhos, taus, cells, first, p_max = [], [], 0, 0, None
    for entry in scored:
        for row in entry["agreement_with_primary"].get("per_model") or []:
            rho, tau = row.get("spearman_rho_agent_means"), row.get("kendall_tau_b_agent_means")
            if isinstance(rho, float) and rho == rho:
                rhos.append(rho)
            if isinstance(tau, float) and tau == tau:
                taus.append(tau)
            cells += 1
            first += 1 if row.get("proposed_rank_here") == 1 else 0
        # Read each arm on ITS OWN axis signal. Using the encoder-axis metric for
        # every arm silently reported the Bloom arm's similarity p-values, which
        # a Bloom swap cannot move: 3.6e-13 instead of that arm's true 1.7e-02.
        arm_metric = entry.get("agreement_metric") or (
            bloom_metric if (entry.get("axis") == "bloom") else metric)
        for entry_model in (entry.get("stats") or {}).get("per_model") or []:
            layers = (entry_model.get("panel") or {}).get(arm_metric) or {}
            for row in layers.get("comparisons") or []:
                if "p_holm" in row:
                    p_max = row["p_holm"] if p_max is None else max(p_max, row["p_holm"])
    return {
        "definition": (
            "Instrument as a swept dimension: the SAME runs re-scored by each "
            "arm. This is a STAR, not an encoder-only sweep — arms vary "
            "the ENCODER or apply the BASELINE correction (own minus the same "
            f"agent's foreign scenarios; both compared on '{metric}') or vary the "
            f"BLOOM CLASSIFIER (compared on '{bloom_metric}'), because a Bloom "
            "swap cannot move a cosine and an encoder swap cannot move a Bloom "
            "level. Read each arm's 'axis' "
            "and 'agreement_metric' rather than assuming one signal. "
            f"'{primary_key}' owns the unsuffixed artifact and stays in "
            "pooled['alignment']; the arms here are read from "
            "alignment_scores.<suffix>.json. agreement_with_primary compares "
            "the per-size agent vector on that arm's own signal — Spearman rho and "
            "Kendall tau-b (descriptive, not tested), plus top-1 / "
            "proposed-rank / sign / Holm-verdict agreement, and a "
            "scenario-level Spearman for the proposed agent."
        ),
        "primary_encoder": primary_key,
        "metric": metric,
        "metric_bloom_axis": bloom_metric,
        "encoders": encoders,
        "summary": {
            "n_encoders": len(scored),
            "n_skipped": len(encoders) - len(scored),
            "min_spearman_rho_any_encoder_any_size": min(rhos) if rhos else None,
            "min_kendall_tau_b_any_encoder_any_size": min(taus) if taus else None,
            "top1_stable_all_encoders_all_sizes": all(
                row.get("top1_agent_here") == row.get("top1_agent_primary")
                for e in scored
                for row in e["agreement_with_primary"].get("per_model") or []
            ) if cells else None,
            "n_cells_proposed_ranks_first": first,
            "n_cells": cells,
            "max_p_holm_any_encoder_any_size": p_max,
        },
    }

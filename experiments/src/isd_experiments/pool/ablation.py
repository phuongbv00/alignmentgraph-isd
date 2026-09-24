"""Pooling the ablation experiment: a 2x2 factorial over decomposition and
substrate.

Reuses the comparison pooling machinery unchanged -- same runs, same readers,
same statistics -- and adds three things the factorial needs:

* **Arm verification.** A run whose recorded ``metadata.run_config`` disagrees
  with the arm it is filed under is a silently wrong factorial, so pooling
  refuses it rather than reporting it.
* **Factorial effects.** The four arms are a complete 2x2, so simple effects
  and an interaction are available. Reading only "arm vs reference" is a
  main-effects-only view, and it hides the case where one mechanism does
  nothing *because the other already did the job*.
* **A drift bound.** The reference arm is re-run inside this experiment rather
  than borrowed from the comparison, so the gap between the two is a bound on
  how much of an arm delta could be session effect rather than treatment.

The cells are read from ``experiment.toml``, not hard-coded: a different
factorial is a config edit.
"""

from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path

from .. import paths, schema
from ..alignment.protocol import ALIGNMENT_SIGNALS
from ..config import current as current_config
from ..runs import iter_scenario_dirs, load_run
from ..stats import BOOT_SEED, N_BOOT, bootstrap_ci, rank_biserial, wilcoxon_signed_rank
from ..util import mean as _mean
from . import diagnostics
from .comparison import discover
from .llm_judge import compare_model, pool_model
from .panel import pool_alignment
from .tokens import pool_tokens


def factorial_cells() -> dict[tuple[str, str], str]:
    """(agent_mode, context_mode) -> arm id, from the declared arms."""
    profile = current_config().profile("ablation")
    return {(a.agent_mode, a.context_mode): a.id for a in profile.arms}


def expected_flags() -> dict[str, dict[str, str]]:
    """Arm id -> the run_config a run filed under it must record."""
    profile = current_config().profile("ablation")
    return {a.id: a.expected_flags for a in profile.arms}


#: LLM judge scores for the factorial readout. The ablation narrative is NOT led
#: by the LLM judge -- the mechanism layer (coverage, the violation ledger, `gave_up`,
#: context behaviour) and the deterministic panel are the readout, and the LLM
#: judge is a cross-check.
FACTORIAL_LLM_JUDGE_SCORES = ("addie_median", "trajectory_score", "total_score")

def check_arm_flags(run_dirs_by_model: dict[str, list[Path]],
                    agents: list[str]) -> dict:
    """Verify each arm ran the config its agent id claims. Hard error on mismatch."""
    report: dict[str, dict[str, str]] = {}
    mismatches: list[str] = []
    for label, run_dirs in run_dirs_by_model.items():
        report[label] = {}
        for run_dir in run_dirs:
            for agent in agents:
                expected = expected_flags().get(agent)
                if expected is None:
                    report[label][agent] = "no expectation registered — skipped"
                    continue
                run_config = None
                for _sid, scen_dir in iter_scenario_dirs(run_dir):
                    traj = scen_dir / f"{agent}_trajectory.json"
                    if not traj.exists():
                        continue
                    try:
                        md = json.loads(traj.read_text(encoding="utf-8")).get("metadata") or {}
                    except (json.JSONDecodeError, OSError):
                        continue
                    run_config = md.get("run_config")
                    break  # one scenario suffices: flags are fixed per process
                if run_config is None:
                    report[label][agent] = (
                        "WARN: no metadata.run_config found (no trajectory "
                        "written for this arm — did it crash?)"
                    )
                    continue
                got = {k: run_config.get(k) for k in expected}
                if got == expected:
                    report[label][agent] = "ok"
                else:
                    report[label][agent] = f"MISMATCH: expected {expected}, got {got}"
                    mismatches.append(f"{label}/{agent}: expected {expected}, got {got}")
    if mismatches:
        print("\nERROR: arm flag mismatch — an arm did not run the config its id claims:",
              file=sys.stderr)
        for m in mismatches:
            print(f"  {m}", file=sys.stderr)
        sys.exit(1)
    return report


def a0_consistency(models: list[dict], a0: str, ladder_pooled_path: Path) -> dict:
    """A0 here (this experiment) vs A0 in the pooled ladder (the comparison experiment) — a drift gauge.

    Read it as a BOUND, not as a result: it says how much of an arm delta could
    be session effect rather than treatment. Two things make a non-zero value
    expected rather than alarming — the two experiments have separate LLM judge
    sessions, and this experiment scores 30 scenarios where the comparison experiment scores 90. Because
    ``test_30`` is a stratified subset of ``test_90``, the two are drawn from
    one pool and the comparison is meaningful; it is still not paired, so a
    small delta carries sampling as well as drift.

    Never use it to compare an arm against the ladder's A0. That is exactly the
    cross-experiment comparison this experiment exists to avoid.
    """
    try:
        ladder = json.loads(ladder_pooled_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        return {"error": f"could not read {ladder_pooled_path}: {exc}"}
    ladder_by_label = {m["label"]: m for m in ladder.get("models", [])}
    rows = []
    for model in models:
        label = model["label"]
        abl = model["agents"].get(a0, {})
        lad = ladder_by_label.get(label, {}).get("agents", {}).get(a0)
        if lad is None:
            rows.append({"label": label,
                         "note": f"size '{label}' not found in ladder pooled JSON"})
            continue
        delta = abl.get("mean_total", float("nan")) - lad.get("mean_total", float("nan"))
        rows.append({
            "label": label,
            "a0_mean_total_ablation_session": abl.get("mean_total"),
            "a0_mean_total_ladder_pooled": lad.get("mean_total"),
            "delta": delta,
            "ladder_run_to_run_sd": lad.get("run_to_run_sd"),
            "within_2x_ladder_run_sd": (
                abs(delta) <= 2 * lad["run_to_run_sd"]
                if isinstance(lad.get("run_to_run_sd"), (int, float)) else None
            ),
        })
    return {
        "definition": (
            "A0 (full pipeline) as run inside this experiment vs A0 as run in the comparison experiment "
            "ladder: two separate executions, separate LLM judge sessions, and "
            "different scenario counts (test_30 is a 30-scenario stratified "
            "subset of test_90). A non-zero delta is expected. It bounds how "
            "much of an arm delta could be session effect rather than "
            "treatment, and is context for the write-up — never an arm "
            "comparison."
        ),
        "per_model": rows,
    }


# ── 2x2 factorial layer ──────────────────────────────────────────────────────


def _structured_activity(tr: dict) -> tuple[int, int]:
    """Read validation/repair activity across all trajectory schemas.

    v3 writes taxonomy actions + a context object. v2's unified list used a
    flat ``type`` discriminator, while v1 kept parallel event streams. Keep
    both fallbacks so the ablation pool remains able to compare existing runs.
    """
    events = tr.get("events")
    if events is None:
        return (
            len(tr.get("verifier_events") or []),
            len(tr.get("repair_events") or []),
        )

    if any("type" in event for event in events):
        return (
            sum(1 for event in events if event.get("type") == "verifier"),
            sum(1 for event in events if event.get("type") == "repair"),
        )

    # v3: count only the structured repair record (the one that has a repaired
    # violation), not a recovery action that happens to apply a repair rule.
    verifier_n = sum(1 for event in events if event.get("action") == "verify")
    repair_n = sum(
        1 for event in events
        if event.get("action") == "repair"
        and isinstance(event.get("context"), dict)
        and "violation_type" in event["context"]
    )
    return verifier_n, repair_n

#: Every signal the factorial layer is computed on: the three LLM judge scores plus
#: the whole alignment panel. Deliberately exhaustive — the panel's defence against
#: selective reporting is that every signal is reported for every comparison,
#: and a factorial computed on a hand-picked subset would break exactly that.
#: The paper's main text leads on one signal; the appendix carries all of them.
FACTORIAL_MEASURES = FACTORIAL_LLM_JUDGE_SCORES + tuple(
    sig for sig, _family in ALIGNMENT_SIGNALS)


def _paired(diffs: list[float]) -> dict:
    if not diffs:
        return {"n": 0}
    w, p, n_eff = wilcoxon_signed_rank(diffs)
    lo, hi = bootstrap_ci(diffs)
    return {"n": len(diffs), "n_effective_nonzero": n_eff,
            "mean_diff": _mean(diffs), "ci95": [lo, hi],
            "wilcoxon_w_plus": w, "p_raw": p,
            "rank_biserial_r": rank_biserial(diffs)}


def per_scenario_maps(run_dirs: list[Path], agents: list[str]) -> dict:
    """signal -> agent -> {scenario: mean over runs}.

    One pass over the run dirs picks up both the LLM judge fields (from
    comparison_report.json) and the alignment panel (from alignment_scores.json),
    so the factorial layer never re-derives a number a different way than the
    rest of the pool does.
    """
    acc: dict[str, dict[str, dict[str, list[float]]]] = {
        sig: {a: {} for a in agents} for sig in FACTORIAL_MEASURES
    }
    panel_signals = [sig for sig, _f in ALIGNMENT_SIGNALS]
    for run_dir in run_dirs:
        for sid, payload in load_run(run_dir).items():
            for a in agents:
                r = (payload.get("rankings") or {}).get(a) or {}
                for sig in FACTORIAL_LLM_JUDGE_SCORES:
                    v = r.get(sig)
                    if isinstance(v, (int, float)):
                        acc[sig][a].setdefault(sid, []).append(float(v))
            doc = payload.get("alignment") or {}
            for a, sc in (doc.get("agents") or {}).items():
                if a not in agents:
                    continue
                for sig in panel_signals:
                    v = sc.get(sig)
                    if isinstance(v, (int, float)):
                        acc[sig][a].setdefault(sid, []).append(float(v))
    return {sig: {a: {sid: _mean(vals) for sid, vals in by_sid.items()}
                  for a, by_sid in by_agent.items()}
            for sig, by_agent in acc.items()}


def factorial_effects(maps: dict[str, dict[str, float]]) -> dict:
    """Simple effects + interaction for one signal at one model size.

    Axis 1 (decomposition): multi-agent (5 Designers) vs single (one
    monolithic agent running the same steps). Axis 2 (context
    representation): graph (structured injection) vs prose (narrative
    serialization). Both simple effects are reported as multi/graph MINUS
    single/prose (i.e. "the richer setting minus the plainer one"), so a
    positive number always favours multi-agent / graph-context respectively.
    """
    cells = {k: maps.get(v, {}) for k, v in factorial_cells().items()}
    shared = sorted(set.intersection(*(set(c) for c in cells.values()))) if all(
        cells.values()) else []
    if not shared:
        return {"n": 0, "note": "no scenario scored for all four cells"}
    g = lambda key: [cells[key][s] for s in shared]  # noqa: E731
    multi_graph, single_graph = g(("multi", "graph")), g(("single", "graph"))
    multi_prose, single_prose = g(("multi", "prose")), g(("single", "prose"))
    decomposition_ctx_graph = [a - b for a, b in zip(multi_graph, single_graph)]
    decomposition_ctx_prose = [a - b for a, b in zip(multi_prose, single_prose)]
    context_decomp_multi = [a - b for a, b in zip(multi_graph, multi_prose)]
    context_decomp_single = [a - b for a, b in zip(single_graph, single_prose)]
    interaction = [a - b for a, b in zip(decomposition_ctx_graph, decomposition_ctx_prose)]
    return {
        "n_scenarios": len(shared),
        "cell_means": {f"agentmode_{k[0]}__contextmode_{k[1]}": _mean(list(cells[k][s] for s in shared))
                       for k in factorial_cells()},
        "decomposition_effect_given_context_graph": _paired(decomposition_ctx_graph),
        "decomposition_effect_given_context_prose": _paired(decomposition_ctx_prose),
        "context_effect_given_decomposition_multi": _paired(context_decomp_multi),
        "context_effect_given_decomposition_single": _paired(context_decomp_single),
        "interaction": _paired(interaction),
    }


def self_validation_activity(run_dirs_by_model: dict[str, list[Path]],
                             agents: list[str]) -> list[dict]:
    """How often self-validation fired and repaired, per arm and size.

    Self-validation is always on (in both `agent_mode` values — see
    config.py), so this is not "ablation mechanism evidence" the way it was
    when the verifier itself was one of the two switched axes. It separates
    "self-validation runs but finds nothing to fix" from "it runs and repairs
    a lot", which is context for reading the decomposition effect.

    Only comparable across arms once both arms record per-Designer
    self-validation. A run dir where the single arm's verifier_events are a
    constant 1.00/scenario against multi's 7.20 predates that instrumentation:
    the number there is an instrumentation and budget gap, not a difference in
    how much either arm found to fix.
    """
    out = []
    for label, dirs in run_dirs_by_model.items():
        per_arm: dict[str, dict[str, list[float]]] = {
            a: {"verifier_events": [], "repair_events": []} for a in agents}
        for run_dir in dirs:
            for _sid, scen_dir in iter_scenario_dirs(run_dir):
                for a in agents:
                    path = scen_dir / f"{a}_trajectory.json"
                    if not path.exists():
                        continue
                    try:
                        doc = json.loads(path.read_text(encoding="utf-8"))
                    except (json.JSONDecodeError, OSError):
                        continue
                    tr = doc.get("trajectory") or {}
                    verifier_n, repair_n = _structured_activity(tr)
                    per_arm[a]["verifier_events"].append(verifier_n)
                    per_arm[a]["repair_events"].append(repair_n)
        out.append({
            "label": label,
            "arms": {
                a: {
                    "n_scenario_runs": len(v["verifier_events"]),
                    "verifier_events_mean": _mean(v["verifier_events"]),
                    "repair_events_mean": _mean(v["repair_events"]),
                    "pct_scenario_runs_with_repair": (
                        100.0 * sum(1 for x in v["repair_events"] if x > 0)
                        / len(v["repair_events"]) if v["repair_events"] else float("nan")),
                }
                for a, v in per_arm.items() if v["verifier_events"]
            },
        })
    return out


def mechanism_layer(run_dirs_by_model: dict[str, list[Path]],
                    agents: list[str]) -> list[dict]:
    """What each arm DID, per size: the readout the factorial is about.

    The LLM judge and the panel score the deliverable; these read how it came to
    be (see ``diagnostics``). Per arm, four summaries:

    ``autonomy``           per-stage counters. The registered directional
                           prediction is read here: context grows across stages
                           in the ``single`` arms and does not in ``multi``.
                           ``pct_via_budget_exhaustion`` is what the
                           decomposition claim rests on -- an arm CUT by its
                           ceiling has a ceiling inside its delta -- and
                           ``history_dropped`` separates a model that degraded
                           from one that hit the serving window.
    ``relation_coverage``  mean coverage per relation. Graph substrate only: a
                           prose run builds no graph, so its entry is None, and
                           that absence is the auditability contrast.
    ``ledger``             every finding and what became of it. Recorded on both
                           substrates, but NOT comparable across ``context_mode``:
                           prose runs only the within-artifact checks, so fewer
                           findings there is fewer checks, not a better design.
    ``health``             stopped runs, runs with errors, the aggregate gate.

    An arm with no harness records (run dirs from before the agentic executor)
    reads None throughout rather than zeros.
    """
    out = []
    for label, dirs in run_dirs_by_model.items():
        cells = diagnostics.collect(dirs, agents)
        arms = {a: diagnostics.summarize(by_sid, diagnostics.STAGE_ORDER)
                for a, by_sid in cells.items() if by_sid}
        out.append({"label": label, "arms": arms,
                    "note": ("" if arms else "no agent trajectories in these run dirs")})
    return out


def factorial_layer(run_dirs_by_model: dict[str, list[Path]],
                    agents: list[str]) -> dict:
    missing = [a for a in factorial_cells().values() if a not in agents]
    if missing:
        return {"skipped": f"arms missing from this pool: {missing}"}
    measures: dict[str, dict] = {sig: {"per_model": []} for sig in FACTORIAL_MEASURES}
    for label, dirs in run_dirs_by_model.items():
        maps = per_scenario_maps(dirs, agents)
        for sig in FACTORIAL_MEASURES:
            measures[sig]["per_model"].append(
                {"label": label, **factorial_effects(maps[sig])})
    return {
        "definition": (
            "The four arms form a complete 2x2 (decomposition x context "
            "representation). 'decomposition_effect_given_context_prose' is "
            "the multi-agent-minus-single effect when context is prose (no "
            "structured injection); 'interaction' is the difference between "
            "the two simple effects — a negative interaction means the two "
            "mechanisms are SUBSTITUTES (multi-agent decomposition matters "
            "less once graph context already carries the structure, or vice "
            "versa). Paired per scenario (mean of runs), Wilcoxon two-sided + "
            f"bootstrap CI ({N_BOOT}, seed {BOOT_SEED}). Reported "
            "uncorrected: these are pre-specified structural contrasts of the "
            "design, not a family of arm-vs-A0 comparisons."),
        "cells": {f"agentmode_{k[0]}__contextmode_{k[1]}": v
                  for k, v in factorial_cells().items()},
        "measures": measures,
    }


def print_report(pooled: dict, a0: str, arms: list[str]) -> None:
    print("\n" + "=" * 78)
    print("ABLATION POOLING — contribution = A0 − arm (positive: component helps)")
    print("=" * 78)
    for model in pooled["models"]:
        print(f"\n[{model['label']}]  runs={model['n_runs']}  "
              f"scenarios={model['n_scenarios_union']}")
        for agent in [a0] + arms:
            s = model["agents"].get(agent, {})
            print(f"  {agent:<38} mean_total={s.get('mean_total', float('nan')):7.2f}  "
                  f"nCC={s.get('n_scenarios_complete', 0):3d}  "
                  f"missing={s.get('n_scenarios_any_missing', 0)}")
        rows = (model["comparisons"]["by_score"]["addie_median"]
                ["policies"]["complete_case"])
        for r in rows:
            if r.get("n"):
                lo, hi = r["ci95"]
                print(f"    A0 − {r['baseline']:<34} Δ={r['mean_diff']:+6.2f} "
                      f"CI95=[{lo:+.2f},{hi:+.2f}] n={r['n']} "
                      f"p_holm={r.get('p_holm', float('nan')):.2g}")
            else:
                print(f"    A0 − {r['baseline']:<34} (no shared scenarios)")
    inter = pooled.get("interaction", {})
    if inter.get("per_baseline"):
        print("\n  H2 / capacity interaction (DiD on addie_median; delta = A0 - arm;")
        print("  NEGATIVE DiD = the architecture's advantage shrinks as the model grows):")
        for r in inter["per_baseline"]:
            lo, hi = r["did_ci95"]
            print(f"    vs {r['baseline']:34s} "
                  f"Δ({r['smallest']})={r['delta_smallest_mean']:+6.2f} "
                  f"Δ({r['largest']})={r['delta_largest_mean']:+6.2f} "
                  f"DiD={r['did_mean']:+6.2f} CI95[{lo:+.2f},{hi:+.2f}] "
                  f"p={r['did_wilcoxon_p']:.3g} n={r['n_paired_scenarios']}")
    elif inter.get("note"):
        print(f"\n  H2 / capacity interaction: skipped — {inter['note']}")

    cons = pooled.get("reference_drift", {})
    for row in cons.get("per_model", []):
        if "delta" in row:
            band = row.get("within_2x_ladder_run_sd")
            if band is None:
                flag = "   (no ladder run-to-run SD — one run per cell)"
            elif band:
                flag = "   (within 2x ladder run SD)"
            else:
                flag = "   <-- LARGER THAN 2x LADDER RUN SD, read arm deltas with care"
            print(f"\n  A0 drift [{row['label']}]: ablation−comparison "
                  f"Δ={row['delta']:+.2f}{flag}")
    for entry in pooled.get("mechanism") or []:
        if not entry.get("arms"):
            continue
        print(f"\n  mechanism [{entry['label']}]  (ctx growth last/first, % stages cut "
              f"by the turn ceiling, core C2-C4 coverage, open findings/run)")
        for arm, a in entry["arms"].items():
            print("    " + diagnostics.one_line(arm, a))
    if pooled.get("alignment") is None:
        print(f"\n  (the alignment layer is absent — run "
              f"`{paths.cli()} judge alignment` on each "
              f"run dir, then re-pool.)")


#: Reading direction for the size interaction, stated once so nobody re-derives
#: the sign from the generic definition and flips it.
#:
#: The frame here is delta = reference - arm, i.e. the full architecture's
#: advantage over that ablated cell. The generic interaction says "positive DiD
#: means the advantage GROWS with size", so the capacity hypothesis -- that the
#: architecture compensates for limited model capacity -- predicts a NEGATIVE
#: DiD: the advantage is largest at the smallest model and shrinks as capacity
#: grows. A DiD near zero with per-size deltas near zero means the axis does not
#: matter at any size; a near-zero DiD with uniformly positive deltas means it
#: matters equally at every size -- the mechanism helps, but not BECAUSE the
#: model is small.
INTERACTION_NOTE = (
    "Ablation frame: delta = reference - arm per scenario. The capacity "
    "hypothesis predicts NEGATIVE did_mean: the full architecture's advantage "
    "over this arm is largest at the smallest model and shrinks as capacity "
    "grows. A DiD near zero with per-size deltas near zero means the axis does "
    "not matter at any size; near-zero DiD with uniformly positive deltas means "
    "it matters equally at every size."
)


def pool(run_dirs_by_model: dict[str, list[Path]], *,
         reference: str | None = None,
         arms: list[str] | None = None,
         comparison_pooled: Path | None = None) -> dict:
    """Build the pooled ablation document. Pure: no printing, no writing."""
    from .inference import interaction_tests

    profile = current_config().profile("ablation")
    ref = reference or profile.reference or profile.arms[0].id
    arm_ids = arms if arms is not None else [a.id for a in profile.arms if a.id != ref]
    agents = [ref] + arm_ids

    flag_check = check_arm_flags(run_dirs_by_model, agents)

    models = []
    for label, dirs in run_dirs_by_model.items():
        model = pool_model(label, dirs, agents)
        model["comparisons"] = compare_model(model, ref, arm_ids)
        models.append(model)

    ladder_path = comparison_pooled or (paths.results_root() / "pooled_comparison.json")
    consistency = (a0_consistency(models, ref, ladder_path) if ladder_path.exists()
                   else {"note": f"{ladder_path} not found — drift check skipped"})

    interaction = {"interaction_note": INTERACTION_NOTE,
                   **interaction_tests(models, ref, arm_ids)}
    interaction_by_score = {
        m: {"interaction_note": INTERACTION_NOTE,
            **interaction_tests(models, ref, arm_ids, metric=m)}
        for m in FACTORIAL_LLM_JUDGE_SCORES
    }

    return {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "config": {
            "experiment": profile.name,
            "dataset": profile.dataset,
            "reference": ref,
            "arms": arm_ids,
            "expected_flags": {a: expected_flags().get(a) for a in agents},
            "score_fields": {
                "lead": "addie_median (ADDIE rubric /100, per-scenario, "
                        "from comparison_report.json)",
                "also_reported": list(FACTORIAL_LLM_JUDGE_SCORES),
                "drift_check": "total_score",
            },
            "direction": "mean_diff = reference - arm = contribution of the removed component(s)",
            "design": ("all arms in one run per size, so they share each scenario's "
                       "LLM judge session; the reference arm is re-run here rather than "
                       "taken from the comparison experiment"),
            "primary_failure_policy": "complete_case",
            "holm_family": f"{len(arm_ids)} arm comparisons within each model size",
            "size_order": [m["label"] for m in models],
        },
        "flag_check": flag_check,
        "models": models,
        "interaction": interaction,
        "interaction_by_score": interaction_by_score,
        "reference_drift": consistency,
        "alignment": pool_alignment(models, run_dirs_by_model, agents, ref, arm_ids),
        "token_usage": pool_tokens(run_dirs_by_model, agents),
        "factorial": factorial_layer(run_dirs_by_model, agents),
        "self_validation_activity": self_validation_activity(run_dirs_by_model, agents),
        # What each arm DID: per-stage autonomy (the series the registered
        # directional prediction is read off, and the guards that decide what an
        # arm delta MEANS), relation coverage, the violation ledger, run health.
        "mechanism": mechanism_layer(run_dirs_by_model, agents),
    }


def run(*, patterns: list[str] | None = None, out: Path | None = None,
        reference: str | None = None, comparison_pooled: Path | None = None,
        quiet: bool = False) -> Path:
    """Discover, pool, report and write. Returns the output path."""
    profile = current_config().profile("ablation")
    default = [f"{profile.dataset}_benchmark_*_"
               f"{''.join(sorted({t.rstrip('0123456789') or t for t in profile.tags})) or '*'}*"]
    run_dirs_by_model = discover(patterns or default, profile)

    if not quiet:
        for label, dirs in run_dirs_by_model.items():
            print(f"model {label!r}: {len(dirs)} run(s)")

    pooled = pool(run_dirs_by_model, reference=reference,
                  comparison_pooled=comparison_pooled)

    if not quiet:
        print_report(pooled, pooled["config"]["reference"], pooled["config"]["arms"])

    for model in pooled["models"]:
        model.pop("_totals", None)
        # Raw per-scenario series: consumed by the comparison and DiD layers
        # above, never meant to reach the JSON.
        model.pop("_scores", None)

    out_path = out or (paths.results_root() / "pooled_ablation.json")
    schema.write(out_path, pooled)
    if not quiet:
        print(f"\nPooled ablation JSON written: {out_path}")
    return out_path

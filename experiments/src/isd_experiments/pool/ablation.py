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
from ..alignment.protocol import PANEL_SIGNALS
from ..config import current as current_config
from ..runs import iter_scenario_dirs, load_run
from ..stats import BOOT_SEED, N_BOOT, bootstrap_ci, rank_biserial, wilcoxon_signed_rank
from ..util import mean as _mean
from .comparison import discover
from .judge import compare_model, pool_model
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


#: Judge signals for the factorial readout. The ablation narrative is NOT led
#: by the judge -- coverage, the violation ledger, `gave_up`, context behaviour
#: and the deterministic panel are the readout, and the judge is a cross-check.
FACTORIAL_JUDGE_SIGNALS = ("addie_median", "trajectory_score", "total_score")

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

    This flipped meaning twice. Originally the arms ran in their own session and
    the delta measured judge/session drift; from 2026-07-26 the arms rode inside
    the ladder runs, both numbers came from the SAME executions, and the delta
    had to be ~0 or something was wrong; since 2026-09-10 this experiment is its own
    experiment again, so it is a drift gauge once more.

    Read it as a BOUND, not as a result: it says how much of an arm delta could
    be session effect rather than treatment. Two things make a non-zero value
    expected rather than alarming — the two experiments have separate judge
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
            "A0 (full pipeline) as run inside this experiment vs A0 as run in the the comparison experiment "
            "ladder: two separate executions, separate judge sessions, and "
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

#: Every signal the factorial layer is computed on: the three judge signals plus
#: the whole alignment-panel panel. Deliberately exhaustive — the panel's defence against
#: selective reporting is that every signal is reported for every comparison,
#: and a factorial computed on a hand-picked subset would break exactly that.
#: The paper's main text leads on one signal; the appendix carries all of them.
FACTORIAL_SIGNALS = FACTORIAL_JUDGE_SIGNALS + tuple(
    sig for sig, _family in PANEL_SIGNALS)


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

    One pass over the run dirs picks up both the judge fields (from
    comparison_report.json) and the alignment panel (from alignment_scores.json),
    so the factorial layer never re-derives a number a different way than the
    rest of the pool does.
    """
    acc: dict[str, dict[str, dict[str, list[float]]]] = {
        sig: {a: {} for a in agents} for sig in FACTORIAL_SIGNALS
    }
    panel_signals = [sig for sig, _f in PANEL_SIGNALS]
    for run_dir in run_dirs:
        for sid, payload in load_run(run_dir).items():
            for a in agents:
                r = (payload.get("rankings") or {}).get(a) or {}
                for sig in FACTORIAL_JUDGE_SIGNALS:
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

    Only comparable across arms for runs produced after 2026-08-25. Before
    that the single arm never called log_verifier_result and ran one
    self-validation pass over all checks against multi's one per Designer, so
    its verifier_events were a constant 1.00/scenario against multi's 7.20 —
    an instrumentation and budget gap, not a difference in how much either arm
    found to fix. Numbers from an older run dir will show that artifact here.
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


#: The stage order the agentic control mode instructs, and therefore the
#: STAGE POSITION the directional prediction is about. Taken from the package's
#: step table order; kept here as a literal so a results dir written by an older
#: package version still reads in the same order it was produced in.
#:
#: `rubrics` was a stage of its own until 2026-09-01 and appears in results dirs
#: written before then; it is kept in this tuple so those still read in order.
#: Reading is driven by what a run ACTUALLY recorded (see `stages_of`), never by
#: this tuple's length — a hardcoded seven silently dropped every arm once the
#: package moved to six.
STAGE_ORDER = ("analysis", "outcomes", "assessment", "activities", "content",
               "rubrics", "implementation")


def stages_of(autonomy: dict) -> tuple[str, ...]:
    """The stages a run recorded, in instructed order, plus any this file has
    never heard of (a newer package) appended so they are not lost."""
    known = tuple(s for s in STAGE_ORDER if s in autonomy)
    return known + tuple(s for s in autonomy if s not in STAGE_ORDER)

#: Per-stage counters carried by ``metadata.autonomy`` (core/runner.py).
AUTONOMY_FIELDS = ("context_len", "turns_used", "submits_rejected", "repeated_calls",
                   "history_dropped", "reads", "batched_calls")


def autonomy_layer(run_dirs_by_model: dict[str, list[Path]],
                   agents: list[str]) -> list[dict]:
    """Per-stage autonomy series per arm per size.

    This is where the registered directional prediction is read: context grows
    across stages in the ``single`` arms and does not in ``multi``, and the
    quality gap that goes with it should widen as the model shrinks.

    Three things it must surface, because each turns the SAME arm delta into a
    different claim:
      * ``context_len`` by stage — the mechanism itself. If the single arm's
        series is flat, the axis did not do what it is defined as doing.
      * ``history_dropped`` by stage — whether the arm DEGRADED or hit the 16k
        serving ceiling. High and early means a wall, and a wall is a property
        of the serving configuration, not of decomposition.
      * ``pct_gave_up`` by stage — how often a stage ended without submitting
        its artifact. An arm that mostly gives up is not exercising the
        mechanism the ablation is about, whatever it scores. ``sets_gave_up``
        is the same fact one tier down, at the Developer work sets.
    """
    out = []
    for label, dirs in run_dirs_by_model.items():
        # Collected lazily: a run records whichever stages its package had, and
        # pre-seeding from a literal is exactly how six-stage runs would vanish.
        per_arm: dict[str, dict[str, dict[str, list[float]]]] = {a: {} for a in agents}

        def bucket(agent: str, stage: str) -> dict[str, list[float]]:
            return per_arm[agent].setdefault(
                stage, {f: [] for f in (*AUTONOMY_FIELDS, "gave_up")})
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
                    autonomy = ((doc.get("metadata") or {}).get("autonomy") or {})
                    for stage, stats in autonomy.items():
                        if not isinstance(stats, dict):
                            continue
                        slot = bucket(a, stage)
                        for field in AUTONOMY_FIELDS:
                            value = stats.get(field)
                            if isinstance(value, (int, float)):
                                slot[field].append(float(value))
                        slot["gave_up"].append(1.0 if stats.get("gave_up") else 0.0)
        arms = {}
        for a, by_stage in per_arm.items():
            series = {}
            for stage in stages_of(by_stage):
                values = by_stage[stage]
                if not values["context_len"]:
                    continue
                series[stage] = {
                    "n": len(values["context_len"]),
                    **{f: _mean(values[f]) for f in AUTONOMY_FIELDS},
                    "pct_gave_up": 100.0 * _mean(values["gave_up"]),
                }
            if series:
                ordered = tuple(series)
                first, last = ordered[0], ordered[-1]
                growth = (series[last]["context_len"] - series[first]["context_len"]
                          if first in series and last in series else float("nan"))
                arms[a] = {
                    "by_stage": series,
                    # The one-number summary of the mechanism: how much longer
                    # the last stage's prompt is than the first's. Expected to
                    # be large and positive for the single arms, ~0 for multi.
                    "context_growth_first_to_last": growth,
                    "peak_context_len": max(v["context_len"] for v in series.values()),
                    "pct_stages_gave_up": _mean(
                        [v["pct_gave_up"] for v in series.values()]),
                }
        # An empty layer means the run dirs predate metadata.autonomy; say so
        # rather than reporting zeros.
        out.append({"label": label, "arms": arms,
                    "note": ("" if arms else
                             "no metadata.autonomy in these run dirs — produced "
                             "before the agentic executor")})
    return out


def factorial_layer(run_dirs_by_model: dict[str, list[Path]],
                    agents: list[str]) -> dict:
    missing = [a for a in factorial_cells().values() if a not in agents]
    if missing:
        return {"skipped": f"arms missing from this pool: {missing}"}
    signals: dict[str, dict] = {sig: {"per_model": []} for sig in FACTORIAL_SIGNALS}
    for label, dirs in run_dirs_by_model.items():
        maps = per_scenario_maps(dirs, agents)
        for sig in FACTORIAL_SIGNALS:
            signals[sig]["per_model"].append(
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
        "signals": signals,
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
        rows = (model["comparisons"]["by_signal"]["addie_median"]
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

    cons = pooled.get("a0_consistency", {})
    for row in cons.get("per_model", []):
        if "delta" in row:
            band = row.get("within_2x_ladder_run_sd")
            if band is None:
                flag = "   (no ladder run-to-run SD — one run per cell)"
            elif band:
                flag = "   (within 2x ladder run SD)"
            else:
                flag = "   <-- LARGER THAN 2x LADDER RUN SD, read arm deltas with care"
            print(f"\n  A0 drift [{row['label']}]: this experiment−the comparison experiment "
                  f"Δ={row['delta']:+.2f}{flag}")
    if pooled.get("alignment") is None:
        print("\n  (alignment-panel alignment layer absent — run "
              "scripts/alignmentgraph-isd-bench/06_score_alignment.py on each "
              "run dir, then re-pool.)")


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
    interaction_by_signal = {
        m: {"interaction_note": INTERACTION_NOTE,
            **interaction_tests(models, ref, arm_ids, metric=m)}
        for m in FACTORIAL_JUDGE_SIGNALS
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
                "also_reported": list(FACTORIAL_JUDGE_SIGNALS),
                "drift_check": "total_score",
            },
            "direction": "mean_diff = reference - arm = contribution of the removed component(s)",
            "design": ("all arms in one run per size, so they share each scenario's "
                       "judge session; the reference arm is re-run here rather than "
                       "taken from the comparison experiment"),
            "primary_failure_policy": "complete_case",
            "holm_family": f"{len(arm_ids)} arm comparisons within each model size",
            "size_order": [m["label"] for m in models],
        },
        "flag_check": flag_check,
        "models": models,
        "interaction": interaction,
        "interaction_by_signal": interaction_by_signal,
        "reference_drift": consistency,
        "alignment": pool_alignment(models, run_dirs_by_model, agents, ref, arm_ids),
        "token_usage": pool_tokens(run_dirs_by_model, agents),
        "factorial": factorial_layer(run_dirs_by_model, agents),
        "self_validation_activity": self_validation_activity(run_dirs_by_model, agents),
        # Per-stage autonomy: the series the registered directional prediction is
        # read off, plus the two guards that decide what an arm delta MEANS
        # (history_dropped = a serving wall, gave_up = the loop produced nothing).
        "autonomy": autonomy_layer(run_dirs_by_model, agents),
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

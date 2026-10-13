"""Pooling the ablation experiment: a 2x2 factorial over decomposition and
substrate.

What the ablation concludes from is ``registered``: the two main effects of the
2x2 (and their change with size), tested and Holm-corrected. Everything else
here is descriptive:

* **Arm verification.** A run whose recorded ``metadata.run_config`` disagrees
  with the arm it is filed under is a silently wrong factorial, so pooling
  refuses it rather than reporting it.
* **The factorial read.** Cell means, simple effects and the interaction on
  every reported measure, estimated with an interval and not tested -- the
  tests are the registered ones.
* **A drift gauge.** The reference arm is re-run inside this experiment rather
  than borrowed from the comparison, so the gap between the two says how much
  could be session effect rather than treatment.

The cells are read from ``experiment.toml``, not hard-coded: a different
factorial is a config edit.
"""

from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path

from .. import paths, schema
from ..alignment import presets
from ..alignment.protocol import ALIGNMENT_SIGNALS
from ..config import FAILURE_POLICY
from ..config import current as current_config
from ..runs import iter_scenario_dirs, load_run
from ..stats import BOOT_METHOD, BOOT_SEED, N_BOOT, describe, software
from ..util import mean as _mean
from . import attempts, diagnostics, registered, rosters
from .comparison import discover
from .llm_judge import pool_model
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
#: by the LLM judge -- the process measures (coverage, triad references, the
#: violation ledger, `gave_up`, context behaviour) and the deterministic panel are
#: the readout, and the LLM
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
        # Through the schema check: a file from another pooling version can
        # carry complete-case means under the key names this one reads as
        # failure = 0, and the difference would be read as drift.
        ladder = schema.load(ladder_pooled_path)
    except SystemExit as exc:
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


def per_scenario_maps(run_dirs: list[Path], agents: list[str],
                      scores_filename: str = presets.PRIMARY_ARTIFACT) -> dict:
    """signal -> agent -> {scenario: mean over runs}, under failure = 0.

    Over the runs each agent was attempted in (``attempts``), on every scenario
    the run holds, judged or not. An attempt that left no scorable output counts
    0 on every measure; a panel signal left undefined by an output that exists
    is an instrument limit and stays out.
    """
    acc: dict[str, dict[str, dict[str, list[float]]]] = {
        sig: {a: {} for a in agents} for sig in FACTORIAL_MEASURES
    }
    panel_signals = [sig for sig, _f in ALIGNMENT_SIGNALS]
    for run_dir in run_dirs:
        reports = load_run(run_dir, scores_filename)
        for sid in attempts.scenarios(run_dir):
            payload = reports.get(sid) or {}
            rankings = payload.get("rankings") or {}
            doc = payload.get("alignment")
            scored = (doc.get("agents") or {}) if isinstance(doc, dict) else {}
            for a in agents:
                if not attempts.attempted(run_dir, sid, a):
                    continue
                r = rankings.get(a) or {}
                for sig in FACTORIAL_LLM_JUDGE_SCORES:
                    v = r.get(sig)
                    acc[sig][a].setdefault(sid, []).append(
                        float(v) if isinstance(v, (int, float)) else 0.0)
                failed = not attempts.produced(run_dir, sid, a)
                for sig in panel_signals:
                    v = 0.0 if failed else (scored.get(a) or {}).get(sig)
                    if isinstance(v, (int, float)):
                        acc[sig][a].setdefault(sid, []).append(float(v))
    return {sig: {a: {sid: _mean(vals) for sid, vals in by_sid.items()}
                  for a, by_sid in by_agent.items()}
            for sig, by_agent in acc.items()}


def factorial_effects(maps: dict[str, dict[str, float]]) -> dict:
    """The 2x2 read of one measure at one model size. Descriptive.

    Simple effects are read "the richer setting minus the plainer one"
    (multi - single, graph - prose), so a positive number favours multi-agent
    decomposition / the graph substrate. Each effect is a mean over the
    scenarios all four cells scored, with its BCa interval; none is tested.
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
        "cell_means": {f"agentmode_{k[0]}__contextmode_{k[1]}":
                       _mean([cells[k][s] for s in shared])
                       for k in factorial_cells()},
        "decomposition_effect_given_context_graph": describe(decomposition_ctx_graph),
        "decomposition_effect_given_context_prose": describe(decomposition_ctx_prose),
        "context_effect_given_decomposition_multi": describe(context_decomp_multi),
        "context_effect_given_decomposition_single": describe(context_decomp_single),
        "interaction": describe(interaction),
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


def process_layer(run_dirs_by_model: dict[str, list[Path]],
                    agents: list[str]) -> list[dict]:
    """What each arm DID, per size: the readout the factorial is about.

    The LLM judge and the panel score the deliverable; these read how it came to
    be (see ``diagnostics``). Per arm, five summaries:

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
    ``triad_references``   the triad's references as the deliverable carries
                           them, read off ``addie_output`` on BOTH substrates,
                           with the share the repair net wrote split out
                           (``*_unrepaired``). The graph-vs-prose reading of
                           "are the parts joined"; structural compliance, not
                           quality.
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
                    agents: list[str],
                    scores_filename: str = presets.PRIMARY_ARTIFACT) -> dict:
    missing = [a for a in factorial_cells().values() if a not in agents]
    if missing:
        return {"skipped": f"arms missing from this pool: {missing}"}
    measures: dict[str, dict] = {sig: {"per_model": []} for sig in FACTORIAL_MEASURES}
    for label, dirs in run_dirs_by_model.items():
        maps = per_scenario_maps(dirs, agents, scores_filename)
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
            f"versa). Per scenario, mean of runs under {FAILURE_POLICY}; each "
            f"effect is a mean with its {BOOT_METHOD} bootstrap CI ({N_BOOT}, "
            f"seed {BOOT_SEED}), DESCRIPTIVE: the tests are in `registered`."),
        "cells": {f"agentmode_{k[0]}__contextmode_{k[1]}": v
                  for k, v in factorial_cells().items()},
        "measures": measures,
    }


def registered_layer(run_dirs_by_model: dict[str, list[Path]], agents: list[str]) -> dict:
    """The tests the ablation concludes from (``registered``), or why they were not run."""
    missing = [a for a in factorial_cells().values() if a not in agents]
    if missing:
        return {"skipped": f"arms missing from this pool: {missing}"}
    return registered.analyse(run_dirs_by_model, factorial_cells())


def print_report(pooled: dict, a0: str, arms: list[str]) -> None:
    print("\n" + "=" * 78)
    print("ABLATION POOLING — 2x2 decomposition x substrate")
    print("=" * 78)
    for model in pooled["models"]:
        print(f"\n[{model['label']}]  runs={model['n_runs']}  "
              f"scenarios={model['n_scenarios_union']}")
        for agent in [a0] + arms:
            s = model["agents"].get(agent, {})
            print(f"  {agent:<38} mean_addie={s.get('mean_addie', float('nan')):7.2f}  "
                  f"mean_total={s.get('mean_total', float('nan')):7.2f}  "
                  f"failed={s.get('n_scenarios_any_missing', 0)}")
    if (pooled.get("registered") or {}).get("family"):
        registered.print_family(pooled["registered"])

    cons = pooled.get("reference_drift", {})
    for row in cons.get("per_model", []):
        if "delta" in row:
            band = row.get("within_2x_ladder_run_sd")
            if band is None:
                flag = "   (no ladder run-to-run SD — one run per cell)"
            elif band:
                flag = "   (within 2x ladder run SD)"
            else:
                flag = "   <-- LARGER THAN 2x LADDER RUN SD, read the effects with care"
            print(f"\n  A0 drift [{row['label']}]: ablation−comparison "
                  f"Δ={row['delta']:+.2f}{flag}")
    for entry in pooled.get("process") or []:
        if not entry.get("arms"):
            continue
        print(f"\n  process [{entry['label']}]  (ctx growth last/first, % stages cut "
              f"by the turn ceiling, core C2-C4 coverage, open findings/run)")
        for arm, a in entry["arms"].items():
            print("    " + diagnostics.one_line(arm, a))
    if "skipped" in (pooled.get("factorial") or {}):
        print(f"\n  (no factorial read: {pooled['factorial']['skipped']})")


def pool(run_dirs_by_model: dict[str, list[Path]], *,
         reference: str | None = None,
         arms: list[str] | None = None,
         comparison_pooled: Path | None = None,
         scores_filename: str = presets.PRIMARY_ARTIFACT) -> dict:
    """Build the pooled ablation document. Pure: no printing, no writing.

    ``scores_filename`` is the alignment artifact the factorial reads: the
    primary encoder's unless another declared arm is named, for a tune slice
    scored while the primary's endpoint was off. The document records which one
    it read (``config.panel_artifact``)."""
    attempts.forget()
    profile = current_config().profile("ablation")
    ref = reference or profile.reference or profile.arms[0].id
    arm_ids = arms if arms is not None else [a.id for a in profile.arms if a.id != ref]
    agents = [ref] + arm_ids

    flag_check = check_arm_flags(run_dirs_by_model, agents)

    models = []
    for label, dirs in run_dirs_by_model.items():
        models.append(pool_model(label, dirs, agents))

    ladder_path = comparison_pooled or (paths.results_root() / "pooled_comparison.json")
    consistency = (a0_consistency(models, ref, ladder_path) if ladder_path.exists()
                   else {"note": f"{ladder_path} not found — drift check skipped"})

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
            "direction": ("every effect reads the richer setting minus the plainer one: "
                          "multi - single, graph - prose"),
            "design": ("all arms in one run per size, so they share each scenario's "
                       "LLM judge session; the reference arm is re-run here rather than "
                       "taken from the comparison experiment"),
            # The registered analysis (``registered``, benchmark_guides §5.5)
            # is what the ablation concludes from, and the only Holm family.
            "primary_failure_policy": FAILURE_POLICY,
            "holm_family": ("the registered tests: H-D and H-S at each size, H-C per "
                            "axis"),
            "size_order": [m["label"] for m in models],
            "panel_artifact": scores_filename,
            "stats_software": software(),
        },
        "flag_check": flag_check,
        "models": models,
        "reference_drift": consistency,
        "token_usage": pool_tokens(run_dirs_by_model, agents),
        "factorial": factorial_layer(run_dirs_by_model, agents, scores_filename),
        "registered": registered_layer(run_dirs_by_model, agents),
        "self_validation_activity": self_validation_activity(run_dirs_by_model, agents),
        # What each arm DID: per-stage autonomy (the series the registered
        # directional prediction is read off, and the guards that decide what an
        # arm delta MEANS), relation coverage, the violation ledger, run health.
        "process": process_layer(run_dirs_by_model, agents),
    }


def run(*, patterns: list[str] | None = None, out: Path | None = None,
        reference: str | None = None, comparison_pooled: Path | None = None,
        encoder: str | None = None, quiet: bool = False) -> Path:
    """Discover, pool, report and write. Returns the output path."""
    profile = current_config().profile("ablation")
    default = [f"{profile.dataset}_benchmark_*_"
               f"{''.join(sorted({t.rstrip('0123456789') or t for t in profile.tags})) or '*'}*"]
    run_dirs_by_model = discover(patterns or default, profile)

    if not quiet:
        for label, dirs in run_dirs_by_model.items():
            print(f"model {label!r}: {len(dirs)} run(s)")

    artifact = (presets.current().encoder(encoder).artifact if encoder
                else presets.PRIMARY_ARTIFACT)
    all_dirs = [d for dirs in run_dirs_by_model.values() for d in dirs]
    rosters.require_declared_roster(
        all_dirs, [a.id for a in profile.arms] + [profile.reference or ""], quiet=quiet)
    rosters.require_judged(all_dirs, [a.id for a in profile.arms] + [profile.reference or ""],
                           artifact)
    if not quiet:
        rosters.warn_missing_artifact(all_dirs, artifact, flag="--encoder <arm>")
    pooled = pool(run_dirs_by_model, reference=reference,
                  comparison_pooled=comparison_pooled, scores_filename=artifact)

    if not quiet:
        print_report(pooled, pooled["config"]["reference"], pooled["config"]["arms"])

    for model in pooled["models"]:
        # Raw per-scenario series, never meant to reach the JSON.
        model.pop("_scores", None)

    out_path = out or (paths.results_root() / "pooled_ablation.json")
    schema.write(out_path, pooled)
    if not quiet:
        print(f"\nPooled ablation JSON written: {out_path}")
    return out_path

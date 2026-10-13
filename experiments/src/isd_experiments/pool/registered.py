"""The ablation's REGISTERED analysis: three hypotheses, six tests, one rule.

Written to ``docs/guides/benchmark_guides.md`` §5.5 before Gate 2, and this
module computes exactly that and nothing chosen afterwards:

* **H-D**  the multi-agent bundle beats the single-agent bundle on
  ``addie_median`` (main effect of decomposition, at each size);
* **H-S**  the graph substrate bundle beats the prose bundle on
  ``objectives_closed_triad`` (main effect of substrate, at each size), with
  the model-written form (``objectives_closed_triad`` over references the
  repair net did not write) reported beside it and never in the family;
* **H-C**  each axis's main effect is larger at the smallest size than at the
  largest (DiD = effect(smallest) - effect(largest), per scenario).

The unit is the scenario: a cell's value on a scenario is the mean over that
size's runs, and a run that left no scorable output counts 0 (``failure =
0``, the primary layer). Each test is a paired Wilcoxon signed-rank
(two-sided, exact null), a BCa bootstrap CI and the rank-biserial r; Holm runs
over exactly the registered tests, and the verdict reads the adjusted p
together with the sign the hypothesis predicts.

Also here, outside the family, per size: the same tests over complete cases
(the sensitivity, with its own Holm so its verdicts read on the same rule);
the decomposition x substrate interaction on each axis's measure, the guide's
pre-specified uncorrected contrast; and two descriptive readings -- H-S's
measure over the references the model wrote itself, and the multi-minus-single
gap by ADDIE phase (H-D's mechanism), each a mean with its interval.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Callable, Optional

from ..config import FAILURE_POLICY, SENSITIVITY_POLICY
from ..runs import load_run
from ..stats import BOOT_METHOD, BOOT_SEED, N_BOOT, describe, holm_correct, paired
from ..util import mean as _mean
from . import attempts, diagnostics

#: The family the guide registers, in the order it lists them.
ALPHA = 0.05
#: H-D and H-S at each of the two sizes, H-C per axis.
REGISTERED_TESTS = 6
#: ADDIE phases in the order a design walks them: the x of the phase slope.
PHASE_ORDER = ("analysis", "design", "development", "implementation", "evaluation")
#: The measure each axis is tested on. The triad's model-written twin is read
#: by ``Reader.triad(unrepaired=True)`` and never enters the family.
PRIMARY_MEASURE = {"decomposition": "addie_median", "substrate": "objectives_closed_triad"}
HYPOTHESIS = {"decomposition": "H-D", "substrate": "H-S"}

Cells = dict[tuple[str, str], str]


# ── per-scenario cell values ────────────────────────────────────────────────

class Reader:
    """Everything the analysis reads off the run dirs, each file once.

    One per analysis rather than a module cache, so a re-pool reads the run
    dirs as they are now."""

    def __init__(self) -> None:
        self._reports: dict[str, dict] = {}

    def scenarios(self, run_dirs: list[Path]) -> list[str]:
        """Every scenario any agent was attempted in, judged or not."""
        return sorted({sid for d in run_dirs for sid in self._dirs(d)})

    def _dirs(self, run_dir: Path) -> dict[str, Path]:
        return attempts.scenarios(run_dir)

    def attempted(self, run_dir: Path, scenario: str, agent: str) -> bool:
        return attempts.attempted(run_dir, scenario, agent)

    def _ranking(self, run_dir: Path, scenario: str, agent: str) -> dict:
        key = str(run_dir)
        if key not in self._reports:
            self._reports[key] = load_run(run_dir)
        return ((self._reports[key].get(scenario) or {}).get("rankings") or {}).get(agent) or {}

    def llm_judge(self, score: str) -> Callable[[Path, str, str], Optional[float]]:
        def read(run_dir: Path, scenario: str, agent: str) -> Optional[float]:
            value = self._ranking(run_dir, scenario, agent).get(score)
            return float(value) if isinstance(value, (int, float)) else None
        return read

    def phase_scores(self, run_dir: Path, scenario: str, agent: str) -> dict:
        return self._ranking(run_dir, scenario, agent).get("phase_scores") or {}

    def triad(self, *, unrepaired: bool = False) -> Callable[[Path, str, str], Optional[float]]:
        """``objectives_closed_triad`` of one agent's deliverable on one scenario.

        ``unrepaired`` reads the triad closed by references the model wrote
        itself (``diagnostics._model_wrote`` per field), the guide's mandatory
        secondary. None when the run left no deliverable or one naming no
        objective, which the failure = 0 layer scores as 0."""
        def read(run_dir: Path, scenario: str, agent: str) -> Optional[float]:
            scen_dir = self._dirs(run_dir).get(scenario)
            output = diagnostics._output_of(scen_dir, agent) if scen_dir else None
            if not isinstance(output, dict):
                return None
            if unrepaired:
                output = _without_repaired_references(output)
            triad = diagnostics.read_triad_references(output)
            return None if triad is None else triad.get("objectives_closed_triad")
        return read


def _without_repaired_references(output: dict) -> dict:
    """The deliverable with every reference the repair net wrote taken out, so
    the triad is closed only by what the model wrote. Field by field, through
    the same ``_model_wrote`` the process measures read."""
    out = json.loads(json.dumps(output))
    for act in (out.get("design") or {}).get("learning_activities") or []:
        if isinstance(act, dict):
            for field in ("aligned_objectives", "prepares_for_assessment"):
                if not diagnostics._model_wrote(act, field):
                    act[field] = []
    for task in (out.get("development") or {}).get("assessment_tools") or []:
        for item in (task.get("items") or [task]) if isinstance(task, dict) else []:
            if isinstance(item, dict) and not diagnostics._model_wrote(item, "aligned_objective"):
                item["aligned_objective"] = ""
    return out


def cell_means(reader: Reader, run_dirs: list[Path], cells: Cells,
               read: Callable[[Path, str, str], Optional[float]], *,
               policy: str = FAILURE_POLICY) -> dict[tuple[str, str], dict[str, float]]:
    """cell -> scenario -> mean over this size's runs.

    Over the runs the cell's agent was attempted in (``attempts``). failure = 0:
    an attempt with nothing scorable counts 0, so the worst outputs stay in the
    denominator (the registered primary layer). complete-case: only the
    scenarios the cell scored in every attempted run, the same definition the
    LLM judge pool uses."""
    out: dict[tuple[str, str], dict[str, float]] = {}
    for cell, agent in cells.items():
        per: dict[str, float] = {}
        for sid in reader.scenarios(run_dirs):
            vals = [read(run_dir, sid, agent) for run_dir in run_dirs
                    if reader.attempted(run_dir, sid, agent)]
            if not vals:
                continue
            if policy == FAILURE_POLICY:
                per[sid] = _mean([0.0 if v is None else v for v in vals])
            elif all(v is not None for v in vals):
                per[sid] = _mean(vals)  # type: ignore[arg-type]
        out[cell] = per
    return out


def main_effects(values: dict[tuple[str, str], dict[str, float]]) -> dict[str, dict[str, float]]:
    """effect -> scenario -> value, over the scenarios all four cells scored.

    decomposition = mean of (multi - single) under graph and under prose;
    substrate = mean of (graph - prose) under multi and under single. Both read
    "the richer setting minus the plainer one", so the registered prediction is
    positive for both. interaction = the decomposition effect under graph minus
    under prose."""
    # Sorted: the bootstrap resamples by position, so a set's hash order would
    # move the CI from one run of the pool to the next.
    shared = sorted(set.intersection(*(set(v) for v in values.values()))) if values else []
    mg, sg = values[("multi", "graph")], values[("single", "graph")]
    mp, sp = values[("multi", "prose")], values[("single", "prose")]
    return {
        "decomposition": {s: ((mg[s] - sg[s]) + (mp[s] - sp[s])) / 2 for s in shared},
        "substrate": {s: ((mg[s] - mp[s]) + (sg[s] - sp[s])) / 2 for s in shared},
        # (multi - single | graph) - (multi - single | prose): positive means
        # decomposition gains more on the graph substrate.
        "interaction": {s: (mg[s] - sg[s]) - (mp[s] - sp[s]) for s in shared},
    }


def verdict(row: dict) -> str:
    """The guide's rule: the adjusted p AND the predicted sign (positive)."""
    p, d = row.get("p_holm"), row.get("mean_diff")
    if not isinstance(p, float) or not isinstance(d, float) or p != p:
        return "not tested"
    if p < ALPHA and d > 0:
        return "supported"
    if p < ALPHA and d < 0:
        return "contrary"
    return "not detected"


# ── the phase slope (H-D's mechanism, outside the family) ───────────────────

def phase_slope(reader: Reader, run_dirs: list[Path], cells: Cells) -> dict:
    """Slope of the multi-minus-single gap over the ADDIE phases, per scenario.

    The gap at a phase is the decomposition main effect on that phase's score
    (mean over runs, complete-case: a cell counts only where the phase was
    scored in every run its agent was attempted in; a phase the LLM judge did
    not score is not a phase the agent failed). The slope is the OLS slope of the gap on the
    phase index, so a positive slope is the registered mechanism — the single
    arm falls further behind the later the phase."""
    slopes: list[float] = []
    by_phase: dict[str, list[float]] = {p: [] for p in PHASE_ORDER}
    for sid in reader.scenarios(run_dirs):
        gaps = []
        for phase in PHASE_ORDER:
            cell = {}
            for key, agent in cells.items():
                vals = [reader.phase_scores(d, sid, agent).get(phase) for d in run_dirs
                        if reader.attempted(d, sid, agent)]
                # Complete-case: the phase scored in every attempted run.
                if vals and all(isinstance(v, (int, float)) for v in vals):
                    cell[key] = _mean([float(v) for v in vals])
            if len(cell) < 4:
                gaps.append(None)
                continue
            gap = ((cell[("multi", "graph")] - cell[("single", "graph")])
                   + (cell[("multi", "prose")] - cell[("single", "prose")])) / 2
            gaps.append(gap)
            by_phase[phase].append(gap)
        points = [(i, g) for i, g in enumerate(gaps) if g is not None]
        if len(points) >= 3:
            xbar = _mean([x for x, _ in points])
            denom = sum((x - xbar) ** 2 for x, _ in points)
            slopes.append(sum((x - xbar) * g for x, g in points) / denom)
    return {"gap_by_phase": {p: (_mean(v) if v else None) for p, v in by_phase.items()},
            "slope": describe(slopes)}


# ── the whole registered analysis ───────────────────────────────────────────

def analyse(run_dirs_by_model: dict[str, list[Path]], cells: Cells) -> dict:
    """Every registered test, the Holm family over exactly them, the verdicts,
    and the secondary readings the guide names. ``run_dirs_by_model`` is in
    size order, smallest first (``runs.group_by_glob``)."""
    sizes = list(run_dirs_by_model)
    reader = Reader()
    readers = {"decomposition": reader.llm_judge(PRIMARY_MEASURE["decomposition"]),
               "substrate": reader.triad()}

    def effect(dirs, axis, read, policy=FAILURE_POLICY) -> dict[str, float]:
        return main_effects(cell_means(reader, dirs, cells, read, policy=policy))[axis]

    effects: dict[str, dict[str, dict[str, float]]] = {}   # size -> axis -> scenario -> effect
    secondary: dict[str, dict] = {}
    # size -> measure -> arm -> mean under failure = 0: the cell values the
    # registered effects are differences of, for a table to print beside them.
    arm_means: dict[str, dict[str, dict[str, float]]] = {}
    for size, dirs in run_dirs_by_model.items():
        effects[size] = {axis: effect(dirs, axis, read) for axis, read in readers.items()}
        arm_means[size] = {
            PRIMARY_MEASURE[axis]: {cells[cell]: _mean(list(vals.values()))
                                    for cell, vals in cell_means(reader, dirs, cells, read).items()
                                    if vals}
            for axis, read in readers.items()}
        sensitivity = [{"test": f"{HYPOTHESIS[axis]} @ {size} complete-case", "axis": axis,
                        **paired(list(effect(dirs, axis, read, SENSITIVITY_POLICY).values()))}
                       for axis, read in readers.items()]
        tested = [r for r in sensitivity if isinstance(r.get("p_raw"), float)]
        for row, adjusted in zip(tested, holm_correct([r["p_raw"] for r in tested])):
            row["p_holm"] = adjusted
            row["holm_family_size"] = len(tested)
        for row in sensitivity:
            row["verdict"] = verdict(row)
        secondary[size] = {
            # The same tests over complete cases, with their own Holm.
            "complete_case": sensitivity,
            # The guide's pre-specified decomposition x substrate contrast,
            # on each axis's measure; reported uncorrected.
            "interaction": {PRIMARY_MEASURE[axis]: paired(list(
                effect(dirs, "interaction", read).values()))
                for axis, read in readers.items()},
            # H-S's mandatory twin: the triad as the model wrote it. Descriptive.
            "substrate|model_written": describe(list(
                effect(dirs, "substrate", reader.triad(unrepaired=True)).values())),
            "phase_slope": phase_slope(reader, dirs, cells),
        }

    family: list[dict] = []
    for axis in ("decomposition", "substrate"):
        for size in sizes:
            family.append({"test": f"{HYPOTHESIS[axis]} @ {size}", "axis": axis, "size": size,
                           "measure": PRIMARY_MEASURE[axis],
                           **paired(list(effects[size][axis].values()))})
    for axis in ("decomposition", "substrate"):
        row = {"test": f"H-C {axis}", "axis": axis, "measure": PRIMARY_MEASURE[axis]}
        if len(sizes) >= 2:
            small, large = effects[sizes[0]][axis], effects[sizes[-1]][axis]
            shared = sorted(set(small) & set(large))
            row.update(smallest=sizes[0], largest=sizes[-1],
                       **paired([small[s] - large[s] for s in shared]))
        else:
            row.update(n=0, note="needs >= 2 model sizes")
        family.append(row)

    tested = [r for r in family if isinstance(r.get("p_raw"), float)]
    for row, adjusted in zip(tested, holm_correct([r["p_raw"] for r in tested])):
        row["p_holm"] = adjusted
        row["holm_family_size"] = len(tested)
    for row in family:
        row["verdict"] = verdict(row)

    return {
        "definition": (
            "Registered in docs/guides/benchmark_guides.md §5.5. Main effect of "
            "decomposition = mean of (multi - single) under graph and under prose; "
            "of substrate = mean of (graph - prose) under multi and under single. "
            "H-C = per-scenario effect at the smallest size minus at the largest. "
            "Scenario is the unit (mean over runs); failure = 0. Paired Wilcoxon "
            f"two-sided (exact null), {BOOT_METHOD} bootstrap CI ({N_BOOT}, seed "
            f"{BOOT_SEED}), rank-biserial r; "
            f"Holm over the tests below that could be run ({len(tested)} of the "
            f"{REGISTERED_TESTS} registered) at alpha {ALPHA}. Verdict: "
            "supported (p_holm < alpha, positive), contrary (p_holm < alpha, "
            "negative), else not detected."),
        "primary_measure": dict(PRIMARY_MEASURE),
        "failure_policy": FAILURE_POLICY,
        "sizes": sizes,
        "family": family,
        "complete": len(tested) == REGISTERED_TESTS,
        "secondary": secondary,
        "arm_means": arm_means,
    }


def print_family(registered: dict) -> None:
    family = registered.get("family") or []
    tested = sum(1 for r in family if "p_holm" in r)
    print(f"\n  REGISTERED TESTS (benchmark_guides §5.5; Holm over {tested}; failure = 0)")
    if tested < REGISTERED_TESTS:
        print(f"    INCOMPLETE: {tested} of the {REGISTERED_TESTS} registered tests could be "
              "run here; the verdicts below are not the registered analysis.")
    for r in family:
        if not r.get("n"):
            print(f"    {r['test']:<28} {r.get('note', 'no shared scenarios')}")
            continue
        lo, hi = r["ci95"]
        print(f"    {r['test']:<28} {r['measure']:<24} d={r['mean_diff']:+.3f} "
              f"CI95=[{lo:+.3f},{hi:+.3f}] r={r['rank_biserial_r']:+.2f} n={r['n']} "
              f"p_holm={r.get('p_holm', float('nan')):.3g}  {r['verdict']}")
    for size, sec in (registered.get("secondary") or {}).items():
        for r in sec.get("complete_case") or []:
            if r.get("n"):
                print(f"    [{size}] {r['test']:<36} d={r['mean_diff']:+.3f} "
                      f"p_holm={r.get('p_holm', float('nan')):.3g}  {r['verdict']} (sensitivity)")
        for measure, r in (sec.get("interaction") or {}).items():
            if r.get("n"):
                print(f"    [{size}] interaction on {measure:<22} d={r['mean_diff']:+.3f} "
                      f"p_raw={r['p_raw']:.3g} (pre-specified, uncorrected)")
        mw = sec.get("substrate|model_written") or {}
        slope = (sec.get("phase_slope") or {}).get("slope") or {}
        if mw.get("n"):
            lo, hi = mw["ci95"]
            print(f"    [{size}] H-S model-written triad d={mw['mean_diff']:+.3f} "
                  f"CI95=[{lo:+.3f},{hi:+.3f}] (descriptive)")
        if slope.get("n"):
            lo, hi = slope["ci95"]
            print(f"    [{size}] H-D phase slope d={slope['mean_diff']:+.3f}/phase "
                  f"CI95=[{lo:+.3f},{hi:+.3f}] (descriptive)")

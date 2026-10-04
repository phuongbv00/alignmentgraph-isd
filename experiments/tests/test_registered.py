"""The ablation's registered analysis (docs/guides/benchmark_guides.md §5.5).

What is pinned here is the registration itself: which six tests form the
Holm family, that a run with nothing scorable counts 0, the verdict rule, and
the two secondary readings the guide names — so a later edit cannot change
what the ablation concludes from without a test saying so.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from isd_experiments.pool import registered

CELLS = {("multi", "graph"): "mg", ("single", "graph"): "sg",
         ("multi", "prose"): "mp", ("single", "prose"): "sp"}


def _output(closed: bool, *, repaired_prep: bool = False) -> dict:
    """One objective; its triad closes when the activity names the task."""
    act = {"id": "TLA-1", "aligned_objectives": ["ILO-01"],
           "prepares_for_assessment": ["AT-01"] if closed else []}
    if repaired_prep:
        act.update(repaired=True, repaired_fields=["prepares_for_assessment"])
    return {"design": {"learning_objectives": [{"id": "ILO-01", "level": "apply"}],
                       "learning_activities": [act]},
            "development": {"assessment_tools": [
                {"id": "AT-01", "items": [{"aligned_objective": "ILO-01",
                                           "required_cognitive_process": "apply"}]}]}}


def _run(root: Path, name: str, scenarios: dict) -> Path:
    """scenarios: sid -> agent -> (addie | None, output | None, phase_scores | None)."""
    run = root / name
    for sid, agents in scenarios.items():
        scen = run / "test_30" / sid
        scen.mkdir(parents=True)
        rankings = []
        for agent, (addie, output, phases) in agents.items():
            if addie is not None:
                rankings.append({"agent_id": agent, "addie_median": addie,
                                 **({"phase_scores": phases} if phases else {})})
            if output is not None:
                (scen / f"{agent}_output.json").write_text(
                    json.dumps({"addie_output": output}), encoding="utf-8")
        (scen / "comparison_report.json").write_text(
            json.dumps({"comparison": {"rankings": rankings}}), encoding="utf-8")
    return run


def test_main_effects_average_the_two_simple_effects():
    values = {("multi", "graph"): {"S": 10.0}, ("single", "graph"): {"S": 4.0},
              ("multi", "prose"): {"S": 7.0}, ("single", "prose"): {"S": 5.0}}
    effects = registered.main_effects(values)
    assert effects["decomposition"]["S"] == pytest.approx(((10 - 4) + (7 - 5)) / 2)
    assert effects["substrate"]["S"] == pytest.approx(((10 - 7) + (4 - 5)) / 2)


def test_a_run_with_nothing_scorable_counts_zero_and_complete_case_leaves_it_out(tmp_path):
    run = _run(tmp_path, "r", {"S1": {"mg": (80.0, None, None), "sg": (None, None, None),
                                     "mp": (70.0, None, None), "sp": (60.0, None, None)}})
    reader = registered.Reader()
    read = reader.llm_judge("addie_median")
    zero = registered.cell_means(reader, [run], CELLS, read, policy="zero")
    assert zero[("single", "graph")] == {"S1": 0.0}
    cc = registered.cell_means(reader, [run], CELLS, read, policy="complete_case")
    assert cc[("single", "graph")] == {}


@pytest.mark.parametrize("p, d, expected", [
    (0.01, 2.0, "supported"), (0.01, -2.0, "contrary"),
    (0.20, 2.0, "not detected"), (0.20, -2.0, "not detected")])
def test_the_verdict_reads_the_adjusted_p_and_the_predicted_sign(p, d, expected):
    assert registered.verdict({"p_holm": p, "mean_diff": d}) == expected


def test_the_family_is_exactly_the_six_registered_tests_and_holm_runs_over_them(tmp_path):
    def size(name, gap):
        return _run(tmp_path, name, {
            f"S{i}": {"mg": (70.0 + gap + i, _output(True), None),
                      "sg": (70.0 + i, _output(False), None),
                      "mp": (70.0 + gap + i, _output(False), None),
                      "sp": (70.0 + i, _output(False), None)}
            for i in range(8)})
    result = registered.analyse({"0.8b": [size("small", 6.0)], "4b": [size("large", 2.0)]},
                                CELLS)
    family = result["family"]
    assert [r["test"] for r in family] == [
        "H-D @ 0.8b", "H-D @ 4b", "H-S @ 0.8b", "H-S @ 4b",
        "H-C decomposition", "H-C substrate"]
    assert [r["measure"] for r in family] == ["addie_median"] * 2 + \
        ["objectives_closed_triad"] * 2 + ["addie_median", "objectives_closed_triad"]
    assert all("p_holm" in r for r in family)
    assert family[0]["mean_diff"] == pytest.approx(6.0)
    # The triad closes only under multi+graph: substrate effect (1 - 0 + 0 - 0)/2.
    assert family[2]["mean_diff"] == pytest.approx(0.5)
    # H-C: effect at the smallest size minus at the largest.
    assert family[4]["mean_diff"] == pytest.approx(6.0 - 2.0)
    assert result["failure_policy"] == "zero" and result["complete"]


def test_the_model_written_triad_drops_what_the_net_wrote(tmp_path):
    """H-S's mandatory twin: a reference the repair net wrote does not close a
    triad the model left open."""
    run = _run(tmp_path, "r", {"S1": {
        "mg": (70.0, _output(True, repaired_prep=True), None)}})
    reader = registered.Reader()
    assert reader.triad()(run, "S1", "mg") == 1.0
    assert reader.triad(unrepaired=True)(run, "S1", "mg") == 0.0


def test_the_phase_slope_is_positive_when_single_falls_further_behind_later(tmp_path):
    later = {p: 70.0 for p in registered.PHASE_ORDER}
    behind = {p: 70.0 - 2.0 * i for i, p in enumerate(registered.PHASE_ORDER)}
    run = _run(tmp_path, "r", {f"S{i}": {
        "mg": (70.0, None, later), "mp": (70.0, None, later),
        "sg": (70.0, None, behind), "sp": (70.0, None, behind)} for i in range(4)})
    slope = registered.phase_slope(registered.Reader(), [run], CELLS)
    assert slope["slope"]["mean_diff"] == pytest.approx(2.0)
    assert slope["gap_by_phase"]["evaluation"] == pytest.approx(8.0)


def test_one_size_is_not_the_registered_analysis_and_says_so(tmp_path):
    run = _run(tmp_path, "r", {f"S{i}": {a: (70.0 + i, _output(a == "mg"), None)
                                        for a in CELLS.values()} for i in range(6)})
    result = registered.analyse({"2b": [run]}, CELLS)
    assert not result["complete"]
    assert [r["test"] for r in result["family"] if "p_holm" in r] == ["H-D @ 2b", "H-S @ 2b"]
    assert all(r["verdict"] == "not tested" for r in result["family"] if "p_holm" not in r)


def test_the_analysis_does_not_depend_on_hash_order():
    """The bootstrap resamples by position, so scenario order must be fixed."""
    import subprocess
    import sys
    code = ("from isd_experiments.pool import registered as r;"
            "v={k:{f'S{i}':(float((i*7)%11) if k==('multi','graph') else 0.0) for i in range(30)}"
            " for k in [('multi','graph'),('single','graph'),('multi','prose'),('single','prose')]};"
            "print(r.paired(list(r.main_effects(v)['decomposition'].values()))['ci95'])")
    outs = {subprocess.run([sys.executable, "-c", code], capture_output=True, text=True,
                           env={"PYTHONHASHSEED": seed, "PATH": ""}).stdout
            for seed in ("1", "2", "3")}
    assert len(outs) == 1, outs

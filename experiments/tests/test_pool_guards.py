"""What a pool checks before it reads anything.

Two guards, each answering a way a pool could be wrong without failing:

* **Size order.** Every size contrast (H-C, the DiD, the trend) reads the first
  size as the smallest, so the order the patterns were typed in must not
  decide a sign.
* **Finished judging.** Under failure = 0 a scenario a system left no output for
  scores 0. An output nobody judged yet would be read the same way, so a pool
  refuses until judging is finished -- and still pools a real failure.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from isd_experiments.alignment.protocol import ALIGNMENT_SIGNALS
from isd_experiments.config import current as current_config
from isd_experiments.pool import comparison, rosters


def test_sizes_come_out_smallest_first_whatever_the_pattern_order(mini_run):
    profile = current_config().profile("comparison")
    small = str(mini_run / "test_90_benchmark_qwen3.5-0.8b_*")
    large = str(mini_run / "test_90_benchmark_qwen3.5-4b_*")
    assert list(comparison.discover([large, small], profile)) == ["qwen3.5-0.8b", "qwen3.5-4b"]


def test_a_run_dir_named_by_two_patterns_is_pooled_once(mini_run):
    profile = current_config().profile("comparison")
    glob = str(mini_run / "test_90_benchmark_qwen3.5-0.8b_*")
    assert [len(d) for d in comparison.discover([glob, glob], profile).values()] == [1]


ROW = {"total_score": 70.0, "addie_median": 72.0, "trajectory_score": 65.0,
       "phase_scores": {"analysis": 70.0},
       "judges": [{"model": "m", "addie_score": 72.0, "trajectory_score": 65.0}]}


def _scenario(run_dir: Path, sid: str, outputs: list[str], judged: list[str] | None) -> Path:
    scen = run_dir / "test_30" / sid
    scen.mkdir(parents=True)
    for agent in outputs:
        (scen / f"{agent}_output.json").write_text("{}", encoding="utf-8")
        (scen / f"{agent}_log.txt").write_text("", encoding="utf-8")
    if judged is not None:
        rankings = [{"agent_id": a, **ROW} for a in judged]
        (scen / "comparison_report.json").write_text(
            json.dumps({"comparison": {"rankings": rankings}}), encoding="utf-8")
    return scen


def test_an_unjudged_output_is_refused(tmp_path):
    run = tmp_path / "test_30_benchmark_m_c1_20260101_000000"
    _scenario(run, "S1", ["a", "b"], judged=["a", "b"])
    _scenario(run, "S2", ["a", "b"], judged=None)            # not judged at all
    _scenario(run, "S3", ["a", "b"], judged=["a"])           # report lacks b
    gaps = rosters.unjudged([run], ["a", "b"])
    assert [g.split(":")[0] for g in gaps] == [f"{run.name}/S2", f"{run.name}/S3"]
    with pytest.raises(SystemExit, match="not judged yet"):
        rosters.require_judged([run], ["a", "b"])


def test_a_system_that_left_no_output_is_a_failure_not_a_gap(tmp_path):
    run = tmp_path / "test_30_benchmark_m_c1_20260101_000000"
    scen = _scenario(run, "S1", ["a"], judged=["a"])
    (scen / "b_log.txt").write_text("crashed", encoding="utf-8")     # b ran and failed
    assert rosters.unjudged([run], ["a", "b"]) == []


def test_a_scenario_missing_the_alignment_artifact_the_others_carry_is_refused(tmp_path):
    run = tmp_path / "test_30_benchmark_m_c1_20260101_000000"
    first = _scenario(run, "S1", ["a"], judged=["a"])
    _scenario(run, "S2", ["a"], judged=["a"])
    (first / "alignment_scores.json").write_text("{}", encoding="utf-8")
    assert rosters.unjudged([run], ["a"], "alignment_scores.json") == [
        f"{run.name}/S2: no alignment_scores.json"]
    # A run dir no scenario of which was scored for alignment is not a gap here:
    # the pool reports the alignment layer as absent.
    (first / "alignment_scores.json").unlink()
    assert rosters.unjudged([run], ["a"], "alignment_scores.json") == []


# ── one definition of a failure, read the same way by every layer ────────────

def _run_tree(root: Path, name: str, cells: dict) -> Path:
    """cells: sid -> agent -> score (float), None (attempted, no output) or absent
    (not attempted). Writes what the runner and the judges write."""
    run = root / name
    for sid, agents in cells.items():
        scen = run / "test_30" / sid
        scen.mkdir(parents=True)
        rankings, scores, missing = [], {}, {}
        for agent, score in agents.items():
            (scen / f"{agent}_log.txt").write_text("", encoding="utf-8")
            if score is None:
                missing[agent] = "attempted, no output"
                continue
            (scen / f"{agent}_output.json").write_text("{}", encoding="utf-8")
            rankings.append({"agent_id": agent, **{**ROW, "total_score": score,
                                                   "addie_median": score}})
            scores[agent] = {signal: score / 100 for signal, _family in ALIGNMENT_SIGNALS}
        if rankings:
            (scen / "comparison_report.json").write_text(
                json.dumps({"comparison": {"rankings": rankings}}), encoding="utf-8")
        (scen / "alignment_scores.json").write_text(
            json.dumps({"agents": scores, "missing_outputs": missing}), encoding="utf-8")
    return run


def test_a_targeted_repeat_of_some_agents_costs_the_others_nothing(tmp_path):
    from isd_experiments.pool import attempts, llm_judge
    attempts.forget()
    r1 = _run_tree(tmp_path, "r1", {"S1": {"a": 80.0, "b": 60.0}, "S2": {"a": 70.0, "b": 50.0}})
    r2 = _run_tree(tmp_path, "r2", {"S1": {"a": 90.0}, "S2": {"a": 72.0}})   # b not run
    model = llm_judge.pool_model("m", [r1, r2], ["a", "b"])
    assert model["agents"]["b"]["mean_total"] == 55.0
    assert model["agents"]["b"]["n_scenarios_any_missing"] == 0
    assert model["agents"]["a"]["mean_total"] == (85.0 + 71.0) / 2


def test_a_scenario_every_agent_failed_still_counts_zero(tmp_path):
    from isd_experiments.pool import attempts, llm_judge
    attempts.forget()
    run = _run_tree(tmp_path, "r1", {"S1": {"a": 80.0, "b": 60.0}, "S2": {"a": None, "b": None}})
    model = llm_judge.pool_model("m", [run], ["a", "b"])
    assert model["n_scenarios_union"] == 2
    assert model["agents"]["a"]["mean_total"] == 40.0
    assert model["agents"]["a"]["n_scenarios_any_missing"] == 1


def test_every_layer_reads_the_same_failure(tmp_path):
    """The LLM judge pool, the registered analysis and the factorial agree on
    a tree with a failure and a scenario one run did not hold."""
    from isd_experiments.pool import ablation, attempts, llm_judge, registered
    attempts.forget()
    r1 = _run_tree(tmp_path, "r1", {"S1": {"a": 80.0}, "S2": {"a": None}})
    r2 = _run_tree(tmp_path, "r2", {"S2": {"a": 60.0}})                       # no S1
    judge = llm_judge.scenario_mean_map(
        llm_judge.pool_model("m", [r1, r2], ["a"])["_scores"]["addie_median"], "a", "zero")
    reader = registered.Reader()
    reg = registered.cell_means(reader, [r1, r2], {("multi", "graph"): "a"},
                                reader.llm_judge("addie_median"))[("multi", "graph")]
    fact = ablation.per_scenario_maps([r1, r2], ["a"])["addie_median"]["a"]
    assert judge == reg == fact == {"S1": 80.0, "S2": 30.0}


def test_a_panel_with_no_complete_case_is_still_pooled(tmp_path):
    from isd_experiments.pool import attempts, llm_judge, panel
    attempts.forget()
    r1 = _run_tree(tmp_path, "r1", {"S1": {"a": 40.0, "b": 40.0}})
    r2 = _run_tree(tmp_path, "r2", {"S1": {"a": None, "b": None}})
    models = [llm_judge.pool_model("m", [r1, r2], ["a", "b"])]
    pooled = panel.pool_alignment(models, {"m": [r1, r2]}, ["a", "b"], "a", ["b"])
    desc = pooled["stats"]["per_model"][0]["panel"]["porter_mean"]["align_descriptive"]
    assert desc["a"]["mean"] == 0.2


def test_a_whole_run_left_unscored_for_alignment_is_refused(tmp_path):
    scored = _run_tree(tmp_path, "r1", {"S1": {"a": 80.0}})
    unscored = _run_tree(tmp_path, "r2", {"S1": {"a": 70.0}})
    (unscored / "test_30" / "S1" / "alignment_scores.json").unlink()
    gaps = rosters.unjudged([scored, unscored], ["a"], "alignment_scores.json")
    assert gaps == ["r2/S1: no alignment_scores.json"]

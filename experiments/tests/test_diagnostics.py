"""The harness's own records, read per scenario, and the two pools that use them.

Three things are held here. ``diagnostics`` reads every source a run writes and
keeps "this agent keeps no ledger" apart from "this agent had no findings".
``pool tune`` keeps successive calibration runs apart rather than averaging them
together. And the ablation pool's output is readable by the ablation tables,
which is the step a key rename once broke without any test noticing: the pool
wrote ``config.reference`` while the tables read ``config.a0``.
"""

from __future__ import annotations

import csv
import json
import os
from pathlib import Path

import pytest

from isd_experiments import paths
from isd_experiments.pool import diagnostics, tune

GOLDEN = paths.exp_root() / "tests" / "fixtures" / "golden"
MINI = paths.exp_root() / "tests" / "fixtures" / "mini_run"
PROPOSED = "alignmentgraph-isd"
BASELINE = "react-isd"


def _write(path: Path, doc) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(doc), encoding="utf-8")


def _scenario(scen: Path, *, cut_stage: str | None = None, open_findings: int = 1,
              c3: float = 1.0) -> None:
    """One scenario as the runner lays it out: the proposed system's four files
    and a baseline's trajectory, and no comparison_report (not judged yet)."""
    stages = ("analysis", "outcomes", "assessment")
    autonomy = {
        stage: {"turns_used": 4 + i, "context_len": 1000 * (i + 1), "gave_up": False,
                "via_budget_exhaustion": stage == cut_stage, "history_dropped": 0}
        for i, stage in enumerate(stages)
    }
    _write(scen / f"{PROPOSED}_trajectory.json", {
        "trajectory": {"events": [
            {"action": "work_sets", "context": {"phase": "assessment", "set_count": 3,
                                                "pair_count": 4}}]},
        "metadata": {
            "token_usage": {"total_tokens": 1000, "llm_calls": 10},
            "execution_time_seconds": 60.0, "errors": [],
            "audit": {"ready_to_aggregate": True},
            "run_config": {"max_turns": 24, "development_mode": "light"},
            "autonomy": autonomy,
        },
    })
    _write(scen / f"{PROPOSED}_graph.json", {
        "relation_coverage": {"C2": {"coverage": 1.0}, "C3": {"coverage": c3},
                              "C4": {"coverage": 0.5}, "P6": {"coverage": 0.0}},
        "objective_alignment": {"o1": {"aligned": True}, "o2": {"aligned": False}},
        "metadata": {"node_counts_by_type": {"objective": 2}},
    })
    findings = [{"type": "C4", "outcome": "open", "open_reason": "unseen",
                 "shown_to_agent": 0} for _ in range(open_findings)]
    findings.append({"type": "bloom", "outcome": "repaired_by_agent", "shown_to_agent": 1})
    _write(scen / f"{PROPOSED}_violations.json", findings)
    _write(scen / f"{BASELINE}_trajectory.json", {
        "metadata": {"token_usage": {"total_tokens": 200}, "execution_time_seconds": 5.0}})


@pytest.fixture
def run_dir(tmp_path):
    root = tmp_path / "train_10_benchmark_qwen3.5-9b_t1_20260101_000000"
    _scenario(root / "train_10" / "S-001", cut_stage="assessment")
    _scenario(root / "train_10" / "S-002", open_findings=3, c3=0.0)
    return root


class TestReadingOneCell:
    def test_every_source_is_read(self, run_dir):
        cell = diagnostics.read_cell(run_dir / "train_10" / "S-001", PROPOSED)
        assert cell["total_tokens"] == 1000.0
        assert cell["ready_to_aggregate"] is True and cell["stopped"] is False
        assert cell["autonomy"]["assessment"]["via_budget_exhaustion"] is True
        assert cell["relation_coverage"]["C4"] == 0.5
        assert cell["objectives_aligned"] == 0.5
        assert cell["work_sets"]["assessment"]["set_count"] == 3.0
        assert cell["ledger"]["by_outcome"]["open"] == 1
        assert cell["ledger"]["open_by_reason"]["unseen"] == 1
        assert cell["ledger"]["shown_to_agent"] == 1

    def test_a_baseline_reads_none_not_zero(self, run_dir):
        cell = diagnostics.read_cell(run_dir / "train_10" / "S-001", BASELINE)
        assert cell["total_tokens"] == 200.0
        for field in ("autonomy", "relation_coverage", "ledger", "ready_to_aggregate"):
            assert cell[field] is None, field

    def test_an_agent_that_left_no_trajectory_is_absent(self, run_dir):
        assert diagnostics.read_cell(run_dir / "train_10" / "S-001", "eduplanner") is None

    def test_an_unjudged_scenario_is_still_read(self, run_dir):
        assert [sid for sid, _ in diagnostics.scenario_dirs(run_dir)] == ["S-001", "S-002"]

    def test_a_stopped_run_is_recognised_by_the_package_marker(self, tmp_path):
        scen = tmp_path / "S"
        _write(scen / f"{PROPOSED}_trajectory.json", {"metadata": {
            "errors": ["outcomes produced no course modules; run stopped"]}})
        assert diagnostics.read_cell(scen, PROPOSED)["stopped"] is True


class TestSummaries:
    def test_a_cut_stage_is_reported_as_cut(self, run_dir):
        cells = diagnostics.collect([run_dir], [PROPOSED])[PROPOSED]
        au = diagnostics.summarize(cells, diagnostics.STAGE_ORDER)["autonomy"]
        assert list(au["by_stage"]) == ["analysis", "outcomes", "assessment"]
        assert au["by_stage"]["assessment"]["pct_via_budget_exhaustion"] == 50.0
        assert au["by_stage"]["analysis"]["pct_via_budget_exhaustion"] == 0.0
        assert au["context_growth_first_to_last"] == 3.0

    def test_coverage_and_ledger_pool_over_runs(self, run_dir):
        cells = diagnostics.collect([run_dir], [PROPOSED])[PROPOSED]
        s = diagnostics.summarize(cells, diagnostics.STAGE_ORDER)
        cov = s["relation_coverage"]
        assert cov["relation_coverage_mean"]["C3"] == 0.5
        assert cov["core_coverage_mean"] == pytest.approx((1.0 + 0.5 + 0.5) / 3)
        assert cov["pct_runs_core_complete"] == 0.0
        lg = s["ledger"]
        assert lg["open_per_run"]["mean"] == 2.0
        assert lg["open_by_type"] == {"C4": 4}
        assert lg["pct_of_open_by_reason"]["unseen"] == 100.0

    def test_a_baseline_summarises_to_cost_only(self, run_dir):
        cells = diagnostics.collect([run_dir], [BASELINE])[BASELINE]
        s = diagnostics.summarize(cells, diagnostics.STAGE_ORDER)
        assert s["cost"]["total_tokens"]["mean"] == 200.0
        assert s["autonomy"] is None and s["ledger"] is None
        assert s["relation_coverage"] is None


class TestPoolTune:
    def test_successive_runs_stay_apart(self, tmp_path, run_dir):
        later = tmp_path / "train_10_benchmark_qwen3.5-9b_t1_20260102_000000"
        _scenario(later / "train_10" / "S-001")
        doc, rows = tune.pool({"qwen3.5-9b": [later, run_dir]}, [PROPOSED, BASELINE])
        assert [e["run_dir"] for e in doc["runs"]] == [run_dir.name, later.name]
        assert doc["runs"][0]["agents"][PROPOSED]["n_scenarios"] == 2
        assert doc["runs"][1]["agents"][PROPOSED]["n_scenarios"] == 1
        assert doc["runs"][0]["agents"][PROPOSED]["run_config"]["max_turns"] == [24]
        assert len(rows) == 6

    def test_the_csv_has_one_row_per_cell(self, tmp_path, run_dir):
        doc, rows = tune.pool({"qwen3.5-9b": [run_dir]}, [PROPOSED, BASELINE])
        path = tmp_path / "tune_diagnostics.csv"
        tune.write_csv(rows, path)
        with open(path, encoding="utf-8") as fh:
            read = list(csv.DictReader(fh))
        assert [(r["scenario"], r["agent"]) for r in read] == [
            ("S-001", PROPOSED), ("S-001", BASELINE), ("S-002", PROPOSED), ("S-002", BASELINE)]
        assert read[0]["stages_cut"] == "assessment"
        assert read[2]["open_types"] == "C4:3"
        assert read[1]["turns_used_analysis"] == ""

    def test_the_panel_is_read_from_the_named_encoder_artifact(self, run_dir):
        scen = run_dir / "train_10" / "S-001"
        sig = tune.PANEL[0]
        _write(scen / "alignment_scores.bgem3.json", {"agents": {PROPOSED: {sig: 0.42}}})
        try:
            primary, _ = tune.pool({"qwen3.5-9b": [run_dir]}, [PROPOSED])
            sweep, rows = tune.pool({"qwen3.5-9b": [run_dir]}, [PROPOSED],
                                    "alignment_scores.bgem3.json")
        finally:
            (scen / "alignment_scores.bgem3.json").unlink()
        assert primary["config"]["panel_artifact"] == "alignment_scores.json"
        assert sweep["config"]["panel_artifact"] == "alignment_scores.bgem3.json"
        assert rows[0][sig] == 0.42


@pytest.fixture(scope="module")
def pooled_ablation(tmp_path_factory):
    from isd_experiments.pool import ablation
    out = tmp_path_factory.mktemp("abl") / "pooled_ablation.json"
    old = os.environ.get("RESULTS_DIR")
    os.environ["RESULTS_DIR"] = str(MINI)
    try:
        ablation.run(patterns=["test_30_benchmark_*_a*"],
                     comparison_pooled=GOLDEN / "pooled_comparison.json",
                     out=out, quiet=True)
    finally:
        if old is None:
            os.environ.pop("RESULTS_DIR", None)
        else:
            os.environ["RESULTS_DIR"] = old
    return json.loads(out.read_text(encoding="utf-8"))


class TestAblationPoolFeedsItsTables:
    def test_the_tables_read_what_the_pool_writes(self, pooled_ablation):
        from isd_experiments.report import ablation_tables
        written = ablation_tables.build(pooled_ablation)
        assert "tab_ablation_mechanism.tex" in written
        assert "Mechanism" in written["stats_ablation.md"]

    def test_the_mechanism_layer_covers_every_size_and_arm(self, pooled_ablation):
        labels = {m["label"] for m in pooled_ablation["models"]}
        assert {e["label"] for e in pooled_ablation["mechanism"]} == labels
        arms = set(pooled_ablation["config"]["arms"]) | {pooled_ablation["config"]["reference"]}
        for entry in pooled_ablation["mechanism"]:
            assert set(entry["arms"]) == arms


# ── reading a tune run without reading it by hand ───────────────────────────

class TestHarnessCounters:
    def test_each_event_lands_in_its_own_counter(self):
        events = [
            {"action": "constrained_pass", "context": {"output_summary": "accepted"}},
            {"action": "constrained_pass",
             "context": {"output_summary": "rejected: no artifact came back"}},
            {"action": "constrained_pass", "context": {"output_summary": "rejected: x.y empty"}},
            {"action": "constrained_pass_skipped",
             "context": {"output_summary": "grammar cannot fix"}},
            {"action": "submit_rejected",
             "context": {"input_summary": "t attempt 1 | raw= | args= | content=0"}},
            {"action": "submit_rejected",
             "context": {"input_summary": "t attempt 1 | raw=a:list | args=a:list"}},
            {"action": "agentic_gave_up", "context": {}},
            {"action": "llm_error", "context": {
                "output_summary": "Error code: 400 - This model's maximum context length is 16384"}},
            {"action": "llm_error", "context": {
                "output_summary": "Could not parse response content as the length limit was reached"}},
            {"action": "llm_error", "context": {"output_summary": "Connection error."}},
            {"action": "argument_reshaped", "context": {
                "input_summary": "a.minItems (schema keyword dropped); b (schema keyword dropped)"}},
        ]
        c = diagnostics.harness_counts(events)
        assert (c["passes"], c["pass_accepted"], c["pass_empty"], c["pass_refused"]) == (3, 1, 1, 1)
        assert c["pass_skipped"] == 1
        assert (c["rejected"], c["rejected_empty_args"]) == (2, 1)
        assert (c["gave_up"], c["context_overflow"], c["completion_cap"], c["connection"]) == (1, 1, 1, 1)
        assert c["schema_keywords_dropped"] == 2

    def test_a_baseline_has_no_harness_record(self, run_dir):
        assert diagnostics.read_cell(run_dir / "train_10" / "S-001", BASELINE)["harness"] is None
        assert diagnostics.read_cell(run_dir / "train_10" / "S-001", PROPOSED)["harness"]["passes"] == 0


class TestPostPilotClaims:
    def test_a_plan_is_not_a_result_and_an_invented_pilot_is(self):
        from isd_experiments.audit import fabrication

        invented = {"evaluation": {
            "formative": {"data_collection": {"learner_feedback": ["It was hard."],
                                              "performance_data": {"m": "Task Completion Rate: 40%"}}},
            "summative": {"adoption_decision": {"decision": "Adopt with minor revisions"}}},
            "development": {"expert_review": {"reviewers": ["Subject Matter Expert (SME)"]}}}
        planned = {"evaluation": {
            "summative": {"adoption_decision": {
                "criteria": {"goal_attainment": "at least 80% of learners at the pass level"},
                "status": "pending pilot"}}},
            "development": {"expert_review": {"reviewers": [
                "Automated pedagogical self-validation suite (deterministic checks)"]}}}
        assert fabrication.audit_output(invented) == {
            "result_fields": 2, "human_reviewers": 1, "decision_taken": True}
        assert fabrication.audit_output({"addie_output": planned}) == {
            "result_fields": 0, "human_reviewers": 0, "decision_taken": False}, (
            "a target stated as a percentage is a plan, not a result")


class TestGapWithItsNoise:
    @staticmethod
    def _view(mine: float, theirs: float, *, g=(0.0, 0.0), o=(0.0, 0.0)) -> dict:
        def agent(total, addie_g, addie_o):
            return {"total_score": total, "addie_median": total, "trajectory_score": total,
                    "judges": {"judge-a": {"addie": addie_g, "traj": total, "items": {"Dev2": addie_g}},
                               "judge-b": {"addie": addie_o, "traj": total, "items": {"Dev2": addie_o}}}}
        return {PROPOSED: agent(mine, *g), BASELINE: agent(theirs, *o)}

    def test_a_gap_carries_its_standard_error_and_says_when_it_is_noise(self):
        steady = {f"S{i}": self._view(80.0, 83.0 + (i % 2) * 0.2) for i in range(10)}
        noisy = {f"S{i}": self._view(80.0 + (8 if i % 2 else -8), 81.0) for i in range(10)}
        g = tune.paired_gap(steady, PROPOSED, BASELINE)["total_score"]
        assert g["n"] == 10 and g["mean"] == pytest.approx(-3.1) and g["detected"]
        n = tune.paired_gap(noisy, PROPOSED, BASELINE)["total_score"]
        assert n["mean"] == pytest.approx(-1.0) and not n["detected"]

    def test_the_gap_is_split_by_judge_and_by_item(self):
        views = {f"S{i}": self._view(80.0, 80.0, g=(90.0, 70.0), o=(80.0, 80.0))
                 for i in range(4)}
        g = tune.paired_gap(views, PROPOSED, BASELINE)
        assert g["addie@judge-a"]["mean"] == pytest.approx(10.0)
        assert g["addie@judge-b"]["mean"] == pytest.approx(-10.0)
        assert g["Dev2@judge-a"]["mean"] == pytest.approx(10.0)

    def test_a_shift_between_runs_cancels_the_baselines_own_drift(self):
        before = {f"S{i}": self._view(80.0, 84.0) for i in range(6)}
        after = {f"S{i}": self._view(81.0, 85.0 + (0.1 if i % 2 else -0.1)) for i in range(6)}
        shift = tune.gap_shift(before, after, PROPOSED, BASELINE)["total_score"]
        assert shift["mean"] == pytest.approx(0.0, abs=1e-9), (
            "both agents moved by one point: the gap did not move")

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


def _report(scen: Path, scores: dict[str, float], *, judges=("judge-a", "judge-b"),
            disagree: bool = False) -> None:
    """A comparison_report.json scoring each agent the same under every judge."""
    _write(scen / "comparison_report.json", {"comparison": {"rankings": [
        {"agent_id": a, "total_score": v, "addie_median": v, "trajectory_score": v,
         "high_disagreement": disagree, "score_range": f"{v - 2}-{v + 2}",
         "judges": [{"model": j, "addie_score": v, "trajectory_score": v} for j in judges]}
        for a, v in scores.items()]}})


class TestPoolTuneReadsEveryExperiment:
    """One pool over a tune, a comparison or an ablation run dir: each read with
    the roster it was launched with, judged by one LLM judge roster only."""

    def test_a_run_dir_is_read_with_the_roster_it_was_launched_with(self, run_dir):
        _write(run_dir / "benchmark_summary.json", {"config": {
            "agents": [PROPOSED], "rate_limit": "turbo",
            "pinned_env": {"AGENT_MODEL_THINKING_BUDGET": "32"}}})
        doc, _ = tune.pool({"m": [run_dir]}, None)
        entry = doc["runs"][0]
        assert entry["roster"] == [PROPOSED] and list(entry["agents"]) == [PROPOSED]
        assert entry["posture"] == {"thinking_budget": "32", "rate_limit": "turbo"}

    def test_a_missing_scenario_is_named(self, run_dir):
        (run_dir / "train_10" / "S-002" / f"{BASELINE}_trajectory.json").unlink()
        doc, _ = tune.pool({"m": [run_dir]}, [PROPOSED, BASELINE])
        assert doc["runs"][0]["agents"][BASELINE]["missing_scenarios"] == ["S-002"]
        assert doc["runs"][0]["agents"][PROPOSED]["missing_scenarios"] == []

    def test_two_judge_rosters_are_never_pooled_into_one_gap(self, run_dir):
        _report(run_dir / "train_10" / "S-001", {PROPOSED: 80.0, BASELINE: 78.0})
        _report(run_dir / "train_10" / "S-002", {PROPOSED: 80.0, BASELINE: 78.0},
                judges=("judge-a", "judge-c"))
        doc, _ = tune.pool({"m": [run_dir]}, [PROPOSED, BASELINE])
        entry = doc["runs"][0]
        assert entry["mixed_roster"] and entry["gaps"] == {}

    def test_two_agents_judged_by_different_rosters_in_one_scenario_are_mixed(self, run_dir):
        # A+B for one agent, A+C for the other, in EVERY scenario: a union over
        # the scenario would read one roster, A+B+C.
        for sid in ("S-001", "S-002"):
            scen = run_dir / "train_10" / sid
            _report(scen, {PROPOSED: 80.0}, judges=("judge-a", "judge-b"))
            doc = json.loads((scen / "comparison_report.json").read_text())
            _report(scen, {BASELINE: 78.0}, judges=("judge-a", "judge-c"))
            other = json.loads((scen / "comparison_report.json").read_text())
            doc["comparison"]["rankings"] += other["comparison"]["rankings"]
            _write(scen / "comparison_report.json", doc)
        doc, _ = tune.pool({"m": [run_dir]}, [PROPOSED, BASELINE])
        entry = doc["runs"][0]
        assert entry["mixed_roster"] and entry["gaps"] == {}
        assert "total_score" not in entry["agents"][PROPOSED]["scores"], (
            "two rosters' scores are not pooled into one mean either")

    def test_an_agent_that_failed_everywhere_stays_as_zero_of_n(self, run_dir):
        _write(run_dir / "benchmark_summary.json", {"scenarios": {"train_10": {
            "S-001": {}, "S-002": {}, "S-003": {}}}})
        doc, _ = tune.pool({"m": [run_dir]}, [PROPOSED, BASELINE, "never-ran"])
        entry = doc["runs"][0]
        assert entry["n_scenarios"] == 3, "a scenario where every agent failed still counts"
        assert entry["agents"]["never-ran"]["n_scenarios"] == 0
        assert entry["agents"]["never-ran"]["missing_scenarios"] == ["S-001", "S-002", "S-003"]
        assert entry["agents"][PROPOSED]["missing_scenarios"] == ["S-003"]

    def test_a_shift_across_two_judge_rosters_is_not_computed(self, tmp_path, run_dir):
        earlier = tmp_path / "train_10_benchmark_qwen3.5-9b_t1_20251231_000000"
        for root, judges in ((earlier, ("judge-a", "judge-c")), (run_dir, ("judge-a", "judge-b"))):
            for sid in ("S-001", "S-002"):
                scen = root / "train_10" / sid
                _scenario(scen)
                _report(scen, {PROPOSED: 80.0, BASELINE: 70.0}, judges=judges)
        doc, _ = tune.pool({"m": [run_dir]}, [PROPOSED, BASELINE])
        tune.add_shifts(doc, earlier)
        sv = doc["runs"][0]["shift_vs"]
        assert sv["pairs"] == {} and "another LLM judge roster" in sv["skipped"]

    def test_the_gap_covers_the_alignment_signals_too(self, run_dir):
        sig = tune.PANEL[0]
        for i, sid in enumerate(("S-001", "S-002")):
            scen = run_dir / "train_10" / sid
            _report(scen, {PROPOSED: 80.0 + i, BASELINE: 78.0}, disagree=bool(i))
            _write(scen / "alignment_scores.json",
                   {"agents": {PROPOSED: {sig: 0.8}, BASELINE: {sig: 0.5 + i / 10}}})
        doc, _ = tune.pool({"m": [run_dir]}, [PROPOSED, BASELINE])
        g = doc["runs"][0]["gaps"][f"{PROPOSED} - {BASELINE}"]
        assert g[sig]["mean"] == pytest.approx(0.25)
        assert g["total_score"]["mean"] == pytest.approx(2.5)
        rel = doc["runs"][0]["agents"][PROPOSED]["judge_reliability"]
        assert rel["high_disagreement"] == 1 and rel["range_mean"] == pytest.approx(4.0)

    def test_findings_are_charged_to_the_stage_their_family_writes(self, run_dir):
        scen = run_dir / "train_10" / "S-001"
        _write(scen / f"{PROPOSED}_violations.json", [
            {"type": "C2", "outcome": "open", "first_family": "assessment_designer"},
            {"type": "C3", "outcome": "repaired_by_agent", "first_family": "activity_designer"}])
        assert tune._findings_by_stage(scen, PROPOSED) == {
            "open": {"assessment": 1}, "all": {"assessment": 1, "activities": 1}}


class TestReadingTheReport:
    def test_an_arm_with_no_c4_reference_is_named(self, run_dir):
        for sid in ("S-001", "S-002"):
            _write(run_dir / "train_10" / sid / f"{PROPOSED}_output.json", {"addie_output": {
                "design": {"learning_objectives": [{"id": "ILO-01", "level": "apply"}],
                           "learning_activities": [{"aligned_objectives": ["ILO-01"]}]},
                "development": {"assessment_tools": [{"id": "AT-01", "items": []}]}}})
        doc, _ = tune.pool({"m": [run_dir]}, [PROPOSED])
        assert "no_c4_references" in doc["runs"][0]["agents"][PROPOSED]["harness"]["attention"]

    def test_an_arm_whose_items_are_one_question_repeated_is_named(self, run_dir):
        repeated = [{"question": "Same?", "aligned_objective": "ILO-01"}] * 6
        for sid, items in (("S-001", repeated), ("S-002", [])):
            _write(run_dir / "train_10" / sid / f"{PROPOSED}_output.json", {"addie_output": {
                "design": {"learning_objectives": [{"id": "ILO-01", "level": "apply"}]},
                "development": {"assessment_tools": [{"id": "AT-01", "items": items}]}}})
        doc, _ = tune.pool({"m": [run_dir]}, [PROPOSED])
        s = doc["runs"][0]["agents"][PROPOSED]
        assert s["items"]["runs_with_repeated_items"] == 1
        assert s["items"]["runs_without_items"] == 1
        assert {"repeated_items", "no_assessment_items"} <= set(s["harness"]["attention"])

    def test_a_missing_panel_artifact_names_the_arms_that_are_there(self, run_dir, capsys):
        _write(run_dir / "train_10" / "S-001" / "alignment_scores.bgem3.json", {"agents": {}})
        doc, _ = tune.pool({"m": [run_dir]}, [PROPOSED])
        assert doc["runs"][0]["panel_missing"] == ["bgem3"]
        tune.print_report(doc)
        assert "--encoder" in capsys.readouterr().out

    def test_one_scenario_says_the_items_cannot_be_separated(self, capsys):
        g = tune.paired_gap({"S1": TestGapWithItsNoise._view(80.0, 70.0)}, PROPOSED, BASELINE)
        tune._print_gap("gap", g)
        assert "not computable (n=1" in capsys.readouterr().out

    def test_a_comparison_run_reads_one_line_per_baseline_and_rungs_side_by_side(
            self, tmp_path, capsys):
        others = ["b1", "b2", "b3"]
        dirs = []
        for k, stamp in enumerate(("20260101_000000", "20260102_000000")):
            root = tmp_path / f"test_90_benchmark_m{k}_c1_{stamp}"
            for sid in ("S-001", "S-002"):
                scen = root / "test_90" / sid
                _scenario(scen)
                for b in others:
                    _write(scen / f"{b}_trajectory.json", {"metadata": {}})
                _report(scen, {PROPOSED: 80.0 + k, **{b: 70.0 for b in others}})
            dirs.append(root)
        doc, _ = tune.pool({"m0": [dirs[0]], "m1": [dirs[1]]}, [PROPOSED, *others])
        tune.print_report(doc)
        out = capsys.readouterr().out
        assert "gaps to each baseline" in out
        assert "Total gap by run dir" in out and "+11.0" in out


class TestFactorial:
    CELLS = {("multi", "graph"): "mg", ("single", "graph"): "sg",
             ("multi", "prose"): "mp", ("single", "prose"): "sp"}

    def test_main_effects_and_interaction_read_off_the_four_cells(self):
        # decomposition +10 under graph, +4 under prose; graph +2 under multi, -4 under single
        views = {f"S{i}": {"mg": {"total_score": 80.0 + i}, "sg": {"total_score": 70.0 + i},
                           "mp": {"total_score": 78.0 + i}, "sp": {"total_score": 74.0 + i}}
                 for i in range(3)}
        f = tune.factorial(views, self.CELLS)["total_score"]
        assert f["decomposition|graph"]["mean"] == pytest.approx(10.0)
        assert f["decomposition|prose"]["mean"] == pytest.approx(4.0)
        assert f["decomposition"]["mean"] == pytest.approx(7.0)
        assert f["substrate"]["mean"] == pytest.approx((2.0 - 4.0) / 2)
        assert f["interaction"]["mean"] == pytest.approx(6.0)

    def test_a_scenario_missing_a_cell_is_left_out(self):
        views = {"S1": {"mg": {"total_score": 1.0}, "sg": {"total_score": 1.0},
                        "mp": {"total_score": 1.0}}}
        assert tune.factorial(views, self.CELLS) == {}


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
        assert "tab_ablation_process.tex" in written
        assert "Process measures" in written["stats_ablation.md"]

    def test_the_registered_tests_reach_the_pool_and_the_report(self, pooled_ablation):
        from isd_experiments.report import ablation_tables
        reg = pooled_ablation["registered"]
        assert len(reg["family"]) == 6 and reg["failure_policy"] == "zero"
        assert pooled_ablation["config"]["primary_failure_policy"] == "zero"
        assert "Registered tests" in ablation_tables.build(pooled_ablation)["stats_ablation.md"]

    def test_the_process_layer_covers_every_size_and_arm(self, pooled_ablation):
        labels = {m["label"] for m in pooled_ablation["models"]}
        assert {e["label"] for e in pooled_ablation["process"]} == labels
        arms = set(pooled_ablation["config"]["arms"]) | {pooled_ablation["config"]["reference"]}
        for entry in pooled_ablation["process"]:
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

    def test_the_single_arms_loop_ends_are_counted(self):
        c = diagnostics.harness_counts([{"action": "stage_abandoned", "context": {}},
                                        {"action": "repair_window_closed", "context": {}},
                                        {"action": "budget_exhausted", "context": {}}])
        assert (c["stage_abandoned"], c["repair_window_closed"], c["budget_exhausted"]) == (1, 1, 1)

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


def _design(*, nested: bool, repaired: bool = False) -> dict:
    """Two objectives; ILO-01 closes its triad, ILO-02 is practised only."""
    items = [{"item_id": "Q1", "aligned_objective": "ILO-01",
              "required_cognitive_process": "apply"}]
    tools = ([{"id": "AT-01", "items": items}] if nested
             else [dict(items[0], task_id="assessment:AT-01")])
    return {"addie_output": {
        "design": {
            "learning_objectives": [{"id": "ILO-01", "level": "apply"},
                                    {"id": "ILO-02", "level": "evaluate"}],
            "learning_activities": [
                {"id": "TLA-1", "aligned_objectives": ["ILO-01"],
                 "learner_cognitive_process": "apply",
                 "prepares_for_assessment": ["AT-01"], "repaired": repaired},
                {"id": "TLA-2", "aligned_objectives": ["ILO-02"],
                 "learner_cognitive_process": "understand",
                 "prepares_for_assessment": ["Q1"]}],
        },
        "development": {"assessment_tools": tools},
    }}


class TestTriadReferences:
    """The triad's references read off the deliverable, the same way on both
    substrates -- the graph arm nests items in tasks, the prose blackboard's
    items name their task -- so the two arms can be compared at all."""

    @pytest.mark.parametrize("nested", [True, False])
    def test_the_same_design_reads_the_same_on_either_shape(self, nested):
        doc = _design(nested=nested)["addie_output"]
        st = diagnostics.read_triad_references(doc)
        assert st["objectives_assessed"] == 0.5
        assert st["objectives_practised"] == 1.0
        # TLA-2 names a QUESTION, not a task: not a C4 reference.
        assert st["activities_prepare"] == 0.5
        assert st["objectives_closed_triad"] == 0.5
        assert st["objectives_item_level_met"] == 0.5
        assert st["objectives_activity_level_met"] == 0.5

    def test_what_the_repair_net_wrote_is_split_out(self):
        st = diagnostics.read_triad_references(_design(nested=True, repaired=True)["addie_output"])
        assert st["activities_prepare"] == 0.5
        assert st["activities_prepare_unrepaired"] == 0.0
        assert st["activities_repaired"] == 0.5

    def test_a_repair_of_one_field_does_not_disown_the_others(self):
        """MEASURED (run t1 20261002_134550): the net re-pointed 63% of the
        graph arm's activities for C4 and touched no ``aligned_objectives``,
        yet C3 read 0.41 unrepaired against 0.97 — the flag marked the
        activity, not the field. ``repaired_fields`` says which."""
        doc = _design(nested=True, repaired=True)["addie_output"]
        doc["design"]["learning_activities"][0]["repaired_fields"] = ["prepares_for_assessment"]
        item = doc["development"]["assessment_tools"][0]["items"][0]
        item.update(repaired=True, repaired_fields=["type"])
        st = diagnostics.read_triad_references(doc)
        assert st["objectives_practised_unrepaired"] == 1.0
        assert st["objectives_assessed_unrepaired"] == 0.5
        assert st["activities_prepare_unrepaired"] == 0.0
        assert st["activities_repaired"] == 0.5

    def test_no_objective_ids_is_not_measured(self):
        assert diagnostics.read_triad_references({"design": {"learning_objectives": [
            {"statement": "x"}]}}) is None

    def test_it_reaches_the_pool_and_a_baseline_stays_none(self, run_dir):
        scen = run_dir / "train_10" / "S-001"
        _write(scen / f"{PROPOSED}_output.json", _design(nested=True))
        _write(scen / f"{BASELINE}_output.json", _design(nested=True))
        assert diagnostics.read_cell(scen, PROPOSED)["triad_references"]["n_objectives"] == 2
        assert diagnostics.read_cell(scen, BASELINE)["triad_references"] is None
        cells = diagnostics.collect([run_dir], [PROPOSED])[PROPOSED]
        st = diagnostics.summarize(cells, diagnostics.STAGE_ORDER)["triad_references"]
        assert st["n_runs"] == 1 and st["objectives_closed_triad"] == 0.5


class TestSingleArmStages:
    """The single arm reports one record for the run; its per-stage numbers
    are what the registered prediction (context grows with stage position) is
    read off, so they become stage entries like the multi arm's."""

    def test_the_design_record_is_split_into_its_stages(self, tmp_path):
        scen = tmp_path / "S"
        _write(scen / f"{PROPOSED}_trajectory.json", {"metadata": {"autonomy": {"design": {
            "context_len": 9000, "turns_used": 30, "via_budget_exhaustion": True,
            "context_len_by_stage": {"analysis": 3000, "outcomes": 6000, "assessment": 9000},
            "turns_by_stage": {"analysis": 10, "outcomes": 8, "assessment": 12}}}}})
        cells = {"S": [diagnostics.read_cell(scen, PROPOSED)]}
        au = diagnostics.summarize(cells, diagnostics.STAGE_ORDER)["autonomy"]
        assert list(au["by_stage"])[:3] == ["analysis", "outcomes", "assessment"]
        assert au["context_growth_first_to_last"] == 3.0
        assert au["by_stage"]["outcomes"]["turns_used"]["mean"] == 8.0
        # The run-level flags stay on the run, not on any one stage.
        assert au["by_stage"]["design"]["pct_via_budget_exhaustion"] == 100.0
        assert "context_len" not in au["by_stage"]["design"]

    def test_what_each_stage_cost_lands_on_that_stage(self, tmp_path):
        scen = tmp_path / "S"
        _write(scen / f"{PROPOSED}_trajectory.json", {"metadata": {"autonomy": {"design": {
            "context_len_by_stage": {"analysis": 3000, "outcomes": 6000},
            "spend_by_stage": {"analysis": {"llm_calls": 4, "prompt_tokens": 9000,
                                            "completion_tokens": 1000}}}}}})
        au = diagnostics.summarize({"S": [diagnostics.read_cell(scen, PROPOSED)]},
                                   diagnostics.STAGE_ORDER)["autonomy"]
        assert au["by_stage"]["analysis"]["prompt_tokens"]["mean"] == 9000.0
        assert "prompt_tokens" not in au["by_stage"]["outcomes"]


def test_pool_ablation_reads_the_named_encoder_arm(tmp_path):
    """A tune slice scored while the primary's endpoint was off has only the
    sensitivity arms' artifacts; `--encoder` points the pool at one of them."""
    from isd_experiments.pool import ablation

    run = tmp_path / "R"
    scen = run / "train_10" / "S-001"
    _write(scen / "comparison_report.json", {"comparison": {"rankings": [
        {"agent_id": PROPOSED, "total_score": 80.0}]}})
    _write(scen / "alignment_scores.bgem3.json",
           {"agents": {PROPOSED: {"porter_mean": 0.4}}})
    primary = ablation.per_scenario_maps([run], [PROPOSED])
    bgem3 = ablation.per_scenario_maps([run], [PROPOSED], "alignment_scores.bgem3.json")
    assert primary["porter_mean"][PROPOSED] == {}
    assert bgem3["porter_mean"][PROPOSED] == {"S-001": 0.4}


class TestThePaperPoolsRefuseAnotherRoster:
    """``pool comparison`` / ``pool ablation`` feed the paper: a cell scored by
    another LLM judge roster than the declared one stops them."""

    def test_a_cell_judged_by_another_roster_stops_the_pool(self, run_dir):
        from isd_experiments.pool import rosters
        _report(run_dir / "train_10" / "S-001", {PROPOSED: 80.0}, judges=("old-a", "old-b"))
        with pytest.raises(SystemExit, match="another LLM judge roster"):
            rosters.require_declared_roster([run_dir], [PROPOSED])

    def test_the_declared_roster_and_an_unrecorded_one_pass(self, run_dir, capsys):
        from isd_experiments.pool import rosters
        _report(run_dir / "train_10" / "S-001", {PROPOSED: 80.0}, judges=rosters.declared())
        _write(run_dir / "train_10" / "S-002" / "comparison_report.json", {"comparison": {
            "rankings": [{"agent_id": PROPOSED, "total_score": 1.0, "judges": []}]}})
        rosters.require_declared_roster([run_dir], [PROPOSED])
        assert "record no LLM judge" in capsys.readouterr().out

    def test_an_absent_arm_is_never_a_baseline(self, run_dir):
        doc, _ = tune.pool({"m": [run_dir]}, [PROPOSED, "alignmentgraph-isd-single-prose",
                                              BASELINE])
        assert set(doc["runs"][0]["gaps"]) == {f"{PROPOSED} - {BASELINE}",
                                               f"alignmentgraph-isd-single-prose - {BASELINE}"}


def test_the_harness_counts_name_a_stage_the_window_ended_and_a_restored_user_turn():
    counts = diagnostics.harness_counts([
        {"action": "agentic_gave_up",
         "context": {"input_summary": "the prompt exceeds the serving window"}},
        {"action": "agentic_gave_up", "context": {"input_summary": "turn budget exhausted"}},
        {"action": "user_turn_restored", "context": {}}])
    assert counts["gave_up"] == 2
    assert counts["prompt_exceeds_window"] == 1
    assert counts["user_turn_restored"] == 1

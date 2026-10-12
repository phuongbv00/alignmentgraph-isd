"""One run, end to end, with agents that call no model.

What a run directory holds is fixed by everything that reads it -- the two
judges, pooling, the audits -- so the layout, the file names and the summary's
shape are asserted here rather than trusted. Then the LLM judge is run over
that directory with the evaluator replaced, to pin what it asks the evaluator
for, what it skips, and what it writes back.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from isd_experiments import paths
from isd_experiments.config import current
from isd_experiments.runner import agents as registry
from isd_experiments.runner import execute
from isd_experiments.runner import llm as runner_llm

SCENARIOS = ("S-001", "S-002")


@pytest.fixture
def world(tmp_path, monkeypatch):
    """A split of two scenarios, a results root, and agents that answer at once."""
    saved = dict(os.environ)
    split = tmp_path / "scenarios" / "tiny_split"
    split.mkdir(parents=True)
    for sid in SCENARIOS:
        (split / f"{sid}.json").write_text(json.dumps({"scenario_id": sid}), encoding="utf-8")
    monkeypatch.setattr(paths, "scenarios_dir", lambda: tmp_path / "scenarios")
    monkeypatch.setattr(runner_llm, "load_credentials", lambda: None)

    seen_configs = []

    def fake_build(agent_id, llm_config, cfg):
        seen_configs.append(llm_config)
        if agent_id == "react-isd":
            def boom(scenario):
                raise RuntimeError("model said no")
            return boom

        def ok(scenario):
            return {"addie_output": {"analysis": {"who": agent_id}},
                    "trajectory": {"steps": []},
                    "metadata": {},
                    "graph": {"nodes": [1]} if agent_id == registry.PROPOSED else None,
                    "contexts": ([{"id": "ctx-1", "agent": "NeedsAnalystAgent"}]
                                 if agent_id == registry.PROPOSED else None),
                    "violations": ([{"key": "C2|ILO-01", "outcome": "open"}]
                                   if agent_id == registry.PROPOSED else None)}
        return ok

    monkeypatch.setattr(registry, "build", fake_build)
    yield tmp_path, current(), seen_configs
    os.environ.clear()
    os.environ.update(saved)


def _generate(tmp_path, cfg, **kw):
    import dataclasses
    profile = dataclasses.replace(cfg.profile("tune"), dataset="tiny_split")
    cfg = dataclasses.replace(cfg, profiles={**cfg.profiles, "tune": profile})
    return execute.generate(cfg, experiment="tune", slot=profile.slots[0], tag="t9",
                            agents=["alignmentgraph-isd", "react-isd"],
                            rate_limit="turbo", results_root=tmp_path / "results",
                            **kw), cfg


class TestTheRunDirectory:
    def test_it_is_named_and_laid_out_as_every_reader_expects(self, world):
        tmp_path, cfg, _ = world
        run_dir, cfg = _generate(tmp_path, cfg)
        model = cfg.by_slot(cfg.profile("tune").slots[0]).model
        assert run_dir.name.startswith(
            f"tiny_split_benchmark_{runner_llm.model_dir_label(model)}_t9_")
        assert cfg.slot_of_label(run_dir.name.split("_benchmark_")[1].split("_t9_")[0])
        for sid in SCENARIOS:
            scen = run_dir / "tiny_split" / sid
            assert (scen / "alignmentgraph-isd_output.json").exists()
            assert (scen / "alignmentgraph-isd_trajectory.json").exists()
            assert (scen / "alignmentgraph-isd_graph.json").exists()
            assert (scen / "alignmentgraph-isd_violations.json").exists()
            assert (scen / "alignmentgraph-isd_contexts.json").exists(), (
                "the transcripts are kept with the run, not lost with the process")
            assert not (scen / "react-isd_contexts.json").exists()
            assert (scen / "alignmentgraph-isd_log.txt").exists()
            # A failure leaves a log and no output: the judges read exactly
            # that pair as "attempted, failed".
            assert (scen / "react-isd_log.txt").exists()
            assert not (scen / "react-isd_output.json").exists()
            assert "FAILED" in (scen / "react-isd_log.txt").read_text(encoding="utf-8")
        for name in ("benchmark_summary.json", "SUMMARY.md", "benchmark_progress.log"):
            assert (run_dir / name).exists(), name

    def test_the_trajectory_carries_tokens_and_time(self, world):
        tmp_path, cfg, _ = world
        run_dir, _ = _generate(tmp_path, cfg)
        traj = json.loads((run_dir / "tiny_split" / "S-001"
                           / "alignmentgraph-isd_trajectory.json").read_text(encoding="utf-8"))
        assert traj["agent_id"] == "alignmentgraph-isd"
        assert "token_usage" in traj["metadata"]
        assert "execution_time_seconds" in traj["metadata"]

    def test_the_summary_says_it_is_not_judged_yet(self, world):
        tmp_path, cfg, _ = world
        run_dir, _ = _generate(tmp_path, cfg)
        results = json.loads((run_dir / "benchmark_summary.json").read_text(encoding="utf-8"))
        assert list(results["scenarios"]) == ["tiny_split"]
        records = results["scenarios"]["tiny_split"]
        assert sorted(records) == list(SCENARIOS)
        for record in records.values():
            assert record["evaluation_deferred"] is True
            assert "evaluation" not in record
            assert record["agents"]["alignmentgraph-isd"]["success"] is True
            assert record["agents"]["react-isd"]["success"] is False

    def test_every_agent_of_a_run_gets_its_own_scope_of_one_config(self, world):
        """Same model, same budget; a counter of its own per agent run."""
        tmp_path, cfg, seen = world
        _generate(tmp_path, cfg)
        assert len(seen) == 4
        assert len({(c.model, c.max_tokens, c.all_base_urls) for c in seen}) == 1
        assert len({id(c._token_counter) for c in seen}) == 4

    def test_the_declared_posture_is_pinned_over_the_environment(self, world, monkeypatch):
        tmp_path, cfg, _ = world
        monkeypatch.setenv("AGENT_MODEL_MAX_OUTPUT_TOKENS", "1")
        _generate(tmp_path, cfg)
        assert os.environ["AGENT_MODEL_MAX_OUTPUT_TOKENS"] == str(cfg.generation.max_output_tokens)
        assert os.environ["BENCHMARK_RATE_LIMIT"] == "turbo"


class TestTheLlmJudgeOverARun:
    @pytest.fixture
    def judged(self, world, monkeypatch):
        tmp_path, cfg, _ = world
        run_dir, _ = _generate(tmp_path, cfg)
        from isd_experiments.judge import llm

        calls = []
        judges = [{"model": m.name, "addie_score": 50.0, "trajectory_score": 50.0}
                  for m in cfg.judge.models]

        def fake_evaluate(command, env, scenario):
            calls.append(command)
            out = Path(command[command.index("--output-dir") + 1])
            agents = command[command.index("--agents") + 1].split(",")
            rankings = [{"agent_id": a, "rank": i + 1, "total_score": 50.0,
                         "addie_median": 50.0, "trajectory_score": 50.0,
                         "phase_scores": {"analysis": 1}, "judges": judges}
                        for i, a in enumerate(agents)]
            (out / "comparison_report.json").write_text(json.dumps(
                {"scenario": {"scenario_id": out.name},
                 "comparison": {"rankings": rankings}}), encoding="utf-8")
            return 0, ""

        monkeypatch.setattr(llm, "evaluate", fake_evaluate)
        monkeypatch.setattr(llm, "load_credentials", lambda: None)
        return run_dir, llm, calls

    def test_it_judges_every_scenario_with_the_benchmarks_evaluator(self, judged):
        run_dir, llm, calls = judged
        assert llm.run(run_dirs=[str(run_dir)]) == 0
        assert len(calls) == len(SCENARIOS)
        for command in calls:
            assert command[1] == "compare"
            assert {"--no-run", "--use-llm", "--multi-judge"} <= set(command)
            # Only the agents that left an output; a failed one has nothing
            # to judge and is the failure policy's to count.
            assert command[command.index("--agents") + 1] == "alignmentgraph-isd"
            scenario = Path(command[command.index("--scenario") + 1])
            assert scenario.parent.name == "tiny_split"

    def test_it_files_each_evaluation_into_the_summary(self, judged):
        run_dir, llm, _ = judged
        llm.run(run_dirs=[str(run_dir)])
        results = json.loads((run_dir / "benchmark_summary.json").read_text(encoding="utf-8"))
        for record in results["scenarios"]["tiny_split"].values():
            assert "evaluation_deferred" not in record
            assert record["evaluation"]["comparison"]["rankings"]
        assert "Evaluation scores" in (run_dir / "SUMMARY.md").read_text(encoding="utf-8")

    def test_a_second_pass_judges_nothing_and_overwrite_judges_all(self, judged):
        run_dir, llm, calls = judged
        llm.run(run_dirs=[str(run_dir)])
        calls.clear()
        llm.run(run_dirs=[str(run_dir)])
        assert calls == []
        llm.run(run_dirs=[str(run_dir)], overwrite=True)
        assert len(calls) == len(SCENARIOS)

    def test_a_report_from_another_roster_is_judged_again(self, judged):
        """Kept, it would be pooled beside rows the declared roster scored."""
        run_dir, llm, calls = judged
        llm.run(run_dirs=[str(run_dir)])
        stale = run_dir / "tiny_split" / SCENARIOS[0] / "comparison_report.json"
        report = json.loads(stale.read_text(encoding="utf-8"))
        for row in report["comparison"]["rankings"]:
            row["judges"] = row["judges"][:-1]
        stale.write_text(json.dumps(report), encoding="utf-8")
        calls.clear()
        llm.run(run_dirs=[str(run_dir)])
        assert [Path(c[c.index("--output-dir") + 1]).name for c in calls] == [SCENARIOS[0]]

    def test_a_dry_run_spends_nothing(self, judged):
        run_dir, llm, calls = judged
        assert llm.run(run_dirs=[str(run_dir)], dry_run=True) == 0
        assert calls == []
        assert not list(run_dir.glob("*/*/comparison_report.json"))

    def test_the_post_run_audit_calls_it_unjudged_not_broken(self, world):
        from isd_experiments.audit.postrun import audit_run

        tmp_path, cfg, _ = world
        run_dir, _ = _generate(tmp_path, cfg)
        result = audit_run(run_dir, agents=["alignmentgraph-isd"], n_scenarios=2)
        assert not any("comparison_report" in r for r in result["red"]), result["red"]
        assert any("not judged yet" in i for i in result["info"])


def test_the_evaluators_progress_markers_become_log_lines():
    """One scenario is several LLM judge calls; the log shows each as it lands
    instead of staying silent until the scenario is done."""
    from isd_experiments.judge.llm import progress_line

    line = "__EVAL_PROGRESS__\t3\t4\talignmentgraph-isd\topenai/gpt-4o-mini\n"
    assert progress_line("S-001", line) == (
        "  [S-001] LLM judge call 3/4 -- alignmentgraph-isd / openai/gpt-4o-mini")
    assert progress_line("S-001", "[MultiJudge] Evaluating x...\n") is None


def test_the_evaluator_is_streamed_with_progress_on(tmp_path, capsys):
    """Run end to end on a stand-in evaluator: progress printed live, the rest
    kept for the error message, the exit code passed through."""
    import sys

    from isd_experiments.judge.llm import evaluate

    script = tmp_path / "fake_eval.py"
    script.write_text(
        "import os, sys\n"
        "assert os.environ.get('ISD_EVAL_PROGRESS') == '1'\n"
        "print('__EVAL_PROGRESS__\\t1\\t2\\tagent-a\\tjudge-x', flush=True)\n"
        "print('ordinary output')\n"
        "print('boom', file=sys.stderr)\n"
        "sys.exit(3)\n", encoding="utf-8")
    code, output = evaluate([sys.executable, str(script)], dict(os.environ), "S-9")
    assert code == 3
    assert "boom" in output
    assert "[S-9] LLM judge call 1/2 -- agent-a / judge-x" in capsys.readouterr().out

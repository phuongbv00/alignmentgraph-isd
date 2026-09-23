"""What each agent is handed, and how it is called.

The comparison holds one thing fixed across seven agents: what they are given.
Every agent is built from the SAME run config -- the uniform output budget and
this run's token counter -- and each baseline is constructed exactly as
ISD-Agent-Bench constructs it. These tests pin both halves, because a quietly
changed constructor argument changes a baseline, and nothing downstream (the
LLM judge, pooling, the tables) would notice.

No network: agents are replaced by recorders, or only constructed.
"""

from __future__ import annotations

import re

import pytest

from isd_experiments import paths
from isd_experiments.config import current
from isd_experiments.runner import agents as registry
from isd_experiments.runner import llm


def _run_config():
    from shared.llm import LLMConfig

    base = LLMConfig(model="test-model", base_url="http://localhost:9/v1",
                     api_key="dummy", allow_dummy_api_key=True)
    return llm.uniform_config(base)


class Recorder:
    """Stands in for an agent class and remembers how it was built."""

    calls: list[dict] = []

    def __init__(self, *args, **kwargs):
        Recorder.calls.append(kwargs)

    def run(self, scenario):
        return {"addie_output": {}, "trajectory": {}, "metadata": {}}

    def generate(self, scenario):
        return self.run(scenario)


@pytest.fixture(autouse=True)
def _reset():
    Recorder.calls = []


class TestTheUniformConfig:
    def test_every_run_gets_the_uniform_budget_and_its_own_counter(self, monkeypatch):
        monkeypatch.delenv("AGENT_MODEL_MAX_TOKENS", raising=False)
        from shared.llm import LLMConfig

        base = LLMConfig(model="m", base_url="http://localhost:9/v1", api_key="k")
        one, two = llm.uniform_config(base), llm.uniform_config(base)
        assert one.max_tokens == two.max_tokens == llm.UNIFORM_MAX_TOKENS
        assert one._token_counter is not two._token_counter, (
            "two runs sharing a counter would each report the other's tokens")

    def test_an_explicit_budget_is_equally_uniform(self, monkeypatch):
        from shared.llm import LLMConfig

        monkeypatch.setenv("AGENT_MODEL_MAX_TOKENS", "4000")
        base = LLMConfig(model="m", base_url="http://localhost:9/v1", api_key="k",
                         max_tokens=4000)
        assert llm.uniform_config(base).max_tokens == 4000

    def test_the_serving_limits_come_from_the_declaration(self):
        cfg = current()
        env = llm.serving_env(cfg)
        assert env["AGENT_MODEL_MAX_OUTPUT_TOKENS"] == str(cfg.serving.max_output_tokens)
        assert env["AGENT_MODEL_CONTEXT_WINDOW"] == str(cfg.serving.context_window)


class TestTheBaselinesAreBuiltAsTheBenchmarkBuildsThem:
    def test_baseline_is_handed_the_uniform_budget_explicitly(self, monkeypatch):
        """Its constructor default (32768) would otherwise override it."""
        import baseline.generator
        monkeypatch.setattr(baseline.generator, "BaselineGenerator", Recorder)
        config = _run_config()
        registry.build("baseline", config, current())({})
        assert Recorder.calls == [{"llm_config": config, "max_tokens": config.max_tokens}]

    def test_eduplanner_keeps_its_iteration_budget_and_target(self, monkeypatch):
        import eduplanner.agents
        import eduplanner.models.schemas

        class Result:
            class _D:
                def to_standard_dict(self):
                    return {}

                def model_dump(self):
                    return {}
            addie_output = trajectory = metadata = _D()

        class EduRecorder(Recorder):
            def run(self, scenario_input):
                return Result()

        monkeypatch.setattr(eduplanner.agents, "EduPlannerAgent", EduRecorder)
        monkeypatch.setattr(eduplanner.models.schemas, "ScenarioInput", lambda **kw: kw)
        config = _run_config()
        registry.build("eduplanner", config, current())({})
        (call,) = Recorder.calls
        assert call["max_iterations"] == 3 and call["target_score"] == 90.0
        assert call["config"].llm_config is config

    @pytest.mark.parametrize("agent_id, module, name", [
        ("react-isd", "react_isd.agent", "ReActISDAgent"),
        ("addie-agent", "addie_agent.agent", "ADDIEAgent"),
        ("dick-carey-agent", "dick_carey_agent.agent", "DickCareyAgent"),
        ("rpisd-agent", "rpisd_agent.agent", "RPISDAgent"),
    ])
    def test_the_rest_take_the_run_config_and_nothing_else(self, monkeypatch,
                                                           agent_id, module, name):
        import importlib
        monkeypatch.setattr(importlib.import_module(module), name, Recorder)
        config = _run_config()
        registry.build(agent_id, config, current())({})
        assert Recorder.calls == [{"llm_config": config}]


class TestTheProposedCells:
    def test_every_ablation_arm_runs_under_its_declared_axes(self, monkeypatch):
        from isd_experiments.runner.adapters import alignmentgraph_isd
        monkeypatch.setattr(alignmentgraph_isd, "AlignmentGraphISDAgent", Recorder)
        cfg = current()
        arms = cfg.profile("ablation").arms
        assert arms, "the ablation declares no arms"
        for arm in arms:
            Recorder.calls = []
            config = _run_config()
            registry.build(arm.id, config, cfg)({})
            (call,) = Recorder.calls
            assert call["llm_config"] is config
            assert {k: call[k] for k in ("agent_mode", "context_mode")} == arm.expected_flags

    def test_the_proposed_system_is_the_full_pipeline(self):
        assert registry.proposed_cells(current())[registry.PROPOSED] == {
            "agent_mode": "multi", "context_mode": "graph"}

    def test_every_rostered_agent_is_known(self):
        cfg = current()
        known = set(registry.known_agents(cfg))
        for profile in cfg.profiles.values():
            assert set(profile.agents) <= known, profile.name

    def test_an_unknown_agent_is_refused(self):
        with pytest.raises(SystemExit, match="Unknown agent"):
            registry.build("no-such-agent", _run_config(), current())


class TestTokenAccountingReachesEveryAgent:
    """Every agent's LLM calls must land in the counter the runner reads.

    ``execute.run_agent`` reads the run config's counter AFTER the agent
    returns, so whatever config an agent ends up building its models from must
    still carry it. The bug this guards was not in the lineage rule but in the
    agents: every baseline copies its config in ``__init__`` to pin a model or
    a temperature, and while a copy handed out a fresh counter their
    token_usage read 0 -- while the proposed system kept real numbers, a
    failure flattering the agent under study.
    """

    @staticmethod
    def _config_used(agent_id: str, config):
        if agent_id == "react-isd":
            from react_isd.agent import ReActISDAgent
            return ReActISDAgent(llm_config=config).llm_config
        if agent_id == "addie-agent":
            from addie_agent.agent import ADDIEAgent
            return ADDIEAgent(llm_config=config).llm_config
        if agent_id == "dick-carey-agent":
            from dick_carey_agent.agent import DickCareyAgent
            return DickCareyAgent(llm_config=config).llm_config
        if agent_id == "rpisd-agent":
            from rpisd_agent.agent import RPISDAgent
            return RPISDAgent(llm_config=config).llm_config
        if agent_id == "baseline":
            from baseline.generator import BaselineGenerator
            return BaselineGenerator(llm_config=config, max_tokens=config.max_tokens).llm_config
        if agent_id == "eduplanner":
            from eduplanner.agents.base import AgentConfig
            return AgentConfig(model=config.model, llm_config=config).to_llm_config()
        if agent_id == registry.PROPOSED:
            # A factory rather than a config: the config it builds models from
            # is whatever the closure captured.
            from shared.llm import LLMConfig

            from isd_experiments.runner.adapters.alignmentgraph_isd import (
                AlignmentGraphISDAgent,
            )
            factory = AlignmentGraphISDAgent(llm_config=config).config.llm_factory
            cells = [c.cell_contents for c in (factory.__closure__ or ())]
            return next(c for c in cells if isinstance(c, LLMConfig))
        raise AssertionError(f"unhandled agent id {agent_id}")

    @pytest.mark.parametrize("agent_id", registry.BASELINES + (registry.PROPOSED,))
    def test_agent_reports_into_the_runs_token_counter(self, agent_id):
        config = _run_config()
        try:
            used = self._config_used(agent_id, config)
        except ImportError as exc:
            pytest.skip(f"{agent_id} not importable: {exc}")
        assert used._token_counter is config._token_counter, (
            f"{agent_id} builds its models from a config detached from the run's "
            "token counter, so its token_usage will be 0 on every run.")


def test_the_launch_banner_sizes_slots_with_the_runners_presets():
    """`matrix_peak_calls` copies the preset table to print a bound; a drift
    misstates the number a reader sizes endpoints by."""
    script = (paths.exp_root() / "bin" / "_matrix.sh").read_text(encoding="utf-8")
    for name, preset in llm.RATE_PRESETS.items():
        m = re.search(rf"{name}\)\s+scen=(\d+);\s+agents=(\d+);", script)
        assert m, f"_matrix.sh has no row for {name}"
        assert (int(m.group(1)), int(m.group(2))) == (preset.scenarios, preset.agents), name


class TestJudgeArms:
    """`[alignment].judge_arms` decides what `run --with-judge` scores."""

    def _load(self, tmp_path, value):
        from isd_experiments.alignment.presets import _load
        from isd_experiments.config import load

        src = (paths.exp_root() / "experiment.toml").read_text(encoding="utf-8")
        line = 'judge_arms = "primary"'
        assert line in src
        path = tmp_path / "experiment.toml"
        path.write_text(src.replace(line, value), encoding="utf-8")
        return _load(load(path))

    def test_the_shipped_declaration_scores_the_primary(self):
        from isd_experiments.alignment.presets import current as arms
        assert arms().judge_arms == "primary"

    def test_absent_means_primary(self, tmp_path):
        assert self._load(tmp_path, "").judge_arms == "primary"

    def test_all_is_the_whole_star(self, tmp_path):
        from isd_experiments.runner import judge_arms_flags
        assert self._load(tmp_path, 'judge_arms = "all"').judge_arms == "all"
        assert judge_arms_flags("all") == {"all_arms": True}
        assert judge_arms_flags("primary") == {"all_arms": False}

    def test_anything_else_is_refused(self, tmp_path):
        with pytest.raises(SystemExit, match="judge_arms"):
            self._load(tmp_path, 'judge_arms = "some"')

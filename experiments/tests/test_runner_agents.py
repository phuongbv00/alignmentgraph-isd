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
        env = llm.pinned_env(cfg)
        assert env["AGENT_MODEL_MAX_OUTPUT_TOKENS"] == str(cfg.generation.max_output_tokens)
        assert env["AGENT_MODEL_CONTEXT_WINDOW"] == str(cfg.serving.context_window)

    def test_the_harness_posture_comes_from_the_declaration(self):
        cfg = current()
        env = llm.pinned_env(cfg)
        assert env["HARNESS_FANOUT_WORKERS"] == str(cfg.harness.fanout_workers)
        assert env["HARNESS_DEVELOPMENT_MODE"] == cfg.harness.development_mode


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

    @pytest.mark.parametrize(
        "agent_id", ["react-isd", "addie-agent", "dick-carey-agent", "rpisd-agent"])
    def test_two_concurrent_runs_of_a_tool_style_agent_keep_their_own_counters(
            self, agent_id):
        """The runner builds and runs each agent inside one pool worker, several
        at once. A tool-style agent finds its config through
        ``shared.llm.get_default_llm_config()`` at call time and fans out on its
        own pool, so that lookup has to be scoped to the run that constructed
        the agent, all the way into its fan-out threads -- or every concurrent
        run of these agents reports into whichever run configured last."""
        import threading

        from shared.llm import ContextThreadPoolExecutor, get_default_llm_config

        try:
            self._config_used(agent_id, _run_config())
        except ImportError as exc:
            pytest.skip(f"{agent_id} not importable: {exc}")

        barrier = threading.Barrier(2)
        seen: list[tuple] = []

        def one_run() -> None:
            config = _run_config()
            # Construct the agent the way `registry.build`'s closure does on
            # call, in this run's thread, without running it.
            self._config_used(agent_id, config)
            barrier.wait()
            with ContextThreadPoolExecutor(max_workers=1) as pool:
                counter = pool.submit(get_default_llm_config).result()._token_counter
            seen.append((config, counter))

        threads = [threading.Thread(target=one_run) for _ in range(2)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        assert len(seen) == 2
        for config, counter in seen:
            assert counter is config._token_counter, (
                f"a concurrent run of {agent_id} resolved the default config to "
                "another run's token counter")


def test_the_launch_banner_sizes_slots_with_the_runners_presets():
    """`matrix_peak_calls` copies the preset table to print a bound; a drift
    misstates the number a reader sizes endpoints by."""
    script = (paths.exp_root() / "bin" / "_matrix.sh").read_text(encoding="utf-8")
    for name, preset in llm.RATE_PRESETS.items():
        m = re.search(rf"{name}\)\s+scen=(\d+);\s+agents=(\d+);", script)
        assert m, f"_matrix.sh has no row for {name}"
        assert (int(m.group(1)), int(m.group(2))) == (preset.scenarios, preset.agents), name


class TestAlignmentArmSelection:
    """`judge alignment` scores the arms experiment.toml declares, unless told
    to narrow; `run --judge` scores the same set."""

    @staticmethod
    def _arms(**flags):
        from types import SimpleNamespace

        from isd_experiments.judge.alignment import resolve_arms
        base = dict(primary_only=False, all_encoders=False, encoder_presets="",
                    encoder_preset="", bloom_presets="", bloom_preset="")
        return resolve_arms(SimpleNamespace(**{**base, **flags}))

    def test_no_selection_is_every_declared_arm(self):
        from isd_experiments.alignment.presets import current as arms
        declared = arms()
        chosen = self._arms()
        assert chosen == declared.star()
        assert chosen[0] == (declared.primary_encoder, declared.primary_bloom)
        assert len(chosen) == len(declared.encoders) + len(declared.bloom) - 1

    def test_primary_only_is_the_primary_configuration(self):
        from isd_experiments.alignment.presets import current as arms
        declared = arms()
        assert self._arms(primary_only=True) == [
            (declared.primary_encoder, declared.primary_bloom)]

    def test_a_selection_narrows_to_one_axis(self):
        from isd_experiments.alignment.presets import current as arms
        declared = arms()
        other = next(k for k in declared.bloom if k != declared.primary_bloom)
        assert self._arms(bloom_presets=other) == [(declared.primary_encoder, other)]

    def test_deviating_on_both_axes_is_refused(self):
        from isd_experiments.alignment.presets import current as arms
        declared = arms()
        enc = next(k for k in declared.encoders if k != declared.primary_encoder)
        bloom = next(k for k in declared.bloom if k != declared.primary_bloom)
        with pytest.raises(SystemExit, match="both axes"):
            self._arms(encoder_presets=enc, bloom_presets=bloom)

    def test_a_chained_judge_never_waits_on_a_prompt(self, monkeypatch, tmp_path):
        """A launched run sits in tmux, which is a terminal: the overwrite
        prompt would wait there for nobody."""
        from isd_experiments import runner
        from isd_experiments.judge import alignment

        seen = {}
        monkeypatch.setattr(alignment, "run", lambda **kw: seen.update(kw) or 0)
        assert runner._judge_alignment(tmp_path) == 0
        assert seen["yes"] is True
        assert "primary_only" not in seen, "the chained judge must score every arm"


class TestTheDeclaredTemperature:
    """`[generation].temperature` is the temperature of the config every agent
    is handed, whatever the environment says. An agent that pins its own keeps
    it -- that is the agent as the benchmark ships it."""

    def test_the_slot_config_carries_the_declared_value(self, monkeypatch):
        monkeypatch.setenv("AGENT_MODEL_TEMPERATURE", "1.9")
        cfg = current()
        model = cfg.by_slot(cfg.profile("tune").slots[0])
        assert llm.slot_config(cfg, model).temperature == cfg.generation.temperature

    def test_it_is_pinned_into_the_environment_too(self):
        cfg = current()
        assert llm.pinned_env(cfg)["AGENT_MODEL_TEMPERATURE"] == str(cfg.generation.temperature)

    def test_every_generation_field_is_published_for_the_plan_and_the_manifest(self):
        """A field the TOML declares must reach what records the run."""
        import dataclasses

        from isd_experiments.config import Generation
        from isd_experiments.launch import profile_env

        emitted = set(profile_env(current().profile("tune")))
        for field in dataclasses.fields(Generation):
            assert f"_AGENT_MODEL_{field.name.upper()}" in emitted, field.name

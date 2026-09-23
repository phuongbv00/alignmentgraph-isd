"""Agent id -> how that agent is built and called.

Six of the agents are ISD-Agent-Bench's own baselines, and how each is
constructed is part of what the comparison holds fixed: EduPlanner's iteration
count and target score, the Baseline's explicit output budget (its constructor
default would otherwise override the uniform one). Those calls are the
benchmark's, kept as the benchmark made them; `tests/test_runner_agents.py`
pins them, because a quietly changed argument here changes a baseline and
nothing downstream would notice.

The proposed system and its ablation cells are one adapter with two axes pinned
per id. The cells are read from ``[[experiment.ablation.arms]]`` rather than
named here, so the id that runs a cell and the id pooling checks its flags
against are one declaration.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from ..config import Experiment

Runner = Callable[[dict], dict]

#: The benchmark's own agents, in its default roster order.
BASELINES = ("eduplanner", "baseline", "react-isd", "addie-agent",
             "dick-carey-agent", "rpisd-agent")

#: The proposed system: the full pipeline, multi-agent over the AlignmentGraph.
PROPOSED = "alignmentgraph-isd"
PROPOSED_AXES = {"agent_mode": "multi", "context_mode": "graph"}


def proposed_cells(cfg: Experiment) -> dict[str, dict[str, str]]:
    """Every id the adapter answers to, with the axes it runs under."""
    cells = {PROPOSED: dict(PROPOSED_AXES)}
    for profile in cfg.profiles.values():
        for arm in profile.arms:
            axes = arm.expected_flags
            if cells.setdefault(arm.id, axes) != axes:
                raise SystemExit(
                    f"{cfg.source}: arm {arm.id!r} is declared with two different "
                    f"axis settings ({cells[arm.id]} and {axes})."
                )
    return cells


def known_agents(cfg: Experiment) -> tuple[str, ...]:
    return BASELINES + tuple(proposed_cells(cfg))


def build(agent_id: str, llm_config: Any, cfg: Experiment) -> Runner:
    """A ``run(scenario) -> dict`` for one agent, bound to one run's config.

    ``llm_config`` is already the run's (``runner.llm.uniform_config``): its
    ``max_tokens`` is the uniform budget and it carries this run's token
    counter. Every branch hands it on unchanged.
    """
    uniform_max_tokens = llm_config.max_tokens

    if agent_id == "baseline":
        from baseline.generator import BaselineGenerator

        def run_baseline(scenario: dict) -> dict:
            # Explicit: the constructor's own default (32768) would otherwise
            # override the uniform budget on the config.
            gen = BaselineGenerator(llm_config=llm_config, max_tokens=uniform_max_tokens)
            return gen.generate(scenario)
        return run_baseline

    if agent_id == "eduplanner":
        from eduplanner.agents import EduPlannerAgent
        from eduplanner.agents.base import AgentConfig
        from eduplanner.models.schemas import ScenarioInput

        def run_eduplanner(scenario: dict) -> dict:
            config = AgentConfig(model=llm_config.model, llm_config=llm_config)
            agent = EduPlannerAgent(config=config, max_iterations=3, target_score=90.0)
            result = agent.run(ScenarioInput(**scenario))
            return {
                "addie_output": result.addie_output.to_standard_dict(),
                "trajectory": result.trajectory.model_dump(),
                "metadata": result.metadata.model_dump(),
            }
        return run_eduplanner

    if agent_id == "react-isd":
        from react_isd.agent import ReActISDAgent
        return lambda scenario: ReActISDAgent(llm_config=llm_config).run(scenario)

    if agent_id == "addie-agent":
        from addie_agent.agent import ADDIEAgent
        return lambda scenario: ADDIEAgent(llm_config=llm_config).run(scenario)

    if agent_id == "dick-carey-agent":
        from dick_carey_agent.agent import DickCareyAgent
        return lambda scenario: DickCareyAgent(llm_config=llm_config).run(scenario)

    if agent_id == "rpisd-agent":
        from rpisd_agent.agent import RPISDAgent
        return lambda scenario: RPISDAgent(llm_config=llm_config).run(scenario)

    cells = proposed_cells(cfg)
    if agent_id in cells:
        from .adapters.alignmentgraph_isd import AlignmentGraphISDAgent
        axes = cells[agent_id]
        return lambda scenario: AlignmentGraphISDAgent(
            llm_config=llm_config, **axes).run(scenario)

    raise SystemExit(
        f"Unknown agent {agent_id!r}. Known: {', '.join(known_agents(cfg))}"
    )

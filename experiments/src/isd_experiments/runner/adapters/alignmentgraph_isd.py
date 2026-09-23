"""The proposed system, as one agent of the runner.

The runner speaks the benchmark's vocabulary -- a *scenario*, an ``LLMConfig``,
a rate preset -- and ``alignmentgraph_isd`` speaks its own: a *design brief*,
a chat-model factory, a ``HarnessRunConfig``. This module is the one place the
two meet. Every other agent of the comparison is the benchmark's own, reached
through ``runner.agents``; this one is the thesis contribution, so its adapter
lives with the experiment rather than inside the benchmark.
"""
from __future__ import annotations

import os
from typing import Any

from alignmentgraph_isd import DesignBrief, MetaAgent
from alignmentgraph_isd.config import ChatModelFactory, HarnessRunConfig

#: In-flight LLM requests this agent allows itself, per rate preset.
#:
#: The runner's rate preset bounds how many AGENTS run at once, which is
#: all an orchestrator can bound. This agent's own topology fans out — the multi
#: arm runs content_designer and rubric_designer in the SAME superstep and each
#: issues one Developer call per work set, peaking at ~12 concurrent requests
#: from a single run — so it has to bound itself, and this table is where it
#: translates the runner's posture into its own limit. Owning the mapping here
#: keeps the runner free of any agent's internal knobs: it publishes
#: ``BENCHMARK_RATE_LIMIT`` and nothing more.
#:
#: A shared endpoint answered the unbounded overflow with HTTP 429 on the two
#: multi arms only (9-25 per run over three runs, against 0-2 on the sequential
#: single arms), so the throttling sat on the ``agent_mode`` ablation axis.
LLM_CONCURRENCY_BY_RATE_LIMIT = {
    "conservative": 2,
    "moderate": 3,
    "aggressive": 4,
    "turbo": 6,
}
#: Used when no preset is named (direct package use). Parallel enough to keep
#: the fan-out meaningful, well inside a typical per-user concurrency cap.
DEFAULT_LLM_MAX_CONCURRENCY = 4


def _llm_concurrency_from_env() -> int:
    """Requests this run may keep in flight: the explicit override if set,
    otherwise whatever the runner's rate preset implies."""
    override = os.getenv("HARNESS_LLM_MAX_CONCURRENCY")
    if override is not None:
        try:
            return max(0, int(override))
        except ValueError:
            pass
    preset = (os.getenv("BENCHMARK_RATE_LIMIT") or "").strip().lower()
    return LLM_CONCURRENCY_BY_RATE_LIMIT.get(preset, DEFAULT_LLM_MAX_CONCURRENCY)


def _regen_settings_from_env() -> dict[str, Any]:
    """Rate-limit posture for the package, sourced from the runner's environment.

    The regen backoff defaults to the runner's own rate knob
    (``BENCHMARK_DELAY``, set by the rate preset) so per-agent re-runs respect
    the same concurrency posture as the outer scheduler; a 429 window then gets a
    chance to drain rather than being hammered by immediate retries.
    ``HARNESS_REGEN_BACKOFF`` overrides the delay, ``HARNESS_REGEN_BUDGET`` the
    number of extra attempts.

    The call-gate cap comes from ``BENCHMARK_RATE_LIMIT`` via
    :data:`LLM_CONCURRENCY_BY_RATE_LIMIT`; ``HARNESS_LLM_MAX_CONCURRENCY``
    overrides it (0 opts out). The outer scheduler only ever counted a whole
    agent as one unit, so without this the in-agent fan-out was outside the rate
    posture entirely. ``HARNESS_LLM_MIN_INTERVAL`` additionally spaces call
    starts, for an endpoint that meters rate rather than concurrency."""
    settings: dict[str, Any] = {
        "llm_max_concurrency": _llm_concurrency_from_env(),
    }
    # ``HARNESS_FANOUT_WORKERS`` runs the multi arm's Developers at once (the
    # harness caps it by the call gate above and commits in plan order); unset
    # keeps the package default of 1, the sequential fan-out the ladder ran.
    # A malformed value RAISES rather than falling back: the launcher publishes
    # it from experiment.toml and the freeze manifest records it, so a value
    # silently ignored here would be a posture written down that never ran.
    workers = os.getenv("HARNESS_FANOUT_WORKERS")
    if workers:
        try:
            count = int(workers)
        except ValueError:
            count = 0
        if count < 1:
            raise ValueError(
                f"HARNESS_FANOUT_WORKERS must be a positive integer, got {workers!r}")
        settings["fanout_workers"] = count
    # ``HARNESS_DEVELOPMENT_MODE`` is ``light`` (a typical, reviewable slice of
    # what the design plans) or ``full`` (everything); unset keeps the package
    # default. An env knob and not a per-arm kwarg: it is not an ablation
    # axis, so every arm of one experiment must share it, and one variable is
    # how they do. A malformed value RAISES, as ``HARNESS_FANOUT_WORKERS``
    # does: experiment.toml declares it and the freeze manifest records it, so
    # a value silently ignored here would be a posture written down that
    # never ran.
    raw_mode = os.getenv("HARNESS_DEVELOPMENT_MODE")
    if raw_mode:
        mode = raw_mode.strip().lower()
        if mode not in ("light", "full"):
            raise ValueError(
                f"HARNESS_DEVELOPMENT_MODE must be 'light' or 'full', got {raw_mode!r}")
        settings["development_mode"] = mode
    interval = os.getenv("HARNESS_LLM_MIN_INTERVAL")
    if interval is not None:
        try:
            settings["llm_min_interval_seconds"] = max(0.0, float(interval))
        except ValueError:
            pass
    backoff = os.getenv("HARNESS_REGEN_BACKOFF") or os.getenv("BENCHMARK_DELAY")
    if backoff is not None:
        try:
            settings["regen_backoff_seconds"] = float(backoff)
        except ValueError:
            pass
    budget = os.getenv("HARNESS_REGEN_BUDGET")
    if budget is not None:
        try:
            settings["regen_budget"] = int(budget)
        except ValueError:
            pass
    # The transcript budget is derived from the SERVING window rather than a
    # constant. ``AGENT_MODEL_CONTEXT_WINDOW`` is the window the pods were
    # launched with (the ladder runs 16384); left unset, the harness keeps its
    # historical 24,000-character default and nothing changes.
    #
    # The reserve is what must be left for the answer, so it reads the same
    # ``AGENT_MODEL_MAX_OUTPUT_TOKENS`` the runner applies uniformly to every
    # agent: a prompt that eats into the completion allowance makes the
    # generation fail, which is a far worse failure than trimming history.
    for env_name, key in (("AGENT_MODEL_CONTEXT_WINDOW", "llm_context_window"),
                          ("AGENT_MODEL_MAX_OUTPUT_TOKENS", "llm_completion_reserve")):
        raw = os.getenv(env_name)
        if raw is None:
            continue
        try:
            settings[key] = int(raw)
        except ValueError:
            pass
    return settings


def _llm_factory_from_config(llm_config: Any) -> ChatModelFactory | None:
    if llm_config is None:
        return None

    # Only supply a default when the caller set nothing; never override an
    # explicit budget. The runner normalizes max_tokens uniformly across all
    # agents (see runner.llm.uniform_config), so overriding here
    # would reintroduce the very asymmetry that normalization removes.
    if getattr(llm_config, "max_tokens", None) is None:
        llm_config = llm_config.copy_with(max_tokens=16384)

    def factory() -> Any:
        from shared.llm import create_chat_model

        return create_chat_model(llm_config)

    return factory


def _scenario_to_design_brief(scenario: dict | DesignBrief) -> DesignBrief:
    """Bridge the benchmark's "scenario" vocabulary to the package's design brief contract.

    The benchmark's ``scenario_id`` becomes the design brief ``id``. All other
    fields share the same names, so this is the one place the two vocabularies meet.
    """
    if isinstance(scenario, DesignBrief):
        return scenario
    data = dict(scenario)
    if "id" not in data and "scenario_id" in data:
        data["id"] = data["scenario_id"]
    return DesignBrief(**data)


class AlignmentGraphISDAgent:
    def __init__(
        self,
        llm_config=None,
        llm_factory: ChatModelFactory | None = None,
        *,
        agent_mode: str = "multi",
        context_mode: str = "graph",
    ) -> None:
        # The factory is the single source of truth for the model; the harness
        # reads model provenance for its metadata by introspecting it (no parallel
        # LLMConfig to keep in sync).
        #
        # The ablation axes are kwargs (not env vars) on purpose: the runner's
        # registry pins them per agent_id (alignmentgraph-isd-single-prose etc.),
        # so an arm can never run with the wrong config because of a missing
        # export. Defaults = the full multi-agent, graph-context pipeline.
        # There is one executor (native tool-calling act->observe loops per
        # stage), so nothing selects it.
        self.config = HarnessRunConfig(
            llm_factory=llm_factory or _llm_factory_from_config(llm_config),
            agent_mode=agent_mode,
            context_mode=context_mode,
            **_regen_settings_from_env(),
        )

    def run(self, scenario: dict | DesignBrief) -> dict:
        return MetaAgent(self.config).run(_scenario_to_design_brief(scenario))

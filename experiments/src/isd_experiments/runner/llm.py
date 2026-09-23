"""What every agent of one run is handed: one model config and one posture.

Fairness across the comparison rests on this module. Every agent -- the six
baselines and the proposed system alike -- is built from the SAME ``LLMConfig``
for a rung, under the same serving limits and the same rate posture, so a
difference between two agents is a difference between the agents and never
between what they were given. Nothing here is per agent.

Everything is read from the declaration (experiment.toml). The one other input
is ``.env``, which carries credentials only; `audit preflight` fails if it
carries an endpoint or a serving limit, and the serving values below are
applied OVER it so a stale line there cannot take them back.
"""

from __future__ import annotations

import os
from dataclasses import dataclass

from .. import paths
from ..config import Experiment, Model

#: The per-call output budget every agent is given, unless ``.env`` states one
#: (``AGENT_MODEL_MAX_TOKENS``), which is then equally uniform. The ceiling
#: (``[generation].max_output_tokens``) is applied on top of it by the model
#: factory as min(this, the ceiling).
UNIFORM_MAX_TOKENS = 16384


@dataclass(frozen=True)
class RatePreset:
    """How much of one run is in flight at once."""

    #: Agents of one scenario running at the same time.
    agents: int
    #: Scenarios running at the same time.
    scenarios: int
    #: Seconds between two submissions, and between two scenarios.
    delay: float


#: The benchmark's rate presets, kept to its numbers so that a posture means
#: what it meant when the benchmark ran it. `bin/_matrix.sh::matrix_peak_calls`
#: prints a bound derived from the same table.
RATE_PRESETS = {
    "conservative": RatePreset(agents=2, scenarios=2, delay=2.0),
    "moderate": RatePreset(agents=3, scenarios=4, delay=0.5),
    "aggressive": RatePreset(agents=7, scenarios=8, delay=0.1),
    "turbo": RatePreset(agents=10, scenarios=15, delay=0.0),
}


def rate_preset(name: str) -> RatePreset:
    try:
        return RATE_PRESETS[name]
    except KeyError:
        raise SystemExit(
            f"Unknown rate preset {name!r}; choose from {', '.join(RATE_PRESETS)}"
        ) from None


def pinned_env(cfg: Experiment) -> dict[str, str]:
    """The window, the generation settings and the harness posture, as the
    variables they are read under.

    ``shared/llm`` reads the generation settings for every agent, and the
    proposed system's adapter reads the window, the ceiling and the worker
    count. Only what the declaration states is emitted: an absent value keeps
    the reader's own default rather than a number this module made up.
    """
    gen, env = cfg.generation, {}
    if cfg.serving.context_window is not None:
        env["AGENT_MODEL_CONTEXT_WINDOW"] = str(cfg.serving.context_window)
    if gen.max_output_tokens is not None:
        env["AGENT_MODEL_MAX_OUTPUT_TOKENS"] = str(gen.max_output_tokens)
    if gen.streaming is not None:
        # "0" rather than nothing: it has to be able to turn streaming OFF.
        env["AGENT_MODEL_STREAMING"] = "1" if gen.streaming else "0"
    if gen.thinking_budget is not None:
        env["AGENT_MODEL_THINKING_BUDGET"] = str(gen.thinking_budget)
    if gen.temperature is not None:
        env["AGENT_MODEL_TEMPERATURE"] = str(gen.temperature)
    if cfg.harness.fanout_workers is not None:
        env["HARNESS_FANOUT_WORKERS"] = str(cfg.harness.fanout_workers)
    return env


def rate_env(name: str) -> dict[str, str]:
    """The posture, published for an agent that has to bound its own fan-out."""
    return {"BENCHMARK_RATE_LIMIT": name,
            "BENCHMARK_DELAY": str(rate_preset(name).delay)}


def load_credentials() -> None:
    """``.env`` into the environment, never over a value already set there."""
    try:
        from dotenv import load_dotenv
    except ImportError:                                   # pragma: no cover
        return
    load_dotenv(paths.env_file(), override=False)


def pin_posture(cfg: Experiment, rate_limit: str) -> None:
    """The declared window, generation settings and rate posture, OVER whatever
    ``.env`` or the shell carried.

    Once per process, before any agent is built: the model factory and the
    adapter read these from ``os.environ`` at call time.
    """
    os.environ.update(pinned_env(cfg))
    os.environ.update(rate_env(rate_limit))


def slot_config(cfg: Experiment, model: Model):
    """The ``LLMConfig`` one rung is served under, before any agent sees it.

    The endpoints travel as one comma-joined value, which the config splits and
    round-robins across; the key variables likewise. The temperature is passed
    explicitly, so it is the declared one whatever the environment says.
    """
    from shared.llm import llm_config_from_env

    return llm_config_from_env(
        api_spec=cfg.api_spec_for(model),
        base_url=",".join(model.base_urls) or None,
        model=model.model,
        api_key_envs=tuple(
            name.strip() for name in cfg.key_env_for(model).split(",") if name.strip()
        ),
        temperature=cfg.generation.temperature,
    )


def uniform_config(llm_config):
    """One run's config: the uniform output budget, then a fresh token scope.

    The scope is opened here and nowhere else. The counter follows the config
    lineage (``copy_with`` re-shares it), so an agent that copies its config to
    pin a model or a temperature still reports into the tally the runner reads
    after the agent returns.
    """
    if not os.getenv("AGENT_MODEL_MAX_TOKENS"):
        llm_config = llm_config.copy_with(max_tokens=UNIFORM_MAX_TOKENS)
    return llm_config.new_token_scope()


def model_dir_label(model_id: str) -> str:
    """The model's part of a run-dir name: the org prefix dropped, ':' -> '-'.

    `config.Experiment.slot_of_label` reverses exactly this spelling.
    """
    return model_id.split("/")[-1].replace(":", "-")

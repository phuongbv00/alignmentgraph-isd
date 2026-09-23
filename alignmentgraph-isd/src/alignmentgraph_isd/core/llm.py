"""Standalone chat-model factory for the CLI and app integrations.

The core harness never constructs an LLM itself — it only consumes an injected
``llm_factory`` (see ``HarnessRunConfig.llm_factory``). Benchmark integrations
supply that factory from ``shared.llm``. This module gives the *standalone* paths
(the CLI, scripts, the demo app) a way to build the same kind of factory from
CLI flags / environment variables **without** depending on the benchmark.

The provider client libraries (``langchain-openai`` / ``langchain-anthropic``)
are optional extras, imported lazily so the core package keeps a light dependency
footprint. Install them with ``pip install 'alignmentgraph-isd[llm]'``.
"""
from __future__ import annotations

import os
from typing import Any

from ..config import ChatModelFactory


def _env(*names: str) -> str:
    for name in names:
        value = os.environ.get(name)
        if value:
            return value
    return ""


#: How long ONE model call may take before it is abandoned, in seconds.
#:
#: There was no timeout anywhere: a request that stalled stalled the run, and
#: the only way out was for someone to press cancel. MEASURED (run d3f566aa):
#: a compaction started at 743 s and had returned nothing 273 s later when the
#: run was cancelled by hand; a whole design was lost to one request that
#: never came back.
#:
#: 240 s is read off what a call can legitimately need rather than off the
#: provider's behaviour. The completion cap is 8,192 tokens, and the slowest
#: HEALTHY throughput measured across these runs is about 40 tokens/s, so
#: 8,192 tokens is roughly 205 s; below that rate the backend is degraded, not
#: busy. The two calls that ever exceeded this were folds that ran 221 s and
#: 244 s and BOTH returned "error", so cutting them loses nothing that worked.
#:
#: A timeout surfaces as an ordinary model error, which every loop already
#: handles as a spent turn — nothing new has to decide what to do about it.
DEFAULT_TIMEOUT_SECONDS = 240.0


def thinking_extra_body(budget: int | None) -> dict[str, Any]:
    """The request fields that hold a reply's reasoning to ``budget`` tokens.

    ``None`` leaves the server's own posture alone. ``0`` turns thinking off.
    A positive number caps the reasoning and lets the answer through.

    Why a CAP rather than an off switch: reasoning shares one completion budget
    with the answer, so a reply that reasons past the cap never closes
    ``</think>``, the reasoning parser classifies the whole output as reasoning,
    and the call is charged in full and comes back with no content. A budget
    forces the block closed, so there is always an answer — without taking the
    model's reasoning away. MEASURED (run 91983c9d): three calls spent all
    8,192 completion tokens that way, returned nothing, and were logged
    `invalid_action` — 182 s, 34% of that run's model time.

    Both spellings go out together, because the two kinds of backend read
    different ones and each ignores the other's: a self-hosted vLLM reads
    `thinking_token_budget` (a `SamplingParams` field) and `chat_template_kwargs`,
    an aggregating router reads `reasoning`. One payload for every endpoint is
    what keeps the posture uniform, which is what a comparison across endpoints
    rests on.

    WHAT A ROUTER CAN AND CANNOT DO, measured (2026-09-23, `qwen/qwen3.5-9b`
    through a router, one question, max_tokens 300): `thinking_token_budget`
    and `chat_template_kwargs` were ignored outright, 300 completion tokens and
    empty content. `reasoning.enabled: false` was honoured every time — 4 to 5
    tokens, an answer. `reasoning.max_tokens: 64` was honoured by one upstream
    provider (68 tokens, an answer) and ignored by another (300 tokens, empty),
    the router choosing per request. So a router enforces the OFF state and NOT
    a ceiling. A ceiling needs an endpoint that is served, not routed.

    TOOL CALLING IS UNAFFECTED: the reasoning parser and the tool-call parser
    are separate, and a bounded reasoning block simply ends sooner.

    The twin of this table is ``shared/llm/factory.py::_thinking_extra_body``
    in the benchmark, which serves the other six agents. It cannot be shared —
    ``shared/`` must not depend on any one agent — so each side pins the exact
    payload in a test and a drift shows up as a diff.
    """
    if budget is None:
        return {}
    if budget <= 0:
        return {"chat_template_kwargs": {"enable_thinking": False},
                "reasoning": {"enabled": False}}
    return {"thinking_token_budget": budget, "reasoning": {"max_tokens": budget}}


def llm_factory_from_env(
    *,
    model_name: str = "",
    api_spec: str = "",
    base_url: str = "",
    api_key: str = "",
    temperature: float | None = None,
    max_tokens: int | None = None,
    timeout: float | None = None,
    thinking_budget: int | None = None,
    http_client: Any = None,
    read_env: bool = True,
) -> ChatModelFactory | None:
    """Build a chat-model factory from explicit args, falling back to env vars.

    Resolution order for each setting is: explicit argument > environment
    variable > default. Environment variable names mirror the benchmark
    (``AGENT_MODEL_*``) so configuration is consistent across the repo.

    Pass ``read_env=False`` to switch the environment out of that order
    entirely, leaving explicit argument > default. The app configures its model
    in its own database and needs a value it did not set to stay unset: with
    the fallback in place, a connection saved with no key silently borrows
    ``AGENT_MODEL_API_KEY`` from the shell, and what the UI shows stops being
    what the run uses.

    Returns ``None`` when no model name can be resolved, so callers can keep
    their existing "llm_factory not configured" error path.

    ``http_client`` lets a caller supply its own ``httpx.Client`` (OpenAI-
    compatible endpoints only; ChatAnthropic does not accept one). The reason it
    exists is cancellation: ``invoke`` blocks a whole thread, and Python cannot
    interrupt a thread sitting in a socket read, so the only way to stop a call
    in flight is for the caller to close the transport underneath it. Nothing
    here closes it — that is the caller's business, and the caller's to clean up.
    """
    def env(*names: str) -> str:
        return _env(*names) if read_env else ""

    model = model_name or env("AGENT_MODEL_NAME")
    if not model:
        return None

    spec = (api_spec or env("AGENT_MODEL_API_SPEC") or "openai_compatible").lower()
    resolved_base_url = base_url or env("AGENT_MODEL_BASE_URL")
    resolved_api_key = api_key or env("AGENT_MODEL_API_KEY")

    if temperature is None:
        env_temperature = env("AGENT_MODEL_TEMPERATURE")
        temperature = float(env_temperature) if env_temperature else 0.0
    if max_tokens is None:
        env_max_tokens = env("AGENT_MODEL_MAX_TOKENS")
        max_tokens = int(env_max_tokens) if env_max_tokens else 4096
    if timeout is None:
        env_timeout = env("AGENT_MODEL_TIMEOUT_SECONDS")
        timeout = float(env_timeout) if env_timeout else DEFAULT_TIMEOUT_SECONDS
    if thinking_budget is None:
        env_budget = env("AGENT_MODEL_THINKING_BUDGET")
        if env_budget:
            try:
                thinking_budget = max(0, int(env_budget))
            except ValueError:
                pass

    def factory() -> Any:
        kwargs: dict[str, Any] = {
            "model": model,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        if timeout and timeout > 0:
            kwargs["timeout"] = timeout
        extra_body = thinking_extra_body(thinking_budget)
        if extra_body:
            kwargs["extra_body"] = extra_body
        if resolved_api_key:
            kwargs["api_key"] = resolved_api_key

        if spec == "anthropic":
            try:
                from langchain_anthropic import ChatAnthropic
            except ImportError as exc:  # pragma: no cover - exercised via clear message
                raise RuntimeError(
                    "api_spec='anthropic' requires langchain-anthropic. "
                    "Install it with: pip install 'alignmentgraph-isd[llm]'"
                ) from exc
            return ChatAnthropic(**kwargs)

        if spec in ("openai", "openai_compatible"):
            try:
                from langchain_openai import ChatOpenAI
            except ImportError as exc:  # pragma: no cover - exercised via clear message
                raise RuntimeError(
                    "api_spec='openai_compatible' requires langchain-openai. "
                    "Install it with: pip install 'alignmentgraph-isd[llm]'"
                ) from exc
            if resolved_base_url:
                kwargs["base_url"] = resolved_base_url
            if http_client is not None:
                kwargs["http_client"] = http_client
            return ChatOpenAI(**kwargs)

        raise ValueError(
            f"Unsupported api_spec: {spec!r}. Use 'openai_compatible' or 'anthropic'."
        )

    return factory

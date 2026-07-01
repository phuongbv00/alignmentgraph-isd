"""Standalone chat-model factory for the CLI and app integrations.

The core harness never constructs an LLM itself — it only consumes an injected
``llm_factory`` (see ``HarnessRunConfig.llm_factory``). Benchmark integrations
supply that factory from ``shared.llm``. This module gives the *standalone* paths
(the CLI, scripts, the planned app) a way to build the same kind of factory from
CLI flags / environment variables **without** depending on the benchmark.

The provider client libraries (``langchain-openai`` / ``langchain-anthropic``)
are optional extras, imported lazily so the core package keeps a light dependency
footprint. Install them with ``pip install 'alignmentgraph-isd[llm]'``.
"""
from __future__ import annotations

import os
from typing import Any

from .config import ChatModelFactory


def _env(*names: str) -> str:
    for name in names:
        value = os.environ.get(name)
        if value:
            return value
    return ""


def llm_factory_from_env(
    *,
    model_name: str = "",
    api_spec: str = "",
    base_url: str = "",
    api_key: str = "",
    temperature: float | None = None,
    max_tokens: int | None = None,
) -> ChatModelFactory | None:
    """Build a chat-model factory from explicit args, falling back to env vars.

    Resolution order for each setting is: explicit argument > environment
    variable > default. Environment variable names mirror the benchmark
    (``AGENT_MODEL_*``) so configuration is consistent across the repo.

    Returns ``None`` when no model name can be resolved, so callers can keep
    their existing "llm_factory not configured" error path.
    """
    model = model_name or _env("AGENT_MODEL_NAME")
    if not model:
        return None

    spec = (api_spec or _env("AGENT_MODEL_API_SPEC") or "openai_compatible").lower()
    resolved_base_url = base_url or _env("AGENT_MODEL_BASE_URL")
    resolved_api_key = api_key or _env("AGENT_MODEL_API_KEY")

    if temperature is None:
        env_temperature = _env("AGENT_MODEL_TEMPERATURE")
        temperature = float(env_temperature) if env_temperature else 0.0
    if max_tokens is None:
        env_max_tokens = _env("AGENT_MODEL_MAX_TOKENS")
        max_tokens = int(env_max_tokens) if env_max_tokens else 4096

    def factory() -> Any:
        kwargs: dict[str, Any] = {
            "model": model,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
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
            return ChatOpenAI(**kwargs)

        raise ValueError(
            f"Unsupported api_spec: {spec!r}. Use 'openai_compatible' or 'anthropic'."
        )

    return factory

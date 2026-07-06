"""Self-contained LLM plumbing for the baseline clone.

This module replaces the benchmark's ``shared.llm`` so the clone has no
dependency on the isd-agent-benchmark repo. It reads the same ``AGENT_MODEL_*``
environment contract used across the thesis experiments, and adds the token
accounting the original agent lacks (its ``metadata.total_tokens`` is hardcoded
to 0): every ``invoke`` goes through :class:`TrackedChatModel`, which
accumulates ``usage_metadata`` into a thread-safe :class:`UsageTracker`.
"""
from __future__ import annotations

import os
import threading
from dataclasses import dataclass, replace


@dataclass(frozen=True)
class LLMSettings:
    model_name: str = ""
    api_spec: str = "openai_compatible"  # or "anthropic"
    base_url: str = ""
    api_key: str = ""
    temperature: float = 0.7
    max_tokens: int = 8192

    def with_max_tokens(self, max_tokens: int) -> "LLMSettings":
        return replace(self, max_tokens=max_tokens)


def settings_from_env(**overrides) -> LLMSettings:
    values = {
        "model_name": os.environ.get("AGENT_MODEL_NAME", ""),
        "api_spec": os.environ.get("AGENT_MODEL_API_SPEC", "openai_compatible"),
        "base_url": os.environ.get("AGENT_MODEL_BASE_URL", ""),
        "api_key": os.environ.get("AGENT_MODEL_API_KEY", ""),
        "temperature": float(os.environ.get("AGENT_MODEL_TEMPERATURE", "0.7")),
        "max_tokens": int(os.environ.get("AGENT_MODEL_MAX_TOKENS", "8192")),
    }
    for key, value in overrides.items():
        if value not in (None, ""):
            values[key] = value
    return LLMSettings(**values)


class UsageTracker:
    """Thread-safe accumulator for LLM usage across a run."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self.prompt_tokens = 0
        self.completion_tokens = 0
        self.llm_calls = 0

    def record(self, usage_metadata: dict | None) -> None:
        with self._lock:
            self.llm_calls += 1
            if usage_metadata:
                self.prompt_tokens += usage_metadata.get("input_tokens", 0) or 0
                self.completion_tokens += usage_metadata.get("output_tokens", 0) or 0

    def snapshot(self) -> dict:
        with self._lock:
            return {
                "prompt_tokens": self.prompt_tokens,
                "completion_tokens": self.completion_tokens,
                "total_tokens": self.prompt_tokens + self.completion_tokens,
                "llm_calls": self.llm_calls,
            }

    def delta_since(self, before: dict) -> dict:
        now = self.snapshot()
        return {key: now[key] - before.get(key, 0) for key in now}


class TrackedChatModel:
    """Wraps a LangChain chat model and records usage on every invoke."""

    def __init__(self, inner, tracker: UsageTracker) -> None:
        self._inner = inner
        self._tracker = tracker

    def invoke(self, prompt):
        response = self._inner.invoke(prompt)
        self._tracker.record(getattr(response, "usage_metadata", None))
        return response


def create_chat_model(settings: LLMSettings, tracker: UsageTracker) -> TrackedChatModel:
    if not settings.model_name:
        raise RuntimeError(
            "A model is required: set AGENT_MODEL_NAME (and AGENT_MODEL_API_KEY / "
            "AGENT_MODEL_BASE_URL as needed) or pass explicit settings."
        )
    if settings.api_spec == "anthropic":
        from langchain_anthropic import ChatAnthropic
        inner = ChatAnthropic(
            model=settings.model_name,
            temperature=settings.temperature,
            max_tokens=settings.max_tokens,
            api_key=settings.api_key or None,
        )
    else:
        from langchain_openai import ChatOpenAI
        inner = ChatOpenAI(
            model=settings.model_name,
            temperature=settings.temperature,
            max_tokens=settings.max_tokens,
            api_key=settings.api_key or "dummy",
            base_url=settings.base_url or None,
        )
    return TrackedChatModel(inner, tracker)

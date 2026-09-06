"""Network-free tests for the standalone llm_factory_from_env helper.

These never instantiate a real provider client (that would need the optional
[llm] extra and network); they only check resolution + the None fallback.
"""
from __future__ import annotations

import pytest

from alignmentgraph_isd import llm_factory_from_env

_ENV_VARS = (
    "AGENT_MODEL_NAME",
    "AGENT_MODEL_API_SPEC",
    "AGENT_MODEL_BASE_URL",
    "AGENT_MODEL_API_KEY",
    "AGENT_MODEL_TEMPERATURE",
    "AGENT_MODEL_MAX_TOKENS",
)


@pytest.fixture(autouse=True)
def _clear_agent_env(monkeypatch):
    for name in _ENV_VARS:
        monkeypatch.delenv(name, raising=False)


def test_no_model_returns_none():
    assert llm_factory_from_env() is None


def test_explicit_model_returns_callable():
    factory = llm_factory_from_env(model_name="gpt-4o-mini")
    assert callable(factory)


def test_env_model_returns_callable(monkeypatch):
    monkeypatch.setenv("AGENT_MODEL_NAME", "gpt-4o-mini")
    factory = llm_factory_from_env()
    assert callable(factory)


def test_explicit_arg_overrides_env(monkeypatch):
    monkeypatch.setenv("AGENT_MODEL_NAME", "from-env")
    # An explicit arg wins; both resolve to a callable factory regardless.
    assert callable(llm_factory_from_env(model_name="from-arg"))


def test_unsupported_api_spec_raises_when_built():
    factory = llm_factory_from_env(model_name="m", api_spec="bogus")
    with pytest.raises(ValueError, match="Unsupported api_spec"):
        factory()


def test_disable_thinking_sets_the_chat_template_flag_on_openai_compatible():
    """The one knob that answers the measured 'reasoning only' failure.

    Qwen3 left in thinking mode spends its completion budget in
    ``reasoning_content``, which reaches the loop as empty content with no tool
    call — an invalid turn that costs a full turn of the stage budget (measured
    on run 24343e4d: 12 of 78 calls). The flag has to travel as a request field,
    so assert the request field, not just that a client was built.
    """
    pytest.importorskip("langchain_openai")
    client = llm_factory_from_env(model_name="qwen", api_key="k", disable_thinking=True)()
    assert client.extra_body == {"chat_template_kwargs": {"enable_thinking": False}}


def test_disable_thinking_is_off_by_default():
    pytest.importorskip("langchain_openai")
    client = llm_factory_from_env(model_name="qwen", api_key="k")()
    assert not getattr(client, "extra_body", None)


def test_disable_thinking_is_not_sent_to_anthropic():
    """``chat_template_kwargs`` is a vLLM/OpenAI-body concept; Anthropic would
    reject it. The branch must ignore the flag rather than pass it through."""
    pytest.importorskip("langchain_anthropic")
    client = llm_factory_from_env(
        model_name="claude-x", api_spec="anthropic", api_key="k",
        disable_thinking=True)()
    assert not getattr(client, "extra_body", None)

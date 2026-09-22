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



def test_every_call_has_a_deadline():
    """There was no timeout anywhere, so a request that stalled stalled the
    run and the only way out was someone pressing cancel. MEASURED (run
    d3f566aa): a compaction started at 743 s and had returned nothing 273 s
    later when the run was cancelled by hand."""
    from alignmentgraph_isd.core.llm import DEFAULT_TIMEOUT_SECONDS, llm_factory_from_env

    model = llm_factory_from_env(
        model_name="m", api_spec="openai_compatible", base_url="http://h/v1",
        api_key="k", read_env=False)()

    assert model.request_timeout == DEFAULT_TIMEOUT_SECONDS
    # Read off what a call can legitimately need: 8,192 completion tokens at
    # the slowest healthy rate measured (~40 tok/s) is about 205 s.
    assert 180 <= DEFAULT_TIMEOUT_SECONDS <= 300


def test_thinking_is_left_on_unless_a_connection_turns_it_off():
    """The ladder serves WITH thinking and the harness records that channel, so
    turning it off is a different posture and has to be asked for."""
    from alignmentgraph_isd.core.llm import llm_factory_from_env

    def build(**over):
        return llm_factory_from_env(
            model_name="m", api_spec="openai_compatible", base_url="http://h/v1",
            api_key="k", read_env=False, **over)()

    assert not getattr(build(), "extra_body", None)
    assert build(disable_thinking=True).extra_body == {
        "chat_template_kwargs": {"enable_thinking": False}}

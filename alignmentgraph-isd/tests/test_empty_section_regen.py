"""A specialist whose first attempt returns an empty section is re-run, instead
of shipping the empty skeleton (which scores that whole ADDIE phase 0 at the
judge). Reproduces the small-model failure mode where a 2B endpoint intermittently
returns an empty/unparseable payload for one phase."""
from __future__ import annotations

from alignmentgraph_isd import HarnessRunConfig, run_design_brief
from alignmentgraph_isd.core.nodes import (
    EMPTY_SECTION_REGEN_BUDGET,
    _empty_required_fields,
)

from conftest import FakeChatModel, load_brief


class _FlakyAnalysis(FakeChatModel):
    """FakeChatModel that returns an EMPTY payload for the first ``fail_first``
    Analysis-phase calls, then behaves normally. Shared ``state`` counts calls
    across the per-attempt model instances the harness creates via llm_factory."""

    def __init__(self, state: dict, fail_first: int) -> None:
        self._state = state
        self._fail_first = fail_first

    def bind(self, **_kwargs):
        return self

    def invoke(self, messages):
        system = ""
        for message in messages:
            if isinstance(message, dict) and message.get("role") == "system":
                system = message.get("content", "")
                break
        if "Analysis phase of ADDIE" in system:
            self._state["analysis_calls"] = self._state.get("analysis_calls", 0) + 1
            if self._state["analysis_calls"] <= self._fail_first:
                from conftest import _Result

                return _Result("")  # empty response -> empty parsed section
        return super().invoke(messages)


def _flaky_factory(fail_first: int):
    state: dict = {}

    def factory():
        return _FlakyAnalysis(state, fail_first)

    return factory, state


class _FlakyRestDesign(FakeChatModel):
    """Empty payload for the first ``fail_first`` objective_design *rest* calls
    (strategies/media/storyboard/content) — the learning-objectives call still
    succeeds. Reproduces the parse failure that leaves design.instructional_strategies
    empty while learning_objectives is present."""

    def __init__(self, state: dict, fail_first: int) -> None:
        self._state = state
        self._fail_first = fail_first

    def bind(self, **_kwargs):
        return self

    def invoke(self, messages):
        system = ""
        for message in messages:
            if isinstance(message, dict) and message.get("role") == "system":
                system = message.get("content", "")
                break
        if "Must have at least 5 learning objectives" in system:
            self._state["lo_calls"] = self._state.get("lo_calls", 0) + 1
        if "remaining Design section" in system:
            self._state["rest_calls"] = self._state.get("rest_calls", 0) + 1
            if self._state["rest_calls"] <= self._fail_first:
                from conftest import _Result

                return _Result("")
        return super().invoke(messages)


def _flaky_rest_factory(fail_first: int):
    state: dict = {}

    def factory():
        return _FlakyRestDesign(state, fail_first)

    return factory, state


class _FlakyFormative(FakeChatModel):
    """Empty payload for the first ``fail_first`` formative-evaluation calls; the
    summative call still succeeds. Exercises evaluation_revision's sub-field regen
    guard (both calls merge into one EVALUATION node)."""

    def __init__(self, state: dict, fail_first: int) -> None:
        self._state = state
        self._fail_first = fail_first

    def bind(self, **_kwargs):
        return self

    def invoke(self, messages):
        system = ""
        for message in messages:
            if isinstance(message, dict) and message.get("role") == "system":
                system = message.get("content", "")
                break
        if "SUMMATIVE evaluation" in system:
            self._state["summative_calls"] = self._state.get("summative_calls", 0) + 1
        if "FORMATIVE evaluation" in system:
            self._state["formative_calls"] = self._state.get("formative_calls", 0) + 1
            if self._state["formative_calls"] <= self._fail_first:
                from conftest import _Result

                return _Result("")
        return super().invoke(messages)


def _flaky_formative_factory(fail_first: int):
    state: dict = {}

    def factory():
        return _FlakyFormative(state, fail_first)

    return factory, state


def _run(factory, **config_kwargs) -> dict:
    config = HarnessRunConfig(**config_kwargs)
    config.llm_factory = factory
    return run_design_brief(load_brief("minimal_brief.json"), config)


def _regen_events(result: dict) -> list[dict]:
    return [
        s for s in result["trajectory"]["agent_steps"]
        if s["action"] == "regen_empty_section"
    ]


# ``_call_llm`` already burns one in-conversation correction retry cycle
# (1 initial + 2 corrections = 3 invokes) before it gives up and returns empty.
# ``fail_first`` must exceed that so the *whole first generation attempt* comes
# back empty, forcing the node-level regen we are testing.
_INVOKES_PER_ATTEMPT = 3


def test_empty_section_triggers_regen_and_recovers():
    # First generation attempt returns empty throughout; the node re-runs fresh
    # and the second attempt recovers a full analysis section.
    factory, state = _flaky_factory(fail_first=_INVOKES_PER_ATTEMPT)
    result = _run(factory)

    analysis = result["addie_output"]["analysis"]
    assert analysis["needs_analysis"], "analysis section should be recovered, not empty"
    assert not _empty_required_fields("needs_context", {
        "needs_analysis": analysis["needs_analysis"],
        "learner_analysis": analysis["learner_analysis"],
        "context_analysis": analysis["context_analysis"],
        "task_analysis": analysis["task_analysis"],
    })

    regens = _regen_events(result)
    assert len(regens) == 1  # exactly one empty attempt, then recovery

    # No leftover empty-analysis validation error once recovered.
    assert not any(
        e.startswith("analysis.") for e in result["metadata"].get("validation_errors", [])
    )


def test_persistent_empty_section_stops_at_budget():
    # Analysis never recovers: the loop must stop after budget+1 attempts (no
    # infinite loop) and surface the empty phase rather than mask it.
    factory, _state = _flaky_factory(fail_first=999)
    result = _run(factory)

    assert len(_regen_events(result)) == EMPTY_SECTION_REGEN_BUDGET + 1
    assert any(
        e.startswith("analysis.") for e in result["metadata"].get("validation_errors", [])
    )


def test_secondary_call_failure_triggers_regen():
    # objective_design generates in two calls; the learning-objectives call
    # succeeds but the "rest" call (instructional_strategies etc.) comes back
    # empty. Because instructional_strategies is a phase-required field the
    # specialist owns, regen must re-run the whole specialist and recover it —
    # not stop just because learning_objectives is present.
    factory, state = _flaky_rest_factory(fail_first=_INVOKES_PER_ATTEMPT)
    result = _run(factory)

    design = result["addie_output"]["design"]
    assert design["learning_objectives"], "objectives should be present throughout"
    assert design["instructional_strategies"], "strategies should be recovered by regen"

    regens = [
        s for s in _regen_events(result)
        if s["agent_name"] == "ObjectiveDesignAgent"
    ]
    assert len(regens) == 1
    assert state["rest_calls"] >= _INVOKES_PER_ATTEMPT + 1  # empty attempt + recovery
    # Surgical regen: the good learning-objectives call is NOT re-rolled on regen
    # — it runs exactly once (its first attempt parsed fine), so the re-run only
    # re-invokes the failed rest call.
    assert state["lo_calls"] == 1
    assert not any(
        e.startswith("design.") for e in result["metadata"].get("validation_errors", [])
    )


def test_evaluation_partial_regen_reuses_good_call():
    # summative parses, formative fails. Regen re-runs evaluation_revision but the
    # sub-field guard reuses the good summative — only formative is re-rolled.
    factory, state = _flaky_formative_factory(fail_first=_INVOKES_PER_ATTEMPT)
    result = _run(factory)

    evaluation = result["addie_output"]["evaluation"]
    assert evaluation["summative"] and evaluation["formative"]
    assert state["summative_calls"] == 1  # not re-rolled on regen
    assert not any(
        e.startswith("evaluation.") for e in result["metadata"].get("validation_errors", [])
    )


def test_regen_budget_is_config_driven():
    # A config-supplied budget (e.g. sourced from HARNESS_REGEN_BUDGET by the
    # benchmark adapter) overrides the module default.
    factory, _state = _flaky_factory(fail_first=999)
    result = _run(factory, regen_budget=1)
    assert len(_regen_events(result)) == 1 + 1


def test_regen_backoff_sleeps_before_each_rerun(monkeypatch):
    # A config-supplied backoff (sourced from BENCHMARK_DELAY / HARNESS_REGEN_BACKOFF)
    # makes the loop wait — growing per attempt — before re-running, so a 429
    # concurrency window can drain instead of being hammered.
    from alignmentgraph_isd.core import nodes

    sleeps: list[float] = []
    monkeypatch.setattr(nodes.time, "sleep", lambda s: sleeps.append(s))

    factory, _state = _flaky_factory(fail_first=999)
    _run(factory, regen_budget=2, regen_backoff_seconds=0.5)

    # Only the needs_context node keeps failing; its two re-runs sleep 0.5*1 and
    # 0.5*2 before attempts 2 and 3. A recovered node sleeps 0 times.
    assert sleeps.count(0.5) == 1 and sleeps.count(1.0) == 1

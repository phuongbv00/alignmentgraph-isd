"""A stage whose LLM call(s) keep coming back empty is re-run, instead of
shipping an empty primary artifact pool (which starves the aggregator and
scores that ADDIE phase 0 at the judge). Reproduces the small-model failure
mode where an endpoint intermittently returns an empty/unparseable payload for
one call.

The regen loop lives in ``core/agentic/run.py`` and is coarse and per-stage
("did this stage's artifact get committed at all"), bounded by
``HarnessRunConfig.regen_budget``. What keeps it from re-rolling work that
already landed is ``specialists.step_done``: a re-run starts the stage's tool
loop from scratch, but a stage whose artifact is already in the design state is
not re-entered. These tests exercise both properties together: regen recovers a
fully-empty attempt, AND work that already succeeded is not re-invoked on the
retry.

Retry/regen plumbing is judge-invisible (``log_recovery_event`` ->
``trajectory["events"]`` with a recovery-taxonomy action, never ``tool_calls`` — see
``core/trajectory.py``), so assertions read the recovery events, not
the judge-visible step stream as the pre-redesign version of this file did."""
from __future__ import annotations

from alignmentgraph_isd import HarnessRunConfig, run_design_brief

#: The default the regen loop runs on. Was a module constant of the
#: scripted pipeline; since that went, the config field IS the budget.

from conftest import FakeChatModel, load_brief


class _FlakySystemPrompt(FakeChatModel):
    """FakeChatModel that returns an EMPTY payload for the first
    ``fail_first`` calls whose system prompt contains ``match_phrase``, then
    behaves normally. ``state`` is shared across the per-attempt model
    instances the harness creates via ``llm_factory``, so call counts
    accumulate across regen attempts."""

    def __init__(self, state: dict, match_phrase: str, counter_key: str, fail_first: int) -> None:
        super().__init__()
        self._state = state
        self._match_phrase = match_phrase
        self._counter_key = counter_key
        self._fail_first = fail_first

    def bind(self, **_kwargs):
        return self

    def invoke(self, messages):
        system = ""
        for message in messages:
            if isinstance(message, dict) and message.get("role") == "system":
                system = message.get("content", "")
                break
        if self._match_phrase in system:
            self._state[self._counter_key] = self._state.get(self._counter_key, 0) + 1
            if self._state[self._counter_key] <= self._fail_first:
                from conftest import _Result

                return _Result("")  # empty response -> empty parsed section
        return super().invoke(messages)


def _flaky_factory(match_phrase: str, counter_key: str, fail_first: int):
    state: dict = {}

    def factory():
        return _FlakySystemPrompt(state, match_phrase, counter_key, fail_first)

    return factory, state


def _run(factory, **config_kwargs) -> dict:
    # The agentic executor regenerates a whole STAGE, and a fan-out family's
    # sets independently. The per-hop regen these tests were written against
    # (analyze vs design, dispatch vs finalize) went with the scripted
    # pipeline; what they still pin is the posture: an empty answer is retried,
    # bounded, and the retry is recorded.
    config = HarnessRunConfig(**config_kwargs)
    config.llm_factory = factory
    return run_design_brief(load_brief("minimal_brief.json"), config)




# ``_call_llm`` already burns one in-conversation correction retry cycle
# (1 initial + 2 corrections = 3 invokes) before it gives up and returns empty.
# ``fail_first`` must exceed that so the *whole first generation attempt* comes
# back empty, forcing the node-level regen we are testing.
_INVOKES_PER_ATTEMPT = 3


def test_an_empty_answer_is_absorbed_inside_the_stage_and_loses_nothing():
    """The agentic executor recovers an empty answer WITHOUT a stage-level
    regen: the act->observe loop simply gets another turn, the nudge is
    recorded, and the section still lands.

    That is a change in mechanism, not in protection. The scripted pipeline had
    to re-run the whole node because a node was one call; a loop that is already
    several turns long absorbs a fumble inside the turn budget it already has.
    What these tests still pin is the posture: an empty answer is retried, the
    retry is recorded, and nothing is lost."""
    factory, state = _flaky_factory("the course goal and learning objectives",
                                    "design_calls", fail_first=_INVOKES_PER_ATTEMPT)
    result = _run(factory)

    assert state["design_calls"] > _INVOKES_PER_ATTEMPT, "the flake never fired"
    design = result["addie_output"]["design"]
    assert design["learning_objectives"], "the fumbled section was lost"
    # The fumble is in the record, not silently swallowed.
    nudges = [a for a in result["trajectory_deep"]["actions"]
              if a["action"] in ("invalid_action", "regen_empty_section")]
    assert nudges


def test_an_earlier_stage_is_not_re_run_when_a_later_one_fumbles():
    """Stages are committed as they land. A stage that fumbles costs its own
    turns and nobody else's — an earlier artifact is never re-rolled, which is
    what makes the cost of a failure local."""
    factory, _state = _flaky_factory("the course goal and learning objectives",
                                     "design_calls", fail_first=_INVOKES_PER_ATTEMPT)
    result = _run(factory)

    analysis = result["addie_output"]["analysis"]
    assert analysis["needs_analysis"], "analysis was re-rolled by a later stage's failure"
    assert analysis["learner_analysis"]


def test_a_stage_that_never_produces_gives_up_within_its_budget():
    """Persistent emptiness must terminate. Since the scripted rescue went
    (2026-09-01) the stage ends with what the model managed and says it did not
    finish; the deterministic repair net is what fills the hole."""
    factory, _state = _flaky_factory("the course goal and learning objectives",
                                     "design_calls", fail_first=999)
    result = _run(factory)

    gave_up = [a for a in result["trajectory_deep"]["actions"]
               if a["action"] == "agentic_gave_up"]
    assert gave_up, "a stage that never produced anything did not record giving up"
    assert result["metadata"]["autonomy"]["outcomes"]["gave_up"]


def test_a_flaky_developer_does_not_lose_its_familys_other_sets():
    """Work sets are independent: one Developer fumbling costs its own set, and
    the family still comes back with the sets that succeeded."""
    factory, state = _flaky_factory(
        "developing learner materials for ONE content module", "materials_calls",
        fail_first=_INVOKES_PER_ATTEMPT,
    )
    result = _run(factory)

    assert state["materials_calls"] > _INVOKES_PER_ATTEMPT, "the flake never fired"
    assert result["addie_output"]["development"]["learner_materials"], \
        "one flaky module took the whole family down"


def test_regen_budget_is_config_driven():
    """The stage-level retry allowance is configuration, not a constant: the
    benchmark adapter sets it from the environment, and a run must honour it."""
    factory, _state = _flaky_factory("the course goal and learning objectives",
                                     "design_calls", fail_first=999)
    result = _run(factory, regen_budget=0)

    assert result["metadata"]["run_config"]["regen_budget"] == 0


def test_regen_backoff_sleeps_before_each_rerun(monkeypatch):
    """A re-run after a rate-limited call must wait, or it hammers the same
    window it was throttled by."""
    import alignmentgraph_isd.core.agentic.run as agentic_run

    slept: list[float] = []
    monkeypatch.setattr(agentic_run.time, "sleep", lambda s: slept.append(s))
    factory, _state = _flaky_factory("the course goal and learning objectives",
                                     "design_calls", fail_first=999)
    _run(factory, regen_backoff_seconds=0.5)

    assert slept, "a re-run happened with no backoff at all"
    assert all(s > 0 for s in slept)


class _PartialImplementationOnce(FakeChatModel):
    """Deposits a truncation-shaped PARTIAL artifact — ``monitoring`` arrives
    as an EMPTY DICT rather than being absent — for a bounded window, then
    behaves normally.

    Empty-not-absent is the case that matters: an absent artifact is obviously
    unfinished, while one whose key is present is exactly what a truncated
    completion produces, and it is the case where the done-guard and the
    validator can silently disagree. Matches on the whole conversation because
    the single arm keeps its schema in the user turn, not the system prompt."""

    #: Long enough that every other implementation artifact has landed, so the
    #: only reason to keep going is the empty one.
    WITHHOLD_CALLS = 5

    def __init__(self, state: dict) -> None:
        # super().__init__() matters now: `_respond` keeps a call counter, and
        # a fake that skips it cannot shape a tool call.
        super().__init__()
        self._state = state

    def bind(self, **_kwargs):
        return self

    def invoke(self, messages):
        prompt = "\n".join(
            m.get("content", "") for m in messages
            if isinstance(m, dict) and isinstance(m.get("content"), str)
        )
        if '"instructor_orientation"' in prompt:
            self._state["impl_calls"] = self._state.get("impl_calls", 0) + 1
            if self._state["impl_calls"] <= self.WITHHOLD_CALLS:
                from conftest import _IMPLEMENTATION

                # Through `_stage_submit`/`_respond` so the payload arrives as
                # a TOOL CALL naming a bound tool: under native tool calling a
                # bare content string is not an answer the loop can use, and
                # every stage would fail instead of the one this is about.
                partial = dict(_IMPLEMENTATION)
                partial["monitoring"] = {}
                name, args = self._stage_submit(partial, messages)
                return self._respond(args, name)
        return super().invoke(messages)


class _ManualsMissingOnce(FakeChatModel):
    """Returns an implementation payload whose four orientation/check/pilot/
    monitoring dicts are populated but whose instructor_guide and
    operator_manual are ABSENT, on the first implementation call only.
    Reproduces the run observed in single_20260827_005607: everything the old
    requiredness covered was present, the two rubric-graded manuals were not,
    and no safeguard fired while judge sub-items 20/21 scored 0.0."""

    #: How many implementation calls answer WITHOUT the two manuals. Four is
    #: the number of other artifacts the stage submits, so by the end of the
    #: window nothing but the manuals is outstanding.
    WITHHOLD_CALLS = 4

    def __init__(self, state: dict) -> None:
        # super().__init__() matters now: `_respond` keeps a call counter, and
        # a fake that skips it cannot shape a tool call.
        super().__init__()
        self._state = state

    def bind(self, **_kwargs):
        return self

    def invoke(self, messages):
        prompt = "\n".join(
            m.get("content", "") for m in messages
            if isinstance(m, dict) and isinstance(m.get("content"), str)
        )
        if '"instructor_orientation"' in prompt:
            self._state["impl_calls"] = self._state.get("impl_calls", 0) + 1
            # Withheld for long enough that every OTHER implementation artifact
            # has landed. That is what makes this test able to fail: if the
            # done-guard did not require the two manuals, the stage would be
            # finished by now and they would never be asked for again. One
            # call per artifact since the 2026-09-03 submit split, so the
            # window has to cover the four that are not withheld.
            if self._state["impl_calls"] <= self.WITHHOLD_CALLS:
                from conftest import _IMPLEMENTATION

                thin = {k: v for k, v in _IMPLEMENTATION.items()
                        if k not in ("instructor_guide", "operator_manual")}
                # Through `_stage_submit` + `_respond` so the payload arrives
                # as a TOOL CALL naming a tool the stage actually binds — see
                # the note in _PartialImplementationOnce.
                name, args = self._stage_submit(thin, messages)
                return self._respond(args, name)
        return super().invoke(messages)


def test_a_deposit_missing_required_fields_counts_as_not_produced():
    """``instructor_guide``/``operator_manual`` are required, so a deposit
    without them is "not produced" and the stage keeps working — in the graph
    arm and the prose arm alike (shared ``_empty_required_fields``).

    The mechanism moved with the executor: what used to be a whole-node re-run
    is now the loop rejecting the submit and getting another turn. What has not
    moved is the definition of done, which is the point of the test."""
    for mode in ("graph", "prose"):
        state: dict = {}
        result = _run(lambda: _ManualsMissingOnce(state), context_mode=mode)

        development = result["addie_output"]["development"]
        assert development["instructor_guide"], f"{mode}: instructor_guide never recovered"
        assert development["operator_manual"], f"{mode}: operator_manual never recovered"
        # Strictly past the withholding window: everything BUT the manuals had
        # landed by then, so a stage that stopped here would be one whose
        # done-guard no longer requires them. (Negative control, measured: with
        # the manuals withheld forever the loop asks 27 times and both stay
        # empty — i.e. this assertion is what fails when the guard goes.)
        assert state["impl_calls"] > _ManualsMissingOnce.WITHHOLD_CALLS, (
            f"{mode}: the stage stopped as soon as the other artifacts landed")
        assert not any(
            e.startswith("development.") for e in result["metadata"].get("validation_errors", [])
        )


def test_a_partial_deposit_does_not_satisfy_the_done_guard():
    """The done-guard and the validator must agree on what "produced" means.

    When they disagreed, a truncated partial deposit satisfied the guard while
    the validator kept demanding a retry, and the loop spun WITHOUT re-calling
    the model (measured on a 4096-clamped endpoint: three regen events, zero
    extra llm_calls, a half-empty implementation shipped). Both arms, both
    context modes."""
    for agent_mode in ("multi", "single"):
        for mode in ("graph", "prose"):
            label = f"{agent_mode}+{mode}"
            state: dict = {}
            result = _run(lambda: _PartialImplementationOnce(state),
                          agent_mode=agent_mode, context_mode=mode)

            impl = result["addie_output"]["implementation"]
            assert impl["system_check"], f"{label}: the stage produced nothing"
            # The artifact that kept arriving EMPTY is the one under test.
            assert impl["monitoring"], (
                f"{label}: an empty artifact was accepted as produced")
            # Strictly past the window: everything else had landed, so a stage
            # that stopped there is one whose guard counts "the key is present"
            # as done. (Negative control, measured: with `monitoring` empty
            # forever the loop asks 27 times, ships `{}`, and the metadata
            # records "implementation.monitoring: required field is missing or
            # empty" — i.e. these two assertions are what fail if it goes.)
            assert state["impl_calls"] > _PartialImplementationOnce.WITHHOLD_CALLS, (
                f"{label}: the stage stopped while an artifact was still empty")

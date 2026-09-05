"""The outbound-call gate (core/ratelimit.py).

WHAT IT ANSWERS, historically: the LangGraph pipeline ran content_designer and
rubric_designer in one superstep, each fanning out one Developer call per work
set, so one agent could put 10+ requests on the endpoint at once while the
benchmark's rate posture counted it as one unit. A shared endpoint answered
with HTTP 429 — 9-25 per run on the two multi arms against 0-2 on the
sequential single arms, a throttling handicap sitting on the ``agent_mode``
axis itself.

WHAT IS TRUE NOW: the executor is fully sequential, so the gate has nothing to
cap in practice and the run-level test below measures a peak of 1 whatever it
is configured to. The gate's own behaviour is covered directly by
``test_gate_bounds_concurrent_holders``; the run-level one is kept as a
tripwire for the day a concurrent fan-out comes back.
"""
from __future__ import annotations

import threading
import time

import pytest

from alignmentgraph_isd import HarnessRunConfig
from alignmentgraph_isd.core.ratelimit import CallGate, gate_for

from conftest import FakeChatModel, load_brief, run_brief


class _Peak:
    """Records the highest number of holders in the gate at any moment."""

    def __init__(self) -> None:
        self.lock = threading.Lock()
        self.live = 0
        self.peak = 0

    def enter(self) -> None:
        with self.lock:
            self.live += 1
            self.peak = max(self.peak, self.live)

    def exit(self) -> None:
        with self.lock:
            self.live -= 1


def _hammer(gate: CallGate, peak: _Peak, threads: int = 12, hold_s: float = 0.02) -> None:
    def work() -> None:
        with gate.hold():
            peak.enter()
            time.sleep(hold_s)
            peak.exit()

    workers = [threading.Thread(target=work) for _ in range(threads)]
    for w in workers:
        w.start()
    for w in workers:
        w.join()


def test_gate_bounds_concurrent_holders():
    peak = _Peak()
    _hammer(CallGate(max_concurrency=3), peak)
    assert peak.peak <= 3


def test_zero_means_unbounded():
    peak = _Peak()
    _hammer(CallGate(max_concurrency=0), peak)
    assert peak.peak > 3  # the default posture for a standalone run


def test_min_interval_spaces_call_starts():
    gate = CallGate(max_concurrency=0, min_interval_seconds=0.05)
    started = time.monotonic()
    for _ in range(3):
        with gate.hold():
            pass
    assert time.monotonic() - started >= 0.10  # three starts, two gaps


def test_gate_is_per_config_and_cached():
    config = HarnessRunConfig(llm_max_concurrency=2)
    gate = gate_for(config)
    assert gate.max_concurrency == 2
    assert gate_for(config) is gate                    # every agent shares one gate
    assert gate_for(HarnessRunConfig()) is not gate    # ...but only within its run
    assert gate_for(HarnessRunConfig()).max_concurrency == 0
    assert gate_for(None).max_concurrency == 0


class _CountingModel(FakeChatModel):
    """The conftest fake, recording peak concurrency across the whole run."""

    peak = _Peak()

    def invoke(self, messages):
        _CountingModel.peak.enter()
        try:
            time.sleep(0.01)          # long enough for the fan-out to overlap
            return super().invoke(messages)
        finally:
            _CountingModel.peak.exit()


def _run_multi(**settings):
    """One full multi-arm run, reporting the peak number of concurrent calls."""
    _CountingModel.peak = _Peak()
    run_brief(
        load_brief("minimal_brief.json"),
        HarnessRunConfig(llm_factory=lambda: _CountingModel(), agent_mode="multi", **settings),
    )
    return _CountingModel.peak.peak


def test_a_run_never_exceeds_the_configured_concurrency():
    """The gate is what stands between a fan-out and an HTTP 429.

    It no longer has anything to cap in practice: the LangGraph superstep that
    ran content and rubric together, and the parallel develop nodes under each
    dev-plan family, went with the scripted pipeline on 2026-09-01. The agentic
    executor runs its stages and its Developers SEQUENTIALLY on purpose —
    concurrent stages would race the trajectory's thread-local actor scope, the
    failure fixed on 2026-08-27.

    So this pins the ceiling rather than the parallelism: whatever a future
    executor does, a run must not exceed what it was configured for. The gate is
    per-run and never process-wide, or one arm would queue behind another and
    inflate its execution_time_seconds."""
    assert _run_multi(llm_max_concurrency=1) == 1
    assert _run_multi(llm_max_concurrency=2) <= 2
    # And an uncapped run is bounded by what the executor actually does.
    assert _run_multi() >= 1
    # The ceiling assertions above are satisfied by a sequential executor no
    # matter what, so they cannot tell "the gate held" from "the gate is not
    # wired in". This can: every model call must pass through the run's gate.
    from alignmentgraph_isd.core import ratelimit

    gate = ratelimit.gate_for(HarnessRunConfig(llm_max_concurrency=1))
    held: list[int] = []
    original = type(gate).hold

    def counting_hold(self):
        held.append(1)
        return original(self)

    monkey = pytest.MonkeyPatch()
    monkey.setattr(type(gate), "hold", counting_hold)
    try:
        _run_multi(llm_max_concurrency=1)
    finally:
        monkey.undo()
    assert held, "no model call went through the run's call gate"


# ── transcript budget derived from the serving window ───────────────────────

def test_the_history_budget_follows_the_serving_window():
    """`HISTORY_CHAR_BUDGET` was 24,000 characters — a number with no relation
    to the model actually being served. On the ladder's configuration the
    derivation lands within 2.4% of it, so the constant was well chosen; the
    point is that it now TRACKS the serving setup instead of coinciding with
    it, and a wider-window model gets the window it has."""
    from alignmentgraph_isd.core.agentic.loop import HISTORY_CHAR_BUDGET, history_budget  # noqa: F401

    def cfg(**kw):
        return HarnessRunConfig(llm_factory=lambda: None, **kw)

    # Unset: unchanged, so a standalone run behaves exactly as before.
    assert history_budget(cfg()) == HISTORY_CHAR_BUDGET

    ladder = history_budget(cfg(llm_context_window=16384, llm_completion_reserve=8192))
    assert abs(ladder - HISTORY_CHAR_BUDGET) / HISTORY_CHAR_BUDGET < 0.05
    # A wider window gives more room, in proportion.
    assert history_budget(cfg(llm_context_window=32768)) > 2 * ladder


def test_a_window_swallowed_by_the_reserve_still_leaves_a_working_budget():
    """A floor, so a misconfigured window cannot leave a budget too small to
    hold the system turn — which trim never drops, and which would then be the
    whole prompt with nothing able to survive beside it."""
    from alignmentgraph_isd.core.agentic.loop import history_budget

    tiny = history_budget(HarnessRunConfig(
        llm_factory=lambda: None, llm_context_window=8192, llm_completion_reserve=8192))
    assert tiny > 0


def test_the_token_budget_is_what_is_equal_across_arms():
    """The invariant is the budget in TOKENS, which is the physical constraint:
    window minus the completion reserve, identical for both arms.

    Characters are only the unit `trim_history` counts in, and the conversion
    goes through each run's own measured ratio — so an arm whose prompts are
    transcript-heavy and one whose prompts are schema-heavy can land on
    slightly different CHARACTER budgets while holding the same token budget.
    That is more correct, not less: equalising characters would have given the
    two arms different amounts of the thing that actually runs out."""
    from alignmentgraph_isd.core.agentic.loop import history_budget, prompt_token_budget

    tokens = {
        mode: prompt_token_budget(HarnessRunConfig(
            llm_factory=lambda: None, llm_context_window=16384, agent_mode=mode))
        for mode in ("multi", "single")
    }
    assert len(set(tokens.values())) == 1, tokens
    assert tokens["multi"] == 16384 - 8192

    # Uncalibrated, the character budgets coincide too.
    chars = {
        mode: history_budget(HarnessRunConfig(
            llm_factory=lambda: None, llm_context_window=16384, agent_mode=mode))
        for mode in ("multi", "single")
    }
    assert len(set(chars.values())) == 1, chars


def test_the_token_ratio_is_measured_not_assumed():
    """Not a library and not a constant. `tiktoken` is OpenAI's vocabulary and
    the ladder serves Qwen, so it would be a DIFFERENT estimate rather than a
    correct one, and the model's real tokenizer means pulling `transformers`
    into a package the benchmark installs plain.

    The exact answer already arrives: every response reports `prompt_tokens`
    for a prompt whose character count we know."""
    from alignmentgraph_isd.core.agentic.loop import (
        COLD_CHARS_PER_TOKEN, TokenRatio, history_budget, ratio_for,
    )

    ratio = TokenRatio()
    assert not ratio.measured
    assert ratio.chars_per_token == COLD_CHARS_PER_TOKEN

    # A real observation replaces the guess.
    ratio.observe(chars=9000, prompt_tokens=4500)
    assert ratio.measured
    assert ratio.chars_per_token == 2.0

    # A provider that reports nothing leaves it where it is rather than driving
    # it to zero — a zero ratio would collapse the budget to nothing.
    ratio.observe(chars=1000, prompt_tokens=0)
    assert ratio.chars_per_token == 2.0

    # A measurement never RAISES the estimate above the cold value: the budget
    # it feeds is a safety limit, and a ratio measured on prose-heavy turns
    # would license a prompt a JSON-heavy turn then overflows.
    generous = TokenRatio()
    generous.observe(chars=10000, prompt_tokens=1000)   # 10 chars/token
    assert generous.chars_per_token == COLD_CHARS_PER_TOKEN

    # And it is what the budget converts through.
    config = HarnessRunConfig(llm_factory=lambda: None, llm_context_window=16384)
    before = history_budget(config)
    ratio_for(config).observe(chars=8000, prompt_tokens=4000)  # 2.0
    assert history_budget(config) < before


def test_the_ratio_is_shared_across_the_whole_run():
    """Per RUN, not per agent, so both arms calibrate off the same traffic —
    the same per-config caching `ratelimit.gate_for` uses."""
    from alignmentgraph_isd.core.agentic.loop import ratio_for

    config = HarnessRunConfig(llm_factory=lambda: None, llm_context_window=16384)
    assert ratio_for(config) is ratio_for(config)
    assert ratio_for(HarnessRunConfig(llm_factory=lambda: None)) is not ratio_for(config)


def test_the_context_parts_are_a_true_partition():
    """The three sum to the transcript, so a bar drawn from them cannot lie
    about what filled the window. The earlier split did not: it measured the
    bound tool SCHEMAS, which are not in the message list at all, so the parts
    overlapped the total instead of dividing it."""
    from alignmentgraph_isd.core.agentic.loop import _prompt_chars_any, context_parts

    messages = [
        {"role": "system", "content": "rules"},
        {"role": "user", "content": "the stage instructions"},
        {"role": "assistant", "content": "", "tool_calls": [
            {"name": "submit", "args": {"learning_objectives": [{"id": "ILO-01"}]}}]},
        {"role": "tool", "name": "submit", "content": "COMMITTED"},
    ]
    parts = context_parts(messages)
    assert sum(parts.values()) == _prompt_chars_any(messages)

    assert parts["system"] == len("rules")
    assert parts["messages"] == len("the stage instructions")
    # The submitted artifact lives in the tool CALL, not in content: an
    # assistant turn that submits carries empty content, so a split that read
    # only `content` would show the run producing nothing.
    assert parts["tools"] > len("COMMITTED")

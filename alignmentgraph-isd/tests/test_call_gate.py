"""The outbound-call gate (core/ratelimit.py) and its effect on the multi arm.

The multi arm runs content_designer and rubric_designer in one superstep and
each fans out one Developer call per work set, so a single agent could put 10+
requests on the endpoint at once while the benchmark's rate posture still
counted it as one unit. A shared endpoint answered with HTTP 429 — measured at
9-25 per run on the two multi arms against 0-2 on the sequential single arms,
i.e. a throttling handicap sitting on the ``agent_mode`` ablation axis.
"""
from __future__ import annotations

import threading
import time

from alignmentgraph_isd import HarnessRunConfig, run_design_brief
from alignmentgraph_isd.core.ratelimit import CallGate, gate_for

from conftest import FakeChatModel, load_brief


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
    _CountingModel.peak = _Peak()
    run_design_brief(
        load_brief("minimal_brief.json"),
        HarnessRunConfig(llm_factory=lambda: _CountingModel(), agent_mode="multi", **settings),
    )
    return _CountingModel.peak.peak


def test_multi_arm_fanout_respects_the_cap():
    """The regression this exists for: content/rubric fan out in one superstep."""
    assert _run_multi(llm_max_concurrency=1) == 1
    assert _run_multi(llm_max_concurrency=2) <= 2


def test_uncapped_multi_arm_really_does_run_calls_in_parallel():
    """Guards the test above from passing for the wrong reason — if the arm were
    sequential anyway, capping it would prove nothing."""
    assert _run_multi() > 1

"""Outbound-call gate: bounds how many LLM requests one run keeps in flight.

Why this exists. The harness is fully sequential, so the gate does not
currently bind. It answers a MEASURED failure of a concurrent pipeline that ran
two Designers in one superstep, each issuing a Developer call per work set:
N+M requests leaving the process at once from a SINGLE agent, which the
benchmark's rate posture (``-r``) counts as one unit, so the in-agent fan-out
was bounded by nothing. Any concurrent fan-out brings that back.

Measured against a shared endpoint capping concurrent requests per user, the
two multi arms took 9-25 HTTP 429s per run across three runs against 0-2 for
the sequential single arms. A dropped call costs a regen attempt and can leave
an artifact family thin, so that throttling difference sat squarely on the
``agent_mode`` axis.

Scope. Per-run (one per :class:`HarnessRunConfig`), NOT process-wide: the
benchmark runs several agents in one process, and a shared gate would make one
arm queue behind another and inflate its ``execution_time_seconds``. Total
in-flight is ``agents_in_flight x llm_max_concurrency``, both from the same
rate preset.

The endpoint's complaint is about CONCURRENCY, not request rate, so the cap
alone is the fix. ``min_interval_seconds`` is available for an endpoint that
also meters rate, and is off by default — wiring it to ``BENCHMARK_DELAY``
would put a 2 s sleep in front of every call of a run.
"""
from __future__ import annotations

import threading
import time
from contextlib import contextmanager


class CallGate:
    """Bounded concurrency (and optional spacing) for outbound LLM calls.

    ``max_concurrency <= 0`` disables the bound, which is the default for a
    standalone run — a package used outside the benchmark should not inherit
    the benchmark's posture.
    """

    def __init__(self, max_concurrency: int = 0, min_interval_seconds: float = 0.0) -> None:
        self.max_concurrency = max(0, int(max_concurrency))
        self.min_interval_seconds = max(0.0, float(min_interval_seconds))
        self._slots = (
            threading.BoundedSemaphore(self.max_concurrency)
            if self.max_concurrency > 0 else None
        )
        self._pace_lock = threading.Lock()
        self._next_start = 0.0

    @contextmanager
    def hold(self):
        """Occupy one slot for the duration of one request."""
        if self._slots is not None:
            self._slots.acquire()
        try:
            self._wait_for_turn()
            yield
        finally:
            if self._slots is not None:
                self._slots.release()

    def _wait_for_turn(self) -> None:
        if self.min_interval_seconds <= 0:
            return
        with self._pace_lock:
            now = time.monotonic()
            if self._next_start > now:
                time.sleep(self._next_start - now)
                now = self._next_start
            self._next_start = now + self.min_interval_seconds


_BUILD_LOCK = threading.Lock()

#: Shared no-op gate for callers with no config (tests, ad-hoc use). Unbounded,
#: so holding it costs nothing.
UNBOUNDED = CallGate()


def gate_for(config) -> CallGate:
    """The run's gate, built once per config object and cached on it.

    Every agent in a run is handed the SAME ``HarnessRunConfig`` instance (see
    the run's own config object), which is what makes the cache per-run.
    A config object that will not hold the attribute (a bare stub in a test)
    gets a fresh unbounded gate rather than an error.
    """
    if config is None:
        return UNBOUNDED
    gate = getattr(config, "_call_gate", None)
    if isinstance(gate, CallGate):
        return gate
    with _BUILD_LOCK:
        gate = getattr(config, "_call_gate", None)
        if isinstance(gate, CallGate):
            return gate
        gate = CallGate(
            max_concurrency=getattr(config, "llm_max_concurrency", 0) or 0,
            min_interval_seconds=getattr(config, "llm_min_interval_seconds", 0.0) or 0.0,
        )
        try:
            config._call_gate = gate
        except (AttributeError, ValueError):  # pragma: no cover - exotic config objects
            pass
        return gate

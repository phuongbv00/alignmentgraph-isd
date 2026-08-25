"""Outbound-call gate: bounds how many LLM requests one run keeps in flight.

Why this exists. The multi arm's LangGraph topology runs ``content_designer``
and ``rubric_designer`` in the SAME superstep, and since the 2026-08-28 dev-plan
fan-out each of those issues one ``Send`` — one Developer call — per work set.
Two families x N sets is N+M requests leaving the process at once, from a SINGLE
agent. The benchmark's rate posture (``-r``: agents x scenarios in flight, plus
``BENCHMARK_DELAY``) counts that whole agent as one unit, so the in-agent
fan-out was never bounded by anything.

Measured against a shared endpoint that caps concurrent requests per user
("Per-user concurrency limit exceeded. This user has 10 active units"), the two
multi arms took 9-25 HTTP 429s per run across three runs while the sequential
single arms took 0-2. Every dropped call costs a regen attempt and can leave an
artifact family thin or empty, so the throttling difference landed squarely on
the ``agent_mode`` ablation axis — the multi arms were being measured against a
handicap the single arms never carried.

Scope. The gate is per-run (one per :class:`HarnessRunConfig`), NOT process-wide.
The benchmark runs several agents concurrently in one process; a shared gate
would make one arm's fan-out queue in front of another arm's calls and inflate
that arm's ``execution_time_seconds``, which is exactly the kind of cross-arm
interference an ablation must not have. Total in-flight requests are therefore
``agents_in_flight x llm_max_concurrency``, both set from the same rate preset.

The endpoint's complaint is about CONCURRENCY, not request rate, so the cap
alone is the fix. ``min_interval_seconds`` is available for an endpoint that
also meters rate, and is off by default — wiring it to ``BENCHMARK_DELAY``
would put a 2 s sleep in front of every one of ~50 calls per run.
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
    ``workflow.NodeFactory._args``), which is what makes the cache per-run.
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

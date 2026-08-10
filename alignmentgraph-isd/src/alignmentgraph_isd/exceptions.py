"""Public exceptions.

Deliberately importable without pulling any of the harness in — the demo web
app raises ``HarnessCancelled`` from inside an ``on_event`` callback, so it must
be cheap to import from anywhere.
"""
from __future__ import annotations


class HarnessCancelled(BaseException):
    """Raised from an ``on_event`` consumer to abort the run in flight.

    Derives from ``BaseException``, not ``Exception``, on purpose. The harness
    swallows consumer errors (``TrajectoryLogger._emit``) and the node/agent
    layers catch ``Exception`` broadly to keep a run alive through a bad LLM
    reply; a cancellation must pass through all of that untouched.

    Cancellation is cooperative and only takes effect at the next emit point,
    so it cannot interrupt an LLM call that is already in flight — expect the
    run to stop within roughly one model call.
    """

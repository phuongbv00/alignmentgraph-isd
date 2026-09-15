"""What a run reports about ITSELF, as opposed to what it produces.

Two audiences, one module. For the RECORD: model provenance, token totals, and
the opt-in graph dump — the fields ``core/agentic/run.py`` assembles its
``metadata`` from. For a LIVE watcher: the safe-emit guarantee and the
``graph_snapshot`` wrapper, which is how the demo app sees the alignment graph
fill in during the 4-7 minutes a run takes.

Deliberately not named ``audit``: in this package that word means the residual
alignment audit of the finished DESIGN (``core/alignment_graph/audit.py``,
relation coverage — the auditability claim), and a second module claiming it
would put two meanings on the term the work stakes a claim on. Nothing here
looks at the design at all.

A leaf on purpose: nothing here imports ``core/agentic/`` or
``core/runner.py``, so ``runner`` can import it at module level.
"""
from __future__ import annotations

import os
import time
from pathlib import Path

from ..config import HarnessRunConfig
from .alignment_graph import AlignmentGraph
from .brief import DesignBrief
from .trajectory import TrajectoryLogger


def _llm_metadata(config: HarnessRunConfig) -> dict:
    """Model provenance for the record, read from the injected factory's model —
    the single source of truth — so it can never drift from what actually ran.
    Best-effort: introspection failures leave the fields blank, never break a run.
    ``model_name`` covers both ChatOpenAI (``model_name``) and ChatAnthropic
    (``model``)."""
    if config.llm_factory is None:
        return {}
    try:
        model = config.llm_factory()
        return {
            "model_name": getattr(model, "model_name", None) or getattr(model, "model", None) or "",
            "temperature": getattr(model, "temperature", None),
            "max_tokens": getattr(model, "max_tokens", None),
        }
    except Exception:  # noqa: BLE001 - metadata is never load-bearing
        return {}


def _token_usage_metadata(trajectory: TrajectoryLogger) -> dict:
    prompt = trajectory.token_usage.get("prompt_tokens", 0)
    completion = trajectory.token_usage.get("completion_tokens", 0)
    return {
        "prompt_tokens": prompt,
        "completion_tokens": completion,
        "total_tokens": prompt + completion,
        "llm_calls": trajectory.llm_calls,
    }


def _maybe_dump_graph(graph: AlignmentGraph, design_brief: DesignBrief, metadata: dict) -> None:
    """Write ``<brief_id>_graph.json`` when opted in via the
    ``ALIGNMENTGRAPH_DUMP_DIR`` env var. Opt-in and best-effort: a dump failure
    never breaks a run, it only annotates metadata."""
    dump_dir = os.environ.get("ALIGNMENTGRAPH_DUMP_DIR")
    if not dump_dir:
        return
    from .alignment_graph import viz

    brief_id = design_brief.id or "brief"
    stem = Path(dump_dir) / f"{brief_id}_graph"
    try:
        written = viz.dump(graph, stem, title=brief_id, design_brief_id=brief_id)
        metadata["graph_dump"] = [str(path) for path in written]
    except Exception as exc:  # noqa: BLE001 - visualization is never load-bearing
        metadata["graph_dump_error"] = str(exc)


# How often the live graph may be re-serialized while a phase is running. The
# graph is only meaningfully different after a specialist writes its nodes, so a
# consumer polling every edit would pay for ~55 snapshots to see ~14 distinct
# states. Phase boundaries are always snapshotted regardless of this floor.
_SNAPSHOT_MIN_INTERVAL_SECONDS = 0.75

# Kinds after which the graph is guaranteed to be in a consistent, worth-showing
# state. Everything else only triggers a snapshot once the interval above passes.
_SNAPSHOT_ALWAYS_AFTER = frozenset({"phase_finished"})


def _safe_emit(on_event, kind: str, payload: dict) -> None:
    """Emit from outside the TrajectoryLogger, with its same guarantees:
    a failing consumer is swallowed, but HarnessCancelled still propagates."""
    if on_event is None:
        return
    try:
        on_event(kind, payload)
    except Exception:  # noqa: BLE001 - observation is never load-bearing.
        pass


def _graph_attaching(on_event, graph: AlignmentGraph, design_brief: DesignBrief):
    """Wrap a consumer so it also receives ``graph_snapshot`` events.

    The alignment graph is the thing a viewer actually wants to watch, but it is
    not part of any recorded stream — it lives in the run's own scope. So the
    snapshot is attached where the graph object is in hand.

    The snapshot is produced (and must be consumed) synchronously on the worker
    thread: ``to_full_dict`` returns the live node/edge dicts, which later nodes
    keep mutating. A consumer that stashes the object and serializes it later
    will read torn or silently-updated state.
    """
    last_snapshot_at = 0.0

    def emit(kind: str, payload: dict) -> None:
        nonlocal last_snapshot_at
        on_event(kind, payload)
        now = time.monotonic()
        if kind not in _SNAPSHOT_ALWAYS_AFTER and (now - last_snapshot_at) < _SNAPSHOT_MIN_INTERVAL_SECONDS:
            return
        last_snapshot_at = now
        on_event("graph_snapshot", graph.to_full_dict(design_brief_id=design_brief.id))

    return emit


def _ledger_attaching(on_event, memory):
    """Wrap a consumer so it also receives ``violations_snapshot`` events.

    The ledger of what a run found wrong (``core.memory.Memory``) is the same
    kind of thing as the graph: live state in the run's own scope, not part of
    any recorded stream, and the thing a viewer most wants to watch fill in.
    So it is attached the same way, where the object is in hand.

    REV-GATED, not time-throttled. A real run mutates the ledger ~80-150 times
    (six owned families x ``SELF_VALIDATION_BUDGET`` rounds x ~2 mutators, once
    for the per-stage net and again in ``_reconcile``, plus the agent tier's
    ``_own_violations``/``_budget_stopped``) — roughly one every 2-4 seconds
    over a 4-7 minute run, already below any interval worth imposing. But
    ``RunState.append`` notifies on essentially every trajectory event, so a
    wrapper that fired on each of them would send ~400 frames, most of them
    byte-identical. The dedup that pays is on THIS side, and one integer
    comparison is the whole of it.

    Emits to the RAW consumer it was handed, so a snapshot never re-enters
    ``_graph_attaching`` — see the composition order in ``core/agentic/run.py``.
    Graph-snapshot cadence is unchanged by this wrapper existing.

    Never touches ``trajectory``: the ledger is not folded into it (the judge
    reads that and the benchmark compares it across arms), and going out
    through the consumer directly rather than through ``TrajectoryLogger.emit``
    makes that structural rather than a rule to remember.

    One aliasing note, because ``events.py`` asks for pre-serialized state:
    ``Finding.as_dict`` copies ``metadata`` shallowly, so a list-valued entry
    (``{"item_ids": [...]}``) is shared with whatever holds the frame. Safe as
    written — metadata is copied at first sighting and each check round builds
    fresh ``Violation`` objects rather than mutating the old ones — so this is
    said rather than paid for with a deep copy of every finding, every frame.
    """
    # Starts at the ledger's OWN starting revision, not below it: a run that
    # has not written a finding yet has nothing to say, and opening every run
    # with an empty frame would set `RunState.violations` to `[]` — which reads
    # as falsy, so `_live_or_persisted` would fall through to a `violations.json`
    # that does not exist yet. A clean run simply never sends one.
    sent_rev = memory.findings_rev

    def emit(kind: str, payload: dict) -> None:
        nonlocal sent_rev
        on_event(kind, payload)
        if memory.findings_rev == sent_rev:
            return
        sent_rev = memory.findings_rev
        # A dict, like every other payload on this channel: `on_event` is typed
        # `(kind, payload: dict)` and consumers read it as one. The findings go
        # out under a key rather than as the payload itself.
        on_event("violations_snapshot",
                 {"findings": [f.as_dict() for f in memory.findings]})

    return emit

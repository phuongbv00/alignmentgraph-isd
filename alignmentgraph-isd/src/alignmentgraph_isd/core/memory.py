"""What a run remembers, in one place.

Three things, and they answer three different questions about the same run:

* **transcripts** — what each agent was shown and said. Per agent, because the
  context boundary IS the ``agent_mode`` axis: ``multi`` gives each stage a
  fresh context under its own identity, ``single`` carries one across all six.
  Reading them side by side is how that axis is inspected rather than asserted.
* **graph** — the alignment state (or, in the ``prose`` arm, the blackboard).
  Exactly one substrate is live per run; which one is the ``context_mode``
  axis, so :class:`Memory` holds the live one and never both.
* **plans** — how each Designer divided its family into work sets before
  handing them to Developers, ROUND BY ROUND — what answers "which Developer
  was asked for what", the question a fan-out failure always turns into.

  Rounds, because a family is planned more than once: the Designer plans, the
  Developers write, the checks find gaps, and the gaps go back to the DESIGNER
  — whose answer is a new plan scoped to them, not artifacts of its own. Plan
  and write stay the two roles they are, and the second plan is the record of
  what the first one missed.

One object rather than three parameters, because the three are read TOGETHER
by everything that reasons about a RUN rather than a step: reconciliation wants
the graph and each violation's owner, a Designer fixing its family wants the
graph, the violations and its own plan, the Context tab wants transcripts and
the plan behind the Developer ones.

Deliberately NOT a god object. It stores; it does not decide. No check, repair,
commit or model call lives here — those take what they need off it.

**Never merged into the trajectory.** The judge reads ``trajectory`` and the
benchmark compares it across arms; transcripts alone would multiply its size
by the number of turns and change what is measured to serve a viewer. Memory
is returned beside it, and only to callers that ask.
"""
from __future__ import annotations

import threading
import uuid
from dataclasses import dataclass, field, replace

from . import repairs


def new_agent_run_id() -> str:
    """A fresh id for one AGENT RUN: one conversation, from its first message
    to its last.

    Minted where the conversation BEGINS, not derived from what it is about:
    a key hashed from ``(agent, phase, label, attempt)`` gave the re-dispatch round
    — which continues the Designer's own message list under a new step name
    — a different id, and the tab showed one conversation as two rows. No
    content-derived key can know that two labels are one conversation; an id
    the conversation carries does (``test_one_conversation_is_one_context``).

    A regenerated stage, a fan-out work set and each arm's design loop all
    start with a fresh message list, so each gets its own automatically —
    ``attempt`` stops being part of an identity and goes back to being a fact
    about the run.
    """
    return uuid.uuid4().hex[:12]


@dataclass(frozen=True)
class Transcript:
    """One context, as one agent saw it at one moment.

    A stage that is regenerated publishes one of these per attempt, and they
    share a label — ``attempt`` is what tells them apart, which is why the
    export addresses a transcript by ``id`` rather than by name.
    """

    #: The agent run this context belongs to (:func:`new_agent_run_id`) — one
    #: conversation, whatever it gets called along the way. A republish of the
    #: same agent run replaces the snapshot before it.
    id: str
    agent: str
    phase: str
    label: str
    attempt: int
    messages: list
    tools: list
    #: Token counts by part (system / messages / tools) plus the schemas and
    #: the budget they are measured against. Computed at publish time from the
    #: ratio measured on this run's own traffic, so a transcript recorded under
    #: one serving window still reads truthfully later.
    tokens: dict = field(default_factory=dict)

    def as_dict(self) -> dict:
        return {"id": self.id, "agent": self.agent, "phase": self.phase,
                "label": self.label, "attempt": self.attempt,
                "messages": self.messages, "tools": self.tools, **self.tokens}


@dataclass(frozen=True)
class Plan:
    """One family's division into work sets, as the Designer decided it.

    ``source`` is the honest part: ``"deterministic"`` — no model proposes a
    grouping, every family derives its sets from an artifact of the design —
    or ``"fallback"`` when there was nothing to derive from, which says the
    stage before it produced nothing to divide. Each set carries its OWN
    ``source`` (``derived`` / ``appended`` / ``fallback``), which is the finer
    question: whether the design covered this obligation or the harness had to.
    """

    stage: str
    family: str
    source: str
    work_sets: tuple = ()
    stats: dict = field(default_factory=dict)
    #: 0 for the family's first division; 1+ for a re-dispatch of the sets
    #: that still owed work after their Developers ran.
    round: int = 0
    #: The violation types this round was asked to close. Empty on round 0.
    answers: tuple[str, ...] = ()

    def as_dict(self) -> dict:
        return {"stage": self.stage, "family": self.family, "source": self.source,
                "round": self.round, "answers": list(self.answers),
                "work_sets": [ws.as_dict() for ws in self.work_sets],
                "stats": dict(self.stats)}


@dataclass(frozen=True)
class Finding:
    """One violation, followed across the run.

    Its identity is ``checks.Violation.key`` — built from the SUBJECT of the
    finding, never the evidence — because a violation is re-derived from state
    by a pure function every round and has no continuous object to carry an id
    the way a :class:`Transcript` does.

    ``messages`` is a tuple because one finding can be reported more than one
    way: a relation's establisher says "this material matched no media
    selection" and the coverage sweep says "this material has no P6 coverage",
    which is the same fact stated twice by two producers. Collapsing them is
    right; losing the more specific wording is not.
    """

    key: str
    #: The whole Violation, so a finding can be routed, explained and re-found.
    node_id: str
    edge_type: str
    violation_type: str
    severity: str
    repair_hint: str
    metadata: dict
    target_designer: str
    messages: tuple[str, ...] = ()

    #: Where and when it was first seen, and how long it lasted.
    first_round: int = 0
    first_phase: str = ""
    first_family: str = ""
    last_round: int = 0
    sightings: int = 0
    #: Rounds in which it reached a model through ``loop.repair_request``.
    shown_to_agent: int = 0

    #: ``open`` | ``repaired_by_harness`` | ``repaired_by_agent``
    outcome: str = "open"
    #: Only meaningful while ``outcome == "open"``, and the whole point of the
    #: ledger: WHY it is still here.
    #:
    #: ``converged`` — tried and could not be fixed;
    #: ``budget``    — a repair/turn/re-dispatch budget ran out first;
    #: ``unowned``   — no family owns the type, so nobody was ever asked;
    #: ``unseen``    — filtered out of the agent's view (element-node filter,
    #:                 a work set's own loop).
    #:
    #: This is the line between a finding about the MODEL and a fact about the
    #: HARNESS. Reporting them merged would be a wrong claim in the paper: "the
    #: model could not fix this" and "we did not give it another turn" are
    #: different results, and only the second is ours to change.
    open_reason: str = ""
    #: True when the deterministic net is DESIGNED never to touch this type.
    #: Orthogonal to ``outcome``, not a value of it: ``repairs.REPORT_ONLY``
    #: constrains the harness and not the agent, so "report-only AND repaired
    #: by the agent" is reachable — and is exactly the evidence that the agent
    #: tier does work the net cannot.
    report_only: bool = False
    repaired_by: str = ""
    repaired_at_round: int = 0
    converged_at_round: int = 0

    @property
    def message(self) -> str:
        return self.messages[0] if self.messages else ""

    def as_dict(self) -> dict:
        return {
            "key": self.key, "node_id": self.node_id, "edge_type": self.edge_type,
            "type": self.violation_type, "severity": self.severity,
            "messages": list(self.messages), "repair_hint": self.repair_hint,
            "metadata": dict(self.metadata), "target_designer": self.target_designer,
            "first_round": self.first_round, "first_phase": self.first_phase,
            "first_family": self.first_family, "last_round": self.last_round,
            "sightings": self.sightings, "shown_to_agent": self.shown_to_agent,
            "outcome": self.outcome, "open_reason": self.open_reason,
            "report_only": self.report_only, "repaired_by": self.repaired_by,
            "repaired_at_round": self.repaired_at_round,
            "converged_at_round": self.converged_at_round,
        }


class Memory:
    """The run's memory: transcripts per agent, the alignment state, the plans.

    Exactly one of ``graph``/``store`` is live — that is the ``context_mode``
    axis — and :attr:`state` is whichever it is, which is what every check,
    commit and view already takes.
    """

    def __init__(self, *, graph=None, store=None) -> None:
        if (graph is None) == (store is None):
            raise ValueError("exactly one of graph/store is live per run "
                             "(context_mode); holding both or neither would "
                             "make the axis unreadable")
        self.graph = graph
        self.store = store
        self._transcripts: list[Transcript] = []
        self._transcript_index: dict[str, int] = {}
        self._plans: dict[str, list[Plan]] = {}
        self._findings: dict[str, Finding] = {}
        self._findings_rev = 0
        # One lock for every mutator and snapshot: a parallel fan-out's
        # workers publish contexts and the orchestrator writes findings on
        # the main thread at the same time. Re-entrant, since a mutator may
        # read a snapshot of its own store.
        self._lock = threading.RLock()

    # ── the substrate ───────────────────────────────────────────────────────
    @classmethod
    def of(cls, state) -> "Memory":
        """Memory around a bare substrate, for a caller that only has one.

        Tests build a graph and run one loop over it; the fan-out builds a
        step and runs it. Neither needs a plan book or a transcript store, and
        requiring them to construct one would push this object into every
        signature that merely touches a node."""
        if isinstance(state, Memory):
            return state
        return cls(graph=state) if hasattr(state, "element_nodes") else cls(store=state)

    @property
    def state(self):
        return self.graph if self.graph is not None else self.store

    # ── transcripts ─────────────────────────────────────────────────────────
    def remember_context(self, transcript: Transcript) -> None:
        """Keep the LATEST snapshot of each context, in first-seen order.

        A loop publishes its context after every turn while a run is being
        watched, so this is called many times for one conversation; appending
        would make ``result["contexts"]`` a pile of prefixes of itself. Held in
        place, the last one wins and the order is when each agent first spoke,
        which is the order a reader wants."""
        with self._lock:
            existing = self._transcript_index.get(transcript.id)
            if existing is None:
                self._transcript_index[transcript.id] = len(self._transcripts)
                self._transcripts.append(transcript)
            else:
                self._transcripts[existing] = transcript

    @property
    def transcripts(self) -> tuple[Transcript, ...]:
        """Every context published this run, in the order it was published —
        which under a parallel fan-out is the order the workers first spoke,
        not the plan's order."""
        with self._lock:
            return tuple(self._transcripts)

    @property
    def agents(self) -> tuple[str, ...]:
        """Who spoke this run, first appearance first. In ``single`` this is
        one name; in ``multi`` it is the roster, which is the axis showing."""
        seen: list[str] = []
        for transcript in self._transcripts:
            if transcript.agent not in seen:
                seen.append(transcript.agent)
        return tuple(seen)

    # ── plans ───────────────────────────────────────────────────────────────
    def remember_plan(self, plan: Plan) -> None:
        with self._lock:
            self._plans.setdefault(plan.stage, []).append(plan)

    @property
    def plans(self) -> tuple[Plan, ...]:
        with self._lock:
            return tuple(plan for rounds in self._plans.values() for plan in rounds)

    # ── findings ────────────────────────────────────────────────────────────
    def _write(self, key: str, finding: Finding) -> None:
        """The ONE way a finding is written, so the revision cannot be
        forgotten.

        Every mutator below rebuilds a frozen ``Finding`` and puts it back;
        routing all of them through here means a future fifth mutator has to
        touch the private dict directly to bypass the counter, which is a
        review-visible act in a way a forgotten call never is."""
        with self._lock:
            self._findings[key] = finding
            self._findings_rev += 1

    @property
    def findings_rev(self) -> int:
        """Bumped on every write. What a live watcher polls to know the ledger
        moved, so it never re-serializes one that has not.

        A counter and not a callback: `Memory` still stores and does not
        decide. It publishes nothing and calls nobody, which is also why it
        cannot become a cancellation point — the consumer that raises
        ``HarnessCancelled`` stays on the emit side, where it already was."""
        return self._findings_rev

    def observe_violations(self, violations, *, round: int, phase: str = "",
                           family: str = "", shown_to_agent: bool = False):
        """Record one check round. Returns the key set it saw.

        Returned rather than recomputed by the caller, because the caller needs
        exactly this set for its convergence test and computing the keys twice
        is how the two drift.
        """
        seen: set[str] = set()
        for violation in violations:
            key = violation.key
            seen.add(key)
            existing = self._findings.get(key)
            message = violation.message
            if existing is None:
                self._write(key, Finding(
                    key=key, node_id=violation.node_id, edge_type=violation.edge_type,
                    violation_type=violation.violation_type, severity=violation.severity,
                    repair_hint=violation.repair_hint, metadata=dict(violation.metadata),
                    target_designer=violation.target_designer,
                    messages=(message,) if message else (),
                    first_round=round, first_phase=phase, first_family=family,
                    last_round=round, sightings=1,
                    shown_to_agent=1 if shown_to_agent else 0,
                    report_only=(violation.violation_type in repairs.REPORT_ONLY
                                 or violation.violation_type not in repairs.OWNER_BY_VIOLATION),
                    open_reason=("unowned"
                                 if violation.violation_type not in repairs.OWNER_BY_VIOLATION
                                 else ""),
                ))
                continue
            self._write(key, replace(
                existing,
                last_round=round,
                sightings=existing.sightings + 1,
                shown_to_agent=existing.shown_to_agent + (1 if shown_to_agent else 0),
                # A later pass stamps the owner; the first sighting has none.
                target_designer=violation.target_designer or existing.target_designer,
                messages=(existing.messages if message in existing.messages
                          else existing.messages + (message,)),
            ))
        return frozenset(seen)

    def credit_repair(self, closed, *, by: str, round: int, harness: bool) -> None:
        """The keys a repair pass actually closed — ``before - after`` around
        one ``repairs.repair`` call.

        A DIFF, never a match on repair events: ``repairs._log_repair`` is
        called with a class id (``str(NodeType.ASSESSMENT)``) in most routines,
        so joining on node_id would silently credit nobody.
        """
        for key in closed:
            existing = self._findings.get(key)
            if existing is None or existing.outcome != "open":
                continue
            self._write(key, replace(
                existing, repaired_by=by, repaired_at_round=round, open_reason="",
                outcome="repaired_by_harness" if harness else "repaired_by_agent"))

    #: Which reason survives when a finding collects more than one.
    #:
    #: The order is "how much of this is OURS". ``unowned`` means it never
    #: entered a repair loop at all; ``budget`` means we cut it short;
    #: ``converged`` means it was genuinely tried and could not be fixed. A
    #: reconciliation pass that converges after a stage ran out of repair turns
    #: must NOT overwrite ``budget`` with ``converged`` — the deterministic net
    #: converging is trivially true for a type it is not allowed to touch,
    #: while "the agent never got its third turn" is a parameter we chose and
    #: the one a reader can act on.
    #: ``unseen`` outranks ``converged``: a type the net may not touch
    #: converges trivially, and reading that as "the agent tried" would credit
    #: the model with a look it never got.
    _REASON_PRECEDENCE = ("unowned", "budget", "unseen", "converged", "unexplained")

    def shown_keys(self) -> set[str]:
        """The findings some agent has actually been shown.

        ``shown_to_agent`` is stamped only by ``repair_turn.stamp_shown``, on
        a state read the agent CHOSE to make after being pointed at its open
        issues — so this is the set that can honestly be called looked at."""
        return {key for key, finding in self._findings.items()
                if finding.shown_to_agent}

    def mark_open_reason(self, keys, *, reason: str, round: int = 0) -> None:
        """Why these are still here — set where the run gave up on them, so a
        budget stop is never read as something the model could not do."""
        order = self._REASON_PRECEDENCE
        for key in keys:
            existing = self._findings.get(key)
            if existing is None or existing.outcome != "open":
                continue
            current = existing.open_reason
            if current in order and order.index(current) <= order.index(reason):
                # Already explained by something at least as strong; only the
                # round of an actual convergence is still worth recording.
                if reason == "converged" and not existing.converged_at_round:
                    self._write(key, replace(existing, converged_at_round=round))
                continue
            self._write(key, replace(
                existing, open_reason=reason,
                converged_at_round=round if reason == "converged"
                else existing.converged_at_round))

    def settle(self, open_keys) -> None:
        """Called once on the run's final re-derived residual.

        Anything the last look did not see is closed; anything it did see and
        that nothing has explained yet is open for a reason nobody recorded,
        which is itself worth saying rather than defaulting to "converged"."""
        remaining = frozenset(open_keys)
        for key, finding in list(self._findings.items()):
            if key in remaining:
                if not finding.open_reason:
                    self._write(key, replace(finding, open_reason="unexplained"))
                continue
            if finding.outcome == "open":
                self._write(key, replace(
                    finding, outcome="repaired_by_agent" if finding.shown_to_agent
                    else "repaired_by_harness", open_reason=""))

    @property
    def findings(self) -> tuple[Finding, ...]:
        with self._lock:
            return tuple(self._findings.values())

    def as_dict(self) -> dict:
        """The inspectable dump. Not part of ``trajectory`` and never sent to
        the judge — see the module docstring."""
        return {
            "agents": list(self.agents),
            "transcripts": [t.as_dict() for t in self._transcripts],
            "plans": [p.as_dict() for p in self.plans],
            "findings": [f.as_dict() for f in self.findings],
        }

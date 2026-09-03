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
  handing them to Developers, ROUND BY ROUND. This one was previously not
  remembered at all: a plan was computed inside ``_run_fanout``, used to build
  prompts, summarised into a trajectory event, and dropped. Nothing could
  afterwards answer "which Developer was asked for what", which is the
  question a fan-out failure always turns into.

  Rounds, because a family is planned more than once: the Designer plans, the
  Developers write, the checks find gaps, and the gaps go back to the DESIGNER
  — whose answer is a new plan scoped to them, not artifacts of its own. Plan
  and write stay the two roles they are, and the second plan is the record of
  what the first one missed.

Why one object rather than three parameters. The three are read TOGETHER, by
everything that reasons about a run rather than about one step: the
reconciliation pass wants the graph and the owner of each violation; a
Designer asked to fix its family's output wants the graph, the violations and
the plan it made; the Context tab wants transcripts and the plan that produced
the Developer ones. Passing them separately meant each such caller grew its
own subset and its own assembly order, and a caller that needed a fourth thing
threaded it through every frame in between.

It is deliberately NOT a god object. It stores; it does not decide. There is
no check, repair, commit or model call here — those live where they already
do, and take what they need off it.

**Never merged into the trajectory.** The judge reads ``trajectory`` and the
benchmark compares it across arms; transcripts alone would multiply its size
by the number of turns and change what is measured to serve a viewer. Memory
is returned beside it, and only to callers that ask.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field


def new_agent_run_id() -> str:
    """A fresh id for one AGENT RUN: one conversation, from its first message
    to its last.

    Minted where the conversation BEGINS, not derived from what it is about.
    That distinction is the whole point, and it was learned the hard way: the
    first version hashed ``(agent, phase, label, attempt)``, and the replan
    round — which continues the Designer's own message list under a new step
    name — hashed to a different id. The tab then showed the same conversation
    twice, the second row containing the first, which is precisely the
    split-block problem the in-loop repair was built to remove. No content-
    derived key can know that two labels are one conversation; an id the
    conversation carries does.

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
    export addresses a transcript by index rather than by name.
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

    ``source`` is the honest part: ``"llm"`` when the Designer's own dev plan
    was used, ``"fallback"`` when it was absent or unusable and the sets were
    derived deterministically. A run where every family reads ``fallback`` is
    a run where the planning half of the design was never exercised — which is
    exactly what was happening, unnoticed, until the dev plan was given
    somewhere to live (see ``specialists.commit_assessment``).
    """

    stage: str
    family: str
    source: str
    work_sets: tuple = ()
    stats: dict = field(default_factory=dict)
    #: 0 for the Designer's first division of the family; 1+ for a plan it made
    #: in answer to violations found after its Developers ran.
    round: int = 0
    #: The violation types this round was asked to close. Empty on round 0.
    answers: tuple[str, ...] = ()

    @property
    def from_the_agent(self) -> bool:
        return self.source == "llm"

    def for_set(self, set_id: str):
        """The work set with this id — what a Developer was actually asked for."""
        return next((ws for ws in self.work_sets if ws.set_id == set_id), None)

    def as_dict(self) -> dict:
        return {"stage": self.stage, "family": self.family, "source": self.source,
                "round": self.round, "answers": list(self.answers),
                "work_sets": [ws.as_dict() for ws in self.work_sets],
                "stats": dict(self.stats)}


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

    @property
    def graph_mode(self) -> bool:
        return self.graph is not None

    # ── transcripts ─────────────────────────────────────────────────────────
    def remember_context(self, transcript: Transcript) -> None:
        """Keep the LATEST snapshot of each context, in first-seen order.

        A loop publishes its context after every turn while a run is being
        watched, so this is called many times for one conversation; appending
        would make ``result["contexts"]`` a pile of prefixes of itself. Held in
        place, the last one wins and the order is when each agent first spoke,
        which is the order a reader wants."""
        existing = self._transcript_index.get(transcript.id)
        if existing is None:
            self._transcript_index[transcript.id] = len(self._transcripts)
            self._transcripts.append(transcript)
        else:
            self._transcripts[existing] = transcript

    @property
    def transcripts(self) -> tuple[Transcript, ...]:
        """Every context published this run, in the order it was published."""
        return tuple(self._transcripts)

    def transcripts_of(self, agent: str) -> tuple[Transcript, ...]:
        return tuple(t for t in self._transcripts if t.agent == agent)

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
        self._plans.setdefault(plan.stage, []).append(plan)

    def plan_for(self, stage: str) -> Plan | None:
        """The stage's LATEST plan — what its Developers were last asked for."""
        rounds = self._plans.get(stage)
        return rounds[-1] if rounds else None

    def rounds_for(self, stage: str) -> tuple[Plan, ...]:
        """Every plan this stage made, first to last. More than one means the
        checks sent work back and the Designer re-planned it."""
        return tuple(self._plans.get(stage) or ())

    def next_round(self, stage: str) -> int:
        return len(self._plans.get(stage) or ())

    @property
    def plans(self) -> tuple[Plan, ...]:
        return tuple(plan for rounds in self._plans.values() for plan in rounds)

    def as_dict(self) -> dict:
        """The inspectable dump. Not part of ``trajectory`` and never sent to
        the judge — see the module docstring."""
        return {
            "agents": list(self.agents),
            "transcripts": [t.as_dict() for t in self._transcripts],
            "plans": [p.as_dict() for p in self.plans],
        }

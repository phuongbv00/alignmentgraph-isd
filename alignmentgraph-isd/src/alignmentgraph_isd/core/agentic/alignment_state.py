"""``read_alignment_state``: what a role needs to know about the design, as
SIGNALS rather than as raw graph.

One argument-less tool, scoped by the step it is bound for. It answers the
three questions an agent otherwise spends its turns assembling from lists,
edges and coverage queries:

* what EXISTS that this stage builds on — one row per artifact, with its id
  and the short facets the rules compare against (``level``,
  ``plan_category``, ``type``, ``aligned_objective``). Ids, never counts:
  every cross-artifact edge in this design is an id the model writes, so a
  state that said "4 activities exist" would leave it nothing to reference;
* what is MISSING that this stage's output must close — the uncovered side of
  the relations in the step's docket, and the plan-promised pairs nobody has
  realised. An enumerated checklist over a universally-quantified rule is the
  deterministic scaffolding SLMs measurably need;
* the OPEN ISSUES in what this stage itself committed — its own family's
  violations, in the checks' own words, and nobody else's.

MEASURED, the cost this replaces: reads were 184 of 270 tool calls on run
14a6b4c7 and 78 of 133 on run 9efc3cfa, each a full round trip of ~3.5k prompt
tokens for a few hundred characters; ``read_edges`` mostly answered "(no …
edges yet)"; and 50 of 63 ERROR observations over runs 53042a0d and 2559b22d
were a list tool and a read tool being reached for through each other's door.
One list-shaped tool with no arguments has no wrong door.

It is a TOOL the agent calls, not text pushed at it: reading the state, acting
on it, reading it again and fixing what is left is the agent's own loop, in one
transcript. PURE — it reads and returns — because the repeat guard re-derives a
read to tell a changed state from a repeated call (``turn.answer_read``); the
structural pre-fixes that WRITE are ``repair_turn.fix_structural`` and run
after a commit. Full text of any one artifact stays ``read_node``.

Graph mode only. The prose substrate holds documents and no alignment state,
which is the ``context_mode`` treatment and not an omission.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from .. import checks, dev_plans
from ..alignment_graph import NodeType, alignment
from . import repair_turn, tools
from .protocol import landed_parts
from .specialists import missing_parts

#: The same ceiling as any other single read (``tools.READ_CHAR_BUDGET``), so a
#: graph state read and a prose ``read_document`` are held to one number.
STATE_CHAR_BUDGET = tools.READ_CHAR_BUDGET


@dataclass
class StateView:
    """One state read: the text, and the violations it rendered and the ones
    it only counted — the split ``repair_turn.stamp_shown`` records."""
    text: str
    shown: list = field(default_factory=list)
    unshown: list = field(default_factory=list)


def read(state, design_brief, step, *, submit_tool: str = "") -> StateView:
    """The alignment state of ``step``'s stage, as the design stands.

    ``submit_tool`` is the tool the caller's next write goes through, named
    in the closing line. That line is the LAST thing in the result, and a
    small model weights the last instruction heaviest: MEASURED (run
    4bb81369), a closing line that ended "...then call this again" was
    obeyed to the letter — 26 consecutive state reads, no submit, the stage
    lost to its turn ceiling. So it names the WRITE and nothing after it."""
    missing_lines, named = _missing(state, step)
    missing_lines += _module_ceiling(state, design_brief, step)
    issues: list = []
    if not missing_parts(step, state):
        # Before every part has landed, a coverage "violation" and the gap
        # line above are one fact, and nothing of the agent's exists to judge.
        issues = repair_turn.collect_own(state, design_brief, step)
    issue_lines, shown, unshown = repair_turn.violation_lines(issues)
    named |= {tools.bare_ref(str(v.node_id)) for v in shown}

    tail: list[str] = ["[MISSING — your output must close these]"]
    tail += missing_lines or ["(nothing)"]
    tail.append("[OPEN ISSUES — in what you committed]"
                + (f" ({len(issues)})" if issues else ""))
    tail += issue_lines or ["(none)"]
    via = f" with {submit_tool}" if submit_tool else ""
    if issues:
        tail.append(f"NEXT: fix these now — submit only the artifact that changes{via}.")
    elif missing_lines or missing_parts(step, state):
        tail.append(f"NEXT: write what is missing and submit it now{via}.")
    else:
        tail.append("NEXT: nothing open — this stage checks out.")

    head = [f"=== ALIGNMENT STATE — {step.name} ==="]
    yours = _yours(state, step)
    pools = [(node_type, *_pool(state, node_type)) for node_type in step.readable_types]
    pools = [pool for pool in pools if pool[1]]
    listed = len(pools) + (1 if yours[1] else 0)
    # Headings, and the "... and N more not shown" line each listing may end
    # on, are paid for up front so that line is never the one the cut takes.
    spent = sum(len(line) + 1 for line in head + tail) + len(yours[0]) + 200 * (listed + 1)
    wants = [len(tools.render_listing(nodes, budget=10 ** 9)) if elements
             else len(tools.render_nodes(nodes, budget=10 ** 9))
             for _type, nodes, elements in pools]
    if yours[1]:
        wants.append(len(tools.render_listing(yours[1], budget=10 ** 9)))
    shares = _shares(wants, STATE_CHAR_BUDGET - spent)

    body: list[str] = ["[EXISTS — what this stage builds on]"]
    if not step.readable_types:
        body.append(f"{step.name} builds on the scenario alone; there is no earlier "
                    "state to align with.")
    elif not pools:
        body.append("(nothing yet)")
    for (node_type, nodes, elements), share in zip(pools, shares):
        body.append(f"{node_type}:")
        body.append(_rows(nodes, share, named) if elements
                    else tools.render_nodes(nodes, budget=share))
    body.append("[YOURS — committed by this stage]")
    body.append(yours[0])
    if yours[1]:
        body.append(_rows(yours[1], shares[-1], named))

    # The shares keep this inside the budget; if a pathological design does
    # not, it is the LISTING that gives way, never the actionable tail.
    tail_text = "\n".join(tail)
    room = STATE_CHAR_BUDGET - len(tail_text) - 1
    text = "\n".join(head + body)[:room] + "\n" + tail_text
    return StateView(text=text, shown=shown, unshown=unshown)


def _shares(wants: list[int], room: int) -> list[int]:
    """Split ``room`` characters between listings that want ``wants``: a pool
    that fits is given what it needs and the rest is shared among the others.

    An EVEN split starves the one large pool beside small ones. MEASURED (run
    1c0a4e81, content): the state read used 3,325 of 8,000 characters and
    still cut 71 of 94 activities, because the topic and constraint pools
    held a row each and kept a third of the budget apiece — and an activity
    the Content Designer cannot see is one no media selection will serve."""
    shares = [0] * len(wants)
    open_ = sorted(range(len(wants)), key=lambda i: wants[i])
    while open_:
        even = max(tools.NODE_CHAR_CAP, room // len(open_))
        index = open_.pop(0)
        shares[index] = min(wants[index] + 1, even) if wants[index] <= even else even
        room = max(0, room - shares[index])
    return shares


def _module_ceiling(state, design_brief, step) -> list[str]:
    """This run's module ceiling, while the modules are still to be written.

    The RULE is in the stage's prompt; the NUMBER depends on this course — how
    many objectives and topics it has and how long it runs — so it is stated
    here, where every per-run fact the agent acts on is. Told, not enforced
    (``dev_plans.MODULES_BY_COURSE_HOURS``)."""
    docket = getattr(step, "docket", None) or {}
    if not docket.get("module_ceiling") or state.element_nodes(NodeType.MODULE):
        return []
    objectives = len(state.element_nodes(NodeType.OBJECTIVE))
    topics = len(state.element_nodes(NodeType.TOPIC))
    hours = checks.duration_hours(design_brief) if design_brief is not None else 0.0
    ceiling = dev_plans.module_ceiling(objectives, topics, hours)
    length = f"about {hours:g} h" if hours else "length not stated"
    lines = [f"course_modules: at most {ceiling} for this course "
             f"({objectives} objectives, {topics} topics, {length})"]
    if hours:
        # MEASURED (run b8576814): a 2-4 week course was given three modules
        # of 40 minutes. The rule says the minutes add up to the course; this
        # is the number they add up to.
        lines.append(f"the modules' minutes together: about {int(hours * 60)} "
                     f"({hours:g} h of learner time)")
    return lines


def _pool(state, node_type: str) -> tuple[list[dict], bool]:
    """A type's element pool, or its section node when it has none (the
    learner profile, the plan nodes). The flag says which: elements are LISTED
    a row each, while a section node IS a whole document and a one-line
    listing of one is useless."""
    elements = state.element_nodes(node_type)
    return (elements, True) if elements else (state.section_nodes(node_type), False)


def _rows(nodes: list[dict], share: int, named: set[str]) -> str:
    """Listing rows within ``share`` characters. When a pool overflows its
    share, the artifacts a gap or an issue NAMES go first: they are the
    prerequisite data for what is about to be written, and a row cut by the
    budget is an id the model cannot reference."""
    if len(tools.render_listing(nodes, budget=10 ** 9)) > share:
        nodes = sorted(nodes, key=lambda n: tools.bare_ref(str(n.get("id", ""))) not in named)
    return tools.render_listing(nodes, budget=share)


def _yours(state, step) -> tuple[str, list[dict]]:
    landed = landed_parts(step, state)
    line = ("committed: " + ", ".join(landed)) if landed else "(nothing yet)"
    own = state.element_nodes(step.primary_type) if step.primary_type else []
    if step.primary_type in step.readable_types:
        own = []        # already listed under EXISTS
    return line, own


def _missing(state, step) -> tuple[list[str], set[str]]:
    """The gap lines for the relations this step's output closes, and the bare
    ids they name. BARE ids: a node id is namespaced (``objective:ILO-01``) and
    a model echoes back what it is shown, into fields every matcher compares
    bare — measured on a single-graph run, ``lo_coverage_targets`` keyed by
    namespaced ids made ``plan_coverage`` report every promised pair
    unrealised."""
    docket = getattr(step, "docket", None) or {}
    lines: list[str] = []
    named: set[str] = set()
    for rid in docket.get("gaps", ()):
        relation = alignment.REGISTRY[rid]
        _, uncovered = alignment.relation_coverage(state, rid)
        if not uncovered:
            continue
        ids = [tools.bare_ref(one) for one in uncovered]
        named.update(ids)
        extra = len(ids) - tools.GAP_ID_CAP
        lines.append(f"{relation.key} ({relation.label}) missing for: "
                     + ", ".join(ids[:tools.GAP_ID_CAP])
                     + (f" (+{extra} more)" if extra > 0 else ""))
    if docket.get("plan_pairs"):
        pairs = [(v.metadata.get("lo_id", ""), v.metadata.get("plan_category", ""))
                 for v in checks.plan_coverage(state)]
        if pairs:
            named.update(objective for objective, _category in pairs)
            lines.append("plan-promised pairs not yet realised — produce exactly these: "
                         + "; ".join(f"{o} x {c}" for o, c in pairs))
    return lines, named

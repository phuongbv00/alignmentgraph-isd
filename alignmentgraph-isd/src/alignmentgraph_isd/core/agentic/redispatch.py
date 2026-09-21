"""When the Developers leave a gap, the same work is dispatched again.

The loop this closes. A family's work sets are derived from the design
(``fanout.SPECS[...].plan_sets``), its Developers write them, and the checks
then find an objective with no assessment item, an activity nothing prepares
for, an activity nobody scheduled. The deterministic net cannot write
instructional content (``core/repairs.py``), so without this the gap reaches
nobody who can act on it.

The answer is a second DISPATCH, not a second plan. Two kinds of set run:

* a set that is NEW — the Designer amended the blueprint during its own
  repair turns (``checks.blueprint_consistency``), so a set now
  exists that had no work set in round 0;
* a set that already ran and still OWNS an open gap — its Developer wrote
  less than the set was commissioned for.

The second kind is re-run with the gap named in its assignment
(``still_missing``), which is what makes it produce the missing element
rather than what it already wrote: a commit drops a repeat
(``dev_plans.without_repeats``), so a blind re-run would produce nothing.

Three things keep it bounded, and each answers a way this could hang on a
small model:

* **The gaps decide which sets run.** Nothing re-runs a set with no gap of
  its own, so a round can only ask for work that is missing.
* **Round-tagged set ids.** ``AS-SET-01`` from round 0 is committed; its
  round-1 re-run is ``AS-SET-01R1``. Without the tag it collides with the
  committed one and ``fanout.committed_set_ids`` skips it, so the round runs
  and produces nothing.
* **One round.** ``REDISPATCH_ROUNDS`` is 1. A gap that survives a fresh
  Developer call with the gap spelled out is a gap the model cannot close,
  and asking again is how a stage turns into a hang.

No Designer call: the grouping is derived from the design, so there is
nothing for a Designer to say here that its own repair turns did not already
ask it. That is also why this module composes no prompt.
"""
from __future__ import annotations

import re

from dataclasses import replace

from .. import dev_plans, repairs

#: Which families can be re-dispatched, and on which gaps. A family is here
#: only when its gaps map exactly onto work the Developer tier can be asked
#: for: an uncovered objective is an item or an activity somebody has to
#: write. ``content`` is absent on purpose — the checks it owns are
#: structural (``P5``, repaired exactly by a lookup) or report-only (``P6``,
#: ``P8``), so there is no gap a fresh material call closes.
REDISPATCHABLE: dict[str, dict] = {
    # P14: a module with no item at all is its sets' items unwritten.
    "assessment": {"gap_types": ("C2", "P3", "P14", "plan_coverage"),
                   "noun": "assessment item"},
    # P13: a module nothing is taught in is a block nobody wrote for.
    "activities": {"gap_types": ("C3", "C4", "P13"), "noun": "learning activity"},
    # P10/P11 are REPORT_ONLY for the deterministic net — appending an id to a
    # finished guide would invent a delivery record that never happened
    # (``audit.AUDIT_ONLY_VIOLATION_TYPES``). That rule is about the HARNESS
    # writing: asking a Developer to schedule what nobody scheduled is the
    # writing it holds out for, not a way around it.
    "implementation": {"gap_types": ("P10", "P11"), "noun": "session guide"},
}


def gaps_for(stage: str, violations: list) -> list:
    """The violations of ``stage`` a fresh Developer call could actually close."""
    spec = REDISPATCHABLE.get(stage)
    if not spec:
        return []
    return [v for v in violations
            if getattr(v, "violation_type", "") in spec["gap_types"]]


def _metadata(gap) -> dict:
    return getattr(gap, "metadata", None) or {}


def _gap_objectives(gap) -> list[str]:
    """The objectives one gap is about: the one it names, or — for a module
    nothing was written for (P13/P14) — every objective that module serves."""
    metadata = _metadata(gap)
    named = [str(metadata.get("lo_id") or "")] + [str(o) for o in metadata.get("lo_ids") or []]
    return [objective for objective in named if objective]


def _gap_element(gap) -> tuple[str, str]:
    """``("activity", "TLA-0203")`` for a gap anchored on an element."""
    node_id = str(_metadata(gap).get("node_id") or getattr(gap, "node_id", "") or "")
    node_type, _, bare = node_id.partition(":")
    return (node_type, bare) if bare else ("", "")


def next_session(state) -> int:
    """Where a second dispatch's session numbering starts: one past the
    highest a committed guide already carries.

    Round 0's numbers are handed out before any Developer runs
    (``dev_plans._number_sessions``), so a second round numbering from one
    again would put two "session 1" in the same deliverable — the same reason
    :func:`tag_round` strides the artifact ordinal."""
    if hasattr(state, "element_nodes"):
        guides = [n.get("data") or {} for n in state.element_nodes("session_guide")]
    else:
        guides = [g for g in state.items("implementation_plan", "session_guides")
                  if isinstance(g, dict)]
    highest = 0
    for guide in guides:
        try:
            highest = max(highest, int(guide.get("session")))
        except (TypeError, ValueError):
            continue
    return highest + 1


def tag_round(work_sets: list, round_index: int) -> list:
    """``AS-SET-01`` -> ``AS-SET-01R1``, and its artifacts' ids out of round
    0's way.

    Two things, both load-bearing. Round 0's sets are already committed and
    ``fanout.committed_set_ids`` reads the ``plan_set`` stamp, so a re-run
    carrying the same set id is treated as already done and never runs — the
    suffix is what makes the round happen at all.

    And the ORDINAL is what every artifact id is composed from
    (``dev_plans._composite_id``), so a re-run reusing ordinal 1 would try to
    name its work ``AT-0101`` again. Striding it puts round 1 at ``AT-5101``,
    which also reads as "written in the second round"."""
    return [replace(ws, set_id=f"{ws.set_id}R{round_index}",
                    ordinal=ws.ordinal + round_index * dev_plans.ROUND_ORDINAL_STRIDE)
            for ws in work_sets]


def _base_set_id(set_id: str) -> str:
    """``AS-SET-01R1`` -> ``AS-SET-01``. A round suffix is this harness's
    (``tag_round``), so a gap left by round 1 still belongs to the set the
    next round derives under its own name."""
    return re.sub(r"R\d+$", "", str(set_id or ""))


def _owns(stage: str, work_set, gap) -> bool:
    """Whether this set is the one that should have produced what is missing.

    The work set that WROTE the element answers first. A gap about a reference
    that resolves to nothing names no objective, so the objective-based tests
    below cannot claim it and it was dropped — measured on run 43c4ca5e, every
    one of the 12 C3 gaps, although ``REDISPATCHABLE`` lists C3 for this
    family. ``plan_set`` is on the element because the commit stamped it."""
    # Only for a gap the deterministic net may NOT close. Paying a Developer
    # call to write what a lookup settles is the waste this whole module is
    # bounded to avoid: MEASURED (run 7123a976), 19 dangling C4s — every one
    # of them `repaired_by_harness` in the round that followed — re-dispatched
    # all three activity blocks, which wrote 10 more activities, spent 6
    # Developer calls instead of 3 and changed nothing. A REPORT_ONLY type has
    # no such lookup, so a writer is the only route it has.
    plan_set = str(_metadata(gap).get("plan_set") or "")
    if (plan_set and str(getattr(gap, "violation_type", "")) in repairs.REPORT_ONLY
            and plan_set == _base_set_id(work_set.set_id)):
        return True
    if stage == "assessment":
        pairs = set(work_set.pairs)
        category = str(_metadata(gap).get("plan_category") or "").strip().lower()
        objectives = set(_gap_objectives(gap))
        if category:
            return any((lo, category) in pairs for lo in objectives)
        return bool(objectives & {lo for lo, _ in pairs})
    if stage == "activities":
        return bool(set(_gap_objectives(gap)) & set(work_set.objectives))
    node_type, bare = _gap_element(gap)
    key = {"activity": "activity_ids", "material": "material_ids"}.get(node_type)
    return bool(key) and bare in (work_set.payload.get(key) or [])


def redo(stage: str, gaps: list, work_sets: list, committed: set, round_index: int) -> list:
    """The sets a second dispatch runs, in plan order.

    A set the state has never seen runs because it is new work; a set it has
    seen runs only if some gap is its own, and is told which
    (``still_missing``) — a commit drops a repeat, so a re-run that is not
    told what is missing produces nothing."""
    if stage not in REDISPATCHABLE or not gaps:
        return []
    out: list = []
    for work_set in work_sets:
        if work_set.set_id not in committed:
            out.append(work_set)
            continue
        mine = [g for g in gaps if _owns(stage, work_set, g)]
        if not mine:
            continue
        out.append(replace(work_set, payload={
            **work_set.payload,
            "still_missing": [str(getattr(g, "message", g)) for g in mine]}))
    return tag_round(out, round_index)

"""The agent tier of repair: which violations reach the agent, and how they
are put to it.

The deterministic net (``core/repairs.py``) rearranges what the design already
holds. Anything that needs WRITING goes back to the agent that owns it, as a
repair turn inside that agent's own tool loop — so the request, the model's
answer and the artifact are three consecutive turns of ONE transcript, and no
second conversation is opened in that agent's name.

ONE implementation for both arms. The arms differ in who holds the context;
they must not differ in which violations an agent is shown or in the words they
are shown in, or an outcome difference could be read off the wording.
"""
from __future__ import annotations

from .. import repairs
from ..checks import serialize_violations
from ..outputs import _collect_violations, _collect_violations_prose
from ..trajectory import ORCHESTRATOR
from . import budget
from .fanout import SPECS


def own_violations(state, design_brief, step, trajectory) -> list:
    """This stage's own violations — only the ones this agent, right now,
    can actually clear with a submit.

    Structural fixes run FIRST and are not shown: a dangling reference or
    a Bloom verb from the taxonomy is fixed exactly by a lookup. What
    reaches the agent is the part that needs WRITING.

    Two things are not that part, and both are measured (test fixture) to
    consume every repair turn in the run:

    * **A work set's own loop sees nothing.** Its commit is a no-op — the
      driver deposits all sets once the loops close — so the state cannot
      show what this Developer just submitted, and every violation it would
      be handed is one its own submit answered. All five
      AssessmentDevelopers were shown the same `C2`/`plan_coverage` gap
      they had each just filled.
    * **A Designer whose family has a Developer tier sees only its own
      sections.** That family's element-level checks (`C2`,
      `plan_coverage`, `item_completeness`, the Bloom cross-check) read
      artifacts the tier has not written yet, so the Designer is asked to
      fix an absence it has no schema to fill: the AssessmentDesigner spent
      all four turns re-reading the same nodes and wrote
      ``{"action": "Add C2 link for ILO-01"}`` into its plan — the
      appearance of a fix, which is what `REPORT_ONLY` exists to prevent.

    Neither is dropped from the run: the deterministic net and the
    reconciliation pass collect both again, and what nothing can fix is
    counted as residual.
    """
    fix_structural(state, design_brief, step, trajectory)
    return collect_own(state, design_brief, step)


def _families(step) -> list[str]:
    return [f for f in (step.family, *step.also_repairs) if f in repairs.OWNED_BY_FAMILY]


def _owned(state, design_brief, families: list[str]) -> list:
    graph_mode = hasattr(state, "element_nodes")
    found: list = []
    for family in families:
        violations = (_collect_violations(family, state, design_brief)
                      if graph_mode
                      else _collect_violations_prose(family, state))
        found += [v for v in violations
                  if v.violation_type in repairs.OWNED_BY_FAMILY[family]]
    return found


def fix_structural(state, design_brief, step, trajectory) -> None:
    """The free fixes, applied to the state: a dangling reference or a Bloom
    verb from the taxonomy is fixed exactly by a lookup, so it is never put to
    an agent. The ONLY half of :func:`own_violations` that writes, and the
    orchestrator's act — run after a commit, never inside a read, because a
    read that rewrote the design would make the read tools impure (the repeat
    guard re-derives a read to compare it) and would book a harness repair
    under an agent's tool call."""
    if not step.commits_to_state:
        return
    graph_mode = hasattr(state, "element_nodes")
    families = _families(step)
    ctx = repairs.RepairContext(
        graph=state if graph_mode else None,
        store=None if graph_mode else state,
        trajectory=trajectory, actor=ORCHESTRATOR)
    for family in families:
        structural = [v for v in _owned(state, design_brief, families)
                      if v.violation_type in repairs.STRUCTURAL
                      and v.violation_type in repairs.OWNED_BY_FAMILY[family]]
        if structural:
            repairs.repair(family, structural, ctx)


def collect_own(state, design_brief, step) -> list:
    """What this agent can clear with a submit, as the state stands. PURE: it
    reads and returns, which is what lets ``read_alignment_state`` call it.

    Everything the family owns, INCLUDING the REPORT_ONLY types. That set
    says the deterministic net must not write content — it never said the
    agent cannot. These are precisely the violations only a writer can answer
    (an activity with no engagement strategy, a criterion its rubric
    contradicts), and the agent is the writer."""
    if not step.commits_to_state:
        return []
    remaining = _owned(state, design_brief, _families(step))
    if hasattr(state, "element_nodes") and step.name in SPECS:
        # The tier has not run. A section node is what this Designer wrote;
        # an element node is what its Developers will write.
        sep = type(state).ELEMENT_SEP
        remaining = [v for v in remaining if sep not in str(v.node_id)]
    return remaining


def violation_lines(violations: list) -> tuple[list[str], list, list]:
    """The lines an agent is shown for ``violations``, and which of them that
    is: ``(lines, shown, unshown)``. Capped at ``REPAIR_REQUEST_CAP`` with the
    overflow counted, and the split returned because only what was actually
    RENDERED may be stamped as shown in the ledger."""
    shown = list(violations[:budget.REPAIR_REQUEST_CAP])
    unshown = list(violations[budget.REPAIR_REQUEST_CAP:])
    lines = []
    for violation in shown:
        hint = getattr(violation, "repair_hint", "")
        lines.append(f"- {getattr(violation, 'message', violation)}"
                     + (f"\n  Fix: {hint}" if hint else ""))
    if unshown:
        lines.append(f"- (+{len(unshown)} more of the same kind)")
    return lines, shown, unshown


def repair_request(stage: str, violations: list, round_index: int, rounds: int) -> str:
    """The user turn that hands a stage its own violations back.

    Deliberately concrete: each line is the check's own message plus its repair
    hint, because "fix the alignment" is the class of instruction this codebase
    has twice measured a small model failing to act on. The stage is named and
    the round is counted so the agent knows it is not starting over.
    """
    lines, _shown, _unshown = violation_lines(violations)
    return (
        f"COMMITTED, but {stage} does not check out yet "
        f"(round {round_index} of {rounds}):\n"
        + "\n".join(lines)
        + "\n\nFix these and submit the corrected artifact. Submit only what "
          "changes — what you have already committed stays committed. If a "
          "point is wrong or you cannot act on it, submit nothing and say why."
    )


def violations_for_agent(state, design_brief, step, *, trajectory, memory,
                         identity: str, phase: str) -> list:
    """:func:`own_violations`, plus the note in the ledger that they reached an
    agent. The bare function is for callers that only have a state (tests,
    one-offs) and no memory to write to.

    Every other check round pairs ``trajectory.log_violations_result`` (the
    ``check`` event ``aggregate._review_findings`` reads to synthesize
    ``expert_review.findings``) with ``memory.observe_violations`` (the ledger
    ``result["violations"]`` serves), so a violation whose ONLY sighting is
    here — a report-only type like P10/P11, which skips the deterministic net —
    must reach both.

    Attributed to ``ORCHESTRATOR`` like every other check round
    (``test_work_done_outside_a_tool_loop_is_the_orchestrator_s``): the agent's
    own act is answering the repair-request turn, not running the check that
    produced it.
    """
    found = own_violations(state, design_brief, step, trajectory)
    _lines, shown, unshown = violation_lines(found)
    stamp_shown(shown, unshown, trajectory=trajectory, memory=memory,
                identity=identity, phase=phase, family=step.family)
    return found


def stamp_shown(shown: list, unshown: list, *, trajectory, memory, identity: str,
                phase: str, family: str) -> None:
    """ONE check round in the record for what an agent was just shown.

    ``shown_to_agent`` is what ``Memory.settle`` reads to credit a finding
    that later disappears to the agent rather than to the harness, so it is
    stamped on the violations that were RENDERED and on no others: past
    ``REPAIR_REQUEST_CAP`` a violation is only counted ("+N more"), the agent
    never read it, and crediting the agent with its repair would be a claim
    the transcript does not support. The rest are still sighted, in the same
    round."""
    if not shown and not unshown:
        return
    round_no = trajectory.log_violations_result(
        serialize_violations(shown + unshown, identity), agent=ORCHESTRATOR)
    if shown:
        memory.observe_violations(shown, round=round_no, phase=phase,
                                  family=family, shown_to_agent=True)
    if unshown:
        memory.observe_violations(unshown, round=round_no, phase=phase,
                                  family=family, shown_to_agent=False)

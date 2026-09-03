"""When the Developers leave a gap, the DESIGNER plans the next round.

The loop this closes. A Designer divides its family into work sets; its
Developers write them; the checks then find that some objective still has no
assessment item, or some objective no activity. Until now that gap reached
nobody who could act on it: the Developers' loops had closed, the Designer's
had closed, and the deterministic net cannot write instructional content
(``core/repairs.py``). It was recorded as residual and shipped.

Sending it to the Designer keeps the two roles the design already has. A
Designer plans and does not write; a Developer writes what it is assigned. So
the answer to "ILO-02 has no item" is not an item — it is a **work set**, and
the Developer tier runs it exactly as it ran the first round. What the round
costs is one Designer call plus one Developer call per gap set.

Three things keep it bounded, and each answers a way this could hang on a
small model:

* **The ground truth is the GAPS, not the family.** A replan normalizes
  against coverage targets built from the violations themselves, so the plan
  can only ask for work that is missing. Re-normalizing the family would
  re-derive every set it already has.
* **Round-tagged set ids.** ``AS-01`` from round 0 is committed; a round-1 set
  is ``AS-01R1``. Without the tag the new sets collide with the committed ones
  and ``committed_set_ids`` skips all of them, so the round runs and produces
  nothing.
* **One round.** ``REPLAN_ROUNDS`` is 1. A gap that survives a Designer
  re-plan and a fresh Developer call is a gap the model cannot close, and
  asking again is how a stage turns into a hang.

The Designer answers in ITS OWN transcript — the replan is a new user turn on
the message list its stage loop built, so the request, the plan and the work
that followed read as one conversation. That is also why it is a ``ToolLoop``
over ``loop.messages`` rather than a second prompt: one agent, one system
prompt (``tests/test_one_agent_one_system_prompt.py``).
"""
from __future__ import annotations

from dataclasses import replace

from .. import rulebook as rules
from .. import dev_plans
from ..dev_plans import WorkSet

#: Replan rounds per family, per run.
REPLAN_ROUNDS = 1

#: Turns the Designer gets to answer with a plan. It has the gaps in front of
#: it and one artifact to submit; more than this is a model that is not going
#: to.
REPLAN_TURNS = 4


def _wrapped(schema: str) -> str:
    """The schema as the ``submit_dev_plan`` TOOL asks for it.

    The rulebook states a dev plan bare (``{"instrument_sets": […]}``) because
    a stage submit nests it under ``dev_plan``. The replan's only tool takes
    that key as its parameter, so a bare schema tells the model to send the
    inside of the envelope and the submit is rejected for a missing key it was
    never shown. Built the same way the stage schemas are (specialists.py)."""
    return '{\n  "dev_plan": ' + schema.replace("\n", "\n  ") + "\n}"


#: Which families can be replanned, and what a plan for them is made of. A
#: family is here only when its gaps map exactly onto work the Developer tier
#: can be asked for: an uncovered objective is an item or an activity somebody
#: has to write. ``content`` is absent on purpose — the checks it owns are
#: structural (``orphan_content``, ``P5``, repaired exactly by a lookup) or
#: report-only (``C5``), so there is no gap a new module assignment closes.
REPLANNABLE: dict[str, dict] = {
    "assessment": {
        "schema": _wrapped(rules.SCHEMA_ASSESSMENT_DEV_PLAN),
        "rules": rules.RULES_ASSESSMENT_DEV_PLAN,
        "gap_types": ("C2", "P3", "plan_coverage"),
        "noun": "assessment item",
    },
    "activities": {
        "schema": _wrapped(rules.SCHEMA_ACTIVITY_DEV_PLAN),
        "rules": rules.RULES_ACTIVITY_DEV_PLAN,
        "gap_types": ("C3", "C4"),
        "noun": "learning activity",
    },
}


def gaps_for(stage: str, violations: list) -> list:
    """The violations of ``stage`` a new work set could actually close."""
    spec = REPLANNABLE.get(stage)
    if not spec:
        return []
    return [v for v in violations
            if getattr(v, "violation_type", "") in spec["gap_types"]]


def gap_targets(gaps: list, plan_targets: dict | None = None) -> dict:
    """Coverage targets naming exactly the gaps: ``{objective: [category…]}``.

    A ``plan_coverage`` violation names its category, so the replan asks for
    that category and no other. A ``C2`` names only the objective — the
    categories then come from what the plan itself promised for it, and fall
    back to summative, because an objective with no item at all needs at least
    one and a summative one is the weakest claim that closes it.
    """
    promised = plan_targets or {}
    targets: dict[str, list[str]] = {}
    for gap in gaps:
        metadata = getattr(gap, "metadata", None) or {}
        objective = str(metadata.get("lo_id") or "")
        if not objective:
            continue
        category = str(metadata.get("plan_category") or "").strip().lower()
        bucket = targets.setdefault(objective, [])
        for candidate in ([category] if category else
                          _promised_for(promised, objective)):
            if candidate and candidate not in bucket:
                bucket.append(candidate)
    return {objective: cats for objective, cats in targets.items() if cats}


def _promised_for(promised: dict, objective: str) -> list[str]:
    entry = promised.get(objective)
    if isinstance(entry, list):
        found = [str(c).strip().lower() for c in entry if isinstance(c, str)]
        found += [str(c.get("plan_category", "")).strip().lower()
                  for c in entry if isinstance(c, dict)]
        found = [c for c in found if c]
        if found:
            return found
    return ["summative"]


def objectives_of(gaps: list) -> tuple[str, ...]:
    """The objectives a replan is about — the activity families' ground truth."""
    seen: list[str] = []
    for gap in gaps:
        objective = str((getattr(gap, "metadata", None) or {}).get("lo_id") or "")
        if objective and objective not in seen:
            seen.append(objective)
    return tuple(seen)


def tag_round(work_sets: list, round_index: int) -> list:
    """``AS-01`` -> ``AS-01R1``, and its artifacts' ids out of round 0's way.

    Two things, both load-bearing. Round 0's sets are already committed and
    ``committed_set_ids`` reads the ``plan_set`` stamp, so a round-1 set
    numbered ``AS-01`` again is treated as already done and never runs — the
    suffix is what makes the round happen at all.

    And the ORDINAL is what every artifact id is composed from
    (``dev_plans._composite_id``), so a replan set reusing ordinal 1 would try
    to name its work ``AT-0101`` again. Striding it puts round 1 at
    ``AT-5101``, which also reads as "written in the second round"."""
    return [WorkSet(set_id=f"{ws.set_id}R{round_index}", objectives=ws.objectives,
                    pairs=ws.pairs, payload=ws.payload, source=ws.source,
                    ordinal=ws.ordinal + round_index * dev_plans.ROUND_ORDINAL_STRIDE)
            for ws in work_sets]


def request(stage: str, gaps: list, round_index: int) -> str:
    """The user turn that asks the Designer for the next round's plan."""
    spec = REPLANNABLE[stage]
    lines = [
        f"Your Developers have finished round {round_index - 1}, and the "
        f"design still has gaps that only new {spec['noun']}s can close:",
        "",
    ]
    for gap in gaps[:12]:
        lines.append(f"- {gap.message}")
    if len(gaps) > 12:
        lines.append(f"- (+{len(gaps) - 12} more of the same kind)")
    lines += [
        "",
        "You are NOT writing them. Submit a dev_plan covering EXACTLY these "
        "gaps and nothing else — one work set per group of gaps a single "
        f"{spec['noun']} genuinely covers — and a Developer will write each "
        "set. Do not re-plan work that is already done: everything not listed "
        "above stays as it is.",
        "",
        "If a gap listed above cannot be closed by new work, submit nothing "
        "and say why.",
    ]
    return "\n".join(lines)


def step_for(step, stage: str, gaps: list, round_index: int):
    """The Designer's stage step, narrowed to "submit a plan for these gaps".

    Same identity and same persona, because it is the same agent taking
    another turn in the conversation it is already in. What changes is the
    task, the one artifact it may submit, and the produced-guard: its dev_plan
    field is filled from round 0, so the default guard would report the step
    finished before it had been asked anything.
    """
    spec = REPLANNABLE[stage]
    return replace(
        step,
        name=f"{step.name}:replan{round_index}",
        intro=request(stage, gaps, round_index),
        schema=spec["schema"],
        rules=spec["rules"],
        submit_fields=(("dev_plan", "object", True),),
        submit_parts=(),
        validate=_validate_plan,
        done=lambda _state: False,
        # No docket: the gaps ARE the assignment, rendered above in full.
        docket={},
    )


def _validate_plan(parsed: dict) -> list[str]:
    plan = (parsed or {}).get("dev_plan")
    if not isinstance(plan, dict) or not plan:
        return ["dev_plan must be a non-empty object naming the work sets that "
                "close the gaps listed above"]
    if not any(isinstance(value, list) and value for value in plan.values()):
        return ["dev_plan names no work sets; list them under instrument_sets "
                "(assessment) or activity_blocks (activities)"]
    return []

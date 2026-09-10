"""Rebuilds ``tests/fixtures/golden_prompts.json`` from the live rulebook-
composed prompts. Run this by hand ONLY after a deliberate wording change to
a specialist/Developer system prompt or a single-arm task constant —
``test_composed_prompts_match_golden_fixture`` exists precisely to catch an
ACCIDENTAL drift, so regenerating the fixture to make that test pass again
without having intended the change defeats its purpose.

Usage:
    cd alignmentgraph-isd && python tests/regen_golden_prompts.py
"""
from __future__ import annotations

import json
from pathlib import Path


def composed_prompts() -> dict[str, str]:
    """Every prompt the golden fixture pins.

    Until 2026-09-01 this also pinned the six scripted specialists' and
    ``SingleDesignerAgent``'s prompt constants; they went with the StateGraph
    pipeline. What remains is what both decomposition arms actually compose
    from — the agentic step table, its bound tool schemas, and the CHECK
    MESSAGES a repair turn puts in front of the model.
    """
    return {**_agentic_prompts(), **_check_messages()}


def _ceiling_briefs() -> dict:
    """Briefs that pin each rung of the ILO-ceiling policy.

    Written here rather than read from ``tests/fixtures/*.json`` so the pin
    does not move when a fixture brief is edited for an unrelated reason.
    """
    from alignmentgraph_isd.core.brief import DesignBrief

    goals3 = ["goal one", "goal two", "goal three"]
    goals4 = goals3 + ["goal four"]
    return {
        "short3": DesignBrief(context={"duration": "Short-term intensive (within 1 week)"},
                              learning_goals=goals3),
        "mid3": DesignBrief(context={"duration": "Mid-term course (2-4 weeks)"},
                            learning_goals=goals3),
        "long4": DesignBrief(context={"duration": "Long-term course (1-6 months)"},
                             learning_goals=goals4),
        "no_goals": DesignBrief(context={"duration": "Long-term course (1-6 months)"}),
    }


def _agentic_prompts() -> dict[str, str]:
    """The executor's own comparability surface.

    Under native tool calling the prompt is only half of what the model sees —
    the bound TOOL SCHEMAS are the other half, and a change to either is a
    change to what the ladder measured. So both are pinned: the per-stage
    block (task + rules — no schema text since 2026-09-08, see
    ``AgenticStep.task_block`` — plus, for ``outcomes``, one rendering per
    rung of the brief-derived ILO ceiling), the shared workflow overview, and the
    serialized tool specs for each stage in each context mode — which is
    where an artifact's field-level SHAPE now lives
    (``artifact_schemas.ARTIFACT_SCHEMAS``, reached through
    ``tool_specs``'s ``parameters``), so pinning the specs already pins it."""
    from alignmentgraph_isd.core.agentic import fanout
    from alignmentgraph_isd.core.agentic import tools as agentic_tools
    from alignmentgraph_isd.core.agentic import compaction
    from alignmentgraph_isd.core.agentic.loop import _WORKFLOW_OVERVIEW, compaction_note
    from alignmentgraph_isd.core.agentic.specialists import SINGLE_PERSONA, STEPS

    _CEILING_BRIEFS = _ceiling_briefs()

    pinned: dict[str, str] = {
        "agentic._WORKFLOW_OVERVIEW": _WORKFLOW_OVERVIEW,
        "agentic.SINGLE_PERSONA": SINGLE_PERSONA,
    }
    for step in STEPS:
        pinned[f"agentic.{step.name}.persona"] = step.persona
        pinned[f"agentic.{step.name}.task_block"] = step.task_block()
        if step.rules_vars is not None:
            # The one step whose rules carry a per-BRIEF number (the ILO
            # ceiling). Pinning a single rendering would pin the template and
            # leave the POLICY — the short/mid/long multipliers and the
            # per-goal scaling — unpinned, so a change to the numbers would
            # turn no test red. A change to them is a change to what the ladder
            # measured, exactly like a reworded rule. Each pinned brief fixes
            # its own number, so the keys are stable.
            for label, brief in _CEILING_BRIEFS.items():
                pinned[f"agentic.{step.name}.task_block.{label}"] = (
                    step.task_block(brief))
        for context_mode, graph_mode in (("graph", True), ("prose", False)):
            specs = agentic_tools.tool_specs(step, graph_mode=graph_mode)
            pinned[f"agentic.{step.name}.tools.{context_mode}"] = json.dumps(
                specs, ensure_ascii=False, indent=2, sort_keys=True)

    # A fanned-out family's artifacts are written by DEVELOPERS, and a stage's
    # own `task_block` shows only the plan's rules — so until 2026-09-06 the
    # rules (and, until 2026-09-08, the schema) that produce every assessment
    # item, activity and material were pinned nowhere, and a change to one of
    # them landed with no fixture diff to review. That is the same hole
    # `_check_messages` was added to close. The SHAPE is pinned once, at its
    # single source (``ARTIFACT_SCHEMAS``), rather than per family here —
    # every family reading the same key would otherwise pin the same JSON
    # under several names.
    for name, spec in sorted(fanout.SPECS.items()):
        for output in spec.outputs:
            key = f"agentic.{name}.developer.{output.schema_key}"
            pinned[f"{key}.rules"] = output.rules
    for artifact_key, schema in sorted(agentic_tools.ARTIFACT_SCHEMAS.items()):
        pinned[f"agentic.artifact_schema.{artifact_key}"] = json.dumps(
            schema, ensure_ascii=False, indent=2, sort_keys=True)

    # The compaction note is prompt surface both arms see verbatim, like the
    # workflow overview beside it — and since 2026-09-06 it also carries what a
    # trim took, which is an instruction the model acts on.
    pinned["agentic.compaction_note"] = compaction_note(1)["content"]
    pinned["agentic.compaction_note.brief_lost"] = compaction_note(
        1, ("implementation",))["content"]
    pinned["agentic.compaction_note.summary"] = compaction_note(
        1, summary="Objectives ILO-01..03 established.")["content"]

    # The compaction HOOK's own prompt. Not an agent's — the agent never sees
    # it — but it decides the content of a PROTECTED, never-trimmed message
    # that every subsequent agent turn reads, in both arms, after every
    # compaction. A reworded task there changes what the ladder measured with
    # no test turning red, which is the same hole `_check_messages` below was
    # added to close.
    pinned["agentic.compaction.system"] = compaction._SYSTEM
    pinned["agentic.compaction.task"] = compaction._TASK
    return pinned


def _check_messages() -> dict[str, str]:
    """What a repair turn actually says, per violation type.

    ``loop._repair_request`` renders ``message`` and ``repair_hint`` VERBATIM
    into a user turn, in both arms — so a check's wording is prompt surface
    exactly like a persona or a tool schema. It was the only such surface
    nothing pinned: a reworded check changed what every agent was asked to fix
    and turned no test red, which is precisely the accidental drift this
    fixture exists to catch.

    Rendered over ``tests/fixtures/broken_design.py``, a fixed graph built to
    provoke every check. Grouped by violation type and sorted, so the pin does
    not depend on check order or on dict iteration.
    """
    import sys
    from pathlib import Path as _Path

    sys.path.insert(0, str(_Path(__file__).parent / "fixtures"))
    from broken_design import broken_graph                     # noqa: E402

    from alignmentgraph_isd.core import checks                 # noqa: E402

    graph = broken_graph()
    produced: list = []
    for name in ("bloom_verbs", "measurability", "rubric_consistency", "plan_coverage",
                 "item_completeness", "evaluation_quality", "activity_engagement",
                 "orphan_content", "evidence_alignment", "actionability",
                 "relation_coverage", "bloom_mismatches"):
        produced += getattr(checks, name)(graph)

    by_type: dict[str, set[str]] = {}
    for violation in produced:
        # Exactly the two lines _repair_request renders, in its own shape.
        rendered = f"- {violation.message}"
        if violation.repair_hint:
            rendered += f"\n  Fix: {violation.repair_hint}"
        by_type.setdefault(violation.violation_type, set()).add(rendered)
    return {f"checks.messages.{vtype}": "\n".join(sorted(rendered))
            for vtype, rendered in by_type.items()}


def main() -> None:
    fixture_path = Path(__file__).parent / "fixtures" / "golden_prompts.json"
    composed = composed_prompts()
    fixture_path.write_text(
        json.dumps(composed, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"Wrote {len(composed)} prompts to {fixture_path}")


if __name__ == "__main__":
    main()

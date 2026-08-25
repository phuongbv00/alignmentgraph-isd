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
    """Every prompt constant the golden fixture pins, keyed
    ``"<module-shortname>.<CONSTANT_NAME>"``. Kept as one function (not
    inlined in the test) so the test and the regen script can never drift
    from each other on WHICH constants are pinned."""
    from alignmentgraph_isd.core.agents import (
        activity_designer, activity_developer, assessment_designer, assessment_developer,
        content_designer, implementation_planner, material_developer,
        outcome_designer, rubric_developer, single_designer,
    )

    return {
        "outcome._SYSTEM_ANALYZE": outcome_designer._SYSTEM_ANALYZE,
        # Course goal (Hop B1) then objectives grounded in it (Hop B2) —
        # split 2026-08-28 from one combined call (see
        # OutcomeDesignerAgent's docstring).
        "outcome._SYSTEM_GOAL": outcome_designer._SYSTEM_GOAL,
        "outcome._SYSTEM_DESIGN": outcome_designer._SYSTEM_DESIGN,
        # Assessment: dispatch (plan, then dev-plan grouping) + per-set Developer.
        "assessment._SYSTEM_PLAN": assessment_designer._SYSTEM_PLAN,
        "assessment._SYSTEM_DEV_PLAN": assessment_designer._SYSTEM_DEV_PLAN,
        "assessment_developer._SYSTEM": assessment_developer._SYSTEM,
        # Activities: same shape as assessment.
        "activity._SYSTEM_PLAN": activity_designer._SYSTEM_PLAN,
        "activity._SYSTEM_DEV_PLAN": activity_designer._SYSTEM_DEV_PLAN,
        "activity_developer._SYSTEM": activity_developer._SYSTEM,
        # Content: dispatch is deterministic grouping (no dev-plan LLM call).
        "content._SYSTEM_MODULES": content_designer._SYSTEM_MODULES,
        "material_developer._SYSTEM": material_developer._SYSTEM,
        # Rubrics: no dispatch call at all — only the per-item Developer.
        "rubric_developer._SYSTEM": rubric_developer._SYSTEM,
        "implementation._SYSTEM": implementation_planner._SYSTEM,
        # Single arm: one persona + one task per state (dispatch task for the
        # three dev-plan families, plus their own per-set task).
        "single._SYSTEM": single_designer._SYSTEM,
        "single._TASK_ANALYSIS": single_designer._TASK_ANALYSIS,
        "single._TASK_OUTCOMES": single_designer._TASK_OUTCOMES,
        "single._TASK_ASSESSMENT": single_designer._TASK_ASSESSMENT,
        "single._TASK_ASSESSMENT_ITEMS": single_designer._TASK_ASSESSMENT_ITEMS,
        "single._TASK_ACTIVITIES": single_designer._TASK_ACTIVITIES,
        "single._TASK_ACTIVITY_SET": single_designer._TASK_ACTIVITY_SET,
        "single._TASK_CONTENT": single_designer._TASK_CONTENT,
        "single._TASK_MATERIALS_UNIT": single_designer._TASK_MATERIALS_UNIT,
        "single._TASK_RUBRICS": single_designer._TASK_RUBRICS,
        "single._TASK_IMPLEMENTATION": single_designer._TASK_IMPLEMENTATION,
    }


def main() -> None:
    fixture_path = Path(__file__).parent / "fixtures" / "golden_prompts.json"
    composed = composed_prompts()
    fixture_path.write_text(
        json.dumps(composed, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"Wrote {len(composed)} prompts to {fixture_path}")


if __name__ == "__main__":
    main()

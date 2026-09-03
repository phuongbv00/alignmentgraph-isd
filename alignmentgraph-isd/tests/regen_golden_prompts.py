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
    from — the agentic step table and its bound tool schemas — which is now the
    whole comparability surface rather than half of it.
    """
    return _agentic_prompts()


def _agentic_prompts() -> dict[str, str]:
    """The executor's own comparability surface.

    Under native tool calling the prompt is only half of what the model sees —
    the bound TOOL SCHEMAS are the other half, and a change to either is a
    change to what the ladder measured. So both are pinned: the per-stage block
    (task + schema + rules), the shared workflow overview, and the serialized
    tool specs for each stage in each context mode."""
    from alignmentgraph_isd.core.agentic import tools as agentic_tools
    from alignmentgraph_isd.core.agentic.loop import _WORKFLOW_OVERVIEW
    from alignmentgraph_isd.core.agentic.specialists import SINGLE_PERSONA, STEPS

    pinned: dict[str, str] = {
        "agentic._WORKFLOW_OVERVIEW": _WORKFLOW_OVERVIEW,
        "agentic.SINGLE_PERSONA": SINGLE_PERSONA,
    }
    for step in STEPS:
        pinned[f"agentic.{step.name}.persona"] = step.persona
        pinned[f"agentic.{step.name}.task_block"] = step.task_block()
        for context_mode, graph_mode in (("graph", True), ("prose", False)):
            specs = agentic_tools.tool_specs(step, graph_mode=graph_mode)
            pinned[f"agentic.{step.name}.tools.{context_mode}"] = json.dumps(
                specs, ensure_ascii=False, indent=2, sort_keys=True)
    return pinned


def main() -> None:
    fixture_path = Path(__file__).parent / "fixtures" / "golden_prompts.json"
    composed = composed_prompts()
    fixture_path.write_text(
        json.dumps(composed, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"Wrote {len(composed)} prompts to {fixture_path}")


if __name__ == "__main__":
    main()

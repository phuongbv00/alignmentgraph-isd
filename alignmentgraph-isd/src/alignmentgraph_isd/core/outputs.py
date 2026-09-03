"""What every run needs, on either side of both ablation axes: the shared
budget, the check runners, and the empty ADDIE skeleton.

Split out of ``workflow.py`` on 2026-09-01, when the scripted StateGraph
pipeline was removed. These were the only things the executor took
from that module, and none of them was ever about graph topology — they are
about the ARTIFACTS: which checks a family owns, whether a section came back
empty, and what an unfilled output looks like.
"""
from __future__ import annotations

from . import checks
from .validation import (
    PLACEHOLDER_FIELD_MARKER, validate_section,
)

#: The two ways a required field can be "there but not really there". Both are
#: what the regen loop reacts to, on either side of both axes.
_EMPTY_FIELD_MARKER = "required field is missing or empty"


SELF_VALIDATION_BUDGET = 2


def _empty_required_fields(section_type: str, data: dict) -> list[str]:
    """Required fields that came back unusable: missing/empty, or filled with
    schema placeholder text copied verbatim (equally absent to a reader, but
    invisible to a plain emptiness check)."""
    return [
        e for e in validate_section(section_type, data)
        if e.endswith(_EMPTY_FIELD_MARKER) or e.endswith(PLACEHOLDER_FIELD_MARKER)
    ]


def _collect_violations(node_name: str, graph, design_brief) -> list:
    """The self-validation checks a family owns/inspects before committing —
    ``repairs.OWNED_BY_FAMILY`` is the table of who owns what. Scoped narrowly
    per family so a repair dispatch does meaningful work rather than every
    agent seeing everything."""
    if node_name == "outcome_designer":
        return checks.bloom_verbs(graph) + checks.measurability(graph)
    if node_name == "assessment_designer":
        coverage = [v for v in checks.relation_coverage(graph) if v.violation_type in ("C2", "P3")]
        bloom = [v for v in checks.bloom_mismatches(graph) if v.violation_type == "bloom_mismatch_assessment"]
        return (coverage + bloom + checks.evaluation_quality(graph) + checks.plan_coverage(graph)
                + checks.item_completeness(graph))
    if node_name == "activity_designer":
        coverage = [v for v in checks.relation_coverage(graph) if v.violation_type in ("C3", "C4", "P4")]
        bloom = [v for v in checks.bloom_mismatches(graph) if v.violation_type == "bloom_mismatch_activity"]
        return coverage + checks.activity_engagement(graph) + bloom
    if node_name == "content_designer":
        coverage = [v for v in checks.relation_coverage(graph) if v.violation_type in ("C5", "P5", "P6")]
        return coverage + checks.orphan_content(graph)
    if node_name == "rubric_designer":
        # No relation coverage left: a criterion is a FIELD of the item it
        # marks (2026-09-02), so C6/C7 and orphan_rubric described conditions
        # that can no longer be false.
        return checks.rubric_consistency(graph) + checks.evidence_alignment(graph)
    if node_name == "implementation_planner":
        return checks.feasibility(graph, design_brief) + checks.actionability(graph)
    return []


def _collect_violations_prose(node_name: str, store) -> list:
    """The prose arm's self-validation scope: the same WITHIN-ARTIFACT check
    cores the graph arm runs (see checks.py), fed from the blackboard. Every
    cross-artifact check — relation coverage, Bloom cross-checks,
    plan_coverage, engagement/orphan/evidence checks, feasibility — is part
    of the alignment machinery this arm ablates and does not run here."""
    if node_name == "outcome_designer":
        objectives = [
            (str(lo.get("id", "")), lo)
            for lo in store.items("objective", "learning_objectives")
            if isinstance(lo, dict)
        ]
        return checks.bloom_verbs_items(objectives) + checks.measurability_items(objectives)
    if node_name == "assessment_designer":
        plan = store.get("assessment_plan")
        quality = checks.evaluation_quality_data("assessment_plan", plan) if plan else []
        tools = [
            (str(t.get("item_id", "")), t)
            for t in store.items("assessment", "assessment_tools")
            if isinstance(t, dict)
        ]
        return quality + checks.item_completeness_items(tools)
    if node_name == "rubric_designer":
        criteria = [
            (f"{t.get('item_id', '?')}/{rc.get('id', '?')}", rc)
            for t in store.items("assessment", "assessment_tools") if isinstance(t, dict)
            for rc in (t.get("rubric") or []) if isinstance(rc, dict)
        ]
        return checks.rubric_consistency_items(criteria)
    if node_name == "implementation_planner":
        data = store.get("implementation_plan")
        return checks.actionability_data("implementation_plan", data) if data else []
    return []


def empty_addie() -> dict:
    return {
        "analysis": {"needs_analysis": {}, "learner_analysis": {}, "context_analysis": {}, "task_analysis": {}},
        "design": {"learning_objectives": [], "instructional_strategies": {}},
        "development": {"learner_materials": [], "assessment_tools": [], "expert_review": {}},
        "implementation": {"instructor_orientation": {}, "system_check": {}, "prototype_execution": {}, "monitoring": {}},
        "evaluation": {"formative": {}, "summative": {}, "improvement_plan": {}},
    }

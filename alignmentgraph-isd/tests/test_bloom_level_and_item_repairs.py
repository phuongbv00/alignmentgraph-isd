"""Two guards on the objective/assessment repair path.

1. ``level`` is validated against Bloom's six. It used to short-circuit the
   verb-vs-level comparison, so an out-of-taxonomy value ("design", "manage")
   passed every round silently — measured on a real run, 4 of 5 arms shipped
   one. The field is also what the evaluator's Bloom sanity check reads, so an
   unvalidated value there is an unvalidated instrument.
2. A coverage repair that must supply a MISSING assessment item asks the model
   to write it. The old template put the objective's own statement into the
   item's ``question``, which reads to any text-similarity measure as
   near-perfect objective-assessment correspondence no design work produced —
   and only the graph arm runs these cross-artifact repairs, so the artefact
   landed on exactly the axis the ablation compares.
"""
from __future__ import annotations

import json

from alignmentgraph_isd.core import checks, repairs
from alignmentgraph_isd.core.alignment_graph import AlignmentGraph, NodeType
from alignmentgraph_isd.core.prose_store import ProseStore
from alignmentgraph_isd.core.trajectory import TrajectoryLogger

_STATEMENT = "Learners will design an interactive web content structure for a maths course."


def _objective(level: str, verb: str = "design") -> dict:
    return {"id": "ILO-01", "level": level, "statement": _STATEMENT, "bloom_verb": verb}


def _ctx(graph, llm_response: str = "") -> repairs.RepairContext:
    return repairs.RepairContext(
        graph=graph, store=None, trajectory=TrajectoryLogger(),
        call_llm=lambda messages, max_retries=0: llm_response, actor="Test")


# ── 1. level enum ───────────────────────────────────────────────────────────

def test_level_inside_the_taxonomy_passes():
    assert checks.bloom_verbs_items([("objective:ILO-01", _objective("create"))]) == []


def test_level_outside_the_taxonomy_is_flagged():
    for bad in ("design", "manage", ""):
        violations = checks.bloom_verbs_items([("objective:ILO-01", _objective(bad))])
        assert len(violations) == 1, bad
        assert violations[0].violation_type == "bloom"
        assert violations[0].metadata["level"] == bad


def test_repair_sets_the_level_from_the_verb_and_leaves_the_statement_alone():
    graph = AlignmentGraph()
    graph.add_element_node(NodeType.OBJECTIVE, "ILO-01", _objective("manage", verb="analyze"))
    violation = checks.bloom_verbs(graph)[0]
    repairs.repair_bloom_verb(_ctx(graph), violation)

    repaired = graph.get_node(f"{NodeType.OBJECTIVE}{graph.ELEMENT_SEP}ILO-01")["data"]
    assert repaired["level"] == "analyze"
    assert repaired["bloom_verb"] == "analyze"      # a valid verb is not rewritten
    assert repaired["statement"] == _STATEMENT      # nor is what the objective asks for
    assert checks.bloom_verbs(graph) == []          # and the check converges


def test_the_prose_arm_repairs_the_level_the_same_way():
    """bloom is a within-artifact check, so it runs in both arms — and both
    have to converge on it."""
    store = ProseStore()
    store.put("objective", {"learning_objectives": [_objective("manage", verb="analyze")]})
    ctx = repairs.RepairContext(graph=None, store=store, trajectory=TrajectoryLogger(),
                                call_llm=lambda messages, max_retries=0: "", actor="Test")
    items = [("objective:ILO-01", store.get("objective")["learning_objectives"][0])]
    repairs.repair_bloom_verb(ctx, checks.bloom_verbs_items(items)[0])

    repaired = store.get("objective")["learning_objectives"][0]
    assert repaired["level"] == "analyze"
    assert repaired["statement"] == _STATEMENT
    assert checks.bloom_verbs_items([("objective:ILO-01", repaired)]) == []


def test_a_verb_spanning_levels_resolves_to_the_lowest():
    # "construct" is both Apply and Create; a repair must not inflate the claim.
    assert repairs._level_from_verb("construct") == "apply"
    assert repairs._level_from_verb("nonsense") == "apply"


# ── 2. coverage repairs regenerate rather than template ─────────────────────

def _graph_needing_an_item() -> AlignmentGraph:
    graph = AlignmentGraph()
    graph.add_element_node(NodeType.OBJECTIVE, "ILO-01", _objective("create", verb="design"))
    graph.add_node(NodeType.ASSESSMENT_PLAN, graph.section_id(NodeType.ASSESSMENT_PLAN),
                   {"summative": ["Capstone"], "lo_coverage_targets": {"ILO-01": ["summative"]}})
    return graph


def _plan_coverage_violation():
    class _V:
        violation_type = "plan_coverage"
        message = "The plan promises a summative item for ILO-01."
        metadata = {"lo_id": "ILO-01", "plan_category": "summative"}
    return _V()


def _written_item(item_id: str, question: str) -> str:
    return json.dumps({"items": [{"item_id": item_id, "question": question,
                                  "scoring_criteria": "Scored 0-3 on working code."}]})


def test_plan_coverage_repair_uses_the_item_the_model_writes():
    graph = _graph_needing_an_item()
    question = "Build a working lesson page and justify each interaction choice."
    ctx = _ctx(graph, _written_item("AT-S-ILO-01", question))
    repairs.repair_plan_coverage(ctx, [_plan_coverage_violation()])

    item = graph.get_node(f"{NodeType.ASSESSMENT}{graph.ELEMENT_SEP}AT-S-ILO-01")["data"]
    assert item["question"] == question
    assert _STATEMENT not in item["question"]
    assert item["scoring_criteria"] == "Scored 0-3 on working code."
    assert item["aligned_objective"] == "ILO-01"
    assert item["type"] == "performance_task"       # Create objective, so not a written answer


def test_plan_coverage_repair_still_converges_when_the_model_returns_nothing():
    graph = _graph_needing_an_item()
    repairs.repair_plan_coverage(_ctx(graph, "not json"), [_plan_coverage_violation()])

    item = graph.get_node(f"{NodeType.ASSESSMENT}{graph.ELEMENT_SEP}AT-S-ILO-01")["data"]
    assert item["question"]                          # the gap is filled either way
    assert item["repaired"] is True


def test_bloom_mismatch_repair_uses_the_item_the_model_writes():
    graph = AlignmentGraph()
    graph.add_element_node(NodeType.OBJECTIVE, "ILO-01", _objective("create", verb="design"))
    graph.add_element_node(NodeType.ASSESSMENT, "AT-01", {
        "item_id": "AT-01", "type": "true_false", "question": "Web pages can be interactive.",
        "aligned_objective": "ILO-01", "plan_category": "diagnostic"})

    class _V:
        violation_type = "bloom_mismatch_assessment"
        message = "No item can elicit ILO-01's Create level."
        metadata = {"lo_id": "ILO-01"}

    question = "Produce a working prototype page and defend its structure in a short memo."
    repairs.repair_assessment_items(_ctx(graph, _written_item("AT-P-ILO-01", question)), [_V()])

    item = graph.get_node(f"{NodeType.ASSESSMENT}{graph.ELEMENT_SEP}AT-P-ILO-01")["data"]
    assert item["question"] == question
    assert _STATEMENT not in item["question"]

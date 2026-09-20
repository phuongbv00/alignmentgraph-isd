"""Two guards on the objective/assessment repair path.

1. ``level`` is validated against Bloom's six. It used to short-circuit the
   verb-vs-level comparison, so an out-of-taxonomy value ("design", "manage")
   passed every round silently — measured on a real run, 4 of 5 arms shipped
   one. The field is also what the evaluator's Bloom sanity check reads, so an
   unvalidated value there is an unvalidated set.
2. A coverage repair never WRITES a missing assessment item: a template that
   put the objective's own statement into the item's ``question`` read to any
   text-similarity measure as near-perfect objective-assessment correspondence
   no design work produced — and only the graph arm runs these cross-artifact
   repairs, so the artefact landed on exactly the axis the ablation compares.
"""
from __future__ import annotations


from alignmentgraph_isd.core import checks, repairs
from alignmentgraph_isd.core.alignment_graph import AlignmentGraph, NodeType
from alignmentgraph_isd.core.prose_store import ProseStore
from alignmentgraph_isd.core.trajectory import TrajectoryLogger

_STATEMENT = "Learners will design an interactive web content structure for a maths course."


def _objective(level: str, verb: str = "design") -> dict:
    return {"id": "ILO-01", "level": level, "statement": _STATEMENT, "bloom_verb": verb}


def _ctx(graph) -> repairs.RepairContext:
    return repairs.RepairContext(
        graph=graph, store=None, trajectory=TrajectoryLogger(), actor="Test")


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
    ctx = repairs.RepairContext(graph=None, store=store, trajectory=TrajectoryLogger(), actor="Test")
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






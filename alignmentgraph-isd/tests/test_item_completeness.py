"""A selectable-response assessment item must ship options + answer key.

Measured 2026-08-28 (Qwen3.5-2B single run): every multiple_choice item in the
main arm's output carried only question + scoring_criteria — no options, no
correct_answer — because the generation schema never asked for them. Such an
item cannot be administered, and the judge scores set completeness
directly (rubric items 22/30). The check flags it and the deterministic
salvage reformats a keyless choice item as short_answer — administrable as
written. No model call is involved: no repair has called the model since
2026-09-03.
"""
from __future__ import annotations


from alignmentgraph_isd.core import repairs
from alignmentgraph_isd.core.alignment_graph import AlignmentGraph, NodeType
from alignmentgraph_isd.core.checks import item_completeness_items
from alignmentgraph_isd.core.trajectory import TrajectoryLogger


def _items(**overrides) -> tuple[str, dict]:
    data = {
        "item_id": "AT-01", "type": "multiple_choice",
        "question": "Which phase of ADDIE produces the design blueprint?",
        "aligned_objective": "ILO-01", "plan_category": "diagnostic",
        "scoring_criteria": "1 point for the correct phase.",
    }
    data.update(overrides)
    return (f"assessment:{data['item_id']}", data)


def test_mcq_without_options_or_answer_is_flagged():
    violations = item_completeness_items([_items()])
    assert len(violations) == 1
    v = violations[0]
    assert v.violation_type == "item_completeness"
    assert set(v.metadata["missing"]) == {"options", "correct_answer"}


def test_complete_mcq_and_open_formats_pass():
    complete = _items(options=["Analysis", "Design", "Development"], correct_answer="Design")
    open_item = _items(item_id="AT-02", type="performance_task")
    short = _items(item_id="AT-03", type="short_answer")
    assert item_completeness_items([complete, open_item, short]) == []


def test_true_false_needs_only_the_answer_key():
    keyless = _items(type="true_false")
    keyed = _items(item_id="AT-02", type="true_false", correct_answer="True")
    violations = item_completeness_items([keyless, keyed])
    assert len(violations) == 1
    assert violations[0].metadata["missing"] == ["correct_answer"]


def _graph_with_mcq() -> AlignmentGraph:
    graph = AlignmentGraph()
    _, data = _items()
    graph.add_element_node(NodeType.ASSESSMENT, "AT-01", data)
    return graph


def _ctx(graph) -> repairs.RepairContext:
    return repairs.RepairContext(
        graph=graph, store=None, trajectory=TrajectoryLogger(),
        actor="AssessmentDesignerAgent",
    )


def test_repair_reformats_a_keyless_item_as_short_answer():
    """The deterministic salvage, and the whole of it: writing the options is
    the agent's job and it has already had its repair turns by the time this
    runs. A keyless choice item administers as nothing, so it is reformatted
    into the one format its question and scoring_criteria already support."""
    graph = _graph_with_mcq()
    violations = item_completeness_items(
        [(n["id"], n["data"]) for n in graph.element_nodes(NodeType.ASSESSMENT)])
    ctx = _ctx(graph)
    repairs.repair_item_completeness(ctx, violations)

    data = graph.get_node(f"{NodeType.ASSESSMENT}{graph.ELEMENT_SEP}AT-01")["data"]
    assert data["type"] == "short_answer"
    assert data.get("repaired") is True
    assert item_completeness_items([("assessment:AT-01", data)]) == []
    # the repair is on the record
    assert ctx.trajectory.repair_events


def test_repair_works_on_the_prose_substrate():
    from alignmentgraph_isd.core.prose_store import ProseStore

    store = ProseStore()
    _, data = _items()
    store.put("assessment", {"assessment_tools": [data]})
    violations = item_completeness_items([("AT-01", data)])
    ctx = repairs.RepairContext(
        graph=None, store=store, trajectory=TrajectoryLogger(),
        actor="SingleDesignerAgent",
    )
    repairs.repair_item_completeness(ctx, violations)

    tools = store.get("assessment")["assessment_tools"]
    assert tools[0]["type"] == "short_answer"

"""Id hygiene between prompts, model output, and the matchers.

Regressions pinned here were measured on a 2B smoke run
(results/single_20260827_022152):

- the model copied namespaced node ids ("objective:ILO-01") from context
  headers into reference fields, and every bare-id matcher then failed —
  plan_coverage reported 14/14 promised pairs as unrealised on a run whose
  items covered them;
- the C4 repair appended whatever node a violation named — including
  ACTIVITY ids — into the first activity's ``prepares_for_assessment``,
  unchecked and without dedup, once per validation round ('TLA-P-ILO-01' x5
  shipped to the judge).
"""
from __future__ import annotations

from alignmentgraph_isd.config import HarnessRunConfig
from alignmentgraph_isd.core import checks, repairs
from alignmentgraph_isd.core.alignment_graph import AlignmentGraph, NodeType, alignment
from alignmentgraph_isd.core.trajectory import TrajectoryLogger


def test_bare_ref_strips_only_known_type_namespaces():
    assert alignment.bare_ref("objective:ILO-01") == "ILO-01"
    assert alignment.bare_ref("assessment:AT-02") == "AT-02"
    assert alignment.bare_ref("ILO-01") == "ILO-01"
    assert alignment.bare_ref(" activity:TLA-01 ") == "TLA-01"
    assert alignment.bare_ref("custom:THING") == "custom:THING"  # not a node type
    assert alignment.bare_ref(None) == ""


def test_matchers_resolve_namespaced_references():
    graph = AlignmentGraph()
    graph.add_element_node(NodeType.OBJECTIVE, "ILO-01", {"id": "ILO-01"})
    graph.add_element_node(NodeType.ASSESSMENT, "AT-01", {
        "item_id": "AT-01", "aligned_objective": "objective:ILO-01",
    })
    violations = alignment.match_id_reverse(graph, "C2", field="aligned_objective")
    assert violations == []
    assert graph.get_edges(relation_id="C2", source="objective:ILO-01")


def test_plan_coverage_accepts_namespaced_target_keys():
    graph = AlignmentGraph()
    graph.add_element_node(NodeType.OBJECTIVE, "ILO-01", {"id": "ILO-01"})
    graph.add_node(NodeType.ASSESSMENT_PLAN, "assessment_plan_0", {
        "lo_coverage_targets": {"objective:ILO-01": ["summative"]},
    })
    graph.add_element_node(NodeType.ASSESSMENT, "AT-01", {
        "item_id": "AT-01", "aligned_objective": "ILO-01", "plan_category": "summative",
    })
    assert checks.plan_coverage(graph) == []


def test_prompt_context_renders_bare_ids_only():
    graph = AlignmentGraph()
    graph.add_element_node(NodeType.OBJECTIVE, "ILO-01", {"id": "ILO-01", "statement": "Apply X."})
    graph.add_node(NodeType.ASSESSMENT_PLAN, "assessment_plan_0", {"formative": ["intent"]})
    # `tools.render_nodes` is where this rendering lives now; it was
    # `BaseISDAgent._element_context` while the scripted specialists existed,
    # and the property is the same one: what the model is shown must use BARE
    # ids, because it echoes back whatever it is shown.
    from alignmentgraph_isd.core.agentic import tools

    ctx = tools.render_nodes(
        graph.element_nodes(NodeType.OBJECTIVE) + graph.section_nodes(NodeType.ASSESSMENT_PLAN)
    )
    assert "[OBJECTIVE:ILO-01]" in ctx
    assert "[ASSESSMENT_PLAN]" in ctx           # section node: plain type header
    assert "objective:ILO-01" not in ctx        # the leak the model was echoing


def _c4_fixture():
    graph = AlignmentGraph()
    graph.add_element_node(NodeType.OBJECTIVE, "ILO-01", {"id": "ILO-01", "level": "apply"})
    graph.add_element_node(NodeType.ASSESSMENT, "AT-01", {
        "item_id": "AT-01", "aligned_objective": "ILO-01", "plan_category": "summative",
    })
    graph.add_node(NodeType.ACTIVITY, "activity_0", {"learning_activities": [
        {"id": "TLA-01", "activity_name": "Practice", "aligned_objectives": ["ILO-01"],
         "prepares_for_assessment": ["TLA-GHOST", "TLA-GHOST"]},
    ]})
    graph.add_element_node(NodeType.ACTIVITY, "TLA-01", {
        "id": "TLA-01", "activity_name": "Practice", "aligned_objectives": ["ILO-01"],
        "prepares_for_assessment": ["TLA-GHOST", "TLA-GHOST"],
    })
    from conftest import RepairActor

    config = HarnessRunConfig(llm_factory=lambda: None)
    return graph, RepairActor("ActivityDesignerAgent", config, graph=graph,
                              trajectory=TrajectoryLogger()).ctx()


class _Violation:
    def __init__(self, vtype, node_id):
        self.violation_type = vtype
        self.node_id = node_id
        self.message = f"{node_id} fails {vtype}"
        self.metadata = {"node_id": node_id}


def test_c4_repair_prunes_dangling_refs_and_links_a_real_item():
    graph, ctx = _c4_fixture()
    violation = _Violation("C4", "activity:TLA-01")
    repairs.repair_activity_coverage(ctx, [violation])
    activity = graph.get_node("activity:TLA-01")["data"]
    prep = activity["prepares_for_assessment"]
    assert prep == ["AT-01"], f"expected pruned+repaired list, got {prep}"


def test_c4_repair_never_appends_activity_ids_and_dedups_across_rounds():
    graph, ctx = _c4_fixture()
    # An uncovered ITEM violation, repeated over two validation rounds, plus a
    # stray activity-id violation of the old broken shape.
    for _ in range(2):
        repairs.repair_activity_coverage(ctx, [
            _Violation("C4", "assessment:AT-01"),
            _Violation("C4", "activity:TLA-01"),
        ])
    for node in graph.element_nodes(NodeType.ACTIVITY):
        prep = node["data"].get("prepares_for_assessment") or []
        assert prep.count("AT-01") <= 1, f"{node['id']}: duplicated item ref: {prep}"
        assert all(not r.startswith("TLA") for r in prep), f"{node['id']}: activity id leaked into item refs: {prep}"


# The joined parent/child rendering this file used to check went with the
# scripted specialists: the agentic arm reads nodes and edges through separate
# tools and asks `coverage_gaps` what is still unlinked, so there is nothing
# left that groups children under a parent in one block. Rebuilding it only to
# test it would be dead code. The property it guarded — an unlinked item is
# SURFACED, not dropped — is now `coverage_gaps`, covered in test_alignment.py
# and exercised end to end in test_agentic_loop.py.
def test_no_full_list_sections_remain_in_a_graph_run(fake_llm_factory):
    """The legacy full-list sections (objective_0/assessment_0/activity_0
    carrying every element twice) are retired: element nodes are the single
    source of truth, sections follow the narrative-only pattern. ~12KB of a
    98KB real dump was byte-identical duplication, and every repair had to
    write both copies or silently diverge."""
    from conftest import run_brief
    from conftest import load_brief

    result = run_brief(load_brief("minimal_brief.json"),
                              HarnessRunConfig(llm_factory=fake_llm_factory))
    nodes = {n["id"]: n for n in result["graph"]["nodes"]}

    assert "objective_0" not in nodes
    assert "activity_0" not in nodes
    if "assessment_0" in nodes:  # narrative-only: expert_review, never the list
        assert "assessment_tools" not in nodes["assessment_0"]["data"]

    # The output contract is untouched: lists come from element nodes.
    addie = result["addie_output"]
    assert addie["design"]["learning_objectives"]
    assert addie["development"]["assessment_tools"]
    assert addie["development"]["expert_review"]
    # audit still validates the (virtual) sections without flagging them missing
    audit = result["metadata"]["audit"]
    assert "objective" not in audit["missing_node_types"]
    assert not audit["missing_section_keys"].get("objective")
    assert not audit["schema_violations"].get("objective")

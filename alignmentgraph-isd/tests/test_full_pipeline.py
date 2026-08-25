"""The default config runs the full pipeline end-to-end: stable result
contract + all 18 alignment relations (7 core + 11 secondary) established
(and repaired to closure)."""
from __future__ import annotations

from alignmentgraph_isd import HarnessRunConfig, run_design_brief
from alignmentgraph_isd.core.alignment_graph import alignment

from conftest import FakeChatModel, load_brief

# Relations establishable via provenance (recorded when generation is
# conditioned on graph nodes the specialist read beforehand) vs. those
# establishable by id/id-list/type-match alone (post-hoc bookkeeping on a
# specialist's own output).
_PROVENANCE_ONLY_RELATIONS = ("C1", "C5", "C6", "P1", "P2", "P4", "P5", "P7", "P8", "P9",
                              "P10", "P11")
_ID_TYPE_MATCH_RELATIONS = ("C2", "C3", "C4", "C7", "P3", "P6")


def _graph_edges(result: dict) -> list[dict]:
    return result["graph"]["edges"]


def _element_nodes(result: dict) -> list[dict]:
    return [n for n in result["graph"]["nodes"] if ":" in n["id"]]


def test_default_config_produces_contract():
    config = HarnessRunConfig()
    config.llm_factory = lambda: FakeChatModel()
    result = run_design_brief(load_brief("minimal_brief.json"), config)

    assert set(result) >= {"addie_output", "trajectory", "metadata", "graph", "graph_dot"}
    addie = result["addie_output"]
    assert set(addie) == {"analysis", "design", "development", "implementation", "evaluation"}
    assert addie["design"]["learning_objectives"]


def test_run_establishes_all_18_relations_and_repairs_gaps():
    config = HarnessRunConfig()
    config.llm_factory = lambda: FakeChatModel()
    result = run_design_brief(load_brief("minimal_brief.json"), config)
    audit = result["metadata"]["audit"]

    # The run builds the graph: element nodes + edges spanning all 18 relations.
    assert _element_nodes(result) and _graph_edges(result)
    established = {e.get("relation_id") for e in _graph_edges(result)}
    assert set(alignment.REGISTRY.keys()) - {"P6"} <= established  # P6 is fuzzy/audit-only

    # P6 (media<->material) is a fuzzy alias type-match, audit-only by design
    # (see audit.py::AUDIT_ONLY_VIOLATION_TYPES); excluded from the coverage check.
    checkable = [r for r in _PROVENANCE_ONLY_RELATIONS + _ID_TYPE_MATCH_RELATIONS if r != "P6"]
    for relation_id in checkable:
        assert audit["relation_coverage"][relation_id]["coverage"] > 0.0, relation_id
    unresolved = {rid for rid in checkable if audit["relation_coverage"][rid]["uncovered"]}
    assert not unresolved, f"relation gaps survived repair: {unresolved}"


# ── the aggregator must not silently drop generated content ─────────────────
# Regression guard for a measured scoring failure: decomposing the analysis
# sections into Gap/Topic/Constraint/Improvement elements originally kept ONLY
# the element list and discarded every sibling narrative field the same LLM
# call produced. The one section stored whole (learner_profile_0) scored 9.6 on
# the benchmark's ADDIE rubric while its stripped siblings scored 1.5-2.5, so
# these fields are load-bearing, not decoration.

_REQUIRED_ANALYSIS_FIELDS = {
    "needs_analysis": ("gaps", "problem_definition", "performance_analysis", "priority_matrix"),
    "learner_analysis": ("target_audience", "characteristics", "prior_knowledge"),
    "context_analysis": ("constraints", "environment", "resources"),
    "task_analysis": ("topics", "prerequisites", "review_summary", "initial_objectives"),
}


def test_analysis_keeps_narrative_fields_alongside_decomposed_elements():
    config = HarnessRunConfig()
    config.llm_factory = lambda: FakeChatModel()
    analysis = run_design_brief(load_brief("minimal_brief.json"), config)["addie_output"]["analysis"]

    for section, fields in _REQUIRED_ANALYSIS_FIELDS.items():
        missing = [f for f in fields if not analysis.get(section, {}).get(f)]
        assert not missing, f"analysis.{section} lost generated field(s): {missing}"


def test_evaluation_carries_formative_findings_and_feedback_summary():
    """E1 of the ADDIE rubric is scored on which areas learners struggle with,
    why, and the first-round revision — not on a list of instruments. Nothing
    generates that narrative since EvaluationRevisionAgent was retired, so the
    assessment plan's pilot_data_plan must reach the output."""
    config = HarnessRunConfig()
    config.llm_factory = lambda: FakeChatModel()
    evaluation = run_design_brief(load_brief("minimal_brief.json"), config)["addie_output"]["evaluation"]

    formative = evaluation["formative"]
    assert formative["data_collection"]["methods"]
    assert formative["anticipated_difficulties"], "no anticipated difficulty analysis (rubric item 28)"
    assert formative["revision_plan"], "no first-round revision actions (rubric item 29)"
    assert all(r["action"] and r["problem_area"] for r in formative["revision_plan"])

    # Sourced from Outcome Designer's improvement plan, NOT the assessment
    # plan — reading it off the latter silently yielded "" on every run.
    assert evaluation["improvement_plan"]["feedback_summary"]


def test_implementation_plan_is_linked_into_the_graph():
    """The implementation plan used to be the one artifact in the graph with no
    edge at all, while its text referenced graph ids in every scenario measured
    (836 activity and 656 material references over 30 runs). The graph could
    therefore not answer "was this activity ever scheduled" or "was this
    material ever handed out" — questions the auditability claim implies it can.

    Only SECTION nodes may sit edgeless: they hold the raw blob while their
    element counterparts carry the relations. implementation_plan_0 has no
    element counterpart, so an edgeless one is an island, not a section."""
    config = HarnessRunConfig()
    config.llm_factory = lambda: FakeChatModel()
    result = run_design_brief(load_brief("minimal_brief.json"), config)
    edges = _graph_edges(result)

    delivered = {e["target"] for e in edges if e.get("relation_id") == "P10"}
    provisioned = {e["target"] for e in edges if e.get("relation_id") == "P11"}
    assert delivered, "no activity is recorded as scheduled by the implementation plan"
    assert provisioned, "no material is recorded as handed out by the implementation plan"
    assert all(e["source"] == "implementation_plan_0" for e in edges
               if e.get("relation_id") in ("P10", "P11"))

    isolated = {
        n["id"] for n in result["graph"]["nodes"]
        if not any(e["source"] == n["id"] or e["target"] == n["id"] for e in edges)
    }
    assert "implementation_plan_0" not in isolated
    assert all(node_id.endswith("_0") for node_id in isolated), (
        f"an ELEMENT node is isolated, which no relation covers: {isolated}")


def test_expert_review_is_always_the_audit_record():
    """Dev2 is a whole judge item with a single sub-item (expert review).
    Since 2026-08-27 the model-authored review is gone from every generation
    schema (a review written by the same model, in the same call, before the
    artifacts it purports to review exist, is fiction) — the aggregator ALWAYS
    reports the verification that actually ran (self-validation rounds,
    repairs, relation coverage) and says so; it never fabricates an SME panel."""
    from alignmentgraph_isd import HarnessRunConfig
    from alignmentgraph_isd.core.agents.addie_aggregator import ADDIEOutputAggregator
    from alignmentgraph_isd.core.alignment_graph import AlignmentGraph, NodeType
    from alignmentgraph_isd.core.trajectory import TrajectoryLogger

    graph = AlignmentGraph()
    trajectory = TrajectoryLogger()
    trajectory.log_violations_result([
        {"node_id": "objective:ILO-01", "type": "C2", "msg": "x", "severity": "error"},
    ])
    trajectory.log_violations_result([])  # clean second round
    trajectory.log_repair_event("AssessmentDesignerAgent", "C2", "assessment_0", ["assessment_tools"])

    development = ADDIEOutputAggregator(
        HarnessRunConfig(), graph, trajectory)._build_development()
    review = development["expert_review"]

    assert review["review_type"] == "internal_automated"
    assert "2 self-validation round(s)" in review["feedback_summary"]
    assert "1 issue(s)" in review["feedback_summary"] and "1 repair(s)" in review["feedback_summary"]
    # honesty clause: the record must SAY no human expert reviewed this
    assert "no external human expert review" in review["feedback_summary"]
    # C2's label appears among the criteria actually checked
    assert any(c.startswith("C2") for c in review["review_criteria"])

    # there is no model-authored channel any more: even if a stray section
    # carried an expert_review, the aggregator does not read it
    graph.add_node(NodeType.ASSESSMENT, "assessment_0", {"expert_review": {"reviewers": ["Dr. X"]}})
    still = ADDIEOutputAggregator(HarnessRunConfig(), graph, trajectory)._build_development()
    assert still["expert_review"]["review_type"] == "internal_automated"


def test_expert_review_itemises_findings_and_relation_coverage():
    """The synthesized review is judged as the expert-review sub-item, so it
    must show its work, not just totals: one finding row per violated
    criterion (issues found, repairs applied) and the per-relation core
    coverage — every row traceable to a recorded trajectory event."""
    from alignmentgraph_isd import HarnessRunConfig
    from alignmentgraph_isd.core.agents.addie_aggregator import ADDIEOutputAggregator
    from alignmentgraph_isd.core.alignment_graph import AlignmentGraph
    from alignmentgraph_isd.core.trajectory import TrajectoryLogger

    graph = AlignmentGraph()
    trajectory = TrajectoryLogger()
    trajectory.log_violations_result([
        {"node_id": "objective:ILO-01", "type": "C2", "msg": "x", "severity": "error"},
        {"node_id": "objective:ILO-02", "type": "C2", "msg": "y", "severity": "error"},
        {"node_id": "activity:TLA-01", "type": "C4", "msg": "z", "severity": "error"},
    ])
    trajectory.log_repair_event("AssessmentDesignerAgent", "C2", "assessment_0", ["assessment_tools"])

    review = ADDIEOutputAggregator(
        HarnessRunConfig(), graph, trajectory)._build_development()["expert_review"]

    by_criterion = {f["criterion"]: f for f in review["findings"]}
    assert by_criterion["C2"]["issues_found"] == 2
    assert by_criterion["C2"]["repairs_applied"] == 1
    assert by_criterion["C4"]["issues_found"] == 1
    assert by_criterion["C4"]["repairs_applied"] == 0
    # per-relation core coverage, keyed by relation id with its label
    assert set(review["alignment_coverage"]) == {f"C{i}" for i in range(1, 8)}
    assert all("label" in row and "coverage" in row for row in review["alignment_coverage"].values())
    assert review["review_process"]


def test_assessment_items_ship_with_their_rubrics():
    """The RubricDesigner's criteria used to live only in the graph dump —
    the deliverable shipped assessments without rubrics, the opposite of
    practice. The aggregator attaches each item's criteria (mapped by the RC
    elements' own aligned_assessment field) as a structured ``rubric`` list
    next to scoring_criteria, in development AND the evaluation slices, on
    both substrates."""
    from alignmentgraph_isd import HarnessRunConfig
    from alignmentgraph_isd.core.agents.addie_aggregator import (
        ADDIEOutputAggregator, aggregate_prose,
    )
    from alignmentgraph_isd.core.alignment_graph import AlignmentGraph, NodeType
    from alignmentgraph_isd.core.prose_store import ProseStore
    from alignmentgraph_isd.core.trajectory import TrajectoryLogger

    item = {"item_id": "AT-01", "type": "short_answer", "question": "Explain X.",
            "aligned_objective": "ILO-01", "plan_category": "summative",
            "scoring_criteria": "Key points named."}
    bare = {"item_id": "AT-02", "type": "short_answer", "question": "Explain Y.",
            "aligned_objective": "ILO-01", "plan_category": "formative",
            "scoring_criteria": "Key points named."}
    rc = {"id": "RC-01", "aligned_assessment": "AT-01", "aligned_objective": "ILO-01",
          "description": "Names all key points with correct reasoning.",
          "evidence_type": "short_answer",
          "levels": {"excellent": "all points", "satisfactory": "most",
                     "needs_improvement": "few"}}

    graph = AlignmentGraph()
    graph.add_element_node(NodeType.ASSESSMENT, "AT-01", item)
    graph.add_element_node(NodeType.ASSESSMENT, "AT-02", bare)
    graph.add_element_node(NodeType.RUBRIC, "RC-01", rc)
    aggregator = ADDIEOutputAggregator(HarnessRunConfig(), graph, TrajectoryLogger())

    development = aggregator._build_development()
    by_id = {t["item_id"]: t for t in development["assessment_tools"]}
    assert by_id["AT-01"]["rubric"][0]["levels"]["excellent"] == "all points"
    assert "rubric" not in by_id["AT-02"]
    # the graph node itself is untouched — the attach never mutates node data
    node = graph.get_node(f"{NodeType.ASSESSMENT}{graph.ELEMENT_SEP}AT-01")
    assert "rubric" not in node["data"]
    # the evaluation slices carry it too (summative slice holds AT-01)
    evaluation = aggregator._build_evaluation()
    summative = {t["item_id"]: t for t in evaluation["summative"]["assessment_tools"]}
    assert summative["AT-01"]["rubric"]

    store = ProseStore()
    store.put("assessment", {"assessment_tools": [dict(item), dict(bare)]})
    store.put("rubric", {"rubric_criteria": [dict(rc)]})
    prose_out = aggregate_prose(store, TrajectoryLogger())
    prose_by_id = {t["item_id"]: t for t in prose_out["development"]["assessment_tools"]}
    assert prose_by_id["AT-01"]["rubric"][0]["id"] == "RC-01"
    assert "rubric" not in prose_by_id["AT-02"]

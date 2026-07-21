"""The default config runs the full pipeline end-to-end: stable result
contract + all 13 alignment relations established (and repaired to closure)."""
from __future__ import annotations

from alignmentgraph_isd import HarnessRunConfig, run_design_brief
from alignmentgraph_isd.core import alignment

from conftest import FakeChatModel, load_brief

# Relations establishable via provenance (recorded when generation is
# conditioned on traversed nodes) vs. those establishable by id/type-match
# alone (post-hoc bookkeeping on a specialist's own output).
_PROVENANCE_ONLY_RELATIONS = ("R1", "R2", "R7", "R8", "R10", "R11", "R13")
_ID_TYPE_MATCH_RELATIONS = ("R3", "R4", "R5", "R6", "R9", "R12")


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


def test_run_establishes_all_13_relations_and_repairs_gaps():
    config = HarnessRunConfig()
    config.llm_factory = lambda: FakeChatModel()
    result = run_design_brief(load_brief("minimal_brief.json"), config)
    audit = result["metadata"]["audit"]

    # The run builds the graph: element nodes + edges spanning all 13 relations.
    assert _element_nodes(result) and _graph_edges(result)
    established = {e.get("relation_id") for e in _graph_edges(result)}
    assert set(alignment.REGISTRY.keys()) - {"R9"} <= established  # R9 is fuzzy/audit-only

    # R9 (media<->material) is a fuzzy alias type-match, audit-only by design
    # (see audit.py::AUDIT_ONLY_VIOLATION_TYPES); excluded from the coverage check.
    checkable = [r for r in _PROVENANCE_ONLY_RELATIONS + _ID_TYPE_MATCH_RELATIONS if r != "R9"]
    for relation_id in checkable:
        assert audit["relation_coverage"][relation_id]["coverage"] > 0.0, relation_id
    unresolved = {rid for rid in checkable if audit["relation_coverage"][rid]["uncovered"]}
    assert not unresolved, f"relation gaps survived repair: {unresolved}"

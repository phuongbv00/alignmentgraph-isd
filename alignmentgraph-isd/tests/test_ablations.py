"""Each ablation preset still produces a stable ADDIE/trajectory/metadata contract."""
from __future__ import annotations

import pytest

from alignmentgraph_isd import HarnessRunConfig, run_design_brief
from alignmentgraph_isd.core import alignment

from conftest import FakeChatModel, load_brief

ABLATIONS = ["full", "wo_graph", "wo_ma"]

# Relations only establishable via provenance (require actual graph-coordinated
# traversal during generation) vs. those establishable by id/type-match alone
# (post-hoc bookkeeping, works regardless of decomposition/coordination).
_PROVENANCE_ONLY_RELATIONS = ("R1", "R2", "R7", "R8", "R10", "R11", "R13")
_ID_TYPE_MATCH_RELATIONS = ("R3", "R4", "R5", "R6", "R9", "R12")


@pytest.mark.parametrize("ablation", ABLATIONS)
def test_ablation_produces_contract(ablation):
    config = HarnessRunConfig.from_ablation(ablation)
    config.llm_factory = lambda: FakeChatModel()
    result = run_design_brief(load_brief("minimal_brief.json"), config)

    assert set(result) >= {"addie_output", "trajectory", "metadata"}
    addie = result["addie_output"]
    assert set(addie) == {"analysis", "design", "development", "implementation", "evaluation"}
    assert addie["design"]["learning_objectives"]
    assert result["metadata"]["ablation"]["enable_alignment_graph"] in (True, False)


# ── The 3-rung RQ2 ladder: wo_ma < wo_graph < full ───────────────────────────
# The alignment graph (element nodes + the 13-relation edges + traversal-
# conditioned generation + the alignment-tier verify/repair) exists ONLY at the
# full rung. wo_ma (single agent, 1 blob call) and wo_graph (N blob calls, one
# per specialist) are graph-FREE: they store plain section blobs and establish no
# edges at all — see AblationConfig.enable_alignment_graph and each specialist's
# `if self._graph_coordination:` guard. That structural gap is the RQ2 contrast.

def _graph_edges(result: dict) -> list[dict]:
    return result["metadata"]["graph"]["edges"]

def _element_nodes(result: dict) -> list[dict]:
    return [n for n in result["metadata"]["graph"]["nodes"] if ":" in n["id"]]


@pytest.mark.parametrize("ablation", ["wo_ma", "wo_graph"])
def test_graph_coordination_off_builds_no_alignment_graph(ablation):
    config = HarnessRunConfig.from_ablation(ablation)
    config.llm_factory = lambda: FakeChatModel()
    result = run_design_brief(load_brief("minimal_brief.json"), config)

    # No alignment graph at all: no element nodes, no relation edges.
    assert _element_nodes(result) == []
    assert _graph_edges(result) == []
    # And the verifier's alignment tier never ran, so no R-typed violation fired.
    verifier_violation_types = {v["type"] for v in result["metadata"]["audit"]["verifier_violations"]}
    assert not (verifier_violation_types & set(alignment.REGISTRY.keys()))
    # The ADDIE output is still complete (section blobs assemble fine).
    addie = result["addie_output"]
    assert addie["design"]["learning_objectives"] and addie["evaluation"]["summative"]


def test_full_establishes_all_13_relations_and_repairs_gaps():
    config = HarnessRunConfig.from_ablation("full")
    config.llm_factory = lambda: FakeChatModel()
    result = run_design_brief(load_brief("minimal_brief.json"), config)
    audit = result["metadata"]["audit"]

    # full DOES build the graph: element nodes + edges spanning all 13 relations.
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

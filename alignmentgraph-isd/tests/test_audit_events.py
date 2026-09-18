"""2026-08-27: the residual whole-graph audit used to have zero trajectory
footprint — only its INPUTS (the ~300 graph reads that compute it) were
recorded, never the finding itself. ``log_audit_result`` closes that gap;
these tests pin the shape and the ORCHESTRATOR attribution.

The cross-agent routing mechanism this file also used to cover (a router
that could send a Designer back for a narrow revision) was removed
2026-08-28 — see ``core/runner.py``'s module docstring — so there is no
``"route"`` trajectory action left to test.
"""
from __future__ import annotations

from alignmentgraph_isd.config import HarnessRunConfig
from alignmentgraph_isd.core.trajectory import ORCHESTRATOR

from conftest import FakeChatModel, load_brief


def test_the_residual_audit_is_logged_and_agrees_with_the_graph():
    config = HarnessRunConfig(llm_factory=lambda: FakeChatModel())
    from conftest import run_brief

    result = run_brief(load_brief("java_oop_brief.json"), config)

    audit_events = [e for e in result["trajectory"]["events"] if e["action"] == "audit"]
    assert len(audit_events) == 1
    event = audit_events[0]
    assert event["agent"] == ORCHESTRATOR

    metadata_audit = result["metadata"]["audit"]
    context = event["context"]
    assert context["objective_count"] == metadata_audit["objective_count"]
    assert context["ready_to_aggregate"] == metadata_audit["ready_to_aggregate"]
    assert context["missing_node_type_count"] == len(metadata_audit["missing_node_types"])

    # The coverage and the per-objective legs are the GRAPH's — `metadata.audit`
    # stopped carrying a second copy of them 2026-09-16. The event summarises
    # what the auditor saw, so it has to agree with the artifact that owns it.
    coverage = result["graph"]["relation_coverage"]
    assert context["unmeasured_count"] == sum(
        1 for flags in result["graph"]["objective_alignment"].values()
        if not flags["assessed_by"]
    )
    assert context["gapped_relations"] == sorted(
        rid for rid, info in coverage.items() if info["uncovered"]
    )
    assert context["residual_gap_count"] == sum(
        len(info["uncovered"]) for info in coverage.values()
    )
    # A summary pointer, not a second copy: the full per-relation detail
    # (labels, mechanism, uncovered node ids) is NOT duplicated into the event.
    assert "relation_coverage" not in context
    assert "node_counts" not in context


# `test_the_agentic_arm_also_logs_the_residual_audit` was removed 2026-09-04.
# It called the run directly with the same config and brief as the
# test above, which reaches the same function through `run_brief` — one
# executor, so "also" named a second one that does not exist — and then made a
# strict subset of that test's assertions. What is worth distinguishing is the
# PROSE arm, which is the test below.


def test_the_prose_arm_has_no_graph_and_therefore_no_audit_event():
    config = HarnessRunConfig(llm_factory=lambda: FakeChatModel(), context_mode="prose")
    from conftest import run_brief

    result = run_brief(load_brief("java_oop_brief.json"), config)
    assert not [e for e in result["trajectory"]["events"] if e["action"] == "audit"]

"""Refinement-session flow: init commits v1, a refinement request repairs only its impact set.

This is the mechanism RQ2's process metrics are computed from, so the test pins
the exact artifacts the metrics scripts read: graph version files, the
``refinement_request:``-prefixed cascade event, ``node_edits``, and the final audit.
"""
from __future__ import annotations

import json
from pathlib import Path

from alignmentgraph_isd import HarnessRunConfig, run_design_brief

from conftest import load_brief

PROGRAM_ID = "refinement-test"


def _config(tmp_path: Path, fake_llm_factory) -> HarnessRunConfig:
    config = HarnessRunConfig.from_ablation("full", memory={
        "enabled": True,
        "persist": True,
        "root_dir": str(tmp_path),
        "training_program_id": PROGRAM_ID,
    })
    config.llm_factory = fake_llm_factory
    return config


def _graph_version(tmp_path: Path, version: int) -> dict:
    path = tmp_path / "programs" / PROGRAM_ID / "graph_versions" / f"alignment_graph_v{version:04d}.json"
    assert path.exists(), f"expected committed graph version file: {path}"
    return json.loads(path.read_text(encoding="utf-8"))


def _node(graph_payload: dict, node_id: str) -> dict:
    nodes = {n["id"]: n for n in graph_payload["graph"]["nodes"]}
    assert node_id in nodes, f"missing node {node_id}"
    return nodes[node_id]


def test_refinement_session_targets_impact_set_only(tmp_path, fake_llm_factory):
    brief = load_brief("java_oop_brief.json")

    # Session 1: init on a fresh program.
    result1 = run_design_brief(brief, _config(tmp_path, fake_llm_factory))
    memory1 = result1["metadata"]["memory"]
    assert memory1["session_type"] == "init"
    assert memory1["committed_graph_version"] == 1
    v1 = _graph_version(tmp_path, 1)

    # Session 2: refinement request against objective_0 on the same program.
    brief2 = brief.model_copy(deep=True)
    brief2.refinement_request = {
        "id": "TR-1",
        "target_node_id": "objective_0",
        "summary": "Add a unit-testing learning objective",
        "instruction": "Add a learning objective about unit testing class designs.",
        "changed_fields": ["learning_objectives"],
    }
    brief2.user_message = brief2.refinement_request["instruction"]
    result2 = run_design_brief(brief2, _config(tmp_path, fake_llm_factory))
    memory2 = result2["metadata"]["memory"]
    assert memory2["session_type"] == "refinement"
    assert memory2["committed_graph_version"] == 2

    # Exactly one refinement cascade event, scoped by IMPACT_POLICY[objective].
    refinement_events = [
        e for e in result2["trajectory"]["cascade_events"]
        if e["reason"].startswith("refinement_request:")
    ]
    assert len(refinement_events) == 1
    impacted = set(refinement_events[0]["nodes"])
    assert "objective_0" in impacted
    assert {"assessment_0", "activity_0", "material_0", "evaluation_0"} <= impacted
    assert "needs_context_0" not in impacted
    assert "implementation_plan_0" not in impacted

    # The impacted sections were regenerated; untouched sections were not edited.
    edited = {e["node_id"] for e in result2["trajectory"]["node_edits"]}
    assert "objective_0" in edited
    assert "needs_context_0" not in edited
    assert "implementation_plan_0" not in edited

    # Untouched sections carry identical content across versions.
    v2 = _graph_version(tmp_path, 2)
    for untouched in ("needs_context_0", "implementation_plan_0"):
        assert _node(v1, untouched)["data"] == _node(v2, untouched)["data"]

    # The refinement run converged: repairs cleared staleness and coverage holds.
    assert all(not n.get("stale") for n in v2["graph"]["nodes"]), "stale nodes leaked into the committed graph"
    audit = result2["metadata"]["audit"]
    assert audit.get("ready_to_aggregate") is True


def test_regenerate_all_scope_invalidates_every_node(tmp_path, fake_llm_factory):
    brief = load_brief("java_oop_brief.json")
    run_design_brief(brief, _config(tmp_path, fake_llm_factory))
    v1 = _graph_version(tmp_path, 1)

    brief2 = brief.model_copy(deep=True)
    brief2.refinement_request = {
        "id": "TR-full",
        "target_node_id": "objective_0",
        "summary": "Full regeneration baseline",
        "scope": "regenerate_all",
    }
    result2 = run_design_brief(brief2, _config(tmp_path, fake_llm_factory))

    events = [
        e for e in result2["trajectory"]["cascade_events"]
        if e["reason"].startswith("refinement_request:")
    ]
    assert len(events) == 1
    assert set(events[0]["nodes"]) == {n["id"] for n in v1["graph"]["nodes"]}

    # Every section was regenerated and the run still converges cleanly.
    edited = {e["node_id"] for e in result2["trajectory"]["node_edits"]}
    for section in ("needs_context_0", "objective_0", "assessment_0", "activity_0",
                    "material_0", "implementation_plan_0", "evaluation_0"):
        assert section in edited
    v2 = _graph_version(tmp_path, 2)
    assert all(not n.get("stale") for n in v2["graph"]["nodes"])
    assert result2["metadata"]["audit"].get("ready_to_aggregate") is True


def test_refinement_request_with_unknown_target_degrades_to_reverify(tmp_path, fake_llm_factory):
    brief = load_brief("java_oop_brief.json")
    run_design_brief(brief, _config(tmp_path, fake_llm_factory))

    brief2 = brief.model_copy(deep=True)
    brief2.refinement_request = {"id": "TR-bad", "target_node_id": "no_such_node"}
    result2 = run_design_brief(brief2, _config(tmp_path, fake_llm_factory))

    assert not [
        e for e in result2["trajectory"]["cascade_events"]
        if e["reason"].startswith("refinement_request:")
    ]
    errors = [
        s for s in result2["trajectory"]["agent_steps"]
        if s["agent_name"] == "RefinementEntrypoint" and s["action"] == "refinement_error"
    ]
    assert len(errors) == 1
    assert result2["metadata"]["memory"]["committed_graph_version"] == 2


def test_refinement_request_ignored_on_init_session(tmp_path, fake_llm_factory):
    brief = load_brief("java_oop_brief.json")
    brief.refinement_request = {"id": "TR-x", "target_node_id": "objective_0"}
    result = run_design_brief(brief, _config(tmp_path, fake_llm_factory))
    assert result["metadata"]["memory"]["session_type"] == "init"
    assert not [
        e for e in result["trajectory"]["cascade_events"]
        if e["reason"].startswith("refinement_request:")
    ]

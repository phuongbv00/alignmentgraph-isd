"""P1.3: the dynamic ISD task graph is a real artifact, snapshotted per round."""
from __future__ import annotations

from alignmentgraph_isd import run_design_brief
from alignmentgraph_isd.audit import GraphAuditor
from alignmentgraph_isd.graph import AlignmentGraph
from alignmentgraph_isd.planner import ISDTaskPlanner
from alignmentgraph_isd.config import HarnessRunConfig
from alignmentgraph_isd.task_graph import TaskGraphBuilder

from conftest import load_brief


def test_builder_emits_tasks_with_owner_and_dependencies():
    config = HarnessRunConfig.from_ablation("full")
    graph = AlignmentGraph()  # empty graph -> first task is needs_context
    audit = GraphAuditor(graph).audit()
    decision = ISDTaskPlanner.from_config(config).decide(audit, {}, config)
    task_graph = TaskGraphBuilder.build(audit, decision, {})

    assert task_graph["tasks"], "expected candidate tasks"
    assert any(t["type"] == "aggregate" for t in task_graph["tasks"])
    for task in task_graph["tasks"]:
        assert "owner" in task and "status" in task and "depends_on" in task
    # dependency edges reference tasks present in the graph
    types = {t["type"] for t in task_graph["tasks"]}
    for edge in task_graph["edges"]:
        assert edge["from"] in types and edge["to"] in types


def test_trajectory_records_task_graph_snapshots(fake_config):
    result = run_design_brief(load_brief("minimal_brief.json"), fake_config)
    snapshots = result["trajectory"]["task_graph_snapshots"]
    assert snapshots, "expected at least one task-graph snapshot"
    first = snapshots[0]["task_graph"]
    assert "tasks" in first and "edges" in first

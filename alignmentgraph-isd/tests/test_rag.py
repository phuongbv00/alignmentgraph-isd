"""RAG = external corpus retrieval only.

`RetrievalPlanner` does RAG only and returns the rag result dict. Brief-derived
context preparation lives in `ContextPlanner` (not retrieval); graph-context and
memory retrieval are core. The benchmark defaults to no_rag; RAG is a
case-study/app add-on.
"""
from __future__ import annotations

from alignmentgraph_isd import (
    DesignBrief,
    HarnessRunConfig,
    LocalCorpusSubagent,
    RetrievalSubagent,
)
from alignmentgraph_isd.context import ContextPlanner
from alignmentgraph_isd.rag.planner import RetrievalPlanner

from conftest import load_brief


def _java_corpus() -> LocalCorpusSubagent:
    return LocalCorpusSubagent(
        name="java-oop-corpus",
        source_type="java_oop",
        corpus={"oop": ["Prefer composition over inheritance.", "Encapsulate invariants."]},
        domains=["software engineering"],
        keywords=["oop", "java"],
    )


def test_context_planner_is_not_retrieval():
    """Brief-derived context is prepared by ContextPlanner, not RetrievalPlanner."""
    pack = ContextPlanner().build(load_brief("java_oop_brief.json"))
    assert pack["design_brief_focus"]["title"]
    assert pack["rubric_focus"]
    assert "rag" not in pack  # RAG is added separately, only by the harness


def test_retrieval_planner_returns_only_rag_and_off_on_benchmark_default():
    config = HarnessRunConfig.from_ablation("full")  # benchmark default -> no_rag
    assert config.ablation.use_rag is False
    config.retrieval_subagents = [_java_corpus()]  # registered but RAG is off
    rag = RetrievalPlanner(config).retrieve(load_brief("java_oop_brief.json"))

    # RetrievalPlanner now returns ONLY the rag result, nothing else.
    assert set(rag) == {"enabled", "task_name", "results", "sources"}
    assert rag["enabled"] is False
    assert rag["results"] == []


def test_rag_runs_for_case_study_when_enabled():
    config = HarnessRunConfig.from_ablation("case_study")  # use_rag=True
    assert config.ablation.use_rag is True
    config.retrieval_subagents = [_java_corpus()]
    rag = RetrievalPlanner(config).retrieve(load_brief("java_oop_brief.json"))

    assert rag["enabled"] is True
    assert rag["results"], "expected the java corpus subagent to fire"
    assert rag["results"][0]["subagent"] == "java-oop-corpus"
    assert rag["results"][0]["content"]
    assert "java_oop" in rag["sources"]


def test_benchmark_default_registers_no_subagents():
    config = HarnessRunConfig.from_ablation("full")  # no subagents configured
    rag = RetrievalPlanner(config).retrieve(load_brief("minimal_brief.json"))
    assert rag["enabled"] is False


def test_registry_routes_by_can_handle():
    class OnlyTesting(RetrievalSubagent):
        name = "testing-corpus"
        source_type = "testing"

        def can_handle(self, design_brief, task_name):
            return "test" in (design_brief.title or "").lower()

        def retrieve(self, design_brief, task_name, graph_context):
            return {"source": self.source_type, "subagent": self.name,
                    "task_name": task_name, "content": ["Use the testing pyramid."], "citations": []}

    config = HarnessRunConfig.from_ablation("case_study")  # use_rag=True
    config.retrieval_subagents = [OnlyTesting()]

    java_rag = RetrievalPlanner(config).retrieve(load_brief("java_oop_brief.json"))
    testing_rag = RetrievalPlanner(config).retrieve(load_brief("software_testing_brief.json"))

    assert java_rag["results"] == []
    assert testing_rag["results"], "testing corpus should match the testing brief"

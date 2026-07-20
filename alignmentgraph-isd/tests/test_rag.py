"""RAG = external corpus retrieval only.

Tests are scoped to the right layer:
- Gate: ``RetrievalPlanner.enabled()``
- Routing: ``RetrievalAgentRegistry.retrieve()`` / ``select()``
- Context separation: brief-derived context is NOT retrieval
"""
from __future__ import annotations

from alignmentgraph_isd import (
    DesignBrief,
    HarnessRunConfig,
    RetrievalAgent,
    RetrievalAgentRegistry,
    RetrievalTool,
)
from alignmentgraph_isd.core.agents.base import _format_design_brief
from alignmentgraph_isd.core.rag.planner import RetrievalPlanner

from conftest import load_brief


def _java_corpus() -> RetrievalAgent:
    corpus = {"oop": ["Prefer composition over inheritance.", "Encapsulate invariants."]}

    def search(query: str = "") -> list[str]:
        return [s for snippets in corpus.values() for s in snippets]

    return RetrievalAgent(
        name="java-oop-corpus",
        source_type="java_oop",
        tools=[RetrievalTool("search_corpus", "Search OOP corpus", search)],
        domains=["software engineering"],
        keywords=["oop", "java"],
    )


def test_brief_carries_standing_guidance_not_retrieval():
    """The specialist prompt is the brief + static design guidance (no external
    corpus). RAG material is prepended separately, only when the harness enables it."""
    text = _format_design_brief(load_brief("java_oop_brief.json"))
    assert "Standing design guidance" in text  # static guidance, appended once
    assert "measurable Bloom verbs" in text
    assert "RETRIEVED" not in text  # no retrieval happened here


def test_retrieval_gate_off_on_benchmark_default():
    """use_rag=False → enabled() is False even with agents registered."""
    config = HarnessRunConfig.from_ablation("full")  # benchmark default → no_rag
    assert config.ablation.use_rag is False
    config.retrieval_subagents = [_java_corpus()]
    assert RetrievalPlanner(config).enabled() is False


def test_retrieval_gate_off_with_empty_registry():
    """use_rag=True but no agents → enabled() is False."""
    config = HarnessRunConfig.from_ablation("full")
    config.ablation.use_rag = True  # RAG on (case-study-style), preset-free
    assert RetrievalPlanner(config).enabled() is False


def test_retrieval_gate_on_when_enabled_and_registered():
    """use_rag=True + agent registered → enabled() is True."""
    config = HarnessRunConfig.from_ablation("full")
    config.ablation.use_rag = True  # RAG on (case-study-style), preset-free
    config.retrieval_subagents = [_java_corpus()]
    assert RetrievalPlanner(config).enabled() is True


def test_registry_retrieves_matching_corpus():
    """Registry returns content when an agent's can_handle matches the brief."""
    registry = RetrievalAgentRegistry([_java_corpus()])
    results = registry.retrieve(load_brief("java_oop_brief.json"), "objective_design")
    assert results, "java corpus should match the java brief"
    assert results[0]["subagent"] == "java-oop-corpus"
    assert results[0]["content"]


def test_registry_routes_by_can_handle():
    """Only the matching agent fires; non-matching brief yields empty results."""
    testing_agent = RetrievalAgent(
        name="testing-corpus",
        source_type="testing",
        domains=["software testing"],
        keywords=["test", "testing"],
        tools=[RetrievalTool("search", "Search", lambda query="": ["Use the testing pyramid."])],
    )

    registry = RetrievalAgentRegistry([testing_agent])
    assert registry.retrieve(load_brief("java_oop_brief.json"), "objective_design") == []
    testing_results = registry.retrieve(load_brief("software_testing_brief.json"), "objective_design")
    assert testing_results
    assert testing_results[0]["subagent"] == "testing-corpus"

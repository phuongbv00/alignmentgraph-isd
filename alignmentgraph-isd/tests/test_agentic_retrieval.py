"""Retrieval inside the tool loop.

The pre-2026-09-01 path — ``BaseISDAgent._maybe_retrieve``, a decision call
made before generation — went with the scripted specialists that ran it. The
agentic arm retrieves by CALLING the ``retrieve`` tool, which is what the
remaining tests here cover.
On-demand agentic retrieval: RQ1 zero-cost gate, decision flow, sandbox behavior."""
from __future__ import annotations

import json

from alignmentgraph_isd import DesignBrief, HarnessRunConfig
from alignmentgraph_isd.core.rag.agent import RetrievalAgent, RetrievalTool
from alignmentgraph_isd.core.rag.sandbox import RetrievalSandbox

from conftest import FakeChatModel, events_of, load_brief, run_brief

BRIEF = DesignBrief(
    id="b1", title="Software Testing Fundamentals", domain="Software Engineering",
    learning_goals=["Apply unit testing"],
)


def _corpus_agent(name="testing_corpus", fail=False, max_tool_calls=3) -> RetrievalAgent:
    def search(query: str = "") -> list[str]:
        if fail:
            raise RuntimeError("corpus exploded")
        return [f"snippet for {query or 'testing'}"]

    return RetrievalAgent(
        name, "corpus",
        description="Internal testing conventions",
        domains=["software engineering"],
        system_prompt="You retrieve internal software-testing conventions.",
        tools=[RetrievalTool("search_corpus", "Search the corpus", search)],
        max_tool_calls=max_tool_calls,
    )


# ── Safety: use_rag off ⇒ identical behavior, zero extra LLM calls ────────────

def test_use_rag_off_is_zero_cost_and_prompt_stable(fake_llm_factory):
    brief = load_brief("java_oop_brief.json")

    config_plain = HarnessRunConfig()
    config_plain.llm_factory = fake_llm_factory
    result_plain = run_brief(brief, config_plain)

    # Even with subagents registered, use_rag=False must gate everything out.
    config_gated = HarnessRunConfig()
    config_gated.llm_factory = fake_llm_factory
    config_gated.retrieval_subagents = [_corpus_agent()]
    result_gated = run_brief(brief, config_gated)

    for result in (result_plain, result_gated):
        assert events_of(result["trajectory"], "retrieval") == []
    assert result_plain["metadata"]["token_usage"]["llm_calls"] == result_gated["metadata"]["token_usage"]["llm_calls"]


def test_use_rag_on_with_empty_registry_is_zero_cost(fake_llm_factory):
    brief = load_brief("java_oop_brief.json")
    config = HarnessRunConfig(use_rag=True)
    config.llm_factory = fake_llm_factory
    result = run_brief(brief, config)
    assert events_of(result["trajectory"], "retrieval") == []


# ── On-demand flow: specialist decides, sandbox executes, prompt gets material ─



def test_sandbox_isolates_failures_and_runs_parallel():
    ok, bad = _corpus_agent("ok_agent"), _corpus_agent("bad_agent", fail=True)
    sandbox = RetrievalSandbox(llm_factory=None)  # no model → deterministic fallback path
    plan = {"agents": ["ok_agent", "bad_agent"], "strategy": "parallel",
            "queries": {"ok_agent": "rubric", "bad_agent": "rubric"}}
    results, events = sandbox.execute(BRIEF, "assessment_design", plan, [ok, bad])

    assert len(results) == 1 and results[0]["subagent"] == "ok_agent"
    statuses = {e["agent"]: e["status"] for e in events}
    assert statuses["ok_agent"] == "ok"
    assert statuses["bad_agent"] in ("error", "empty")


def test_retrieval_agent_loop_respects_tool_budget():
    calls = {"n": 0}

    class GreedyModel:
        def invoke(self, messages):
            calls["n"] += 1

            class R:
                usage_metadata = None
                content = json.dumps({"tool": "search_corpus", "args": {"query": "more"}})
            return R()

    agent = _corpus_agent(max_tool_calls=2)
    result = agent.run_agentic(GreedyModel(), "rubric", "assessment_design")
    # budget: at most max_tool_calls tool rounds + 1 final round
    assert calls["n"] <= 3
    assert result["tool_calls"] == 2
    assert result["content"] == []  # never produced a final answer → empty fallback


def test_corpus_agent_deterministic_path():
    corpus = {"unit test": ["AAA convention"]}
    agent = RetrievalAgent(
        "kw", "corpus",
        tools=[RetrievalTool("search", "Search", lambda query="": [s for v in corpus.values() for s in v])],
        domains=["software engineering"],
    )
    sandbox = RetrievalSandbox(llm_factory=None)
    results, events = sandbox.execute(
        BRIEF, "assessment_design",
        {"agents": ["kw"], "strategy": "single", "queries": {}}, [agent],
    )
    assert results and results[0]["content"] == ["AAA convention"]
    assert events[0]["status"] == "ok"


class _RetrieveThenSubmitModel(FakeChatModel):
    """Agentic arm: call ``retrieve`` once on the first stage, then submit
    everything normally. Retrieval here is not a separate
    coordinator decision — it is a tool the model may choose to call, so what
    has to be proven is that the tool is BOUND when RAG is on and that calling
    it reaches ``core/rag``'s own planner/sandbox rather than a second path."""

    def __init__(self) -> None:
        super().__init__()
        self.retrieved = False
        self.retrieve_offered = False

    def bind_tools(self, specs):
        bound = super().bind_tools(specs)
        bound.retrieve_offered = any(
            spec["function"]["name"] == "retrieve" for spec in specs)
        return bound

    def invoke(self, messages):
        if self.retrieve_offered and not _RetrieveThenSubmitModel._done:
            _RetrieveThenSubmitModel._done = True
            self.retrieved = True

            class R:
                usage_metadata = None
                content = ""
                tool_calls = [{"name": "retrieve", "args": {"query": "unit test rubric"},
                               "id": "r1"}]

            return R()
        return super().invoke(messages)


_RetrieveThenSubmitModel._done = False


def test_agentic_arm_retrieves_by_calling_the_tool():
    _RetrieveThenSubmitModel._done = False
    config = HarnessRunConfig(use_rag=True, llm_factory=_RetrieveThenSubmitModel)
    config.retrieval_subagents = [_corpus_agent()]

    result = run_brief(load_brief("software_testing_brief.json"), config)

    events = events_of(result["trajectory"], "retrieval")
    assert events, "the retrieve tool call must reach the planner and be recorded"
    assert any(e["context"].get("decision") == "retrieve" for e in events)
    # And the run still completes every stage — retrieval costs a turn, not a step.
    assert result["addie_output"]["analysis"]


def test_retrieve_tool_is_not_bound_when_rag_is_off():
    """The gate has to close at the BINDING, not inside the executor: a tool
    the model can see costs it a turn to discover it cannot use."""
    from alignmentgraph_isd.core.agentic import tools as agentic_tools
    from alignmentgraph_isd.core.agentic.specialists import STEPS

    names = agentic_tools.tool_names(
        agentic_tools.tool_specs(STEPS[0], retrieval_available=False))
    assert "retrieve" not in names
    names_on = agentic_tools.tool_names(
        agentic_tools.tool_specs(STEPS[0], retrieval_available=True))
    assert "retrieve" in names_on

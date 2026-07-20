"""On-demand agentic retrieval: RQ1 zero-cost gate, decision flow, sandbox behavior."""
from __future__ import annotations

import json

from alignmentgraph_isd import DesignBrief, HarnessRunConfig, run_design_brief
from alignmentgraph_isd.core.rag.agent import RetrievalAgent, RetrievalTool
from alignmentgraph_isd.core.rag.sandbox import RetrievalSandbox

from conftest import FakeChatModel, _payload_for_system, load_brief

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


# ── RQ1 safety: enable_rag off ⇒ identical behavior, zero extra LLM calls ─────────

def test_enable_rag_off_is_zero_cost_and_prompt_stable(fake_llm_factory):
    brief = load_brief("java_oop_brief.json")

    config_plain = HarnessRunConfig.from_ablation("full")
    config_plain.llm_factory = fake_llm_factory
    result_plain = run_design_brief(brief, config_plain)

    # Even with subagents registered, enable_rag=False must gate everything out.
    config_gated = HarnessRunConfig.from_ablation("full")
    config_gated.llm_factory = fake_llm_factory
    config_gated.retrieval_subagents = [_corpus_agent()]
    result_gated = run_design_brief(brief, config_gated)

    for result in (result_plain, result_gated):
        assert result["trajectory"]["retrieval_events"] == []
    assert result_plain["trajectory"]["llm_calls"] == result_gated["trajectory"]["llm_calls"]


def test_enable_rag_on_with_empty_registry_is_zero_cost(fake_llm_factory):
    brief = load_brief("java_oop_brief.json")
    config = HarnessRunConfig.from_ablation("full")
    config.ablation.enable_rag = True  # RAG on (case-study-style), preset-free
    config.llm_factory = fake_llm_factory
    result = run_design_brief(brief, config)
    assert result["trajectory"]["retrieval_events"] == []


# ── On-demand flow: specialist decides, sandbox executes, prompt gets material ─

class _RagFakeModel(FakeChatModel):
    """Fake model that opts in to retrieval and answers the retrieval-agent loop."""

    def __init__(self) -> None:
        self.seen_domain_material = 0

    def invoke(self, messages):
        system = ""
        user = ""
        for message in messages:
            role = message.get("role") if isinstance(message, dict) else ""
            if role == "system":
                system = message.get("content", "")
            if role == "user":
                user = message.get("content", "")

        class R:
            usage_metadata = None

        r = R()
        if "retrieval coordinator" in system:
            r.content = json.dumps({
                "retrieve": True,
                "agents": ["testing_corpus"],
                "strategy": "single",
                "queries": {"testing_corpus": "unit test rubric"},
            })
            return r
        if "You retrieve internal software-testing conventions." in system:
            r.content = json.dumps({"tool": "search_corpus", "args": {"query": "rubric"}}) \
                if "TOOL RESULT" not in user else json.dumps({
                    "content": ["Use AAA structure", "Rubric 0-4 anchors"],
                    "citations": ["corpus:search_corpus"],
                })
            return r
        if "DOMAIN MATERIAL" in user:
            self.seen_domain_material += 1
        payload = _payload_for_system(system)
        r.content = json.dumps(payload, ensure_ascii=False)
        return r


def test_on_demand_retrieval_flow_end_to_end():
    brief = load_brief("software_testing_brief.json")
    model = _RagFakeModel()
    config = HarnessRunConfig.from_ablation("full")
    config.ablation.enable_rag = True  # RAG on (case-study-style), preset-free
    config.llm_factory = lambda: model
    config.retrieval_subagents = [_corpus_agent()]

    result = run_design_brief(brief, config)

    events = result["trajectory"]["retrieval_events"]
    retrieved = [e for e in events if e["decision"] == "retrieve"]
    assert retrieved, "expected at least one specialist to retrieve"
    assert retrieved[0]["strategy"] == "single"
    assert retrieved[0]["retrieval_agents"] == ["testing_corpus"]
    assert retrieved[0]["snippets"] >= 1
    assert all(e["executions"][0]["status"] == "ok" for e in retrieved)
    assert model.seen_domain_material >= 1, "retrieved material should reach specialist prompts"


# ── Sandbox behavior ───────────────────────────────────────────────────────────

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

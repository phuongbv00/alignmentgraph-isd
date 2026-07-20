"""Token-usage capture + graph-dump snapshot — both are reported artifacts the
RQ2 analysis reads, so pin their shape."""
from __future__ import annotations

import json

from alignmentgraph_isd import HarnessRunConfig, run_design_brief
from alignmentgraph_isd.core import viz
from alignmentgraph_isd.core.agents.base import _extract_token_usage
from alignmentgraph_isd.core.graph import AlignmentGraph, NodeType

from conftest import FakeChatModel, load_brief


# ── token usage extraction across provider shapes ────────────────────────────

def test_extract_token_usage_from_langchain_dict():
    class R:
        usage_metadata = {"input_tokens": 1500, "output_tokens": 800, "total_tokens": 2300}
    assert _extract_token_usage(R()) == (1500, 800)


def test_extract_token_usage_from_openai_response_metadata():
    class R:
        usage_metadata = None
        response_metadata = {"token_usage": {"prompt_tokens": 1200, "completion_tokens": 600}}
    assert _extract_token_usage(R()) == (1200, 600)


def test_extract_token_usage_none_when_absent():
    class R:
        pass
    assert _extract_token_usage(R()) == (0, 0)


def test_run_records_nonzero_token_usage():
    class TokenModel(FakeChatModel):
        def invoke(self, messages):
            r = super().invoke(messages)
            r.usage_metadata = {"input_tokens": 1000, "output_tokens": 500}
            return r

    config = HarnessRunConfig.from_ablation("full")
    config.llm_factory = lambda: TokenModel()
    result = run_design_brief(load_brief("minimal_brief.json"), config)
    usage = result["trajectory"]["token_usage"]
    calls = result["trajectory"]["llm_calls"]
    assert calls > 0
    assert usage["prompt_tokens"] == 1000 * calls
    assert usage["completion_tokens"] == 500 * calls


# ── graph snapshot in metadata + node-link / dot artifacts ───────────────────

def test_metadata_carries_lightweight_graph_snapshot():
    config = HarnessRunConfig.from_ablation("full")
    config.llm_factory = lambda: FakeChatModel()
    result = run_design_brief(load_brief("minimal_brief.json"), config)
    graph = result["metadata"]["graph"]

    assert {"nodes", "edges", "objective_alignment", "relation_coverage"} <= set(graph)
    # lightweight: node data payload is stripped (it duplicates addie_output)
    assert all("data" not in node for node in graph["nodes"])
    # edges keep the structural fields the alignment analysis needs
    typed_edges = [e for e in graph["edges"] if e.get("relation_id")]
    assert typed_edges and all("established_by" in e for e in typed_edges)
    assert set(graph["relation_coverage"]) == {f"R{i}" for i in range(1, 14)}


def test_graph_dump_written_when_env_opts_in(tmp_path, monkeypatch):
    monkeypatch.setenv("ALIGNMENTGRAPH_DUMP_DIR", str(tmp_path))
    config = HarnessRunConfig.from_ablation("full")
    config.llm_factory = lambda: FakeChatModel()
    result = run_design_brief(load_brief("minimal_brief.json"), config)

    dumped = result["metadata"].get("graph_dump")
    assert dumped and len(dumped) == 2
    json_path = next(p for p in dumped if p.endswith(".json"))
    dot_path = next(p for p in dumped if p.endswith(".dot"))
    # full dump keeps node data (unlike the metadata snapshot)
    payload = json.loads(open(json_path, encoding="utf-8").read())
    assert any("data" in node for node in payload["nodes"])
    assert open(dot_path, encoding="utf-8").read().startswith("digraph alignment {")


def test_objective_annotation_flags_unaligned_objective():
    graph = AlignmentGraph()
    graph.add_element_node(NodeType.OBJECTIVE, "LO-01", {"id": "LO-01", "level": "Apply"})
    graph.add_element_node("assessment", "AT-01", {"item_id": "AT-01"})
    graph.add_edge("R3-measures", "assessment:AT-01", "objective:LO-01", relation_id="R3", established_by="id")
    # measured only — no supports/evaluates edge -> not fully aligned
    ann = viz.objective_annotations(graph)["objective:LO-01"]
    assert ann["measured"] and not ann["supported"] and not ann["evaluated"]
    assert ann["aligned"] is False

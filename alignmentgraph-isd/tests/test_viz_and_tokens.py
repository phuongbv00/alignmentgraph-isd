"""Token-usage capture + the alignment-graph dump — both are reported
artifacts downstream analysis reads, so pin their shape."""
from __future__ import annotations

import json
import shutil
import subprocess

from alignmentgraph_isd import HarnessRunConfig
from alignmentgraph_isd.core.alignment_graph import viz
from alignmentgraph_isd.core.llm_io import _extract_token_usage
from alignmentgraph_isd.core.alignment_graph import AlignmentGraph, NodeType

from conftest import FakeChatModel, load_brief, run_brief


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

    config = HarnessRunConfig()
    config.llm_factory = lambda: TokenModel()
    result = run_brief(load_brief("minimal_brief.json"), config)
    usage = result["metadata"]["token_usage"]
    calls = usage["llm_calls"]
    assert calls > 0
    assert usage["prompt_tokens"] == 1000 * calls
    assert usage["completion_tokens"] == 500 * calls


# ── the graph dump: its own result keys + json/dot artifacts ─────────────────

def _run_default():
    config = HarnessRunConfig()
    config.llm_factory = lambda: FakeChatModel()
    return run_brief(load_brief("minimal_brief.json"), config)


def test_result_carries_full_graph_dump_separate_from_trajectory():
    result = _run_default()
    graph = result["graph"]

    assert {"nodes", "edges", "objective_alignment", "relation_coverage", "metadata"} <= set(graph)
    # FULL dump: every node keeps its complete data payload
    assert all("data" in node for node in graph["nodes"])
    # edges keep the structural fields the alignment analysis needs
    typed_edges = [e for e in graph["edges"] if e.get("relation_id")]
    assert typed_edges and all("established_by" in e for e in typed_edges)
    from alignmentgraph_isd.core.alignment_graph import alignment
    assert set(graph["relation_coverage"]) == set(alignment.REGISTRY)
    # dump metadata: brief id, timestamp, counts by type
    meta = graph["metadata"]
    assert meta["design_brief_id"] and meta["generated_at"]
    assert meta["node_count"] == len(graph["nodes"])
    assert meta["edge_count"] == len(graph["edges"])
    assert sum(meta["node_counts_by_type"].values()) == meta["node_count"]
    assert sum(meta["edge_counts_by_type"].values()) == meta["edge_count"]
    # the dump lives OUTSIDE trajectory/metadata (separate file downstream)
    assert "graph" not in result["metadata"]
    assert "graph" not in result["trajectory"]


def test_graph_dump_round_trips_through_json():
    result = _run_default()
    restored = json.loads(json.dumps(result["graph"], ensure_ascii=False))
    assert restored == result["graph"]


def _assert_valid_dot(dot: str) -> None:
    assert dot.startswith("digraph ") and dot.rstrip().endswith("}")
    # Balanced braces/brackets outside quoted strings, and quotes all closed.
    depth_brace = depth_bracket = 0
    in_string = escape = False
    for ch in dot:
        if escape:
            escape = False
            continue
        if in_string and ch == "\\":
            escape = True
            continue
        if ch == '"':
            in_string = not in_string
            continue
        if in_string:
            continue
        if ch == "{":
            depth_brace += 1
        elif ch == "}":
            depth_brace -= 1
            assert depth_brace >= 0
        elif ch == "[":
            depth_bracket += 1
        elif ch == "]":
            depth_bracket -= 1
            assert depth_bracket >= 0
    assert not in_string and depth_brace == 0 and depth_bracket == 0
    dot_bin = shutil.which("dot")
    if dot_bin:  # render for real when graphviz is installed
        proc = subprocess.run([dot_bin, "-Tsvg"], input=dot.encode("utf-8"),
                              capture_output=True, timeout=60)
        assert proc.returncode == 0, proc.stderr.decode()[:500]


def test_graph_dot_is_valid_dot_syntax():
    result = _run_default()
    _assert_valid_dot(result["graph_dot"])


def test_graph_dot_escapes_unicode_and_special_chars():
    graph = AlignmentGraph()
    graph.add_element_node(NodeType.OBJECTIVE, 'LO-"한글"',
                           {"id": 'LO-"한글"', "level": "Apply", "statement": '학습자는 "OOP"를\n적용한다'})
    graph.add_element_node("assessment", "AT-01", {"item_id": "AT-01", "type": "수행평가"})
    graph.add_edge("R3-measures", "assessment:AT-01", 'objective:LO-"한글"',
                   relation_id="R3", established_by="id")
    _assert_valid_dot(graph.to_dot(title='한국어 "브리프"'))


def test_graph_dump_written_when_env_opts_in(tmp_path, monkeypatch):
    monkeypatch.setenv("ALIGNMENTGRAPH_DUMP_DIR", str(tmp_path))
    result = _run_default()

    dumped = result["metadata"].get("graph_dump")
    assert dumped and len(dumped) == 2
    json_path = next(p for p in dumped if p.endswith(".json"))
    dot_path = next(p for p in dumped if p.endswith(".dot"))
    # the dumped file matches the in-result full dump (modulo timestamp)
    payload = json.loads(open(json_path, encoding="utf-8").read())
    assert any("data" in node for node in payload["nodes"])
    assert payload["metadata"]["design_brief_id"] == result["graph"]["metadata"]["design_brief_id"]
    assert open(dot_path, encoding="utf-8").read().startswith("digraph alignment {")


def _triad_graph(*, with_c4: bool, same_assessment: bool = True) -> AlignmentGraph:
    """An objective assessed by AT-01 and practiced by TLA-01, with the C4 edge
    optionally closing the triad — onto AT-01, or onto an unrelated item."""
    graph = AlignmentGraph()
    graph.add_element_node(NodeType.OBJECTIVE, "ILO-01", {"id": "ILO-01", "level": "apply"})
    graph.add_element_node(NodeType.ASSESSMENT, "AT-01", {"item_id": "AT-01"})
    graph.add_element_node(NodeType.ASSESSMENT, "AT-99", {"item_id": "AT-99"})
    graph.add_element_node(NodeType.ACTIVITY, "TLA-01", {"activity_name": "practice"})
    # C2 (assessed_by) and C3 (practiced_by) are id-reverse: source=LO.
    graph.add_edge("C2-assessed_by", "objective:ILO-01", "assessment:AT-01",
                   relation_id="C2", established_by="id")
    graph.add_edge("C3-practiced_by", "objective:ILO-01", "activity:TLA-01",
                   relation_id="C3", established_by="id")
    if with_c4:
        target = "assessment:AT-01" if same_assessment else "assessment:AT-99"
        graph.add_edge("C4-prepares_for", "activity:TLA-01", target,
                       relation_id="C4", established_by="id")
    return graph


def test_objective_annotation_flags_unaligned_objective():
    graph = AlignmentGraph()
    graph.add_element_node(NodeType.OBJECTIVE, "ILO-01", {"id": "ILO-01", "level": "apply"})
    graph.add_element_node(NodeType.ASSESSMENT, "AT-01", {"item_id": "AT-01"})
    # C2 (assessed_by) is id-reverse: source=LO, target=Assessment.
    graph.add_edge("C2-assessed_by", "objective:ILO-01", "assessment:AT-01", relation_id="C2", established_by="id")
    # measured (assessed) only — no practiced edge -> the triad cannot close
    ann = viz.objective_annotations(graph)["objective:ILO-01"]
    assert ann["measured"] and not ann["supported"]
    assert "evaluated" not in ann
    assert ann["aligned"] is False


def test_aligned_needs_the_triad_to_close():
    """C2 and C3 alone are two spokes. Before 2026-09-10 that read as aligned."""
    ann = viz.objective_annotations(_triad_graph(with_c4=False))["objective:ILO-01"]
    assert ann["measured"] and ann["supported"]
    assert ann["prepares"] is False
    assert ann["aligned"] is False

    ann = viz.objective_annotations(_triad_graph(with_c4=True))["objective:ILO-01"]
    assert ann["prepares"] is True
    assert ann["aligned"] is True


def test_c4_onto_an_unrelated_item_does_not_close_the_triad():
    """The activity prepares for SOMETHING, just not for what assesses this
    objective — the case a per-edge existential would wave through."""
    ann = viz.objective_annotations(
        _triad_graph(with_c4=True, same_assessment=False))["objective:ILO-01"]
    assert ann["measured"] and ann["supported"]
    assert ann["prepares"] is False
    assert ann["aligned"] is False


def test_bloom_is_no_longer_a_leg_of_aligned():
    """Bloom is a content condition; `aligned` is the structural triad. A
    closed triad stays aligned however the Bloom cross-check lands, and the
    cross-check is still reported on its own flags."""
    graph = _triad_graph(with_c4=True)
    # An Apply-level objective assessed by a recall-only item: the Bloom
    # cross-check fails while every structural edge stands.
    graph.update_node("assessment:AT-01", {"required_cognitive_process": "remember"})
    ann = viz.objective_annotations(graph)["objective:ILO-01"]
    assert ann["aligned"] is True
    assert ann["bloom_ok"] is False
    assert ann["bloom_notes"]

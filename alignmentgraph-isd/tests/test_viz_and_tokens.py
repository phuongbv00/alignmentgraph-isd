"""Token-usage capture + the alignment-graph dump — both are reported
artifacts downstream analysis reads, so pin their shape."""
from __future__ import annotations

import json
import shutil
import subprocess

import pytest

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


def test_rendered_dot_is_valid_dot_syntax():
    result = _run_default()
    _assert_valid_dot(viz.to_dot(result["graph"]))


def test_rendered_dot_escapes_unicode_and_special_chars():
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

    # ONE file: the DOT is a rendering of this payload, reproducible from it
    # (`alignmentgraph-isd dot <stem>.json`), so it is not written beside it.
    dumped = result["metadata"].get("graph_dump")
    assert dumped and len(dumped) == 1
    json_path = dumped[0]
    assert json_path.endswith(".json")
    # the dumped file matches the in-result full dump (modulo timestamp)
    payload = json.loads(open(json_path, encoding="utf-8").read())
    assert any("data" in node for node in payload["nodes"])
    assert payload["metadata"]["design_brief_id"] == result["graph"]["metadata"]["design_brief_id"]
    assert viz.to_dot(payload).startswith("digraph alignment {")


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
    assert ann["assessed_by"] and not ann["practiced_by"]
    assert "evaluated" not in ann
    assert ann["aligned"] is False


def test_aligned_needs_the_triad_to_close():
    """C2 and C3 alone are two spokes. Before 2026-09-10 that read as aligned."""
    ann = viz.objective_annotations(_triad_graph(with_c4=False))["objective:ILO-01"]
    assert ann["assessed_by"] and ann["practiced_by"]
    assert ann["prepares_for"] is False
    assert ann["aligned"] is False

    ann = viz.objective_annotations(_triad_graph(with_c4=True))["objective:ILO-01"]
    assert ann["prepares_for"] is True
    assert ann["aligned"] is True


def test_c4_onto_an_unrelated_item_does_not_close_the_triad():
    """The activity prepares for SOMETHING, just not for what assesses this
    objective — the case a per-edge existential would wave through."""
    ann = viz.objective_annotations(
        _triad_graph(with_c4=True, same_assessment=False))["objective:ILO-01"]
    assert ann["assessed_by"] and ann["practiced_by"]
    assert ann["prepares_for"] is False
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


# ── The payload as the single source both renderers read ────────────────────
# These pin the invariants the 2026-09-11 change rests on. Each one, if it
# broke, would look like nothing at all: the app would quietly fall back to
# computing display rules of its own, which is the arrangement this replaced.


def test_to_node_link_does_not_touch_the_live_graph():
    """`to_dict` hands back the LIVE node and edge dicts, and a `graph_snapshot`
    fires mid-run while later phases are still writing. Annotating in place
    would edit the running design."""
    graph = _triad_graph(with_c4=True)
    payload = viz.to_node_link(graph)

    assert all(set(node) == {"type", "id", "data"} for node in graph.get_nodes())
    assert all(set(edge) == {"type", "source", "target", "evidence", "rationale",
                             "relation_id", "established_by"} for edge in graph.get_edges())
    # Not the same objects, so a later mutation of the payload cannot reach the
    # graph either.
    assert payload["nodes"][0] is not graph.get_nodes()[0]
    assert payload["edges"][0] is not graph.get_edges()[0]


def test_dot_from_a_reloaded_payload_matches_the_live_render():
    """The property the whole design rests on: a saved `graph.json` renders the
    same DOT as the graph it came from, so the payload really is the artifact
    and the DOT really is just a view of it."""
    graph = _triad_graph(with_c4=True)
    payload = viz.to_node_link(graph)
    reloaded = AlignmentGraph.from_dict(payload)

    assert viz.to_dot(viz.to_node_link(reloaded), title="t") == graph.to_dot(title="t")


def test_a_payload_written_before_the_display_fields_is_upgraded():
    """An archived dump has no `label`, no edge `id`, no `legs`, no `legend`.
    It upgrades by passing through the producer's own function — which is what
    keeps those rules from being reimplemented in the browser for old runs."""
    graph = _triad_graph(with_c4=True)
    full = viz.to_node_link(graph)
    archived = {
        "nodes": [{k: v for k, v in n.items() if k in {"type", "id", "data"}}
                  for n in full["nodes"]],
        "edges": [{k: v for k, v in e.items()
                   if k in {"type", "source", "target", "evidence", "rationale",
                            "relation_id", "established_by"}} for e in full["edges"]],
        # Stripped too — this is the field the first version of the upgrade
        # forgot, and 33 of the 36 archived dumps then crashed `to_dot` with a
        # bare KeyError. A fixture that keeps it does not test the upgrade.
        "objective_alignment": {
            node_id: {k: v for k, v in flags.items() if k != "legs"}
            for node_id, flags in full["objective_alignment"].items()
        },
    }
    assert "schema_version" not in archived
    assert all("legs" not in f for f in archived["objective_alignment"].values())

    upgraded = viz.with_display_semantics(archived)
    assert upgraded["schema_version"] == viz.SCHEMA_VERSION
    assert all(node["label"] and node["kind"] for node in upgraded["nodes"])
    assert all(edge["id"] and edge["layer"] for edge in upgraded["edges"])
    assert all(flags["legs"] for flags in upgraded["objective_alignment"].values())
    assert upgraded["legend"]["nodes"]
    # Idempotent: upgrading an upgraded payload changes nothing.
    assert viz.with_display_semantics(upgraded) == upgraded
    assert viz.to_dot(archived).startswith("digraph alignment {")


def test_to_dot_refuses_a_graph_object():
    """It takes a payload now. Auto-converting would restore the two-input
    function the change exists to remove."""
    with pytest.raises(TypeError, match="node-link payload"):
        viz.to_dot(_triad_graph(with_c4=True))


def test_the_alignment_legs_are_declared_once():
    """`aligned`, the DOT letters, the app's badge and the inspector's flag rows
    are one ordered list. Adding a leg used to be four edits that could
    disagree — and the app's legend, a fifth, never learned about C4 at all."""
    from alignmentgraph_isd.core.alignment_graph import alignment

    ann = viz.objective_annotations(_triad_graph(with_c4=False))["objective:ILO-01"]
    assert [leg["relation_id"] for leg in ann["legs"]] == list(alignment.ALIGNMENT_LEGS)
    # The scalar beside each leg is named by that relation's own verb.
    for leg in ann["legs"]:
        assert ann[leg["verb"]] == leg["ok"]
    assert ann["aligned"] == all(leg["ok"] for leg in ann["legs"])
    assert ann["aligned"] is False
    # Wording comes from the registry, never written again: a leg IS a core
    # relation seen from the objective.
    for leg in ann["legs"]:
        assert leg["label"] == alignment.REGISTRY[leg["relation_id"]].label


def test_a_red_edge_names_the_check_that_actually_failed():
    """C2 reddens on the assessment rule, C3 on the activity rule. Under the
    old union, an objective whose ITEM was too shallow reddened its
    `practiced_by` edge too — pointing a reader at the wrong artifact."""
    graph = _triad_graph(with_c4=True)
    # The activity practices at the objective's own level, so only the
    # assessment rule can fail — which is the whole point of the split.
    graph.update_node("activity:TLA-01", {"learner_cognitive_process": "apply"})
    graph.update_node("assessment:AT-01", {"required_cognitive_process": "remember"})
    annotations = viz.to_node_link(graph)["objective_alignment"]["objective:ILO-01"]
    assert annotations["bloom_assessment_ok"] is False
    assert annotations["bloom_activity_ok"] is True

    edges = {e["relation_id"]: e for e in viz.to_node_link(graph)["edges"]}
    assert edges["C2"]["invalid"] is True
    assert edges["C2"]["invalid_reason"] == "bloom_assessment"
    # The union rule reddened this one too, for a failure in another artifact.
    assert edges["C3"]["invalid"] is False


def test_an_edge_id_is_stable_unique_and_covers_scaffolding():
    """Composed once, here. Composed twice in the webapp it drifted: the
    inspector dropped the `scaffold` prefix, so selecting a `narrates` edge
    from a node's relation list matched nothing on the canvas."""
    graph = _triad_graph(with_c4=True)
    graph.add_edge("narrates", "objective_0", "objective:ILO-01")
    payload = viz.to_node_link(graph)

    ids = [edge["id"] for edge in payload["edges"]]
    assert len(ids) == len(set(ids))
    assert all(ids)
    scaffolding = next(e for e in payload["edges"] if e["layer"] == "scaffolding")
    assert scaffolding["id"].startswith("scaffold|")
    assert scaffolding["tier"] == ""
    # Stable: re-serializing the same graph gives the same ids.
    assert [e["id"] for e in viz.to_node_link(graph)["edges"]] == ids


def test_an_edge_takes_its_layer_and_tier_from_the_registry():
    """Not from the id's first letter. A future secondary relation numbered C
    would otherwise land in the alignment layer by accident."""
    from alignmentgraph_isd.core.alignment_graph import alignment

    payload = viz.to_node_link(_triad_graph(with_c4=True))
    for edge in payload["edges"]:
        relation = alignment.REGISTRY[edge["relation_id"]]
        assert edge["tier"] == relation.tier
        assert edge["layer"] == ("alignment" if relation.tier == "core" else "provenance")
        # The edge type IS the registry's own key: "<id>-<verb>".
        assert edge["type"] == relation.key


def test_without_node_data_drops_data_and_nothing_else():
    """The server's wire view. It used to rebuild each node as a whitelist of
    `{id, type}`, which was the same thing only while a node carried nothing
    else worth keeping — the display fields now sit beside `data`, and a
    whitelist would take them out with it."""
    payload = viz.to_node_link(_triad_graph(with_c4=True))
    light = viz.without_node_data(payload)

    assert all("data" not in node for node in light["nodes"])
    for full_node, light_node in zip(payload["nodes"], light["nodes"]):
        assert set(full_node) - set(light_node) == {"data"}
        assert light_node["label"] and light_node["kind"]
    # Everything else rides across untouched.
    assert light["edges"] == payload["edges"]
    assert light["legend"] == payload["legend"]
    assert light["objective_alignment"] == payload["objective_alignment"]


def test_an_old_payload_keeps_the_red_edges_it_recorded():
    """29 of the 36 archived dumps predate `bloom_assessment_ok` and carry only
    the union. Judging them by a flag they do not have would silently drop
    every red edge — 13 real findings across two runs — so the union is the
    fallback: the coarser marking is what those runs themselves recorded."""
    graph = _triad_graph(with_c4=True)
    graph.update_node("assessment:AT-01", {"required_cognitive_process": "remember"})
    archived = viz.to_node_link(graph)
    archived["objective_alignment"] = {
        node_id: {k: v for k, v in flags.items()
                  if k not in {"bloom_assessment_ok", "bloom_activity_ok", "legs"}}
        for node_id, flags in archived["objective_alignment"].items()
    }

    edges = {e["relation_id"]: e for e in viz.with_display_semantics(archived)["edges"]}
    assert edges["C2"]["invalid"] is True
    assert edges["C3"]["invalid"] is True   # the union, as that run drew it

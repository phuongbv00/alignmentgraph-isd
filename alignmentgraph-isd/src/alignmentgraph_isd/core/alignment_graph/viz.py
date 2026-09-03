"""Dump the alignment graph to files a human can visualize.

A faithful snapshot of the REAL internal graph the harness built (not a
reconstruction from the ADDIE output) — it shows repair-added nodes, every
established edge's ``relation_id`` / ``established_by`` mechanism, and the
structural alignment state the verifier actually saw.

Two artifacts:
- ``<stem>.json`` — the full dump (``AlignmentGraph.to_full_dict``): node-link
  JSON with complete node payloads, per-objective and per-relation alignment
  annotations from the single definition in ``alignment.py`` (nothing
  re-implements the rules here), plus run metadata (brief id, timestamp,
  node/edge counts by type).
- ``<stem>.dot`` — GraphViz DOT, renderable in one command:
      dot -Tsvg <stem>.dot -o <stem>.svg

Colouring is the structural alignment state, not decoration:
- objective nodes: green when measured (C2) and supported (C3) and the
  Bloom/format rule holds, amber otherwise. The third leg went with C7 on
  2026-09-02, when a rubric criterion became a field of its assessment item.
- edges by establishment mechanism: id-match solid green, type-match solid blue,
  provenance solid grey; a C2/C3 edge that fails the Bloom/format rule is
  red-dashed (e.g. an MCQ assessing an Apply objective).
"""
from __future__ import annotations

import json
from pathlib import Path

from . import alignment
from .graph import AlignmentGraph, NodeType

_NODE_STYLE = {
    NodeType.COURSE_GOAL: {"shape": "diamond", "style": "filled", "fillcolor": "#fef3c7"},
    NodeType.OBJECTIVE: {"shape": "box", "style": "filled,rounded"},
    NodeType.ASSESSMENT: {"shape": "ellipse", "style": "filled", "fillcolor": "#dbeafe"},
    NodeType.ACTIVITY: {"shape": "ellipse", "style": "filled", "fillcolor": "#dcfce7"},
    NodeType.CONTENT: {"shape": "folder", "style": "filled", "fillcolor": "#f3f4f6"},
    NodeType.MATERIAL: {"shape": "folder", "style": "filled", "fillcolor": "#f3f4f6"},
    NodeType.IMPLEMENTATION_PLAN: {"shape": "component", "style": "filled", "fillcolor": "#f3f4f6"},
}
_ALIGNED_FILL = "#bbf7d0"      # green
_UNALIGNED_FILL = "#fde68a"    # amber
_EDGE_COLOR = {"id": "#16a34a", "type": "#2563eb", "provenance": "#6b7280"}
_INVALID_EDGE = "#dc2626"      # red — a measures edge failing the Bloom/format rule


def objective_annotations(graph: AlignmentGraph) -> dict[str, dict]:
    """Per-objective structural alignment: is it assessed and practiced, and
    does the Bloom cross-check hold? All read from the graph's established
    edges via the single alignment definition. C2 (assessed_by) and C3
    (practiced_by) are both id-reverse — the LO is the edge SOURCE."""
    bloom_violated = {v["node_id"] for v in alignment.bloom_assessment_violations(graph)}
    bloom_violated |= {v["node_id"] for v in alignment.bloom_activity_violations(graph)}
    out: dict[str, dict] = {}
    for node in graph.element_nodes(NodeType.OBJECTIVE):
        node_id = node["id"]
        assessed = bool(graph.get_edges(relation_id="C2", source=node_id))
        practiced = bool(graph.get_edges(relation_id="C3", source=node_id))
        bloom_ok = node_id not in bloom_violated
        # No rubric leg since 2026-09-02: a criterion is a field of the item it
        # marks, so "is this objective scored by a rubric" was true for every
        # objective that had an item at all. It never varied, so it never
        # narrowed `aligned` — dropping it changes the definition and not the
        # answer.
        out[node_id] = {
            "measured": assessed,
            "supported": practiced,
            "bloom_ok": bloom_ok,
            "aligned": assessed and practiced and bloom_ok,
        }
    return out


def to_node_link(graph: AlignmentGraph, *, include_data: bool = True) -> dict:
    """Node-link snapshot + alignment annotations.

    ``include_data=True`` (the disk dump) keeps each node's full ``data``
    payload. ``include_data=False`` (the always-in-metadata snapshot) drops it,
    since the payload duplicates the ADDIE output — the structural view
    (topology + each edge's ``relation_id``/``established_by`` + coverage) is
    what alignment inspection needs, at a fraction of the size."""
    payload = graph.to_dict()
    if not include_data:
        payload["nodes"] = [
            {k: v for k, v in node.items() if k != "data"}
            for node in payload["nodes"]
        ]
    payload["objective_alignment"] = objective_annotations(graph)
    payload["relation_coverage"] = alignment.all_relations_coverage(graph)
    return payload


def _esc(text: str) -> str:
    return str(text).replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")


def _node_label(node: dict, annotations: dict) -> str:
    data = node.get("data") or {}
    lines = [node["id"]]
    if node["type"] == NodeType.OBJECTIVE:
        level = data.get("level")
        if level:
            lines.append(f"level: {level}")
        ann = annotations.get(node["id"])
        if ann:
            flags = "".join([
                "M" if ann["measured"] else "·",
                "S" if ann["supported"] else "·",
                "" if ann["bloom_ok"] else " ⚠bloom",
            ])
            lines.append(("✓ " if ann["aligned"] else "✗ ") + flags)
    else:
        detail = data.get("type") or data.get("activity_name") or data.get("title") or data.get("item_id")
        if detail:
            lines.append(str(detail))
        if data.get("repaired"):
            lines.append("(repair)")
    return "\\n".join(_esc(line) for line in lines)


def _legend() -> list[str]:
    """A compact legend cluster: what edge colours and node fills mean.

    The edge label is just the relation key ("C2-assessed_by"); the *mechanism*
    (id/type/provenance) is carried by colour and explained here, so the graph
    itself stays low-ink."""
    return [
        "  subgraph cluster_legend {",
        '    label="Legend"; fontsize=11; style=dotted; color="#9ca3af"; fontname="Helvetica";',
        f'    leg_id [label="id-match edge", shape=plaintext, fontcolor="{_EDGE_COLOR["id"]}"];',
        f'    leg_type [label="type-match edge", shape=plaintext, fontcolor="{_EDGE_COLOR["type"]}"];',
        f'    leg_prov [label="provenance edge", shape=plaintext, fontcolor="{_EDGE_COLOR["provenance"]}"];',
        f'    leg_bad [label="Bloom/format ⚠ (invalid)", shape=plaintext, fontcolor="{_INVALID_EDGE}"];',
        f'    leg_ok [label="objective aligned (M/S ok)", shape=box, style="filled,rounded", fillcolor="{_ALIGNED_FILL}"];',
        f'    leg_gap [label="objective has a gap", shape=box, style="filled,rounded", fillcolor="{_UNALIGNED_FILL}"];',
        "    leg_id -> leg_type -> leg_prov -> leg_bad [style=invis];",
        "  }",
    ]


def to_dot(graph: AlignmentGraph, *, title: str = "") -> str:
    annotations = objective_annotations(graph)
    # Visualise the 16-relation matrix only: edges that carry a relation_id.
    # Internal scaffolding edges (``precedes``, relation_id="") stay in the JSON
    # dump but are dropped here — they add no matrix information and dominate the
    # picture. A node renders iff it is an objective or takes part in a matrix edge.
    matrix_edges = [e for e in graph.get_edges() if e.get("relation_id")]
    linked_ids = {e["source"] for e in matrix_edges} | {e["target"] for e in matrix_edges}
    bloom_violated_objectives = {v["node_id"] for v in alignment.bloom_assessment_violations(graph)}
    bloom_violated_objectives |= {v["node_id"] for v in alignment.bloom_activity_violations(graph)}

    lines = [
        "digraph alignment {",
        "  rankdir=LR;",
        "  concentrate=true;",           # merge parallel edges into the same head
        "  splines=true;",
        "  nodesep=0.35; ranksep=1.4;",
        '  node [fontname="Helvetica"];',
        '  edge [fontname="Helvetica", fontsize=9];',
    ]
    if title:
        lines.append(f'  labelloc="t"; label="{_esc(title)}"; fontname="Helvetica";')
    lines.extend(_legend())

    for node in graph.get_nodes():
        is_objective = node["type"] == NodeType.OBJECTIVE and graph.is_element(node["id"])
        if not is_objective and node["id"] not in linked_ids:
            continue
        style = dict(_NODE_STYLE.get(node["type"], {"shape": "ellipse", "style": "filled", "fillcolor": "#f3f4f6"}))
        if is_objective:
            ann = annotations.get(node["id"], {})
            style["fillcolor"] = _ALIGNED_FILL if ann.get("aligned") else _UNALIGNED_FILL
        attrs = ", ".join(f'{k}="{v}"' for k, v in style.items())
        lines.append(f'  "{_esc(node["id"])}" [label="{_node_label(node, annotations)}", {attrs}];')

    for edge in matrix_edges:
        established_by = edge.get("established_by", "")
        relation_id = edge.get("relation_id") or ""
        is_bad_bloom = relation_id in ("C2", "C3") and edge["source"] in bloom_violated_objectives
        if is_bad_bloom:
            color, style = _INVALID_EDGE, "dashed"
        else:
            color = _EDGE_COLOR.get(established_by, "#9ca3af")
            style = "dotted" if relation_id.startswith("P") else "solid"
        # Label is the relation key only; colour (+legend) carries the mechanism.
        label = str(edge["type"]) + (" ⚠" if is_bad_bloom else "")
        lines.append(
            f'  "{_esc(edge["source"])}" -> "{_esc(edge["target"])}" '
            f'[label="{_esc(label)}", color="{color}", style="{style}", fontcolor="{color}"];'
        )

    lines.append("}")
    return "\n".join(lines)


def dump(
    graph: AlignmentGraph,
    path_stem: str | Path,
    *,
    title: str = "",
    design_brief_id: str | None = None,
) -> list[Path]:
    """Write ``<stem>.json`` (the full dump, ``AlignmentGraph.to_full_dict``)
    and ``<stem>.dot``. Returns the paths written."""
    stem = Path(path_stem)
    stem.parent.mkdir(parents=True, exist_ok=True)
    json_path = stem.with_suffix(".json")
    dot_path = stem.with_suffix(".dot")
    payload = graph.to_full_dict(design_brief_id=design_brief_id)
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    dot_path.write_text(to_dot(graph, title=title), encoding="utf-8")
    return [json_path, dot_path]

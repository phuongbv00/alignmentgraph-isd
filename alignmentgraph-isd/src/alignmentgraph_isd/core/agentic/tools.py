"""Deterministic tool executors for the agentic arm.

EXPERIMENTAL ARM (see the package README): everything in this subpackage is
opt-in and imported only via ``core.agentic``; nothing in ``core/`` imports it.

Each tool wraps an existing read API (graph queries, relation coverage, the
per-step deterministic validation) and renders its observation with fixed
caps, so what the model sees is a pure function of graph state — the agency
is in WHICH tools the model calls, never in what a call returns.

The renderers are copied from ``core/agents/base.py`` (``_element_context``,
``_alignment_state`` + ``_render_state_structured``) — experimental arm,
keep in sync manually.
"""
from __future__ import annotations

import json
from typing import TYPE_CHECKING

from .. import checks
from ..alignment_graph import alignment

if TYPE_CHECKING:  # pragma: no cover - typing only
    from ..alignment_graph import AlignmentGraph
    from .specialists import AgenticStep

#: Rendering caps — same numbers as BaseISDAgent's, plus a node-count cap for
#: whole-type reads (the classic arm caps per call site; a tool cannot).
NODE_CHAR_CAP = 600
NODE_COUNT_CAP = 25
EDGE_LINE_CAP = 30
GAP_ID_CAP = 20


def render_nodes(nodes: list[dict], max_chars: int = NODE_CHAR_CAP,
                 max_nodes: int = NODE_COUNT_CAP) -> str:
    """One ``[TYPE:ID]`` block per node, data as truncated JSON.

    Copied from ``BaseISDAgent._element_context`` — keep in sync manually.
    """
    lines: list[str] = []
    for node in nodes[:max_nodes]:
        data_str = json.dumps(node.get("data", {}), ensure_ascii=False)
        if len(data_str) > max_chars:
            data_str = data_str[:max_chars] + "…"
        lines.append(f"[{str(node.get('type', '')).upper()}:{node.get('id', '')}]\n{data_str}")
    extra = len(nodes) - max_nodes
    if extra > 0:
        lines.append(f"... and {extra} more nodes")
    return "\n\n".join(lines) if lines else "(no nodes yet)"


def alignment_docket(graph: "AlignmentGraph", *, edges: tuple[str, ...] = (),
                     gaps: tuple[str, ...] = (), plan_pairs: bool = False) -> str:
    """The alignment-state block: established edges, instantiated coverage
    gaps, and unrealised plan pairs for the named relations.

    Copied from ``BaseISDAgent._alignment_state`` +
    ``_render_state_structured`` — keep in sync manually. Kept in the agentic
    arm because it is the deterministic scaffolding SLMs measurably need (an
    enumerated checklist over a universally-quantified rule); the agency this
    arm adds sits on top of it, not instead of it.
    """
    facts: dict = {"edges": [], "gaps": [], "plan_pairs": []}
    for rid in edges:
        relation = alignment.REGISTRY[rid]
        for edge in graph.get_edges(relation_id=rid):
            facts["edges"].append({
                "source": edge["source"], "target": edge["target"],
                "relation": relation.key,
            })
    for rid in gaps:
        relation = alignment.REGISTRY[rid]
        _, uncovered = alignment.relation_coverage(graph, rid)
        if uncovered:
            facts["gaps"].append({
                "relation": relation.key, "label": relation.label,
                "nodes": uncovered,
            })
    if plan_pairs:
        for violation in checks.plan_coverage(graph):
            facts["plan_pairs"].append({
                "objective": violation.metadata.get("lo_id", ""),
                "category": violation.metadata.get("plan_category", ""),
            })
    if not (facts["edges"] or facts["gaps"] or facts["plan_pairs"]):
        return ""

    lines: list[str] = ["=== ALIGNMENT STATE ==="]
    if facts["edges"]:
        lines.append("[EDGES]")
        for edge in facts["edges"][:EDGE_LINE_CAP]:
            lines.append(f"{edge['source']} --{edge['relation']}--> {edge['target']}")
        extra = len(facts["edges"]) - EDGE_LINE_CAP
        if extra > 0:
            lines.append(f"... and {extra} more edges")
    if facts["gaps"]:
        lines.append("[GAPS — your output must close these]")
        for gap in facts["gaps"]:
            ids = ", ".join(gap["nodes"][:GAP_ID_CAP])
            extra = len(gap["nodes"]) - GAP_ID_CAP
            more = f" (+{extra} more)" if extra > 0 else ""
            lines.append(f"{gap['relation']} missing for: {ids}{more}")
    if facts["plan_pairs"]:
        lines.append("[PLAN-PROMISED PAIRS, NOT YET REALISED — produce exactly these]")
        lines.append("; ".join(f"{p['objective']} x {p['category']}" for p in facts["plan_pairs"]))
    return "\n".join(lines)


# ── tool executors ──────────────────────────────────────────────────────────
# Uniform contract: (graph, step, args) -> observation string. Errors are
# returned as "ERROR: ..." observations — the model gets to correct itself
# inside its turn budget instead of the run failing.


def run_read_nodes(graph: "AlignmentGraph", step: "AgenticStep", args: dict) -> str:
    node_type = str(args.get("node_type", "")).strip().lower()
    if node_type not in step.readable_types:
        return ("ERROR: node_type must be one of: "
                + ", ".join(step.readable_types))
    nodes = graph.element_nodes(node_type)
    if not nodes:
        # Section-only artifacts (learner_profile, the plan nodes) have no
        # element pool; fall back to their section node so the read still
        # answers.
        nodes = graph.section_nodes(node_type)
    return render_nodes(nodes)


def run_read_node(graph: "AlignmentGraph", step: "AgenticStep", args: dict) -> str:
    node_id = str(args.get("id", "")).strip()
    if not node_id:
        return 'ERROR: args must carry {"id": "<node id>"}'
    node = graph.get_node(node_id)
    if node is None and graph.ELEMENT_SEP not in node_id:
        # Convenience: a bare element id ("ILO-01") resolves against the
        # readable types' namespaces.
        for node_type in step.readable_types:
            node = graph.get_node(f"{node_type}{graph.ELEMENT_SEP}{node_id}")
            if node is not None:
                break
    if node is None:
        return f"ERROR: no node with id {node_id!r}"
    return render_nodes([node])


def run_read_edges(graph: "AlignmentGraph", step: "AgenticStep", args: dict) -> str:
    rid = str(args.get("relation_id", "")).strip().upper()
    if rid not in step.relations:
        return "ERROR: relation_id must be one of: " + ", ".join(step.relations)
    relation = alignment.REGISTRY[rid]
    edges = graph.get_edges(relation_id=rid)
    if not edges:
        return f"(no {relation.key} edges yet)"
    lines = [f"{e['source']} --{relation.key}--> {e['target']}" for e in edges[:EDGE_LINE_CAP]]
    extra = len(edges) - EDGE_LINE_CAP
    if extra > 0:
        lines.append(f"... and {extra} more edges")
    return "\n".join(lines)


def run_coverage_gaps(graph: "AlignmentGraph", step: "AgenticStep", args: dict) -> str:
    rid = str(args.get("relation_id", "")).strip().upper()
    if rid not in step.relations:
        return "ERROR: relation_id must be one of: " + ", ".join(step.relations)
    relation = alignment.REGISTRY[rid]
    _, uncovered = alignment.relation_coverage(graph, rid)
    if not uncovered:
        return f"OK: every node is covered by {relation.key}"
    ids = ", ".join(uncovered[:GAP_ID_CAP])
    extra = len(uncovered) - GAP_ID_CAP
    more = f" (+{extra} more)" if extra > 0 else ""
    return f"{relation.key} ({relation.label}) missing for: {ids}{more}"


def unwrap_section(section: dict, validate) -> tuple[dict, list[str]]:
    """Deterministic envelope tolerance: small models often wrap the artifact
    under one extra key ({"artifact": {...}}, {"draft": {...}}, or the
    artifact's own name) despite the protocol. Try the object as given, then
    one level of unwrapping; return the first candidate that validates,
    otherwise the original object with its errors. Measured failure this
    answers: a 2B model wrapped the implementation plan as {"artifact": ...}
    on every attempt, shipped an empty-looking section and scored 0 on the
    whole Implementation phase."""
    if not isinstance(section, dict):
        return {}, validate({})
    errors = validate(section)
    if not errors:
        return section, []
    candidates: list[dict] = []
    for key in ("artifact", "draft", "section", "args"):
        value = section.get(key)
        if isinstance(value, dict) and value:
            candidates.append(value)
    if len(section) == 1:
        only = next(iter(section.values()))
        if isinstance(only, dict) and only:
            candidates.append(only)
    for candidate in candidates:
        if not validate(candidate):
            return candidate, []
    return section, errors


def run_check_artifact(graph: "AlignmentGraph", step: "AgenticStep", args: dict) -> str:
    _draft, errors = unwrap_section(args or {}, step.validate)
    if not errors:
        return "OK: the draft passes the deterministic checks. Submit it."
    return "ISSUES:\n- " + "\n- ".join(errors)


EXECUTORS = {
    "read_nodes": run_read_nodes,
    "read_node": run_read_node,
    "read_edges": run_read_edges,
    "coverage_gaps": run_coverage_gaps,
    "check_artifact": run_check_artifact,
}


def tool_menu(step: "AgenticStep", *, retrieval_available: bool = False) -> str:
    """The tool list rendered into the step's system prompt. Only tools whose
    allowlists are non-empty for this step are offered — an empty menu line
    invites wasted turns on a small model."""
    lines: list[str] = []
    if step.readable_types:
        types = ", ".join(step.readable_types)
        lines.append(f'- read_nodes: args {{"node_type": "<one of: {types}>"}} — '
                     "list the existing artifacts of that type.")
        lines.append('- read_node: args {"id": "<node id>"} — one artifact in full.')
    if step.relations:
        rels = ", ".join(step.relations)
        lines.append(f'- read_edges: args {{"relation_id": "<one of: {rels}>"}} — '
                     "the alignment links already established for that relation.")
        lines.append(f'- coverage_gaps: args {{"relation_id": "<one of: {rels}>"}} — '
                     "which artifacts that relation still leaves uncovered.")
    lines.append('- check_artifact: args = your draft artifact object — '
                 "run the deterministic checks on it before submitting.")
    if retrieval_available:
        lines.append('- retrieve: args {"query": "<what to fetch, specific>"} — '
                     "fetch external domain material (templates, conventions, examples).")
    lines.append("- submit: args = the COMPLETE artifact object in the exact schema below. "
                 "This ends your work on this artifact.")
    return "\n".join(lines)

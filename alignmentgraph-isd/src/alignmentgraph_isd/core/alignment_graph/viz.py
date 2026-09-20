"""Dump the alignment graph to files a human can visualize.

A faithful snapshot of the REAL internal graph the harness built (not a
reconstruction from the ADDIE output) — it shows repair-added nodes, every
established edge's ``relation_id`` / ``established_by`` mechanism, and the
structural alignment state the verifier actually saw.

ONE artifact, two renderings of it:
- ``<stem>.json`` — the dump (``AlignmentGraph.to_full_dict``): node-link JSON
  with complete node payloads, per-objective and per-relation alignment
  annotations from the single definition in ``alignment.py`` (nothing
  re-implements the rules here), the display semantics below, plus run metadata
  (brief id, timestamp, node/edge counts by type).
- GraphViz DOT, rendered FROM that payload on demand and never persisted:
      alignmentgraph-isd dot <stem>.json -o <stem>.dot
      dot -Tsvg <stem>.dot -o <stem>.svg

The payload carries every DISPLAY SEMANTIC, and that is the point of it: a node
knows its ``label`` and ``kind``, an edge its ``id``, ``layer``, ``tier`` and
whether it is ``invalid``, an objective the ordered ``legs`` of its alignment,
and the whole graph its ``legend``. Two rules follow, and both are load-bearing:

- **Colour and shape are the renderer's, everything else is the payload's.**
  GraphViz and cytoscape share no primitives (there is no ``folder`` shape in
  cytoscape), so each keeps a key -> style table and nothing more.
- **No renderer reads** ``node["data"]`` **to draw.** That is what lets the
  server's wire frame drop ``data`` and stay complete, and it is why
  ``label``/``detail``/``level``/``repaired`` exist as fields.

A relation is named by ``alignment.REGISTRY`` — its ``edge_type`` verb
(``assessed_by``) and its ``label`` sentence — verbatim, everywhere, in both
renderers. No synonyms and no reversed phrasings: that is how the app came to
call C1 "derived from" and P10 "scheduled by", words this system does not use.

Colouring is the structural alignment state, not decoration (DOT's table; the
webapp keeps its own against the same legend keys):
- objective nodes: green when the constructive-alignment triad CLOSES on the
  objective — it is ``assessed_by`` an item (C2), ``practiced_by`` an activity
  (C3), and that activity ``prepares_for`` that item (C4) — amber otherwise.
  Those three verbs are the relations' own, and they are what the legs are
  reported under. Bloom is not part of that test; it is a content condition and
  rides as a separate ⚠ on the label and on the offending edge.
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
    NodeType.MODULE: {"shape": "folder", "style": "filled", "fillcolor": "#f3f4f6"},
    NodeType.MATERIAL: {"shape": "folder", "style": "filled", "fillcolor": "#f3f4f6"},
    NodeType.IMPLEMENTATION_PLAN: {"shape": "component", "style": "filled", "fillcolor": "#f3f4f6"},
    NodeType.SESSION_GUIDE: {"shape": "note", "style": "filled", "fillcolor": "#f3f4f6"},
}
#: The node type an archived dump wrote for what is now ``NodeType.MODULE``.
#: Read here and in the webapp's style tables, and nowhere else: a dump is a
#: record, so its ``type`` values are drawn as written, never rewritten.
_LEGACY_NODE_TYPES = {"content": NodeType.MODULE}
_ALIGNED_FILL = "#bbf7d0"      # green
_UNALIGNED_FILL = "#fde68a"    # amber
_EDGE_COLOR = {"id": "#16a34a", "type": "#2563eb", "provenance": "#6b7280"}
#: red — an `assessed_by` (C2) or `practiced_by` (C3) edge failing its own
#: Bloom/format rule. Named by the relation's own verb: there is no relation
#: called "measures", and a synonym here is how the webapp came to invent a
#: whole vocabulary of its own ("derived from", "traceable to", "scheduled by").
_INVALID_EDGE = "#dc2626"

#: The node id separator, borrowed rather than restated: `kind` must agree with
#: `AlignmentGraph.is_element`, which is the authority on what an element is.
ELEMENT_SEP = AlignmentGraph.ELEMENT_SEP

#: Bumped when the display fields below change shape. A payload that does not
#: carry it predates them and is upgraded on read (`with_display_semantics`).
SCHEMA_VERSION = 2


def objective_annotations(graph: AlignmentGraph) -> dict[str, dict]:
    """Per-objective structural alignment: does the constructive-alignment
    triad close on this objective, and does the Bloom cross-check hold?

    All read from the graph's established edges via the single alignment
    definition. C2 (assessed_by) and C3 (practiced_by) are both id-reverse —
    the LO is the edge SOURCE — while C4 (prepares_for) runs activity→
    assessment and touches the objective only through those two.

    ``aligned`` is the Biggs triad CLOSED on the objective: it is practiced by
    an activity that prepares for an item that assesses that same objective.
    Two things make that a statement the paper can carry:

    * C4 is IN. "Assessed" and "practiced" alone are two independent
      existentials — an objective could be measured by one item and rehearsed
      by an activity pointing at some unrelated item, and still read aligned.
      The third edge is what makes it a triangle rather than two spokes, and it
      is the edge the RQ2 panel's third family-A signal measures, so the
      predicate and the measurement name the same three relations.
    * ``bloom_ok`` is OUT. Bloom is a CONTENT condition, and this predicate is
      the one ``alignment.py`` documents as "the single definition of what
      aligned means STRUCTURALLY" — the same module that calls Bloom
      "attribute-based, not an edge". It stands as its own flag below, where a
      reader who wants the cognitive check can find it.

    Both differ from the predicate any archived run recorded, so ``aligned`` is
    not comparable across them."""
    assessment = {v["node_id"]: v for v in alignment.bloom_assessment_violations(graph)}
    activity = {v["node_id"]: v for v in alignment.bloom_activity_violations(graph)}
    out: dict[str, dict] = {}
    for node in graph.element_nodes(NodeType.OBJECTIVE):
        node_id = node["id"]
        assessing = {e["target"] for e in graph.get_edges(relation_id="C2", source=node_id)}
        practicing = {e["target"] for e in graph.get_edges(relation_id="C3", source=node_id)}
        assessed = bool(assessing)
        practiced = bool(practicing)
        # The closing edge, and the reason it is quantified over BOTH sets
        # rather than asked of either alone: "some activity of mine prepares
        # for something" and "some item of mine is prepared for by something"
        # are each satisfiable without the triangle ever meeting.
        prepares = any(
            edge["target"] in assessing
            for activity_id in practicing
            for edge in graph.get_edges(relation_id="C4", source=activity_id)
        )
        # SPLIT, because the union answered "something Bloom is wrong" and the
        # reader then had to open the trajectory to learn which of the two —
        # the question this whole flag was supposed to answer.
        #
        # TRI-STATE, and `None` is the load-bearing value: both checks group by
        # the C2/C3 edges they read, so an objective nothing assesses produces
        # no violation and an objective whose `level` is outside the taxonomy
        # is skipped outright. Read as a boolean that is "not violated", and
        # the inspector drew a green "assessed at its own Bloom level (C2)"
        # beside a red C2 leg on the very objective that had no item at all.
        # A check that did not run must not report a pass.
        stated = alignment.bloom_level_of(str(node["data"].get("level", ""))) is not None
        bloom_assessment_ok = _bloom_flag(node_id, assessment, stated and assessed)
        bloom_activity_ok = _bloom_flag(node_id, activity, stated and practiced)
        # The conjunction as `to_dot` and every archived payload read it: a
        # check that could not run raises no ⚠, which is what it did before.
        bloom_ok = bloom_assessment_ok is not False and bloom_activity_ok is not False
        # No rubric leg: a criterion is a field of the item it marks, so "is
        # this objective scored by a rubric" holds for every objective that has
        # an item at all. It cannot vary, so it cannot narrow `aligned`.
        held = {"C2": assessed, "C3": practiced, "C4": prepares}
        #: The legs as a RENDERABLE list, in the order `ALIGNMENT_LEGS` declares
        #: — what the DOT label, the app's badge and the inspector's flag rows
        #: all read, so the three cannot show different legs in different orders.
        #: Every word in it comes from the REGISTRY: a leg is a core relation
        #: seen from the objective, so the verb and the wording are the
        #: relation's own. `ok` is the only thing this function contributes.
        legs = [
            {"relation_id": relation_id,
             "verb": alignment.leg_verb(relation_id),
             "label": alignment.REGISTRY[relation_id].label,
             "ok": held[relation_id]}
            for relation_id in alignment.ALIGNMENT_LEGS
        ]
        out[node_id] = {
            # One scalar per leg, named by the relation's own VERB — never an
            # invented name, which would be a third set of words for C2/C3/C4
            # beside the registry's and the app's. Nothing outside this package
            # reads them (no benchmark script, no evaluator); an archived dump
            # naming them otherwise is read through `_LEGACY_LEG_FLAGS`.
            **{leg["verb"]: leg["ok"] for leg in legs},
            #: True = the rule holds, False = it is violated, None = it could
            #: not be applied (nothing to judge against, or a `level` outside
            #: the taxonomy). A renderer must tell the third apart from the
            #: first: they are "checked and fine" and "not checked".
            "bloom_ok": bloom_ok,
            "bloom_assessment_ok": bloom_assessment_ok,
            "bloom_activity_ok": bloom_activity_ok,
            #: The checks' own messages, verbatim. A flag that says what was
            #: found — the level, the best level reached, the field to edit —
            #: instead of a boolean whose two causes were unioned away.
            "bloom_notes": [v["message"] for v in
                            (assessment.get(node_id), activity.get(node_id)) if v],
            "legs": legs,
            #: Derived FROM `legs` rather than written out again, so the
            #: predicate and what a reader is shown cannot disagree.
            "aligned": all(leg["ok"] for leg in legs),
        }
    return out



def _bloom_flag(node_id: str, violations: dict[str, dict], checkable: bool) -> bool | None:
    """One Bloom flag: ``True`` held, ``False`` violated, ``None`` not checked.

    The check reports a violation or says nothing, and "says nothing" has two
    causes — it found no fault, or it never ran on this objective. Both
    ``bloom_assessment_violations`` and ``bloom_activity_violations`` group by
    the C2/C3 edges they read and skip an objective whose ``level`` is not one
    of Bloom's six, so an objective nothing assesses and an objective assessed
    at its own level were the same value.
    """
    if node_id in violations:
        return False
    return True if checkable else None


def _node_display(node: dict) -> dict:
    """The display fields of one node: what a renderer needs and nothing else.

    ``label``/``detail``/``level``/``repaired`` exist so that **no renderer
    reads** ``node["data"]`` **to draw anything**. Left inside the DOT label
    composer, that four-branch ``or`` chain is a derivation the webapp has to
    either duplicate or do without — and doing without shows a bare id.

    It is also what makes the server's light view safe: that frame drops
    ``data`` and nothing else, and ``data`` is by this rule not part of drawing.
    """
    data = node.get("data") or {}
    node_id = str(node.get("id", ""))
    node_type = str(node.get("type", ""))
    element = ELEMENT_SEP in node_id
    is_objective = node_type == NodeType.OBJECTIVE
    return {
        # Element: the item id it carries (`objective:LO-01` -> `LO-01`).
        # Section: the type, because a section node IS its type.
        "label": node_id.split(ELEMENT_SEP, 1)[-1] if element else (node_type or node_id),
        "kind": "element" if element else "section",
        "detail": "" if is_objective else str(
            data.get("type") or data.get("activity_name")
            or data.get("title") or data.get("item_id") or ""),
        "level": str(data.get("level") or "") if is_objective else "",
        "repaired": bool(data.get("repaired")),
    }


#: The verbs the structural relations stamp, for reading an archived payload
#: whose edges predate their registration (see ``_edge_display``).
_STRUCTURAL_EDGE_TYPES = frozenset(r.edge_type for r in alignment.STRUCTURAL.values())


def _edge_display(edge: dict, annotations: dict) -> dict:
    """The display fields of one edge.

    ``id`` is the identity tuple ``_find_edge`` matches on, rendered as one
    string — so it is unique, and stable across snapshots because those four
    fields never change after an edge is created (only ``evidence``,
    ``rationale`` and ``established_by`` are refreshed). Composed HERE and
    nowhere else, so the inspector cannot compose a different one: an inspector
    that drops the ``scaffold`` fallback matches nothing on the canvas when a
    ``narrates`` edge is selected from a node's relation list.

    ``tier``/``layer`` come from ``REGISTRY``, not from the id's first letter.
    The prefix is only a fallback for an id the registry does not know (a test
    fixture's ``R3``); with the registry in charge, a secondary relation
    numbered C cannot land in the alignment layer by accident.
    """
    relation_id = str(edge.get("relation_id") or "")
    relation = alignment.REGISTRY.get(relation_id)
    if relation is not None:
        tier = relation.tier
    elif relation_id:
        tier = "core" if relation_id.startswith("C") else "secondary"
    else:
        # An archived payload written before the S relations were registered
        # carries "" on exactly the edges they name, so an empty id still means
        # structural.
        tier = "structural" if edge.get("type") in _STRUCTURAL_EDGE_TYPES else ""
    # An `assessed_by`/`practiced_by` edge out of an objective whose Bloom level
    # does not hold up. Each side is judged by ITS OWN check: a `practiced_by`
    # edge reddened because an assessment ITEM was too shallow pointed a reader
    # at the wrong artifact, and splitting `bloom_ok` in two existed precisely
    # to answer "which of the two failed".
    #
    # A payload older than the split flags (29 of 36 archived dumps) has only
    # the union, so it falls back to it — the coarser marking is what that run
    # itself recorded, and dropping the red edge entirely would lose 13 real
    # findings rather than re-describe them.
    flags = annotations.get(str(edge.get("source", ""))) or {}
    union = flags.get("bloom_ok")
    reason = ""
    if relation_id == "C2" and flags.get("bloom_assessment_ok", union) is False:
        reason = "bloom_assessment"
    elif relation_id == "C3" and flags.get("bloom_activity_ok", union) is False:
        reason = "bloom_activity"
    return {
        "id": "|".join((relation_id or "scaffold", str(edge.get("source", "")),
                        str(edge.get("target", "")), str(edge.get("type", "")))),
        "layer": ("scaffolding" if tier in ("structural", "")
                  else "alignment" if tier == "core" else "provenance"),
        "tier": tier,
        "invalid": bool(reason),
        "invalid_reason": reason,
    }


#: The invented leg names an archived payload may carry instead of the
#: relations' own verbs. Read-only, and the only place these words survive:
#: 36 archived dumps carry them, and re-rendering one must not silently lose a
#: leg to a field name this package does not write.
_LEGACY_LEG_FLAGS = {"C2": "measured", "C3": "supported", "C4": "prepares"}


def _with_legs(annotation: dict) -> dict:
    """Backfill an objective's ordered ``legs`` from the scalars beside them.

    An archived payload has the scalars but no list — and everything that draws
    a leg reads the list. A leg the payload says nothing about is DROPPED
    rather than rendered as a failure: a dump from before ``prepares`` existed
    is silent about C4, and a `✗` there would be an answer that run never gave.
    """
    if "legs" in annotation:
        return annotation
    legs = []
    for relation_id in alignment.ALIGNMENT_LEGS:
        verb = alignment.leg_verb(relation_id)
        for field in (verb, _LEGACY_LEG_FLAGS[relation_id]):
            if field in annotation:
                legs.append({"relation_id": relation_id, "verb": verb,
                             "label": alignment.REGISTRY[relation_id].label,
                             "ok": bool(annotation[field])})
                break
    return {**annotation, "legs": legs}


def with_display_semantics(payload: dict) -> dict:
    """A NEW payload whose nodes and edges carry their display fields.

    The one place display semantics are decided, and therefore the one place
    both renderers read: ``to_dot`` below, and the webapp. Pure and idempotent,
    and it needs only ``nodes``/``edges``/``objective_alignment``, which every
    archived dump already has — so a ``graph.json`` written before this existed
    upgrades by passing through here rather than by the browser computing the
    same rules a second time in another language.

    **Never mutates its input.** ``AlignmentGraph.to_dict`` hands back the LIVE
    node and edge dicts, so writing a key here would edit the running graph.
    Every node and edge is shallow-copied before a field is added.

    That copy is shallow on purpose: ``data`` is still the live object it
    always was, so a ``graph_snapshot`` must STILL be serialized on the
    producing thread (``server/runner.py`` rule 1, ``run_report._graph_attaching``).
    This function reads like it hands back a safe copy and it does not — it
    makes the wrappers safe and leaves ``data`` aliased. Deep-copying would cost
    the whole payload on every frame to buy what that rule already gives.
    """
    annotations = {node_id: _with_legs(annotation)
                   for node_id, annotation in (payload.get("objective_alignment") or {}).items()}
    return {
        **payload,
        "nodes": [{**node, **_node_display(node)} for node in payload.get("nodes") or []],
        "edges": [{**edge, **_edge_display(edge, annotations)}
                  for edge in payload.get("edges") or []],
        "objective_alignment": annotations,
        "legend": _legend_entries(),
        "schema_version": SCHEMA_VERSION,
    }


def without_node_data(payload: dict) -> dict:
    """The same payload with each node's ``data`` dropped, and nothing else lost.

    The server's wire view. It is here, beside the producer, rather than in the
    server, because the server must be able to LEAVE OUT but never to decide:
    an earlier version of this lived there and rebuilt each node as a whitelist
    of ``{id, type}``, which silently discards every field above.
    """
    return {
        **payload,
        "nodes": [{k: v for k, v in node.items() if k != "data"}
                  for node in payload.get("nodes") or []],
    }


def to_node_link(graph: AlignmentGraph) -> dict:
    """Node-link snapshot + alignment annotations + display semantics."""
    payload = graph.to_dict()          # LIVE dicts — never written to
    payload["objective_alignment"] = objective_annotations(graph)
    payload["relation_coverage"] = alignment.all_relations_coverage(graph)
    payload["node_violations"] = node_violations(graph)
    return with_display_semantics(payload)   # ← the copy


def node_violations(graph: AlignmentGraph) -> dict[str, list[str]]:
    """``node_id -> the violation types standing against it``, for EVERY node.

    ``objective_alignment`` only covers objectives, because it is built by
    walking ``element_nodes(OBJECTIVE)`` — so an activity linked to no
    objective, a material whose module does not exist, an item with no answer
    key had no signal anywhere on the graph. The one place a reader looks first
    said nothing about them.

    Types only, not messages: this rides in the graph payload the browser gets
    on every update, and the messages are already in the run's ledger, which
    the Violations tab serves in full."""
    # Lazy: `checks` imports this package, so a module-level import here
    # would close the loop. The direction is the odd one — a renderer
    # reading the verification layer — and it is deliberate: the badge has
    # to ride in the payload the browser already gets, and the payload is
    # built here.
    from .. import checks

    out: dict[str, list[str]] = {}
    for check in (checks.bloom_verbs, checks.measurability, checks.rubric_consistency,
                  checks.plan_coverage, checks.item_completeness,
                  checks.evaluation_quality, checks.activity_engagement,
                  checks.evidence_alignment, checks.blueprint_consistency,
                  checks.set_alignment, checks.media_coverage,
                  checks.actionability, checks.relation_coverage,
                  checks.bloom_mismatches):
        for violation in check(graph):
            types = out.setdefault(violation.node_id, [])
            if violation.violation_type not in types:
                types.append(violation.violation_type)
    return {node_id: sorted(types) for node_id, types in out.items()}


def _esc(text: str) -> str:
    return str(text).replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")


def _leg_flags(annotation: dict) -> str:
    """``C2 C3 C4`` / ``C2 · C4``: the legs in the declared order, each named or
    replaced by a dot.

    The relation's own id, never an initial: a glyph like ``MSP`` spells an
    invented name for the leg, which is the one thing the registry exists to
    stop."""
    return " ".join(leg["relation_id"] if leg["ok"] else "·" for leg in annotation["legs"])


def _node_label(node: dict, annotations: dict) -> str:
    """The DOT label, composed from the node's DISPLAY fields.

    Reads no ``data``: whatever a renderer needs to draw was decided once, in
    ``_node_display``. DOT names a node by its id, so that is the first line
    here where the app uses ``label`` — the same declared fields, a different
    choice of which to show."""
    lines = [node["id"]]
    if node["type"] == NodeType.OBJECTIVE:
        if node.get("level"):
            lines.append(f"level: {node['level']}")
        ann = annotations.get(node["id"])
        if ann:
            flags = _leg_flags(ann) + ("" if ann["bloom_ok"] else " ⚠bloom")
            lines.append(("✓ " if ann["aligned"] else "✗ ") + flags)
    else:
        if node.get("detail"):
            lines.append(str(node["detail"]))
        if node.get("repaired"):
            lines.append("(repair)")
    return "\\n".join(_esc(line) for line in lines)


def _legend_entries() -> dict[str, list[dict]]:
    """The legend as MEANING — what each key says — with no colour and no shape.

    It ships in the payload so both renderers read ONE list. A legend kept per
    renderer drifts: four edge rows and two node rows on one side against four
    and six on the other, with the alignment legs missing from the app's
    entirely, so the green fill it explains cannot be traced to the three
    relations that produce it.

    The aligned row is composed from ``ALIGNMENT_LEGS``, so it cannot go stale
    the way a hand-written "(M/S ok)" does when a leg is added."""
    leg_ids = "/".join(alignment.ALIGNMENT_LEGS)
    return {
        "edges": [
            {"key": "id", "label": "id-match edge"},
            {"key": "type", "label": "type-match edge"},
            {"key": "provenance", "label": "provenance edge"},
            {"key": "secondary", "label": "secondary (P) relation"},
            {"key": "invalid", "label": "Bloom/format ⚠ (invalid)"},
        ],
        "nodes": [
            {"key": "objective_aligned", "label": f"objective aligned ({leg_ids} ok)"},
            {"key": "objective_unaligned", "label": "objective has a gap"},
            {"key": "course_goal", "label": "course goal"},
            {"key": "assessment", "label": "assessment task (AT)"},
            {"key": "activity", "label": "activity (TLA)"},
            {"key": "module", "label": "module / material"},
            {"key": "section", "label": "section node (a whole ADDIE section)"},
            {"key": "has_violation", "label": "a check failed on this node"},
        ],
    }


#: DOT can only draw the rows it has a colour or a fill for; the app draws the
#: rest. Each renderer owns its own key -> style table, which is the whole of
#: what a renderer still decides after this change.
_LEGEND_DOT_EDGE_COLOR = {
    "id": _EDGE_COLOR["id"], "type": _EDGE_COLOR["type"],
    "provenance": _EDGE_COLOR["provenance"], "invalid": _INVALID_EDGE,
}
_LEGEND_DOT_NODE_FILL = {
    "objective_aligned": _ALIGNED_FILL, "objective_unaligned": _UNALIGNED_FILL,
}


def _legend(entries: dict[str, list[dict]]) -> list[str]:
    """A compact legend cluster, rendered from the payload's own legend.

    The edge label is just the relation key ("C2-assessed_by"); the *mechanism*
    (id/type/provenance) is carried by colour and explained here, so the graph
    itself stays low-ink."""
    lines = [
        "  subgraph cluster_legend {",
        '    label="Legend"; fontsize=11; style=dotted; color="#9ca3af"; fontname="Helvetica";',
    ]
    drawn = []
    for index, entry in enumerate(entries.get("edges") or []):
        colour = _LEGEND_DOT_EDGE_COLOR.get(entry["key"])
        if not colour:
            continue
        name = f"leg_e{index}"
        drawn.append(name)
        lines.append(f'    {name} [label="{_esc(entry["label"])}", shape=plaintext, '
                     f'fontcolor="{colour}"];')
    for index, entry in enumerate(entries.get("nodes") or []):
        fill = _LEGEND_DOT_NODE_FILL.get(entry["key"])
        if not fill:
            continue
        lines.append(f'    leg_n{index} [label="{_esc(entry["label"])}", shape=box, '
                     f'style="filled,rounded", fillcolor="{fill}"];')
    if len(drawn) > 1:
        lines.append("    " + " -> ".join(drawn) + " [style=invis];")
    lines.append("  }")
    return lines


def to_dot(payload: dict, *, title: str = "") -> str:
    """Render a node-link PAYLOAD as GraphViz DOT.

    Takes the payload, not a graph, so that everything DOT draws has to be a
    declared field — which is what makes the browser and this renderer show the
    same picture instead of two independent readings of the same graph. A live
    graph renders through ``AlignmentGraph.to_dot``.

    An archived payload (no ``schema_version``) is upgraded on the way in, so
    this is the only place the renderer computes anything, and only for a file
    written before the fields existed."""
    if isinstance(payload, AlignmentGraph):
        raise TypeError(
            "to_dot takes a node-link payload, not an AlignmentGraph — "
            "call graph.to_dot(...) or viz.to_dot(viz.to_node_link(graph))")
    if payload.get("schema_version") != SCHEMA_VERSION:
        payload = with_display_semantics(payload)
    annotations = payload.get("objective_alignment") or {}
    # Visualise the 18-relation matrix only: edges that carry a relation_id.
    # Internal scaffolding edges (``precedes``/``narrates``, relation_id="") stay in the JSON
    # dump but are dropped here — they add no matrix information and dominate the
    # picture. A node renders iff it is an objective or takes part in a matrix edge.
    matrix_edges = [e for e in payload.get("edges") or [] if e["layer"] != "scaffolding"]
    linked_ids = {e["source"] for e in matrix_edges} | {e["target"] for e in matrix_edges}

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
    lines.extend(_legend(payload.get("legend") or _legend_entries()))

    for node in payload.get("nodes") or []:
        is_objective = node["type"] == NodeType.OBJECTIVE and node["kind"] == "element"
        if not is_objective and node["id"] not in linked_ids:
            continue
        node_type = _LEGACY_NODE_TYPES.get(node["type"], node["type"])
        style = dict(_NODE_STYLE.get(node_type, {"shape": "ellipse", "style": "filled", "fillcolor": "#f3f4f6"}))
        if is_objective:
            ann = annotations.get(node["id"], {})
            style["fillcolor"] = _ALIGNED_FILL if ann.get("aligned") else _UNALIGNED_FILL
        attrs = ", ".join(f'{k}="{v}"' for k, v in style.items())
        lines.append(f'  "{_esc(node["id"])}" [label="{_node_label(node, annotations)}", {attrs}];')

    for edge in matrix_edges:
        if edge["invalid"]:
            color, style = _INVALID_EDGE, "dashed"
        else:
            color = _EDGE_COLOR.get(edge.get("established_by", ""), "#9ca3af")
            style = "dotted" if edge["tier"] == "secondary" else "solid"
        # Label is the relation key only; colour (+legend) carries the mechanism.
        label = str(edge["type"]) + (" ⚠" if edge["invalid"] else "")
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
    """Write ``<stem>.json`` (the full dump, ``AlignmentGraph.to_full_dict``).

    One file, not two: the DOT is a RENDERING of this payload and is
    reproducible from it byte-for-byte (``alignmentgraph-isd dot <stem>.json``),
    while the payload carries what the DOT cannot — every node's ``data``, the
    scaffolding edges, relation coverage, the violation index. ``title`` is
    kept for callers and for that renderer."""
    stem = Path(path_stem)
    stem.parent.mkdir(parents=True, exist_ok=True)
    json_path = stem.with_suffix(".json")
    payload = graph.to_full_dict(design_brief_id=design_brief_id)
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return [json_path]

"""The alignment construct — single source of truth for the 13-relation matrix.

Alignment is a *structural* property of the graph: an edge exists iff a
deterministic establisher confirms it (id-match, type-match, or provenance
recorded by a specialist that traversed source -> target while generating).
There is no continuous score, no threshold, and no LLM call anywhere in this
module. Everything here is called by specialists (to establish edges) and by
``pedagogical_verifier.py``'s alignment tier (to turn gaps into violations).

Edge direction convention
--------------------------
R3 (``measures``), R4 (``supports``), R5 (``evaluates``) are the pre-existing
edge types. To stay compatible with existing consumers (``audit.py``'s
``_uncovered_objectives``, which reads ``edge.target``), their direction stays
as the codebase already has it: the *artifact* is the source, the *objective*
is the target (e.g. an assessment item "measures" an objective -> edge
source=item, target=objective). Every other relation (R1,R2,R6-R13) is new, so
it follows the matrix table literally: first column is source, second is
target.

Every edge's ``type`` is the relation *key* ``"RX-NAME"`` (e.g. ``"R3-measures"``,
``"R6-realizes"``) — a generic, human-readable label built from the relation id
and its verb. The ``RX`` prefix keeps keys unique even where the verb repeats
(``realizes`` across R6/R7/R9/R12). The bare ``relation_id`` (``"R3"``) stays on
the edge for coverage indexing (see ``graph.py::add_edge``).
"""
from __future__ import annotations

from dataclasses import dataclass

from .graph import AlignmentGraph, NodeType


@dataclass(frozen=True)
class Relation:
    relation_id: str
    label: str
    edge_type: str  # the bare verb ("measures", "realizes", ...)
    mechanism: str  # "id" | "type" | "provenance"
    source_node_type: str
    target_node_types: tuple[str, ...]  # coverage is checked over these target element types

    @property
    def key(self) -> str:
        """The edge ``type`` this relation stamps: ``"R3-measures"``."""
        return f"{self.relation_id}-{self.edge_type}"


REGISTRY: dict[str, Relation] = {
    r.relation_id: r
    for r in (
        Relation("R1", "needs/task inform objective", "informs", "provenance",
                  "needs_context", (NodeType.OBJECTIVE,)),
        Relation("R2", "objective fits learner", "fits", "provenance",
                  "needs_context", (NodeType.OBJECTIVE,)),
        Relation("R3", "assessment measures objective", "measures", "id",
                  "assessment", (NodeType.OBJECTIVE,)),
        Relation("R4", "activity supports objective", "supports", "id",
                  "activity", (NodeType.OBJECTIVE,)),
        Relation("R5", "summative evidence evaluates objective", "evaluates", "id",
                  "summative", (NodeType.OBJECTIVE,)),
        Relation("R6", "assessment item realizes assessment plan", "realizes", "type",
                  "assessment_plan", ("assessment",)),
        Relation("R7", "activity realizes instructional strategy", "realizes", "provenance",
                  "instructional_strategies", ("activity",)),
        Relation("R8", "activity/material covers content module", "covers", "provenance",
                  "content", ("activity", "material")),
        Relation("R9", "material realizes media selection", "realizes", "type",
                  "media", ("material",)),
        Relation("R10", "content module covers task topic", "covers", "provenance",
                  "task", ("content",)),
        Relation("R11", "media constrained by context", "constrains", "provenance",
                  "needs_context", ("media",)),
        Relation("R12", "formative evaluation realizes formative plan", "realizes", "type",
                  "assessment_plan", (NodeType.EVALUATION,)),
        Relation("R13", "improvement plan addresses gap", "addresses", "provenance",
                  "gap", ("improvement",)),
    )
}


# ── id-match: generic single-field resolver, used by R3 and R5 ──────────────

def match_id(
    graph: AlignmentGraph,
    relation_id: str,
    *,
    target_node_type: str = NodeType.OBJECTIVE,
    field: str = "aligned_objective",
) -> list[dict]:
    """Resolve ``field`` on every element node of the relation's source type
    against an existing ``target_node_type`` element id; establish an edge on
    a match. Returns violation dicts (one per unresolved/missing reference)
    for the ones that don't resolve — the caller (verifier) decides whether to
    surface them (alignment tier only).
    """
    relation = REGISTRY[relation_id]
    violations: list[dict] = []
    for node in graph.element_nodes(relation.source_node_type):
        ref = str(node["data"].get(field, "") or "")
        target_id = f"{target_node_type}{graph.ELEMENT_SEP}{ref}" if ref else ""
        if ref and graph.get_node(target_id):
            graph.add_edge(
                relation.key, node["id"], target_id,
                evidence=ref, relation_id=relation_id, established_by="id",
                rationale=f"{node['id']} declares {field}={ref}, resolved to {target_id}.",
            )
        else:
            violations.append({
                "relation_id": relation_id, "node_id": node["id"],
                "message": f"{node['id']} has no resolvable {field} ({ref!r}).",
            })
    return violations


# ── R4 needs a list-aware id-match: an activity declares MULTIPLE objectives ─

def match_r4_supports(graph: AlignmentGraph, *, field: str = "aligned_objectives") -> list[dict]:
    """R4: an activity supports every objective listed in its ``aligned_objectives``
    array (unlike R3/R5's single-id field, so it can't reuse ``match_id``)."""
    violations: list[dict] = []
    for node in graph.element_nodes("activity"):
        refs = node["data"].get(field) or []
        if not isinstance(refs, list):
            refs = [refs]
        resolved = False
        for ref in refs:
            target_id = f"{NodeType.OBJECTIVE}{graph.ELEMENT_SEP}{ref}"
            if ref and graph.get_node(target_id):
                graph.add_edge(
                    REGISTRY["R4"].key, node["id"], target_id,
                    evidence=str(ref), relation_id="R4", established_by="id",
                    rationale=f"{node['id']} declares support for {ref}.",
                )
                resolved = True
        if not resolved:
            violations.append({
                "relation_id": "R4", "node_id": node["id"],
                "message": f"{node['id']} has no resolvable {field}.",
            })
    return violations


# ── type-match: bespoke per relation, the schemas don't share a clean vocab ──

_ASSESSMENT_PLAN_CATEGORIES = ("diagnostic", "formative", "summative")


def match_r6_realizes(graph: AlignmentGraph) -> list[dict]:
    """R6: an assessment item realizes the plan when its declared
    ``plan_category`` names a non-empty list in ``assessment_plan`` (the
    specialist tags each item with the plan category it fulfills when it
    generates it — see ``assessment_design.py``)."""
    plan_node = graph.get_node(graph.section_id("assessment_plan"))
    plan = plan_node["data"] if plan_node else {}
    violations: list[dict] = []
    for item in graph.element_nodes("assessment"):
        category = str(item["data"].get("plan_category", "") or "").strip().lower()
        if category in _ASSESSMENT_PLAN_CATEGORIES and plan.get(category):
            graph.add_edge(
                REGISTRY["R6"].key, graph.section_id("assessment_plan"), item["id"],
                evidence=category, relation_id="R6", established_by="type",
                rationale=f"{item['id']} realizes the '{category}' assessment_plan category.",
            )
        else:
            violations.append({
                "relation_id": "R6", "node_id": item["id"],
                "message": f"{item['id']} has no valid plan_category tying it to assessment_plan.",
            })
    return violations


_MEDIA_TYPE_ALIASES: dict[str, tuple[str, ...]] = {
    "video": ("video", "screencast", "recording"),
    "slides": ("slide", "presentation", "deck"),
    "simulation": ("simulation", "sandbox", "interactive"),
    "document": ("document", "pdf", "handout", "guide", "reading"),
    "audio": ("audio", "podcast"),
}


def _normalize_media_category(text: str) -> str:
    lowered = text.strip().lower()
    for canonical, aliases in _MEDIA_TYPE_ALIASES.items():
        if any(alias in lowered for alias in aliases):
            return canonical
    return lowered


def match_r9_realizes(graph: AlignmentGraph) -> list[dict]:
    """R9: a material realizes a media_selection entry when their type
    vocab normalizes to the same category (alias table above), matched by
    position order since neither side declares a shared id."""
    media_items = graph.element_nodes("media")
    material_items = graph.element_nodes("material")
    violations: list[dict] = []
    media_by_category: dict[str, list[dict]] = {}
    for media in media_items:
        cat = _normalize_media_category(str(media["data"].get("media_type", "")))
        media_by_category.setdefault(cat, []).append(media)
    for material in material_items:
        cat = _normalize_media_category(
            f"{material['data'].get('type', '')} {material['data'].get('format', '')}"
        )
        sources = media_by_category.get(cat, [])
        if sources:
            for media in sources:
                graph.add_edge(
                    REGISTRY["R9"].key, media["id"], material["id"],
                    evidence=cat, relation_id="R9", established_by="type",
                    rationale=f"{material['id']} realizes media category '{cat}'.",
                )
        else:
            violations.append({
                "relation_id": "R9", "node_id": material["id"],
                "message": f"{material['id']} does not match any media_selection category.",
            })
    return violations


def match_r12_realizes(graph: AlignmentGraph) -> list[dict]:
    """R12: the formative evaluation realizes the formative plan when both
    are declared non-empty. Both sides are free-text lists with no shared
    per-item vocabulary, so this is a coarse presence-level type-match rather
    than a per-item one (documented limitation)."""
    plan_node = graph.get_node(graph.section_id("assessment_plan"))
    plan_formative = (plan_node["data"].get("formative") if plan_node else None) or []
    eval_node = graph.get_node(graph.section_id(NodeType.EVALUATION))
    eval_formative = (eval_node["data"].get("formative") if eval_node else None) or {}
    if plan_formative and eval_formative:
        graph.add_edge(
            REGISTRY["R12"].key, graph.section_id("assessment_plan"), graph.section_id(NodeType.EVALUATION),
            evidence="formative", relation_id="R12", established_by="type",
            rationale="Formative evaluation section realizes the plan's formative intent.",
        )
        return []
    return [{
        "relation_id": "R12", "node_id": graph.section_id(NodeType.EVALUATION),
        "message": "Formative evaluation does not realize a declared formative plan.",
    }]


# ── provenance: recorded explicitly by the specialist that traversed ────────

def record_provenance(
    graph: AlignmentGraph,
    relation_id: str,
    source_ids: list[str],
    target_id: str,
    *,
    rationale: str = "",
) -> None:
    """Called by a specialist right after it traversed ``source_ids`` to
    build ``target_id`` — the edge exists *because* that traversal happened,
    not because of any post-hoc matching. No-op for ids that don't exist yet
    (a specialist may traverse a source that turned out empty)."""
    relation = REGISTRY[relation_id]
    if not graph.get_node(target_id):
        return
    for source_id in source_ids:
        if not graph.get_node(source_id):
            continue
        graph.add_edge(
            relation.key, source_id, target_id,
            relation_id=relation_id, established_by="provenance",
            rationale=rationale or f"{target_id} was generated by traversing {source_id}.",
        )


# ── Bloom/format validity — the one boolean rule beyond coverage ────────────
# Moved here from pedagogical_verifier.py so alignment.py stays the single
# definition of what "aligned" means structurally.

_BLOOM_LEVEL_INDEX = {"remember": 1, "understand": 2, "apply": 3, "analyze": 4, "evaluate": 5, "create": 6}
_ITEM_TYPE_CAPABILITY: dict[str, int] = {
    "true_false": 1,
    "matching": 1,
    "multiple_choice": 2,
    "quiz": 2,
    "short_answer": 4,
}
_RECALL_CAPABILITY_CEILING = 2
_DEFAULT_ITEM_CAPABILITY = 6


def item_type_capability(item_type: str) -> int:
    return _ITEM_TYPE_CAPABILITY.get(str(item_type or "").strip().lower(), _DEFAULT_ITEM_CAPABILITY)


def bloom_level_of(level_name: str) -> int | None:
    return _BLOOM_LEVEL_INDEX.get(str(level_name or "").strip().lower())


def format_valid_for_capability(capability: int, objective_level: int | None) -> bool:
    if objective_level is None or objective_level < 3:
        return True
    return capability > _RECALL_CAPABILITY_CEILING


def bloom_format_violations(graph: AlignmentGraph) -> list[dict]:
    """The single boolean constructive-alignment rule this refactor keeps
    beyond coverage: an objective is violated only when NONE of the items
    measuring it can elicit its Bloom level (grouped by objective, not
    per-edge — one performance item redeems several recognition-only ones,
    same as the objective ever demonstrating its target level in any format)."""
    by_objective: dict[str, tuple[dict, list[dict]]] = {}
    for edge in graph.get_edges(relation_id="R3"):
        item = graph.get_node(edge["source"])
        objective = graph.get_node(edge["target"])
        if not item or not objective:
            continue
        by_objective.setdefault(objective["id"], (objective, []))[1].append(item)

    violations: list[dict] = []
    for objective, items in by_objective.values():
        level = bloom_level_of(str(objective["data"].get("level", "")))
        capability = max((item_type_capability(i["data"].get("type", "")) for i in items), default=0)
        if format_valid_for_capability(capability, level):
            continue
        lo_id = str(objective["data"].get("id") or objective["id"].split(graph.ELEMENT_SEP, 1)[-1])
        item_ids = [str(i["data"].get("item_id") or i["id"].split(graph.ELEMENT_SEP, 1)[-1]) for i in items]
        violations.append({
            "relation_id": "R3", "node_id": objective["id"],
            "message": (
                f"Objective '{lo_id}' targets a higher-order level but is measured only by "
                f"recognition-level formats ({', '.join(item_ids)})."
            ),
            "metadata": {"lo_id": lo_id, "item_ids": item_ids},
        })
    return violations


# ── coverage aggregation (structural, no LLM) ────────────────────────────────

def relation_coverage(graph: AlignmentGraph, relation_id: str) -> tuple[float, list[str]]:
    """Fraction of the relation's required target elements that have >=1
    incoming edge of this relation_id, plus the list of uncovered node ids.
    Coverage is always checked from the *target* side."""
    relation = REGISTRY[relation_id]
    required: list[dict] = []
    for target_type in relation.target_node_types:
        required.extend(graph.element_nodes(target_type))
    if not required:
        return 1.0, []
    uncovered = [
        node["id"] for node in required
        if not graph.get_edges(relation_id=relation_id, target=node["id"])
    ]
    covered = len(required) - len(uncovered)
    return covered / len(required), uncovered


def all_relations_coverage(graph: AlignmentGraph) -> dict[str, dict]:
    """Per-relation coverage + uncovered ids for every R1..R13 — the data
    behind the aggregator's alignment_matrix and the audit summary."""
    return {
        relation_id: {
            "label": relation.label,
            "mechanism": relation.mechanism,
            "coverage": (result := relation_coverage(graph, relation_id))[0],
            "uncovered": result[1],
        }
        for relation_id, relation in REGISTRY.items()
    }

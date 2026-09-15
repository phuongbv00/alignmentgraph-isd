"""The alignment construct — single source of truth for the relation ontology.

Alignment is a *structural* property of the graph: an edge exists iff a
deterministic establisher confirms it (id-match, type-match, or provenance
recorded by a specialist that read source while generating target).
There is no continuous score, no threshold, and no LLM call anywhere in this
module. Everything here is called by Designers (to establish edges) and by
``checks.py`` (to turn coverage gaps into feedback signals).

Two tiers
---------
**Core** (``C1``-``C5``): the construct-validity backbone. Each relation traces
to a named construct in Constructive Alignment (Biggs), Backward Design /
Understanding by Design (Wiggins & McTighe), or outcome-based assessment
theory — see each ``Relation.theory`` string. These are the only relations
whose coverage is reported as a panel signal.

**Secondary** (``P1``-``P11``): provenance/traceability for supporting artifacts
(needs-analysis inputs, media/material realization, plan->execute links).
Kept in the graph dump for full auditability, but not claimed as
construct-validity evidence — dropping one doesn't argue anything went
pedagogically wrong, only that a bookkeeping trace is thinner.

Edge direction convention
--------------------------
Some core relations are the *reverse* of which artifact declares the
cross-reference field. E.g. C2 (``assessed_by``): an Assessment item declares
`aligned_objective`, but the edge is stored LO -> Assessment (not
Assessment -> LO) because the construct-validity claim reads LO-first ("this
LO is assessed by ..."). ``match_id_reverse``/``match_list_reverse`` exist
specifically for this: they resolve the same declared field as
``match_list`` but store the edge with source and target
swapped. Every other mechanism (`"provenance"`, `"type"`, and the
standard-direction `"id-list"` relations) stores source/target exactly as the
field declares them.

Every edge's ``type`` is the relation *key* ``"Cx-name"``/``"Px-name"`` (e.g.
``"C2-assessed_by"``, ``"P3-realizes"``) — a generic, human-readable label
built from the relation id and its verb. The prefix keeps keys unique where a
verb repeats (``realizes`` across P3/P4/P6; ``covers`` across P5/P7). The
bare ``relation_id`` (``"C2"``) stays on the edge for coverage indexing (see
``graph.py::add_edge``).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, get_args

from .graph import AlignmentGraph, NodeType

#: The closed set of relation ids. A type alias, not an enum: an id travels as
#: a plain string (it is stored on every edge, serialized into ``graph.json``,
#: read back off archived dumps, and read by the webapp's TypeScript), and it
#: shares a namespace with the non-relation check names in
#: ``repairs.OWNED_BY_FAMILY``, so a distinct runtime type would have to be
#: unwrapped at every one of those boundaries. This costs nothing at runtime
#: and lets a type checker or an editor catch a typo'd id in an annotated
#: signature. ``graph.py`` deliberately does NOT use it — that module resolves
#: no relations and importing this would be the ``graph <-> alignment`` cycle
#: ``add_edge``'s docstring exists to avoid.
RelationId = Literal[
    "C1", "C2", "C3", "C4", "C5",
    "P1", "P2", "P3", "P4", "P5", "P6", "P7", "P8", "P9", "P10", "P11",
]


@dataclass(frozen=True)
class Relation:
    relation_id: RelationId
    label: str
    edge_type: str  # the bare verb ("assessed_by", "realizes", ...)
    mechanism: str  # "id-reverse" | "id-list" | "id-list-reverse" | "type" | "provenance"
    source_node_types: tuple[str, ...]  # coverage is checked over these when coverage_side="source"
    target_node_types: tuple[str, ...]  # coverage is checked over these target element types
    coverage_side: Literal["source", "target"]
    tier: Literal["core", "secondary"]
    theory: str = ""  # citation anchor for core relations; empty for secondary

    @property
    def key(self) -> str:
        """The edge ``type`` this relation stamps: ``"C2-assessed_by"``."""
        return f"{self.relation_id}-{self.edge_type}"

    @property
    def single_source_type(self) -> str:
        """The ONE type an id-mechanism establisher resolves a bare ref
        against (``"ILO-01"`` -> ``"objective:ILO-01"``): with two candidate
        types that resolution is ambiguous, so those mechanisms require a
        single source and this raises rather than picking one. Provenance
        relations, whose source ids arrive already resolved, may declare
        several (P1: a learning outcome is informed by gaps AND topics)."""
        source_type, = self.source_node_types
        return source_type


REGISTRY: dict[str, Relation] = {
    r.relation_id: r
    for r in (
        # ── Core (C1-C5): construct-validity backbone ───────────────────────
        Relation("C1", "course goal decomposes to learning outcome", "decomposes_to", "provenance",
                 (NodeType.COURSE_GOAL,), (NodeType.OBJECTIVE,), "target", "core",
                 theory="Outcome-based design / Backward Design (Wiggins & McTighe)"),
        Relation("C2", "learning outcome assessed by assessment task", "assessed_by", "id-reverse",
                 (NodeType.OBJECTIVE,), (NodeType.ASSESSMENT,), "source", "core",
                 theory="Constructive Alignment (Biggs) + Understanding by Design Stage 2"),
        Relation("C3", "learning outcome practiced by activity", "practiced_by", "id-list-reverse",
                 (NodeType.OBJECTIVE,), (NodeType.ACTIVITY,), "source", "core",
                 theory="Constructive Alignment (Biggs)"),
        Relation("C4", "activity prepares for assessment task", "prepares_for", "id-list",
                 (NodeType.ACTIVITY,), (NodeType.ASSESSMENT,), "target", "core",
                 theory="Backward Design + Constructive Alignment"),
        Relation("C5", "content module supports activity", "supports", "provenance",
                 (NodeType.CONTENT,), (NodeType.ACTIVITY,), "target", "core",
                 theory="Backward Design (Wiggins & McTighe)"),
        # ── Secondary (P1-P11): provenance/traceability, not construct-validity ──
        Relation("P1", "gap/topic informs learning outcome", "informs", "provenance",
                 (NodeType.GAP, NodeType.TOPIC), (NodeType.OBJECTIVE,), "target", "secondary"),
        Relation("P2", "learner profile fits learning outcome", "fits", "provenance",
                 (NodeType.LEARNER_PROFILE,), (NodeType.OBJECTIVE,), "target", "secondary"),
        Relation("P3", "assessment plan realized by assessment task", "realizes", "type",
                 (NodeType.ASSESSMENT_PLAN,), (NodeType.ASSESSMENT,), "target", "secondary"),
        Relation("P4", "activity plan realized by activity", "realizes", "provenance",
                 (NodeType.ACTIVITY_PLAN,), (NodeType.ACTIVITY,), "target", "secondary"),
        Relation("P5", "content module covers material", "covers", "provenance",
                 (NodeType.CONTENT,), (NodeType.MATERIAL,), "target", "secondary"),
        Relation("P6", "media selection realized by material", "realizes", "type",
                 (NodeType.MEDIA_SELECTION,), (NodeType.MATERIAL,), "target", "secondary"),
        Relation("P7", "topic covered by content module", "covers", "provenance",
                 (NodeType.TOPIC,), (NodeType.CONTENT,), "target", "secondary"),
        Relation("P8", "constraint constrains media selection", "constrains", "provenance",
                 (NodeType.CONSTRAINT,), (NodeType.MEDIA_SELECTION,), "target", "secondary"),
        Relation("P9", "gap addressed by improvement", "addresses", "provenance",
                 (NodeType.GAP,), (NodeType.IMPROVEMENT,), "target", "secondary"),
        Relation("P10", "session guide delivers activity", "delivers", "provenance",
                 (NodeType.SESSION_GUIDE,), (NodeType.ACTIVITY,), "target", "secondary"),
        Relation("P11", "session guide provisions material", "provisions", "provenance",
                 (NodeType.SESSION_GUIDE,), (NodeType.MATERIAL,), "target", "secondary"),
    )
}

assert set(get_args(RelationId)) == set(REGISTRY), (
    "RelationId and REGISTRY must name the same relations")

# Only a provenance relation may declare several sources: every other
# mechanism resolves a bare ref against ONE type (see ``single_source_type``).
assert all(len(r.source_node_types) == 1
           for r in REGISTRY.values() if r.mechanism != "provenance")

ALIGNMENT_LEGS: tuple[RelationId, ...] = ("C2", "C3", "C4")
assert all(relation_id in REGISTRY for relation_id in ALIGNMENT_LEGS)


def leg_verb(relation_id: RelationId) -> str:
    """The field name a leg is reported under: the relation's own verb.

    ``assessed_by`` / ``practiced_by`` / ``prepares_for`` — so an objective's
    alignment reads in the same words as the edges it is made of."""
    return REGISTRY[relation_id].edge_type


#: "<node_type>:" prefixes a model sometimes copies into id-reference fields.
_NAMESPACE_PREFIXES: tuple[str, ...] = tuple(f"{t}:" for t in NodeType)


def bare_ref(ref: object) -> str:
    """Normalize a model-written id reference to its bare form.

    Models occasionally echo a namespaced node id ("objective:ILO-01") into a
    field that every matcher compares as a bare id ("ILO-01") — measured on a
    2B single-graph run, where ``lo_coverage_targets`` keyed by namespaced ids
    made plan_coverage report every promised pair unrealised. Every reader of
    a model-written reference normalizes through here; graph node ids
    themselves are never passed through this."""
    text = str(ref or "").strip()
    for prefix in _NAMESPACE_PREFIXES:
        if text.startswith(prefix):
            return text[len(prefix):]
    return text


# ── id-match, REVERSED direction: source=resolved node, target=referencing ──

def match_id_reverse(
    graph: AlignmentGraph,
    relation_id: RelationId,
    *,
    field: str,
) -> list[dict]:
    """Resolve a declared id field, but store the edge source=resolved node,
    target=referencing node — for relations where the theoretical direction
    (e.g. "LO assessed_by Assessment") is the reverse of which artifact
    actually declares the cross-reference field (the Assessment item declares
    ``aligned_objective``, not the LO). ``relation.single_source_type`` is the
    RESOLVED type (edge source); ``relation.target_node_types[0]`` is the
    REFERENCING type (edge target, the one with ``field`` in its data)."""
    relation = REGISTRY[relation_id]
    resolved_type = relation.single_source_type
    referencing_type = relation.target_node_types[0]
    violations: list[dict] = []
    for node in graph.element_nodes(referencing_type):
        ref = bare_ref(node["data"].get(field, ""))
        resolved_id = f"{resolved_type}{graph.ELEMENT_SEP}{ref}" if ref else ""
        if ref and graph.get_node(resolved_id):
            graph.add_edge(
                relation.key, resolved_id, node["id"],
                evidence=ref, relation_id=relation_id, established_by="id",
                rationale=f"{node['id']} declares {field}={ref}, resolved to {resolved_id}.",
            )
        else:
            violations.append({
                "relation_id": relation_id, "node_id": node["id"],
                "message": f"{node['id']} has no resolvable {field} ({ref!r}).",
            })
    return violations


# ── id-list match, standard direction: source declares a list of targets ────

def match_list(
    graph: AlignmentGraph,
    relation_id: RelationId,
    *,
    field: str,
) -> list[dict]:
    """C4-style: the source element declares a LIST of target ids in
    ``field`` (e.g. an Activity's ``prepares_for_assessment``). Establishes
    one edge per resolved reference; a violation only if NONE resolve."""
    relation = REGISTRY[relation_id]
    target_node_type = relation.target_node_types[0]
    violations: list[dict] = []
    for node in graph.element_nodes(relation.single_source_type):
        refs = node["data"].get(field) or []
        if not isinstance(refs, list):
            refs = [refs]
        resolved = False
        for ref in refs:
            ref = bare_ref(ref)
            target_id = f"{target_node_type}{graph.ELEMENT_SEP}{ref}"
            if ref and graph.get_node(target_id):
                graph.add_edge(
                    relation.key, node["id"], target_id,
                    evidence=str(ref), relation_id=relation_id, established_by="id",
                    rationale=f"{node['id']} declares {field} including {ref}.",
                )
                resolved = True
        if not resolved:
            violations.append({
                "relation_id": relation_id, "node_id": node["id"],
                "message": f"{node['id']} has no resolvable {field}.",
            })
    return violations


# ── id-list match, REVERSED direction ────────────────────────────────────────

def match_list_reverse(
    graph: AlignmentGraph,
    relation_id: RelationId,
    *,
    field: str,
) -> list[dict]:
    """C3-style: the REFERENCING element (``relation.target_node_types[0]``,
    e.g. an Activity) declares a LIST of resolved-type ids in ``field`` (e.g.
    ``aligned_objectives``), but the edge is stored source=resolved node
    (``relation.single_source_type``, e.g. the LO), target=referencing node —
    mirrors ``match_id_reverse`` for the list case."""
    relation = REGISTRY[relation_id]
    resolved_type = relation.single_source_type
    referencing_type = relation.target_node_types[0]
    violations: list[dict] = []
    for node in graph.element_nodes(referencing_type):
        refs = node["data"].get(field) or []
        if not isinstance(refs, list):
            refs = [refs]
        resolved = False
        for ref in refs:
            ref = bare_ref(ref)
            resolved_id = f"{resolved_type}{graph.ELEMENT_SEP}{ref}"
            if ref and graph.get_node(resolved_id):
                graph.add_edge(
                    relation.key, resolved_id, node["id"],
                    evidence=str(ref), relation_id=relation_id, established_by="id",
                    rationale=f"{node['id']} declares {field} including {ref}.",
                )
                resolved = True
        if not resolved:
            violations.append({
                "relation_id": relation_id, "node_id": node["id"],
                "message": f"{node['id']} has no resolvable {field}.",
            })
    return violations


# ── type-match: bespoke per relation, the schemas don't share a clean vocab ──

_ASSESSMENT_PLAN_CATEGORIES = ("diagnostic", "formative", "summative")


def _promised_categories(plan: dict) -> set[str]:
    """The plan categories the assessment plan actually COMMITS to.

    Read off ``lo_coverage_targets`` — the plan's REQUIRED field, the one
    ``RULES_ASSESSMENT_PLAN`` asks for and the one ``checks.plan_coverage``
    and ``dev_plans`` already read — through the single shared reader, so
    every consumer of this field normalizes it the same way.

    MEASURED (run 7ef3ed16, multi+graph, 13 items): P3 used to require a
    non-empty ``plan["diagnostic"|"formative"|"summative"]``. Those three keys
    are OPTIONAL in ``artifact_schemas`` and are named by no rule, so the model
    wrote the required ``lo_coverage_targets`` ({"ILO-01": ["diagnostic",
    "formative"], ...}) and left them absent. All 13 items carried a valid
    ``plan_category``, and P3 still scored 0.0 — the relation could not fire on
    any run. Two parts of one system were reading two different keys for one
    fact.

    The three bucket keys stay as a fallback for an archived plan that has
    them, and for nothing else.

    This does NOT make P3 unfailable (the objection that retired C6/C7): an
    item with no ``plan_category``, or one naming a category the plan never
    promised, still has no edge.
    """
    from .. import dev_plans

    promised = {category
                for _, category in dev_plans.plan_category_pairs(
                    plan.get("lo_coverage_targets"))}
    promised |= {c for c in _ASSESSMENT_PLAN_CATEGORIES if plan.get(c)}
    return promised


def match_p3_realizes(graph: AlignmentGraph) -> list[dict]:
    """P3: an assessment item realizes the plan when its declared
    ``plan_category`` is one the plan promised (see
    :func:`_promised_categories`)."""
    plan_node = graph.get_node(graph.section_id(NodeType.ASSESSMENT_PLAN))
    plan = plan_node["data"] if plan_node else {}
    promised = _promised_categories(plan)
    violations: list[dict] = []
    for item in graph.element_nodes(NodeType.ASSESSMENT):
        category = str(item["data"].get("plan_category", "") or "").strip().lower()
        if category and category in promised:
            graph.add_edge(
                REGISTRY["P3"].key, graph.section_id(NodeType.ASSESSMENT_PLAN), item["id"],
                evidence=category, relation_id="P3", established_by="type",
                rationale=f"{item['id']} realizes the '{category}' assessment_plan category.",
            )
        else:
            violations.append({
                "relation_id": "P3", "node_id": item["id"],
                "message": f"{item['id']} has no valid plan_category tying it to the assessment plan.",
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


def match_p6_realizes(graph: AlignmentGraph) -> list[dict]:
    """P6: a material realizes a media selection entry when their type vocab
    normalizes to the same category (alias table above), matched by category
    since neither side declares a shared id."""
    media_items = graph.element_nodes(NodeType.MEDIA_SELECTION)
    material_items = graph.element_nodes(NodeType.MATERIAL)
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
                    REGISTRY["P6"].key, media["id"], material["id"],
                    evidence=cat, relation_id="P6", established_by="type",
                    rationale=f"{material['id']} realizes media category '{cat}'.",
                )
        else:
            violations.append({
                "relation_id": "P6", "node_id": material["id"],
                "message": f"{material['id']} does not match any media selection category.",
            })
    return violations


# ── provenance: recorded explicitly by the specialist that traversed ────────

def record_provenance(
    graph: AlignmentGraph,
    relation_id: RelationId,
    source_ids: list[str],
    target_id: str,
    *,
    rationale: str = "",
) -> None:
    """Called by a Designer right after it read ``source_ids`` to build
    ``target_id`` — the edge exists *because* that read happened, not because
    of any post-hoc matching. No-op for ids that don't exist yet (a Designer
    may read a source that turned out empty, or call this before both ends of
    the edge are written)."""
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


def establish_delivery(graph: AlignmentGraph, session_node_ids: list[str]) -> None:
    """P10/P11: record which activities each SESSION GUIDE schedules and which
    materials it hands out — a shared establisher, called by the fan-out commit
    on either decomposition arm (``fanout._establish``).

    Without this the implementation plan was the one artifact in the graph
    with no edge at all, while its text referenced graph ids in every scenario
    measured (836 activity and 656 material references across 30 runs). The
    graph therefore could not answer "was this activity ever scheduled" — a
    question the auditability claim implies it can.

    The SOURCE is the session guide, not the plan section (2026-09-07). The
    edge then says WHICH session delivers an activity rather than only that
    some part of the plan does, and it is established from the node the
    Developer actually wrote — the plan section no longer carries the guides.
    Coverage is unchanged: both relations are checked on the target side, so
    an activity nobody scheduled is still exactly an activity with no incoming
    P10.

    Ids come from the dedicated ``activity_ids``/``material_ids`` fields
    rather than from the prose beside them: the model writes ids inline in
    ``activities`` ("... on mobile LMS (MAT-01)"), and recovering edges by
    regex over prose would make the audit trail depend on phrasing.
    """
    sep = graph.ELEMENT_SEP
    for node_id in session_node_ids:
        data = (graph.get_node(node_id) or {}).get("data") or {}
        for field, node_type, relation_id in (
                ("activity_ids", NodeType.ACTIVITY, "P10"),
                ("material_ids", NodeType.MATERIAL, "P11"),
        ):
            referenced = [bare_ref(r) for r in (data.get(field) or []) if r]
            for ref in dict.fromkeys(referenced):
                record_provenance(graph, relation_id, [node_id], f"{node_type}{sep}{ref}")


# ── Bloom/cognitive-process cross-checks — attribute-based, not an edge ─────
# Revised Bloom's Taxonomy (Anderson & Krathwohl) is not a relation in
# REGISTRY: it is a set of attributes (``level`` on Objective,
# ``required_cognitive_process`` on Assessment, ``learner_cognitive_process``
# on Activity) cross-checked along the C2/C3 edges those relations already
# established. Kept here (not in checks.py) so alignment.py stays the single
# definition of what "aligned" means structurally, matching the existing
# convention for the coverage/mechanism functions above.

_BLOOM_LEVEL_INDEX = {"remember": 1, "understand": 2, "apply": 3, "analyze": 4, "evaluate": 5, "create": 6}
#: The reverse. A level printed as a bare integer ("elicits more than level 2")
#: is a number the reader has to look up before it means anything, and these
#: messages go straight into an agent's repair turn.
BLOOM_LEVEL_NAME = {index: name for name, index in _BLOOM_LEVEL_INDEX.items()}


def bloom_level_name(index: int | None) -> str:
    return BLOOM_LEVEL_NAME.get(index or 0, "")


def a_level(name: str) -> str:
    """``an apply-level``, ``a create-level``. Four of the six Bloom names begin
    with a vowel, so a hardcoded "a" is wrong most of the time — and these
    strings go verbatim into an agent's repair turn."""
    return f"{'an' if name[:1].lower() in 'aeiou' else 'a'} {name}" if name else ""


def formats_reaching(level: int) -> str:
    """Item formats whose own ceiling can carry ``level``, named.

    Read off ``_ITEM_TYPE_CAPABILITY`` so the advice cannot drift from the
    table the check actually applies."""
    ceilinged = {fmt for fmt, cap in _ITEM_TYPE_CAPABILITY.items() if cap < level}
    return (", ".join(sorted(ceilinged)) if ceilinged else "")


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
    """Whether an item of this elicitation ``capability`` can honestly measure
    an objective at ``objective_level``.

    Constructive alignment asks the assessment task to require the SAME
    cognitive process the objective states, so the test is
    ``capability >= objective_level``. It used to be a binary
    recognition/non-recognition gate (``capability > 2`` for any Apply+
    objective), which passed an Apply-level item measuring a Create-level
    objective — a two-level shortfall it could not see, because both sides
    are merely "not recognition".

    Measured consequence of the coarse version: 26% of the items in a run sat
    BELOW the objective they were aligned to, the highest of the four ablation
    arms, while the check reported nothing. That gap is exactly what the RQ2
    cognitive-demand family scores, and it is where this system lost to
    dick-carey-agent (congruence 0.744 vs 0.889).

    Both this rule and that metric derive independently from Anderson &
    Krathwohl, so this is enforcing the theory rather than fitting the
    instrument — but it was calibrated on train_30, and test_90 is untouched.
    """
    if objective_level is None:
        return True
    return capability >= objective_level


def _item_capability(item_data: dict) -> int:
    """An item's elicitation capability: its own declared
    ``required_cognitive_process`` (an explicit claim) if present, else a
    fallback derived from its format (a multiple_choice item can't actually
    elicit Create-level thinking no matter what it claims) — the declared
    attribute takes precedence since it is the artifact's own stated intent;
    the format-based table is the floor when nothing is declared."""
    declared = bloom_level_of(str(item_data.get("required_cognitive_process", "")))
    if declared is not None:
        return declared
    return item_type_capability(item_data.get("type", ""))


def bloom_assessment_violations(graph: AlignmentGraph) -> list[dict]:
    """An objective is violated only when NONE of the assessment items
    measuring it (via C2) can elicit its Bloom level (grouped by objective —
    one performance item redeems several recognition-only ones). Reads C2
    edges with the objective as ``edge.source`` (the id-reverse direction)."""
    by_objective: dict[str, tuple[dict, list[dict]]] = {}
    for edge in graph.get_edges(relation_id="C2"):
        objective = graph.get_node(edge["source"])
        item = graph.get_node(edge["target"])
        if not item or not objective:
            continue
        by_objective.setdefault(objective["id"], (objective, []))[1].append(item)

    violations: list[dict] = []
    for objective, items in by_objective.values():
        level = bloom_level_of(str(objective["data"].get("level", "")))
        capability = max((_item_capability(i["data"]) for i in items), default=0)
        if format_valid_for_capability(capability, level):
            continue
        lo_id = str(objective["data"].get("id") or objective["id"].split(graph.ELEMENT_SEP, 1)[-1])
        item_ids = [str(i["data"].get("item_id") or i["id"].split(graph.ELEMENT_SEP, 1)[-1]) for i in items]
        violations.append({
            "relation_id": "C2", "node_id": objective["id"],
            "message": (
                f"Objective '{lo_id}' states {a_level(bloom_level_name(level)) or 'a ?'}-level "
                f"performance, but the best of the {len(item_ids)} item(s) measuring "
                f"it ({', '.join(item_ids)}) only reaches "
                f"{bloom_level_name(capability) or 'no stated level'} — an objective "
                f"measured below its own level is not measured."
            ),
            "repair_hint": (
                f"On at least one of {', '.join(item_ids)}, set "
                f"required_cognitive_process to '{bloom_level_name(level)}' AND give it "
                f"a format that can carry it (short_answer or a performance task; "
                f"{formats_reaching(level)} cap out below it) — or add a new "
                f"{bloom_level_name(level)}-level item aligned to {lo_id}."
            ),
            "metadata": {"lo_id": lo_id, "item_ids": item_ids,
                         "objective_level": level, "best_capability": capability,
                         "field": "required_cognitive_process"},
        })
    return violations


def bloom_activity_violations(graph: AlignmentGraph) -> list[dict]:
    """An objective is violated when NONE of the activities practicing it
    (via C3) declare a ``learner_cognitive_process`` at or above the
    objective's own ``level`` level. Reads C3 edges with the
    objective as ``edge.source``."""
    by_objective: dict[str, tuple[dict, list[dict]]] = {}
    for edge in graph.get_edges(relation_id="C3"):
        objective = graph.get_node(edge["source"])
        activity = graph.get_node(edge["target"])
        if not activity or not objective:
            continue
        by_objective.setdefault(objective["id"], (objective, []))[1].append(activity)

    violations: list[dict] = []
    for objective, activities in by_objective.values():
        level = bloom_level_of(str(objective["data"].get("level", "")))
        if level is None:
            continue
        best = max(
            (bloom_level_of(str(a["data"].get("learner_cognitive_process", ""))) or 0 for a in activities),
            default=0,
        )
        if best >= level:
            continue
        lo_id = str(objective["data"].get("id") or objective["id"].split(graph.ELEMENT_SEP, 1)[-1])
        act_ids = [str(a["data"].get("id") or a["id"].split(graph.ELEMENT_SEP, 1)[-1]) for a in activities]
        violations.append({
            "relation_id": "C3", "node_id": objective["id"],
            "message": (
                f"Objective '{lo_id}' targets {bloom_level_name(level)}, but of the "
                f"{len(act_ids)} activity/activities practising it "
                f"({', '.join(act_ids)}), "
                + (f"the highest learner_cognitive_process is "
                   f"{bloom_level_name(best)}" if best else
                   "none declares a learner_cognitive_process at all")
                + " — learners never rehearse at the level they are assessed on."
            ),
            "repair_hint": (
                f"Set learner_cognitive_process to '{bloom_level_name(level)}' on at "
                f"least one of {', '.join(act_ids)} and make the activity actually "
                f"require it ({a_level(bloom_level_name(level))}-level task, not a "
                f"walkthrough of one) — or add such an activity aligned to {lo_id}."
            ),
            "metadata": {"lo_id": lo_id, "activity_ids": act_ids,
                         "objective_level": level, "best_level": best,
                         "field": "learner_cognitive_process"},
        })
    return violations


# ── coverage aggregation (structural, no LLM) ────────────────────────────────

def relation_coverage(graph: AlignmentGraph, relation_id: RelationId) -> tuple[float, list[str]]:
    """Fraction of the relation's required elements (on ``coverage_side``)
    that have >=1 edge of this relation_id on that side, plus the list of
    uncovered node ids. Core relations (C2/C3) check the *source* side
    (the id-reverse direction moves the construct-validity subject there);
    every other relation checks the *target* side."""
    relation = REGISTRY[relation_id]
    required: list[dict] = []
    check_types = (relation.source_node_types if relation.coverage_side == "source"
                   else relation.target_node_types)
    for check_type in check_types:
        required.extend(graph.element_nodes(check_type))
    if not required:
        return 1.0, []
    if relation.coverage_side == "source":
        uncovered = [
            node["id"] for node in required
            if not graph.get_edges(relation_id=relation_id, source=node["id"])
        ]
    else:
        uncovered = [
            node["id"] for node in required
            if not graph.get_edges(relation_id=relation_id, target=node["id"])
        ]
    covered = len(required) - len(uncovered)
    return covered / len(required), uncovered


def all_relations_coverage(graph: AlignmentGraph) -> dict[RelationId, dict]:
    """Per-relation coverage + uncovered ids for every C1..C5/P1..P11 — the
    data behind the aggregator's alignment_matrix and the audit summary."""
    return {
        relation_id: {
            "label": relation.label,
            "mechanism": relation.mechanism,
            "tier": relation.tier,
            "coverage": (result := relation_coverage(graph, relation_id))[0],
            "uncovered": result[1],
        }
        for relation_id, relation in REGISTRY.items()
    }

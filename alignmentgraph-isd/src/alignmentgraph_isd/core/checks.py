"""Self-validation checks — extracted from the retired ``PedagogicalVerifierAgent``.

Each function here is a free function a Designer calls inline, in its own
self-validation step, instead of a separate agent/QC-node reading the whole
graph after the fact. This is a mechanical extraction (same regexes, same
thresholds, same violation shape) adapted to the new node layout: LO/
Activity/Assessment/Rubric are now individual element nodes (one per
artifact), not entries in one section node's embedded list — so every check
here reads ``graph.element_nodes(...)`` directly, not
``graph.section_nodes(...)[0]["data"]["learning_objectives"]`` as the prior
design did.

A violation only becomes a cross-agent feedback signal (``target_designer``
set) when its root cause plausibly sits in an earlier Designer than the one
that found it; most violations are still repaired locally by whichever
Designer owns the check (self-contained, same as before).
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from .alignment_graph import alignment
from .alignment_graph import NodeType
from .brief import DesignBrief

# Bloom's taxonomy verbs by level — used to verify measurability of objectives
_BLOOM_VERBS: dict[str, list[str]] = {
    "Remember":  ["define","list","recall","recognize","identify","name","state","describe","label","match"],
    "Understand":["explain","summarize","paraphrase","classify","compare","interpret","translate","discuss","distinguish","infer"],
    "Apply":     ["apply","use","demonstrate","solve","execute","implement","calculate","construct","produce","operate"],
    "Analyze":   ["analyze","differentiate","examine","compare","contrast","organize","attribute","deconstruct","outline","relate"],
    "Evaluate":  ["evaluate","judge","justify","assess","critique","argue","defend","recommend","prioritize","rate"],
    "Create":    ["design","create","formulate","develop","compose","plan","generate","synthesize","construct","propose"],
}
_ALL_BLOOM_VERBS = {v for verbs in _BLOOM_VERBS.values() for v in verbs}

# Vague rubric language that signals a non-observable scoring criterion.
_VAGUE_RUBRIC_TERMS = ("good", "clear", "appropriate", "nice", "well done", "as expected", "satisfactory")
# Observable anchors that redeem an otherwise vague criterion.
_OBSERVABLE_TERMS = (
    "rubric", "score", "scores", "criteria", "checklist", "%", "percent", "points",
    "accuracy", "complete", "correct", "demonstrat", "measur", "level", "0-", "1-",
)
_PLACEHOLDER_MARKERS = ("<", "tbd", "todo", "placeholder", "lorem ipsum", "n/a")

_BLOOM_LEVEL_INDEX = {"remember": 1, "understand": 2, "apply": 3, "analyze": 4, "evaluate": 5, "create": 6}
_VERB_LEVELS: dict[str, set[int]] = {}
for _level, _verbs in _BLOOM_VERBS.items():
    for _v in _verbs:
        _VERB_LEVELS.setdefault(_v, set()).add(_BLOOM_LEVEL_INDEX[_level.lower()])

# Non-observable ("fuzzy") objective verbs: these describe an internal state that
# cannot be directly observed or scored, so an objective built on one needs an
# explicit criterion to be measurable. A proper observable Bloom verb (analyze,
# design, apply, ...) is already measurable enough and is NOT flagged.
_VAGUE_VERBS = frozenset({
    "understand", "know", "learn", "comprehend", "grasp", "appreciate",
    "aware", "familiar", "realize", "internalize", "value", "believe",
})

# An objective statement is considered measurable when it states a degree
# (criterion of acceptable performance) or a condition (Mager's ABCD model).
_DEGREE_PATTERN = re.compile(
    r"\d|%|percent|at least|at most|or more|or fewer|within|correctly|accurately"
    r"|without (?:error|reference|assistance)"
    r"|against (?:the )?(?:rubric|checklist|criteria)"
    r"|\b(?:one|two|three|four|five|six|seven|eight|nine|ten)\b",
    re.IGNORECASE,
)
_CONDITION_PATTERN = re.compile(
    r"\bgiven\b|\busing\b|\bprovided\b|\bwith (?:an? )?examples?\b|\bwhen\b"
    r"|\bin (?:a|an|the) (?:realistic|provided|given|new|team)?\s?(?:scenario|context|case|codebase|project|setting)\b",
    re.IGNORECASE,
)

# Activity-format markers used to judge whether higher-order objectives get
# active practice rather than passive exposure.
_PASSIVE_ACTIVITY_MARKERS = (
    "lecture", "presentation", "reading", "video", "overview", "introduction", "briefing", "webinar",
)
_ACTIVE_ACTIVITY_MARKERS = (
    "lab", "exercise", "practice", "hands-on", "workshop", "project", "simulation",
    "role-play", "roleplay", "case study", "build", "implement", "solve", "cod",
    "review", "critique", "discussion", "pair", "debate", "apply",
)


@dataclass
class Violation:
    node_id: str
    edge_type: str
    message: str
    # violation_type: bloom | measurability | activity_engagement | rubric_consistency |
    #   feasibility | actionability | evaluation_quality | orphan_content |
    #   evidence_alignment | C1..C7 | P1..P9 | bloom_mismatch_assessment | bloom_mismatch_activity
    violation_type: str = "coverage"
    severity: str = "error"                   # error | warning
    repair_hint: str = ""
    metadata: dict = field(default_factory=dict)
    # Which Designer this should route to if the owning Designer can't repair
    # it locally (empty = self-contained, repaired by whichever agent found it).
    target_designer: str = ""


def _bare_id(graph, node_id: str) -> str:
    return node_id.split(graph.ELEMENT_SEP, 1)[-1] if graph.is_element(node_id) else node_id


def _has_concrete_items(*candidates) -> bool:
    for candidate in candidates:
        if isinstance(candidate, list):
            for item in candidate:
                text = item if isinstance(item, str) else str(item)
                lowered = text.strip().lower()
                if lowered and not any(marker in lowered for marker in _PLACEHOLDER_MARKERS):
                    return True
    return False


def _duration_hours(design_brief: DesignBrief) -> float:
    text = f"{design_brief.context.duration} {design_brief.duration}".lower()
    hours = 0.0
    for value, unit in re.findall(r"(\d+(?:\.\d+)?)\s*(hour|hr|h|day|d|week|w)", text):
        amount = float(value)
        if unit.startswith("h"):
            hours += amount
        elif unit.startswith("d"):
            hours += amount * 6  # ~6 instructional hours per day
        elif unit.startswith("w"):
            hours += amount * 30
    return hours


# ══════════════════════ Outcome Designer's own checks ═══════════════════════
#
# The within-artifact checks (bloom_verbs, measurability, item_completeness,
# rubric_consistency, evaluation_quality, actionability) each carry a
# ``*_items``/``*_data`` core
# that inspects plain ``(node_id, data)`` pairs — no graph access. Both arms
# run the SAME core: the graph arm feeds it element/section nodes, the prose
# arm feeds it the matching blackboard document (see the prose branch of
# ``workflow._collect_violations``). Cross-artifact checks stay graph-only by
# design — they are part of the alignment machinery the prose arm ablates.

def bloom_verbs(graph) -> list[Violation]:
    """Every LO (an individual element node) declares a valid Bloom verb
    consistent with its declared ``level``, and that ``level`` is one of
    Bloom's six."""
    return bloom_verbs_items(
        [(lo["id"], lo["data"]) for lo in graph.element_nodes(NodeType.OBJECTIVE)]
    )


def bloom_verbs_items(items: list[tuple[str, dict]]) -> list[Violation]:
    violations: list[Violation] = []
    for node_id, data in items:
        lo_id = data.get("id", node_id.rsplit(":", 1)[-1])
        verb = str(data.get("bloom_verb", "")).lower().strip(".,;")
        statement = str(data.get("statement", ""))
        if not verb:
            violations.append(Violation(
                node_id=node_id, edge_type="", violation_type="bloom", severity="warning",
                message=f"LO '{lo_id}' missing bloom_verb field.",
                repair_hint="Add a measurable Bloom's taxonomy verb.",
                metadata={"lo_id": lo_id, "statement": statement},
            ))
            continue
        if verb not in _ALL_BLOOM_VERBS:
            stmt_lower = statement.lower()
            if not any(bv in stmt_lower for bv in _ALL_BLOOM_VERBS):
                violations.append(Violation(
                    node_id=node_id, edge_type="", violation_type="bloom", severity="warning",
                    message=f"LO '{lo_id}' uses non-standard verb '{verb}' not in Bloom's taxonomy.",
                    repair_hint=f"Use a standard Bloom's verb such as: {', '.join(list(_ALL_BLOOM_VERBS)[:8])}...",
                    metadata={"lo_id": lo_id, "verb": verb},
                ))
            continue
        declared = str(data.get("level", "")).strip()
        level_idx = _BLOOM_LEVEL_INDEX.get(declared.lower())
        if not level_idx:
            # An out-of-taxonomy level ("design", "manage") used to short-circuit
            # the verb-vs-level comparison below and pass silently, so the field
            # the whole Bloom apparatus reads was never validated against its own
            # enum. Flag it; the repair sets the level from the verb.
            violations.append(Violation(
                node_id=node_id, edge_type="", violation_type="bloom", severity="warning",
                message=(
                    f"LO '{lo_id}' declares level '{declared or '(missing)'}', which is not one of "
                    f"Bloom's six levels."
                ),
                repair_hint=(
                    "Set level to one of: remember, understand, apply, analyze, evaluate, create."
                ),
                metadata={"lo_id": lo_id, "verb": verb, "level": declared},
            ))
            continue
        verb_levels = _VERB_LEVELS.get(verb, set())
        if verb_levels and level_idx not in verb_levels:
            violations.append(Violation(
                node_id=node_id, edge_type="", violation_type="bloom", severity="warning",
                message=(
                    f"LO '{lo_id}' declares level '{data.get('level')}' but "
                    f"uses verb '{verb}', which belongs to a different Bloom level."
                ),
                repair_hint="Align the verb with the declared level (or fix the level).",
                metadata={"lo_id": lo_id, "verb": verb, "level": data.get("level")},
            ))
    return violations


def measurability(graph) -> list[Violation]:
    """Audit-only (never auto-repaired by this check itself — a vague verb is
    fixed by ``bloom_verbs``' repair): only a non-observable verb with no
    stated degree/condition is unmeasurable."""
    return measurability_items(
        [(lo["id"], lo["data"]) for lo in graph.element_nodes(NodeType.OBJECTIVE)]
    )


def measurability_items(items: list[tuple[str, dict]]) -> list[Violation]:
    violations: list[Violation] = []
    for node_id, data in items:
        statement = str(data.get("statement", ""))
        if not statement.strip():
            continue
        lo_id = data.get("id", node_id.rsplit(":", 1)[-1])
        verb = str(data.get("bloom_verb", "")).lower().strip(".,;")
        stmt_lower = statement.lower()
        is_vague = verb in _VAGUE_VERBS or any(
            re.search(rf"\b{re.escape(v)}\b", stmt_lower) for v in _VAGUE_VERBS
        )
        if not is_vague:
            continue
        if _DEGREE_PATTERN.search(statement) or _CONDITION_PATTERN.search(statement):
            continue
        violations.append(Violation(
            node_id=node_id, edge_type="", violation_type="measurability", severity="warning",
            message=f"LO '{lo_id}' states no success criterion or condition; achievement cannot be judged objectively.",
            repair_hint=(
                "Add an observable degree and/or condition to the statement, "
                "e.g. 'given a starter codebase, ... with at least 80% of unit tests passing'."
            ),
            metadata={"lo_id": lo_id, "statement": statement},
        ))
    return violations


# ══════════════════════ Assessment Designer's own checks ═══════════════════
# (rubric_consistency moved further below, under Rubric Designer's checks —
# Rubric nodes don't exist yet when Assessment Designer runs, since Rubric
# Designer is much later in the DAG.)

def rubric_consistency(graph) -> list[Violation]:
    """Every Rubric criterion states an observable scoring description (moved
    from the old per-item ``scoring_criteria`` check to the dedicated Rubric
    node type, which now owns this concern). Called by Rubric Designer's own
    self-validation, not Assessment Designer's."""
    return rubric_consistency_items(
        [(rc["id"], rc["data"]) for rc in graph.element_nodes(NodeType.RUBRIC)]
    )


def rubric_consistency_items(items: list[tuple[str, dict]]) -> list[Violation]:
    violations: list[Violation] = []
    for node_id, data in items:
        rc_id = data.get("id", node_id.rsplit(":", 1)[-1])
        criteria = str(data.get("description") or data.get("scoring_criteria") or "").strip()
        lowered = criteria.lower()
        if not criteria or any(marker in lowered for marker in _PLACEHOLDER_MARKERS):
            violations.append(Violation(
                node_id=node_id, edge_type="", violation_type="rubric_consistency", severity="warning",
                message=f"Rubric criterion '{rc_id}' has no scoring description.",
                repair_hint="State how this criterion is scored (levels, points, or descriptors).",
                metadata={"rc_id": rc_id, "description": criteria},
            ))
        elif len(criteria) < 40 or (
            any(term in lowered for term in _VAGUE_RUBRIC_TERMS)
            and not any(term in lowered for term in _OBSERVABLE_TERMS)
        ):
            violations.append(Violation(
                node_id=node_id, edge_type="", violation_type="rubric_consistency", severity="warning",
                message=f"Rubric criterion '{rc_id}' lacks an observable scoring description.",
                repair_hint="Replace vague language with observable, scorable descriptors.",
                metadata={"rc_id": rc_id, "description": criteria},
            ))
    return violations


def plan_coverage(graph) -> list[Violation]:
    """Every (objective, plan_category) pair the assessment plan declares in
    ``lo_coverage_targets`` must be realised by at least one assessment item.

    P3 only checks that an item's ``plan_category`` names a non-empty list on
    the plan node, so nothing verified the plan's OWN coverage promise. A
    measured run showed the cost: the plan asked for 5 summative and 1
    diagnostic item, the items hop produced 1 summative and 16 diagnostic,
    and nothing objected. The summative pool being near-empty then collapsed
    the whole summative half of ADDIE Evaluation, because effectiveness and
    adoption are computed from it.

    This is the plan->execute check the 2-hop design implies but did not
    have."""
    plan_node = graph.get_node(graph.section_id(NodeType.ASSESSMENT_PLAN))
    if plan_node is None:
        return []
    targets = plan_node["data"].get("lo_coverage_targets")
    if not isinstance(targets, dict) or not targets:
        return []

    realised: set[tuple[str, str]] = set()
    for item in graph.element_nodes(NodeType.ASSESSMENT):
        data = item["data"]
        lo = alignment.bare_ref(data.get("aligned_objective", ""))
        category = str(data.get("plan_category", "") or "").lower()
        if lo and category:
            realised.add((lo, category))

    violations: list[Violation] = []
    for raw_lo_id, categories in targets.items():
        # bare_ref: a model that copied the namespaced node id from context
        # ("objective:ILO-01") must not make every promised pair read as
        # unrealised (measured on a 2B single-graph run: 14/14 false gaps).
        lo_id = alignment.bare_ref(raw_lo_id)
        if not isinstance(categories, list):
            continue
        for category in categories:
            key = (str(lo_id), str(category).lower())
            if key in realised:
                continue
            violations.append(Violation(
                node_id=f"{NodeType.OBJECTIVE}{graph.ELEMENT_SEP}{lo_id}",
                edge_type="", violation_type="plan_coverage", severity="error",
                message=(f"The assessment plan promises a {category} item for {lo_id}, "
                         f"but no assessment item realises that pair."),
                repair_hint=f"Add a {category} assessment item aligned to {lo_id}.",
                metadata={"lo_id": str(lo_id), "plan_category": str(category).lower()},
            ))
    return violations


_CHOICE_ITEM_TYPES = frozenset({"multiple_choice", "true_false", "matching"})


def item_completeness(graph) -> list[Violation]:
    """A selectable-response assessment item (multiple_choice/true_false/
    matching) is not an administrable instrument without its response set:
    options (except true_false, whose options are implicit) and the answer
    key. Measured 2026-08-28: every MCQ in a 2B run shipped question-only."""
    return item_completeness_items(
        [(a["id"], a["data"]) for a in graph.element_nodes(NodeType.ASSESSMENT)]
    )


def item_completeness_items(items: list[tuple[str, dict]]) -> list[Violation]:
    violations: list[Violation] = []
    for node_id, data in items:
        item_type = str(data.get("type", "")).lower().strip()
        if item_type not in _CHOICE_ITEM_TYPES:
            continue
        item_id = data.get("item_id", node_id.rsplit(":", 1)[-1])
        options = data.get("options")
        missing: list[str] = []
        if item_type != "true_false" and not (isinstance(options, list) and len(options) >= 2):
            missing.append("options")
        if not str(data.get("correct_answer", "") or "").strip():
            missing.append("correct_answer")
        if missing:
            violations.append(Violation(
                node_id=node_id, edge_type="", violation_type="item_completeness",
                severity="warning",
                message=(
                    f"Item '{item_id}' is {item_type} but has no {' or '.join(missing)} — "
                    "it cannot be administered as written."
                ),
                repair_hint=(
                    "Add the answer options (plausible distractors included) and the correct "
                    "answer, or reformat the item as short_answer."
                ),
                metadata={"item_id": item_id, "item_type": item_type, "missing": missing},
            ))
    return violations


def evaluation_quality(graph) -> list[Violation]:
    """Kept in *meaning* from the old R12 relation ("formative evaluation
    realizes the formative plan"), but now a plain internal check rather than
    a graph edge — there is no ``evaluation`` node to point a relation at
    (see the aggregation-matrix note in the architecture plan). Checks
    directly that ``assessment_plan_0.formative_methods`` is non-empty
    whenever the plan declares a non-trivial formative intent."""
    plan_node = graph.get_node(graph.section_id(NodeType.ASSESSMENT_PLAN))
    if plan_node is None:
        return []
    return evaluation_quality_data(plan_node["id"], plan_node["data"])


def evaluation_quality_data(node_id: str, data: dict) -> list[Violation]:
    formative_intent = data.get("formative")
    if not formative_intent:
        return []
    violations: list[Violation] = []
    if not _has_concrete_items(data.get("formative_methods")):
        violations.append(Violation(
            node_id=node_id, edge_type="", violation_type="evaluation_quality", severity="warning",
            message="Assessment plan declares formative intent but names no concrete data-collection method.",
            repair_hint=(
                "List concrete formative methods (observation checklist, exit tickets, "
                "rubric checkpoints) under assessment_plan.formative_methods."
            ),
            metadata={"section": "formative_methods"},
        ))
    # The formative half of ADDIE Evaluation is scored on pilot_data_plan:
    # which areas learners will struggle with, why, and what first revision
    # follows (the aggregator surfaces exactly these fields as
    # evaluation.formative). RULES_ASSESSMENT_PLAN demands two specific
    # anticipated difficulties, but nothing enforced it — a small model that
    # drops or thins the plan ships an evaluation phase the rubric scores 0-2
    # (measured on both arms).
    pilot = data.get("pilot_data_plan")
    pilot = pilot if isinstance(pilot, dict) else {}
    difficulties = [
        entry for entry in (pilot.get("anticipated_difficulties") or [])
        if isinstance(entry, dict)
        and str(entry.get("area", "")).strip()
        and str(entry.get("first_revision", "")).strip()
    ]
    if len(difficulties) < 2 or not _has_concrete_items(pilot.get("collection_points")):
        violations.append(Violation(
            node_id=node_id, edge_type="", violation_type="evaluation_quality", severity="warning",
            message=(
                "Pilot data plan is missing or thin: it needs concrete collection points and "
                "at least two anticipated difficulties, each naming an area and a first revision."
            ),
            repair_hint=(
                "Fill assessment_plan.pilot_data_plan with collection_points and >=2 "
                "anticipated_difficulties ({area, rationale, detected_by, first_revision}), "
                "each naming a real objective or content module."
            ),
            metadata={"section": "pilot_data_plan"},
        ))
    return violations


# ══════════════════════ Activity Designer's own checks ══════════════════════

def activity_engagement(graph) -> list[Violation]:
    """A higher-order (Apply+) objective practiced only through passive
    formats (lecture, reading, video) gives learners no chance to perform the
    target skill. Uses the already-established C3 edges (LO practiced_by
    Activity) to find which activities practice which LO, rather than
    re-reading the raw declared field."""
    higher = {
        lo["id"]: lo["data"]
        for lo in graph.element_nodes(NodeType.OBJECTIVE)
        if (_BLOOM_LEVEL_INDEX.get(str(lo["data"].get("level", "")).lower().strip()) or 0) >= 3
    }
    if not higher:
        return []
    violations: list[Violation] = []
    for lo_node_id, lo_data in higher.items():
        lo_id = lo_data.get("id", _bare_id(graph, lo_node_id))
        linked = [
            graph.get_node(edge["target"])
            for edge in graph.get_edges(relation_id="C3", source=lo_node_id)
        ]
        linked = [a for a in linked if a is not None]
        if not linked:
            continue  # missing linkage entirely is C3 coverage's concern, not this check's
        texts = [
            f"{a['data'].get('activity_name', '')} {a['data'].get('description', '')}".lower()
            for a in linked
        ]
        if any(marker in text for text in texts for marker in _ACTIVE_ACTIVITY_MARKERS):
            continue
        if not any(marker in text for text in texts for marker in _PASSIVE_ACTIVITY_MARKERS):
            continue  # unclassifiable formats: do not guess
        names = [str(a["data"].get("activity_name", "?")) for a in linked]
        violations.append(Violation(
            node_id=lo_node_id, edge_type="", violation_type="activity_engagement", severity="warning",
            message=f"Higher-order objective '{lo_id}' is practiced only through passive formats ({', '.join(names)}).",
            repair_hint="Add a hands-on activity (lab, exercise, project, simulation) aligned to this objective.",
            metadata={"lo_id": lo_id, "passive_activities": names},
        ))
    return violations


# ══════════════════════ Content Designer's own checks ═══════════════════════

def orphan_content(graph) -> list[Violation]:
    """Every Content module and every Material must trace to >=1 Activity
    (module-side C5 coverage; P5 coverage for materials) — "no orphan
    content untraceable to instructional purpose", per the Content
    Designer's own brief.

    C5's own ``coverage_side`` is ``"target"`` (the core construct-validity
    claim it backs is "every Activity has supporting content", checked
    elsewhere via ``relation_coverage()``/the residual audit) — the OPPOSITE
    side from what an orphan-module check needs, so this can't reuse
    ``alignment.relation_coverage(graph, "C5")`` (that returns uncovered
    Activities, not modules, and returns nothing at all when no Activity
    exists yet). This checks the module side directly instead."""
    violations: list[Violation] = []
    for module in graph.element_nodes(NodeType.CONTENT):
        if graph.get_edges(relation_id="C5", source=module["id"]):
            continue
        violations.append(Violation(
            node_id=module["id"], edge_type="", violation_type="orphan_content", severity="warning",
            message=f"{module['id']} supports no Activity (orphan content module).",
            repair_hint="Link this module to an existing Activity, or remove it.",
            metadata={"node_id": module["id"]},
        ))
    _, uncovered_materials = alignment.relation_coverage(graph, "P5")
    for node_id in uncovered_materials:
        violations.append(Violation(
            node_id=node_id, edge_type="", violation_type="orphan_content", severity="warning",
            message=f"{node_id} has no source content module (orphan material).",
            repair_hint="Set linked_module to an existing content module.",
            metadata={"node_id": node_id},
        ))
    return violations


# ══════════════════════ Rubric Designer's own checks ════════════════════════

def orphan_rubric(graph) -> list[Violation]:
    """A rubric criterion with neither a C6 nor a C7 edge points at nothing —
    and is invisible to both coverage checks, because C6's coverage side is
    the assessment (does every item have a criterion) and C7's is the
    objective (is every objective measured). A criterion that names no item
    and no objective sits on the unchecked side of both. Measured: a repaired
    criterion shipped with no ``aligned_assessment`` and no
    ``aligned_objective`` and sailed through every net into the final graph
    dump as an isolated element node — the exact class of island the
    element-reachability invariant forbids.

    Symmetric with ``orphan_content``: same "no artifact untraceable to
    instructional purpose" rule, applied to the scoring side."""
    violations: list[Violation] = []
    for rc in graph.element_nodes(NodeType.RUBRIC):
        if graph.get_edges(relation_id="C6", target=rc["id"]):
            continue
        if graph.get_edges(relation_id="C7", source=rc["id"]):
            continue
        rc_id = rc["data"].get("id", _bare_id(graph, rc["id"]))
        violations.append(Violation(
            node_id=rc["id"], edge_type="", violation_type="orphan_rubric", severity="error",
            message=f"Rubric criterion '{rc_id}' evaluates no assessment item and measures no objective.",
            repair_hint="Attach it to an assessment item (preferring one that has no criterion yet).",
            metadata={"node_id": rc["id"], "rc_id": rc_id},
        ))
    return violations


def evidence_alignment(graph) -> list[Violation]:
    """A Rubric criterion's declared evidence type must be producible by the
    Assessment item it evaluates (C6 target) — generalizes the old Bloom/
    format-validity capability lookup (``item_type_capability``) to rubric
    criteria instead of raw assessment format."""
    violations: list[Violation] = []
    for rc in graph.element_nodes(NodeType.RUBRIC):
        evidence_type = str(rc["data"].get("evidence_type", "") or "")
        if not evidence_type:
            continue
        required = alignment.item_type_capability(evidence_type)
        evaluated_edges = graph.get_edges(relation_id="C6", target=rc["id"])
        if not evaluated_edges:
            continue  # C6 coverage's concern, not this check's
        capability = max(
            (alignment.item_type_capability((graph.get_node(e["source"]) or {"data": {}})["data"].get("type", ""))
             for e in evaluated_edges),
            default=0,
        )
        if capability >= required:
            continue
        rc_id = rc["data"].get("id", _bare_id(graph, rc["id"]))
        violations.append(Violation(
            node_id=rc["id"], edge_type="", violation_type="evidence_alignment", severity="warning",
            message=f"Rubric criterion '{rc_id}' expects '{evidence_type}' evidence but its linked assessment item(s) can't produce it.",
            repair_hint="Either loosen the criterion's evidence type or change the linked item's format.",
            metadata={"rc_id": rc_id, "evidence_type": evidence_type},
        ))
    return violations


# ══════════════════════ ImplementationPlannerAgent's own checks ═════════════

def feasibility(graph, design_brief: DesignBrief | None) -> list[Violation]:
    if design_brief is None:
        return []
    total_hours = _duration_hours(design_brief)
    if total_hours <= 0:
        return []
    load_units = len(graph.element_nodes(NodeType.CONTENT)) + len(graph.element_nodes(NodeType.ACTIVITY))
    # Heuristic: each module/activity needs ~1.5h. Flag only clear overload.
    if load_units and load_units * 1.5 > total_hours * 2:
        return [Violation(
            node_id=graph.section_id(NodeType.IMPLEMENTATION_PLAN), edge_type="constrains",
            violation_type="feasibility", severity="warning",
            message=f"Design packs {load_units} modules/activities into ~{total_hours}h; delivery is likely infeasible.",
            repair_hint="Reduce scope per session or extend the schedule in the implementation plan.",
            metadata={"load_units": load_units, "total_hours": total_hours},
        )]
    return []


def actionability(graph) -> list[Violation]:
    violations: list[Violation] = []
    for node in graph.section_nodes(NodeType.IMPLEMENTATION_PLAN):
        violations += actionability_data(node["id"], node["data"])
    return violations


def actionability_data(node_id: str, data: dict) -> list[Violation]:
    violations: list[Violation] = []
    orientation = data.get("instructor_orientation", {})
    if isinstance(orientation, dict) and not _has_concrete_items(
        orientation.get("competency_checklist"), orientation.get("materials")
    ):
        violations.append(Violation(
            node_id=node_id, edge_type="constrains", violation_type="actionability", severity="warning",
            message="Instructor orientation lacks concrete facilitator actions or materials.",
            repair_hint="Add a competency checklist and facilitator materials with concrete steps.",
            metadata={"section": "instructor_orientation"},
        ))
    system_check = data.get("system_check", {})
    if isinstance(system_check, dict) and not _has_concrete_items(system_check.get("checklist")):
        violations.append(Violation(
            node_id=node_id, edge_type="constrains", violation_type="actionability", severity="warning",
            message="System check has no actionable checklist.",
            repair_hint="Add concrete pre-session verification steps.",
            metadata={"section": "system_check"},
        ))
    return violations


# ══════════════════════ shared: relation coverage + Bloom cross-checks ══════

# Only these relations have a re-runnable establisher (id/id-list/type
# mechanisms); provenance-mechanism relations (C1, C5, C6, P1, P2, P4, P5,
# P7, P8, P9) can't be re-established generically — they need the specific
# source ids the producing Designer traversed, which only that Designer
# knows at generation time. This mirrors the old verifier's behavior, which
# likewise only re-ran R3/R4/R5/R6/R9/R12 (never the provenance relations).
_RERUNNABLE_RELATIONS: tuple[str, ...] = ("C2", "C3", "C4", "C7", "P3", "P6")


def relation_coverage(graph) -> list[Violation]:
    """Re-run the re-runnable establishers (idempotent — safe to call
    repeatedly, and catches a reference that stopped resolving after a
    repair elsewhere) to surface dangling/mismatched references, then check
    coverage of all 18 relations (core + secondary) for missing links."""
    violations: list[Violation] = []

    establisher_gaps: list[dict] = []
    establisher_gaps += alignment.match_id_reverse(graph, "C2", field="aligned_objective")
    establisher_gaps += alignment.match_list_reverse(graph, "C3", field="aligned_objectives")
    establisher_gaps += alignment.match_list(graph, "C4", field="prepares_for_assessment")
    establisher_gaps += alignment.match_id(graph, "C7", field="aligned_objective")
    establisher_gaps += alignment.match_p3_realizes(graph)
    establisher_gaps += alignment.match_p6_realizes(graph)
    for gap in establisher_gaps:
        node_id = gap["node_id"]
        bare_id = _bare_id(graph, node_id)
        violations.append(Violation(
            node_id=node_id, edge_type="", violation_type=gap["relation_id"],
            severity="error", message=gap["message"],
            metadata={"node_id": node_id, "item_id": bare_id},
        ))

    for relation_id, relation in alignment.REGISTRY.items():
        _, uncovered = alignment.relation_coverage(graph, relation_id)
        for node_id in uncovered:
            metadata = {"node_id": node_id}
            if node_id.startswith(f"{NodeType.OBJECTIVE}{graph.ELEMENT_SEP}"):
                metadata["lo_id"] = _bare_id(graph, node_id)
            violations.append(Violation(
                node_id=node_id, edge_type="", violation_type=relation_id,
                severity="error" if relation.tier == "core" else "warning",
                message=f"{node_id} has no {relation_id} ({relation.label}) coverage.",
                repair_hint=f"Establish a {relation.label} link.",
                metadata=metadata,
            ))
    return violations


def bloom_mismatches(graph) -> list[Violation]:
    """Both cross-checks: LO vs Assessment (C2) and LO vs Activity (C3).
    Assessment Designer calls the C2 half on its own items; Activity
    Designer calls the C3 half on its own activities — both self-contained,
    same as ``bloom_mismatch`` was in the old single-relation (R3-only)
    verifier."""
    violations: list[Violation] = []
    for bv in alignment.bloom_assessment_violations(graph):
        violations.append(Violation(
            node_id=bv["node_id"], edge_type="", violation_type="bloom_mismatch_assessment",
            severity="error", message=bv["message"], metadata=bv.get("metadata", {}),
        ))
    for bv in alignment.bloom_activity_violations(graph):
        violations.append(Violation(
            node_id=bv["node_id"], edge_type="", violation_type="bloom_mismatch_activity",
            severity="error", message=bv["message"], metadata=bv.get("metadata", {}),
        ))
    return violations

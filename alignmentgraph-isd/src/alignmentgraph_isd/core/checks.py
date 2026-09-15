"""Self-validation checks: free functions the harness runs over the design
state after a family has produced, instead of a separate QC agent reading the
whole graph after the fact. Objectives, activities and assessment items are
individual element nodes (one per artifact), so every check reads
``graph.element_nodes(...)``; rubric criteria are a field of their item.

Most violations are repaired locally, by whichever family owns the check, in
the self-validation round that follows its own generation stage. A violation a
LATER stage surfaces but an EARLIER family owns cannot be repaired that way --
the owning stage has already finished. Those become cross-agent feedback: the
reconciliation pass that runs once after the last stage stamps
``target_designer`` from ``repairs.OWNER_BY_VIOLATION`` and hands each
violation to the family that owns it. See ``core/runner.py::_reconcile``.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from . import dev_plans
from .alignment_graph import NodeType, alignment
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


def _term_matcher(terms, *, whole_word: bool = False) -> "re.Pattern":
    """Match a vocabulary at WORD BOUNDARIES instead of anywhere in the text.

    Plain ``in`` made three of these lists lie. MEASURED (run 2b9e911a):
    ``"clear"`` matched "clearly articulates" and flagged three specific rubric
    descriptions as non-observable. The same class sits in two more:
    ``"rate"`` matches "generate" and ``"use"`` matches "because", so a
    statement carrying no taxonomy verb redeems itself; ``"lab"`` matches
    "collaborate" and "syllabus", so a lecture-only design escapes
    ``activity_engagement``.

    The DEFAULT is a LEADING boundary only, not a whole word, because several
    entries are deliberate STEMS ("demonstrat", "measur", "cod") and several
    lists want inflections ("generate" must still match "generates"). ``\\bcod``
    kills "encoded" while keeping "coding"; ``\\bcod\\b`` would kill both.
    ``whole_word=True`` is for the one list where the inflection IS the false
    positive: "clear" must not match "clearly".

    A term that does not begin (or end) with an alphanumeric gets no boundary on
    that side — ``_OBSERVABLE_TERMS`` carries "%", "0-", "1-".
    """
    def bounded(term: str) -> str:
        pattern = re.escape(term)
        if term[:1].isalnum():
            pattern = r"\b" + pattern
        if whole_word and term[-1:].isalnum():
            pattern += r"\b"
        return pattern

    # Sorted so a set-derived vocabulary compiles to the same pattern in every
    # process, the way `_ALL_BLOOM_VERBS` has to be sorted before it is sliced.
    return re.compile("|".join(bounded(t) for t in sorted(terms)), re.IGNORECASE)


#: Accuse only on the word itself; redeem on the word or an inflection of it.
_VAGUE_RUBRIC_RE = _term_matcher(_VAGUE_RUBRIC_TERMS, whole_word=True)
_OBSERVABLE_RE = _term_matcher(_OBSERVABLE_TERMS)

#: One Bloom index, defined with the relations that compare on it.
_BLOOM_LEVEL_INDEX = alignment._BLOOM_LEVEL_INDEX
_BLOOM_LEVEL_NAME = alignment.BLOOM_LEVEL_NAME
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
_ACTIVE_ACTIVITY_RE = _term_matcher(_ACTIVE_ACTIVITY_MARKERS)
_PASSIVE_ACTIVITY_RE = _term_matcher(_PASSIVE_ACTIVITY_MARKERS)
_BLOOM_VERB_RE = _term_matcher(_ALL_BLOOM_VERBS)
_VAGUE_VERB_RE = _term_matcher(_VAGUE_VERBS, whole_word=True)


@dataclass
class Violation:
    node_id: str
    edge_type: str
    message: str
    #: The check that raised it — a relation id or a check name; the owning
    #: family is ``repairs.OWNED_BY_FAMILY``.
    violation_type: str
    severity: str = "error"                   # error | warning
    repair_hint: str = ""
    metadata: dict = field(default_factory=dict)
    # The family that OWNS this violation type, stamped by the reconciliation
    # pass from ``repairs.OWNER_BY_VIOLATION``. Empty until then, and empty
    # forever for a type no family owns (``measurability`` is audit-only).
    target_designer: str = ""

    @property
    def key(self) -> str:
        """What makes two occurrences across check rounds the SAME finding.

        A violation is CONTENT-ADDRESSED, unlike a published context. A context
        is a continuous object that can carry an id minted where it starts
        (``memory.new_agent_run_id``); a violation is re-derived from state by
        a pure function on every round, so there is no object to carry
        anything. But the lesson from that id transfers in the form that
        applies here:

            **The key is built from the SUBJECT, never from the EVIDENCE.**
            Subject = what has to change for this to go away.
            Evidence = what the check saw while deciding.

        ``bloom_mismatch_assessment.metadata["item_ids"]`` is evidence: it
        grows as Developers commit more items while the problem stands, so a
        key including it would report the old finding closed and a new one
        opened on every commit. Same for ``missing`` on an incomplete item and
        ``passive_activities`` on an unengaging objective.
        """
        parts = [self.violation_type, self.node_id]
        parts += [str(self.metadata.get(f, ""))
                  for f in IDENTITY_FIELDS.get(self.violation_type, ())]
        return "|".join(parts)


def serialize_violations(violations: list, owner: str) -> list[dict]:
    """The wire form of a violation: every field plus its identity.

    ``node_id``/``type``/``msg``/``severity``/``owner`` keep their names —
    ``audit.py`` and every archived run read them."""
    return [
        {"key": v.key, "node_id": v.node_id, "type": v.violation_type,
         "msg": v.message, "severity": v.severity, "owner": owner,
         "edge_type": v.edge_type, "repair_hint": v.repair_hint,
         "metadata": dict(v.metadata), "target_designer": v.target_designer}
        for v in violations
    ]


#: Metadata fields that DISCRIMINATE two violations of the same type on the
#: same node — the subject of the finding, never the evidence behind it. A type
#: absent here is identified by ``(violation_type, node_id)`` alone.
#:
#: Three of these five are not bookkeeping but latent bugs: ``evaluation_quality``
#: and ``actionability`` each emit TWO violations on ONE node_id (the plan
#: section, the implementation plan), told apart only by ``section``; and
#: ``evidence_alignment``'s node_id is the ITEM while an item can carry several
#: criteria. Without the discriminator those pairs are one finding to anything
#: that groups by identity.
IDENTITY_FIELDS: dict[str, tuple[str, ...]] = {
    "plan_coverage": ("plan_category",),      # one objective, several unrealised categories
    "evaluation_quality": ("section",),       # formative_methods vs pilot_data_plan
    "actionability": ("section",),            # instructor_orientation vs system_check
    "evidence_alignment": ("rc_id",),         # several criteria on one item
    "bloom": ("rule",),                       # four sub-rules, one node
}


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
# arm feeds it the matching blackboard document (see
# ``outputs._collect_violations_prose``). Cross-artifact checks stay graph-only by
# design — they are part of the alignment machinery the prose arm ablates.

def _verbs_for(level: str, count: int = 6) -> str:
    """Example verbs OF A GIVEN LEVEL, in the rulebook's own order.

    Deterministic on purpose: the hint used to slice ``_ALL_BLOOM_VERBS``,
    which is a SET, so the model was shown eight arbitrary verbs spanning
    arbitrary levels in an order stable only within one process — a prompt that
    differed between two runs of the same design."""
    return ", ".join(_BLOOM_VERBS.get(str(level).strip().capitalize(), [])[:count])


def _level_of_verb(verb: str) -> str:
    """The Bloom level a verb belongs to, by name. Lowest when it spans two."""
    levels = _VERB_LEVELS.get(verb, set())
    if not levels:
        return ""
    return _BLOOM_LEVEL_NAME[min(levels)]


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
        declared_raw = str(data.get("level", "")).strip()
        if not verb:
            violations.append(Violation(
                node_id=node_id, edge_type="", violation_type="bloom", severity="warning",
                message=(
                    f"LO '{lo_id}' has no bloom_verb — nothing states which cognitive "
                    f"level it targets, so no assessment item or activity can be "
                    f"checked against it."
                ),
                repair_hint=(
                    "Set bloom_verb to the Bloom's verb the statement already performs"
                    + (f" ({_verbs_for(declared_raw)})" if _verbs_for(declared_raw) else "")
                    + ", and set level to that verb's own Bloom level."
                ),
                metadata={"lo_id": lo_id, "statement": statement,
                          "level": declared_raw, "rule": "missing_verb"},
            ))
            continue
        if verb not in _ALL_BLOOM_VERBS:
            stmt_lower = statement.lower()
            if not _BLOOM_VERB_RE.search(stmt_lower):
                violations.append(Violation(
                    node_id=node_id, edge_type="", violation_type="bloom", severity="warning",
                    message=(
                        f"LO '{lo_id}' uses bloom_verb '{verb}', which is in none of "
                        f"Bloom's six levels, and its statement contains no taxonomy "
                        f"verb either — the objective's cognitive level cannot be read "
                        f"from either field."
                    ),
                    # The suggestions are the verbs of the level this LO ALREADY
                    # declares, in the rulebook's own order (see `_verbs_for`).
                    repair_hint=(
                        f"Replace bloom_verb with "
                        f"{alignment.a_level(declared_raw) or 'a Bloom'}-level verb "
                        f"({_verbs_for(declared_raw) or _verbs_for('apply')}) and "
                        f"restate the objective around it."
                    ),
                    metadata={"lo_id": lo_id, "verb": verb, "level": declared_raw,
                              "rule": "non_taxonomy_verb"},
                ))
            continue
        declared = declared_raw
        level_idx = _BLOOM_LEVEL_INDEX.get(declared.lower())
        if not level_idx:
            # An out-of-taxonomy level ("design", "manage") used to short-circuit
            # the verb-vs-level comparison below and pass silently, so the field
            # the whole Bloom apparatus reads was never validated against its own
            # enum. Flag it; the repair sets the level from the verb.
            violations.append(Violation(
                node_id=node_id, edge_type="", violation_type="bloom", severity="warning",
                message=(
                    f"LO '{lo_id}' declares level '{declared or '(missing)'}', which is "
                    f"not one of Bloom's six (remember, understand, apply, analyze, "
                    f"evaluate, create) — every Bloom cross-check reads this field and "
                    f"skips an objective it cannot place, so this objective is going "
                    f"unchecked."
                ),
                repair_hint=(
                    f"Set level to '{_level_of_verb(verb)}', the level its own "
                    f"bloom_verb '{verb}' belongs to."
                    if _level_of_verb(verb) else
                    "Set level to one of: remember, understand, apply, analyze, "
                    "evaluate, create."
                ),
                metadata={"lo_id": lo_id, "verb": verb, "level": declared,
                          "rule": "invalid_level"},
            ))
            continue
        verb_levels = _VERB_LEVELS.get(verb, set())
        if verb_levels and level_idx not in verb_levels:
            violations.append(Violation(
                node_id=node_id, edge_type="", violation_type="bloom", severity="warning",
                message=(
                    f"LO '{lo_id}' declares level '{declared}' but its bloom_verb "
                    f"'{verb}' is a {_level_of_verb(verb)}-level verb — the two fields "
                    f"name different cognitive processes, and every downstream check "
                    f"reads level."
                ),
                repair_hint=(
                    f"Either set level to '{_level_of_verb(verb)}', or replace "
                    f"bloom_verb with {alignment.a_level(declared)}-level verb "
                    f"({_verbs_for(declared)})."
                ),
                metadata={"lo_id": lo_id, "verb": verb, "level": declared,
                          "verb_level": _level_of_verb(verb),
                          "rule": "verb_level_mismatch"},
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
        is_vague = verb in _VAGUE_VERBS or bool(_VAGUE_VERB_RE.search(stmt_lower))
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
# `rubric_consistency` is defined below rather than here because it reads the
# criteria off the items: since 2026-09-02 a rubric criterion is a FIELD of its
# assessment item, not a node, so there is no separate Rubric stage to own it.

def _criteria_of(graph) -> list[tuple[str, dict]]:
    """Every rubric criterion in the design, read off the assessment items.

    Since 2026-09-02 a criterion is a FIELD of the item it marks, not a node of
    its own — it is written by the same call, in the same breath, and the rules
    require it to name that item's objective. So the graph arm reads them the
    way the prose arm always has, and both run the identical check.
    """
    found: list[tuple[str, dict]] = []
    for item in graph.element_nodes(NodeType.ASSESSMENT):
        for rc in item["data"].get("rubric") or []:
            if isinstance(rc, dict):
                found.append((f"{item['id']}/{rc.get('id', '?')}", rc))
    return found


def rubric_consistency(graph) -> list[Violation]:
    """Every rubric criterion states an observable scoring description."""
    return rubric_consistency_items(_criteria_of(graph))


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
            _VAGUE_RUBRIC_RE.search(lowered)
            and not _OBSERVABLE_RE.search(lowered)
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
    # ONE reader for this field, shared with the fan-out's work-set planner:
    # it strips the namespace off an objective id a model copied from context
    # ("objective:ILO-01"), accepts both the bare-category and the
    # {plan_category, instrument} shapes, and drops anything that is not one
    # of the three categories. Reading it here instead meant a dict category
    # became `str(dict)`, which no item could ever realise.
    for lo_id, category in dev_plans.plan_category_pairs(targets):
        key = (lo_id, category)
        if key not in realised:
            violations.append(Violation(
                node_id=f"{NodeType.OBJECTIVE}{graph.ELEMENT_SEP}{lo_id}",
                edge_type="", violation_type="plan_coverage", severity="error",
                message=(f"The assessment plan promises a {category} item for {lo_id}, "
                         f"but no assessment item realises that pair."),
                repair_hint=f"Add a {category} assessment item aligned to {lo_id}.",
                metadata={"lo_id": lo_id, "plan_category": category},
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
    """Kept in *meaning* from the formative-intent rule ("formative evaluation
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
    # "Declares formative intent" = the plan PROMISED a formative item for some
    # objective, read off `lo_coverage_targets` like everything else that asks
    # what the plan committed to. It used to gate on `data["formative"]`, one of
    # the three optional buckets P3 also hung on: no rule asked for them and the
    # schema no longer declares them, so this check could not fire either —
    # measured on run 7ef3ed16, whose plan named formative for eight of nine
    # objectives and produced zero `evaluation_quality` findings.
    if "formative" not in alignment._promised_categories(data):
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
        if any(_ACTIVE_ACTIVITY_RE.search(text) for text in texts):
            continue
        if not any(_PASSIVE_ACTIVITY_RE.search(text) for text in texts):
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

def evidence_alignment(graph) -> list[Violation]:
    """A rubric criterion's declared evidence type must be producible by the
    assessment item it marks.

    The item is now the criterion's PARENT rather than the far end of a C6
    edge, so the lookup is direct: a criterion cannot be evaluated against an
    item it does not belong to, and the "no linked item" case this used to skip
    can no longer occur.
    """
    violations: list[Violation] = []
    for item in graph.element_nodes(NodeType.ASSESSMENT):
        capability = alignment.item_type_capability(str(item["data"].get("type", "") or ""))
        for rc in item["data"].get("rubric") or []:
            if not isinstance(rc, dict):
                continue
            evidence_type = str(rc.get("evidence_type", "") or "")
            if not evidence_type:
                continue
            if alignment.item_type_capability(evidence_type) <= capability:
                continue
            rc_id = str(rc.get("id", "?"))
            violations.append(Violation(
                node_id=item["id"], edge_type="", violation_type="evidence_alignment",
                severity="warning",
                message=(f"Rubric criterion '{rc_id}' expects '{evidence_type}' evidence but "
                         f"'{item['data'].get('item_id', '?')}' can't produce it."),
                repair_hint="Either loosen the criterion's evidence type or change the item's format.",
                metadata={"rc_id": rc_id, "evidence_type": evidence_type,
                          "item_id": str(item["data"].get("item_id", ""))},
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

# Only C2/C3/C4/P3/P6 have a re-runnable establisher (the id / id-list / type
# mechanisms); the eleven provenance-mechanism relations (C1, C5, P1, P2, P4,
# P5, P7, P8, P9, P10, P11) can't be re-established generically — they need the
# specific source ids the producing agent had at generation time. The five are
# called explicitly below rather than driven off a table: a table nothing else
# reads is just a second place for the list to go stale.
def relation_coverage(graph) -> list[Violation]:
    """Re-run the re-runnable establishers (idempotent — safe to call
    repeatedly, and catches a reference that stopped resolving after a
    repair elsewhere) to surface dangling/mismatched references, then check
    coverage of every relation (core + secondary) for missing links."""
    violations: list[Violation] = []

    establisher_gaps: list[dict] = []
    establisher_gaps += alignment.match_id_reverse(graph, "C2", field="aligned_objective")
    establisher_gaps += alignment.match_list_reverse(graph, "C3", field="aligned_objectives")
    establisher_gaps += alignment.match_list(graph, "C4", field="prepares_for_assessment")
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

    # What the establishers already reported, by the SAME identity the ledger
    # uses (``Violation.key``; no relation id is in ``IDENTITY_FIELDS``, so the
    # pair IS the key). P3 and P6 check their ``coverage_side`` node directly —
    # an item gets its edge iff it is not a gap — so the loop below would raise
    # a second Violation on the very node just reported, with a vaguer message.
    #
    # MEASURED (run 7ef3ed16): 13 assessment items reported as 26 P3
    # violations. The ledger deduplicated them, the raw list did not, and the
    # cost landed on the reconciliation pass — rounds 12/13/14 each returned
    # the same 29, ``SELF_VALIDATION_BUDGET`` ran out, and three
    # ``plan_coverage`` findings were stamped ``open_reason: "budget"`` when
    # they had in fact converged. That relabels a parameter we chose as a
    # result about the model, which is the one thing ``memory.py``'s reason
    # precedence exists to prevent.
    #
    # C2/C3/C4 are deliberately NOT skipped: they report on the node that
    # DECLARES the reference (the item, the activity) while their coverage side
    # is the node that should receive one (the objective, the assessment task).
    # Two different node sets, two different findings — the pair below tells
    # them apart without a table to keep in step.
    reported = {(v.violation_type, v.node_id) for v in violations}

    for relation_id, relation in alignment.MATRIX.items():
        _, uncovered = alignment.relation_coverage(graph, relation_id)
        for node_id in uncovered:
            if (relation_id, node_id) in reported:
                continue
            metadata = {"node_id": node_id}
            if node_id.startswith(f"{NodeType.OBJECTIVE}{graph.ELEMENT_SEP}"):
                metadata["lo_id"] = _bare_id(graph, node_id)
            violations.append(Violation(
                node_id=node_id, edge_type="", violation_type=relation_id,
                severity="error" if relation.tier == "core" else "warning",
                message=f"{node_id} has no {relation_id} ({relation.label}) coverage.",
                repair_hint=_COVERAGE_HINTS.get(
                    relation_id, f"Establish a {relation.label} link."),
                metadata=metadata,
            ))
    return violations


#: What the OWNING agent can actually do about an uncovered node, for the
#: relations whose fix is a field edit rather than a new artifact. The generic
#: "establish a link" is the class of instruction a small model does not act
#: on; naming the field is what closes the gap.
_COVERAGE_HINTS = {
    "P8": ("This media selection names no constraint that exists. Set "
           "`respects_constraints` to constraint ids from `read_nodes`, which "
           "lists every constraint of this brief."),
    "P10": ("Nobody scheduled this activity. Put it in a session block of the "
            "implementation dev_plan, so a session guide delivers it."),
    "P11": ("Nobody hands this material out. Put it in a session block of the "
            "implementation dev_plan, so a session guide provisions it."),
}


def bloom_mismatches(graph) -> list[Violation]:
    """Both cross-checks: LO vs Assessment (C2) and LO vs Activity (C3).
    Assessment Designer calls the C2 half on its own items; Activity
    Designer calls the C3 half on its own activities — both self-contained,
    same as ``bloom_mismatch`` was in the old single-relation (R3-only)
    verifier."""
    # ``repair_hint`` is carried through, not dropped. ``_repair_request``
    # (core/agentic/loop.py) renders the "Fix:" line only when a hint exists, so
    # without this both Bloom mismatches reached the agent as a bare sentence
    # with no instruction — and neither has a deterministic repair either, so
    # the hint is the ONLY thing that can close them.
    violations: list[Violation] = []
    for bv in alignment.bloom_assessment_violations(graph):
        violations.append(Violation(
            node_id=bv["node_id"], edge_type="", violation_type="bloom_mismatch_assessment",
            severity="error", message=bv["message"],
            repair_hint=bv.get("repair_hint", ""), metadata=bv.get("metadata", {}),
        ))
    for bv in alignment.bloom_activity_violations(graph):
        violations.append(Violation(
            node_id=bv["node_id"], edge_type="", violation_type="bloom_mismatch_activity",
            severity="error", message=bv["message"],
            repair_hint=bv.get("repair_hint", ""), metadata=bv.get("metadata", {}),
        ))
    return violations

from __future__ import annotations
import re
from ..graph import NodeType
from ..schema import DesignBrief
from .. import alignment
from dataclasses import dataclass, field
from .base import BaseISDAgent

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
class VerifierViolation:
    node_id: str
    edge_type: str
    message: str
    # Completeness tier: bloom | measurability | activity_engagement | rubric_consistency |
    #   feasibility | actionability | evaluation_quality
    # Alignment tier: R1..R13 | bloom_mismatch
    violation_type: str = "coverage"
    severity: str = "error"                   # error | warning
    repair_hint: str = ""
    metadata: dict = field(default_factory=dict)


class PedagogicalVerifierAgent(BaseISDAgent):
    def run(self, design_brief: DesignBrief) -> None:
        pass  # not used directly; call verify()

    def verify(self, design_brief: DesignBrief | None = None) -> list[VerifierViolation]:
        """Two tiers, both always on: completeness (single-artifact content
        quality — a small model still needs self-repair to avoid a broken/empty
        output) and alignment (relation coverage + the Bloom/format validity
        rule, read from the alignment graph's established edges)."""
        violations: list[VerifierViolation] = []
        violations.extend(self._check_bloom_verbs())
        violations.extend(self._check_measurability())
        violations.extend(self._check_activity_engagement())
        violations.extend(self._check_rubric_consistency())
        violations.extend(self._check_feasibility(design_brief))
        violations.extend(self._check_actionability())
        violations.extend(self._check_evaluation_quality())
        violations.extend(self._check_relation_coverage())
        violations.extend(self._check_bloom_format_validity())
        return violations

    # ══════════════════════ completeness tier (always on) ═══════════════════
    # Single-artifact quality: every check here reads exactly one node/item,
    # never a relation between two artifacts, so none of it needs the graph.

    # ── Bloom verb taxonomy validity ──────────────────────────────────────────
    def _check_bloom_verbs(self) -> list[VerifierViolation]:
        violations: list[VerifierViolation] = []
        for obj in self.graph.section_nodes(NodeType.OBJECTIVE):
            lo_list = obj["data"].get("learning_objectives", [])
            for lo in lo_list:
                verb = lo.get("bloom_verb", "").lower().strip(".,;")
                statement = lo.get("statement", "")
                lo_id = lo.get("id", obj["id"])
                if not verb:
                    violations.append(VerifierViolation(
                        node_id=obj["id"],
                        edge_type="",
                        violation_type="bloom",
                        severity="warning",
                        message=f"LO '{lo_id}' missing bloom_verb field.",
                        repair_hint="Add a measurable Bloom's taxonomy verb.",
                        metadata={"lo_id": lo_id, "statement": statement},
                    ))
                elif verb not in _ALL_BLOOM_VERBS:
                    stmt_lower = statement.lower()
                    has_bloom = any(bv in stmt_lower for bv in _ALL_BLOOM_VERBS)
                    if not has_bloom:
                        violations.append(VerifierViolation(
                            node_id=obj["id"],
                            edge_type="",
                            violation_type="bloom",
                            severity="warning",
                            message=f"LO '{lo_id}' uses non-standard verb '{verb}' not in Bloom's taxonomy.",
                            repair_hint=f"Use a standard Bloom's verb such as: {', '.join(list(_ALL_BLOOM_VERBS)[:8])}...",
                            metadata={"lo_id": lo_id, "verb": verb},
                        ))
                else:
                    level_idx = _BLOOM_LEVEL_INDEX.get(str(lo.get("level", "")).lower().strip())
                    verb_levels = _VERB_LEVELS.get(verb, set())
                    if level_idx and verb_levels and level_idx not in verb_levels:
                        violations.append(VerifierViolation(
                            node_id=obj["id"],
                            edge_type="",
                            violation_type="bloom",
                            severity="warning",
                            message=(
                                f"LO '{lo_id}' declares level '{lo.get('level')}' but uses verb "
                                f"'{verb}', which belongs to a different Bloom level."
                            ),
                            repair_hint="Align the verb with the declared level (or fix the level).",
                            metadata={"lo_id": lo_id, "verb": verb, "level": lo.get("level")},
                        ))
        return violations

    # ── objectives state a measurable degree or condition (audit-only) ───────
    def _check_measurability(self) -> list[VerifierViolation]:
        """Narrowly: only a *non-observable* verb (understand, know, ...) with
        no criterion is unmeasurable. Audit-only (not auto-repaired): the vague
        verb itself is fixed by the Bloom-verb repair."""
        violations: list[VerifierViolation] = []
        for obj in self.graph.section_nodes(NodeType.OBJECTIVE):
            for lo in obj["data"].get("learning_objectives", []) or []:
                if not isinstance(lo, dict):
                    continue
                statement = str(lo.get("statement", ""))
                lo_id = lo.get("id", obj["id"])
                if not statement.strip():
                    continue
                verb = str(lo.get("bloom_verb", "")).lower().strip(".,;")
                stmt_lower = statement.lower()
                is_vague = verb in _VAGUE_VERBS or any(
                    re.search(rf"\b{re.escape(v)}\b", stmt_lower) for v in _VAGUE_VERBS
                )
                if not is_vague:
                    continue
                if _DEGREE_PATTERN.search(statement) or _CONDITION_PATTERN.search(statement):
                    continue
                violations.append(VerifierViolation(
                    node_id=obj["id"],
                    edge_type="",
                    violation_type="measurability",
                    severity="warning",
                    message=(
                        f"LO '{lo_id}' states no success criterion or condition; "
                        "achievement cannot be judged objectively."
                    ),
                    repair_hint=(
                        "Add an observable degree and/or condition to the statement, "
                        "e.g. 'given a starter codebase, ... with at least 80% of unit tests passing'."
                    ),
                    metadata={"lo_id": lo_id, "statement": statement},
                ))
        return violations

    # ── higher-order objectives get active practice ───────────────────────────
    def _check_activity_engagement(self) -> list[VerifierViolation]:
        """An Apply+ objective practiced only through passive formats (lecture,
        reading, video) gives learners no chance to perform the target skill."""
        levels = self._objective_levels()
        higher = sorted(lo_id for lo_id, idx in levels.items() if idx >= 3)
        if not higher:
            return []
        violations: list[VerifierViolation] = []
        for obj in self.graph.section_nodes(NodeType.ACTIVITY):
            activities = [
                a for a in obj["data"].get("learning_activities", []) or []
                if isinstance(a, dict)
            ]
            if not activities:
                continue
            any_declared = any(a.get("aligned_objectives") for a in activities)
            for lo_id in higher:
                relevant = [
                    a for a in activities
                    if not any_declared or lo_id in (a.get("aligned_objectives") or [])
                ]
                if not relevant:
                    continue  # missing linkage is the R4 coverage check's concern
                texts = [
                    f"{a.get('activity_name', '')} {a.get('description', '')}".lower()
                    for a in relevant
                ]
                if any(marker in text for text in texts for marker in _ACTIVE_ACTIVITY_MARKERS):
                    continue
                if not any(marker in text for text in texts for marker in _PASSIVE_ACTIVITY_MARKERS):
                    continue  # unclassifiable formats: do not guess
                names = [str(a.get("activity_name", "?")) for a in relevant]
                violations.append(VerifierViolation(
                    node_id=obj["id"],
                    edge_type="",
                    violation_type="activity_engagement",
                    severity="warning",
                    message=(
                        f"Higher-order objective '{lo_id}' is practiced only through "
                        f"passive formats ({', '.join(names)})."
                    ),
                    repair_hint=(
                        "Add a hands-on activity (lab, exercise, project, simulation) "
                        "aligned to this objective."
                    ),
                    metadata={"lo_id": lo_id, "passive_activities": names},
                ))
        return violations

    # ── assessment rubric quality (item-level, not cross-artifact) ───────────
    def _check_rubric_consistency(self) -> list[VerifierViolation]:
        violations: list[VerifierViolation] = []
        for node in self.graph.section_nodes(NodeType.ASSESSMENT):
            for item in node["data"].get("assessment_tools", []) or []:
                if not isinstance(item, dict):
                    continue
                item_id = item.get("item_id", "?")
                criteria = str(item.get("scoring_criteria") or item.get("scoring_rubric") or "").strip()
                lowered = criteria.lower()
                if not criteria or any(marker in lowered for marker in _PLACEHOLDER_MARKERS):
                    violations.append(VerifierViolation(
                        node_id=node["id"],
                        edge_type="",
                        violation_type="rubric_consistency",
                        severity="warning",
                        message=f"Assessment item '{item_id}' has no scoring criteria.",
                        repair_hint="State how the item is scored (key, point scale, or rubric).",
                        metadata={"item_id": item_id, "scoring_criteria": criteria},
                    ))
                elif str(item.get("type", "")).lower() in ("performance_task", "performance", "project", "rubric"):
                    is_vague = len(criteria) < 40 or (
                        any(term in lowered for term in _VAGUE_RUBRIC_TERMS)
                        and not any(term in lowered for term in _OBSERVABLE_TERMS)
                    )
                    if is_vague:
                        violations.append(VerifierViolation(
                            node_id=node["id"],
                            edge_type="",
                            violation_type="rubric_consistency",
                            severity="warning",
                            message=f"Performance item '{item_id}' lacks an observable scoring rubric.",
                            repair_hint="Replace vague language with observable, scorable criteria.",
                            metadata={"item_id": item_id, "scoring_criteria": criteria},
                        ))
        return violations

    def _objective_levels(self) -> dict[str, int]:
        """LO id -> Bloom level index (1-6), from the declared level or the verb."""
        levels: dict[str, int] = {}
        for obj in self.graph.section_nodes(NodeType.OBJECTIVE):
            for lo in obj["data"].get("learning_objectives", []) or []:
                if not isinstance(lo, dict) or not lo.get("id"):
                    continue
                idx = _BLOOM_LEVEL_INDEX.get(str(lo.get("level", "")).lower().strip())
                if not idx:
                    verb = str(lo.get("bloom_verb", "")).lower().strip(".,;")
                    idx = max(_VERB_LEVELS.get(verb, {0}))
                levels[str(lo["id"])] = idx
        return levels

    # ── delivery feasibility against the brief's constraints ─────────────────
    def _check_feasibility(self, design_brief: DesignBrief | None) -> list[VerifierViolation]:
        if design_brief is None:
            return []
        total_hours = _duration_hours(design_brief)
        if total_hours <= 0:
            return []
        modules: list = []
        sessions: list = []
        for node in self.graph.section_nodes("content_structure"):
            modules += node["data"].get("modules", []) or []
        for node in self.graph.section_nodes(NodeType.ACTIVITY) + self.graph.section_nodes(NodeType.MATERIAL):
            guide = node["data"].get("instructor_guide", {})
            if isinstance(guide, dict):
                sessions += guide.get("session_guides", []) or []
        load_units = len(modules) + len(sessions)
        # Heuristic: each module/session needs ~1.5h. Flag only clear overload.
        if load_units and load_units * 1.5 > total_hours * 2:
            return [VerifierViolation(
                node_id=self.graph.section_id(NodeType.IMPLEMENTATION_PLAN),
                edge_type="constrains",
                violation_type="feasibility",
                severity="warning",
                message=(
                    f"Design packs {load_units} modules/sessions into ~{total_hours}h; "
                    "delivery is likely infeasible."
                ),
                repair_hint="Reduce scope per session or extend the schedule in the implementation plan.",
                metadata={"load_units": load_units, "total_hours": total_hours},
            )]
        return []

    # ── actionability of implementation/development guidance ─────────────────
    def _check_actionability(self) -> list[VerifierViolation]:
        violations: list[VerifierViolation] = []
        for node in self.graph.section_nodes(NodeType.IMPLEMENTATION_PLAN):
            data = node["data"]
            orientation = data.get("instructor_orientation", {})
            if isinstance(orientation, dict) and not _has_concrete_items(
                orientation.get("competency_checklist"), orientation.get("materials")
            ):
                violations.append(VerifierViolation(
                    node_id=node["id"],
                    edge_type="constrains",
                    violation_type="actionability",
                    severity="warning",
                    message="Instructor orientation lacks concrete facilitator actions or materials.",
                    repair_hint="Add a competency checklist and facilitator materials with concrete steps.",
                    metadata={"section": "instructor_orientation"},
                ))
            system_check = data.get("system_check", {})
            if isinstance(system_check, dict) and not _has_concrete_items(system_check.get("checklist")):
                violations.append(VerifierViolation(
                    node_id=node["id"],
                    edge_type="constrains",
                    violation_type="actionability",
                    severity="warning",
                    message="System check has no actionable checklist.",
                    repair_hint="Add concrete pre-session verification steps.",
                    metadata={"section": "system_check"},
                ))
        return violations

    # ── the formative evaluation plan is concrete ─────────────────────────────
    def _check_evaluation_quality(self) -> list[VerifierViolation]:
        """An evaluation section whose formative plan names no data-collection
        method cannot drive the revision loop it exists for."""
        violations: list[VerifierViolation] = []
        for node in self.graph.section_nodes(NodeType.EVALUATION):
            formative = node["data"].get("formative")
            if not isinstance(formative, dict):
                continue
            data_collection = formative.get("data_collection")
            methods = None
            if isinstance(data_collection, dict):
                methods = data_collection.get("methods")
            if methods is None:
                methods = formative.get("methods")
            if not _has_concrete_items(methods):
                violations.append(VerifierViolation(
                    node_id=node["id"],
                    edge_type="",
                    violation_type="evaluation_quality",
                    severity="warning",
                    message="Formative evaluation names no concrete data-collection method.",
                    repair_hint=(
                        "List concrete formative methods (observation checklist, exit "
                        "tickets, rubric checkpoints) under formative data collection."
                    ),
                    metadata={"section": "formative"},
                ))
        return violations

    # ═══════════════════ alignment tier ═════════════════════════════════════
    # Cross-artifact checks: coverage of the 13-relation matrix + the one
    # boolean Bloom/format-validity rule. Never runs unless the harness has
    # graph coordination active (see verify()).

    def _check_relation_coverage(self) -> list[VerifierViolation]:
        """Re-run the deterministic establishers (idempotent — safe to call
        repeatedly, and catches a reference that stopped resolving after a
        repair elsewhere) to surface dangling/mismatched references, then
        check coverage of all 13 relations for missing links entirely."""
        violations: list[VerifierViolation] = []

        establisher_gaps: list[dict] = []
        establisher_gaps += alignment.match_id(self.graph, "R3", target_node_type=NodeType.OBJECTIVE, field="aligned_objective")
        establisher_gaps += alignment.match_r4_supports(self.graph)
        establisher_gaps += alignment.match_id(self.graph, "R5", target_node_type=NodeType.OBJECTIVE, field="aligned_objective")
        establisher_gaps += alignment.match_r6_realizes(self.graph)
        establisher_gaps += alignment.match_r9_realizes(self.graph)
        establisher_gaps += alignment.match_r12_realizes(self.graph)
        for gap in establisher_gaps:
            node_id = gap["node_id"]
            # These gaps are always about the SOURCE item failing to resolve
            # its own reference (dangling aligned_objective, no plan_category
            # match, ...) — repair() methods key on the bare item id, mirroring
            # the item's own id field (e.g. "AT-02", not "assessment:AT-02").
            bare_id = node_id.split(self.graph.ELEMENT_SEP, 1)[-1] if self.graph.is_element(node_id) else node_id
            violations.append(VerifierViolation(
                node_id=node_id, edge_type="", violation_type=gap["relation_id"],
                severity="error", message=gap["message"],
                metadata={"node_id": node_id, "item_id": bare_id},
            ))

        for relation_id in alignment.REGISTRY:
            _, uncovered = alignment.relation_coverage(self.graph, relation_id)
            for node_id in uncovered:
                metadata = {"node_id": node_id}
                if node_id.startswith(f"{NodeType.OBJECTIVE}{self.graph.ELEMENT_SEP}"):
                    metadata["lo_id"] = node_id.split(self.graph.ELEMENT_SEP, 1)[-1]
                violations.append(VerifierViolation(
                    node_id=node_id, edge_type="", violation_type=relation_id,
                    severity="error" if relation_id in ("R3", "R5") else "warning",
                    message=f"{node_id} has no {relation_id} ({alignment.REGISTRY[relation_id].label}) coverage.",
                    repair_hint=f"Establish a {alignment.REGISTRY[relation_id].label} link.",
                    metadata=metadata,
                ))
        return violations

    def _check_bloom_format_validity(self) -> list[VerifierViolation]:
        """The one boolean rule beyond coverage: can the assessment format
        elicit the objective's declared Bloom level?"""
        violations: list[VerifierViolation] = []
        for bv in alignment.bloom_format_violations(self.graph):
            violations.append(VerifierViolation(
                node_id=bv["node_id"], edge_type="", violation_type="bloom_mismatch",
                severity="error", message=bv["message"], metadata=bv.get("metadata", {}),
            ))
        return violations


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


def _has_concrete_items(*candidates) -> bool:
    for candidate in candidates:
        if isinstance(candidate, list):
            for item in candidate:
                text = item if isinstance(item, str) else str(item)
                lowered = text.strip().lower()
                if lowered and not any(marker in lowered for marker in _PLACEHOLDER_MARKERS):
                    return True
    return False

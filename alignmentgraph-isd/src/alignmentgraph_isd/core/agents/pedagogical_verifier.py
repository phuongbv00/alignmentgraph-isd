from __future__ import annotations
import re
from ..graph import EdgeType, NodeType
from ..schema import DesignBrief
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

# The highest Bloom level an assessment format can plausibly elicit. Unknown
# formats default to 6 so only clearly recognition-bound formats can fire.
_ITEM_TYPE_CAPABILITY = {
    "true_false": 1,
    "matching": 1,
    "multiple_choice": 2,
    "quiz": 2,
    "short_answer": 4,
}
_RECALL_CAPABILITY_CEILING = 2

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
    # coverage | bloom | measurability | activity_support | activity_engagement |
    # rubric_consistency | bloom_mismatch | feasibility | actionability |
    # evaluation_alignment | evaluation_quality
    violation_type: str = "coverage"
    severity: str = "error"                   # error | warning
    repair_hint: str = ""
    metadata: dict = field(default_factory=dict)


class PedagogicalVerifierAgent(BaseISDAgent):
    def run(self, design_brief: DesignBrief, context_pack: dict) -> None:
        pass  # not used directly; call verify()

    def verify(self, design_brief: DesignBrief | None = None) -> list[VerifierViolation]:
        # No ablation gate: the verifier always runs when called. Whether it is
        # called at all is a workflow decision (full/wo_ma wire QC nodes; wo_qc
        # does not; the dynamic planner schedules it per its own policy).
        violations: list[VerifierViolation] = []
        violations.extend(self._check_assessment_coverage())
        violations.extend(self._check_bloom_verbs())
        violations.extend(self._check_measurability())
        violations.extend(self._check_activity_support())
        violations.extend(self._check_activity_engagement())
        violations.extend(self._check_rubric_consistency())
        violations.extend(self._check_assessment_bloom_match())
        violations.extend(self._check_feasibility(design_brief))
        violations.extend(self._check_actionability())
        violations.extend(self._check_evaluation_alignment())
        violations.extend(self._check_evaluation_quality())
        return violations

    # ── Check 1: every objective has ≥1 assessment measuring it ───────────────
    def _check_assessment_coverage(self) -> list[VerifierViolation]:
        return self._coverage_violations(
            edge_type=EdgeType.MEASURES,
            violation_type="coverage",
            severity="error",
            message_tpl="Objective '{lo}' has no assessment measuring it.",
            repair_hint="Create an assessment item aligned with this objective and add a 'measures' edge.",
        )

    def _coverage_violations(
        self,
        *,
        edge_type: str,
        violation_type: str,
        severity: str,
        message_tpl: str,
        repair_hint: str,
    ) -> list[VerifierViolation]:
        """Element-level coverage: each objective element node needs an aligned edge.

        Coverage is computed over the first-class objective element nodes rather
        than the single ``objective_0`` section node. Falls back to the section
        node when no element nodes exist (e.g. an empty graph)."""
        edges = [e for e in self.graph.get_edges(edge_type) if not e.get("stale")]
        covered_targets = {e["target"] for e in edges}
        covered_evidence = {e.get("evidence") for e in edges if e.get("evidence")}

        targets = self.graph.element_nodes(NodeType.OBJECTIVE) or self.graph.section_nodes(NodeType.OBJECTIVE)
        violations: list[VerifierViolation] = []
        for node in targets:
            lo_id = str(node["data"].get("id") or node["id"])
            if node["id"] in covered_targets or lo_id in covered_evidence:
                continue
            violations.append(VerifierViolation(
                node_id=node["id"],
                edge_type=edge_type,
                violation_type=violation_type,
                severity=severity,
                message=message_tpl.format(lo=lo_id),
                repair_hint=repair_hint,
                metadata={"lo_id": lo_id},
            ))
        return violations

    # ── Check 2: learning objectives use measurable Bloom's verbs ─────────────
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
                    # Check if verb appears in the statement as a fallback
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
                    # Verb is standard: it must be consistent with the declared level.
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

    # ── Check 2b: objectives state a measurable degree or condition ──────────
    def _check_measurability(self) -> list[VerifierViolation]:
        """Measurability, narrowly: only a *non-observable* verb (understand, know,
        ...) with no criterion is unmeasurable. A well-formed objective with an
        observable Bloom verb (analyze, design, apply, ...) is measurable enough
        even without a numeric degree — flagging those over-fires and forces
        needless rewrites. This check is audit-only (not auto-repaired); the vague
        verb itself is fixed by the Bloom-verb repair."""
        violations: list[VerifierViolation] = []
        for obj in self.graph.section_nodes(NodeType.OBJECTIVE):
            for lo in obj["data"].get("learning_objectives", []) or []:
                if not isinstance(lo, dict):
                    continue
                statement = str(lo.get("statement", ""))
                lo_id = lo.get("id", obj["id"])
                if not statement.strip():
                    continue  # empty statements are a schema concern, not measurability
                verb = str(lo.get("bloom_verb", "")).lower().strip(".,;")
                stmt_lower = statement.lower()
                is_vague = verb in _VAGUE_VERBS or any(
                    re.search(rf"\b{re.escape(v)}\b", stmt_lower) for v in _VAGUE_VERBS
                )
                if not is_vague:
                    continue  # observable verb → measurable enough, do not flag
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

    # ── Check 3: every objective has ≥1 activity supporting it ───────────────
    def _check_activity_support(self) -> list[VerifierViolation]:
        # Only flag this if we have activity nodes (not in single-agent mode where
        # activities are embedded inside the design section)
        if not self.graph.get_nodes(NodeType.ACTIVITY):
            return []
        return self._coverage_violations(
            edge_type=EdgeType.SUPPORTS,
            violation_type="activity_support",
            severity="warning",
            message_tpl="Objective '{lo}' has no learning activity explicitly supporting it.",
            repair_hint="Create a learning activity that explicitly supports this objective and add a 'supports' edge.",
        )

    # ── Check 3b: higher-order objectives get active practice ────────────────
    def _check_activity_engagement(self) -> list[VerifierViolation]:
        """An Apply+ objective practiced only through passive formats (lecture,
        reading, video) gives learners no chance to perform the target skill."""
        levels = self._objective_levels()
        higher = sorted(lo_id for lo_id, idx in levels.items() if idx >= 3)
        if not higher:
            return []
        violations: list[VerifierViolation] = []
        for obj in self.graph.section_nodes(NodeType.OBJECTIVE):
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
                    continue  # missing linkage is the coverage check's concern
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

    # ── Check 4: assessment rubric consistency ───────────────────────────────
    def _check_rubric_consistency(self) -> list[VerifierViolation]:
        violations: list[VerifierViolation] = []
        valid_lo_ids = set(self._objective_levels())
        for node in self.graph.section_nodes(NodeType.ASSESSMENT):
            for item in node["data"].get("assessment_tools", []) or []:
                if not isinstance(item, dict):
                    continue
                item_id = item.get("item_id", "?")
                aligned = item.get("aligned_objective")
                if not aligned:
                    violations.append(VerifierViolation(
                        node_id=node["id"],
                        edge_type=EdgeType.MEASURES,
                        violation_type="rubric_consistency",
                        severity="error",
                        message=f"Assessment item '{item_id}' has no aligned_objective.",
                        repair_hint="Set aligned_objective to the LO id this item measures.",
                        metadata={"item_id": item_id},
                    ))
                elif valid_lo_ids and str(aligned) not in valid_lo_ids:
                    violations.append(VerifierViolation(
                        node_id=node["id"],
                        edge_type=EdgeType.MEASURES,
                        violation_type="rubric_consistency",
                        severity="error",
                        message=(
                            f"Assessment item '{item_id}' claims to measure '{aligned}', "
                            "but no such objective exists."
                        ),
                        repair_hint="Point aligned_objective at an existing LO id.",
                        metadata={"item_id": item_id, "aligned_objective": str(aligned), "dangling": True},
                    ))
                criteria = str(item.get("scoring_criteria") or item.get("scoring_rubric") or "").strip()
                lowered = criteria.lower()
                if not criteria or any(marker in lowered for marker in _PLACEHOLDER_MARKERS):
                    violations.append(VerifierViolation(
                        node_id=node["id"],
                        edge_type=EdgeType.MEASURES,
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
                            edge_type=EdgeType.MEASURES,
                            violation_type="rubric_consistency",
                            severity="warning",
                            message=f"Performance item '{item_id}' lacks an observable scoring rubric.",
                            repair_hint="Replace vague language with observable, scorable criteria.",
                            metadata={"item_id": item_id, "scoring_criteria": criteria},
                        ))
        return violations

    # ── Check 4b: assessment formats can elicit the objective's Bloom level ──
    def _check_assessment_bloom_match(self) -> list[VerifierViolation]:
        """Constructive alignment at the format level: a higher-order objective
        (Apply+) measured exclusively by recognition-bound formats (MCQ,
        true/false) cannot demonstrate the intended cognitive level."""
        levels = self._objective_levels()
        violations: list[VerifierViolation] = []
        for node in self.graph.section_nodes(NodeType.ASSESSMENT):
            items_by_lo: dict[str, list[dict]] = {}
            for item in node["data"].get("assessment_tools", []) or []:
                if isinstance(item, dict) and item.get("aligned_objective"):
                    items_by_lo.setdefault(str(item["aligned_objective"]), []).append(item)
            for lo_id, lo_level in levels.items():
                items = items_by_lo.get(lo_id, [])
                if lo_level < 3 or not items:
                    continue
                capability = max(
                    _ITEM_TYPE_CAPABILITY.get(str(item.get("type", "")).lower(), 6)
                    for item in items
                )
                if capability <= _RECALL_CAPABILITY_CEILING:
                    item_ids = [str(item.get("item_id", "?")) for item in items]
                    violations.append(VerifierViolation(
                        node_id=node["id"],
                        edge_type=EdgeType.MEASURES,
                        violation_type="bloom_mismatch",
                        severity="error",
                        message=(
                            f"Objective '{lo_id}' targets a higher-order level but is measured "
                            f"only by recognition-level formats ({', '.join(item_ids)})."
                        ),
                        repair_hint=(
                            "Add a constructed-response or performance item for this objective "
                            "(short answer, performance task, or project)."
                        ),
                        metadata={"lo_id": lo_id, "item_ids": item_ids, "lo_level": lo_level},
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

    # ── Check 5: delivery feasibility against the brief's constraints ─────────
    def _check_feasibility(self, design_brief: DesignBrief | None) -> list[VerifierViolation]:
        if design_brief is None:
            return []
        total_hours = _duration_hours(design_brief)
        if total_hours <= 0:
            return []
        modules: list = []
        sessions: list = []
        for node in self.graph.section_nodes(NodeType.OBJECTIVE):
            modules += node["data"].get("content_structure", {}).get("modules", []) or []
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

    # ── Check 6: actionability of implementation/development guidance ────────
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

    # ── Check 7: every objective has evaluation evidence ─────────────────────
    def _check_evaluation_alignment(self) -> list[VerifierViolation]:
        objective_nodes = self.graph.section_nodes(NodeType.OBJECTIVE)
        if not objective_nodes:
            return []
        evaluates_edges = self.graph.get_edges(EdgeType.EVALUATES)
        evaluated_targets = {e["target"] for e in evaluates_edges if not e.get("stale")}
        evaluated_evidence = {e.get("evidence") for e in evaluates_edges if not e.get("stale")}
        # Summative tools that name an aligned objective also count as evidence.
        for node in self.graph.section_nodes(NodeType.EVALUATION):
            for item in node["data"].get("summative", {}).get("assessment_tools", []) or []:
                if isinstance(item, dict) and item.get("aligned_objective"):
                    evaluated_evidence.add(item["aligned_objective"])

        violations: list[VerifierViolation] = []
        for obj in objective_nodes:
            lo_ids = [
                lo.get("id")
                for lo in obj["data"].get("learning_objectives", [])
                if isinstance(lo, dict) and lo.get("id")
            ]
            if obj["id"] in evaluated_targets:
                continue
            uncovered = [lo_id for lo_id in lo_ids if lo_id not in evaluated_evidence]
            if uncovered or (not lo_ids and obj["id"] not in evaluated_targets):
                violations.append(VerifierViolation(
                    node_id=obj["id"],
                    edge_type=EdgeType.EVALUATES,
                    violation_type="evaluation_alignment",
                    severity="warning",
                    message=(
                        f"Objective '{obj['id']}' lacks evaluation evidence for: "
                        f"{', '.join(uncovered) or obj['id']}."
                    ),
                    repair_hint="Add an 'evaluates' edge or a summative item aligned to each objective.",
                    metadata={"uncovered": uncovered},
                ))
        return violations

    # ── Check 7b: the formative evaluation plan is concrete ──────────────────
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


def _duration_hours(design_brief: DesignBrief) -> float:
    text = f"{design_brief.context.duration} {design_brief.duration}".lower()
    import re
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

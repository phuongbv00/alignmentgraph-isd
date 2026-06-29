from __future__ import annotations
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


@dataclass
class VerifierViolation:
    node_id: str
    edge_type: str
    message: str
    # coverage | bloom | activity_support | rubric_consistency | feasibility |
    # actionability | evaluation_alignment
    violation_type: str = "coverage"
    severity: str = "error"                   # error | warning
    repair_hint: str = ""
    metadata: dict = field(default_factory=dict)


class PedagogicalVerifierAgent(BaseISDAgent):
    def run(self, design_brief: DesignBrief, context_pack: dict) -> None:
        pass  # not used directly; call verify()

    def verify(self, design_brief: DesignBrief | None = None) -> list[VerifierViolation]:
        if not self.config.ablation.use_verifier:
            return []
        violations: list[VerifierViolation] = []
        violations.extend(self._check_assessment_coverage())
        violations.extend(self._check_bloom_verbs())
        violations.extend(self._check_activity_support())
        violations.extend(self._check_rubric_consistency())
        violations.extend(self._check_feasibility(design_brief))
        violations.extend(self._check_actionability())
        violations.extend(self._check_evaluation_alignment())
        return violations

    # ── Check 1: every objective has ≥1 assessment measuring it ───────────────
    def _check_assessment_coverage(self) -> list[VerifierViolation]:
        return self._coverage_violations(
            edge_type="measures",
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

        targets = self.graph.element_nodes("objective") or self.graph.section_nodes("objective")
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
        for obj in self.graph.section_nodes("objective"):
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
        return violations

    # ── Check 3: every objective has ≥1 activity supporting it ───────────────
    def _check_activity_support(self) -> list[VerifierViolation]:
        # Only flag this if we have activity nodes (not in single-agent mode where
        # activities are embedded inside the design section)
        if not self.graph.get_nodes("activity"):
            return []
        return self._coverage_violations(
            edge_type="supports",
            violation_type="activity_support",
            severity="warning",
            message_tpl="Objective '{lo}' has no learning activity explicitly supporting it.",
            repair_hint="Create a learning activity that explicitly supports this objective and add a 'supports' edge.",
        )

    # ── Check 4: assessment rubric consistency ───────────────────────────────
    def _check_rubric_consistency(self) -> list[VerifierViolation]:
        violations: list[VerifierViolation] = []
        for node in self.graph.section_nodes("assessment"):
            for item in node["data"].get("assessment_tools", []) or []:
                if not isinstance(item, dict):
                    continue
                item_id = item.get("item_id", "?")
                if not item.get("aligned_objective"):
                    violations.append(VerifierViolation(
                        node_id=node["id"],
                        edge_type="measures",
                        violation_type="rubric_consistency",
                        severity="error",
                        message=f"Assessment item '{item_id}' has no aligned_objective.",
                        repair_hint="Set aligned_objective to the LO id this item measures.",
                        metadata={"item_id": item_id},
                    ))
                if str(item.get("type", "")).lower() in ("performance_task", "performance", "project", "rubric"):
                    criteria = str(item.get("scoring_criteria") or item.get("scoring_rubric") or "").strip()
                    lowered = criteria.lower()
                    is_vague = (
                        not criteria
                        or (
                            any(term in lowered for term in _VAGUE_RUBRIC_TERMS)
                            and not any(term in lowered for term in _OBSERVABLE_TERMS)
                        )
                    )
                    if is_vague:
                        violations.append(VerifierViolation(
                            node_id=node["id"],
                            edge_type="measures",
                            violation_type="rubric_consistency",
                            severity="warning",
                            message=f"Performance item '{item_id}' lacks an observable scoring rubric.",
                            repair_hint="Replace vague language with observable, scorable criteria.",
                            metadata={"item_id": item_id, "scoring_criteria": criteria},
                        ))
        return violations

    # ── Check 5: delivery feasibility against the brief's constraints ─────────
    def _check_feasibility(self, design_brief: DesignBrief | None) -> list[VerifierViolation]:
        if design_brief is None:
            return []
        total_hours = _duration_hours(design_brief)
        if total_hours <= 0:
            return []
        modules: list = []
        sessions: list = []
        for node in self.graph.section_nodes("objective"):
            modules += node["data"].get("content_structure", {}).get("modules", []) or []
        for node in self.graph.section_nodes("activity") + self.graph.section_nodes("material"):
            guide = node["data"].get("instructor_guide", {})
            if isinstance(guide, dict):
                sessions += guide.get("session_guides", []) or []
        load_units = len(modules) + len(sessions)
        # Heuristic: each module/session needs ~1.5h. Flag only clear overload.
        if load_units and load_units * 1.5 > total_hours * 2:
            return [VerifierViolation(
                node_id="constraint_0",
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
        for node in self.graph.section_nodes("constraint"):
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
        objective_nodes = self.graph.section_nodes("objective")
        if not objective_nodes:
            return []
        evaluates_edges = self.graph.get_edges("evaluates")
        evaluated_targets = {e["target"] for e in evaluates_edges if not e.get("stale")}
        evaluated_evidence = {e.get("evidence") for e in evaluates_edges if not e.get("stale")}
        # Summative tools that name an aligned objective also count as evidence.
        for node in self.graph.section_nodes("evaluation"):
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
                    edge_type="evaluates",
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

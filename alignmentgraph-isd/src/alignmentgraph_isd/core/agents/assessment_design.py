from __future__ import annotations
from ..graph import NodeType
from ..schema import DesignBrief
from .. import alignment
from .base import BaseISDAgent, _format_design_brief, parse_json_response

_SYSTEM = """\
You are an expert instructional designer creating assessment instruments (ADDIE Development phase).

Given a training scenario, its learning objectives, and its assessment plan (diagnostic/formative/
summative), produce ONLY valid JSON with this EXACT schema:
{
  "assessment_tools": [
    {"item_id": "AT-01", "type": "multiple_choice", "question": "<question>", "aligned_objective": "LO-01", "plan_category": "summative", "scoring_criteria": "<criteria>"},
    {"item_id": "AT-02", "type": "multiple_choice", "question": "<question>", "aligned_objective": "LO-02", "plan_category": "summative", "scoring_criteria": "<criteria>"},
    {"item_id": "AT-03", "type": "multiple_choice", "question": "<question>", "aligned_objective": "LO-03", "plan_category": "diagnostic", "scoring_criteria": "<criteria>"},
    {"item_id": "AT-04", "type": "short_answer", "question": "<question>", "aligned_objective": "LO-03", "plan_category": "formative", "scoring_criteria": "<criteria>"},
    {"item_id": "AT-05", "type": "short_answer", "question": "<question>", "aligned_objective": "LO-04", "plan_category": "formative", "scoring_criteria": "<criteria>"},
    {"item_id": "AT-06", "type": "performance_task", "question": "<question>", "aligned_objective": "LO-04", "plan_category": "summative", "scoring_criteria": "<criteria>"},
    {"item_id": "AT-07", "type": "performance_task", "question": "<question>", "aligned_objective": "LO-05", "plan_category": "summative", "scoring_criteria": "<criteria>"},
    {"item_id": "AT-08", "type": "multiple_choice", "question": "<question>", "aligned_objective": "LO-01", "plan_category": "diagnostic", "scoring_criteria": "<criteria>"},
    {"item_id": "AT-09", "type": "short_answer", "question": "<question>", "aligned_objective": "LO-02", "plan_category": "formative", "scoring_criteria": "<criteria>"},
    {"item_id": "AT-10", "type": "performance_task", "question": "<question>", "aligned_objective": "LO-05", "plan_category": "summative", "scoring_criteria": "<criteria>"}
  ],
  "expert_review": {
    "reviewers": ["<SME reviewer>", "<instructional designer reviewer>"],
    "review_criteria": ["<criterion1>", "<criterion2>", "<criterion3>", "<criterion4>", "<criterion5>"],
    "feedback_summary": "<summary of expected feedback and validation>",
    "revisions_made": ["<revision1>", "<revision2>"]
  }
}

Must include at least 10 assessment items distributed across difficulty levels (easy/medium/hard).
Every learning objective must have at least one assessment item, and any Apply-or-higher objective
must be measured by a performance_task or short_answer/constructed-response item, never
multiple_choice/true_false alone. ``plan_category`` must name one of the assessment plan's own
diagnostic/formative/summative categories that this item realizes.
Output ONLY the JSON object, no markdown, no explanation.\
"""


class AssessmentDesignAgent(BaseISDAgent):
    # R3/R6 are the alignment-tier coverage checks (gated by enable_alignment_graph);
    # rubric_consistency/bloom_mismatch are content-quality checks that always run.
    OWNED_VIOLATION_TYPES = frozenset({"R3", "R6", "rubric_consistency", "bloom_mismatch"})

    def run(self, design_brief: DesignBrief) -> None:
        prompt = _format_design_brief(design_brief)
        if self._graph_coordination:
            objective_nodes = self.graph.element_nodes(NodeType.OBJECTIVE)
            plan_node = self.graph.get_node(self.graph.section_id("assessment_plan"))
            prior_ctx = self._element_context(objective_nodes + ([plan_node] if plan_node else []))
        else:
            prior_ctx = self._graph_context([NodeType.OBJECTIVE, "assessment_plan"])
        user_content = prompt
        if prior_ctx:
            user_content = f"=== LEARNING OBJECTIVES + ASSESSMENT PLAN ===\n{prior_ctx}\n\n=== SCENARIO ===\n{prompt}"
        user_content = self._with_retrieval(design_brief, "assessment_design", user_content)
        messages = [
            {"role": "system", "content": _SYSTEM},
            {"role": "user", "content": user_content},
        ]
        response = self._call_llm(messages)
        parsed = parse_json_response(response)
        # NO deterministic coverage patch here: R3 gaps are the alignment
        # tier's job (verifier surfaces them -> _repair_alignment_coverage
        # fixes them, full arm only). Patching at generation time ran in every
        # ablation arm and silently equalized wo_graph/wo_ma with full
        # on assessment coverage — leaking the graph mechanism into the arms
        # that ablate it, and hiding the gap count the RQ2 story reports.
        node_id = self.graph.section_id(NodeType.ASSESSMENT)
        self.graph.add_node(NodeType.ASSESSMENT, node_id, parsed)
        self.trajectory.log_node_edit("add", node_id, NodeType.ASSESSMENT)

        # Element decomposition + edge establishment are the alignment graph.
        # The wo-graph arm ablates them entirely (section blob only).
        if self._graph_coordination:
            item_ids = self._decompose_elements("assessment", parsed.get("assessment_tools", []), id_field="item_id")
            for iid in item_ids:
                self.trajectory.log_node_edit("add", iid, "assessment")
            alignment.match_id(self.graph, "R3", target_node_type=NodeType.OBJECTIVE, field="aligned_objective")
            alignment.match_r6_realizes(self.graph)
        self.trajectory.log_step("AssessmentDesignAgent", "design_assessments", prompt[:200], response[:200] if response else "")

    def repair(self, violations: list) -> list:
        remaining = []
        item_violations = []
        coverage_violations = []
        for violation in violations:
            vtype = getattr(violation, "violation_type", "")
            if vtype in ("rubric_consistency", "bloom_mismatch"):
                item_violations.append(violation)
            elif vtype in ("R3", "R6"):
                coverage_violations.append(violation)
            else:
                remaining.append(violation)
        if item_violations:
            self._repair_assessment_items(item_violations)
        if coverage_violations:
            self._repair_alignment_coverage(coverage_violations)
        return remaining

    def _repair_alignment_coverage(self, violations: list) -> None:
        """Resolve R3 (measures) / R6 (realizes) gaps: either a dangling item
        reference (fix it) or an uncovered objective (add an item for it).
        Re-establishes edges afterward so the graph reflects the fix."""
        node_id = self.graph.section_id(NodeType.ASSESSMENT)
        assessment = self.graph.get_node(node_id)
        if not assessment:
            assessment = {"data": {"assessment_tools": [], "expert_review": {}, "repaired": True}}
            self.graph.add_node(NodeType.ASSESSMENT, node_id, assessment["data"])
            self.trajectory.log_node_edit("add", node_id, NodeType.ASSESSMENT)
        tools = [
            dict(item) if isinstance(item, dict) else item
            for item in assessment["data"].get("assessment_tools", []) or []
        ]
        objective_node = self.graph.get_node(self.graph.section_id(NodeType.OBJECTIVE))
        lo_map = {
            str(lo["id"]): lo
            for lo in (objective_node["data"].get("learning_objectives", []) if objective_node else [])
            if isinstance(lo, dict) and lo.get("id")
        }
        plan_node = self.graph.get_node(self.graph.section_id("assessment_plan"))
        plan_categories = [
            cat for cat in alignment._ASSESSMENT_PLAN_CATEGORIES
            if plan_node and plan_node["data"].get(cat)
        ] or ["summative"]

        repaired_ids: list[str] = []
        for violation in violations:
            md = violation.metadata
            lo_id = str(md.get("lo_id") or "")
            item_id = str(md.get("item_id") or "")
            if lo_id:
                # Uncovered objective: add a new item measuring it.
                new_item_id = f"AT-R-{lo_id}"
                tools.append({
                    "item_id": new_item_id,
                    "type": "performance_task",
                    "question": f"Demonstrate the target skill for {lo_id}: {lo_map.get(lo_id, {}).get('statement', '')}",
                    "aligned_objective": lo_id,
                    "plan_category": plan_categories[0],
                    "scoring_criteria": self._OBSERVABLE_RUBRIC,
                    "difficulty": "hard",
                    "repaired": True,
                })
                repaired_ids.append(new_item_id)
            elif item_id:
                item = next((t for t in tools if isinstance(t, dict) and str(t.get("item_id")) == item_id), None)
                if not item:
                    continue
                aligned = str(item.get("aligned_objective") or "")
                if lo_map and aligned not in lo_map:
                    question = str(item.get("question", "")).lower()
                    item["aligned_objective"] = next(
                        (lo for lo in lo_map if lo.lower() in question), next(iter(lo_map), aligned)
                    )
                if str(item.get("plan_category", "")).lower() not in alignment._ASSESSMENT_PLAN_CATEGORIES:
                    item["plan_category"] = plan_categories[0]
                item["repaired"] = True
                repaired_ids.append(item_id)

        self.graph.update_node(node_id, {"assessment_tools": tools, "repaired": True})
        for item in tools:
            if isinstance(item, dict) and item.get("item_id"):
                self.graph.add_element_node("assessment", str(item["item_id"]), dict(item))
        alignment.match_id(self.graph, "R3", target_node_type=NodeType.OBJECTIVE, field="aligned_objective")
        alignment.match_r6_realizes(self.graph)
        self._log_repair(node_id, violation_type=violations[0].violation_type, repaired_fields=["assessment_tools"])
        self.trajectory.log_step(
            "AssessmentDesignAgent",
            "repair_alignment_coverage",
            "; ".join(v.message for v in violations)[:200],
            f"Fixed/added items for {', '.join(repaired_ids) or 'existing coverage'}.",
        )

    _OBSERVABLE_RUBRIC = (
        "Analytic rubric, 4 levels (0-3) per criterion: task completed with at least 80% "
        "accuracy; target concepts applied correctly; justification cites observable evidence."
    )

    def _repair_assessment_items(self, violations: list) -> None:
        """Resolve rubric_consistency / bloom_mismatch findings on assessment items.

        One LLM call revises the flagged items; a deterministic fallback then
        resolves anything the model left unfixed (dangling references, missing
        or vague criteria, recognition-only coverage of higher-order LOs), so
        the verify-repair loop always converges.
        """
        node_id = self.graph.section_id(NodeType.ASSESSMENT)
        assessment = self.graph.get_node(node_id)
        if not assessment:
            return
        from .pedagogical_verifier import _OBSERVABLE_TERMS, _VAGUE_RUBRIC_TERMS
        from ..alignment import item_type_capability, _RECALL_CAPABILITY_CEILING as RECALL_CAPABILITY_CEILING

        tools = [
            dict(item) if isinstance(item, dict) else item
            for item in assessment["data"].get("assessment_tools", []) or []
        ]
        objective_node = self.graph.get_node(self.graph.section_id(NodeType.OBJECTIVE))
        lo_map = {}
        if objective_node:
            lo_map = {
                str(lo["id"]): lo
                for lo in objective_node["data"].get("learning_objectives", []) or []
                if isinstance(lo, dict) and lo.get("id")
            }

        flagged_item_ids = {
            str(v.metadata.get("item_id"))
            for v in violations if v.metadata.get("item_id")
        }
        for v in violations:
            flagged_item_ids.update(str(i) for i in v.metadata.get("item_ids", []) or [])

        # LLM pass: revise the flagged items in place.
        revised = self._llm_item_revision(violations, tools, flagged_item_ids, lo_map)
        for rev in revised.get("assessment_tools", []) or []:
            if not isinstance(rev, dict) or str(rev.get("item_id")) not in flagged_item_ids:
                continue
            item = next((t for t in tools if isinstance(t, dict) and str(t.get("item_id")) == str(rev["item_id"])), None)
            if not item:
                continue
            for field in ("type", "question", "scoring_criteria"):
                if rev.get(field):
                    item[field] = rev[field]
            if rev.get("aligned_objective") and (not lo_map or str(rev["aligned_objective"]) in lo_map):
                item["aligned_objective"] = str(rev["aligned_objective"])

        # Deterministic fallback, violation by violation.
        def _criteria_ok(item: dict) -> bool:
            criteria = str(item.get("scoring_criteria") or item.get("scoring_rubric") or "").strip()
            lowered = criteria.lower()
            if not criteria:
                return False
            if str(item.get("type", "")).lower() in ("performance_task", "performance", "project", "rubric"):
                return len(criteria) >= 40 and not (
                    any(term in lowered for term in _VAGUE_RUBRIC_TERMS)
                    and not any(term in lowered for term in _OBSERVABLE_TERMS)
                )
            return True

        lo_ids = list(lo_map)
        for violation in violations:
            md = violation.metadata
            if violation.violation_type == "rubric_consistency":
                item = next(
                    (t for t in tools if isinstance(t, dict) and str(t.get("item_id")) == str(md.get("item_id"))),
                    None,
                )
                if not item:
                    continue
                aligned = str(item.get("aligned_objective") or "")
                if lo_ids and aligned not in lo_map:
                    question = str(item.get("question", "")).lower()
                    item["aligned_objective"] = next(
                        (lo_id for lo_id in lo_ids if lo_id.lower() in question), lo_ids[0]
                    )
                if not _criteria_ok(item):
                    item["scoring_criteria"] = self._OBSERVABLE_RUBRIC
                item["repaired"] = True
            elif violation.violation_type == "bloom_mismatch":
                lo_id = str(md.get("lo_id") or "")
                if not lo_id:
                    continue
                capability = max(
                    (
                        item_type_capability(t.get("type", ""))
                        for t in tools
                        if isinstance(t, dict) and str(t.get("aligned_objective")) == lo_id
                    ),
                    default=0,
                )
                if capability > RECALL_CAPABILITY_CEILING:
                    continue
                statement = str(lo_map.get(lo_id, {}).get("statement", ""))
                tools.append({
                    "item_id": f"AT-P-{lo_id}",
                    "type": "performance_task",
                    "question": f"Perform a realistic task that demonstrates {lo_id}: {statement}",
                    "aligned_objective": lo_id,
                    "scoring_criteria": self._OBSERVABLE_RUBRIC,
                    "difficulty": "hard",
                    "repaired": True,
                })

        self.graph.update_node(node_id, {"assessment_tools": tools, "repaired": True})
        for item in tools:
            if isinstance(item, dict) and item.get("item_id"):
                self.graph.add_element_node("assessment", str(item["item_id"]), dict(item))
        alignment.match_id(self.graph, "R3", target_node_type=NodeType.OBJECTIVE, field="aligned_objective")
        alignment.match_r6_realizes(self.graph)
        self._log_repair(node_id, violation_type=violations[0].violation_type, repaired_fields=["assessment_tools"])
        self.trajectory.log_node_edit("update", node_id, NodeType.ASSESSMENT)
        self.trajectory.log_step(
            "AssessmentDesignAgent",
            "repair_assessment_items",
            "; ".join(v.message for v in violations)[:200],
            f"Revised {len(flagged_item_ids)} flagged item(s).",
        )

    def _llm_item_revision(self, violations: list, tools: list, flagged_item_ids: set, lo_map: dict) -> dict:
        import json

        findings = [
            {
                "type": v.violation_type,
                "item_id": v.metadata.get("item_id"),
                "lo_id": v.metadata.get("lo_id"),
                "message": v.message,
                "hint": v.repair_hint,
            }
            for v in violations
        ]
        flagged_items = [
            t for t in tools if isinstance(t, dict) and str(t.get("item_id")) in flagged_item_ids
        ]
        objectives = [
            {"id": lo_id, "level": lo.get("level"), "statement": lo.get("statement")}
            for lo_id, lo in lo_map.items()
        ]
        system = (
            "You are an expert instructional designer revising assessment items to resolve "
            "verifier findings. Return ONLY valid JSON with this schema:\n"
            '{"assessment_tools": [{"item_id": "<existing id>", "type": "<type>", '
            '"question": "<question>", "aligned_objective": "<LO id>", "scoring_criteria": "<criteria>"}]}\n'
            "Rules: keep item ids; point every aligned_objective at an existing LO id; write "
            "observable, scorable criteria (point scales, thresholds, behavior anchors); use a "
            "constructed-response or performance format when the finding demands a higher-order "
            "format. Include only the revised items."
        )
        user = json.dumps(
            {"findings": findings, "flagged_items": flagged_items, "objectives": objectives},
            ensure_ascii=False,
        )
        response = self._call_llm(
            [{"role": "system", "content": system}, {"role": "user", "content": user}],
            max_retries=0,
        )
        return parse_json_response(response, warn=False) or {}



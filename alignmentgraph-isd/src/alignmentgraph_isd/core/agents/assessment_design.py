from __future__ import annotations
from ..graph import EdgeType, NodeType
from ..schema import DesignBrief
from .base import BaseISDAgent, _format_design_brief, parse_json_response

_SYSTEM = """\
You are an expert instructional designer creating assessment instruments (ADDIE Development phase).

Given a training scenario, produce ONLY valid JSON with this EXACT schema:
{
  "assessment_tools": [
    {"item_id": "AT-01", "type": "multiple_choice", "question": "<question>", "aligned_objective": "LO-01", "scoring_criteria": "<criteria>"},
    {"item_id": "AT-02", "type": "multiple_choice", "question": "<question>", "aligned_objective": "LO-02", "scoring_criteria": "<criteria>"},
    {"item_id": "AT-03", "type": "multiple_choice", "question": "<question>", "aligned_objective": "LO-03", "scoring_criteria": "<criteria>"},
    {"item_id": "AT-04", "type": "short_answer", "question": "<question>", "aligned_objective": "LO-03", "scoring_criteria": "<criteria>"},
    {"item_id": "AT-05", "type": "short_answer", "question": "<question>", "aligned_objective": "LO-04", "scoring_criteria": "<criteria>"},
    {"item_id": "AT-06", "type": "performance_task", "question": "<question>", "aligned_objective": "LO-04", "scoring_criteria": "<criteria>"},
    {"item_id": "AT-07", "type": "performance_task", "question": "<question>", "aligned_objective": "LO-05", "scoring_criteria": "<criteria>"},
    {"item_id": "AT-08", "type": "multiple_choice", "question": "<question>", "aligned_objective": "LO-01", "scoring_criteria": "<criteria>"},
    {"item_id": "AT-09", "type": "short_answer", "question": "<question>", "aligned_objective": "LO-02", "scoring_criteria": "<criteria>"},
    {"item_id": "AT-10", "type": "performance_task", "question": "<question>", "aligned_objective": "LO-05", "scoring_criteria": "<criteria>"}
  ],
  "expert_review": {
    "reviewers": ["<SME reviewer>", "<instructional designer reviewer>"],
    "review_criteria": ["<criterion1>", "<criterion2>", "<criterion3>", "<criterion4>", "<criterion5>"],
    "feedback_summary": "<summary of expected feedback and validation>",
    "revisions_made": ["<revision1>", "<revision2>"]
  }
}

Must include at least 10 assessment items distributed across difficulty levels (easy/medium/hard).
Every learning objective LO-01 through LO-05 must have at least one assessment item, and LO-05 must be measured by a performance_task or rubric-based peer-feedback task.
Output ONLY the JSON object, no markdown, no explanation.\
"""




class AssessmentDesignAgent(BaseISDAgent):
    OWNED_VIOLATION_TYPES = frozenset({"coverage", "rubric_consistency", "bloom_mismatch"})

    def run(self, design_brief: DesignBrief, context_pack: dict) -> None:
        prompt = _format_design_brief(design_brief)
        # Graph-context retrieval (core, not RAG): inject prior G_t nodes into this prompt
        prior_ctx = self._graph_context([NodeType.NEEDS_CONTEXT, NodeType.OBJECTIVE])
        user_content = prompt
        if prior_ctx:
            user_content = f"=== ANALYSIS + DESIGN RESULTS (from prior agents) ===\n{prior_ctx}\n\n=== SCENARIO ===\n{prompt}"
        pack_ctx = self._context_pack_text(context_pack)
        if pack_ctx:
            user_content = f"=== RETRIEVED CONTEXT PACK ===\n{pack_ctx}\n\n{user_content}"
        user_content = self._with_retrieval(design_brief, "assessment_design", user_content)
        messages = [
            {"role": "system", "content": _SYSTEM},
            {"role": "user", "content": user_content},
        ]
        response = self._call_llm(messages)
        parsed = parse_json_response(response)
        node_id = self.graph.section_id(NodeType.ASSESSMENT)
        if self.graph.get_nodes(NodeType.OBJECTIVE):
            objective_data = self.graph.get_nodes(NodeType.OBJECTIVE)[0]["data"]
            self._ensure_assessment_coverage(parsed, objective_data.get("learning_objectives", []))
        self.graph.add_node(NodeType.ASSESSMENT, node_id, parsed)
        self.trajectory.log_node_edit("add", node_id, NodeType.ASSESSMENT)
        # No per-item element nodes: assessment stays section-level. Item→LO mapping
        # is kept as data (assessment_tools[i].aligned_objective) and coverage is
        # checked at the objective element node, so assessment:AT-* would be unused.
        if self.graph.get_nodes(NodeType.OBJECTIVE):
            obj_id = self.graph.get_nodes(NodeType.OBJECTIVE)[0]["id"]
            objective_data = self.graph.get_nodes(NodeType.OBJECTIVE)[0]["data"]
            lo_ids = [
                lo.get("id")
                for lo in objective_data.get("learning_objectives", [])
                if isinstance(lo, dict) and lo.get("id")
            ]
            aligned_ids = {
                item.get("aligned_objective")
                for item in parsed.get("assessment_tools", [])
                if isinstance(item, dict) and item.get("aligned_objective")
            }
            for lo_id in sorted(set(aligned_ids).union(lo_ids)):
                rationale = f"Assessment tool set includes an item aligned to {lo_id}."
                self.graph.add_edge(
                    EdgeType.MEASURES,
                    node_id,
                    obj_id,
                    evidence=lo_id,
                    rationale=rationale,
                    verified=True,
                )
                self._add_element_edge(EdgeType.MEASURES, node_id, lo_id, rationale=rationale)
                self.trajectory.log_edge_edit("add", node_id, obj_id, EdgeType.MEASURES, lo_id, rationale)
        self.trajectory.log_step("AssessmentDesignAgent", "design_assessments", prompt[:200], response[:200] if response else "")

    def repair(self, violations: list) -> list:
        remaining = []
        item_violations = []
        for violation in violations:
            vtype = getattr(violation, "violation_type", "")
            if vtype in ("rubric_consistency", "bloom_mismatch"):
                item_violations.append(violation)
            elif vtype == "coverage" or getattr(violation, "edge_type", "") == EdgeType.MEASURES:
                self._repair_assessment_coverage(violation)
            else:
                remaining.append(violation)
        if item_violations:
            self._repair_assessment_items(item_violations)
        return remaining

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
        from .pedagogical_verifier import (
            _ITEM_TYPE_CAPABILITY,
            _OBSERVABLE_TERMS,
            _RECALL_CAPABILITY_CEILING,
            _VAGUE_RUBRIC_TERMS,
        )

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
                        _ITEM_TYPE_CAPABILITY.get(str(t.get("type", "")).lower(), 6)
                        for t in tools
                        if isinstance(t, dict) and str(t.get("aligned_objective")) == lo_id
                    ),
                    default=0,
                )
                if capability > _RECALL_CAPABILITY_CEILING:
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
                rationale = f"AssessmentDesignAgent repair added a performance item for {lo_id}."
                self._add_element_edge(EdgeType.MEASURES, node_id, lo_id, rationale=rationale)

        self.graph.update_node(node_id, {"assessment_tools": tools, "repaired": True})
        self.graph.clear_stale(node_id)
        for violation in violations:
            self.graph.mark_repaired(node_id, violation.message)
        impact = self._invalidate_impacted(
            node_id,
            "Assessment item repair changed instruments; dependent practice and evaluation plans must be refreshed.",
            action="repair_cascade",
            changed_fields=["assessment_tools"],
            violation_type=violations[0].violation_type,
        )
        self.trajectory.log_node_edit("update", node_id, NodeType.ASSESSMENT)
        self.trajectory.log_step(
            "AssessmentDesignAgent",
            "repair_assessment_items",
            "; ".join(v.message for v in violations)[:200],
            (
                f"Revised {len(flagged_item_ids)} flagged item(s); "
                f"invalidated nodes={len(impact['nodes'])} edges={len(impact['edges'])}."
            ),
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

    def _ensure_assessment_coverage(self, parsed: dict, objectives: list) -> None:
        tools = parsed.setdefault("assessment_tools", [])
        if not isinstance(tools, list):
            parsed["assessment_tools"] = []
            tools = parsed["assessment_tools"]

        covered = {
            item.get("aligned_objective")
            for item in tools
            if isinstance(item, dict) and item.get("aligned_objective")
        }

        for lo in objectives:
            if not isinstance(lo, dict):
                continue
            lo_id = lo.get("id")
            if not lo_id or lo_id in covered:
                continue
            tools.append({
                "item_id": f"AT-R-{lo_id}",
                "type": "performance_task",
                "question": f"Use scenario evidence to demonstrate and evaluate mastery of {lo_id}: {lo.get('statement', '')}",
                "aligned_objective": lo_id,
                "scoring_criteria": "Rubric scores observable performance, communication accuracy, peer-feedback quality, and transfer to a realistic scenario.",
                "difficulty": "hard",
                "coverage_repair": True,
            })
            covered.add(lo_id)

    def _repair_assessment_coverage(self, violation) -> None:
        objective = self.graph.get_node(violation.node_id)
        if not objective:
            return

        assessment = self.graph.get_node(self.graph.section_id(NodeType.ASSESSMENT))
        if assessment:
            assessment_data = assessment["data"]
        else:
            assessment_data = {"assessment_tools": [], "expert_review": {}, "repaired": True}
            self.graph.add_node(NodeType.ASSESSMENT, self.graph.section_id(NodeType.ASSESSMENT), assessment_data, repair_history=[violation.message])
            self.trajectory.log_node_edit("add", self.graph.section_id(NodeType.ASSESSMENT), NodeType.ASSESSMENT)

        assessment_tools = assessment_data.setdefault("assessment_tools", [])
        if not isinstance(assessment_tools, list):
            assessment_data["assessment_tools"] = []
            assessment_tools = assessment_data["assessment_tools"]

        covered = {
            item.get("aligned_objective")
            for item in assessment_tools
            if isinstance(item, dict) and item.get("aligned_objective")
        }
        repaired_ids: list[str] = []
        for lo in objective["data"].get("learning_objectives", []):
            if not isinstance(lo, dict):
                continue
            lo_id = lo.get("id")
            if not lo_id or lo_id in covered:
                continue
            item_id = f"AT-R-{lo_id}"
            assessment_tools.append({
                "item_id": item_id,
                "type": "performance_task",
                "question": f"Demonstrate the target skill for {lo_id}: {lo.get('statement', '')}",
                "aligned_objective": lo_id,
                "scoring_criteria": "Score accuracy, context appropriateness, learner independence, and evidence of transfer.",
                "difficulty": "hard",
                "repaired": True,
            })
            rationale = f"AssessmentDesignAgent repair added {item_id} to measure {lo_id}."
            self.graph.add_edge(
                EdgeType.MEASURES,
                self.graph.section_id(NodeType.ASSESSMENT),
                violation.node_id,
                evidence=lo_id,
                rationale=rationale,
                verified=True,
            )
            self._add_element_edge(EdgeType.MEASURES, self.graph.section_id(NodeType.ASSESSMENT), lo_id, rationale=rationale)
            self.trajectory.log_edge_edit("add", self.graph.section_id(NodeType.ASSESSMENT), violation.node_id, EdgeType.MEASURES, lo_id, rationale)
            covered.add(lo_id)
            repaired_ids.append(lo_id)

        self.graph.update_node(self.graph.section_id(NodeType.ASSESSMENT), {"assessment_tools": assessment_tools, "repaired": True})
        self.graph.clear_stale(self.graph.section_id(NodeType.ASSESSMENT))
        self.graph.mark_repaired(self.graph.section_id(NodeType.ASSESSMENT), violation.message)
        impact = self._invalidate_impacted(
            self.graph.section_id(NodeType.ASSESSMENT),
            "Assessment repair changed evidence coverage; dependent practice and evaluation plans must be refreshed.",
            action="repair_cascade",
            changed_fields=["assessment_tools", "measures_edges"],
            violation_type=getattr(violation, "violation_type", "coverage"),
        )
        self.trajectory.log_step(
            "AssessmentDesignAgent",
            "repair_assessment_coverage",
            violation.message,
            (
                f"Added assessment coverage for {', '.join(repaired_ids) or 'existing objectives'}; "
                f"invalidated nodes={len(impact['nodes'])} edges={len(impact['edges'])}."
            ),
        )

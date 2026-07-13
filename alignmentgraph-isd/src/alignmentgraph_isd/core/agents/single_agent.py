from __future__ import annotations
from ..graph import EdgeType, NodeType
from ..schema import DesignBrief
from .base import BaseISDAgent, _format_design_brief, parse_json_response

_SYSTEM = """\
You are an expert instructional designer. Given a training scenario, produce a COMPLETE, DETAILED ADDIE instructional design.

Return ONLY valid JSON with EXACTLY this nested schema:
{
  "analysis": {
    "needs_analysis": {
      "problem_definition": "<2-3 sentences on performance gap>",
      "gap_analysis": ["<gap1>", "<gap2>", "<gap3>"],
      "performance_analysis": "<2-3 sentences on instructional solution>",
      "priority_matrix": {"high": ["<item>"], "medium": ["<item>"], "low": ["<item>"]}
    },
    "learner_analysis": {
      "target_audience": "<audience description>",
      "characteristics": ["<char1>", "<char2>", "<char3>", "<char4>", "<char5>"],
      "prior_knowledge": "<prior knowledge>",
      "learning_preferences": ["<pref1>", "<pref2>", "<pref3>"],
      "motivation": "<motivation>",
      "challenges": ["<challenge1>", "<challenge2>", "<challenge3>"]
    },
    "context_analysis": {
      "environment": "<learning environment>",
      "duration": "<total time>",
      "constraints": ["<constraint1>", "<constraint2>", "<constraint3>"],
      "resources": ["<resource1>", "<resource2>"],
      "technical_requirements": ["<tech1>", "<tech2>"]
    },
    "task_analysis": {
      "main_topics": ["<topic1>", "<topic2>", "<topic3>"],
      "subtopics": ["<sub1>", "<sub2>", "<sub3>", "<sub4>"],
      "prerequisites": ["<prereq1>", "<prereq2>"],
      "review_summary": "<synthesis in 3-4 sentences>"
    }
  },
  "design": {
    "learning_objectives": [
      {"id": "LO-01", "level": "Remember", "statement": "<objective>", "bloom_verb": "<verb>", "measurable": true},
      {"id": "LO-02", "level": "Understand", "statement": "<objective>", "bloom_verb": "<verb>", "measurable": true},
      {"id": "LO-03", "level": "Apply", "statement": "<objective>", "bloom_verb": "<verb>", "measurable": true},
      {"id": "LO-04", "level": "Analyze", "statement": "<objective>", "bloom_verb": "<verb>", "measurable": true},
      {"id": "LO-05", "level": "Evaluate", "statement": "<objective>", "bloom_verb": "<verb>", "measurable": true}
    ],
    "assessment_plan": {
      "diagnostic": ["<diagnostic1>", "<diagnostic2>"],
      "formative": ["<formative1>", "<formative2>"],
      "summative": ["<summative1>", "<summative2>"]
    },
    "content_structure": {
      "modules": ["<module1>", "<module2>", "<module3>"],
      "topics": ["<topic1>", "<topic2>", "<topic3>"],
      "sequencing": "<sequence rationale>"
    },
    "instructional_strategies": {
      "model": "Gagné's 9 Events",
      "sequence": [
        {"event": "Gain attention", "activity": "<activity>", "duration": "<time>", "resources": ["<resource>"]},
        {"event": "Inform learners of objectives", "activity": "<activity>", "duration": "<time>", "resources": ["<resource>"]},
        {"event": "Stimulate recall of prior learning", "activity": "<activity>", "duration": "<time>", "resources": ["<resource>"]},
        {"event": "Present content", "activity": "<activity>", "duration": "<time>", "resources": ["<resource>"]},
        {"event": "Provide learning guidance", "activity": "<activity>", "duration": "<time>", "resources": ["<resource>"]},
        {"event": "Elicit performance", "activity": "<activity>", "duration": "<time>", "resources": ["<resource>"]},
        {"event": "Provide feedback", "activity": "<activity>", "duration": "<time>", "resources": ["<resource>"]},
        {"event": "Assess performance", "activity": "<activity>", "duration": "<time>", "resources": ["<resource>"]},
        {"event": "Enhance retention and transfer", "activity": "<activity>", "duration": "<time>", "resources": ["<resource>"]}
      ],
      "methods": ["<method1>", "<method2>", "<method3>"],
      "rationale": "<strategy rationale>"
    },
    "non_instructional_strategies": {
      "motivation_strategies": ["<motivation1>", "<motivation2>"],
      "self_directed_learning": ["<self1>", "<self2>"],
      "support_strategies": ["<support1>", "<support2>"]
    },
    "learning_activities": [
      {"activity_name": "<name1>", "duration": "<time>", "description": "<desc>", "materials": ["<material>"]},
      {"activity_name": "<name2>", "duration": "<time>", "description": "<desc>", "materials": ["<material>"]},
      {"activity_name": "<name3>", "duration": "<time>", "description": "<desc>", "materials": ["<material>"]}
    ],
    "media_selection": [
      {"media_type": "<type>", "purpose": "<purpose>", "rationale": "<rationale>"},
      {"media_type": "<type>", "purpose": "<purpose>", "rationale": "<rationale>"}
    ],
    "storyboard": [
      {"frame_number": 1, "screen_title": "<title>", "visual_description": "<visual>", "interaction": "<interaction>", "notes": "<notes>"},
      {"frame_number": 2, "screen_title": "<title>", "visual_description": "<visual>", "interaction": "<interaction>", "notes": "<notes>"},
      {"frame_number": 3, "screen_title": "<title>", "visual_description": "<visual>", "interaction": "<interaction>", "notes": "<notes>"}
    ]
  },
  "development": {
    "learner_materials": [
      {"title": "<title>", "type": "<type>", "content": "<description>", "format": "<format>"},
      {"title": "<title>", "type": "<type>", "content": "<description>", "format": "<format>"},
      {"title": "<title>", "type": "<type>", "content": "<description>", "format": "<format>"}
    ],
    "instructor_guide": {
      "overview": "<guide overview>",
      "session_guides": [
        {"session": 1, "objectives": ["<obj>"], "activities": ["<activity>"], "notes": "<notes>"},
        {"session": 2, "objectives": ["<obj>"], "activities": ["<activity>"], "notes": "<notes>"},
        {"session": 3, "objectives": ["<obj>"], "activities": ["<activity>"], "notes": "<notes>"}
      ],
      "facilitation_tips": ["<tip1>", "<tip2>", "<tip3>"],
      "troubleshooting": ["<issue1>", "<issue2>"]
    },
    "operator_manual": {
      "system_setup": "<setup guide>",
      "operation_procedures": ["<proc1>", "<proc2>", "<proc3>"],
      "support_procedures": ["<support1>", "<support2>"],
      "escalation_process": "<escalation process>"
    },
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
      "reviewers": ["<SME1>", "<designer1>"],
      "review_criteria": ["<criterion1>", "<criterion2>", "<criterion3>", "<criterion4>", "<criterion5>"],
      "feedback_summary": "<feedback summary>",
      "revisions_made": ["<revision1>", "<revision2>"]
    }
  },
  "implementation": {
    "instructor_orientation": {
      "orientation_objectives": ["<obj1>", "<obj2>", "<obj3>"],
      "schedule": "<schedule>",
      "materials": ["<material1>", "<material2>"],
      "competency_checklist": ["<comp1>", "<comp2>", "<comp3>"]
    },
    "system_check": {
      "checklist": ["<check1>", "<check2>", "<check3>", "<check4>", "<check5>"],
      "technical_validation": "<validation>",
      "contingency_plans": ["<plan1>", "<plan2>"]
    },
    "prototype_execution": {
      "pilot_scope": "<scope>",
      "participants": "<participants>",
      "execution_log": ["<log1>", "<log2>", "<log3>"],
      "issues_encountered": ["<issue1>", "<issue2>"]
    },
    "monitoring": {
      "monitoring_criteria": ["<criterion1>", "<criterion2>", "<criterion3>"],
      "support_channels": ["<channel1>", "<channel2>"],
      "issue_resolution_log": ["<resolution1>", "<resolution2>"],
      "real_time_adjustments": ["<adjustment1>", "<adjustment2>"]
    }
  },
  "evaluation": {
    "formative": {
      "data_collection": {
        "methods": ["<method1>", "<method2>", "<method3>"],
        "learner_feedback": ["<feedback1>", "<feedback2>", "<feedback3>"],
        "performance_data": {"metric1": "<description>", "metric2": "<description>"},
        "observations": ["<observation1>", "<observation2>"]
      },
      "improvements": [
        {"issue_identified": "<issue>", "improvement_action": "<action>", "priority": "high"},
        {"issue_identified": "<issue>", "improvement_action": "<action>", "priority": "medium"},
        {"issue_identified": "<issue>", "improvement_action": "<action>", "priority": "low"}
      ]
    },
    "summative": {
      "assessment_tools": [
        {"item_id": "SA-01", "type": "comprehensive", "question": "<question>", "scoring_rubric": "<rubric>"},
        {"item_id": "SA-02", "type": "comprehensive", "question": "<question>", "scoring_rubric": "<rubric>"},
        {"item_id": "SA-03", "type": "comprehensive", "question": "<question>", "scoring_rubric": "<rubric>"},
        {"item_id": "SA-04", "type": "performance", "question": "<question>", "scoring_rubric": "<rubric>"},
        {"item_id": "SA-05", "type": "performance", "question": "<question>", "scoring_rubric": "<rubric>"}
      ],
      "effectiveness_analysis": {
        "learning_outcomes": {"achievement_rate": "85%", "details": "<outcome analysis>"},
        "goal_achievement_rate": "<rate>",
        "statistical_analysis": "<analysis>",
        "recommendations": ["<rec1>", "<rec2>", "<rec3>"]
      },
      "adoption_decision": {
        "decision": "adopt",
        "rationale": "<rationale>",
        "conditions": ["<condition1>", "<condition2>"],
        "stakeholder_approval": "<approval status>"
      }
    },
    "improvement_plan": {
      "feedback_summary": "<summary>",
      "improvement_areas": ["<area1>", "<area2>", "<area3>"],
      "action_items": ["<action1>", "<action2>", "<action3>"],
      "feedback_loop": "<feedback loop>",
      "next_iteration_goals": ["<goal1>", "<goal2>"]
    }
  }
}

CRITICAL:
- Replace ALL placeholder values (<...>) with specific, detailed content tailored to the scenario
- instructional_strategies.sequence MUST contain ALL 9 Gagné events in order
- learning_objectives MUST have at least 5 items spanning multiple Bloom's levels
- assessment_tools MUST have at least 10 items
- Return ONLY the JSON, no markdown fences, no explanation\
"""

_SECTION_TO_NODE = {
    "analysis": NodeType.NEEDS_CONTEXT,
    "design": NodeType.OBJECTIVE,
    "development": NodeType.ACTIVITY,
    "implementation": NodeType.IMPLEMENTATION_PLAN,
    "evaluation": NodeType.EVALUATION,
}


class SingleAgent(BaseISDAgent):
    # The single agent owns every content check it can repair holistically. Edge
    # coverage (measures/supports/evaluates) is satisfied by construction in
    # _add_alignment_edges, so those types are not listed.
    OWNED_VIOLATION_TYPES = frozenset({
        "bloom", "activity_engagement",
        "rubric_consistency", "bloom_mismatch", "evaluation_quality",
    })  # measurability is audit-only (see PedagogicalVerifierAgent._check_measurability)

    def run(self, design_brief: DesignBrief, context_pack: dict) -> None:
        prompt = _format_design_brief(design_brief)
        user_content = prompt
        pack_ctx = self._context_pack_text(context_pack)
        if pack_ctx:
            user_content = f"=== RETRIEVED CONTEXT PACK ===\n{pack_ctx}\n\n=== SCENARIO ===\n{prompt}"
        user_content = self._with_retrieval(design_brief, "full_design", user_content)
        messages = [
            {"role": "system", "content": _SYSTEM},
            {"role": "user", "content": user_content},
        ]
        raw = self._call_llm(messages)
        parsed = parse_json_response(raw)
        for section, node_type in _SECTION_TO_NODE.items():
            node_id = self.graph.section_id(node_type)
            self.graph.add_node(node_type, node_id, parsed.get(section, {}))
            self.trajectory.log_node_edit("add", node_id, node_type)
        development = parsed.get("development", {})
        if development.get("assessment_tools") or development.get("expert_review"):
            self.graph.add_node(NodeType.ASSESSMENT, self.graph.section_id(NodeType.ASSESSMENT), {
                "assessment_tools": development.get("assessment_tools", []),
                "expert_review": development.get("expert_review", {}),
            })
            self.trajectory.log_node_edit("add", self.graph.section_id(NodeType.ASSESSMENT), NodeType.ASSESSMENT)
        self._add_element_nodes(parsed)
        self._add_alignment_edges(parsed)
        self.trajectory.log_step("SingleAgent", "generate_addie", prompt[:200], raw[:200] if raw else "(empty)")

    def _add_element_nodes(self, parsed: dict) -> None:
        # Only ``objective`` is element-level: coverage is checked per learning
        # outcome. Other artifact types stay section-level (no per-item consumer).
        for lo in parsed.get("design", {}).get("learning_objectives", []) or []:
            if isinstance(lo, dict) and lo.get("id"):
                self.graph.add_element_node(NodeType.OBJECTIVE, str(lo["id"]), dict(lo))

    def _add_alignment_edges(self, parsed: dict) -> None:
        objective_node = self.graph.get_node(self.graph.section_id(NodeType.OBJECTIVE))
        if not objective_node:
            return
        objective_ids = [
            lo.get("id")
            for lo in parsed.get("design", {}).get("learning_objectives", [])
            if isinstance(lo, dict) and lo.get("id")
        ]
        assessment_source = self.graph.section_id(NodeType.ASSESSMENT) if self.graph.get_node(self.graph.section_id(NodeType.ASSESSMENT)) else self.graph.section_id(NodeType.ACTIVITY)
        for lo_id in objective_ids:
            self.graph.add_edge(
                EdgeType.MEASURES,
                assessment_source,
                self.graph.section_id(NodeType.OBJECTIVE),
                evidence=lo_id,
                rationale=f"Single-agent assessment output measures {lo_id}.",
                verified=True,
            )
            self.graph.add_edge(
                EdgeType.SUPPORTS,
                self.graph.section_id(NodeType.ACTIVITY),
                self.graph.section_id(NodeType.OBJECTIVE),
                evidence=lo_id,
                rationale=f"Single-agent learning activities support {lo_id}.",
                verified=True,
            )
            self.graph.add_edge(
                EdgeType.EVALUATES,
                self.graph.section_id(NodeType.EVALUATION),
                self.graph.section_id(NodeType.OBJECTIVE),
                evidence=lo_id,
                rationale=f"Single-agent evaluation plan evaluates {lo_id}.",
                verified=True,
            )
            self._add_element_edge(EdgeType.MEASURES, assessment_source, lo_id)
            self._add_element_edge(EdgeType.SUPPORTS, self.graph.section_id(NodeType.ACTIVITY), lo_id)
            self._add_element_edge(EdgeType.EVALUATES, self.graph.section_id(NodeType.EVALUATION), lo_id)
            self.trajectory.log_edge_edit("add", assessment_source, self.graph.section_id(NodeType.OBJECTIVE), EdgeType.MEASURES, lo_id)
            self.trajectory.log_edge_edit("add", self.graph.section_id(NodeType.ACTIVITY), self.graph.section_id(NodeType.OBJECTIVE), EdgeType.SUPPORTS, lo_id)
            self.trajectory.log_edge_edit("add", self.graph.section_id(NodeType.EVALUATION), self.graph.section_id(NodeType.OBJECTIVE), EdgeType.EVALUATES, lo_id)

    # ── Self-repair (used when multi-agent decomposition is ablated) ──────────
    # In the ``wo-ma`` arm generation is a single agent, so repair must
    # also be single-agent — routing to specialist repair agents would smuggle
    # decomposition back into the quality-control loop. This method fixes every
    # violation the single agent owns in ONE holistic LLM pass, with deterministic
    # mechanical fallbacks (shared, non-agent graph edits) guaranteeing that the
    # verify-repair loop converges.
    def repair(self, violations: list) -> list:
        if not violations:
            return []
        design_node = self.graph.get_node(self.graph.section_id(NodeType.OBJECTIVE))
        assessment_node = self.graph.get_node(self.graph.section_id(NodeType.ASSESSMENT))
        evaluation_node = self.graph.get_node(self.graph.section_id(NodeType.EVALUATION))
        design = dict(design_node["data"]) if design_node else {}
        assessment = dict(assessment_node["data"]) if assessment_node else {}
        evaluation = dict(evaluation_node["data"]) if evaluation_node else {}

        # One holistic LLM repair call (best effort; fallbacks guarantee closure).
        revised = self._llm_self_repair(violations, design, assessment, evaluation)
        if isinstance(revised.get("design"), dict):
            _merge_design(design, revised["design"])
        if isinstance(revised.get("assessment_tools"), list) and revised["assessment_tools"]:
            assessment["assessment_tools"] = revised["assessment_tools"]
        if isinstance(revised.get("evaluation"), dict):
            evaluation.update(revised["evaluation"])

        # Deterministic mechanical fallbacks, per violation type.
        _apply_design_fallbacks(design, violations)
        _apply_assessment_fallbacks(assessment, design, violations)
        _apply_evaluation_fallbacks(evaluation, violations)

        touched = []
        if design_node:
            self.graph.update_node(self.graph.section_id(NodeType.OBJECTIVE), design)
            for lo in design.get("learning_objectives", []) or []:
                if isinstance(lo, dict) and lo.get("id"):
                    self.graph.add_element_node(NodeType.OBJECTIVE, str(lo["id"]), dict(lo))
            touched.append(self.graph.section_id(NodeType.OBJECTIVE))
        if assessment_node:
            self.graph.update_node(self.graph.section_id(NodeType.ASSESSMENT), assessment)
            touched.append(self.graph.section_id(NodeType.ASSESSMENT))
        if evaluation_node:
            self.graph.update_node(self.graph.section_id(NodeType.EVALUATION), evaluation)
            touched.append(self.graph.section_id(NodeType.EVALUATION))

        for node_id in touched:
            self.graph.clear_stale(node_id)
            self.graph.mark_repaired(node_id, "SingleAgent self-repair")
        impact = {"nodes": [], "edges": []}
        if touched:
            impact = self._invalidate_impacted(
                touched[0],
                "Single-agent self-repair revised the flagged sections; downstream alignment refreshed.",
                action="repair_cascade",
                changed_fields=["learning_objectives", "assessment_tools", "formative"],
                violation_type=getattr(violations[0], "violation_type", "content"),
            )
        self.trajectory.log_node_edit("update", self.graph.section_id(NodeType.OBJECTIVE), NodeType.OBJECTIVE)
        self.trajectory.log_step(
            "SingleAgent",
            "self_repair",
            "; ".join(getattr(v, "message", "") for v in violations)[:200],
            f"Repaired {len(violations)} violation(s) in one agent; cascade nodes={len(impact['nodes'])}.",
        )
        return []

    def _llm_self_repair(self, violations: list, design: dict, assessment: dict, evaluation: dict) -> dict:
        import json

        findings = [
            {
                "type": getattr(v, "violation_type", ""),
                "node": getattr(v, "node_id", ""),
                "message": getattr(v, "message", ""),
                "hint": getattr(v, "repair_hint", ""),
                "metadata": getattr(v, "metadata", {}),
            }
            for v in violations
        ]
        system = (
            "You are an expert instructional designer revising your own ADDIE design to resolve "
            "verifier findings. Return ONLY valid JSON with this schema:\n"
            '{"design": {"learning_objectives": [{"id": "<id>", "statement": "<revised>"}], '
            '"learning_activities": [{"activity_name": "<name>", "duration": "<d>", "description": '
            '"<desc>", "materials": ["<m>"], "aligned_objectives": ["<LO id>"]}]},\n'
            ' "assessment_tools": [{"item_id": "<id>", "type": "<type>", "question": "<q>", '
            '"aligned_objective": "<LO id>", "scoring_criteria": "<criteria>"}],\n'
            ' "evaluation": {"formative": {"data_collection": {"methods": ["<method>"]}}}}\n'
            "Rules: keep objective/item ids; give every LO statement a measurable degree and a "
            "condition; align each item to an existing LO with observable criteria; add a "
            "constructed-response item for higher-order objectives; ensure active practice for "
            "Apply+ objectives; list concrete formative methods. Include only revised entries."
        )
        user = json.dumps(
            {"findings": findings, "design": design,
             "assessment_tools": assessment.get("assessment_tools", []),
             "evaluation": evaluation},
            ensure_ascii=False,
        )[:8000]
        response = self._call_llm(
            [{"role": "system", "content": system}, {"role": "user", "content": user}],
            max_retries=0,
        )
        return parse_json_response(response, warn=False) or {}


# ── Shared deterministic mechanical repair helpers ───────────────────────────
# These are plain graph-data edits (not agents). They give the single-agent
# self-repair the same convergence guarantees the specialist fallbacks provide,
# so the wo-ma arm differs from full only in WHO makes the LLM repair
# call (one agent vs specialists), not in whether the safety net exists.

_OBSERVABLE_RUBRIC = (
    "Analytic rubric, 4 levels (0-3) per criterion: task completed with at least 80% "
    "accuracy; target concepts applied correctly; justification cites observable evidence."
)


def _violation_ids(violations: list, vtype: str, key: str = "lo_id") -> list[str]:
    out = []
    for v in violations:
        if getattr(v, "violation_type", "") != vtype:
            continue
        val = getattr(v, "metadata", {}).get(key)
        if val:
            out.append(str(val))
        out.extend(str(i) for i in getattr(v, "metadata", {}).get(key + "s", []) or [])
    return out


def _merge_design(design: dict, revised: dict) -> None:
    revised_los = {
        str(lo["id"]): lo for lo in revised.get("learning_objectives", []) or []
        if isinstance(lo, dict) and lo.get("id")
    }
    for lo in design.get("learning_objectives", []) or []:
        if isinstance(lo, dict) and str(lo.get("id")) in revised_los:
            statement = str(revised_los[str(lo["id"])].get("statement") or "").strip()
            if statement:
                lo["statement"] = statement
    activities = design.setdefault("learning_activities", [])
    if isinstance(activities, list):
        for act in revised.get("learning_activities", []) or []:
            if isinstance(act, dict) and act.get("activity_name"):
                activities.append(act)


def _apply_design_fallbacks(design: dict, violations: list) -> None:
    from .objective_design import _BLOOM_VERB_BY_LEVEL, _VERB_REPLACEMENTS
    from .pedagogical_verifier import _CONDITION_PATTERN, _DEGREE_PATTERN

    objectives = design.get("learning_objectives", []) or []
    by_id = {str(lo.get("id")): lo for lo in objectives if isinstance(lo, dict) and lo.get("id")}

    for lo_id in _violation_ids(violations, "bloom"):
        lo = by_id.get(lo_id)
        if not lo:
            continue
        old = str(lo.get("bloom_verb", "")).strip()
        lo["bloom_verb"] = _VERB_REPLACEMENTS.get(old.lower()) or _BLOOM_VERB_BY_LEVEL.get(lo.get("level"), "Explain")

    for lo_id in _violation_ids(violations, "measurability"):
        lo = by_id.get(lo_id)
        if not lo:
            continue
        statement = str(lo.get("statement", ""))
        if not (_DEGREE_PATTERN.search(statement) or _CONDITION_PATTERN.search(statement)):
            lo["statement"] = statement.rstrip(". ") + ", achieving at least 80% accuracy against the scoring rubric."
            lo["measurable"] = True

    engagement_ids = _violation_ids(violations, "activity_engagement")
    if engagement_ids:
        activities = design.setdefault("learning_activities", [])
        if isinstance(activities, list):
            for lo_id in engagement_ids:
                covered = any(
                    isinstance(a, dict) and lo_id in (a.get("aligned_objectives") or [])
                    and any(m in f"{a.get('activity_name','')} {a.get('description','')}".lower()
                            for m in ("lab", "practice", "exercise", "project", "hands-on", "workshop", "simulation"))
                    for a in activities
                )
                if not covered:
                    activities.append({
                        "activity_name": f"Guided practice lab for {lo_id}",
                        "duration": "45m",
                        "description": (
                            f"Learners practice the skill behind {lo_id} on a realistic task "
                            "with instructor feedback and a completion checklist."
                        ),
                        "materials": ["Practice task sheet"],
                        "aligned_objectives": [lo_id],
                    })


def _apply_assessment_fallbacks(assessment: dict, design: dict, violations: list) -> None:
    from .pedagogical_verifier import (
        _ITEM_TYPE_CAPABILITY,
        _OBSERVABLE_TERMS,
        _RECALL_CAPABILITY_CEILING,
        _VAGUE_RUBRIC_TERMS,
    )

    tools = assessment.get("assessment_tools")
    if not isinstance(tools, list):
        tools = []
        assessment["assessment_tools"] = tools
    lo_map = {str(lo.get("id")): lo for lo in design.get("learning_objectives", []) or []
              if isinstance(lo, dict) and lo.get("id")}
    lo_ids = list(lo_map)

    def _criteria_ok(item: dict) -> bool:
        criteria = str(item.get("scoring_criteria") or item.get("scoring_rubric") or "").strip()
        low = criteria.lower()
        if not criteria:
            return False
        if str(item.get("type", "")).lower() in ("performance_task", "performance", "project", "rubric"):
            return len(criteria) >= 40 and not (
                any(t in low for t in _VAGUE_RUBRIC_TERMS) and not any(t in low for t in _OBSERVABLE_TERMS)
            )
        return True

    flagged_items = set(_violation_ids(violations, "rubric_consistency", "item_id"))
    for item in tools:
        if not isinstance(item, dict) or str(item.get("item_id")) not in flagged_items:
            continue
        aligned = str(item.get("aligned_objective") or "")
        if lo_ids and aligned not in lo_map:
            q = str(item.get("question", "")).lower()
            item["aligned_objective"] = next((i for i in lo_ids if i.lower() in q), lo_ids[0])
        if not _criteria_ok(item):
            item["scoring_criteria"] = _OBSERVABLE_RUBRIC

    for lo_id in _violation_ids(violations, "bloom_mismatch"):
        capability = max(
            (_ITEM_TYPE_CAPABILITY.get(str(t.get("type", "")).lower(), 6)
             for t in tools if isinstance(t, dict) and str(t.get("aligned_objective")) == lo_id),
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
            "scoring_criteria": _OBSERVABLE_RUBRIC,
            "difficulty": "hard",
        })


def _apply_evaluation_fallbacks(evaluation: dict, violations: list) -> None:
    if not any(getattr(v, "violation_type", "") == "evaluation_quality" for v in violations):
        return
    fallback_methods = [
        "Structured observation during activities using a facilitation checklist",
        "Exit tickets after each module scored against the objective criteria",
        "Rubric-scored formative checkpoints with instructor feedback",
    ]
    formative = evaluation.get("formative")
    if not isinstance(formative, dict):
        formative = {}
        evaluation["formative"] = formative
    dc = formative.get("data_collection")
    methods = dc.get("methods") if isinstance(dc, dict) else formative.get("methods")
    if not (isinstance(methods, list) and any(str(m).strip() for m in methods)):
        if isinstance(dc, dict):
            dc["methods"] = fallback_methods
        else:
            formative["methods"] = fallback_methods

from __future__ import annotations
from ..alignment_graph import NodeType
from ..brief import DesignBrief
from ..alignment_graph import alignment
from .. import rulebook as rules
from .. import repairs
from .base import BaseISDAgent, _format_design_brief, parse_json_response

# ── Hop A ("analyze"): needs/context analysis, decomposed into real element
# nodes (Gap, Topic, LearnerProfile, Constraint) instead of one bundle node —
# plus the improvement plan, grounded in the same gap analysis, in the same call.
# Schema + rules come from the shared rulebook (core/rulebook.py); only the
# persona and the task framing are this specialist's own.
_SYSTEM_ANALYZE = f"""\
You are an expert instructional designer performing the Analysis phase of ADDIE.

Given a training scenario, produce ONLY valid JSON with this EXACT schema:
{rules.SCHEMA_ANALYSIS}

{rules.RULES_ANALYSIS} {rules.JSON_ONLY}"""

_SYSTEM_GOAL = f"""\
You are an expert instructional designer stating the course goal (ADDIE Design phase).

Given a training scenario and its needs/task/learner analysis, produce ONLY valid JSON with
this EXACT schema:
{rules.SCHEMA_COURSE_GOAL}

{rules.RULES_COURSE_GOAL}
{rules.JSON_ONLY}"""

_SYSTEM_DESIGN = f"""\
You are an expert instructional designer writing the learning objectives (ADDIE Design phase).

Given a training scenario, its needs/task/learner analysis, and the course goal you already
committed to, produce ONLY valid JSON with this EXACT schema:
{rules.SCHEMA_LEARNING_OBJECTIVES}

{rules.RULES_OUTCOMES}
{rules.JSON_ONLY}"""


class OutcomeDesignerAgent(BaseISDAgent):
    """Retires NeedsContextAgent + ObjectiveDesignAgent's first call. Hop A
    ("analyze") decomposes needs/context analysis directly into real element
    nodes (Gap/Topic/LearnerProfile/Constraint — no bundle container) and the
    improvement plan (grounded in the same gaps, same call).

    Design used to be ONE further call asking for CourseGoal + the LOs that
    decompose it together — split (2026-08-28) into Hop B1 (course goal
    alone) then Hop B2 (objectives, now grounded in the COMMITTED goal, not
    a goal the same call is simultaneously inventing). Motivating measurement:
    a 2B model's single combined call committed a course_goal SECTION NODE
    with empty data (a required-but-unfilled field the two-field call
    quietly dropped), scoring the judge's objective-elaboration sub-item
    0/10 even though the objectives themselves were fine — a narrower,
    single-field call is far less likely to omit the one thing it is asked
    for. Every hop commits before returning control — see
    ``core/workflow.py``'s generation node."""

    # measurability is audit-only (the vague verb it targets is already fixed
    # by the shared bloom-verb repair).
    OWNED_VIOLATION_TYPES = repairs.OWNED_BY_FAMILY["outcome_designer"]

    def run(self, design_brief: DesignBrief) -> None:
        if not self._graph_mode:
            self._run_prose(design_brief)
            return
        gap_ids, topic_ids, learner_id, constraint_ids = self._run_analyze(design_brief)
        course_goal_id = self._run_goal(design_brief, gap_ids, topic_ids, learner_id)
        self._run_design(design_brief, gap_ids, topic_ids, learner_id, course_goal_id)

    # ── prose arm: same three hops, same prompts, blackboard store ────────
    def _run_prose(self, design_brief: DesignBrief) -> None:
        """All three hops against the ProseStore: identical system prompts
        and section headers to the graph path; the only differences are the
        context channel (whole blackboard documents, verbatim JSON, instead
        of relation-selected nodes) and the commit (read-modify-write into
        the shared "objective" document instead of element decomposition +
        provenance)."""
        prompt = _format_design_brief(design_brief)
        # Hop A — guard mirrors the graph arm's gap-pool check.
        if not ((self.store.get("analysis") or {}).get("needs_analysis") or {}).get("gaps"):
            user_content = self._with_retrieval(design_brief, "outcome_designer", prompt)
            response = self._call_llm([
                {"role": "system", "content": _SYSTEM_ANALYZE},
                {"role": "user", "content": user_content},
            ])
            parsed = parse_json_response(response)
            if parsed:
                self.store.put("analysis", parsed)
            self.trajectory.log_step("OutcomeDesignerAgent", "needs_analysis", prompt[:200], response[:200] if response else "")

        # Hop B1 — course goal (existence guard, like the graph arm's
        # section-node-presence check: a failed attempt is not retried on
        # its own, only via the whole-node regen loop re-entering this
        # method — see the graph arm's _run_goal for why).
        if "course_goal" not in (self.store.get("objective") or {}):
            prior_ctx = self._store_context(("analysis",))
            user_content = prompt
            if prior_ctx:
                user_content = f"=== NEEDS/TASK/LEARNER ANALYSIS ===\n{prior_ctx}\n\n=== SCENARIO ===\n{prompt}"
            user_content = self._with_retrieval(design_brief, "outcome_designer", user_content)
            response = self._call_llm([
                {"role": "system", "content": _SYSTEM_GOAL},
                {"role": "user", "content": user_content},
            ])
            parsed = parse_json_response(response)
            doc = self.store.get("objective") or {}
            self.store.put("objective", {**doc, "course_goal": parsed.get("course_goal") or {}})
            self.trajectory.log_step("OutcomeDesignerAgent", "design_course_goal", prompt[:200], response[:200] if response else "")

        # Hop B2 — objectives, grounded in the course goal Hop B1 committed.
        if self.store.items("objective", "learning_objectives"):
            return
        prior_ctx = self._store_context(("analysis", "objective"))
        user_content = prompt
        if prior_ctx:
            user_content = f"=== NEEDS/TASK/LEARNER ANALYSIS + COURSE GOAL ===\n{prior_ctx}\n\n=== SCENARIO ===\n{prompt}"
        user_content = self._with_retrieval(design_brief, "outcome_designer", user_content)
        response = self._call_llm([
            {"role": "system", "content": _SYSTEM_DESIGN},
            {"role": "user", "content": user_content},
        ])
        parsed = parse_json_response(response)
        # Deposited unconditionally, like the graph arm's element write — the
        # regen loop judges emptiness on the primary list, not key presence.
        doc = self.store.get("objective") or {}
        self.store.put("objective", {**doc, "learning_objectives": parsed.get("learning_objectives") or []})
        self.trajectory.log_step("OutcomeDesignerAgent", "design_objectives", prompt[:200], response[:200] if response else "")

    # ── Hop A ────────────────────────────────────────────────────────────
    def _run_analyze(self, design_brief: DesignBrief) -> tuple[list[str], list[str], str, list[str]]:
        # Surgical regen: if a prior attempt already produced gaps, reuse them.
        existing_gaps = self.graph.element_nodes(NodeType.GAP)
        if existing_gaps:
            return (
                [n["id"] for n in existing_gaps],
                [n["id"] for n in self.graph.element_nodes(NodeType.TOPIC)],
                self.graph.section_id(NodeType.LEARNER_PROFILE),
                [n["id"] for n in self.graph.element_nodes(NodeType.CONSTRAINT)],
            )

        prompt = _format_design_brief(design_brief)
        user_content = self._with_retrieval(design_brief, "outcome_designer", prompt)
        messages = [
            {"role": "system", "content": _SYSTEM_ANALYZE},
            {"role": "user", "content": user_content},
        ]
        response = self._call_llm(messages)
        parsed = parse_json_response(response)

        needs = parsed.get("needs_analysis", {}) or {}
        gap_ids = self._decompose_elements(NodeType.GAP, needs.get("gaps"))
        for gid in gap_ids:
            self.trajectory.log_node_edit("add", gid, NodeType.GAP)
        self._store_analysis_narrative(NodeType.GAP, needs, "gaps")

        task = parsed.get("task_analysis", {}) or {}
        topic_ids = self._decompose_elements(NodeType.TOPIC, task.get("topics"))
        for tid in topic_ids:
            self.trajectory.log_node_edit("add", tid, NodeType.TOPIC)
        self._store_analysis_narrative(NodeType.TOPIC, task, "topics")

        context = parsed.get("context_analysis", {}) or {}
        constraint_ids = self._decompose_elements(NodeType.CONSTRAINT, context.get("constraints"))
        for cid in constraint_ids:
            self.trajectory.log_node_edit("add", cid, NodeType.CONSTRAINT)
        self._store_analysis_narrative(NodeType.CONSTRAINT, context, "constraints")

        learner = parsed.get("learner_analysis", {}) or {}
        learner_id = self.graph.section_id(NodeType.LEARNER_PROFILE)
        if learner:
            self.graph.add_node(NodeType.LEARNER_PROFILE, learner_id, learner)
            self.trajectory.log_node_edit("add", learner_id, NodeType.LEARNER_PROFILE)

        improvement_plan = parsed.get("improvement_plan", {}) or {}
        improvement_ids = self._decompose_elements(NodeType.IMPROVEMENT, improvement_plan.get("improvements"))
        for iid in improvement_ids:
            self.trajectory.log_node_edit("add", iid, NodeType.IMPROVEMENT)
        # P9: each improvement addresses the gap it declares.
        gap_by_bare_id = {n["data"].get("id"): n["id"] for n in self.graph.element_nodes(NodeType.GAP)}
        for improvement in improvement_plan.get("improvements") or []:
            if not isinstance(improvement, dict):
                continue
            gap_ref = alignment.bare_ref(improvement.get("addresses_gap"))
            improvement_full_id = f"{NodeType.IMPROVEMENT}{self.graph.ELEMENT_SEP}{improvement.get('id')}"
            source_gap_id = gap_by_bare_id.get(gap_ref)
            if source_gap_id:
                alignment.record_provenance(self.graph, "P9", [source_gap_id], improvement_full_id)
        self._store_analysis_narrative(NodeType.IMPROVEMENT, improvement_plan, "improvements")

        self.trajectory.log_step("OutcomeDesignerAgent", "needs_analysis", prompt[:200], response[:200] if response else "")
        return gap_ids, topic_ids, learner_id, constraint_ids

    def _store_analysis_narrative(self, node_type: str, section: dict, element_key: str) -> None:
        """Persist the fields of an analysis section that are NOT the element
        list, on that type's section node (``gap_0``, ``topic_0``, ...).

        Decomposing ``needs_analysis``/``task_analysis``/``context_analysis``
        into Gap/Topic/Constraint elements captures only the enumerable half
        of each section. Their siblings — ``problem_definition``,
        ``priority_matrix``, ``prerequisites``, ``review_summary``,
        ``feedback_summary`` — carry the judgement a designer actually made,
        are not derivable from the element list, and are what several ADDIE
        analysis sub-items are scored on. Dropping them (as the first version
        of this decomposition did) cost ~7 rubric points per affected
        sub-item while the one section stored whole (``learner_profile_0``)
        scored ~9.6, so this is the same treatment applied consistently.

        Storing them here does NOT reintroduce a bundle container: the
        element list is stripped, so the section node holds only what no
        element node holds."""
        if not isinstance(section, dict):
            return
        narrative = {k: v for k, v in section.items() if k != element_key}
        if not narrative:
            return
        section_id = self.graph.section_id(node_type)
        self.graph.add_node(node_type, section_id, narrative)
        self.graph.link_section_narrative(node_type)
        self.trajectory.log_node_edit("add", section_id, node_type)

    # ── Hop B1: course goal alone ───────────────────────────────────────────
    def _run_goal(
        self, design_brief: DesignBrief, gap_ids: list[str], topic_ids: list[str], learner_id: str,
    ) -> str:
        """One narrow call, one field. Existence-guarded like every other
        first-half hop in this codebase (assessment's ``_run_plan``,
        activity's ``_run_plan``): a failed attempt deposits an empty
        section and is not retried on its own — only the whole-node regen
        loop re-entering ``run()`` would call this again, and by then the
        idempotency guard below skips straight to Hop B2."""
        course_goal_id = self.graph.section_id(NodeType.COURSE_GOAL)
        if self.graph.get_node(course_goal_id) is not None:
            return course_goal_id

        prompt = _format_design_brief(design_brief)
        source_ids = gap_ids + topic_ids + ([learner_id] if self.graph.get_node(learner_id) else [])
        prior_ctx = self._element_context(
            [n for n in (self.graph.get_node(nid) for nid in source_ids) if n is not None]
        )
        user_content = prompt
        if prior_ctx:
            user_content = f"=== NEEDS/TASK/LEARNER ANALYSIS ===\n{prior_ctx}\n\n=== SCENARIO ===\n{prompt}"
        user_content = self._with_retrieval(design_brief, "outcome_designer", user_content)
        response = self._call_llm([
            {"role": "system", "content": _SYSTEM_GOAL},
            {"role": "user", "content": user_content},
        ])
        parsed = parse_json_response(response)
        course_goal = parsed.get("course_goal") or {}
        self.graph.add_node(NodeType.COURSE_GOAL, course_goal_id, course_goal)
        self.trajectory.log_node_edit("add", course_goal_id, NodeType.COURSE_GOAL)
        self.trajectory.log_step(
            "OutcomeDesignerAgent", "design_course_goal", prompt[:200], response[:200] if response else "")
        return course_goal_id

    # ── Hop B2: objectives, grounded in the committed course goal ─────────
    def _run_design(
        self, design_brief: DesignBrief, gap_ids: list[str], topic_ids: list[str],
        learner_id: str, course_goal_id: str,
    ) -> None:
        # Element-pool check, not section-node presence: the section node
        # below is written unconditionally (even with an empty
        # learning_objectives list on a failed LLM call), so guarding on it
        # would poison the node-level regen loop's retry — it would see the
        # node "already exists" from the failed attempt and never call the
        # LLM again.
        if self.graph.element_nodes(NodeType.OBJECTIVE):
            return

        prompt = _format_design_brief(design_brief)
        source_ids = gap_ids + topic_ids + ([learner_id] if self.graph.get_node(learner_id) else [])
        prior_nodes = [n for n in (self.graph.get_node(nid) for nid in source_ids) if n is not None]
        course_goal_node = self.graph.get_node(course_goal_id)
        if course_goal_node is not None:
            prior_nodes = prior_nodes + [course_goal_node]
        prior_ctx = self._element_context(prior_nodes)
        user_content = prompt
        if prior_ctx:
            user_content = f"=== NEEDS/TASK/LEARNER ANALYSIS + COURSE GOAL ===\n{prior_ctx}\n\n=== SCENARIO ===\n{prompt}"
        user_content = self._with_retrieval(design_brief, "outcome_designer", user_content)
        messages = [
            {"role": "system", "content": _SYSTEM_DESIGN},
            {"role": "user", "content": user_content},
        ]
        response = self._call_llm(messages)
        parsed = parse_json_response(response)

        # No objective_0 section: element nodes are the single source of
        # truth for the LO list (the legacy full-list section duplicated every
        # byte and forced every repair to write both copies).
        objective_ids = self._decompose_elements(NodeType.OBJECTIVE, parsed.get("learning_objectives", []))
        for oid in objective_ids:
            self.trajectory.log_node_edit("add", oid, NodeType.OBJECTIVE)
            # C1: LO decomposes from the course goal (core, provenance).
            alignment.record_provenance(self.graph, "C1", [course_goal_id], oid)
            # P1/P2: secondary provenance back to the analysis sources.
            if gap_ids or topic_ids:
                alignment.record_provenance(self.graph, "P1", gap_ids + topic_ids, oid)
            if self.graph.get_node(learner_id):
                alignment.record_provenance(self.graph, "P2", [learner_id], oid)

        self.trajectory.log_step("OutcomeDesignerAgent", "design_objectives", prompt[:200], response[:200] if response else "")

    # ── self-validation (owns: bloom) ────────────────────────────────────
    def repair(self, violations: list) -> list:
        return repairs.repair("outcome_designer", violations, repairs.context_for(self))

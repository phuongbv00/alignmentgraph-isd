from __future__ import annotations
from ..alignment_graph import NodeType
from ..brief import DesignBrief
from ..alignment_graph import alignment
from .. import rulebook as rules
from .. import repairs
from .. import dev_plans
from .base import BaseISDAgent, _format_design_brief, parse_json_response
from .assessment_developer import AssessmentDeveloperAgent

_SYSTEM_PLAN = f"""\
You are an expert instructional designer planning an assessment strategy (ADDIE Design phase).

Given a training scenario, its learning objectives (ILO = Intended Learning Outcome), and the
analysis context (topics, constraints, learner profile), produce ONLY valid JSON with this
EXACT schema:
{rules.SCHEMA_ASSESSMENT_PLAN}

{rules.RULES_ASSESSMENT_PLAN}
{rules.JSON_ONLY}"""

_SYSTEM_DEV_PLAN = f"""\
You are an expert instructional designer grouping assessment work into instrument sets (ADDIE
Design phase), so separate developers can write items for each set independently.

Given a training scenario, its learning objectives, and the assessment plan you already
committed to (its lo_coverage_targets fixes every (objective, plan_category) pair a later step
must cover), produce ONLY valid JSON with this EXACT schema:
{rules.SCHEMA_ASSESSMENT_DEV_PLAN}

{rules.RULES_ASSESSMENT_DEV_PLAN}
{rules.JSON_ONLY}"""


class AssessmentDesignerAgent(BaseISDAgent):
    """Retires AssessmentDesignAgent; absorbs the assessment_plan half of
    ObjectiveDesignAgent's call 2, and all of EvaluationRevisionAgent
    (diagnostic/formative/summative are one unified pool now, distinguished
    only by ``plan_category`` — no separate `summative` node type).

    Dev-plan fan-out (2026-08-28): this class owns the PLANNING half only —
    the assessment strategy (``_run_plan``) and its grouping into instrument
    sets (``_run_dev_plan``). Writing the actual items is
    :class:`AssessmentDeveloperAgent`'s job, one call per instrument set,
    fanned out in parallel by the ``assessment_developer`` LangGraph node
    (``core/workflow.py``). This class commits the pooled result,
    re-establishes C2/P3, and self-validates at ``finalize()``. ``run()``
    composes all three phases sequentially for direct/test callers; the
    workflow drives them through separate nodes instead.
    """

    OWNED_VIOLATION_TYPES = repairs.OWNED_BY_FAMILY["assessment_designer"]
    FAMILY = "assessment_designer"

    def __init__(self, config, graph, trajectory, store=None) -> None:
        super().__init__(config, graph, trajectory, store)
        self._work_sets: list[dev_plans.WorkSet] = []

    def run(self, design_brief: DesignBrief) -> None:
        self.run_dispatch(design_brief)
        developer = AssessmentDeveloperAgent(self.config, self.graph, self.trajectory, self.store)
        payloads = [developer.run_worker(ws, design_brief) for ws in self._work_sets]
        self.finalize(self._work_sets, payloads, design_brief)

    def take_work_sets(self) -> list[dev_plans.WorkSet]:
        return list(self._work_sets)

    def _analysis_nodes(self) -> list[dict]:
        """Analysis artifacts both hops condition on: subject matter (topics),
        delivery constraints (item-format feasibility), and the learner
        profile (difficulty, stem context). Backward Design forbids deriving
        assessment from instructional materials, not from knowing the subject
        matter and learners — content/activity nodes stay out."""
        return (self.graph.element_nodes(NodeType.TOPIC)
                + self.graph.element_nodes(NodeType.CONSTRAINT)
                + self.graph.section_nodes(NodeType.LEARNER_PROFILE))

    # ── dispatch: plan, then group the plan into instrument sets ──────────
    def run_dispatch(self, design_brief: DesignBrief) -> None:
        if not self._graph_mode:
            self._run_dispatch_prose(design_brief)
            return
        self._run_plan(design_brief)
        self._run_dev_plan(design_brief)

    def _run_plan(self, design_brief: DesignBrief) -> None:
        if self.graph.get_node(self.graph.section_id(NodeType.ASSESSMENT_PLAN)) is not None:
            return
        prompt = _format_design_brief(design_brief)
        lo_nodes = self.graph.element_nodes(NodeType.OBJECTIVE)
        prior_ctx = self._element_context(lo_nodes + self._analysis_nodes())
        user_content = prompt
        if prior_ctx:
            user_content = f"=== LEARNING OBJECTIVES + ANALYSIS CONTEXT ===\n{prior_ctx}\n\n=== SCENARIO ===\n{prompt}"
        user_content = self._with_retrieval(design_brief, "assessment_designer", user_content)
        response = self._call_llm([
            {"role": "system", "content": _SYSTEM_PLAN},
            {"role": "user", "content": user_content},
        ])
        parsed = parse_json_response(response)
        plan = parsed.get("assessment_plan", {}) or {}
        plan_id = self.graph.section_id(NodeType.ASSESSMENT_PLAN)
        self.graph.add_node(NodeType.ASSESSMENT_PLAN, plan_id, plan)
        self.trajectory.log_node_edit("add", plan_id, NodeType.ASSESSMENT_PLAN)
        self.trajectory.log_step("AssessmentDesignerAgent", "plan_assessment", prompt[:200], response[:200] if response else "")

    def _run_dev_plan(self, design_brief: DesignBrief) -> None:
        plan_node = self.graph.get_node(self.graph.section_id(NodeType.ASSESSMENT_PLAN))
        plan_data = (plan_node or {}).get("data") or {}
        lo_nodes = self.graph.element_nodes(NodeType.OBJECTIVE)
        lo_ids = [self._bare(n["id"]) for n in lo_nodes]
        prompt = _format_design_brief(design_brief)
        prior_ctx = self._element_context(lo_nodes + ([plan_node] if plan_node else []))
        user_content = prompt
        if prior_ctx:
            user_content = f"=== LEARNING OBJECTIVES + ASSESSMENT PLAN ===\n{prior_ctx}\n\n=== SCENARIO ===\n{prompt}"
        user_content = self._with_retrieval(design_brief, "assessment_designer", user_content)
        response = self._call_llm([
            {"role": "system", "content": _SYSTEM_DEV_PLAN},
            {"role": "user", "content": user_content},
        ])
        parsed = parse_json_response(response)
        sets, stats = dev_plans.normalize_assessment_dev_plan(
            parsed, lo_ids, plan_data.get("lo_coverage_targets"))
        self._work_sets = sets
        self.trajectory.log_step(
            "AssessmentDesignerAgent", "plan_assessment_sets", prompt[:200], response[:200] if response else "")
        self._log_dev_plan(sets, stats)

    def _log_dev_plan(self, sets: list[dev_plans.WorkSet], stats: dict) -> None:
        self.trajectory.log_dev_plan(
            "assessment_designer",
            set_count=stats["set_count"], pair_count=stats["pair_count"],
            sets=[{"set_id": ws.set_id, "objectives": list(ws.objectives),
                   "categories": sorted({category for _, category in ws.pairs})}
                  for ws in sets],
            source="fallback" if stats["fallback_used"] else "llm",
            fallback_used=stats["fallback_used"], dropped_refs=stats["dropped_lo_refs"],
            appended_sets=stats["appended_sets"], agent="AssessmentDesignerAgent",
        )

    # ── prose arm: same two hops, same prompts, blackboard store ──────────
    def _run_dispatch_prose(self, design_brief: DesignBrief) -> None:
        prompt = _format_design_brief(design_brief)
        # Plan hop guard mirrors the graph arm's section-presence check (a
        # failed plan hop deposits {} and is not retried; only the dev-plan
        # call, and via it the develop fan-out, drives regen).
        if not self.store.has("assessment_plan"):
            prior_ctx = self._store_context(("objective", "analysis"))
            user_content = prompt
            if prior_ctx:
                user_content = f"=== LEARNING OBJECTIVES + ANALYSIS CONTEXT ===\n{prior_ctx}\n\n=== SCENARIO ===\n{prompt}"
            user_content = self._with_retrieval(design_brief, "assessment_designer", user_content)
            response = self._call_llm([
                {"role": "system", "content": _SYSTEM_PLAN},
                {"role": "user", "content": user_content},
            ])
            parsed = parse_json_response(response)
            self.store.put("assessment_plan", parsed.get("assessment_plan", {}) or {})
            self.trajectory.log_step("AssessmentDesignerAgent", "plan_assessment", prompt[:200], response[:200] if response else "")

        plan_data = self.store.get("assessment_plan") or {}
        lo_ids = [
            str(lo.get("id", "")) for lo in self.store.items("objective", "learning_objectives")
            if isinstance(lo, dict) and lo.get("id")
        ]
        prior_ctx = self._store_context(("objective", "assessment_plan"))
        user_content = prompt
        if prior_ctx:
            user_content = f"=== LEARNING OBJECTIVES + ASSESSMENT PLAN ===\n{prior_ctx}\n\n=== SCENARIO ===\n{prompt}"
        user_content = self._with_retrieval(design_brief, "assessment_designer", user_content)
        response = self._call_llm([
            {"role": "system", "content": _SYSTEM_DEV_PLAN},
            {"role": "user", "content": user_content},
        ])
        parsed = parse_json_response(response)
        sets, stats = dev_plans.normalize_assessment_dev_plan(
            parsed, lo_ids, plan_data.get("lo_coverage_targets"))
        self._work_sets = sets
        self.trajectory.log_step(
            "AssessmentDesignerAgent", "plan_assessment_sets", prompt[:200], response[:200] if response else "")
        self._log_dev_plan(sets, stats)

    # ── finalize: fan-in commit + per-set regen + relation matchers ───────
    def finalize(self, work_sets: list[dev_plans.WorkSet], payloads: list[dict],
                 design_brief: DesignBrief) -> None:
        developer = AssessmentDeveloperAgent(self.config, self.graph, self.trajectory, self.store)
        payloads = self._regen_missing_sets(
            work_sets, payloads, developer, design_brief, "assessment_designer")
        merged = dev_plans.remap_and_tag(work_sets, payloads, id_field="item_id")

        if not self._graph_mode:
            doc = self.store.get("assessment") or {}
            existing = doc.get("assessment_tools") or []
            self.store.put("assessment", {**doc, "assessment_tools": existing + merged})
            return

        item_ids = self._decompose_elements(NodeType.ASSESSMENT, merged, id_field="item_id")
        for iid in item_ids:
            self.trajectory.log_node_edit("add", iid, NodeType.ASSESSMENT)
        # C2: learning outcome assessed by assessment task (core).
        alignment.match_id_reverse(self.graph, "C2", field="aligned_objective")
        # P3: assessment plan realized by assessment task (secondary).
        alignment.match_p3_realizes(self.graph)

    # ── self-validation ───────────────────────────────────────────────────
    def repair(self, violations: list) -> list:
        return repairs.repair("assessment_designer", violations, repairs.context_for(self))

from __future__ import annotations
from ..alignment_graph import NodeType
from ..brief import DesignBrief
from ..alignment_graph import alignment
from .. import rulebook as rules
from .. import repairs
from .. import dev_plans
from .base import BaseISDAgent, _format_design_brief, parse_json_response
from .activity_developer import ActivityDeveloperAgent

_SYSTEM_PLAN = f"""\
You are an expert instructional designer planning the instructional strategy (ADDIE Design phase).

Given a training scenario, its learning objectives (ILO), and its assessment strategy, produce
ONLY valid JSON with this EXACT schema:
{rules.SCHEMA_ACTIVITY_PLAN}

{rules.RULES_ACTIVITY_PLAN}
{rules.JSON_ONLY}"""

_SYSTEM_DEV_PLAN = f"""\
You are an expert instructional designer grouping learning activities into blocks (ADDIE Design
phase), so separate developers can write activities for each block independently.

Given a training scenario, its learning objectives, and the instructional strategy you already
committed to, produce ONLY valid JSON with this EXACT schema:
{rules.SCHEMA_ACTIVITY_DEV_PLAN}

{rules.RULES_ACTIVITY_DEV_PLAN}
{rules.JSON_ONLY}"""


class ActivityDesignerAgent(BaseISDAgent):
    """Retires the activity half of ActivityMaterialAgent; absorbs
    instructional_strategies + non_instructional_strategies from
    ObjectiveDesignAgent's call 2 into one ActivityPlan node.

    Dev-plan fan-out (2026-08-28): this class owns the PLANNING half only —
    the instructional strategy (``_run_plan``) and its grouping into activity
    blocks (``_run_dev_plan``). Writing the actual activities is
    :class:`ActivityDeveloperAgent`'s job, one call per block, fanned out in
    parallel by the ``activity_developer`` LangGraph node. This class commits
    the pooled result, re-establishes C3/C4/P4 + ``precedes``, and
    self-validates at ``finalize()``.
    """

    OWNED_VIOLATION_TYPES = repairs.OWNED_BY_FAMILY["activity_designer"]

    def __init__(self, config, graph, trajectory, store=None) -> None:
        super().__init__(config, graph, trajectory, store)
        self._work_sets: list[dev_plans.WorkSet] = []

    def run(self, design_brief: DesignBrief) -> None:
        self.run_dispatch(design_brief)
        developer = ActivityDeveloperAgent(self.config, self.graph, self.trajectory, self.store)
        payloads = [developer.run_worker(ws, design_brief) for ws in self._work_sets]
        self.finalize(self._work_sets, payloads, design_brief)

    def take_work_sets(self) -> list[dev_plans.WorkSet]:
        return list(self._work_sets)

    # ── dispatch: plan, then group into activity blocks ────────────────────
    def run_dispatch(self, design_brief: DesignBrief) -> None:
        if not self._graph_mode:
            self._run_dispatch_prose(design_brief)
            return
        self._run_plan(design_brief)
        self._run_dev_plan(design_brief)

    def _run_plan(self, design_brief: DesignBrief) -> None:
        if self.graph.get_node(self.graph.section_id(NodeType.ACTIVITY_PLAN)) is not None:
            return
        prompt = _format_design_brief(design_brief)
        lo_nodes = self.graph.element_nodes(NodeType.OBJECTIVE)
        assessment_nodes = self.graph.element_nodes(NodeType.ASSESSMENT)
        # Relation-join: each objective arrives WITH the items that assess it
        # (C2 edges), so the docket no longer needs to restate the edge list.
        prior_ctx = self._element_context_joined(lo_nodes, assessment_nodes, "C2", "assessed by")
        state_ctx = self._alignment_state_context(gaps=("C3", "C4"))
        user_content = prompt
        if prior_ctx:
            user_content = f"=== LEARNING OBJECTIVES + ASSESSMENT ITEMS ===\n{prior_ctx}\n\n=== SCENARIO ===\n{prompt}"
        if state_ctx:
            user_content = f"{state_ctx}\n\n{user_content}"
        user_content = self._with_retrieval(design_brief, "activity_designer", user_content)
        response = self._call_llm([
            {"role": "system", "content": _SYSTEM_PLAN},
            {"role": "user", "content": user_content},
        ])
        parsed = parse_json_response(response)
        plan_id = self.graph.section_id(NodeType.ACTIVITY_PLAN)
        self.graph.add_node(NodeType.ACTIVITY_PLAN, plan_id, {
            "instructional_strategies": parsed.get("instructional_strategies", {}),
            "non_instructional_strategies": parsed.get("non_instructional_strategies", {}),
        })
        self.trajectory.log_node_edit("add", plan_id, NodeType.ACTIVITY_PLAN)
        self.trajectory.log_step("ActivityDesignerAgent", "plan_activities", prompt[:200], response[:200] if response else "")

    def _items_by_lo(self) -> dict[str, list[str]]:
        """Bare LO id -> bare assessment item ids assessing it (C2 edges) —
        the ground truth an activity block's ``prepares_for_assessment``
        hints can draw from."""
        result: dict[str, list[str]] = {}
        for lo_node in self.graph.element_nodes(NodeType.OBJECTIVE):
            lo_id = self._bare(lo_node["id"])
            result[lo_id] = [
                self._bare(edge["target"])
                for edge in self.graph.get_edges(relation_id="C2", source=lo_node["id"])
            ]
        return result

    def _run_dev_plan(self, design_brief: DesignBrief) -> None:
        lo_nodes = self.graph.element_nodes(NodeType.OBJECTIVE)
        lo_ids = [self._bare(n["id"]) for n in lo_nodes]
        plan_node = self.graph.get_node(self.graph.section_id(NodeType.ACTIVITY_PLAN))
        prompt = _format_design_brief(design_brief)
        prior_ctx = self._element_context(lo_nodes + ([plan_node] if plan_node else []))
        user_content = prompt
        if prior_ctx:
            user_content = f"=== LEARNING OBJECTIVES + INSTRUCTIONAL STRATEGY ===\n{prior_ctx}\n\n=== SCENARIO ===\n{prompt}"
        user_content = self._with_retrieval(design_brief, "activity_designer", user_content)
        response = self._call_llm([
            {"role": "system", "content": _SYSTEM_DEV_PLAN},
            {"role": "user", "content": user_content},
        ])
        parsed = parse_json_response(response)
        sets, stats = dev_plans.normalize_activity_dev_plan(parsed, lo_ids, self._items_by_lo())
        self._work_sets = sets
        self.trajectory.log_step(
            "ActivityDesignerAgent", "plan_activity_blocks", prompt[:200], response[:200] if response else "")
        self._log_dev_plan(sets, stats)

    def _log_dev_plan(self, sets: list[dev_plans.WorkSet], stats: dict) -> None:
        self.trajectory.log_dev_plan(
            "activity_designer",
            set_count=stats["set_count"], pair_count=stats["pair_count"],
            sets=[{"set_id": ws.set_id, "objectives": list(ws.objectives)} for ws in sets],
            source="fallback" if stats["fallback_used"] else "llm",
            fallback_used=stats["fallback_used"], dropped_refs=stats["dropped_lo_refs"],
            appended_sets=stats["appended_sets"], agent="ActivityDesignerAgent",
        )

    # ── prose arm: same two hops, same prompts, blackboard store ──────────
    def _run_dispatch_prose(self, design_brief: DesignBrief) -> None:
        prompt = _format_design_brief(design_brief)
        if not self.store.has("activity_plan"):
            prior_ctx = self._store_context(("objective", "assessment"))
            user_content = prompt
            if prior_ctx:
                user_content = f"=== LEARNING OBJECTIVES + ASSESSMENT ITEMS ===\n{prior_ctx}\n\n=== SCENARIO ===\n{prompt}"
            user_content = self._with_retrieval(design_brief, "activity_designer", user_content)
            response = self._call_llm([
                {"role": "system", "content": _SYSTEM_PLAN},
                {"role": "user", "content": user_content},
            ])
            parsed = parse_json_response(response)
            self.store.put("activity_plan", {
                "instructional_strategies": parsed.get("instructional_strategies", {}),
                "non_instructional_strategies": parsed.get("non_instructional_strategies", {}),
            })
            self.trajectory.log_step("ActivityDesignerAgent", "plan_activities", prompt[:200], response[:200] if response else "")

        lo_ids = [
            str(lo.get("id", "")) for lo in self.store.items("objective", "learning_objectives")
            if isinstance(lo, dict) and lo.get("id")
        ]
        items_by_lo: dict[str, list[str]] = {}
        for tool in self.store.items("assessment", "assessment_tools"):
            if not isinstance(tool, dict):
                continue
            lo = str(tool.get("aligned_objective", ""))
            item_id = str(tool.get("item_id", ""))
            if lo and item_id:
                items_by_lo.setdefault(lo, []).append(item_id)

        prior_ctx = self._store_context(("objective", "activity_plan"))
        user_content = prompt
        if prior_ctx:
            user_content = f"=== LEARNING OBJECTIVES + INSTRUCTIONAL STRATEGY ===\n{prior_ctx}\n\n=== SCENARIO ===\n{prompt}"
        user_content = self._with_retrieval(design_brief, "activity_designer", user_content)
        response = self._call_llm([
            {"role": "system", "content": _SYSTEM_DEV_PLAN},
            {"role": "user", "content": user_content},
        ])
        parsed = parse_json_response(response)
        sets, stats = dev_plans.normalize_activity_dev_plan(parsed, lo_ids, items_by_lo)
        self._work_sets = sets
        self.trajectory.log_step(
            "ActivityDesignerAgent", "plan_activity_blocks", prompt[:200], response[:200] if response else "")
        self._log_dev_plan(sets, stats)

    # ── finalize: fan-in commit + per-set regen + relation matchers ───────
    def finalize(self, work_sets: list[dev_plans.WorkSet], payloads: list[dict],
                 design_brief: DesignBrief) -> None:
        developer = ActivityDeveloperAgent(self.config, self.graph, self.trajectory, self.store)
        payloads = self._regen_missing_sets(
            work_sets, payloads, developer, design_brief, "activity_designer")
        merged = dev_plans.remap_and_tag(
            work_sets, payloads, id_field="id", ref_fields=("prerequisite_activities",))

        if not self._graph_mode:
            doc = self.store.get("activity") or {}
            existing = doc.get("learning_activities") or []
            self.store.put("activity", {**doc, "learning_activities": existing + merged})
            return

        activity_ids = self._decompose_elements(NodeType.ACTIVITY, merged)
        for aid in activity_ids:
            self.trajectory.log_node_edit("add", aid, NodeType.ACTIVITY)
        self._establish_relations(activity_ids)

    def _establish_relations(self, activity_ids: list[str]) -> None:
        # C3: LO practiced_by activity (reversed id-list match).
        alignment.match_list_reverse(self.graph, "C3", field="aligned_objectives")
        # C4: activity prepares_for assessment (standard id-list match).
        alignment.match_list(self.graph, "C4", field="prepares_for_assessment")
        # P4: the activity plan realized by activity (provenance; the whole
        # call was conditioned on the plan node).
        plan_id = self.graph.section_id(NodeType.ACTIVITY_PLAN)
        if self.graph.get_node(plan_id):
            for activity_id in activity_ids:
                alignment.record_provenance(self.graph, "P4", [plan_id], activity_id)
        # Structural progression edges (not in REGISTRY, no coverage check —
        # mirrors the existing "rooted-in" scaffolding pattern): an activity
        # that declares prerequisite_activities depends on them.
        for activity_id in activity_ids:
            node = self.graph.get_node(activity_id)
            if not node:
                continue
            for prereq in node["data"].get("prerequisite_activities", []) or []:
                prereq_id = f"{NodeType.ACTIVITY}{self.graph.ELEMENT_SEP}{prereq}"
                if self.graph.get_node(prereq_id):
                    self.graph.add_edge(
                        "precedes", prereq_id, activity_id, established_by="provenance",
                        rationale=f"{activity_id} declares {prereq_id} as a prerequisite.",
                    )

    # ── self-validation ───────────────────────────────────────────────────
    def repair(self, violations: list) -> list:
        return repairs.repair("activity_designer", violations, repairs.context_for(self))

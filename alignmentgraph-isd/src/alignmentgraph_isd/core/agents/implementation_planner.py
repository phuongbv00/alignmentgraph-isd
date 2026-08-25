from __future__ import annotations
from ..alignment_graph import NodeType
from ..alignment_graph import alignment
from ..brief import DesignBrief
from .. import rulebook as rules
from .. import repairs
from .base import BaseISDAgent, _format_design_brief, parse_json_response

_SYSTEM = f"""\
You are an expert instructional designer planning the Implementation phase of ADDIE.

Given a training scenario, produce ONLY valid JSON with this EXACT schema:
{rules.SCHEMA_IMPLEMENTATION}

{rules.RULES_IMPLEMENTATION}
{rules.JSON_ONLY}"""




class ImplementationPlannerAgent(BaseISDAgent):
    OWNED_VIOLATION_TYPES = repairs.OWNED_BY_FAMILY["implementation_planner"]

    def run(self, design_brief: DesignBrief) -> None:
        if not self._graph_mode:
            self._run_prose(design_brief)
            return
        prompt = _format_design_brief(design_brief)
        # Traversal-scoped context: what must be operationalized (activities/
        # materials) and how it was meant to run (instructional strategy).
        # No relation in the 13-relation matrix targets implementation_plan,
        # so this specialist establishes no alignment edges — only context.
        plan_node = self.graph.get_node(self.graph.section_id(NodeType.ACTIVITY_PLAN))
        prior_nodes = (
            self.graph.element_nodes(NodeType.ACTIVITY)
            + self.graph.element_nodes(NodeType.MATERIAL)
            + ([plan_node] if plan_node else [])
        )
        prior_ctx = self._element_context(prior_nodes)
        # P10/P11 docket: every activity not yet scheduled, every material not
        # yet handed out — at first pass that is all of them, which is exactly
        # the id list the session guides' activity_ids/material_ids must cover.
        state_ctx = self._alignment_state_context(gaps=("P10", "P11"))
        user_content = prompt
        if prior_ctx:
            user_content = f"=== DESIGN + DEVELOPMENT RESULTS (from prior agents) ===\n{prior_ctx}\n\n=== SCENARIO ===\n{prompt}"
        if state_ctx:
            user_content = f"{state_ctx}\n\n{user_content}"
        user_content = self._with_retrieval(design_brief, "implementation_plan", user_content)
        messages = [
            {"role": "system", "content": _SYSTEM},
            {"role": "user", "content": user_content},
        ]
        response = self._call_llm(messages)
        parsed = parse_json_response(response)
        node_id = self.graph.section_id(NodeType.IMPLEMENTATION_PLAN)
        self.graph.add_node(NodeType.IMPLEMENTATION_PLAN, node_id, parsed)
        self.trajectory.log_node_edit("add", node_id, NodeType.IMPLEMENTATION_PLAN)
        alignment.establish_delivery(self.graph, node_id, parsed)
        parse_ok = bool(parsed)
        self.trajectory.log_step(
            "ImplementationPlannerAgent", "plan_implementation",
            prompt[:200],
            f"[PARSE={'OK' if parse_ok else 'FAILED'} len={len(response)}] " + response[:400],
        )

    # ── prose arm: same prompt, blackboard store, no P10/P11 provenance ───
    def _run_prose(self, design_brief: DesignBrief) -> None:
        prompt = _format_design_brief(design_brief)
        prior_ctx = self._store_context(("activity", "material", "activity_plan"))
        user_content = prompt
        if prior_ctx:
            user_content = f"=== DESIGN + DEVELOPMENT RESULTS (from prior agents) ===\n{prior_ctx}\n\n=== SCENARIO ===\n{prompt}"
        user_content = self._with_retrieval(design_brief, "implementation_plan", user_content)
        response = self._call_llm([
            {"role": "system", "content": _SYSTEM},
            {"role": "user", "content": user_content},
        ])
        parsed = parse_json_response(response)
        self.store.put("implementation_plan", parsed)
        parse_ok = bool(parsed)
        self.trajectory.log_step(
            "ImplementationPlannerAgent", "plan_implementation",
            prompt[:200],
            f"[PARSE={'OK' if parse_ok else 'FAILED'} len={len(response)}] " + response[:400],
        )

    def repair(self, violations: list) -> list:
        return repairs.repair("implementation_planner", violations, repairs.context_for(self))

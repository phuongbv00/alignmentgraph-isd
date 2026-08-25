from __future__ import annotations
from ..brief import DesignBrief
from .. import rulebook as rules
from ..dev_plans import render_activity_set as _render_work_set
from .base import BaseISDAgent, _format_design_brief, parse_json_response

_SYSTEM = f"""\
You are an expert instructional designer developing ONE activity block (ADDIE Development
phase) — writing the actual learning activities for exactly the objectives your assigned block
names. You are NOT responsible for any other objective; another Developer is handling those.

Given a training scenario and your assigned activity block, produce ONLY valid JSON with this
EXACT schema:
{rules.SCHEMA_ACTIVITIES}

{rules.RULES_ACTIVITIES_SET}
{rules.JSON_ONLY}"""


class ActivityDeveloperAgent(BaseISDAgent):
    """Spawned once per activity block by ActivityDesignerAgent's fan-out
    (``activity_developer`` node in ``core/workflow.py``): one LLM call
    producing activities for exactly the objectives its assigned
    :class:`core.dev_plans.WorkSet` names. Makes no graph/store writes and
    owns no violation types of its own — ActivityDesignerAgent commits and
    self-validates the pooled result at ``finalize()``.
    """

    def run(self, design_brief: DesignBrief) -> None:  # pragma: no cover
        raise NotImplementedError(
            "ActivityDeveloperAgent is driven via run_worker(work_set, design_brief), not run().")

    def run_worker(self, work_set, design_brief: DesignBrief) -> dict:
        prompt = _format_design_brief(design_brief)
        set_text = _render_work_set(work_set)
        prior_ctx = self._objective_context(work_set)
        user_content = f"=== YOUR ASSIGNED BLOCK ===\n{set_text}\n\n=== SCENARIO ===\n{prompt}"
        if prior_ctx:
            user_content = f"=== YOUR OBJECTIVES + THEIR ASSESSMENT ITEMS ===\n{prior_ctx}\n\n{user_content}"
        user_content = self._with_retrieval(design_brief, "activity_designer", user_content)
        response = self._call_llm([
            {"role": "system", "content": _SYSTEM},
            {"role": "user", "content": user_content},
        ])
        parsed = parse_json_response(response)
        items = parsed.get("learning_activities", [])
        self.trajectory.log_step(
            "ActivityDeveloperAgent", f"develop_activities_{work_set.set_id}",
            prompt[:200], response[:200] if response else "",
        )
        return {
            "family": "activity_designer", "set_id": work_set.set_id,
            "items": items if isinstance(items, list) else [],
        }

    def _objective_context(self, work_set) -> str:
        if not work_set.objectives:
            return ""
        if self._graph_mode:
            from ..alignment_graph import NodeType
            lo_ids = set(work_set.objectives)
            lo_nodes = [n for n in self.graph.element_nodes(NodeType.OBJECTIVE) if self._bare(n["id"]) in lo_ids]
            relevant_item_ids = {
                edge["target"] for lo in lo_nodes
                for edge in self.graph.get_edges(relation_id="C2", source=lo["id"])
            }
            assessment_nodes = [
                n for n in self.graph.element_nodes(NodeType.ASSESSMENT) if n["id"] in relevant_item_ids
            ]
            return self._element_context_joined(lo_nodes, assessment_nodes, "C2", "assessed by")
        return self._store_context(("objective", "assessment"))

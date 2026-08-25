from __future__ import annotations
from ..brief import DesignBrief
from .. import rulebook as rules
from ..dev_plans import render_rubric_set as _render_work_set
from .base import BaseISDAgent, _format_design_brief, parse_json_response

_SYSTEM = f"""\
You are an expert instructional designer writing rubric criteria for ONE assessment item (ADDIE
Development phase). You are NOT responsible for any other item; another Developer is handling
those.

Given a training scenario and your assigned assessment item (with its aligned objective),
produce ONLY valid JSON with this EXACT schema:
{rules.SCHEMA_RUBRICS}

{rules.RULES_RUBRICS_ITEM}
{rules.JSON_ONLY}"""


class RubricDeveloperAgent(BaseISDAgent):
    """Spawned once per assessment item by RubricDesignerAgent's fan-out
    (``rubric_developer`` node in ``core/workflow.py``): one LLM call
    producing criteria for exactly the ONE item its assigned
    :class:`core.dev_plans.WorkSet` names. Makes no graph/store writes and
    owns no violation types of its own — RubricDesignerAgent commits and
    self-validates the pooled result at ``finalize()``.
    """

    def run(self, design_brief: DesignBrief) -> None:  # pragma: no cover
        raise NotImplementedError(
            "RubricDeveloperAgent is driven via run_worker(work_set, design_brief), not run().")

    def run_worker(self, work_set, design_brief: DesignBrief) -> dict:
        prompt = _format_design_brief(design_brief)
        set_text = _render_work_set(work_set)
        prior_ctx = self._objective_context(work_set)
        user_content = f"=== YOUR ASSIGNED ITEM ===\n{set_text}\n\n=== SCENARIO ===\n{prompt}"
        if prior_ctx:
            user_content = f"=== ITS OBJECTIVE ===\n{prior_ctx}\n\n{user_content}"
        user_content = self._with_retrieval(design_brief, "rubric_designer", user_content)
        response = self._call_llm([
            {"role": "system", "content": _SYSTEM},
            {"role": "user", "content": user_content},
        ])
        parsed = parse_json_response(response)
        items = parsed.get("rubric_criteria", [])
        self.trajectory.log_step(
            "RubricDeveloperAgent", f"design_rubrics_{work_set.set_id}",
            prompt[:200], response[:200] if response else "",
        )
        return {
            "family": "rubric_designer", "set_id": work_set.set_id,
            "items": items if isinstance(items, list) else [],
        }

    def _objective_context(self, work_set) -> str:
        lo_refs = {
            str(item.get("aligned_objective", "")) for item in (work_set.payload.get("items") or [])
            if item.get("aligned_objective")
        }
        if not lo_refs:
            return ""
        if self._graph_mode:
            from ..alignment_graph import NodeType
            lo_nodes = [n for n in self.graph.element_nodes(NodeType.OBJECTIVE) if self._bare(n["id"]) in lo_refs]
            return self._element_context(lo_nodes)
        return self._store_context(("objective",))

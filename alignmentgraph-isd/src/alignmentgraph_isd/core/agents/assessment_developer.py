from __future__ import annotations
from ..brief import DesignBrief
from .. import rulebook as rules
from ..dev_plans import render_assessment_set as _render_work_set
from .base import BaseISDAgent, _format_design_brief, parse_json_response

_SYSTEM = f"""\
You are an expert instructional designer developing ONE assessment instrument set (ADDIE
Development phase) — writing the actual items for exactly the objectives and plan categories
your assigned set names. You are NOT responsible for any other objective or category; another
Developer is handling those.

Given a training scenario and your assigned instrument set, produce ONLY valid JSON with this
EXACT schema:
{rules.SCHEMA_ASSESSMENT_ITEMS}

{rules.RULES_ASSESSMENT_ITEMS_SET}
{rules.JSON_ONLY}"""


class AssessmentDeveloperAgent(BaseISDAgent):
    """Spawned once per instrument set by AssessmentDesignerAgent's fan-out
    (``assessment_developer`` node in ``core/workflow.py``): one LLM call
    producing items for exactly the (objective, plan_category) pairs its
    assigned :class:`core.dev_plans.WorkSet` names. Makes no graph/store
    writes and owns no violation types of its own — AssessmentDesignerAgent
    commits and self-validates the pooled result at ``finalize()``.
    """

    def run(self, design_brief: DesignBrief) -> None:  # pragma: no cover
        raise NotImplementedError(
            "AssessmentDeveloperAgent is driven via run_worker(work_set, design_brief), not run().")

    def run_worker(self, work_set, design_brief: DesignBrief) -> dict:
        prompt = _format_design_brief(design_brief)
        set_text = _render_work_set(work_set)
        prior_ctx = self._objective_context(work_set)
        user_content = f"=== YOUR ASSIGNED SET ===\n{set_text}\n\n=== SCENARIO ===\n{prompt}"
        if prior_ctx:
            user_content = f"=== YOUR OBJECTIVES ===\n{prior_ctx}\n\n{user_content}"
        user_content = self._with_retrieval(design_brief, "assessment_designer", user_content)
        response = self._call_llm([
            {"role": "system", "content": _SYSTEM},
            {"role": "user", "content": user_content},
        ])
        parsed = parse_json_response(response)
        items = parsed.get("assessment_tools", [])
        self.trajectory.log_step(
            "AssessmentDeveloperAgent", f"develop_assessments_{work_set.set_id}",
            prompt[:200], response[:200] if response else "",
        )
        return {
            "family": "assessment_designer", "set_id": work_set.set_id,
            "items": items if isinstance(items, list) else [],
        }

    def _objective_context(self, work_set) -> str:
        lo_ids = {lo for lo, _ in work_set.pairs} | set(work_set.objectives)
        if not lo_ids:
            return ""
        if self._graph_mode:
            from ..alignment_graph import NodeType
            nodes = [n for n in self.graph.element_nodes(NodeType.OBJECTIVE) if self._bare(n["id"]) in lo_ids]
            return self._element_context(nodes)
        return self._store_context(("objective",))

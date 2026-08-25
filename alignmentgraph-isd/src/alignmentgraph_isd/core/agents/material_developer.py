from __future__ import annotations
from ..brief import DesignBrief
from .. import rulebook as rules
from ..dev_plans import render_material_set as _render_work_set
from .base import BaseISDAgent, _format_design_brief, parse_json_response

_SYSTEM = f"""\
You are an expert instructional designer developing learner materials for ONE content module
(ADDIE Development phase), realizing that module's media selections. You are NOT responsible
for any other module; another Developer is handling those.

Given a training scenario and your assigned module (with its media selections and the
constraints they respect), produce ONLY valid JSON with this EXACT schema:
{rules.SCHEMA_MATERIALS}

{rules.RULES_MATERIALS_UNIT}
{rules.JSON_ONLY}"""


class MaterialDeveloperAgent(BaseISDAgent):
    """Spawned once per content module by ContentDesignerAgent's fan-out
    (``content_developer`` node in ``core/workflow.py``): one LLM call
    producing materials for exactly the ONE module (and its own media
    selections) its assigned :class:`core.dev_plans.WorkSet` names. Every
    fact the call needs is already in the work set's payload (deterministic,
    computed at dispatch — see ``core/dev_plans.py::material_work_units``),
    so unlike the assessment/activity Developers this one needs no
    graph/store context lookup of its own. Makes no graph/store writes and
    owns no violation types — ContentDesignerAgent commits and self-validates
    the pooled result at ``finalize()``.
    """

    def run(self, design_brief: DesignBrief) -> None:  # pragma: no cover
        raise NotImplementedError(
            "MaterialDeveloperAgent is driven via run_worker(work_set, design_brief), not run().")

    def run_worker(self, work_set, design_brief: DesignBrief) -> dict:
        prompt = _format_design_brief(design_brief)
        set_text = _render_work_set(work_set)
        user_content = f"=== YOUR ASSIGNED MODULE ===\n{set_text}\n\n=== SCENARIO ===\n{prompt}"
        user_content = self._with_retrieval(design_brief, "content_designer", user_content)
        response = self._call_llm([
            {"role": "system", "content": _SYSTEM},
            {"role": "user", "content": user_content},
        ])
        parsed = parse_json_response(response)
        items = parsed.get("learner_materials", [])
        self.trajectory.log_step(
            "MaterialDeveloperAgent", f"develop_materials_{work_set.set_id}",
            prompt[:200], response[:200] if response else "",
        )
        return {
            "family": "content_designer", "set_id": work_set.set_id,
            "items": items if isinstance(items, list) else [],
        }

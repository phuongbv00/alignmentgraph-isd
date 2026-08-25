from __future__ import annotations
from ..alignment_graph import NodeType
from ..brief import DesignBrief
from ..alignment_graph import alignment
from .. import rulebook as rules
from .. import repairs
from .. import dev_plans
from .base import BaseISDAgent, _format_design_brief, parse_json_response
from .material_developer import MaterialDeveloperAgent

_SYSTEM_MODULES = f"""\
You are an expert instructional designer organizing course content (ADDIE Design phase).

Given a training scenario, its learning activities (TLA) and the topics identified during needs
analysis, produce ONLY valid JSON with this EXACT schema:
{rules.SCHEMA_CONTENT_MODULES}

{rules.RULES_CONTENT_MODULES}
{rules.JSON_ONLY}"""


class ContentDesignerAgent(BaseISDAgent):
    """New role; retires the material half of ActivityMaterialAgent and the
    content_structure/media_selection/storyboard fields of
    ObjectiveDesignAgent's call 2 (storyboard is now computed by the
    aggregator, not written here — see the aggregation matrix). Runs AFTER
    Activity Designer.

    Dev-plan fan-out (2026-08-28): unlike assessment/activity, the grouping
    here is DETERMINISTIC, not an LLM decision — a content module already
    IS the natural unit, enumerated by ``_run_modules_and_media``'s own
    single call (unchanged: design ContentModule + choose MediaSelection in
    one turn, still establishing C5/P7/P8 itself). Dispatch derives one
    :class:`core.dev_plans.WorkSet` per committed module
    (``dev_plans.material_work_units``); writing the actual materials is
    :class:`MaterialDeveloperAgent`'s job, one call per module, fanned out in
    parallel by the ``content_developer`` LangGraph node. This class commits
    the pooled result, re-establishes P5/P6, and self-validates at
    ``finalize()``.
    """

    OWNED_VIOLATION_TYPES = repairs.OWNED_BY_FAMILY["content_designer"]

    def __init__(self, config, graph, trajectory, store=None) -> None:
        super().__init__(config, graph, trajectory, store)
        self._work_sets: list[dev_plans.WorkSet] = []

    def run(self, design_brief: DesignBrief) -> None:
        self.run_dispatch(design_brief)
        developer = MaterialDeveloperAgent(self.config, self.graph, self.trajectory, self.store)
        payloads = [developer.run_worker(ws, design_brief) for ws in self._work_sets]
        self.finalize(self._work_sets, payloads, design_brief)

    def take_work_sets(self) -> list[dev_plans.WorkSet]:
        return list(self._work_sets)

    def dispatch_produced(self) -> bool:
        """``material_work_units`` never returns an empty list — zero
        modules degenerates to one ``MU-ALL`` unit (today's whole-pool call)
        rather than nothing — so ``take_work_sets()`` alone can't tell the
        outer regen loop whether the modules+media LLM call actually
        produced anything. Check the real artifact instead, mirroring what
        this hop's own emptiness meant before the fan-out existed."""
        if self._graph_mode:
            return bool(self.graph.element_nodes(NodeType.CONTENT))
        return bool(self.store.items("content", "content_modules"))

    # ── dispatch: modules+media (1 call, unchanged), then one unit per module ──
    def run_dispatch(self, design_brief: DesignBrief) -> None:
        if not self._graph_mode:
            self._run_dispatch_prose(design_brief)
            return
        self._run_modules_and_media(design_brief)
        modules = [{**n["data"], "id": self._bare(n["id"])} for n in self.graph.element_nodes(NodeType.CONTENT)]
        media = [{**n["data"], "id": self._bare(n["id"])} for n in self.graph.element_nodes(NodeType.MEDIA_SELECTION)]
        constraints = [{**n["data"], "id": self._bare(n["id"])} for n in self.graph.element_nodes(NodeType.CONSTRAINT)]
        self._work_sets = dev_plans.material_work_units(modules, media, constraints)
        self._log_dev_plan()

    def _log_dev_plan(self) -> None:
        self.trajectory.log_dev_plan(
            "content_designer", set_count=len(self._work_sets), pair_count=len(self._work_sets),
            sets=[
                {"set_id": ws.set_id,
                 "module": (ws.payload.get("modules") or [{}])[0].get("id", "")}
                for ws in self._work_sets
            ],
            source="deterministic", fallback_used=False, dropped_refs=0, appended_sets=0,
            agent="ContentDesignerAgent",
        )

    # ── Steps 1-2: design ContentModule, then choose MediaSelection ──────
    def _run_modules_and_media(self, design_brief: DesignBrief) -> None:
        if self.graph.element_nodes(NodeType.CONTENT):
            return
        prompt = _format_design_brief(design_brief)
        activity_nodes = self.graph.element_nodes(NodeType.ACTIVITY)
        topic_nodes = self.graph.element_nodes(NodeType.TOPIC)
        constraint_nodes = self.graph.element_nodes(NodeType.CONSTRAINT)
        prior_ctx = self._element_context(activity_nodes + topic_nodes + constraint_nodes)
        state_ctx = self._alignment_state_context(gaps=("C5",))
        user_content = prompt
        if prior_ctx:
            user_content = f"=== ACTIVITIES + TOPICS + CONSTRAINTS ===\n{prior_ctx}\n\n=== SCENARIO ===\n{prompt}"
        if state_ctx:
            user_content = f"{state_ctx}\n\n{user_content}"
        user_content = self._with_retrieval(design_brief, "content_designer", user_content)
        response = self._call_llm([
            {"role": "system", "content": _SYSTEM_MODULES},
            {"role": "user", "content": user_content},
        ])
        parsed = parse_json_response(response)

        module_ids = self._decompose_elements(NodeType.CONTENT, parsed.get("content_modules", []))
        for mid in module_ids:
            self.trajectory.log_node_edit("add", mid, NodeType.CONTENT)
        media_ids = self._decompose_elements(NodeType.MEDIA_SELECTION, parsed.get("media_selections", []))
        for mid in media_ids:
            self.trajectory.log_node_edit("add", mid, NodeType.MEDIA_SELECTION)

        # C5: content module supports the activities it declares (core).
        for module_id in module_ids:
            module = self.graph.get_node(module_id)
            for activity_ref in (module["data"].get("supports_activities") or []):
                activity_ref = alignment.bare_ref(activity_ref)
                activity_id = f"{NodeType.ACTIVITY}{self.graph.ELEMENT_SEP}{activity_ref}"
                alignment.record_provenance(self.graph, "C5", [module_id], activity_id)
        # P7: content module covers the topics it declares (secondary, cross-agent).
        for module_id in module_ids:
            module = self.graph.get_node(module_id)
            topic_ids = [
                f"{NodeType.TOPIC}{self.graph.ELEMENT_SEP}{alignment.bare_ref(ref)}"
                for ref in (module["data"].get("covers_topics") or [])
            ]
            alignment.record_provenance(self.graph, "P7", topic_ids, module_id)
        # P8: media selection constrained by the constraints it declares (secondary, cross-agent).
        for media_id in media_ids:
            media = self.graph.get_node(media_id)
            declared_constraints = [
                f"{NodeType.CONSTRAINT}{self.graph.ELEMENT_SEP}{alignment.bare_ref(ref)}"
                for ref in (media["data"].get("respects_constraints") or [])
            ]
            alignment.record_provenance(self.graph, "P8", declared_constraints, media_id)

        self.trajectory.log_step("ContentDesignerAgent", "design_content_modules", prompt[:200], response[:200] if response else "")

    # ── prose arm: same modules+media call, then one unit per module ──────
    def _run_dispatch_prose(self, design_brief: DesignBrief) -> None:
        prompt = _format_design_brief(design_brief)
        if not self.store.items("content", "content_modules"):
            prior_ctx = self._store_context(("activity", "analysis"))
            user_content = prompt
            if prior_ctx:
                user_content = f"=== ACTIVITIES + TOPICS + CONSTRAINTS ===\n{prior_ctx}\n\n=== SCENARIO ===\n{prompt}"
            user_content = self._with_retrieval(design_brief, "content_designer", user_content)
            response = self._call_llm([
                {"role": "system", "content": _SYSTEM_MODULES},
                {"role": "user", "content": user_content},
            ])
            self.store.put("content", parse_json_response(response))
            self.trajectory.log_step("ContentDesignerAgent", "design_content_modules", prompt[:200], response[:200] if response else "")

        modules = [dict(m) for m in self.store.items("content", "content_modules") if isinstance(m, dict)]
        media = [dict(m) for m in self.store.items("content", "media_selections") if isinstance(m, dict)]
        constraints = (
            (self.store.get("analysis") or {}).get("context_analysis") or {}
        ).get("constraints") or []
        constraints = [c for c in constraints if isinstance(c, dict)]
        self._work_sets = dev_plans.material_work_units(modules, media, constraints)
        self._log_dev_plan()

    # ── finalize: fan-in commit + per-set regen + relation matchers ───────
    def finalize(self, work_sets: list[dev_plans.WorkSet], payloads: list[dict],
                 design_brief: DesignBrief) -> None:
        developer = MaterialDeveloperAgent(self.config, self.graph, self.trajectory, self.store)
        payloads = self._regen_missing_sets(
            work_sets, payloads, developer, design_brief, "content_designer")
        merged = dev_plans.remap_and_tag(work_sets, payloads, id_field="id")

        if not self._graph_mode:
            doc = self.store.get("material") or {}
            existing = doc.get("learner_materials") or []
            self.store.put("material", {**doc, "learner_materials": existing + merged})
            return

        material_ids = self._decompose_elements(NodeType.MATERIAL, merged)
        for mid in material_ids:
            self.trajectory.log_node_edit("add", mid, NodeType.MATERIAL)

        # P5: content module covers the material (via the declared linked_module).
        for material_id in material_ids:
            material = self.graph.get_node(material_id)
            module_ref = alignment.bare_ref(material["data"].get("linked_module", ""))
            module_id = f"{NodeType.CONTENT}{self.graph.ELEMENT_SEP}{module_ref}" if module_ref else ""
            if module_ref and self.graph.get_node(module_id):
                alignment.record_provenance(self.graph, "P5", [module_id], material_id)
        # P6: media selection realized by material (type-match, no field).
        alignment.match_p6_realizes(self.graph)

    # ── self-validation ───────────────────────────────────────────────────
    def repair(self, violations: list) -> list:
        return repairs.repair("content_designer", violations, repairs.context_for(self))

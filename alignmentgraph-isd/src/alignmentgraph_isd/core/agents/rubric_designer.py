from __future__ import annotations
from ..alignment_graph import NodeType
from ..alignment_graph import alignment
from ..brief import DesignBrief
from .. import repairs
from .. import dev_plans
from .base import BaseISDAgent
from .rubric_developer import RubricDeveloperAgent


class RubricDesignerAgent(BaseISDAgent):
    """Entirely new role, no prior analog. Reads the finished Assessment
    pool + learning objectives; for each assessment item, writes one or more
    Rubric criteria, establishing C6 (Assessment evaluated_by Rubric,
    provenance — this agent traversed the item to create the criterion) and
    C7 (Rubric measures LO, standard id-match).

    Dev-plan fan-out (2026-08-28): unlike every other family, the grouping
    here needs no LLM decision — an assessment item already IS the natural
    work unit, and the pool of them is already fully known before this
    family ever runs (dispatch makes ZERO LLM calls: see
    ``dev_plans.rubric_work_units``, one :class:`core.dev_plans.WorkSet` per
    committed item). Writing the actual criteria is
    :class:`RubricDeveloperAgent`'s job, one call per item, fanned out in
    parallel by the ``rubric_developer`` LangGraph node. This class commits
    the pooled result, re-establishes C6/C7, and self-validates at
    ``finalize()``.
    """

    OWNED_VIOLATION_TYPES = repairs.OWNED_BY_FAMILY["rubric_designer"]

    def __init__(self, config, graph, trajectory, store=None) -> None:
        super().__init__(config, graph, trajectory, store)
        self._work_sets: list[dev_plans.WorkSet] = []

    def run(self, design_brief: DesignBrief) -> None:
        self.run_dispatch(design_brief)
        developer = RubricDeveloperAgent(self.config, self.graph, self.trajectory, self.store)
        payloads = [developer.run_worker(ws, design_brief) for ws in self._work_sets]
        self.finalize(self._work_sets, payloads, design_brief)

    def take_work_sets(self) -> list[dev_plans.WorkSet]:
        return list(self._work_sets)

    def dispatch_produced(self) -> bool:
        """Dispatch makes zero LLM calls — ``rubric_work_units`` is pure and
        deterministic over the committed assessment pool. An empty result
        means upstream produced zero assessment items, which retrying this
        hop cannot fix (it would compute the exact same empty result every
        time), so always report success and let the family's own empty-pool
        state surface downstream instead of burning the regen budget on a
        retry that cannot possibly change anything."""
        return True

    # ── dispatch: zero LLM calls, one unit per committed assessment item ──
    def run_dispatch(self, design_brief: DesignBrief) -> None:
        if not self._graph_mode:
            self._run_dispatch_prose(design_brief)
            return
        items = [
            {**n["data"], "item_id": self._bare(n["id"])}
            for n in self.graph.element_nodes(NodeType.ASSESSMENT)
        ]
        self._work_sets = dev_plans.rubric_work_units(items)
        self._log_dev_plan()

    def _run_dispatch_prose(self, design_brief: DesignBrief) -> None:
        items = [
            dict(tool) for tool in self.store.items("assessment", "assessment_tools")
            if isinstance(tool, dict)
        ]
        self._work_sets = dev_plans.rubric_work_units(items)
        self._log_dev_plan()

    def _log_dev_plan(self) -> None:
        self.trajectory.log_dev_plan(
            "rubric_designer", set_count=len(self._work_sets), pair_count=len(self._work_sets),
            sets=[
                {"set_id": ws.set_id,
                 "items": [item.get("item_id", "") for item in (ws.payload.get("items") or [])]}
                for ws in self._work_sets
            ],
            source="deterministic", fallback_used=False, dropped_refs=0, appended_sets=0,
            agent="RubricDesignerAgent",
        )

    # ── finalize: fan-in commit + per-set regen + relation matchers ───────
    def finalize(self, work_sets: list[dev_plans.WorkSet], payloads: list[dict],
                 design_brief: DesignBrief) -> None:
        developer = RubricDeveloperAgent(self.config, self.graph, self.trajectory, self.store)
        payloads = self._regen_missing_sets(
            work_sets, payloads, developer, design_brief, "rubric_designer")
        merged = dev_plans.remap_and_tag(work_sets, payloads, id_field="id")

        if not self._graph_mode:
            doc = self.store.get("rubric") or {}
            existing = doc.get("rubric_criteria") or []
            self.store.put("rubric", {**doc, "rubric_criteria": existing + merged})
            return

        rubric_ids = self._decompose_elements(NodeType.RUBRIC, merged)
        for rid in rubric_ids:
            self.trajectory.log_node_edit("add", rid, NodeType.RUBRIC)
            data = self.graph.get_node(rid)["data"]
            assessment_ref = alignment.bare_ref(data.get("aligned_assessment", ""))
            assessment_id = f"{NodeType.ASSESSMENT}{self.graph.ELEMENT_SEP}{assessment_ref}" if assessment_ref else ""
            if assessment_ref and self.graph.get_node(assessment_id):
                alignment.record_provenance(self.graph, "C6", [assessment_id], rid)
        alignment.match_id(self.graph, "C7", field="aligned_objective")

    # ── self-validation ───────────────────────────────────────────────────
    def repair(self, violations: list) -> list:
        return repairs.repair("rubric_designer", violations, repairs.context_for(self))

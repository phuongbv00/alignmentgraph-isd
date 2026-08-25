"""The `single` arm of the decomposition ablation axis — a designer written as
one agent, not five (now nine, with the dev-plan fan-out) agents wearing one
nametag.

Why this is a separate implementation rather than a loop over the Designers.
Role decomposition lives in two places: the persona a prompt opens with, and
**how the work is cut into questions**. An arm that reuses the Designer/
Developer classes inherits the second even after the first is neutralised: it
still asks the same number of separate questions with the same schemas, one
per specialist hop, which is task decomposition regardless of what the
trajectory labels it. So this agent owns its own prompt and its own state
machine, and cuts the work the way one designer would.

This module imports NOTHING from the specialist agents (Designer OR
Developer classes). What both arms consume instead is the shared substrate,
addressed from each side independently:

- **The rulebook** (``core/rulebook.py``): generation schemas and rules per
  artifact family, including the dev-plan/per-set rules added for the
  2026-08-28 fan-out. Specialist prompts compose persona + schema + rules
  from it; this arm's state machine composes its own merged/per-set task
  text from the SAME constants. The rules are identical by construction.
  ``tests/fixtures/golden_prompts.json`` pins every composed prompt
  byte-for-byte.
- **The dev-plan toolbox** (``core/dev_plans.py``): ``normalize_*_dev_plan``,
  ``material_work_units``/``rubric_work_units``, ``remap_and_tag``,
  ``pending_set_ids``, and the ``render_*_set`` work-set formatters — pure,
  substrate-agnostic functions neither arm's agent classes own, so reusing
  them here is not "borrowing the other arm's decomposition", it is drawing
  from the same shared toolbox the multi arm's Designers draw from too.
- **The repair toolbox** (``core/repairs.py``) and **safeguard scaffolding**
  (``NodeFactory.run_generation_step``, ``BaseISDAgent._regen_missing_sets``):
  empty-output regen (whole-state AND, since the fan-out, per-set), exception
  containment, the self-validation budget, and the deterministic repairs —
  identical in both arms because both call the same functions, not because
  this arm instantiates Designer/Developer classes.
- **The graph tools**: element decomposition, the relation establishers in
  ``alignment`` (including ``establish_delivery`` for P10/P11), and the graph
  itself. Re-implementing them would change the output contract, not the
  decomposition.

Four artifact families (assessment, activities, content, rubrics) are now
TWO-LEVEL here too, mirroring the multi arm's dispatch/develop split: one
call decides the plan/grouping (merged into ONE call for assessment/
activities, since deciding an approach and grouping it is one act for one
designer — collapsing hops is what this arm's axis manipulates; zero calls
for rubrics, whose grouping is deterministic in both arms), then one
SEQUENTIAL call per work set. Sequential, not parallel, by construction —
parallelism is part of what the multi arm's fan-out measures, and this arm's
state machine has always run everything in one thread. Analysis, outcomes,
and implementation are unchanged: a single call each, no fan-out (there is
nothing to group — the artifact IS one thing).
"""
from __future__ import annotations

from ..alignment_graph import NodeType
from ..brief import DesignBrief
from ..alignment_graph import alignment
from .. import rulebook as rules
from .. import dev_plans
from .base import BaseISDAgent, _format_design_brief, parse_json_response

#: One persona for the whole job. Compare the multi-agent arm, where each hop
#: (and, since the fan-out, each Developer) opens with its own specialist
#: framing ("You are ... performing the Analysis phase", "... writing
#: rubric criteria for ONE assessment item").
_SYSTEM = """\
You are ONE instructional designer, personally responsible for this entire course design from
analysis through evaluation. You are not part of a team and you are not handing work to anyone
else: every artifact here is your own, and each one has to stay consistent with what you already
decided earlier in the design.

You work through the design one artifact family at a time. For each, you decide the approach and
produce the concrete artifacts together — you do not write a plan for someone else to execute.

Always reply with ONLY a valid JSON object in the exact schema you are given. No markdown, no
commentary. Every <angle-bracket text> in a schema is a placeholder: replace it with real,
scenario-specific content, never copy it into the output.\
"""

# Each task = the SCHEMA this arm asks for (merged, for a family's dispatch
# call — that IS the manipulation) + the same rulebook rules the multi-agent
# prompts state. Only persona and granularity differ between the arms.

_TASK_ANALYSIS = f"""\
Analyse the situation: the performance gaps, who the learners are, what constrains delivery, what
has to be taught, and what you would improve.

{rules.SCHEMA_ANALYSIS}

{rules.RULES_ANALYSIS} {rules.JSON_ONLY}"""

_TASK_OUTCOMES = """\
State what this course is for and what learners will be able to do, grounded in YOUR analysis above.

""" + rules.SCHEMA_OUTCOMES + "\n\n" + rules.rules_for("outcomes")

# ── assessment: dispatch (plan + dev-plan grouping) then one call per set ───

_TASK_ASSESSMENT = """\
Decide how you will know learners met each objective, AND group that plan into instrument sets
so you can write each set's items in a focused pass later — the strategy and the grouping
together, in ONE object merging both of these:

""" + rules.SCHEMA_ASSESSMENT_PLAN + "\n\n" + rules.SCHEMA_ASSESSMENT_DEV_PLAN + "\n\n" \
    + rules.RULES_ASSESSMENT_PLAN.strip() + "\n\n" + rules.RULES_ASSESSMENT_DEV_PLAN.strip() + "\n" + rules.JSON_ONLY

_TASK_ASSESSMENT_ITEMS = """\
Write the actual items for YOUR ASSIGNED instrument set below.

""" + rules.SCHEMA_ASSESSMENT_ITEMS + "\n\n" + rules.RULES_ASSESSMENT_ITEMS_SET.strip() + "\n" + rules.JSON_ONLY

# ── activities: dispatch (strategy + block grouping) then one call per block ─

_TASK_ACTIVITIES = """\
Design how learners spend their time, AND group the objectives into activity blocks so you can
write each block's activities in a focused pass later — the approach and the grouping together,
in ONE object merging both of these:

""" + rules.SCHEMA_ACTIVITY_PLAN + "\n\n" + rules.SCHEMA_ACTIVITY_DEV_PLAN + "\n\n" \
    + rules.RULES_ACTIVITY_PLAN.strip() + "\n\n" + rules.RULES_ACTIVITY_DEV_PLAN.strip() + "\n" + rules.JSON_ONLY

_TASK_ACTIVITY_SET = """\
Write the actual learning activities for YOUR ASSIGNED block below.

""" + rules.SCHEMA_ACTIVITIES + "\n\n" + rules.RULES_ACTIVITIES_SET.strip() + "\n" + rules.JSON_ONLY

# ── content: dispatch (modules + media only) then one call per module ──────

_TASK_CONTENT = """\
Decide how the content is organised and what form it takes: the modules and the media selections
that realise them.

""" + rules.SCHEMA_CONTENT_MODULES + "\n\n" + rules.RULES_CONTENT_MODULES.strip() + "\n" + rules.JSON_ONLY

_TASK_MATERIALS_UNIT = """\
Produce the actual materials for YOUR ASSIGNED module below.

""" + rules.SCHEMA_MATERIALS + "\n\n" + rules.RULES_MATERIALS_UNIT.strip() + "\n" + rules.JSON_ONLY

_TASK_IMPLEMENTATION = f"""\
Plan how this design is actually delivered: what instructors and operators need, and which
activities and materials each session carries.

{rules.SCHEMA_IMPLEMENTATION}

{rules.RULES_IMPLEMENTATION}
{rules.JSON_ONLY}"""

# ── rubrics: no dispatch call (grouping is deterministic in both arms) ─────

_TASK_RUBRICS = """\
Write the scoring criteria for YOUR ASSIGNED assessment item below.

""" + rules.SCHEMA_RUBRICS + "\n\n" + rules.RULES_RUBRICS_ITEM.strip() + "\n" + rules.JSON_ONLY


# A `_SetRunner` adapter used to live here, wrapping this agent's per-set call
# in the ``run_worker`` contract so `BaseISDAgent._regen_missing_sets` could
# drive it. It was removed 2026-08-30: that inner retry sat UNDERNEATH
# `run_generation_step`'s outer `_regen_loop`, so the two budgets multiplied
# and a stubborn work set got `(1 + regen_budget)^2` attempts against the multi
# arm's `1 + regen_budget` (measured: 9 vs 3). `_run_fanout_state` is
# re-entrant, so the outer loop alone now gives both arms the same ceiling.


class SingleDesignerAgent(BaseISDAgent):
    """One designer, one persona, one state machine over artifact families."""

    IDENTITY = "SingleDesignerAgent"

    #: States whose artifact family uses the dev-plan fan-out in the multi
    #: arm too — see ``run_state``/``_run_fanout_state``.
    _FANOUT_STATES = frozenset({"assessment", "activities", "content", "rubrics"})

    _DISPATCH_TASK: dict = {
        "assessment": _TASK_ASSESSMENT, "activities": _TASK_ACTIVITIES, "content": _TASK_CONTENT,
    }
    _SET_TASK: dict = {
        "assessment": _TASK_ASSESSMENT_ITEMS, "activities": _TASK_ACTIVITY_SET,
        "content": _TASK_MATERIALS_UNIT, "rubrics": _TASK_RUBRICS,
    }
    _SET_RENDER: dict = {
        "assessment": dev_plans.render_assessment_set, "activities": dev_plans.render_activity_set,
        "content": dev_plans.render_material_set, "rubrics": dev_plans.render_rubric_set,
    }
    _SET_SCHEMA_KEY: dict = {
        "assessment": "assessment_tools", "activities": "learning_activities",
        "content": "learner_materials", "rubrics": "rubric_criteria",
    }
    _FAMILY: dict = {
        "assessment": "assessment_designer", "activities": "activity_designer",
        "content": "content_designer", "rubrics": "rubric_designer",
    }
    _ID_FIELD: dict = {"assessment": "item_id", "activities": "id", "content": "id", "rubrics": "id"}
    _REF_FIELDS: dict = {"activities": ("prerequisite_activities",)}
    _ELEMENT_TYPE: dict = {
        "assessment": NodeType.ASSESSMENT, "activities": NodeType.ACTIVITY,
        "content": NodeType.MATERIAL, "rubrics": NodeType.RUBRIC,
    }
    _DOC_KEY: dict = {
        "assessment": ("assessment", "assessment_tools"), "activities": ("activity", "learning_activities"),
        "content": ("material", "learner_materials"), "rubrics": ("rubric", "rubric_criteria"),
    }

    #: The state machine, in order. Each entry is
    #: (state, dispatch/whole-state task prompt, primary artifact type,
    #: artifact family — the key the shared checks and repair toolbox are
    #: addressed by). For a fan-out state the task here is the DISPATCH
    #: prompt (or, for rubrics, unused — its grouping needs no LLM call);
    #: the per-set task lives in ``_SET_TASK``.
    #:
    #: Seven states against the multi-agent pipeline's ten-plus-fan-out node
    #: set: analysis and outcomes stay separate because the second genuinely
    #: depends on the first, but every plan/execute pair is collapsed —
    #: deciding an approach and producing the artifacts (or, for the three
    #: dev-plan families, deciding an approach AND grouping it) is one act
    #: for one designer, and splitting it is precisely the decomposition
    #: under test.
    STATES: tuple[tuple[str, str, str, str], ...] = (
        ("analysis", _TASK_ANALYSIS, NodeType.GAP, "outcome_designer"),
        ("outcomes", _TASK_OUTCOMES, NodeType.OBJECTIVE, "outcome_designer"),
        ("assessment", _TASK_ASSESSMENT, NodeType.ASSESSMENT, "assessment_designer"),
        ("activities", _TASK_ACTIVITIES, NodeType.ACTIVITY, "activity_designer"),
        ("content", _TASK_CONTENT, NodeType.MATERIAL, "content_designer"),
        ("rubrics", _TASK_RUBRICS, NodeType.RUBRIC, "rubric_designer"),
        # The implementation planner is a specialist in the multi arm, so the
        # single agent has to cover it too — otherwise this arm would keep a
        # second persona for it and the decomposition contrast would be
        # skewed rather than clean.
        ("implementation", _TASK_IMPLEMENTATION, NodeType.IMPLEMENTATION_PLAN, "implementation_planner"),
    )

    def __init__(self, config, graph, trajectory, store=None) -> None:
        super().__init__(config, graph, trajectory, store)
        #: Per-state work sets, memoized for the agent instance's lifetime —
        #: populated the FIRST time a fan-out state's dispatch runs, read by
        #: every subsequent regen re-entry of that same state (the outer
        #: run_generation_step regen loop calls run_state again on the SAME
        #: agent instance, never a fresh one, for one node's whole lifetime).
        self._work_sets: dict[str, list[dev_plans.WorkSet]] = {}

    def run(self, design_brief: DesignBrief) -> None:
        """Direct entry (tests, API use). The graph builder drives the states
        one at a time instead, so each gets the same regen and
        self-validation scaffolding a multi-agent node gets."""
        for state, _task, _primary, _family in self.STATES:
            self.run_state(state, design_brief)

    # ── the state machine ──────────────────────────────────────────────────
    def run_state(self, state: str, design_brief: DesignBrief) -> None:
        # Read by produced() (see below) after run_state returns -- the outer
        # regen loop's produced-check has no state parameter of its own to
        # pass, so it needs this agent instance to remember which state it
        # was just asked to run.
        self._last_state = state
        if state in self._FANOUT_STATES:
            self._run_fanout_state(state, design_brief)
            return
        task = dict((s, t) for s, t, _p, _f in self.STATES)[state]
        if self._already_done(state):
            return
        prompt = _format_design_brief(design_brief)
        context = self._context_for(state)
        user_content = f"{task}\n\n=== SCENARIO ===\n{prompt}"
        if context:
            user_content = (f"{task}\n\n=== WHAT YOU HAVE DESIGNED SO FAR ===\n{context}"
                            f"\n\n=== SCENARIO ===\n{prompt}")
        user_content = self._with_retrieval(design_brief, "single_designer", user_content)
        response = self._call_llm([
            {"role": "system", "content": _SYSTEM},
            {"role": "user", "content": user_content},
        ])
        parsed = parse_json_response(response)
        if self._graph_mode:
            getattr(self, f"_commit_{state}")(parsed)
        else:
            self._commit_prose(state, parsed)
        self.trajectory.log_step(
            self.IDENTITY, f"design_{state}", prompt[:200], response[:200] if response else "")

    # ── fan-out states: dispatch (memoized) -> per-set calls -> commit ─────
    def produced(self) -> bool:
        """Per-set-aware produced predicate for the outer regen loop (see
        ``NodeFactory.run_generation_step``'s ``getattr(agent, "produced",
        None)`` hook, and ``_SingleStateStep.produced`` which delegates
        here): for a fan-out state, plan/dispatch committed AND every work
        set this state currently knows about has been realised — the coarse
        "primary pool non-empty" check ``_already_done`` uses would call a
        state "done" the moment ONE set landed anything, masking still-
        pending sets. For every other state, ``_already_done`` already means
        exactly this. Only meaningful for the state ``run_state`` was most
        recently asked to run (it stamps ``_last_state` unconditionally)."""
        state = self._last_state
        if state not in self._FANOUT_STATES:
            return self._already_done(state)
        work_sets = self._work_sets.get(state) or []
        if not work_sets:
            return False
        committed = self._committed_set_ids(state)
        return all(ws.set_id in committed for ws in work_sets)

    def _run_fanout_state(self, state: str, design_brief: DesignBrief) -> None:
        work_sets = self._run_dispatch(state, design_brief)
        committed = self._committed_set_ids(state)
        pending = [ws for ws in work_sets if ws.set_id not in committed]
        if not pending:
            return
        payloads = [self._run_set(state, ws, design_brief) for ws in pending]
        # NO inner `_regen_missing_sets` here. This method is re-entrant --
        # `committed`/`pending` are recomputed above on every call and
        # `_run_dispatch` is memoized -- so the OUTER `_regen_loop` in
        # `NodeFactory.run_generation_step` already retries exactly the sets
        # that came back empty, giving each set `1 + regen_budget` attempts:
        # the same ceiling the multi arm gets from `_regen_missing_sets` in
        # `finalize_node`. Doing both stacked the budgets to
        # `(1 + budget)^2` (9 attempts against multi's 3) and made the
        # decomposition axis partly measure retry effort (audit 2026-08-30).
        self._commit_sets(state, pending, payloads)

    def _committed_set_ids(self, state: str) -> set[str]:
        if not self._graph_mode:
            doc_key, field = self._DOC_KEY[state]
            items = self.store.items(doc_key, field)
            return {i.get("plan_set") for i in items if isinstance(i, dict) and i.get("plan_set")}
        node_type = self._ELEMENT_TYPE[state]
        return {
            n["data"].get("plan_set") for n in self.graph.element_nodes(node_type)
            if n["data"].get("plan_set")
        }

    def _run_dispatch(self, state: str, design_brief: DesignBrief) -> list[dev_plans.WorkSet]:
        if state in self._work_sets:
            return self._work_sets[state]
        if state == "rubrics":
            sets = self._rubric_work_sets()
            self._work_sets[state] = sets
            return sets
        if self._dispatch_done(state):
            # Defensive only: normal operation always populates the cache
            # above in the SAME call that commits the plan/dev-plan hop, for
            # this agent instance's whole lifetime (see __init__) — this path
            # is for a graph/store this agent instance did not itself
            # dispatch into. Recompute via the pure fallback, no LLM re-call.
            sets = self._fallback_work_sets(state)
            self._work_sets[state] = sets
            return sets
        task = self._DISPATCH_TASK[state]
        prompt = _format_design_brief(design_brief)
        context = self._context_for(state)
        user_content = f"{task}\n\n=== SCENARIO ===\n{prompt}"
        if context:
            user_content = (f"{task}\n\n=== WHAT YOU HAVE DESIGNED SO FAR ===\n{context}"
                            f"\n\n=== SCENARIO ===\n{prompt}")
        user_content = self._with_retrieval(design_brief, "single_designer", user_content)
        response = self._call_llm([
            {"role": "system", "content": _SYSTEM},
            {"role": "user", "content": user_content},
        ])
        parsed = parse_json_response(response)
        sets = self._commit_dispatch(state, parsed)
        self.trajectory.log_step(
            self.IDENTITY, f"design_{state}", prompt[:200], response[:200] if response else "")
        self._work_sets[state] = sets
        return sets

    def _dispatch_done(self, state: str) -> bool:
        if state == "assessment":
            if self._graph_mode:
                return self.graph.get_node(self.graph.section_id(NodeType.ASSESSMENT_PLAN)) is not None
            return self.store.has("assessment_plan")
        if state == "activities":
            if self._graph_mode:
                return self.graph.get_node(self.graph.section_id(NodeType.ACTIVITY_PLAN)) is not None
            return self.store.has("activity_plan")
        if state == "content":
            if self._graph_mode:
                return bool(self.graph.element_nodes(NodeType.CONTENT))
            return bool(self.store.items("content", "content_modules"))
        return True

    def _commit_dispatch(self, state: str, parsed: dict) -> list[dev_plans.WorkSet]:
        if state == "assessment":
            plan = parsed.get("assessment_plan") or {}
            if self._graph_mode:
                self.graph.add_node(
                    NodeType.ASSESSMENT_PLAN, self.graph.section_id(NodeType.ASSESSMENT_PLAN), plan)
                lo_ids = [self._bare(n["id"]) for n in self.graph.element_nodes(NodeType.OBJECTIVE)]
            else:
                self.store.put("assessment_plan", plan)
                lo_ids = [
                    str(lo.get("id", "")) for lo in self.store.items("objective", "learning_objectives")
                    if isinstance(lo, dict) and lo.get("id")
                ]
            sets, stats = dev_plans.normalize_assessment_dev_plan(parsed, lo_ids, plan.get("lo_coverage_targets"))
            self._log_dev_plan("assessment_designer", sets, stats)
            return sets

        if state == "activities":
            plan_data = {
                "instructional_strategies": parsed.get("instructional_strategies") or {},
                "non_instructional_strategies": parsed.get("non_instructional_strategies") or {},
            }
            if self._graph_mode:
                self.graph.add_node(NodeType.ACTIVITY_PLAN, self.graph.section_id(NodeType.ACTIVITY_PLAN), plan_data)
                lo_nodes = self.graph.element_nodes(NodeType.OBJECTIVE)
                lo_ids = [self._bare(n["id"]) for n in lo_nodes]
                items_by_lo = {
                    self._bare(lo["id"]): [
                        self._bare(edge["target"])
                        for edge in self.graph.get_edges(relation_id="C2", source=lo["id"])
                    ]
                    for lo in lo_nodes
                }
            else:
                self.store.put("activity_plan", plan_data)
                lo_ids = [
                    str(lo.get("id", "")) for lo in self.store.items("objective", "learning_objectives")
                    if isinstance(lo, dict) and lo.get("id")
                ]
                items_by_lo = {}
                for tool in self.store.items("assessment", "assessment_tools"):
                    if not isinstance(tool, dict):
                        continue
                    lo, item_id = str(tool.get("aligned_objective", "")), str(tool.get("item_id", ""))
                    if lo and item_id:
                        items_by_lo.setdefault(lo, []).append(item_id)
            sets, stats = dev_plans.normalize_activity_dev_plan(parsed, lo_ids, items_by_lo)
            self._log_dev_plan("activity_designer", sets, stats)
            return sets

        if state == "content":
            modules_raw, media_raw = parsed.get("content_modules", []), parsed.get("media_selections", [])
            if self._graph_mode:
                module_ids = self._decompose_elements(NodeType.CONTENT, modules_raw)
                for mid in module_ids:
                    self.trajectory.log_node_edit("add", mid, NodeType.CONTENT)
                media_ids = self._decompose_elements(NodeType.MEDIA_SELECTION, media_raw)
                for mid in media_ids:
                    self.trajectory.log_node_edit("add", mid, NodeType.MEDIA_SELECTION)
                for module_id in module_ids:
                    module = self.graph.get_node(module_id)
                    for ref in (module["data"].get("supports_activities") or []):
                        activity_id = f"{NodeType.ACTIVITY}{self.graph.ELEMENT_SEP}{alignment.bare_ref(ref)}"
                        alignment.record_provenance(self.graph, "C5", [module_id], activity_id)
                for module_id in module_ids:
                    module = self.graph.get_node(module_id)
                    topic_ids = [
                        f"{NodeType.TOPIC}{self.graph.ELEMENT_SEP}{alignment.bare_ref(r)}"
                        for r in (module["data"].get("covers_topics") or [])
                    ]
                    alignment.record_provenance(self.graph, "P7", topic_ids, module_id)
                for media_id in media_ids:
                    media = self.graph.get_node(media_id)
                    constraints = [
                        f"{NodeType.CONSTRAINT}{self.graph.ELEMENT_SEP}{alignment.bare_ref(r)}"
                        for r in (media["data"].get("respects_constraints") or [])
                    ]
                    alignment.record_provenance(self.graph, "P8", constraints, media_id)
                modules = [{**n["data"], "id": self._bare(n["id"])} for n in self.graph.element_nodes(NodeType.CONTENT)]
                media = [{**n["data"], "id": self._bare(n["id"])} for n in self.graph.element_nodes(NodeType.MEDIA_SELECTION)]
                constraints = [{**n["data"], "id": self._bare(n["id"])} for n in self.graph.element_nodes(NodeType.CONSTRAINT)]
            else:
                self.store.put("content", {"content_modules": modules_raw, "media_selections": media_raw})
                modules = [dict(m) for m in self.store.items("content", "content_modules") if isinstance(m, dict)]
                media = [dict(m) for m in self.store.items("content", "media_selections") if isinstance(m, dict)]
                constraints = ((self.store.get("analysis") or {}).get("context_analysis") or {}).get("constraints") or []
                constraints = [c for c in constraints if isinstance(c, dict)]
            sets = dev_plans.material_work_units(modules, media, constraints)
            self._log_dev_plan("content_designer", sets)
            return sets

        return []

    def _fallback_work_sets(self, state: str) -> list[dev_plans.WorkSet]:
        """Recompute a state's work sets from already-committed data, with no
        LLM call — the defensive path noted in ``_run_dispatch``."""
        if state == "assessment":
            if self._graph_mode:
                plan_node = self.graph.get_node(self.graph.section_id(NodeType.ASSESSMENT_PLAN))
                plan_data = (plan_node or {}).get("data") or {}
                lo_ids = [self._bare(n["id"]) for n in self.graph.element_nodes(NodeType.OBJECTIVE)]
            else:
                plan_data = self.store.get("assessment_plan") or {}
                lo_ids = [
                    str(lo.get("id", "")) for lo in self.store.items("objective", "learning_objectives")
                    if isinstance(lo, dict) and lo.get("id")
                ]
            sets, stats = dev_plans.normalize_assessment_dev_plan({}, lo_ids, plan_data.get("lo_coverage_targets"))
            self._log_dev_plan("assessment_designer", sets, stats)
            return sets
        if state == "activities":
            if self._graph_mode:
                lo_ids = [self._bare(n["id"]) for n in self.graph.element_nodes(NodeType.OBJECTIVE)]
            else:
                lo_ids = [
                    str(lo.get("id", "")) for lo in self.store.items("objective", "learning_objectives")
                    if isinstance(lo, dict) and lo.get("id")
                ]
            sets, stats = dev_plans.normalize_activity_dev_plan({}, lo_ids, {})
            self._log_dev_plan("activity_designer", sets, stats)
            return sets
        if state == "content":
            if self._graph_mode:
                modules = [{**n["data"], "id": self._bare(n["id"])} for n in self.graph.element_nodes(NodeType.CONTENT)]
                media = [{**n["data"], "id": self._bare(n["id"])} for n in self.graph.element_nodes(NodeType.MEDIA_SELECTION)]
                constraints = [{**n["data"], "id": self._bare(n["id"])} for n in self.graph.element_nodes(NodeType.CONSTRAINT)]
            else:
                modules = [dict(m) for m in self.store.items("content", "content_modules") if isinstance(m, dict)]
                media = [dict(m) for m in self.store.items("content", "media_selections") if isinstance(m, dict)]
                constraints = []
            sets = dev_plans.material_work_units(modules, media, constraints)
            self._log_dev_plan("content_designer", sets)
            return sets
        return []

    def _rubric_work_sets(self) -> list[dev_plans.WorkSet]:
        if self._graph_mode:
            items = [
                {**n["data"], "item_id": self._bare(n["id"])} for n in self.graph.element_nodes(NodeType.ASSESSMENT)
            ]
        else:
            items = [dict(t) for t in self.store.items("assessment", "assessment_tools") if isinstance(t, dict)]
        sets = dev_plans.rubric_work_units(items)
        self._log_dev_plan("rubric_designer", sets)
        return sets

    def _log_dev_plan(self, family: str, sets: list[dev_plans.WorkSet], stats: dict | None = None) -> None:
        deterministic = stats is None
        if stats is None:
            stats = {"set_count": len(sets), "pair_count": len(sets), "dropped_lo_refs": 0,
                      "appended_sets": 0, "fallback_used": False}
        summary = []
        for ws in sets:
            entry: dict = {"set_id": ws.set_id}
            if ws.objectives:
                entry["objectives"] = list(ws.objectives)
            if ws.pairs:
                entry["categories"] = sorted({category for _, category in ws.pairs})
            summary.append(entry)
        self.trajectory.log_dev_plan(
            family, set_count=stats["set_count"], pair_count=stats["pair_count"], sets=summary,
            source="deterministic" if deterministic else ("fallback" if stats["fallback_used"] else "llm"),
            fallback_used=stats["fallback_used"], dropped_refs=stats["dropped_lo_refs"],
            appended_sets=stats["appended_sets"], agent=self.IDENTITY,
        )

    def _run_set(self, state: str, work_set: dev_plans.WorkSet, design_brief: DesignBrief) -> dict:
        task = self._SET_TASK[state]
        set_text = self._SET_RENDER[state](work_set)
        prompt = _format_design_brief(design_brief)
        prior_ctx = self._set_context(state, work_set)
        # `task` (carrying the schema) stays FIRST no matter what -- the same
        # convention every other single-arm call follows (see run_state/
        # _run_dispatch). Unlike a multi-arm Developer, whose schema lives in
        # a dedicated system prompt untouched by anything in user content,
        # this arm's ONE persona system message carries no schema at all, so
        # the schema's position here is load-bearing for a plain model too:
        # it must read as the task, not as a trailing fragment after two
        # "=== ... ===" context blocks.
        user_content = f"{task}\n\n=== YOUR ASSIGNED SET ===\n{set_text}\n\n=== SCENARIO ===\n{prompt}"
        if prior_ctx:
            user_content = (f"{task}\n\n=== YOUR OBJECTIVES ===\n{prior_ctx}"
                            f"\n\n=== YOUR ASSIGNED SET ===\n{set_text}\n\n=== SCENARIO ===\n{prompt}")
        user_content = self._with_retrieval(design_brief, "single_designer", user_content)
        response = self._call_llm([
            {"role": "system", "content": _SYSTEM},
            {"role": "user", "content": user_content},
        ])
        parsed = parse_json_response(response)
        items = parsed.get(self._SET_SCHEMA_KEY[state], [])
        self.trajectory.log_step(
            self.IDENTITY, f"design_{state}_{work_set.set_id}", prompt[:200], response[:200] if response else "")
        return {
            "family": self._FAMILY[state], "set_id": work_set.set_id,
            "items": items if isinstance(items, list) else [],
        }

    def _set_context(self, state: str, work_set: dev_plans.WorkSet) -> str:
        if state == "assessment":
            lo_ids = {lo for lo, _ in work_set.pairs} | set(work_set.objectives)
            return self._objective_context(lo_ids)
        if state == "activities":
            return self._objective_context(set(work_set.objectives), with_assessment=True)
        if state == "rubrics":
            lo_refs = {
                str(item.get("aligned_objective", "")) for item in (work_set.payload.get("items") or [])
                if item.get("aligned_objective")
            }
            return self._objective_context(lo_refs)
        return ""

    def _objective_context(self, lo_ids: set[str], *, with_assessment: bool = False) -> str:
        if not lo_ids:
            return ""
        if not self._graph_mode:
            return self._store_context(("objective", "assessment") if with_assessment else ("objective",))
        lo_nodes = [n for n in self.graph.element_nodes(NodeType.OBJECTIVE) if self._bare(n["id"]) in lo_ids]
        if not with_assessment:
            return self._element_context(lo_nodes)
        relevant_item_ids = {
            edge["target"] for lo in lo_nodes
            for edge in self.graph.get_edges(relation_id="C2", source=lo["id"])
        }
        assessment_nodes = [n for n in self.graph.element_nodes(NodeType.ASSESSMENT) if n["id"] in relevant_item_ids]
        return self._element_context_joined(lo_nodes, assessment_nodes, "C2", "assessed by")

    def _commit_sets(self, state: str, work_sets: list[dev_plans.WorkSet], payloads: list[dict]) -> None:
        merged = dev_plans.remap_and_tag(
            work_sets, payloads, id_field=self._ID_FIELD[state], ref_fields=self._REF_FIELDS.get(state, ()))

        if not self._graph_mode:
            doc_key, field = self._DOC_KEY[state]
            doc = self.store.get(doc_key) or {}
            existing = doc.get(field) or []
            self.store.put(doc_key, {**doc, field: existing + merged})
            return

        node_type = self._ELEMENT_TYPE[state]
        node_ids = self._decompose_elements(node_type, merged, id_field=self._ID_FIELD[state])
        for node_id in node_ids:
            self.trajectory.log_node_edit("add", node_id, node_type)

        if state == "assessment":
            alignment.match_id_reverse(self.graph, "C2", field="aligned_objective")
            alignment.match_p3_realizes(self.graph)
        elif state == "activities":
            alignment.match_list_reverse(self.graph, "C3", field="aligned_objectives")
            alignment.match_list(self.graph, "C4", field="prepares_for_assessment")
            plan_id = self.graph.section_id(NodeType.ACTIVITY_PLAN)
            if self.graph.get_node(plan_id):
                for node_id in node_ids:
                    alignment.record_provenance(self.graph, "P4", [plan_id], node_id)
            for node_id in node_ids:
                node = self.graph.get_node(node_id)
                if not node:
                    continue
                for prereq in node["data"].get("prerequisite_activities", []) or []:
                    prereq_id = f"{NodeType.ACTIVITY}{self.graph.ELEMENT_SEP}{prereq}"
                    if self.graph.get_node(prereq_id):
                        self.graph.add_edge(
                            "precedes", prereq_id, node_id, established_by="provenance",
                            rationale=f"{node_id} declares {prereq_id} as a prerequisite.")
        elif state == "content":
            for node_id in node_ids:
                material = self.graph.get_node(node_id)
                module_ref = alignment.bare_ref(material["data"].get("linked_module", ""))
                module_id = f"{NodeType.CONTENT}{self.graph.ELEMENT_SEP}{module_ref}" if module_ref else ""
                if module_ref and self.graph.get_node(module_id):
                    alignment.record_provenance(self.graph, "P5", [module_id], node_id)
            alignment.match_p6_realizes(self.graph)
        elif state == "rubrics":
            for node_id in node_ids:
                data = self.graph.get_node(node_id)["data"]
                assessment_ref = alignment.bare_ref(data.get("aligned_assessment", ""))
                assessment_id = f"{NodeType.ASSESSMENT}{self.graph.ELEMENT_SEP}{assessment_ref}" if assessment_ref else ""
                if assessment_ref and self.graph.get_node(assessment_id):
                    alignment.record_provenance(self.graph, "C6", [assessment_id], node_id)
            alignment.match_id(self.graph, "C7", field="aligned_objective")

    # ── prose arm: blackboard commits, one put per document the multi arm's
    # matching step would deposit (analysis/outcomes/implementation only —
    # the four fan-out families commit via _commit_dispatch/_commit_sets) ──
    def _commit_prose(self, state: str, parsed: dict) -> None:
        if state == "analysis":
            if parsed:
                self.store.put("analysis", parsed)
        elif state == "outcomes":
            self.store.put("objective", parsed)
        elif state == "implementation":
            self.store.put("implementation_plan", parsed)

    def _commit_implementation(self, parsed: dict) -> None:
        node_id = self.graph.section_id(NodeType.IMPLEMENTATION_PLAN)
        self.graph.add_node(NodeType.IMPLEMENTATION_PLAN, node_id, parsed)
        self.trajectory.log_node_edit("add", node_id, NodeType.IMPLEMENTATION_PLAN)
        # P10/P11 via the shared establisher — the same tool the multi arm's
        # planner calls, not a second copy that can drift from it.
        alignment.establish_delivery(self.graph, node_id, parsed)

    def _already_done(self, state: str) -> bool:
        """Idempotence guard for the NON-fan-out states (analysis, outcomes,
        implementation), so a node-level regen re-runs only what is still
        missing. Fan-out states are re-entrant by construction instead (see
        ``_run_fanout_state``: dispatch is self-guarded, per-set calls skip
        already-committed sets) — a single "is this whole family done" gate
        would skip STILL-PENDING sets the moment any one item existed."""
        primary = dict((s, p) for s, _t, p, _f in self.STATES)[state]
        if primary == NodeType.IMPLEMENTATION_PLAN:
            # Section-only artifact: "done" must mean exactly what the regen
            # loop's ``_produced`` means — required fields populated, not
            # merely "some data present". With the weaker check, a truncated
            # partial deposit satisfied this guard while ``_produced`` kept
            # saying "retry", so regen spun without ever re-calling the LLM
            # (measured on a 4096-clamped endpoint: 3 regen_empty_section
            # events, zero extra llm_calls, a half-empty implementation
            # shipped and Dev/Impl collapsed).
            from ..workflow import _empty_required_fields
            if self._graph_mode:
                data = (self.graph.get_node(self.graph.section_id(primary)) or {}).get("data") or {}
            else:
                data = self.store.get("implementation_plan") or {}
            return bool(data) and not _empty_required_fields(primary, data)
        if not self._graph_mode:
            from ..prose_store import primary_items
            return bool(primary_items(self.store, str(primary)))
        return bool(self.graph.element_nodes(primary))

    #: Alignment-state scope per NON-fan-out state and per fan-out state's
    #: DISPATCH call — mirrors the multi arm's dispatch call sites (the
    #: assessment/activity dev-plan hops, content's modules+media hop), so
    #: the scaffolding a step receives is identical in both arms and only
    #: persona + granularity differ. Asymmetry here would hand one arm
    #: better instantiated checklists than the other, which is the
    #: prompt-strength confound all over again. No ``plan_pairs`` entry
    #: anywhere: that docket names (objective, category) pairs a PLAN has
    #: promised but no ITEM yet realises — a fact that can only exist once
    #: both a plan and some items exist, which is true of neither arm's
    #: dispatch/planning call (the multi arm's own dev-plan hop carries no
    #: such docket either — see AssessmentDesignerAgent._run_dev_plan).
    _STATE_ALIGNMENT_SCOPE: dict = {
        "content": {"gaps": ("C5",)},
        "implementation": {"gaps": ("P10", "P11")},
    }

    #: Prose read-lists per state — the blackboard documents whose graph-mode
    #: node selection the branch below mirrors.
    _PROSE_READS: dict[str, tuple[str, ...]] = {
        "outcomes": ("analysis",),
        "assessment": ("objective", "analysis"),
        "activities": ("objective", "assessment"),
        "content": ("activity", "analysis"),
        "implementation": ("activity", "material"),
    }

    def _context_for(self, state: str) -> str:
        """Prior artifacts this state needs, through the SAME channel the
        multi-agent arm uses — so ``context_mode`` (graph machinery vs prose
        blackboard) switches identically in both arms. Deliberately not a
        chat history: that would be a third channel for prior artifacts and
        would make the context axis meaningless here."""
        if not self._graph_mode:
            keys = self._PROSE_READS.get(state)
            return self._store_context(keys) if keys else ""
        g = self.graph
        nodes: list[dict] = []
        rendered = ""
        if state == "outcomes":
            nodes = (g.element_nodes(NodeType.GAP) + g.element_nodes(NodeType.TOPIC)
                     + g.section_nodes(NodeType.LEARNER_PROFILE))
        elif state == "assessment":
            # Objectives + analysis context, mirroring the multi arm's
            # assessment dev-plan hop (topics/constraints/learner shape item
            # formats and stems; content/activity nodes stay out — Backward
            # Design).
            nodes = (g.element_nodes(NodeType.OBJECTIVE) + g.element_nodes(NodeType.TOPIC)
                     + g.element_nodes(NodeType.CONSTRAINT)
                     + g.section_nodes(NodeType.LEARNER_PROFILE))
        elif state == "activities":
            # Relation-join, mirroring the multi arm's activity plan hop:
            # each objective arrives WITH the items that assess it (C2).
            rendered = self._element_context_joined(
                g.element_nodes(NodeType.OBJECTIVE),
                g.element_nodes(NodeType.ASSESSMENT), "C2", "assessed by")
        elif state == "content":
            nodes = (g.element_nodes(NodeType.ACTIVITY) + g.element_nodes(NodeType.TOPIC)
                     + g.element_nodes(NodeType.CONSTRAINT))
        elif state == "implementation":
            nodes = g.element_nodes(NodeType.ACTIVITY) + g.element_nodes(NodeType.MATERIAL)
        if nodes and not rendered:
            rendered = self._element_context(nodes)
        scope = self._STATE_ALIGNMENT_SCOPE.get(state)
        if scope:
            state_ctx = self._alignment_state_context(**scope)
            if state_ctx:
                rendered = f"{rendered}\n\n{state_ctx}" if rendered else state_ctx
        return rendered

    # ── commits: shared tools only (element decomposition + establishers) ───
    # analysis/outcomes/implementation are unchanged single-call families.
    def _commit_analysis(self, parsed: dict) -> None:
        needs = parsed.get("needs_analysis") or {}
        gap_ids = self._decompose_elements(NodeType.GAP, needs.get("gaps"))
        self._store_narrative(NodeType.GAP, needs, "gaps")

        task = parsed.get("task_analysis") or {}
        self._decompose_elements(NodeType.TOPIC, task.get("topics"))
        self._store_narrative(NodeType.TOPIC, task, "topics")

        context = parsed.get("context_analysis") or {}
        self._decompose_elements(NodeType.CONSTRAINT, context.get("constraints"))
        self._store_narrative(NodeType.CONSTRAINT, context, "constraints")

        learner = parsed.get("learner_analysis") or {}
        if learner:
            self.graph.add_node(
                NodeType.LEARNER_PROFILE, self.graph.section_id(NodeType.LEARNER_PROFILE), learner)

        improvement = parsed.get("improvement_plan") or {}
        self._decompose_elements(NodeType.IMPROVEMENT, improvement.get("improvements"))
        self._store_narrative(NodeType.IMPROVEMENT, improvement, "improvements")
        gap_by_id = {n["data"].get("id"): n["id"] for n in self.graph.element_nodes(NodeType.GAP)}
        for item in improvement.get("improvements") or []:
            if not isinstance(item, dict):
                continue
            source = gap_by_id.get(alignment.bare_ref(item.get("addresses_gap")))
            if source:
                alignment.record_provenance(
                    self.graph, "P9", [source],
                    f"{NodeType.IMPROVEMENT}{self.graph.ELEMENT_SEP}{item.get('id')}")
        for node_id in gap_ids:
            self.trajectory.log_node_edit("add", node_id, NodeType.GAP)

    def _commit_outcomes(self, parsed: dict) -> None:
        goal_id = self.graph.section_id(NodeType.COURSE_GOAL)
        self.graph.add_node(NodeType.COURSE_GOAL, goal_id, parsed.get("course_goal") or {})

        objectives = parsed.get("learning_objectives") or []
        # element nodes are the single source of truth — no objective_0 section
        objective_ids = self._decompose_elements(NodeType.OBJECTIVE, objectives)
        gap_ids = [n["id"] for n in self.graph.element_nodes(NodeType.GAP)]
        topic_ids = [n["id"] for n in self.graph.element_nodes(NodeType.TOPIC)]
        learner_id = self.graph.section_id(NodeType.LEARNER_PROFILE)
        for node_id in objective_ids:
            self.trajectory.log_node_edit("add", node_id, NodeType.OBJECTIVE)
            alignment.record_provenance(self.graph, "C1", [goal_id], node_id)
            if gap_ids or topic_ids:
                alignment.record_provenance(self.graph, "P1", gap_ids + topic_ids, node_id)
            if self.graph.get_node(learner_id):
                alignment.record_provenance(self.graph, "P2", [learner_id], node_id)

    def _store_narrative(self, node_type: str, section: dict, element_key: str) -> None:
        """Keep the fields of an analysis section that are not the element list
        — see OutcomeDesignerAgent._store_analysis_narrative for why dropping
        them costs rubric points."""
        if not isinstance(section, dict):
            return
        narrative = {k: v for k, v in section.items() if k != element_key}
        if narrative:
            self.graph.add_node(node_type, self.graph.section_id(node_type), narrative)
            self.graph.link_section_narrative(node_type)

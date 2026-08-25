"""Ablation matrix: agent_mode (single/multi) x context_mode (prose/graph).
Defaults preserve the full pipeline (multi + graph); each axis cleanly
switches exactly its own mechanism, independent of the other."""
from __future__ import annotations

from alignmentgraph_isd import HarnessRunConfig, run_design_brief
from alignmentgraph_isd.core.alignment_graph import AlignmentGraph, NodeType
from alignmentgraph_isd.core.workflow import build_workflow
from alignmentgraph_isd.core.agents.assessment_designer import AssessmentDesignerAgent
from alignmentgraph_isd.core.prose_store import ProseStore
from alignmentgraph_isd.core.trajectory import TrajectoryLogger

from conftest import FakeChatModel, events_of, load_brief

MULTI_AGENT_NODES = {
    "outcome_designer", "assessment_designer", "activity_designer",
    "content_designer", "rubric_designer", "implementation_planner", "aggregate",
}


def _compiled_node_names(config, brief):
    compiled = build_workflow(config, AlignmentGraph(), TrajectoryLogger(), brief)
    return set(compiled.get_graph().nodes)


def test_flags_default_on():
    config = HarnessRunConfig()
    assert config.agent_mode == "multi"
    assert config.context_mode == "graph"


def test_multi_mode_wires_all_six_designers(fake_config):
    brief = load_brief("minimal_brief.json")
    names = _compiled_node_names(fake_config, brief)
    assert MULTI_AGENT_NODES <= names


def test_single_mode_wires_one_monolithic_node(fake_llm_factory):
    config = HarnessRunConfig(llm_factory=fake_llm_factory, agent_mode="single")
    brief = load_brief("minimal_brief.json")
    names = _compiled_node_names(config, brief)
    assert "monolithic_designer" in names
    assert not (MULTI_AGENT_NODES - {"aggregate"}) & names
    # Aggregation stays; the implementation planner does NOT get its own node
    # here — the single agent covers it as one of its own states, so wiring it
    # separately would run implementation twice and reintroduce a second persona.
    assert "aggregate" in names
    assert "implementation_planner" not in names


#: The dev-plan fan-out (2026-08-28) gives assessment/activity/content/rubric
#: three nodes each (dispatch keeps the family's own name, so it is already
#: in MULTI_AGENT_NODES) instead of one flat node — see core/workflow.py's
#: FANOUT_FAMILIES / _FANOUT_NODE_PREFIX.
FANOUT_DEVELOP_FINALIZE_NODES = {
    f"{prefix}_{suffix}"
    for prefix in ("assessment", "activity", "content", "rubric")
    for suffix in ("developer", "finalize")
}


def test_graph_and_prose_multi_mode_share_the_same_topology(fake_llm_factory):
    """`context_mode` swaps only the substrate a Designer reads/writes
    (AlignmentGraph vs. the graph-free ProseStore blackboard), never the
    wiring: both build the identical topology — the linear six-Designer
    pipeline, with four of those families expanded into their own
    dispatch/develop/finalize fan-out (2026-08-28) — with no checkpoint/
    router/revision-plumbing nodes at all (removed 2026-08-28 — see
    core/workflow.py's module docstring)."""
    brief = load_brief("minimal_brief.json")

    graph_config = HarnessRunConfig(llm_factory=fake_llm_factory)
    graph_names = _compiled_node_names(graph_config, brief)

    prose_config = HarnessRunConfig(llm_factory=fake_llm_factory, context_mode="prose")
    compiled = build_workflow(prose_config, None, TrajectoryLogger(), brief, ProseStore())
    prose_names = set(compiled.get_graph().nodes)

    assert MULTI_AGENT_NODES <= graph_names
    assert MULTI_AGENT_NODES <= prose_names
    assert FANOUT_DEVELOP_FINALIZE_NODES <= graph_names
    assert FANOUT_DEVELOP_FINALIZE_NODES <= prose_names
    assert graph_names == prose_names, "the two substrates must build the IDENTICAL topology"
    assert not any("validate" in n or "_set_ctx" in n for n in graph_names | prose_names)


def test_prose_store_context_is_verbatim_json_of_deposited_documents():
    """The prose arm's context channel: whole documents, raw JSON text, static
    read-list — the named-slice pattern non-graph agents use. Ids and schema
    fields SURVIVE (this axis ablates the machinery, not the information a
    document already carries); what is absent is everything the graph derives:
    type-labeled records, selection, docket."""
    store = ProseStore()
    store.put("objective", {"learning_objectives": [
        {"id": "ILO-01", "level": "apply",
         "statement": "Apply inheritance to a domain model."},
    ]})
    store.put("assessment_plan", {"lo_coverage_targets": {"ILO-01": ["summative"]}})

    ctx = store.context(("objective", "assessment_plan", "assessment"))
    assert "[OBJECTIVE]" in ctx and "[ASSESSMENT_PLAN]" in ctx
    assert "[ASSESSMENT]" not in ctx  # absent document skipped, no placeholder
    assert '"id": "ILO-01"' in ctx and '"level": "apply"' in ctx
    assert "[OBJECTIVE:objective:" not in ctx  # no graph-style typed node header


def test_single_prose_run_end_to_end(fake_llm_factory):
    config = HarnessRunConfig(llm_factory=fake_llm_factory, agent_mode="single", context_mode="prose")
    brief = load_brief("minimal_brief.json")
    result = run_design_brief(brief, config)

    # A prose run has no graph and therefore no graph artifact keys at all.
    assert set(result) >= {"addie_output", "trajectory", "metadata"}
    assert "graph" not in result and "graph_dot" not in result
    addie = result["addie_output"]
    assert set(addie) == {"analysis", "design", "development", "implementation", "evaluation"}
    assert addie["design"]["learning_objectives"], "expected learning objectives"
    assert result["metadata"]["audit"] == {}


def test_multi_prose_run_is_graph_free_and_unrouted(fake_llm_factory):
    """End-to-end guarantees of the prose arm: the run completes with a full
    ADDIE output, never touches an AlignmentGraph (graph=None would surface as
    an agent_error recovery event), emits no cross-agent revision actions, and
    logs check rounds whose violations are all within-artifact types."""
    brief = load_brief("minimal_brief.json")
    result = run_design_brief(brief, HarnessRunConfig(llm_factory=fake_llm_factory, context_mode="prose"))

    assert "graph" not in result and "graph_dot" not in result
    addie = result["addie_output"]
    assert addie["design"]["learning_objectives"]
    assert addie["development"]["assessment_tools"]
    # design.alignment_matrix is a product of established edges — must be absent
    assert "alignment_matrix" not in addie["design"]

    trajectory = result["trajectory"]
    errors = [e for e in events_of(trajectory, "recovery") if e["action"] == "agent_error"]
    assert not errors, f"prose run hit agent errors (graph leak?): {errors}"
    step_actions = [c["args"]["action"] for c in trajectory["tool_calls"]]
    assert not any(action.startswith("revise_") for action in step_actions)

    within_artifact = {"bloom", "measurability", "rubric_consistency",
                       "evaluation_quality", "actionability"}
    for event in events_of(trajectory, "check"):
        assert set(event["context"].get("by_type") or {}) <= within_artifact, event

    # Both arms produce the same output skeleton (phases and their fields are
    # judged on one schema — implementation asymmetry would corrupt the axis).
    graph_result = run_design_brief(brief, HarnessRunConfig(llm_factory=fake_llm_factory))
    for phase in ("analysis", "design", "development", "implementation", "evaluation"):
        missing = ({k for k, v in graph_result["addie_output"][phase].items() if v}
                   - set(addie[phase]) - {"alignment_matrix"})
        assert not missing, f"prose arm never produces {phase}.{missing}"


def test_metadata_records_run_config(fake_config, fake_llm_factory):
    brief = load_brief("minimal_brief.json")

    result = run_design_brief(brief, fake_config)
    rc = result["metadata"]["run_config"]
    assert rc["agent_mode"] == "multi"
    assert rc["context_mode"] == "graph"

    single = HarnessRunConfig(llm_factory=fake_llm_factory, agent_mode="single", context_mode="prose")
    result = run_design_brief(brief, single)
    rc = result["metadata"]["run_config"]
    assert rc["agent_mode"] == "single"
    assert rc["context_mode"] == "prose"


def test_prose_prompts_carry_no_docket_and_no_graph_records(fake_llm_factory):
    """The docket (instantiated gaps, promised pairs, edge lists) is a product
    of the alignment machinery — the prose arm's prompts must not carry it,
    while its store documents DO reach the model verbatim. This is the load-
    bearing difference between the current arm and the retired rendering arm,
    which still fed graph-computed facts to the model in sentence form."""
    brief = load_brief("minimal_brief.json")
    captured: list[str] = []

    class _Spy(FakeChatModel):
        def bind(self, **_kwargs):
            return self

        def invoke(self, messages):
            captured.append(next(
                (m.get("content", "") for m in messages
                 if isinstance(m, dict) and m.get("role") == "user"), ""))
            return super().invoke(messages)

    config = HarnessRunConfig(context_mode="prose")
    config.llm_factory = lambda: _Spy()
    run_design_brief(brief, config)

    joined = "\n".join(captured)
    for marker in ("=== ALIGNMENT STATE ===", "missing for:", "PLAN-PROMISED",
                   "--C2-assessed_by-->", "[OBJECTIVE:objective:"):
        assert marker not in joined, f"prose prompt carries graph-derived marker {marker!r}"
    # Prior documents do reach later specialists, verbatim.
    assert "[OBJECTIVE]" in joined and "[ASSESSMENT_PLAN]" in joined
    # 2026-08-28: assessment_designer's dev-plan hop reads objectives + the
    # plan it just committed (not analysis context, which only the FIRST
    # hop -- planning the strategy itself -- needs), so this is the header
    # its dev-plan call carries, not the pre-fan-out single-call header.
    assert any("=== LEARNING OBJECTIVES + ASSESSMENT PLAN ===" in u for u in captured)


def test_single_mode_reports_one_agent_identity_not_five(fake_llm_factory):
    """The decomposition axis has to be observable in the trajectory, not just
    in the LangGraph topology. The arm originally reused the five
    Designer classes as internal steps and each of those hardcodes its own
    class name in its log_step call, so the `single` arm was emitting a trace
    naming six distinct agents — identical in shape to the `multi` arm down to
    the tool-name order. Measured consequence: the judge scored the two arms
    on byte-identical input, and multi-minus-single on trajectory_score came
    out at -0.008 to -0.317, i.e. noise around zero by construction."""
    brief = load_brief("minimal_brief.json")

    multi = run_design_brief(brief, HarnessRunConfig(llm_factory=fake_llm_factory, agent_mode="multi"))
    single = run_design_brief(brief, HarnessRunConfig(llm_factory=fake_llm_factory, agent_mode="single"))

    def identities(result):
        return {c["args"]["agent"] for c in result["trajectory"]["tool_calls"]}

    # The implementation planner is a specialist now, not a bolt-on, so the
    # single arm covers it too: one persona for the whole job against NINE —
    # six Designers (rubric_designer makes no LLM call of its own, so it
    # never appears here) plus the four dev-plan fan-out families' own
    # Developer classes (2026-08-28).
    assert identities(single) == {"SingleDesignerAgent"}
    assert len(identities(multi)) == 9

    single_tools = [c["tool"] for c in single["trajectory"]["tool_calls"]]
    assert not any(t.startswith(("OutcomeDesigner", "AssessmentDesigner", "AssessmentDeveloper",
                                 "ActivityDesigner", "ActivityDeveloper", "ContentDesigner",
                                 "MaterialDeveloper", "RubricDesigner", "RubricDeveloper"))
                   for t in single_tools)
    # The two arms must not be indistinguishable to the judge.
    assert single_tools != [c["tool"] for c in multi["trajectory"]["tool_calls"]]


# ── the axis must change its own mechanism and nothing else ─────────────────

def _work_set_total(result) -> int:
    """Per-work-set LLM calls in a run: one call per set, in BOTH arms."""
    return sum(int((e.get("context") or {}).get("set_count") or 0)
               for e in result["trajectory"]["events"] if e["action"] == "dev_plan")


def test_retry_ceiling_and_validation_count_match_across_the_decomposition_axis(
        fake_llm_factory, monkeypatch):
    """Two scaffolding asymmetries the audit of 2026-08-30 found, both
    favouring the single arm and neither part of the manipulation:

    * a fan-out state carries the per-set retry story INSIDE
      ``_run_fanout_state`` (``_regen_missing_sets``, ceiling ``1 + budget``
      per set). Running it through ``run_generation_step``'s outer
      ``_regen_loop`` as well stacked the budgets: ``(1+budget)^2`` = 9
      attempts on a stubborn set against the multi arm's 3.
    * self-validation is once per FAMILY in the multi arm. The single arm's
      ``analysis`` and ``outcomes`` are two states of the SAME family, so it
      ran seven passes to multi's six.
    """
    from alignmentgraph_isd.core import workflow as wf
    from alignmentgraph_isd.core.agents import base as agent_base

    validated: dict[str, list[str]] = {}
    inner_regens: dict[str, int] = {}
    orig_validate = wf.NodeFactory._self_validate
    orig_inner = agent_base.BaseISDAgent._regen_missing_sets

    brief = load_brief("minimal_brief.json")
    for mode in ("multi", "single"):
        validated[mode], inner_regens[mode] = [], 0

        def _validate(self, agent, identity, node_name, _tag=mode):
            validated[_tag].append(node_name)
            return orig_validate(self, agent, identity, node_name)

        def _inner(self, *a, _tag=mode, **k):
            inner_regens[_tag] += 1
            return orig_inner(self, *a, **k)

        monkeypatch.setattr(wf.NodeFactory, "_self_validate", _validate)
        monkeypatch.setattr(agent_base.BaseISDAgent, "_regen_missing_sets", _inner)
        run_design_brief(brief, HarnessRunConfig(llm_factory=fake_llm_factory, agent_mode=mode))

    # One self-validation pass per family, in both arms — no family twice.
    for mode in ("multi", "single"):
        assert len(validated[mode]) == len(set(validated[mode])), (
            f"{mode} arm validated a family more than once: {validated[mode]}")
    assert sorted(validated["multi"]) == sorted(validated["single"]), (
        f"validated families differ: multi={sorted(validated['multi'])} "
        f"single={sorted(validated['single'])}")

    # Each arm applies the per-set retry at exactly ONE level. The multi arm's
    # level is `_regen_missing_sets` inside `finalize_node` (its worker nodes
    # sit outside any regen loop); the single arm's is the outer `_regen_loop`
    # re-entering its re-entrant `_run_fanout_state`. If the single arm also
    # called `_regen_missing_sets`, the two would multiply.
    assert inner_regens["multi"] > 0, "multi arm lost its per-set retry"
    assert inner_regens["single"] == 0, (
        "single arm runs an INNER per-set retry underneath the outer regen "
        "loop — the ceiling becomes (1+budget)^2 against the multi arm's "
        "1+budget")

def _flaky_design_factory():
    """Empty payload for every call whose schema carries learning_objectives,
    so only node-level regen can recover them. Matches the multi arm's
    outcome_designer Hop B2 (``_SYSTEM_DESIGN``, per the 2026-08-28 course_goal/
    LO hop split) and the single arm's still-merged outcomes task — NOT the
    multi arm's Hop B1 (course_goal alone), whose emptiness doesn't blank
    OBJECTIVE elements and so wouldn't trigger the outer regen this test
    checks for."""
    from conftest import _Result

    class _Flaky(FakeChatModel):
        def bind(self, **_kwargs):
            return self

        def invoke(self, messages):
            # Whole conversation, keyed on the SCHEMA: the single arm carries a
            # stable persona in `system` and puts the task and schema in
            # `user`, so a system-only, persona-keyed flake would never fire
            # there and the test would silently check only one arm.
            prompt = "\n".join(m.get("content", "") for m in messages
                               if isinstance(m, dict) and isinstance(m.get("content"), str))
            if '"learning_objectives"' in prompt:
                return _Result("")
            return super().invoke(messages)

    return lambda: _Flaky()


def test_both_arms_get_the_same_generation_scaffolding(fake_llm_factory):
    """`multi - single` must measure decomposition, not robustness. The single
    arm originally ran the five steps inside one try-free call with no regen
    loop and a self-validation budget of 2 for ALL checks against multi's 2 per
    Designer, and never called log_violations_result at all -- so its
    check_events were a constant 1.00/scenario against multi's 7.20, which
    the ablation pooling then reported as mechanism evidence."""
    brief = load_brief("minimal_brief.json")
    runs = {
        mode: run_design_brief(brief, HarnessRunConfig(llm_factory=fake_llm_factory, agent_mode=mode))
        for mode in ("multi", "single")
    }
    multi, single = runs["multi"]["trajectory"], runs["single"]["trajectory"]

    # Raw call counts legitimately differ: collapsing plan/execute pairs is
    # part of what "less decomposed" means, so the single arm asks fewer,
    # broader questions. What must NOT differ is whether each arm gets the
    # scaffolding at all.
    for event_type in ("check", "repair"):
        assert events_of(single, event_type), \
            f"single arm produced no {event_type} events — scaffolding is missing there"
        assert events_of(multi, event_type)
    # One judge-visible tool call per real model call, in both arms.
    llm_calls = {m: runs[m]["metadata"]["token_usage"]["llm_calls"] for m in runs}
    for name, trace in (("multi", multi), ("single", single)):
        assert len(trace["tool_calls"]) == llm_calls[name], f"{name} leaks non-model steps"

    # ...and the axis itself still separates them.
    ids = lambda t: {c["args"]["agent"] for c in t["tool_calls"]}  # noqa: E731
    assert len(ids(multi)) > len(ids(single))
    # Compare FIXED hops, not total calls. Both arms make one extra call per
    # dev-plan work set, and the set count is ENDOGENOUS — it is a function of
    # each arm's own upstream output (objectives x coverage pairs, committed
    # items, ...), so total llm_calls is an OUTCOME of the run, not a property
    # of the axis. On this fixture both arms happen to plan the same sets; on
    # real models they do not, and the audit of 2026-08-30 measured the single
    # arm spending ~44% MORE calls than multi at 9B precisely because its own
    # output inflated the fan-out. Asserting on the raw total would pin a
    # fixture artifact and state the real-world direction backwards.
    fixed = {name: llm_calls[name] - _work_set_total(runs[name]) for name in runs}
    assert fixed["single"] < fixed["multi"], (
        "the single arm should ask fewer, broader FIXED questions (it collapses "
        "three plan/execute splits); equal counts would mean a split survived")


def test_single_mode_regenerates_an_empty_section_like_multi_does():
    """Empty-output regen is scaffolding, not an ablated mechanism. The single
    arm had none, so on a weak model it would lose artifacts the multi arm
    retries into existence -- a robustness gap read as a decomposition effect."""
    brief = load_brief("minimal_brief.json")
    results = {}
    for mode in ("multi", "single"):
        config = HarnessRunConfig(agent_mode=mode)
        config.llm_factory = _flaky_design_factory()
        results[mode] = run_design_brief(brief, config)

    for mode, result in results.items():
        regens = [e for e in events_of(result["trajectory"], "recovery")
                  if e["action"] == "regen_empty_section"]
        assert regens, f"{mode} arm did not retry an empty section at all"


def test_single_mode_uses_one_persona_not_five_specialist_prompts():
    """Role decomposition lives in the SYSTEM PROMPT. The five Designers are
    five personas plus five graph-write routines, so an arm that kept all five
    personas was still a five-specialist pipeline to the model however few
    LangGraph nodes it ran in — measured: `single` sent ten specialist system
    prompts byte-identical to `multi`'s.

    The steps themselves stay: the full ADDIE output measures ~37k completion
    tokens against the ladder's 8192 cap, so a one-call arm would fail by
    truncation and stand in a token-budget artifact for a decomposition effect.
    """
    brief = load_brief("minimal_brief.json")
    seen: dict[str, list[str]] = {}

    def spy(tag):
        class _Spy(FakeChatModel):
            def bind(self, **_kwargs):
                return self

            def invoke(self, messages):
                seen.setdefault(tag, []).append(next(
                    (m.get("content", "") for m in messages
                     if isinstance(m, dict) and m.get("role") == "system"), ""))
                return super().invoke(messages)

        return lambda: _Spy()

    for mode in ("multi", "single"):
        config = HarnessRunConfig(agent_mode=mode)
        config.llm_factory = spy(mode)
        run_design_brief(brief, config)

    personas = {mode: {p.partition("\n\n")[0] for p in prompts}
                for mode, prompts in seen.items()}

    # 13, not 10: the 2026-08-28 dev-plan fan-out gave assessment/activity/
    # content/rubric their own Developer persona (one call per work set) on
    # top of each family's Designer persona(s) -- rubric_designer itself
    # makes no LLM call (its grouping is deterministic), so only its
    # Developer's persona appears. Plus one more: outcome_designer's
    # course_goal/LO split (same date) gave course_goal its own persona
    # (_SYSTEM_GOAL) alongside the objectives persona (_SYSTEM_DESIGN).
    assert len(personas["multi"]) == 13, "multi should keep one persona per step"
    # One persona for the WHOLE job, with nothing left over: the implementation
    # planner is a specialist in the multi arm, so this arm covers it too.
    assert len(personas["single"]) == 1
    assert "You are ONE instructional designer" in personas["single"].pop()

    # Fewer, broader questions — the task decomposition is gone too, not just
    # the personas.
    assert len(seen["single"]) < len(seen["multi"])


def test_both_arms_state_the_same_rules():
    """Only persona and task granularity may differ between arms. Every other
    instruction — how many objectives, which formats may claim which Bloom
    level, what must reference an existing id — has to be word-for-word the
    same, or `multi - single` measures prompt strength instead.

    It did once: the single arm's outcome task was a hand-written paraphrase
    that dropped "do not merge unrelated gaps into one objective to hit a
    count" and the worked Bloom example, and produced 2-3 objectives against
    the multi-agent arm's 5 on the same scenario. Both arms now compose their
    prompts from the shared rulebook (core/rulebook.py) — neither derives
    from the other — and this asserts every rulebook block reaches both arms'
    rendered prompts verbatim."""
    from alignmentgraph_isd.core import rulebook
    from alignmentgraph_isd.core.agents import (
        activity_designer, activity_developer, assessment_designer, assessment_developer,
        content_designer, implementation_planner, material_developer,
        rubric_developer, single_designer,
    )
    from alignmentgraph_isd.core.agents import outcome_designer

    triples = (
        ("ANALYSIS", outcome_designer._SYSTEM_ANALYZE, single_designer._TASK_ANALYSIS),
        # course_goal (Hop B1) and objectives (Hop B2) are split calls in the
        # multi arm but still one merged call in the single arm -- both
        # rulebook blocks must reach that one task.
        ("COURSE_GOAL", outcome_designer._SYSTEM_GOAL, single_designer._TASK_OUTCOMES),
        ("OUTCOMES", outcome_designer._SYSTEM_DESIGN, single_designer._TASK_OUTCOMES),
        # Assessment: dispatch (plan + dev-plan grouping, merged into one
        # call in the single arm) then a per-set call.
        ("ASSESSMENT_PLAN", assessment_designer._SYSTEM_PLAN, single_designer._TASK_ASSESSMENT),
        ("ASSESSMENT_DEV_PLAN", assessment_designer._SYSTEM_DEV_PLAN, single_designer._TASK_ASSESSMENT),
        ("ASSESSMENT_ITEMS_SET", assessment_developer._SYSTEM, single_designer._TASK_ASSESSMENT_ITEMS),
        # Activities: same shape as assessment.
        ("ACTIVITY_PLAN", activity_designer._SYSTEM_PLAN, single_designer._TASK_ACTIVITIES),
        ("ACTIVITY_DEV_PLAN", activity_designer._SYSTEM_DEV_PLAN, single_designer._TASK_ACTIVITIES),
        ("ACTIVITIES_SET", activity_developer._SYSTEM, single_designer._TASK_ACTIVITY_SET),
        # Content: dispatch is deterministic grouping (no dev-plan LLM call),
        # so only the modules+media call and the per-module call carry rules.
        ("CONTENT_MODULES", content_designer._SYSTEM_MODULES, single_designer._TASK_CONTENT),
        ("MATERIALS_UNIT", material_developer._SYSTEM, single_designer._TASK_MATERIALS_UNIT),
        # Rubrics: no dispatch call at all (deterministic, zero LLM calls) —
        # only the per-item call carries rules, in both arms.
        ("RUBRICS_ITEM", rubric_developer._SYSTEM, single_designer._TASK_RUBRICS),
        ("IMPLEMENTATION", implementation_planner._SYSTEM, single_designer._TASK_IMPLEMENTATION),
    )
    for family, specialist_prompt, single_task in triples:
        block = getattr(rulebook, f"RULES_{family}").strip()
        assert block and block in specialist_prompt, (
            f"the multi arm dropped rulebook block RULES_{family}")
        assert block in single_task, (
            f"the single arm dropped rulebook block RULES_{family}:\n{block[:200]}")
    # rubric_designer.py itself makes no LLM call any more (deterministic
    # dispatch) and so composes no rulebook rules at all — nothing to assert
    # symmetry against there; RubricDeveloperAgent (above) is where
    # RULES_RUBRICS_ITEM actually reaches a prompt in the multi arm.


def test_both_arms_show_the_same_output_exemplars():
    """RULES parity was enforced from 2026-08-26 but SCHEMA parity never was,
    and the arms drifted: the single arm carried hand-written JSON exemplars
    while the multi arm inlined ``rulebook.SCHEMA_*``. Measured gap (audit
    2026-08-30): `_TASK_ASSESSMENT_ITEMS` showed ONE `performance_task`
    exemplar against `SCHEMA_ASSESSMENT_ITEMS`' three, omitting the
    `multiple_choice` case with `options`/`correct_answer` entirely — so the
    `item_completeness` check and its LLM-backed repair fired more often in
    the single arm for a reason that is prompt strength, not decomposition.
    Both arms now inline the SAME block, and this pins it."""
    from alignmentgraph_isd.core import rulebook
    from alignmentgraph_isd.core.agents import (
        activity_designer, activity_developer, assessment_designer, assessment_developer,
        content_designer, implementation_planner, material_developer, outcome_designer,
        rubric_developer, single_designer,
    )

    triples = (
        ("ANALYSIS", outcome_designer._SYSTEM_ANALYZE, single_designer._TASK_ANALYSIS),
        ("ASSESSMENT_PLAN", assessment_designer._SYSTEM_PLAN, single_designer._TASK_ASSESSMENT),
        ("ASSESSMENT_DEV_PLAN", assessment_designer._SYSTEM_DEV_PLAN, single_designer._TASK_ASSESSMENT),
        ("ASSESSMENT_ITEMS", assessment_developer._SYSTEM, single_designer._TASK_ASSESSMENT_ITEMS),
        ("ACTIVITY_PLAN", activity_designer._SYSTEM_PLAN, single_designer._TASK_ACTIVITIES),
        ("ACTIVITY_DEV_PLAN", activity_designer._SYSTEM_DEV_PLAN, single_designer._TASK_ACTIVITIES),
        ("ACTIVITIES", activity_developer._SYSTEM, single_designer._TASK_ACTIVITY_SET),
        ("CONTENT_MODULES", content_designer._SYSTEM_MODULES, single_designer._TASK_CONTENT),
        ("MATERIALS", material_developer._SYSTEM, single_designer._TASK_MATERIALS_UNIT),
        ("RUBRICS", rubric_developer._SYSTEM, single_designer._TASK_RUBRICS),
        ("IMPLEMENTATION", implementation_planner._SYSTEM, single_designer._TASK_IMPLEMENTATION),
    )
    for family, specialist_prompt, single_task in triples:
        block = getattr(rulebook, f"SCHEMA_{family}").strip()
        assert block and block in specialist_prompt, (
            f"the multi arm dropped rulebook block SCHEMA_{family}")
        assert block in single_task, (
            f"the single arm dropped rulebook block SCHEMA_{family}:\n{block[:200]}")

    # Outcomes is the one family the decomposition axis deliberately merges:
    # multi splits course_goal (Hop B1) and objectives (Hop B2) into two calls
    # with two schemas, single asks for both in one. Parity here means the
    # merged schema must not ask for LESS than the two split ones together.
    assert rulebook.SCHEMA_COURSE_GOAL.strip() in outcome_designer._SYSTEM_GOAL
    assert rulebook.SCHEMA_LEARNING_OBJECTIVES.strip() in outcome_designer._SYSTEM_DESIGN
    assert rulebook.SCHEMA_OUTCOMES.strip() in single_designer._TASK_OUTCOMES
    for split in (rulebook.SCHEMA_COURSE_GOAL, rulebook.SCHEMA_LEARNING_OBJECTIVES):
        for line in (ln.strip() for ln in split.splitlines()):
            if line in ("{", "}", ""):
                continue
            assert line in rulebook.SCHEMA_OUTCOMES, (
                f"the merged SCHEMA_OUTCOMES asks for less than the split schemas: {line!r}")

    # ...and no arm may reintroduce a hand-written exemplar: every JSON opening
    # brace in a single-arm task must belong to a rulebook block.
    for name in [n for n in dir(single_designer) if n.startswith("_TASK_")]:
        task = getattr(single_designer, name)
        schemas = [getattr(rulebook, s) for s in dir(rulebook) if s.startswith("SCHEMA_")]
        stripped = task
        for schema in sorted(schemas, key=len, reverse=True):
            stripped = stripped.replace(schema.strip(), "")
        assert "{\n" not in stripped, (
            f"{name} carries a hand-written JSON exemplar outside the rulebook")


def test_composed_prompts_match_golden_fixture():
    """The refactor from prompt-string derivation to the shared rulebook must
    not change a byte of what either arm sends: the ladder was run on these
    prompts, so any drift here silently invalidates cross-run comparability.
    The fixture pins every composed prompt byte-for-byte (see
    tests/regen_golden_prompts.py to regenerate it after a deliberate
    wording change)."""
    import json
    from pathlib import Path

    from regen_golden_prompts import composed_prompts

    golden = json.loads(
        (Path(__file__).parent / "fixtures" / "golden_prompts.json").read_text())
    composed = composed_prompts()
    assert set(composed) == set(golden)
    for key, text in composed.items():
        assert text == golden[key], f"{key} drifted from the golden fixture"


def test_single_mode_instantiates_no_specialist_agent_classes(fake_llm_factory, monkeypatch):
    """The single arm must not borrow the multi arm's agents: its rules come
    from the rulebook, its repairs from the shared toolbox, its P10/P11 edges
    from the shared establisher. Instantiating a Designer class anywhere in a
    single-mode run means a borrowed persona, identity, or routine leaked
    back in."""
    from alignmentgraph_isd.core import workflow as wf

    for name, cls in wf.GENERATION_AGENTS.items():
        def _boom(self, *a, _name=name, **k):
            raise AssertionError(f"single-mode run instantiated {_name}")
        monkeypatch.setattr(cls, "__init__", _boom)

    brief = load_brief("minimal_brief.json")
    result = run_design_brief(
        brief, HarnessRunConfig(llm_factory=fake_llm_factory, agent_mode="single"))
    assert result["addie_output"]

    # ...and every repair/recovery row carries the one identity.
    trajectory = result["trajectory"]
    assert events_of(trajectory, "repair"), "expected the shared repairs to run"
    for event in events_of(trajectory, "repair") + events_of(trajectory, "recovery"):
        assert event["agent"] == "SingleDesignerAgent", event


def test_single_arm_asks_for_every_output_field_the_aggregator_reads():
    """A field the single arm's schema never asks for is a silent zero, not a
    quality difference. Measured: `expert_review` was missing from this arm's
    assessment schema, and since it is the ONLY sub-item under the judge's Dev2
    item, both single cells scored exactly 0.0 there and lost ~46 points of
    Development phase against the multi cells."""
    brief = load_brief("minimal_brief.json")
    outputs = {}
    for mode in ("multi", "single"):
        config = HarnessRunConfig(agent_mode=mode)
        config.llm_factory = lambda: FakeChatModel()
        outputs[mode] = run_design_brief(brief, config)["addie_output"]

    def populated(output):
        found = set()
        for phase, block in output.items():
            for field, value in (block or {}).items():
                if value:
                    found.add(f"{phase}.{field}")
        return found

    missing = populated(outputs["multi"]) - populated(outputs["single"])
    assert not missing, f"single arm produces nothing for: {sorted(missing)}"


# ── alignment-state scaffolding: same facts, both representations, both arms ──

def _scaffold_graph():
    """LO + one C2-established item + a plan promising an unrealised pair."""
    from alignmentgraph_isd.core.alignment_graph import alignment
    from alignmentgraph_isd.core.alignment_graph import AlignmentGraph, NodeType as NT

    graph = AlignmentGraph()
    graph.add_element_node(NT.OBJECTIVE, "ILO-01", {"id": "ILO-01", "level": "apply"})
    graph.add_element_node(NT.OBJECTIVE, "ILO-02", {"id": "ILO-02", "level": "create"})
    graph.add_element_node(NT.ASSESSMENT, "AT-01", {
        "item_id": "AT-01", "type": "performance_task", "aligned_objective": "ILO-01",
        "plan_category": "summative", "required_cognitive_process": "apply",
    })
    alignment.match_id_reverse(graph, "C2", field="aligned_objective")
    graph.add_node(NT.ASSESSMENT_PLAN, "assessment_plan_0", {
        "lo_coverage_targets": {"ILO-01": ["summative"], "ILO-02": ["summative"]},
    })
    return graph


def _state_block(graph, mode):
    config = HarnessRunConfig(llm_factory=lambda: None, context_mode=mode)
    agent = AssessmentDesignerAgent(config, graph, TrajectoryLogger())
    return agent._alignment_state_context(edges=("C2",), gaps=("C2",), plan_pairs=True)


def test_alignment_state_is_instantiated_not_quantified():
    """The block carries the docket, not the law: which SPECIFIC targets are
    uncovered and which SPECIFIC plan pairs are unrealised. Motivating
    measurement: with only the quantified rule in the prompt ("one item for
    every pair the plan names"), a 9B model produced 16 diagnostic / 1
    summative items against a plan promising 1 / 5."""
    block = _state_block(_scaffold_graph(), "graph")
    # BARE ids only: namespaced ids in prompts leak into model reference
    # fields and break the bare-id matchers (the measured single-graph bug).
    assert "ILO-01 --C2-assessed_by--> AT-01" in block
    assert "objective:" not in block and "assessment:" not in block
    assert "ILO-02" in block                    # the uncovered LO is NAMED
    assert "ILO-02 x summative" in block        # the unrealised pair is NAMED
    # covered artifacts are not listed as gaps
    gap_section = block.split("[GAPS", 1)[1]
    assert "ILO-01" not in gap_section.split("[PLAN-PROMISED", 1)[0]


def test_prose_repairs_operate_on_the_blackboard(fake_llm_factory):
    """The kept safeguards (within-artifact checks + owned repairs) must fix
    the blackboard documents, not a graph. A bad Bloom verb deposited by the
    model comes out repaired in the final output."""
    from alignmentgraph_isd.core.workflow import NodeFactory
    from alignmentgraph_isd.core.agents.outcome_designer import OutcomeDesignerAgent
    from alignmentgraph_isd.core.brief import DesignBrief

    store = ProseStore()
    store.put("analysis", {"needs_analysis": {"gaps": [{"id": "GAP-01", "description": "g"}]}})
    store.put("objective", {"learning_objectives": [
        {"id": "ILO-01", "level": "apply", "bloom_verb": "understand",
         "statement": "Understand inheritance."},
    ]})
    config = HarnessRunConfig(llm_factory=fake_llm_factory, context_mode="prose")
    brief = load_brief("minimal_brief.json")
    nf = NodeFactory(config, None, TrajectoryLogger(), brief, store)
    agent = OutcomeDesignerAgent(*nf._args())
    nf.run_generation_step(agent, "OutcomeDesignerAgent", "outcome_designer")

    repaired = store.items("objective", "learning_objectives")[0]
    assert repaired["bloom_verb"] != "understand", "prose repair did not touch the blackboard"


def test_alignment_state_empty_graph_renders_nothing():
    from alignmentgraph_isd.core.alignment_graph import AlignmentGraph

    config = HarnessRunConfig(llm_factory=lambda: None)
    agent = AssessmentDesignerAgent(config, AlignmentGraph(), TrajectoryLogger())
    assert agent._alignment_state_context(edges=("C2",), gaps=("C2",), plan_pairs=True) == ""


def test_scaffolding_reaches_generation_prompts_in_both_arms(fake_llm_factory):
    """End-to-end: the docket and the C2 edges actually reach the model's user
    turn — in the multi arm AND (machinery parity) in the single arm's later
    states.

    2026-08-28: the [PLAN-PROMISED PAIRS] docket (`_alignment_state_context
    (plan_pairs=True)`) is retired along with the monolithic items hop it was
    built for — a fan-out Developer's assigned set is rendered as an
    EXPLICIT slice of the plan instead ("=== YOUR ASSIGNED SET ===", one
    call per set, no other pairs to instantiate a docket over), which is a
    strictly more targeted version of the same guarantee (a produced item
    can only be for THIS set's pairs, not merely "the model saw all the
    promised pairs and might get any of them right"). Both arms carry that
    marker for the SAME family (assessment) — the single arm's per-set call
    uses the same header text as AssessmentDeveloperAgent (the multi arm's
    other three Developers use their own family-appropriate header instead —
    see e.g. ActivityDeveloperAgent's "=== YOUR ASSIGNED BLOCK ===")."""
    brief = load_brief("minimal_brief.json")
    captured: dict[str, list[str]] = {}

    def spy(tag):
        class _Spy(FakeChatModel):
            def bind(self, **_kwargs):
                return self

            def invoke(self, messages):
                captured.setdefault(tag, []).append(next(
                    (m.get("content", "") for m in messages
                     if isinstance(m, dict) and m.get("role") == "user"), ""))
                return super().invoke(messages)

        return lambda: _Spy()

    for mode in ("multi", "single"):
        config = HarnessRunConfig(agent_mode=mode)
        config.llm_factory = spy(mode)
        run_design_brief(brief, config)

    multi, single = captured["multi"], captured["single"]
    for tag, prompts in (("multi", multi), ("single", single)):
        assert any("=== YOUR ASSIGNED SET ===" in u for u in prompts), \
            f"{tag}: assessment's per-set call lost its assigned-set slice"
        # C2 reaches the activity/rubric prompts as relation-JOINED context
        # (each objective carrying the items that assess it), not as a docket
        # edge list any more.
        assert any("assessed by:" in u for u in prompts), f"{tag}: no C2 join shown"
        assert any("missing for:" in u for u in prompts), f"{tag}: no instantiated gaps"
        assert any("P10-delivers missing" in u for u in prompts), f"{tag}: no delivery docket"

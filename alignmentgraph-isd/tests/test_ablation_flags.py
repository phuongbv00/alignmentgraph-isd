"""Ablation matrix: agent_mode (single/multi) x context_mode (prose/graph).
Defaults preserve the full pipeline (multi + graph); each axis cleanly
switches exactly its own mechanism, independent of the other."""
from __future__ import annotations

from alignmentgraph_isd import HarnessRunConfig
from alignmentgraph_isd.core.alignment_graph import AlignmentGraph
from alignmentgraph_isd.core.prose_store import ProseStore
from alignmentgraph_isd.core.trajectory import TrajectoryLogger

from alignmentgraph_isd.core.agentic.specialists import STEPS
from conftest import FakeChatModel, events_of, load_brief, run_brief


def test_flags_default_on():
    config = HarnessRunConfig()
    assert config.agent_mode == "multi"
    assert config.context_mode == "graph"


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
    result = run_brief(brief, config)

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
    result = run_brief(brief, HarnessRunConfig(llm_factory=fake_llm_factory, context_mode="prose"))

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
    graph_result = run_brief(brief, HarnessRunConfig(llm_factory=fake_llm_factory))
    for phase in ("analysis", "design", "development", "implementation", "evaluation"):
        missing = ({k for k, v in graph_result["addie_output"][phase].items() if v}
                   - set(addie[phase]) - {"alignment_matrix"})
        assert not missing, f"prose arm never produces {phase}.{missing}"


def test_metadata_records_run_config(fake_config, fake_llm_factory):
    brief = load_brief("minimal_brief.json")

    result = run_brief(brief, fake_config)
    rc = result["metadata"]["run_config"]
    assert rc["agent_mode"] == "multi"
    assert rc["context_mode"] == "graph"

    single = HarnessRunConfig(llm_factory=fake_llm_factory, agent_mode="single", context_mode="prose")
    result = run_brief(brief, single)
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

    # No graph-derived fact may reach a prose prompt.
    captured.clear()
    config = HarnessRunConfig(context_mode="prose")
    config.llm_factory = lambda: _Spy()
    run_brief(brief, config)

    joined = "\n".join(captured)
    for marker in ("=== ALIGNMENT STATE ===", "missing for:", "PLAN-PROMISED",
                   "--C2-assessed_by-->", "[OBJECTIVE:objective:"):
        assert marker not in joined, (
            f"prose prompt carries graph-derived marker {marker!r}")

    # Prior documents are no longer INJECTED into the prompt: the prose arm
    # offers ``read_document`` and the model calls it, symmetric with
    # ``read_nodes`` in graph mode. So what this file asserts is the absence
    # above; that the documents are reachable AT ALL is covered end to end by
    # test_agentic_run.py, and the tool's own allowlist by test_agentic_loop.py.
    from alignmentgraph_isd.core.agentic import tools
    from alignmentgraph_isd.core.agentic.specialists import STEPS

    prose_tools = tools.tool_names(tools.tool_specs(STEPS[2], graph_mode=False))
    assert "read_document" in prose_tools and "read_nodes" not in prose_tools


def test_single_mode_reports_one_agent_identity_not_five(fake_llm_factory):
    """The decomposition axis has to be observable in the TRAJECTORY, not only
    in the configuration.

    The arm once reused the specialist classes as internal steps, and each
    hardcodes its own name in its log_step call, so `single` emitted a trace
    naming six distinct agents — identical in shape to `multi` down to the
    tool-name order. Measured consequence: the judge scored the two arms on
    byte-identical input and multi-minus-single on trajectory_score came out
    between -0.008 and -0.317, i.e. noise around zero by construction."""
    brief = load_brief("minimal_brief.json")

    def run(mode):
        return run_brief(brief, HarnessRunConfig(
            llm_factory=fake_llm_factory, agent_mode=mode))

    def identities(result):
        return {c["args"]["agent"] for c in result["trajectory"]["tool_calls"]}

    agentic_multi = run("multi")
    agentic_single = run("single")
    # The multi arm reports the stage specialists AND the Developer identities
    # it spawns per work set (fanout.py); which Developers appear depends on
    # which families this scenario fans out, so the assertion is on the SHAPE:
    # single is one actor, multi is many, and only multi spawns Developers.
    assert identities(agentic_single) == {"SingleDesignerAgent"}
    developers = {"AssessmentDeveloperAgent", "ActivityDeveloperAgent",
                  "MaterialDeveloperAgent"}
    assert identities(agentic_multi) & developers, "the multi arm spawned no Developer"
    assert not (identities(agentic_single) & developers)
    assert len(identities(agentic_multi)) > 6
    assert ([c["tool"] for c in agentic_single["trajectory"]["tool_calls"]]
            != [c["tool"] for c in agentic_multi["trajectory"]["tool_calls"]])

    # No second pair of runs: the block that used to sit here re-ran the whole
    # pipeline twice more and then asserted a strict subset of the above. Its
    # one distinct check was that no tool name is prefixed with a specialist's,
    # which the identity assertion already implies — a tool is recorded as
    # f"{agent}.{action}" (trajectory.py), so `identities(single) ==
    # {"SingleDesignerAgent"}` is the same fact, stated once.


# ── the axis must change its own mechanism and nothing else ─────────────────



def _flaky_design_factory():
    """Empty payload the FIRST time a call asks for learning objectives, and
    normal behaviour after that.

    Once, not always: the point is that a fumbled answer is recovered, and a
    model that fails every time cannot be recovered from by any mechanism. It
    also has to be once because the single arm's whole workflow — every stage's
    schema — is in one system prompt, so a fixture keyed on a schema string
    fires on every call there and would blank the entire run rather than one
    section."""
    from conftest import _Result

    state = {"failed": False}

    class _Flaky(FakeChatModel):
        def bind(self, **_kwargs):
            return self

        def invoke(self, messages):
            prompt = "\n".join(str(m.get("content", "")) for m in messages
                                if isinstance(m, dict))
            if '"learning_objectives"' in prompt and not state["failed"]:
                state["failed"] = True
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
    # The single arm asks fewer, broader questions because it collapses the
    # plan/execute splits — that call-count difference IS the treatment, not a
    # confound. What the axis claim actually rests on is stated and checked in
    # ``test_the_agentic_arms_are_two_shapes_not_two_settings``: neither arm was
    # CUT by its turn budget.
    runs = {
        mode: run_brief(brief, HarnessRunConfig(
            llm_factory=fake_llm_factory, agent_mode=mode,))
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
    # No judge-visible tool call without a real model call, in either arm, and
    # no model call that is neither a step nor a RECORDED recovery. Repairs are
    # on neither side of this any more: none of them calls the model.
    llm_calls = {m: runs[m]["metadata"]["token_usage"]["llm_calls"] for m in runs}
    for name, trace in (("multi", multi), ("single", single)):
        recovery = len(events_of(runs[name]["trajectory"], "recovery"))
        assert len(trace["tool_calls"]) <= llm_calls[name], f"{name} leaks non-model steps"
        assert llm_calls[name] - len(trace["tool_calls"]) <= recovery, (
            f"{name} made a model call that is neither a step nor a recorded recovery")

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
    # NOT equal, and not ordered either. The single arm plans its own batching
    # and the multi arm's set count is a function of its own upstream output,
    # so call totals are an OUTCOME of each run rather than a property of the
    # axis — the 2026-08-30 audit measured the single arm spending ~44% MORE
    # calls than multi at 9B for exactly that reason. What must hold is that
    # both arms did real work and neither was cut off by its ceiling.
    assert all(count > len(STEPS) for count in llm_calls.values()), llm_calls
    for name, result in runs.items():
        autonomy = result["metadata"]["autonomy"]
        assert not any(stage["via_budget_exhaustion"] for stage in autonomy.values()), name


def test_the_agentic_arms_are_two_shapes_not_two_settings(fake_llm_factory):
    """The decomposition axis, since the single arm became a ReAct loop.

    It is deliberately a BUNDLE now, not one variable: context boundary, who
    walks the stages, how many personas, and whether work is delegated. That is
    what "multi-agent vs single-agent" means to a reader, and it is disclosed as
    a bundle exactly as `context_mode` is. Equal model effort is therefore NOT
    the parity requirement any more — an agent that plans its own order and
    writes its own item batches cannot spend the same number of calls as a
    harness walking a fixed plan with Developers.

    What is still checkable, and is what the claim rests on: neither arm was
    CUT by its turn budget. While that holds, a difference in outcome cannot be
    blamed on the ceiling."""
    brief = load_brief("minimal_brief.json")
    runs = {
        mode: run_brief(brief, HarnessRunConfig(
            llm_factory=fake_llm_factory, agent_mode=mode))
        for mode in ("multi", "single")
    }
    autonomy = {m: runs[m]["metadata"]["autonomy"] for m in runs}

    # Shape: six stage records against one loop record.
    from alignmentgraph_isd.core.agentic.specialists import STEPS as AGENTIC_STEPS

    assert set(autonomy["multi"]) == {step.name for step in AGENTIC_STEPS}
    assert set(autonomy["single"]) == {"design"}

    # One actor against many, and only one arm delegates.
    ids = lambda r: {c["args"]["agent"] for c in r["trajectory"]["tool_calls"]}
    assert ids(runs["single"]) == {"SingleDesignerAgent"}
    assert len(ids(runs["multi"])) > 1
    assert any(i.endswith("DeveloperAgent") for i in ids(runs["multi"]))

    # Both arms still run the shared safeguards — the axis is decomposition,
    # not "one arm gets checked and the other does not".
    for mode in runs:
        assert events_of(runs[mode]["trajectory"], "check"), f"{mode} ran no checks"

    # Neither arm hit its ceiling.
    assert not autonomy["single"]["design"]["via_budget_exhaustion"]
    assert not any(s["via_budget_exhaustion"] for s in autonomy["multi"].values())

def test_an_empty_first_answer_loses_no_artifact_in_either_arm():
    """Recovery from an empty answer is scaffolding, not an ablated mechanism:
    an arm that loses artifacts a weaker model fumbled would read as a
    decomposition effect when it is a robustness gap.

    The two arms recover DIFFERENTLY, which is the axis and not a difference in
    protection: `multi` re-runs the stage (`regen_empty_section`), while in
    `single` the stage simply stays open — its `submit_<stage>` tool is still
    bound — and the agent submits again. So the assertion is on the OUTCOME,
    which is arm-neutral: nothing is lost either way."""
    brief = load_brief("minimal_brief.json")
    for mode in ("multi", "single"):
        config = HarnessRunConfig(agent_mode=mode)
        config.llm_factory = _flaky_design_factory()
        result = run_brief(brief, config)

        objectives = (result["addie_output"].get("design") or {}).get("learning_objectives")
        assert objectives, f"{mode} arm lost the section its first answer fumbled"
        assert not result["metadata"]["validation_errors"], mode

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
        outputs[mode] = run_brief(brief, config)["addie_output"]

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
    """The alignment docket, as the graph arm's prompts carry it.

    Was ``BaseISDAgent._alignment_state_context`` while the scripted
    specialists existed; ``tools.alignment_docket`` is the same block from the
    same graph — what it asserts is the CONTENT of the docket, which did not
    move with the executor."""
    from alignmentgraph_isd.core.agentic import tools

    if mode != "graph":
        return ""
    return tools.alignment_docket(graph, edges=("C2",), gaps=("C2",), plan_pairs=True)


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
    from conftest import RepairActor

    from alignmentgraph_isd.core import repairs
    from alignmentgraph_isd.core.outputs import _collect_violations_prose

    store = ProseStore()
    store.put("analysis", {"needs_analysis": {"gaps": [{"id": "GAP-01", "description": "g"}]}})
    store.put("objective", {"learning_objectives": [
        {"id": "ILO-01", "level": "apply", "bloom_verb": "understand",
         "statement": "Understand inheritance."},
    ]})
    config = HarnessRunConfig(llm_factory=fake_llm_factory, context_mode="prose")
    trajectory = TrajectoryLogger()
    violations = _collect_violations_prose("outcome_designer", store)
    repairs.repair("outcome_designer", violations,
                   RepairActor("OutcomeDesignerAgent", config,
                               store=store, trajectory=trajectory).ctx())

    repaired = store.items("objective", "learning_objectives")[0]
    assert repaired["bloom_verb"] != "understand", "prose repair did not touch the blackboard"


def test_alignment_state_empty_graph_renders_nothing():
    from alignmentgraph_isd.core.alignment_graph import AlignmentGraph

    from alignmentgraph_isd.core.agentic import tools

    # Nothing established and nothing uncovered: the block is omitted rather
    # than shown empty, so an early stage is not handed a header with no facts
    # under it.
    assert tools.alignment_docket(AlignmentGraph(), edges=("C2",), gaps=("C2",),
                                  plan_pairs=True) == ""


def test_scaffolding_reaches_generation_prompts_in_both_arms(fake_llm_factory):
    """End-to-end: the alignment scaffolding actually reaches the model's turn,
    in BOTH decomposition arms.

    What reaches it changed with the executor, and the docstring is worth
    keeping honest about which. The relation-JOINED rendering (each objective
    carrying the items that assess it) went with the scripted specialists — the
    agentic arms read nodes and edges through separate tools and ask
    ``coverage_gaps`` what is still open. What both arms still carry into the
    prompt is the docket: instantiated gaps, named, not a quantified rule. A
    fanned-out Developer additionally gets its own slice rendered explicitly,
    which is the stronger version of the same guarantee — a produced item can
    only be for THIS set's pairs, rather than "the model saw all the promised
    pairs and might get any of them right"."""
    brief = load_brief("minimal_brief.json")
    captured: dict[str, list[str]] = {}

    def spy(tag):
        class _Spy(FakeChatModel):
            def invoke(self, messages):
                captured.setdefault(tag, []).append("\n".join(
                    str(m.get("content", "")) for m in messages if isinstance(m, dict)))
                return super().invoke(messages)

        return lambda: _Spy()

    for mode in ("multi", "single"):
        config = HarnessRunConfig(agent_mode=mode)
        config.llm_factory = spy(mode)
        run_brief(brief, config)

    for tag in ("multi", "single"):
        prompts = captured[tag]
        assert any("=== ALIGNMENT STATE ===" in u for u in prompts), f"{tag}: no docket"
        assert any("missing for:" in u for u in prompts), f"{tag}: no instantiated gaps"

    # Only the arm that delegates hands a Developer an assignment slice: the
    # single agent has no Developer to hand one to, and that is the axis.
    assert any("=== YOUR ASSIGNED SET ===" in u for u in captured["multi"])
    assert not any("=== YOUR ASSIGNED SET ===" in u for u in captured["single"])

def test_the_docket_reaches_the_graph_arm_and_never_the_prose_arm(fake_llm_factory):
    """Machinery parity for `context_mode`: the alignment docket (instantiated
    coverage gaps) reaches the graph arm's prompts in BOTH decomposition arms,
    and never the prose arm, which has no docket to compute. Asserted over the
    whole prompt rather than a per-stage message, because the single arm has no
    per-stage message any more."""
    brief = load_brief("minimal_brief.json")
    captured: dict[str, list[str]] = {}

    def spy(tag):
        class _Spy(FakeChatModel):
            def invoke(self, messages):
                captured.setdefault(tag, []).append("\n".join(
                    str(m.get("content", "")) for m in messages if isinstance(m, dict)))
                return super().invoke(messages)

        return lambda: _Spy()

    for mode in ("multi", "single"):
        for context_mode in ("graph", "prose"):
            config = HarnessRunConfig(agent_mode=mode, context_mode=context_mode)
            config.llm_factory = spy(f"{mode}-{context_mode}")
            run_brief(brief, config)

    for mode in ("multi", "single"):
        assert any("=== ALIGNMENT STATE ===" in p for p in captured[f"{mode}-graph"]), \
            f"{mode}: the graph arm never saw the docket"
        assert not any("=== ALIGNMENT STATE ===" in p for p in captured[f"{mode}-prose"]), \
            f"{mode}: the prose arm was shown a docket it cannot compute"

def test_agentic_arm_keeps_one_persona_per_stage_or_one_for_the_job(fake_llm_factory):
    """Persona parity. The multi arm carries one
    persona per stage; the single arm carries exactly one for the whole run.
    Counted over STAGE prompts only — a repair composes its own persona-free
    system turn, and counting those would make the two arms look alike for a
    reason that has nothing to do with the axis."""
    from alignmentgraph_isd.core.agentic.loop import _WORKFLOW_OVERVIEW

    brief = load_brief("minimal_brief.json")
    seen: dict[str, list[str]] = {}

    def spy(tag):
        class _Spy(FakeChatModel):
            def invoke(self, messages):
                seen.setdefault(tag, []).append(next(
                    (m.get("content", "") for m in messages
                     if isinstance(m, dict) and m.get("role") == "system"), ""))
                return super().invoke(messages)

        return lambda: _Spy()

    for mode in ("multi", "single"):
        config = HarnessRunConfig(agent_mode=mode)
        config.llm_factory = spy(mode)
        run_brief(brief, config)

    personas = {
        mode: {p.partition("\n\n")[0] for p in prompts if _WORKFLOW_OVERVIEW in p}
        for mode, prompts in seen.items()
    }
    assert len(personas["single"]) == 1, personas["single"]
    assert len(personas["multi"]) > 1, "the multi arm must keep a persona per stage"
    # And the instructed stage order reaches BOTH arms, verbatim: the pivot
    # makes the agents autonomous in HOW a stage is executed, never in what
    # order the stages run.
    for mode in ("multi", "single"):
        assert any(_WORKFLOW_OVERVIEW in p for p in seen[mode])


def test_neither_arm_composes_its_own_rules_or_schema():
    """The two arms are shown the SAME stage text, because they read it from the
    same place.

    While the scripted pipeline existed this had to be enforced: the six
    specialists and ``SingleDesignerAgent`` each built their own prompt, so a
    rule added to one could silently miss the other, and a 13-triple test held
    them together. The agentic executor removed the possibility instead of
    policing it — both arms render ``AgenticStep.task_block()``, which composes
    from ``core/rulebook.py``. This test pins that they still BOTH go through
    it, because the cheapest way to reintroduce the old bug is for one arm to
    start writing its own.
    """
    from alignmentgraph_isd.core.agentic import react
    from alignmentgraph_isd.core.agentic.specialists import STEPS

    brief = load_brief("minimal_brief.json")
    config = HarnessRunConfig(llm_factory=lambda: None)
    loop = react.ReactLoop(config, AlignmentGraph(), TrajectoryLogger(), brief)

    for step in STEPS:
        task = step.task_block()
        assert task in loop.stage_brief(step.name), (
            f"the single arm rewrote {step.name}'s task instead of reading it")
        # ...and those rules are the RULEBOOK's own text, not a paraphrase the
        # step table happens to carry. Asserting `step.rules in task` was a
        # construction tautology: `task_block()` interpolates `self.rules`.
        from alignmentgraph_isd.core import rulebook

        rulebook_blocks = {
            v.strip() for k, v in vars(rulebook).items()
            if k.startswith("RULES_") and isinstance(v, str)
        }
        composed = {rulebook.rules_for(state).strip()
                    for state in rulebook._STATE_FAMILIES}
        assert step.rules.strip(), f"{step.name} carries no rules at all"
        assert step.rules.strip() in rulebook_blocks | composed, (
            f"{step.name} shows rules that are not the rulebook's own text")


#: Reference fields the HARNESS reads back off a committed artifact. Each one is
#: an id (or an enum) the model has to write for something downstream to work,
#: so a rule that demands one while the schema example never shows it is a
#: prompt that contradicts itself.
_HARNESS_READ_FIELDS = (
    "for_modules", "supports_activities", "covers_topics", "respects_constraints",
    "aligned_objectives", "aligned_objective", "prepares_for_assessment",
    "linked_module", "activity_ids", "material_ids", "prerequisite_activities",
    "addresses_gap", "learner_cognitive_process", "required_cognitive_process",
)


def test_no_rule_demands_a_field_its_schema_example_never_shows():
    """A field named in the rules must be visible in the JSON example the same
    family is given — in its STAGE schema or, for a fanned-out family, in its
    Developer's, since that is where those artifacts are actually written.

    MEASURED FAILURE (found 2026-09-04). ``RULES_CONTENT_MODULES`` said "Every
    media selection should also set ``for_modules``" while the content stage's
    schema — a hand-written copy of the rulebook's, drifted from it — showed a
    media selection without one. ``dev_plans.material_work_units`` reads exactly
    that field and attaches a media selection with no ``for_modules`` to EVERY
    module unit: three modules x three media went out as nine media-slots
    instead of three, and ``RULES_MATERIALS_UNIT`` makes each slot a material,
    so every Developer was asked for three times what it should write.

    The fix was to stop copying: the content schema now comes from the rulebook
    like the assessment and activity ones already did. This test is the guard on
    the copy never coming back."""
    from alignmentgraph_isd.core.agentic import fanout
    from alignmentgraph_isd.core.agentic.specialists import STEPS

    for step in STEPS:
        spec = fanout.SPECS.get(step.name)
        outputs = spec.outputs if spec else ()
        schema = "\n".join([step.schema, *(o.schema for o in outputs)])
        rules = "\n".join([step.rules, *(o.rules for o in outputs)])
        for field in _HARNESS_READ_FIELDS:
            if field in rules:
                assert field in schema, (
                    f"{step.name}: the rules demand `{field}` but no JSON example "
                    "shown to that family contains it — the model is being told to "
                    "write a field it has never seen"
                )


def test_a_fanned_out_family_shows_its_developer_the_same_rulebook():
    """A Developer's prompt is composed from the same rulebook blocks as its
    stage's — the fan-out changes WHO writes an artifact, never what the rules
    for it are."""
    from alignmentgraph_isd.core import dev_plans
    from alignmentgraph_isd.core.agentic import fanout
    from alignmentgraph_isd.core.agentic.specialists import STEPS

    by_name = {step.name: step for step in STEPS}
    for family, spec in fanout.SPECS.items():
        dev = fanout.set_step(spec, dev_plans.WorkSet(set_id="S1"), by_name[family])
        for output in spec.outputs:
            assert output.rules.strip().splitlines()[0] in dev.rules, (
                f"{family}'s Developer was given rules the rulebook does not hold")
            assert output.schema.strip().splitlines()[0] in dev.schema


def test_the_instructed_stage_order_is_generated_from_the_step_table():
    """It was hand-written, and it drifted: it still named a "rubrics" stage
    long after that stage was removed, so every agent in every run was told to
    expect a seventh step that does not exist.

    A list beside the table that defines the thing is a list that will disagree
    with it."""
    from alignmentgraph_isd.core.agentic.loop import _WORKFLOW_OVERVIEW
    from alignmentgraph_isd.core.agentic.specialists import STEPS

    for index, step in enumerate(STEPS, start=1):
        assert f"{index}. {step.name}" in _WORKFLOW_OVERVIEW, step.name
    # Nothing that is not a step: the drift this guards against is a name
    # surviving its stage, not a missing one.
    assert f"{len(STEPS) + 1}." not in _WORKFLOW_OVERVIEW
    assert "rubrics" not in _WORKFLOW_OVERVIEW

    # Both arms are told the same order — the axis is who holds the context,
    # not who decides the sequence.
    from alignmentgraph_isd.core.agentic import react
    assert react._WORKFLOW_OVERVIEW is _WORKFLOW_OVERVIEW


def test_the_media_vocabulary_is_typed_once():
    """`rulebook.MEDIA_TYPES` is what the prompts state and
    `alignment._MEDIA_TYPE_ALIASES` is what P6 actually matches on. They are two
    copies because they must be: this module is the prompt layer the PROSE arm
    composes from, and importing the graph package here would add exactly the
    coupling `context_mode` exists to ablate. So the copies are asserted equal
    instead — a matcher and a prompt that disagree about the vocabulary make
    every material fail a check for saying what it was told to say."""
    from alignmentgraph_isd.core import rulebook
    from alignmentgraph_isd.core.alignment_graph import alignment

    assert set(rulebook.MEDIA_TYPES) == set(alignment._MEDIA_TYPE_ALIASES)


def test_no_schema_example_hands_a_model_a_value_it_must_derive():
    """MEASURED (run 2b9e911a): `SCHEMA_MATERIALS` showed `"type": "video",
    "format": "mp4"` and all eight materials came out video/mp4 — against six
    media selections that were slides and simulation. P6 failed 8 of 8. For a
    small model the exemplar VALUE outranks the rule beside it, so a field whose
    value has to come from the design state must show a placeholder, not one of
    its legal values."""
    from alignmentgraph_isd.core import rulebook

    example = rulebook.SCHEMA_MATERIALS
    for media_type in rulebook.MEDIA_TYPES:
        assert f'"type": "{media_type}"' not in example, (
            f"the materials example hands the model {media_type!r} to copy")
    assert '"type": "<' in example, "and it must show a placeholder instead"

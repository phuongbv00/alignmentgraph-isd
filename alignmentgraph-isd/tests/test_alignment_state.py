"""``read_alignment_state``: one role-scoped, argument-less read that answers
with alignment SIGNALS — what exists (with ids), what is missing, and the
role's own open issues — and the read → submit → re-read → fix loop it lets an
agent drive.

MEASURED, what it replaces: reads were 184 of 270 tool calls on run 14a6b4c7
and 78 of 133 on run 9efc3cfa, each a full round trip for a few hundred
characters, across three list/relation tools the model kept reaching for
through each other's door.
"""
from __future__ import annotations

import copy
import json

from alignmentgraph_isd.core.agentic import alignment_state, budget, specialists, tools
from alignmentgraph_isd.core.agentic.loop import ToolLoop
from alignmentgraph_isd.core.agentic.specialists import STEPS
from alignmentgraph_isd.core.agentic.transcript import (
    SUPERSEDED_STUB, message_size, serialize_messages, supersede_earlier,
)
from alignmentgraph_isd.core.alignment_graph import AlignmentGraph, NodeType
from alignmentgraph_isd.core.trajectory import TrajectoryLogger

from conftest import load_brief
from test_agentic_loop import (
    _ANALYSIS, _ASSESSMENT, _OUTCOMES, _harness, _loop, call,
)

STEP = {step.name: step for step in STEPS}
BRIEF = load_brief("minimal_brief.json")


def _designed_up_to_outcomes() -> tuple[AlignmentGraph, TrajectoryLogger]:
    graph, trajectory = AlignmentGraph(), TrajectoryLogger()
    specialists.commit_analysis(graph, trajectory, _ANALYSIS)
    specialists.commit_outcomes(graph, trajectory, _OUTCOMES)
    return graph, trajectory


def _plan(**over) -> dict:
    plan = copy.deepcopy(_ASSESSMENT["assessment_plan"])
    plan["lo_coverage_targets"] = {"ILO-01": ["formative", "summative"]}
    plan["instruments"] = [
        dict(plan["instruments"][0], id=f"INS-0{n}", timing=timing)
        for n, timing in enumerate(("formative", "summative"), start=1)]
    plan.update(over)
    return {"assessment_plan": plan}


# ── what the state says ─────────────────────────────────────────────────────

def test_the_state_names_ids_never_bare_counts():
    graph, _t = _designed_up_to_outcomes()
    text = alignment_state.read(graph, BRIEF, STEP["assessment"]).text

    assert text.startswith("=== ALIGNMENT STATE — assessment ===")
    assert "[OBJECTIVE:ILO-01] level=apply" in text, "id AND the facets the rules compare"
    assert "objective:ILO-01" not in text, "ids are BARE: a model echoes what it is shown"
    assert "missing for: ILO-01" in text
    assert text.rstrip().splitlines()[-1].startswith("NEXT:"), "the actionable part is LAST"


def test_a_role_sees_only_its_own_scope():
    graph, _t = _designed_up_to_outcomes()
    assessment = alignment_state.read(graph, BRIEF, STEP["assessment"]).text
    content = alignment_state.read(graph, BRIEF, STEP["content"]).text

    assert "C2-assessed_by" in assessment and "C3-" not in assessment and "C5-" not in assessment
    assert "C2-" not in content and "[OBJECTIVE:" not in content
    for step in STEPS:
        bound = tools.tool_names(tools.tool_specs(step))
        assert not {"read_nodes", "read_edges", "coverage_gaps"} & set(bound)
    assert tools.spec_parameters(tools.tool_specs(STEP["content"]),
                                 tools.STATE_TOOL)["properties"] == {}


def test_open_issues_appear_only_once_the_parts_have_landed_and_are_the_roles_own():
    graph, trajectory = _designed_up_to_outcomes()
    step = STEP["assessment"]
    before = alignment_state.read(graph, BRIEF, step)
    assert not before.shown and "(none)" in before.text

    specialists.commit_assessment(graph, trajectory, _plan(formative_methods=[]))
    after = alignment_state.read(graph, BRIEF, step)

    assert {v.violation_type for v in after.shown} == {"evaluation_quality"}
    assert "Fix:" in after.text and "NEXT: fix these" in after.text
    # A Designer whose Developer tier has not run sees no ELEMENT-level issue
    # (C2, plan_coverage: about items nobody has written yet) — and never
    # another family's.
    assert all(graph.ELEMENT_SEP not in str(v.node_id) for v in after.shown)
    assert "evaluation_quality" not in {
        v.violation_type for v in alignment_state.read(graph, BRIEF, STEP["activities"]).shown}


def test_reading_the_state_writes_nothing():
    graph, trajectory = _designed_up_to_outcomes()
    graph.add_element_node(NodeType.OBJECTIVE, "ILO-09", {
        "id": "ILO-09", "level": "apply", "bloom_verb": "memorize", "statement": "Apply Z."})
    nodes = json.dumps(graph.to_full_dict()["nodes"], sort_keys=True, default=str)
    events = len(trajectory.events)

    for step in STEPS:
        alignment_state.read(graph, BRIEF, step)

    assert json.dumps(graph.to_full_dict()["nodes"], sort_keys=True, default=str) == nodes
    assert len(trajectory.events) == events


def test_rows_a_gap_names_survive_the_budget():
    """A design large enough to overflow one read: what is cut is announced,
    the artifacts the gaps NAME come first, and the tail is never the part
    that gives way."""
    graph, _t = _designed_up_to_outcomes()
    for i in range(400):
        graph.add_element_node(NodeType.ACTIVITY, f"TLA-{i:04d}", {
            "id": f"TLA-{i:04d}", "activity_name": f"Activity number {i} " + "x" * 60,
            "duration": "60 minutes", "learner_cognitive_process": "apply"})
    text = alignment_state.read(graph, BRIEF, STEP["implementation"]).text

    assert len(text) <= alignment_state.STATE_CHAR_BUDGET
    assert "more not shown" in text
    assert "[ACTIVITY:TLA-0000]" in text, "P10 names it as unscheduled"
    assert text.rstrip().splitlines()[-1].startswith("NEXT:")


# ── the loop the agent drives ───────────────────────────────────────────────

def _assessment_run(script, **kwargs):
    model, config, graph, trajectory, brief = _harness(script)
    specialists.commit_outcomes(graph, trajectory, _OUTCOMES)
    loop = _loop(config, graph, trajectory, brief, STEP["assessment"],
                 repair_turns=ToolLoop.REPAIR_TURNS, **kwargs)
    loop.run()
    answers = [m for m in loop.messages if isinstance(m, dict) and m.get("role") == "tool"]
    return model, loop, trajectory, answers


def test_read_submit_reread_fix_is_one_loop_in_one_transcript():
    model, loop, trajectory, answers = _assessment_run([
        call("read_alignment_state", {}),
        call("submit_assessment_plan", _plan(formative_methods=[])),
        call("read_alignment_state", {}),
        call("submit_assessment_plan", _plan()),
    ])

    pointer = answers[1]["content"]
    assert pointer.startswith("COMMITTED. 1 open issue(s) on assessment (round 1 of 3)")
    assert "Fix:" not in pointer, "the details are the agent's to READ, never pushed"
    assert "Fix:" in answers[2]["content"], "...and the tool is where they are"
    assert answers[-1]["content"].startswith("COMMITTED: the assessment artifact")
    assert not loop.stats["gave_up"]
    assert loop.stats["state_reads"] == 2 and loop.stats["rereads_changed"] == 1
    # Shown by the tool => the ledger can credit the agent with the fix.
    finding = next(f for f in loop.memory.findings if f.violation_type == "evaluation_quality")
    assert finding.shown_to_agent == 1
    steps = [tc["tool"].split(".", 1)[1] for tc in trajectory.tool_calls]
    assert steps == ["tool_read_alignment_state_assessment",
                     "design_assessment_assessment_plan",
                     "tool_read_alignment_state_assessment_r2", "design_assessment_fix1"]


def test_an_agent_that_reads_its_issues_and_submits_nothing_closes_the_stage_uncut():
    """Looking and declining is the agent's right. Left to the turn ceiling it
    would read as `via_budget_exhaustion` — the figure the decomposition claim
    rests on neither arm having reached."""
    idle = [call("read_node", {"ids": ["ILO-01"], "n": i}) for i in range(10)]
    model, loop, trajectory, _answers = _assessment_run([
        call("submit_assessment_plan", _plan(formative_methods=[])),
        call("read_alignment_state", {}),
    ] + idle)

    assert model.invocations == 2 + budget.REPAIR_IDLE_TURNS
    assert not loop.stats["via_budget_exhaustion"] and not loop.stats["gave_up"]
    declined = [e for e in trajectory.recovery_events if e["action"] == "repair_declined"]
    assert len(declined) == 1
    finding = next(f for f in loop.memory.findings if f.violation_type == "evaluation_quality")
    assert finding.shown_to_agent == 1 and finding.open_reason == "converged"


def test_an_agent_that_never_rechecks_leaves_its_findings_unshown():
    """The pointer says THAT something is open. An agent that keeps submitting
    without looking spends its rounds, and the ledger says nobody showed it."""
    resubmit = call("submit_assessment_plan", _plan(formative_methods=[]))
    _model, loop, trajectory, answers = _assessment_run(
        [resubmit] + [resubmit] * 6)

    pointers = [a["content"] for a in answers if "open issue(s)" in a["content"]]
    assert len(pointers) == budget.REPAIR_TURNS, "repair rounds are still bounded"
    assert loop.stats["state_reads"] == 0
    finding = next(f for f in loop.memory.findings if f.violation_type == "evaluation_quality")
    assert finding.shown_to_agent == 0 and finding.open_reason == "budget"
    assert any(e["action"] == "budget_exhausted" for e in trajectory.recovery_events)


def test_a_developer_binds_no_read_unless_its_assignment_was_cut():
    """A work set's assignment IS its state, written into its turn, and the
    family's gaps belong to whoever planned the sets. MEASURED: Developer reads
    were 139 of 184 (run 14a6b4c7) and 42 of 78 (run 9efc3cfa) with a list
    tool bound, and still 31 of 80 (run 53a9cd1a) with only `read_node` —
    every one of them for an id the assignment had written out."""
    from alignmentgraph_isd.core import dev_plans
    from alignmentgraph_isd.core.agentic import fanout

    for name, spec in fanout.SPECS.items():
        developer = fanout.set_step(spec, dev_plans.WorkSet(set_id="S1"), STEP[spec.stage])
        reads = [n for n in tools.tool_names(tools.tool_specs(developer)) if n.startswith("read")]
        assert reads == [], (name, reads)
    long_set = dev_plans.WorkSet(set_id="MU-01", payload={"modules": [
        {"id": "MOD-01", "title": "t", "description": "x" * fanout.ASSIGNMENT_CHAR_CAP}]})
    cut = fanout.set_step(fanout.SPECS["content"], long_set, STEP["content"])
    assert "read_node" in tools.tool_names(tools.tool_specs(cut)), "what the cut took is readable"
    assert "too long to show whole" in cut.intro



# ── an old snapshot does not sit in the window ──────────────────────────────

def _state_result(call_id: str, text: str) -> dict:
    return {"role": "tool", "tool_call_id": call_id, "name": tools.STATE_TOOL, "content": text}


def test_an_older_state_read_is_stubbed_in_the_live_context_and_kept_in_the_record():
    messages = [{"role": "system", "content": "s"},
                _state_result("c1", "=== ALIGNMENT STATE — a ===\n" + "x" * 3000),
                {"role": "tool", "tool_call_id": "c2", "name": "read_node", "content": "node"},
                _state_result("c3", "=== ALIGNMENT STATE — a ===\nnewer")]

    assert supersede_earlier(messages, tools.STATE_TOOL, "c3") == 1

    assert messages[1]["content"] == SUPERSEDED_STUB and messages[1]["tool_call_id"] == "c1"
    assert messages[2]["content"] == "node", "a read by id is never superseded"
    assert messages[3]["content"].endswith("newer")
    assert message_size(messages[1]) < 100, "the window holds the stub, and is metered as it"
    published = serialize_messages(messages)
    assert published[1]["superseded"] is True
    assert published[1]["original_content"].endswith("x" * 3000), "the record keeps what was shown"
    assert "superseded" not in published[3]
    assert supersede_earlier(messages, tools.STATE_TOOL, "c3") == 0, "idempotent"


def test_the_loop_supersedes_on_a_new_read_and_never_on_a_refused_repeat():
    _model, loop, _t, answers = _assessment_run([
        call("read_alignment_state", {}),
        call("read_alignment_state", {}),                 # unchanged: refused, nothing stubbed
        # Leaves an issue open, so the stage keeps its repair turns and the
        # read below runs; a clean plan ends the stage on the spot.
        call("submit_assessment_plan", _plan(formative_methods=[])),
        call("read_alignment_state", {}),                 # changed: answered, the first is stubbed
    ])
    state = [a for a in answers if a["name"] == tools.STATE_TOOL]

    assert state[0].get("superseded") and state[0]["content"] == SUPERSEDED_STUB
    assert "has not changed" in state[1]["content"] and not state[1].get("superseded")
    assert state[2]["content"].startswith("=== ALIGNMENT STATE") and not state[2].get("superseded")


# ── the same loop in the single arm, and the run-level record ───────────────

def test_both_arms_point_at_the_tool_and_close_a_declined_repair_by_one_rule():
    """The pointer's words, the idle allowance and the event are ONE rule: a
    repair flow lenient on one side of the decomposition axis would be a
    termination difference sitting inside the treatment."""
    import inspect

    from alignmentgraph_isd.core.agentic import loop, react

    for owner in (loop.ToolLoop, react.ReactLoop):
        source = inspect.getsource(owner)
        assert "open_issues_pointer(" in source
        assert "budget.REPAIR_IDLE_TURNS" in source and '"repair_declined"' in source
        assert "repair_turn.stamp_shown(" in source
        assert "supersede_earlier(" in source
    assert budget.REPAIR_IDLE_TURNS == 2


def test_a_run_says_which_protocol_it_spoke_and_how_blind_its_submits_were():
    from alignmentgraph_isd import HarnessRunConfig
    from alignmentgraph_isd.core.agentic import protocol
    from conftest import FakeChatModel, run_brief

    for mode in ("multi", "single"):
        result = run_brief(BRIEF, HarnessRunConfig(llm_factory=lambda: FakeChatModel(),
                                                   agent_mode=mode))
        assert result["metadata"]["run_config"]["protocol_rev"] == protocol.PROTOCOL_REV
        autonomy = result["metadata"]["autonomy"]
        assert sum(stage["state_reads"] for stage in autonomy.values()) >= 5, mode
        # The fixture reads before it writes, as the protocol asks — except
        # `analysis` in the multi arm, which builds on the scenario alone and
        # binds no state tool to read.
        assert sum(stage["blind_submits"] for stage in autonomy.values()) == 0, mode
        assert not any(stage["via_budget_exhaustion"] for stage in autonomy.values()), mode


# ── a model that has stopped acting (run 4bb81369) ──────────────────────────

def test_the_closing_line_names_the_write_and_nothing_after_it():
    """MEASURED (run 4bb81369, assessment): the state's last line ended
    "...then call this again", and a 2B model did exactly that — 26 state reads
    in a row, no submit, the stage lost to its turn ceiling. A small model
    weights the LAST instruction heaviest, so it is the write, by tool name."""
    graph, _t = _designed_up_to_outcomes()
    last = alignment_state.read(graph, BRIEF, STEP["assessment"],
                                submit_tool="submit_assessment_plan").text.splitlines()[-1]

    assert last == "NEXT: write what is missing and submit it now with submit_assessment_plan."
    assert "call this again" not in last and "read_alignment_state" not in last


def test_reads_that_buy_nothing_are_withheld_until_the_agent_submits():
    """The same run: a refusal in words did not move the model, because under
    a forced tool call the safest call it has is the read. After
    `FRUITLESS_READS` of them the binding offers submits only — its next call
    is work — and the reads come back the moment it submits."""
    from test_agentic_loop import _recording_bindings

    read = call("read_alignment_state", {})
    # A REJECTED submit, so the stage stays open and the binding after it can
    # be looked at: the completing submit ends the stage and binds nothing.
    script = [read] * 4 + [call("submit_assessment_plan", {"assessment_plan": {}}),
                           read, call("submit_assessment_plan", _plan())]
    model, bindings = _recording_bindings(script)
    from alignmentgraph_isd import HarnessRunConfig
    from alignmentgraph_isd.core.agentic.client import AgenticLLM

    config = HarnessRunConfig(llm_factory=lambda: model)
    graph, trajectory = AlignmentGraph(), TrajectoryLogger()
    specialists.commit_outcomes(graph, trajectory, _OUTCOMES)
    loop = ToolLoop(config, graph, trajectory, BRIEF, STEP["assessment"],
                    AgenticLLM(config, trajectory, STEP["assessment"].identity))
    loop.run()

    reads_offered = [any(n.startswith("read") for n in b) for b in bindings]
    # call 1 answered, calls 2-3 refused (fruitless 1, 2) -> withheld from call 4 on
    assert reads_offered[:3] == [True, True, True]
    assert reads_offered[3] is False, bindings[3]
    assert all(n.startswith("submit") for n in bindings[3])
    refusals = [m["content"] for m in loop.messages
                if isinstance(m, dict) and "has not changed" in str(m.get("content"))]
    assert "call submit_assessment_plan now" in refusals[0]
    assert "read tools are withheld until you submit" in refusals[1]
    # ...and once it has submitted, reading is on offer again.
    assert reads_offered[5] is True, bindings[5]
    assert not loop.stats["via_budget_exhaustion"]


def test_a_developer_guessing_ids_is_moved_to_its_submit():
    """The same run, assessment:AS-03: `read_node` for `ITEMS`, `ALL_ITEMS`,
    `ITEMS_ASSET`… through 16 reads to the turn ceiling. An ERROR read is as
    fruitless as a repeat."""
    from alignmentgraph_isd.core import dev_plans
    from alignmentgraph_isd.core.agentic import fanout
    from test_agentic_loop import _recording_bindings

    guesses = [call("read_node", {"ids": [f"ITEMS_{i}"]}) for i in range(6)]
    model, bindings = _recording_bindings(guesses)
    from alignmentgraph_isd import HarnessRunConfig
    from alignmentgraph_isd.core.agentic.client import AgenticLLM

    config = HarnessRunConfig(llm_factory=lambda: model)
    graph, trajectory = _designed_up_to_outcomes()
    from dataclasses import replace

    # As bound when its assignment had to be cut — the one case with reads.
    developer = replace(
        fanout.set_step(fanout.SPECS["assessment"],
                        dev_plans.WorkSet(set_id="AS-03", objectives=("ILO-01",)),
                        STEP["assessment"], graph),
        readable_types=fanout.SPECS["assessment"].developer_reads)
    ToolLoop(config, graph, trajectory, BRIEF, developer,
             AgenticLLM(config, trajectory, developer.identity),
             max_turns=budget.DEVELOPER_MAX_TURNS).run()

    assert bindings[0] == ("read_node", "submit_assessment_tools") or "read_node" in bindings[0]
    assert all(n.startswith("submit") for n in bindings[budget.FRUITLESS_READS]), bindings


def test_a_resent_artifact_is_not_answered_as_committed():
    """The same run, analysis: `needs_analysis` was re-sent seven times, each
    answered "COMMITTED", until the stage ran out of submit turns owing four
    artifacts. A re-send is called what it is and the artifact to write is
    named."""
    part = {"needs_analysis": _ANALYSIS["needs_analysis"]}
    _model, config, graph, trajectory, brief = _harness(
        [call("submit_needs_analysis", part)] * 2)
    loop = _loop(config, graph, trajectory, brief, STEP["analysis"])
    loop.run()

    answers = [m["content"] for m in loop.messages
               if isinstance(m, dict) and m.get("role") == "tool"]
    assert answers[0].startswith("COMMITTED. ")
    assert answers[1].startswith("ALREADY COMMITTED: needs_analysis")
    assert "Call submit_learner_analysis next." in answers[1]


def test_a_large_pool_gets_the_room_the_small_ones_leave():
    """MEASURED (run 1c0a4e81, content): the state read used 3,325 of 8,000
    characters and still cut 71 of 94 activities — an even split gave the
    one-row topic and constraint pools a third of the budget each."""
    graph, _t = _designed_up_to_outcomes()
    for i in range(94):
        graph.add_element_node(NodeType.ACTIVITY, f"TLA-{i:04d}", {
            "id": f"TLA-{i:04d}", "activity_name": f"Activity {i}",
            "duration": "45 minutes", "learner_cognitive_process": "apply"})
    text = alignment_state.read(graph, BRIEF, STEP["content"]).text

    # Under the even split this design listed 23 of its 94 activities; with the
    # small pools keeping only what they need, the budget itself is the limit.
    assert text.count("[ACTIVITY:") >= 75
    assert "more not shown" in text, "and what still does not fit is announced"
    assert "[MODULE:MOD-01]" in text and "[CONSTRAINT:CON-01]" in text
    assert len(text) <= alignment_state.STATE_CHAR_BUDGET

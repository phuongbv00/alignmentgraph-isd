"""The single arm: ONE agent, ONE loop, walking the workflow itself.

Until 2026-09-01 `single` was seven ToolLoops sharing a message list, driven by
a `for step in STEPS` in run.py — the harness decided when a stage was finished
in BOTH arms, so "single agent" named a context-sharing trick. These tests pin
the properties that make it an agent instead.
"""
from __future__ import annotations


from conftest import FakeChatModel, load_brief

from alignmentgraph_isd import HarnessRunConfig, run_design_brief
from alignmentgraph_isd.core.agentic import react, tools
from alignmentgraph_isd.core.agentic.specialists import STEPS
from alignmentgraph_isd.core.alignment_graph import AlignmentGraph, NodeType
from alignmentgraph_isd.core.trajectory import TrajectoryLogger


def _loop(responses=None, *, graph_mode=True):
    from alignmentgraph_isd.core.prose_store import ProseStore

    model = _Scripted(responses) if responses is not None else FakeChatModel()
    config = HarnessRunConfig(llm_factory=lambda: model)
    state = AlignmentGraph() if graph_mode else ProseStore()
    trajectory = TrajectoryLogger()
    loop = react.ReactLoop(config, state, trajectory, load_brief("minimal_brief.json"))
    return loop, state, trajectory, model


class _Scripted(FakeChatModel):
    """Answers a fixed script of tool calls, ignoring the prompt."""

    def __init__(self, turns):
        super().__init__()
        self._turns = list(turns)
        # A LIST, not an int: `bind_tools` copies the model on every turn, and a
        # scalar cursor would reset to 0 each time because the increment lands
        # on the copy.
        self._cursor = [0]

    def bind_tools(self, specs, **_kwargs):
        import copy as _copy

        bound = _copy.copy(self)
        bound._tools_bound = True
        bound._offered = tuple(s["function"]["name"] for s in specs)
        return bound

    def invoke(self, messages):
        from conftest import _Result

        i = self._cursor[0]
        if i >= len(self._turns):
            return _Result(content="I have nothing further.")
        name, args = self._turns[i]
        self._cursor[0] = i + 1
        return _Result(tool_calls=[{"name": name, "args": args, "id": f"c{i}"}])


def test_the_agent_walks_the_stages_itself_and_stops_when_they_are_done():
    """No harness loop over STEPS: the agent chooses each stage, and the run
    ends when the last one lands — not when a for-loop runs out."""
    result = run_design_brief(load_brief("minimal_brief.json"), HarnessRunConfig(
        llm_factory=lambda: FakeChatModel(), agent_mode="single"))

    stats = result["metadata"]["autonomy"]["design"]
    assert stats["stage_order"], "the agent recorded no stage order"
    assert set(stats["stage_order"]) == {s.name for s in STEPS}
    assert not stats["via_budget_exhaustion"], "it ran out of turns instead of finishing"
    assert not result["metadata"]["validation_errors"]
    # One record, not seven: there are no stage boundaries to report.
    assert set(result["metadata"]["autonomy"]) == {"design"}


def test_the_submit_menu_shrinks_as_stages_land():
    """A `submit_<stage>` is offered only while that stage is open. That is
    state being reported, not the harness steering: the agent still picks."""
    before = tools.tool_names(tools.react_specs(STEPS, frozenset()))
    after = tools.tool_names(tools.react_specs(STEPS, frozenset({"analysis", "outcomes"})))

    assert "submit_analysis" in before and "submit_analysis" not in after
    assert "submit_content" in before and "submit_content" in after
    # The read tools are the UNION over every stage: this agent is not scoped.
    assert {"read_nodes", "read_node", "read_edges", "coverage_gaps"} <= set(before)
    # Compare the SETS, not a tail slice of the longer list: the all-done
    # binding is strictly smaller, so `[len(before):]` was always empty and the
    # assertion could not fail.
    done = tools.tool_names(tools.react_specs(STEPS, frozenset(s.name for s in STEPS)))
    assert not [n for n in done if n.startswith("submit_")], "no submits left when done"
    assert {n for n in done if not n.startswith("submit_")} == {
        n for n in before if not n.startswith("submit_")}, "the read tools must not change"


def test_a_submit_adds_to_a_stage_rather_than_replacing_it():
    """The affordance that makes "the agent splits its own work" a real option:
    a family too large for one 8192-token completion can only be produced across
    several calls, so a second submit must ADD."""
    from test_agentic_loop import _ANALYSIS, _ASSESSMENT, _OUTCOMES

    first = dict(_ASSESSMENT)
    second = {"assessment_tools": [
        dict(_ASSESSMENT["assessment_tools"][0], item_id="AT-99", question="A second batch.")]}
    loop, graph, _t, _m = _loop([
        ("submit_analysis", _ANALYSIS),
        ("submit_outcomes", _OUTCOMES),
        ("submit_assessment", first),
        ("submit_assessment", second),
    ])
    loop.run()

    items = graph.element_nodes(NodeType.ASSESSMENT)
    assert len(items) > len(first["assessment_tools"]), (
        "the second submit replaced the first batch instead of adding to it")
    assert loop.stats["submits_per_stage"]["assessment"] == 2


def test_every_key_the_submit_offers_appears_in_that_stages_brief():
    """A fan-out family's brief must cover BOTH halves: in the multi arm its
    items come from Developers who are shown their schema separately, but this
    agent writes plan and items alike. Offering `assessment_tools` on the submit
    tool while the brief shows only the plan asks for something the agent has
    never been shown the shape of."""
    loop, _g, _t, _m = _loop([])
    brief = loop.stage_brief("assessment")

    spec = [s for s in tools.react_specs(STEPS, frozenset())
            if s["function"]["name"] == "submit_assessment"][0]
    for key in spec["function"]["parameters"]["properties"]:
        assert f'"{key}"' in brief, f"the submit offers {key} but the brief never shows it"


def test_the_system_turn_leaves_room_for_the_transcript():
    """MEASURED FAILURE (run single_20260901_151738): with all six stages'
    schemas inlined, the system turn was 23,668 characters against a 24,000
    history budget. `trim_history` kept it and dropped everything else — 189
    drops in one run — so the agent saw the whole specification and almost
    nothing of what it had just done: 26-42 repeated reads, 21 rejected
    submits, and 96 turns with ZERO stages complete.

    A specification the agent cannot afford to remember anything alongside is
    not a specification it can act on."""
    from alignmentgraph_isd.core.agentic.loop import HISTORY_CHAR_BUDGET

    loop, _g, _t, _m = _loop([])
    system = len(loop._system_prompt())

    assert system < HISTORY_CHAR_BUDGET // 3, (
        f"the system turn is {system} of a {HISTORY_CHAR_BUDGET} budget; "
        "the agent has no room left to remember its own work")
    # ...and the schemas it displaces are still reachable, one at a time.
    assert "stage_brief" in tools.tool_names(tools.react_specs(STEPS, frozenset()))
    assert '"assessment_plan"' in loop.stage_brief("assessment")


def test_the_graph_arm_is_pushed_the_docket_and_the_prose_arm_is_not():
    """`context_mode` has to mean the same thing in both decomposition arms.
    The multi arm's stage message carries the docket; leaving it out here would
    make the two axes interact for a reason that is not either axis."""
    from test_agentic_loop import _ANALYSIS, _OUTCOMES
    from alignmentgraph_isd.core.agentic import specialists

    # A docket is coverage instantiated against graph state, so an EMPTY graph
    # has none in EITHER arm — comparing the two there compares "" with "" and
    # proves nothing. Commit enough for the graph arm to have something to say.
    loop, graph, traj, _m = _loop([], graph_mode=True)
    specialists.commit_analysis(graph, traj, _ANALYSIS)
    specialists.commit_outcomes(graph, traj, _OUTCOMES)

    prose_loop, store, ptraj, _m2 = _loop([], graph_mode=False)
    specialists.commit_analysis_prose(store, ptraj, _ANALYSIS)
    specialists.commit_outcomes_prose(store, ptraj, _OUTCOMES)

    docket = loop._docket()
    assert "=== ALIGNMENT STATE ===" in docket, (
        "the graph arm computed no docket from a graph that has objectives — "
        "without this the contrast below is vacuous")
    assert prose_loop._docket() == "", "the prose arm has no docket to compute"


def test_a_stage_that_is_already_done_is_never_offered():
    """The exit condition and the menu are the same fact, so a run over an
    already-complete design makes no model call at all."""
    from test_agentic_loop import _ANALYSIS

    loop, graph, _t, model = _loop([])
    from alignmentgraph_isd.core.agentic import specialists

    specialists.commit_analysis(graph, _t, _ANALYSIS)
    assert "analysis" in loop._done()
    # The docstring's actual claim, which nothing checked: a stage already in
    # the design state is not offered, so nothing asks the model about it.
    assert "submit_analysis" not in tools.tool_names(
        tools.react_specs(STEPS, loop._done()))
    assert model._cursor[0] == 0, "reading the design state cost a model turn"


def test_running_out_of_turns_is_recorded_not_hidden():
    """The budget is deliberately non-binding, and the claim that it did not cut
    either arm is only checkable if the moment it does is recorded."""
    loop, _g, trajectory, _m = _loop([("read_nodes", {"node_type": "gap"})] * 200)
    loop.MAX_TURNS = 4
    loop.run()

    assert loop.stats["via_budget_exhaustion"]
    assert any(e["action"] == "budget_exhausted"
               for e in trajectory.to_dict()["events"])


def test_one_stage_cannot_consume_the_whole_run():
    """MEASURED FAILURE (run single_20260901_154303): the prose arm submitted
    `analysis` 61 times and spent its entire 96-turn budget on a stage it had
    already finished, overwriting it each time.

    A stage submitted over and over without completing is a disagreement
    between the validator (which accepted) and the done-guard (which did not),
    and accepting it forever turns that disagreement into the whole run. The
    submits stay ADDITIVE — a second batch is the point — but they are capped,
    and the cap says what to do next."""
    from test_agentic_loop import _ANALYSIS

    over = react.ReactLoop.SUBMIT_CAP + 4
    loop, graph, trajectory, _m = _loop([("submit_analysis", _ANALYSIS)] * over)
    loop.run()

    assert loop.stats["submits_per_stage"]["analysis"] == react.ReactLoop.SUBMIT_CAP
    # ...and the refusal is actionable, not a silent drop.
    told = " ".join(str(m.get("content", "")) for m in loop.messages if isinstance(m, dict))
    assert "another stage" in told


def test_a_stage_that_keeps_being_rejected_hits_the_same_cap():
    """MEASURED FAILURE (run single_20260901_205901): the cap counted only
    ACCEPTED submits, so a stage stuck at 1 accepted submit could be rejected
    76 more times without ever reaching it. The arm burned all 96 turns on
    three of six stages and scored 0.0 on Analysis and Implementation.

    A rejected submit costs the same turn as an accepted one, and a stage that
    cannot pass its validator is exactly what the cap is for."""
    over = react.ReactLoop.SUBMIT_CAP + 6
    # `{}` is an empty submit: rejected every time, never committed.
    loop, _g, trajectory, _m = _loop([("submit_analysis", {})] * over)
    loop.run()

    rejected = [e for e in trajectory.recovery_events if e["action"] == "submit_rejected"]
    assert len(rejected) == react.ReactLoop.SUBMIT_CAP, (
        "rejections must count toward the per-stage cap, not run unbounded")
    # What the stage COMMITTED stays its own series: folding failures into it
    # would make a stuck stage read as a productive one.
    assert loop.stats["submits_per_stage"].get("analysis", 0) == 0
    told = " ".join(str(m.get("content", "")) for m in loop.messages if isinstance(m, dict))
    assert "another stage" in told


def test_the_prose_merge_reads_the_keys_the_commits_actually_write():
    """`_doc_keys` used to return the FAMILY name ("outcome_designer"), which is
    not a document key ("objective"). The additive merge therefore read a key
    nothing had ever written, and every second submit silently replaced its
    predecessor instead of adding to it."""

    by_name = {s.name: s for s in STEPS}
    for name in ("assessment", "activities", "content"):
        keys = react._doc_keys(by_name[name])
        assert keys, f"{name} has no document keys to merge"
        assert not any(k.endswith("_designer") or k.endswith("_planner") for k in keys), (
            f"{name} merges on a family name, not a document key: {keys}")


def test_a_rejection_brings_back_the_schema_it_lost():
    """MEASURED FAILURE (run single_20260901_162455): the graph arm was told
    "assessment_plan.lo_coverage_targets is missing" 15 times and the prose arm
    "needs_analysis.gaps must be a non-empty list" 48 times, resubmitting the
    same broken shape each time. `history_dropped` was 170 and 186 — the
    `stage_brief` answer is the oldest and largest tool observation, so trimming
    takes it first, and the agent was being corrected against a specification it
    could no longer see."""
    loop, _g, _t, _m = _loop([])
    step = {s.name: s for s in STEPS}["assessment"]

    # Nothing in the transcript: the schema comes back with the correction.
    loop.messages = [{"role": "system", "content": "s"}]
    assert "--- STAGE: assessment ---" in loop._respec(step)

    # Still in the transcript: not repeated. It is up to 7,400 characters, and
    # pasting it onto every rejection would push out the transcript it is meant
    # to sit beside.
    loop.messages.append({"role": "tool", "content": loop.stage_brief("assessment")})
    assert loop._respec(step) == ""


def test_a_committed_artifact_is_kept_as_a_record_not_as_its_payload():
    """MEASURED (run single_20260901_162455): `context_len` sat at the 23.9k trim
    ceiling for the whole run with `history_dropped` at 186, and most of the
    transcript was the agent's OWN committed artifacts carried verbatim in their
    tool-call arguments — about 5k each, all of them already in the design state
    and readable with the tools.

    Compacting them is what a single-agent design would really do, and it makes
    the axis measure the right thing: the multi arm carries no payloads either
    (it starts each stage fresh), so before this, part of the measured gap was
    the single arm re-sending its own JSON. What it still accumulates is what it
    must actually hold in mind — every instruction, every observation, and a
    record of everything it produced."""
    from test_agentic_loop import _ANALYSIS, _ASSESSMENT, _OUTCOMES

    loop, graph, _t, _m = _loop([
        ("submit_analysis", _ANALYSIS),
        ("submit_outcomes", _OUTCOMES),
        ("submit_assessment", _ASSESSMENT),
    ])
    loop.run()

    for message in loop.messages:
        calls = (message.get("tool_calls") if isinstance(message, dict)
                 else getattr(message, "tool_calls", None)) or []
        for call_ in calls:
            args = str(call_.get("function", {}).get("arguments", call_.get("args", "")))
            assert "Build the model." not in args, (
                "a committed artifact is still carried verbatim in the transcript")

    # The RECORD survives: the agent can still see what it produced and how much.
    joined = " ".join(str(m.get("content", "")) for m in loop.messages if isinstance(m, dict))
    assert "COMMITTED" in joined
    # ...and the state holds the real thing.
    assert graph.element_nodes(NodeType.ASSESSMENT)


def test_a_spent_stage_schema_is_released():
    """A stage brief is the largest observation in the transcript (up to 7,400
    characters). Keeping the spec for work already written crowds out the work
    still to do — and `_respec` puts it back the moment something is wrong."""
    from test_agentic_loop import _ANALYSIS

    loop, _g, _t, _m = _loop([
        ("stage_brief", {"stage": "analysis"}),
        ("submit_analysis", _ANALYSIS),
    ])
    loop.run()

    joined = " ".join(str(m.get("content", "")) for m in loop.messages if isinstance(m, dict))
    assert "--- STAGE: analysis ---" not in joined, "the spent schema is still held"
    assert "that stage has been submitted" in joined, "and nothing says why it went"

"""The single arm: ONE agent, ONE loop, walking the workflow itself.

Until 2026-09-01 `single` was seven ToolLoops sharing a message list, driven by
a `for step in STEPS` in run.py — the harness decided when a stage was finished
in BOTH arms, so "single agent" named a context-sharing trick. These tests pin
the properties that make it an agent instead.
"""
from __future__ import annotations


from conftest import FakeChatModel, load_brief, run_brief

from alignmentgraph_isd import HarnessRunConfig
from alignmentgraph_isd.core.agentic import react, tools
from alignmentgraph_isd.core.agentic.protocol import STAGE_BRIEF_HEADER
from alignmentgraph_isd.core.agentic.specialists import STEPS
from alignmentgraph_isd.core.alignment_graph import AlignmentGraph, NodeType
from alignmentgraph_isd.core.trajectory import TrajectoryLogger


def _said(loop) -> str:
    """Everything the agent was shown, compacted turns included.

    `loop.messages` is only what is still being SENT, so a long run answers
    "was it told X" with "not any more" once `trim_history` has fired. The
    package already models the whole conversation — `compacted_transcript` is
    what the Context tab renders — and that is the thing these assertions are
    about.
    """
    from alignmentgraph_isd.core.agentic.transcript import compacted_transcript
    return " ".join(str(m.get("content", ""))
                    for m in compacted_transcript(loop.messages, loop.compacted)
                    if isinstance(m, dict))


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
    result = run_brief(load_brief("minimal_brief.json"), HarnessRunConfig(
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
    # One state read (scoped to whichever stage is current) and the full-text
    # read by id, whose scope is the UNION over every stage.
    assert {"read_alignment_state", "read_node"} <= set(before)
    assert not {"read_nodes", "read_edges", "coverage_gaps"} & set(before)
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

    import copy

    # The PLAN travels with the first batch: its tasks are what an item is
    # filed inside, so a batch arriving before them has nowhere to land. Two
    # tasks and items for one: the stage still owes the other, so it stays
    # open for the second batch.
    first = copy.deepcopy(_ASSESSMENT)
    tasks = first["assessment_plan"]["sets"][0]["assessment_tasks"]
    tasks.append(dict(tasks[0], id="AT-02", timing="formative", weight_percent=0))
    first["assessment_plan"]["lo_coverage_targets"] = {"ILO-01": ["summative", "formative"]}
    second = {"assessment_tools": [
        dict(_ASSESSMENT["assessment_tools"][0], item_id="AT-99", task_id="AT-02",
             plan_category="formative", question="A second batch.")]}
    loop, graph, _t, _m = _loop([
        ("submit_analysis", _ANALYSIS),
        ("submit_outcomes", _OUTCOMES),
        ("submit_assessment", first),
        ("submit_assessment", second),
    ])
    loop.run()

    items = [one for n in graph.element_nodes(NodeType.ASSESSMENT)
             for one in (n["data"].get("items") or [])]
    assert len(items) > len(first["assessment_tools"]), (
        "the second submit replaced the first batch instead of adding to it")
    assert loop.stats["submits_per_stage"]["assessment"] == 2


def test_every_key_the_submit_offers_appears_in_that_stages_brief():
    """A fan-out family's submit tool must cover BOTH halves: in the multi arm
    its items come from Developers who are shown their schema separately, but
    this agent writes plan and items alike — so the ONE ``submit_assessment``
    tool it is offered must carry parameters for both, not just the plan.

    The artifact's SHAPE moved out of the brief's text and into the tool's own
    ``parameters`` (2026-09-08, see ``artifact_schemas.py``): a key the submit
    tool offers no longer needs to appear in the brief as text for the model to
    see its shape — the binding itself carries it, every call. What still
    matters is that the OFFER is complete."""
    spec = [s for s in tools.react_specs(STEPS, frozenset())
            if s["function"]["name"] == "submit_assessment"][0]
    offered = set(spec["function"]["parameters"]["properties"])
    assert {"assessment_plan", "assessment_tools"} <= offered, (
        f"the assessment submit tool is missing a half of what it should offer: {offered}")


def test_the_system_turn_leaves_room_for_the_transcript():
    """MEASURED FAILURE (run single_20260901_151738): with all six stages'
    schemas inlined, the system turn was 23,668 characters against a 24,000
    history budget. `trim_history` kept it and dropped everything else — 189
    drops in one run — so the agent saw the whole specification and almost
    nothing of what it had just done: 26-42 repeated reads, 21 rejected
    submits, and 96 turns with ZERO stages complete.

    A specification the agent cannot afford to remember anything alongside is
    not a specification it can act on."""
    from alignmentgraph_isd.core.agentic.transcript import HISTORY_CHAR_BUDGET

    loop, _g, _t, _m = _loop([])
    system = len(loop._system_prompt())

    assert system < HISTORY_CHAR_BUDGET // 3, (
        f"the system turn is {system} of a {HISTORY_CHAR_BUDGET} budget; "
        "the agent has no room left to remember its own work")
    # ...and the schemas it displaces still arrive, ONE STAGE AT A TIME: pushed
    # by `_offer_contract` as each stage comes up, not fetched and not all six.
    assert "stage_brief" not in tools.tool_names(tools.react_specs(STEPS, frozenset()))
    loop._done_set = frozenset()
    loop.messages = []
    loop._offer_contract()
    assert len(loop.messages) == 1
    assert loop.messages[0]["content"].startswith(
        STAGE_BRIEF_HEADER.format(stage=STEPS[0].name))
    assert all(STAGE_BRIEF_HEADER.format(stage=s.name) not in loop.messages[0]["content"]
               for s in STEPS[1:]), "one stage's contract, not all six"
    # The schema itself is not text any more (2026-09-08) — it is the bound
    # `submit_assessment` tool's own `parameters`, offered every turn
    # regardless of what the pushed brief text says or loses to compaction.
    spec = [s for s in tools.react_specs(STEPS, frozenset())
            if s["function"]["name"] == "submit_assessment"][0]
    assert "assessment_plan" in spec["function"]["parameters"]["properties"]


def test_the_state_tool_follows_the_current_stage_and_prose_has_none():
    """`context_mode` has to mean the same thing in both decomposition arms:
    the graph arm PULLS its alignment state, scoped to the stage it is on (the
    first not yet complete — the same "current stage" the contract follows),
    and the prose arm has no such state to read."""
    from test_agentic_loop import _ANALYSIS, _OUTCOMES
    from alignmentgraph_isd.core.agentic import specialists

    loop, graph, traj, _m = _loop([], graph_mode=True)
    loop._done_set = frozenset()
    assert loop._read("read_alignment_state", {}).startswith("=== ALIGNMENT STATE — analysis ===")

    specialists.commit_analysis(graph, traj, _ANALYSIS)
    specialists.commit_outcomes(graph, traj, _OUTCOMES)
    loop._done_set = loop._done()
    state = loop._read("read_alignment_state", {})
    assert state.startswith("=== ALIGNMENT STATE — assessment ===")
    assert "missing for: ILO-01" in state, "instantiated, from a graph that has objectives"

    # While a stage is under repair the tool stays on it.
    loop._repairing = "outcomes"
    assert loop._read("read_alignment_state", {}).startswith("=== ALIGNMENT STATE — outcomes ===")

    prose_loop, _store, _pt, _m2 = _loop([], graph_mode=False)
    assert prose_loop._read("read_alignment_state", {}).startswith("ERROR: unknown tool")


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

    # Once analysis is finished its submit is no longer bound -- the current
    # stage's is -- so every resubmit after the first is refused, not counted.
    assert loop.stats["submits_per_stage"]["analysis"] == 1
    assert "submit_analysis" not in tools.tool_names(loop._live_specs)
    # ...and the refusal is actionable, not a silent drop.
    told = _said(loop)
    assert "the current one is outcomes: call submit_outcomes" in told


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
    told = _said(loop)
    assert "another stage" in told


def test_a_capped_stage_is_closed_and_the_run_moves_on():
    """MEASURED FAILURE (run a1 20261001_101147): at the cap the agent was told
    to leave the stage while the harness kept that stage current — its
    contract re-offered, the state read still on it — and 13 of 20 single-arm
    runs spent their turn ceiling resubmitting one stage. A closed stage leaves
    the menu, stops being current, and the next stage's contract is offered."""
    over = react.ReactLoop.SUBMIT_CAP + 6
    loop, _g, trajectory, _m = _loop([("submit_analysis", {})] * over)
    loop.run()

    assert loop.stats["abandoned_stages"] == ["analysis"]
    assert any(e["action"] == "stage_abandoned" for e in trajectory.recovery_events)
    assert "analysis" in loop._done_set and "analysis" not in loop._finished()
    assert "submit_analysis" not in tools.tool_names(loop._live_specs)
    assert loop._state_step().name == "outcomes"
    told = _said(loop)
    assert STAGE_BRIEF_HEADER.format(stage="outcomes") in told
    assert "repaired for you" not in told


def test_a_finished_stage_is_never_recorded_as_abandoned():
    """The cap refuses further submits to a stage that is complete; it does
    not turn written work into an abandoned stage."""
    from test_agentic_loop import _ANALYSIS

    loop, _g, _t, _m = _loop([("submit_analysis", _ANALYSIS)] * (react.ReactLoop.SUBMIT_CAP + 4))
    loop.run()

    assert loop.stats["abandoned_stages"] == []
    assert "analysis" in loop._finished()


def test_a_fanout_stage_owes_its_items_not_just_its_plan():
    """MEASURED FAILURE (run a1 20261001_101147): the single arm finished a
    fan-out stage the moment its plan landed, its submit left the menu, and 20
    of 20 single-arm runs shipped no assessment item. This agent has no
    Developers, so the item lists are part of what the stage owes — on both
    substrates."""
    from alignmentgraph_isd.core.agentic import fanout

    for graph_mode in (True, False):
        loop, _s, _t, _m = _loop([], graph_mode=graph_mode)
        by_name = {s.name: s for s in STEPS}
        for stage, items in (("assessment", "assessment_tools"),
                             ("activities", "learning_activities"),
                             ("content", "learner_materials"),
                             ("implementation", "session_guides")):
            assert fanout.missing_outputs(stage, loop.state) == (items,)
            assert items in loop._owed(by_name[stage])
        assert fanout.missing_outputs("analysis", loop.state) == ()


def test_a_single_run_writes_the_items_its_plans_ask_for():
    """End to end, both substrates: every fan-out family has artifacts."""
    for context_mode in ("graph", "prose"):
        result = run_brief(load_brief("minimal_brief.json"), HarnessRunConfig(
            llm_factory=lambda: FakeChatModel(), agent_mode="single",
            context_mode=context_mode))
        dev = result["addie_output"]["development"]
        items = [i for t in dev["assessment_tools"] for i in (t.get("items") or [t])]
        assert items, context_mode
        assert dev["learner_materials"], context_mode
        assert result["metadata"]["autonomy"]["design"]["abandoned_stages"] == []


def test_the_single_arm_reports_context_per_stage():
    """The registered prediction is that context grows with stage position in
    single and not in multi. The multi arm reports one record per stage; the
    single arm's one record has to carry the same series or the prediction
    cannot be read off it."""
    result = run_brief(load_brief("minimal_brief.json"), HarnessRunConfig(
        llm_factory=lambda: FakeChatModel(), agent_mode="single"))
    design = result["metadata"]["autonomy"]["design"]
    by_stage = design["context_len_by_stage"]
    assert set(by_stage) == {s.name for s in STEPS}
    assert all(v > 0 for v in by_stage.values())
    assert max(by_stage.values()) == design["context_len"]
    assert set(design["turns_by_stage"]) == set(by_stage)


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
    assert STAGE_BRIEF_HEADER.format(stage="assessment") in loop._respec(step)

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
    joined = _said(loop)
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

    joined = _said(loop)
    assert STAGE_BRIEF_HEADER.format(stage="analysis") not in joined, (
        "the spent schema is still held")
    assert "that stage has been submitted" in joined, "and nothing says why it went"


def test_both_arms_answer_a_repeat_through_the_one_guard():
    """One wording and one rule: a guard lenient on one side of the
    decomposition axis would be a ceiling difference inside the treatment."""
    import inspect

    from alignmentgraph_isd.core.agentic import loop, protocol, react

    for owner in (loop.ToolLoop, react.ReactLoop):
        source = inspect.getsource(owner)
        assert "turn_mod.answer_read(" in source
        assert "You already made" not in source and "You already called" not in source, (
            f"{owner.__name__} words its own refusal")
    assert "result has not changed since the last call" in protocol.REPEAT_UNCHANGED


def test_only_the_current_stage_submit_is_bound():
    """MEASURED FAILURE (run a1 20261001_101147): every open stage's submit at
    once was ~19.5k characters of schema, ~6.5k of the 8,192 prompt tokens the
    window leaves, and the single arms sent 419 requests over the window. The
    stage order is instructed and fixed in both arms, so the binding carries
    the current stage's submit the way a stage loop carries its own."""
    names = tools.tool_names(tools.react_specs(STEPS, frozenset(), current="analysis"))
    assert [n for n in names if n.startswith("submit_")] == ["submit_analysis"]
    # A stage under repair is current even though it is finished.
    names = tools.tool_names(tools.react_specs(
        STEPS, frozenset({"analysis"}), current="analysis"))
    assert [n for n in names if n.startswith("submit_")] == ["submit_analysis"]


class _OverflowsFirst(_Scripted):
    """Refuses the first ``n`` requests the way vLLM refuses a prompt that
    does not fit, then answers the script."""

    def __init__(self, turns, n):
        super().__init__(turns)
        self._refusals = [n]

    def invoke(self, messages):
        if self._refusals[0] > 0:
            self._refusals[0] -= 1
            raise RuntimeError(
                "Error code: 400 - This model's maximum context length is 16384 tokens. "
                "However, you requested 8192 output tokens and your prompt contains at "
                "least 8193 input tokens")
        return super().invoke(messages)


def test_a_request_over_the_window_is_trimmed_not_blamed_on_the_model():
    """The window refusing a request is the harness's sizing, not the model
    failing to call a tool: it is not nudged, not charged within the error
    allowance, and the next request carries a narrower transcript."""
    from test_agentic_loop import _ANALYSIS

    from alignmentgraph_isd.core.agentic import turn as turn_mod

    model = _OverflowsFirst([("submit_analysis", _ANALYSIS)], n=2)
    config = HarnessRunConfig(llm_factory=lambda: model)
    loop = react.ReactLoop(config, AlignmentGraph(), TrajectoryLogger(),
                           load_brief("minimal_brief.json"))
    loop.run()

    assert loop.stats["context_overflows"] == 2
    assert loop.stats["submits_per_stage"]["analysis"] == 1
    # The refusals are not answered with a nudge: the first thing the agent
    # is told after its protocol turn is the answer to its submit. (Nudges
    # later in the run answer the script running out, not the window.)
    told = _said(loop)
    assert told.index("COMMITTED") < told.find("must CALL A TOOL") or \
        "must CALL A TOOL" not in told
    # Every refusal halves what the next request may carry; a request that
    # fits restores it.
    meter = turn_mod.TurnMeter({}, max_turns=10)
    meter.context_overflowed()
    meter.context_overflowed()
    assert turn_mod.squeezed(8000, meter) == 2000
    meter.request_fit()
    assert turn_mod.squeezed(8000, meter) == 8000


def test_both_arms_report_what_each_stage_cost_and_it_adds_up():
    """The cost of a stage is read the same way on both arms: the run's calls
    and tokens between two stage boundaries. Every call the run made is charged
    to exactly one stage, so the stages add up to the run's own total."""
    for agent_mode in ("multi", "single"):
        result = run_brief(load_brief("minimal_brief.json"), HarnessRunConfig(
            llm_factory=lambda: FakeChatModel(), agent_mode=agent_mode))
        autonomy = result["metadata"]["autonomy"]
        per_stage = (autonomy["design"]["spend_by_stage"] if agent_mode == "single"
                     else {name: rec for name, rec in autonomy.items()})
        assert set(per_stage) == {s.name for s in STEPS}, agent_mode
        assert all(rec["llm_calls"] > 0 for rec in per_stage.values()), agent_mode
        total = result["metadata"]["token_usage"]
        assert sum(rec["llm_calls"] for rec in per_stage.values()) == total["llm_calls"], agent_mode


def test_a_turns_cost_is_charged_to_the_stage_it_prepares():
    """The boundary sits at the TOP of a turn, before the trim and the
    compaction that prepare it: a fold made for the outcomes turn is outcomes'
    cost, not analysis's, and nothing spent before the first turn is dropped."""
    import inspect

    loop, _g, trajectory, _m = _loop([])
    spent = [(0, 0, 0)]
    trajectory.spent = lambda: spent[0]
    loop.stats["spend_by_stage"] = {}
    loop._spend_mark, loop._spend_stage = spent[0], "analysis"
    spent[0] = (2, 100, 10)            # the analysis turns
    loop._book_spend("outcomes")
    spent[0] = (3, 160, 30)            # a compaction, then the outcomes turn
    loop._book_spend(None)
    assert loop.stats["spend_by_stage"] == {
        "analysis": {"llm_calls": 2, "prompt_tokens": 100, "completion_tokens": 10},
        "outcomes": {"llm_calls": 1, "prompt_tokens": 60, "completion_tokens": 20}}

    body = inspect.getsource(react.ReactLoop._turns)
    assert body.index("_book_spend") < body.index("trim_history") < body.index("compact(")


def test_a_plan_only_resubmit_does_not_multiply_the_items_on_prose():
    """single x prose re-merges a document's lists after each commit. A submit
    that re-sends the plan and no items leaves the item list alone, so it must
    not be joined to itself: MEASURED on run train_1 20261002_130041, one item
    and seven plan-only submits shipped 64 copies of it."""
    import copy

    from test_agentic_loop import _ANALYSIS, _ASSESSMENT, _OUTCOMES

    loop, store, _t, _m = _loop([], graph_mode=False)
    by_name = {s.name: s for s in STEPS}
    for name, payload in (("analysis", _ANALYSIS), ("outcomes", _OUTCOMES)):
        loop._commit(by_name[name], copy.deepcopy(payload))

    def items():
        return [i for doc in [store.get(k) for k in react._doc_keys(by_name["assessment"])]
                if isinstance(doc, dict) for i in doc.get("assessment_tools") or []]

    loop._commit(by_name["assessment"], copy.deepcopy(_ASSESSMENT))
    first = len(items())
    assert first > 0
    for _ in range(6):
        loop._commit(by_name["assessment"],
                     {"assessment_plan": copy.deepcopy(_ASSESSMENT["assessment_plan"])})
    assert len(items()) == first


def _submit_params(loop, name):
    loop._done_set = loop._done()           # what `run` keeps current each turn
    return tools.spec_parameters(loop._bound_specs(), name)


def test_a_landed_artifact_is_not_offered_again_and_the_next_owed_is_required():
    """MEASURED FAILURE (run t1 20261002_134550): the fan-out stages' submit
    kept the PLAN required after it had landed, so every further call had to
    write it again; the 2B model did, and nothing else, until ``SUBMIT_CAP``
    closed the stage. 0 assessment items in 20 of 20 single-arm runs, and
    analysis resent ``needs_analysis`` eight times. Both substrates."""
    from test_agentic_loop import _ANALYSIS, _ASSESSMENT, _OUTCOMES

    for graph_mode in (True, False):
        loop, state, trajectory, _m = _loop([], graph_mode=graph_mode)
        commit = {s.name: s.commit if graph_mode else s.commit_prose for s in STEPS}

        commit["analysis"](state, trajectory, {"needs_analysis": _ANALYSIS["needs_analysis"]})
        params = _submit_params(loop, "submit_analysis")
        assert "needs_analysis" not in params["properties"], graph_mode
        assert params["required"] == ["learner_analysis"], graph_mode

        rest = {k: v for k, v in _ANALYSIS.items() if k != "needs_analysis"}
        commit["analysis"](state, trajectory, rest)
        commit["outcomes"](state, trajectory, _OUTCOMES)
        params = _submit_params(loop, "submit_assessment")
        assert params["required"] == ["assessment_plan"], graph_mode
        # The items name tasks the plan has not declared yet, so their schema
        # is not offered beside it: the two together were over the window
        # before any message (run t1 20261005_205508).
        assert list(params["properties"]) == ["assessment_plan"], graph_mode

        commit["assessment"](state, trajectory, {"assessment_plan": _ASSESSMENT["assessment_plan"]})
        params = _submit_params(loop, "submit_assessment")
        assert list(params["properties"]) == ["assessment_tools"], graph_mode
        assert params["required"] == ["assessment_tools"], graph_mode


def test_a_finished_stage_under_repair_offers_everything_and_requires_nothing():
    """A repair submits only what changes, so no artifact may be forced."""
    names = tools.react_specs(STEPS, frozenset({"assessment"}), current="assessment",
                              open_fields=())
    params = tools.spec_parameters(names, "submit_assessment")
    assert set(params["properties"]) == {"assessment_plan", "assessment_tools"}
    assert params["required"] == []


def test_a_prompt_no_trim_can_fit_ends_the_stage_instead_of_resending_it():
    """MEASURED (run t1 20261005_205508): three single-arm runs resent one
    8,193-token request 270-280 times until the turn ceiling closed the run.
    Once the squeeze is at its floor and the window still refuses, the part no
    trim reaches is over the window and sending it again changes nothing."""
    from alignmentgraph_isd.core.agentic import turn as turn_mod
    from alignmentgraph_isd.core.agentic.protocol import PROMPT_EXCEEDS_WINDOW

    meter = turn_mod.TurnMeter({}, max_turns=10)
    for _ in range(turn_mod.SQUEEZE_STEPS):
        meter.context_overflowed()
    assert not meter.cannot_fit, "the squeeze has not reached its floor yet"
    meter.context_overflowed()
    assert meter.cannot_fit
    meter.request_fit()
    assert not meter.cannot_fit

    endless = 10 ** 6
    model = _OverflowsFirst([], n=endless)
    config = HarnessRunConfig(llm_factory=lambda: model)
    trajectory = TrajectoryLogger()
    loop = react.ReactLoop(config, AlignmentGraph(), trajectory, load_brief("minimal_brief.json"))
    loop.run()
    sent = endless - model._refusals[0]
    # Bounded by the stages, a few requests each — not by the 288-turn ceiling.
    assert sent < 2 * len(STEPS) * (turn_mod.SQUEEZE_STEPS + 1), sent
    assert loop.stats["prompt_exceeds_window"]
    assert any(e["action"] == "agentic_gave_up"
               and PROMPT_EXCEEDS_WINDOW in e["context"].get("input_summary", "")
               for e in trajectory.to_dict()["events"])


def test_the_multi_arm_gives_a_stage_up_the_same_way():
    from alignmentgraph_isd.core.agentic import turn as turn_mod

    endless = 10 ** 6
    model = _OverflowsFirst([], n=endless)
    result = run_brief(load_brief("minimal_brief.json"),
                       HarnessRunConfig(llm_factory=lambda: model))
    analysis = result["metadata"]["autonomy"]["analysis"]
    assert analysis["prompt_exceeds_window"] and analysis["gave_up"]
    # Every attempt the regen loop makes stops at the floor, not the ceiling.
    assert analysis["turns_used"] <= turn_mod.SQUEEZE_STEPS + 1


import pytest as _pytest


@_pytest.mark.parametrize("graph_mode", [True, False])
def test_a_submit_that_adds_an_artifact_is_not_charged_against_the_cap(graph_mode):
    """MEASURED (run t1 20261006_091626, train_1): both single arms wrote the
    assessment items one per submit, every one committed, and the stage was
    closed at ``SUBMIT_CAP`` still owing two tasks' items. Progress is not
    charged; a submit that adds nothing still is, so a model that only resends
    is still closed."""
    import copy

    from test_agentic_loop import _ANALYSIS, _ASSESSMENT, _OUTCOMES

    from alignmentgraph_isd.core.agentic import specialists

    from alignmentgraph_isd.core import dev_plans
    from alignmentgraph_isd.core.agentic import fanout
    from alignmentgraph_isd.core.prose_store import ProseStore

    graph, trajectory = (AlignmentGraph() if graph_mode else ProseStore()), TrajectoryLogger()
    if graph_mode:
        specialists.commit_analysis(graph, trajectory, _ANALYSIS)
        specialists.commit_outcomes(graph, trajectory, _OUTCOMES)
    else:
        specialists.commit_analysis_prose(graph, trajectory, _ANALYSIS)
        specialists.commit_outcomes_prose(graph, trajectory, _OUTCOMES)
    plan = copy.deepcopy(_ASSESSMENT["assessment_plan"])
    tasks = plan["sets"][0]["assessment_tasks"]
    tasks.append(dict(tasks[0], id="AT-02", timing="formative", weight_percent=0))
    item = _ASSESSMENT["assessment_tools"][0]
    fresh = [dict(item, question=f"Build model number {i}.") for i in range(react.ReactLoop.SUBMIT_CAP + 1)]
    turns = ([("submit_assessment", {"assessment_plan": plan})]
             + [("submit_assessment", {"assessment_tools": [one]}) for one in fresh]
             + [("submit_assessment", {"assessment_tools": [fresh[0]]})] * (react.ReactLoop.SUBMIT_CAP + 2))
    model = _Scripted(turns)
    loop = react.ReactLoop(HarnessRunConfig(llm_factory=lambda: model), graph, trajectory,
                           load_brief("minimal_brief.json"))
    loop.run()

    accepted = loop.stats["submits_per_stage"]["assessment"]
    assert accepted > react.ReactLoop.SUBMIT_CAP, "progress past the cap was accepted"
    assert "assessment" in loop.stats["abandoned_stages"], "resending still closes it"
    assert loop._submit_attempts("assessment") >= react.ReactLoop.SUBMIT_CAP
    # The resends are dropped as repeats, not appended as second copies.
    held = loop._held(fanout.SPECS["assessment"].outputs[0])
    assert len(held) == len(fresh)
    assert len({dev_plans.same_artifact_key("assessment_tools", one) for one in held}) == len(held)

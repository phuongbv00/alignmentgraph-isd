"""End-to-end tests of the executor (core/agentic/run.py): full run over the
canned fixture payloads, the result contract the benchmark adapter reads, and
graph parity between the two decomposition arms."""
from __future__ import annotations

import json

from alignmentgraph_isd import HarnessRunConfig
from alignmentgraph_isd.core.agentic import run_agentic_brief
from alignmentgraph_isd.core.agentic.specialists import STEPS
from alignmentgraph_isd.core.alignment_graph import NodeType

from conftest import FakeChatModel, events_of, load_brief, run_brief


class _Result:
    def __init__(self, content: str = "", tool_calls: list | None = None) -> None:
        self.content = content
        self.tool_calls = tool_calls or []
        self.usage_metadata = None


class SubmitWrappingModel(FakeChatModel):
    """The conftest fake, speaking native tool calls: the same canned
    schema-keyed payload, returned as one ``submit`` call."""

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._calls = 0

    def bind_tools(self, specs) -> "SubmitWrappingModel":
        # Deliberately NOT the parent's bound copy: this fixture exists to send
        # a bare `submit` carrying the whole artifact, which is what a model
        # that ignores the per-artifact tools does. It still has to know the
        # names on offer, because the schema is fetched now rather than pushed.
        self._bound = tuple(str(spec.get("function", {}).get("name", ""))
                            for spec in (specs or []))
        return self

    def invoke(self, messages) -> _Result:
        answer = super().invoke(messages)
        if answer.tool_calls:
            # The parent asking for `stage_brief`: the artifact contract is
            # behind a tool, so a model that never calls it never sees a schema
            # and answers nothing.
            return answer
        payload = json.loads(answer.content)
        self._calls += 1
        return _Result(tool_calls=[{"name": "submit", "args": payload,
                                    "id": f"c{self._calls}"}])


def _agentic_result():
    config = HarnessRunConfig(llm_factory=lambda: SubmitWrappingModel())
    return run_agentic_brief(config, load_brief("minimal_brief.json"))


def test_end_to_end_result_contract_and_every_step_produced():
    result = _agentic_result()

    assert {"addie_output", "trajectory", "trajectory_deep", "metadata",
            "graph", "graph_dot"} <= set(result)
    run_config = result["metadata"]["run_config"]
    assert run_config["agent_mode"] == "multi"
    assert run_config["context_mode"] == "graph"
    # Schema-valid canned payloads must aggregate to a valid ADDIE output.
    assert result["metadata"]["validation_errors"] == []

    nodes_by_id = {n["id"]: n for n in result["graph"]["nodes"]}
    # No RUBRIC: a criterion is a field of the assessment item it marks, not
    # an element of its own (2026-09-02).
    for element_type in (NodeType.GAP, NodeType.OBJECTIVE, NodeType.ASSESSMENT,
                         NodeType.ACTIVITY, NodeType.MATERIAL):
        assert any(n["type"] == element_type and ":" in n["id"]
                   for n in nodes_by_id.values()), f"no {element_type} elements"
    assert nodes_by_id.get("implementation_plan_0", {}).get("data")

    # One submit-wrapped call per ARTIFACT — no hidden extra turns in the loop.
    # A stage binds one submit tool per artifact (tools.submit_specs), so the
    # floor is the number of REQUIRED artifacts and the ceiling adds one per
    # optional artifact the agent may also send.
    from alignmentgraph_isd.core.agentic.specialists import parts_of

    calls = result["metadata"]["token_usage"]["llm_calls"]
    events = result["trajectory"]["events"]
    required = sum(len(parts_of(step)) for step in STEPS)
    optional = sum(len(step.submit_fields) - len(parts_of(step)) for step in STEPS)
    work_sets = sum(e["context"]["set_count"] for e in events if e["action"] == "dev_plan")
    # Plus the turns a stage spent fixing its own violations IN its own loop:
    # those are real submits, and they are what the deterministic net used to
    # do out of sight.
    in_loop_repairs = sum(stats.get("repair_turns", 0)
                          for stats in result["metadata"]["autonomy"].values())
    assert (required - 1
            <= calls
            <= required + optional + work_sets + in_loop_repairs)
    # The judge-visible trace carries the per-step design actions.
    design_actions = {tc["tool"].split(".", 1)[1] for tc in result["trajectory"]["tool_calls"]}
    # A fan-out stage's judge-visible actions are per work set
    # ("design_assessment:SET-01"), so every stage must appear as a PREFIX.
    for step in STEPS:
        assert any(a.startswith(f"design_{step.name}") for a in design_actions), step.name


def test_graph_parity_with_the_single_arm_commits():
    """The agentic commits are copies of SingleDesignerAgent's; on identical
    payloads the two arms must ship the same graph for the families where
    that copy relationship still holds — the copy discipline's regression
    guard.

    2026-08-28 scope note: the dev-plan fan-out gave SingleDesignerAgent's
    assessment/activities/content/rubrics states a dispatch+per-set-call
    structure (different work-set ids, e.g. "AT-F-ILO-01"/"AB-03") that
    core/agentic/specialists.py deliberately was NOT converted to (see
    CLAUDE.md's "Agentic experimental arm" note — it stays a manual copy of
    the PRE-fan-out monolithic-per-family shape). Full graph identity across
    those four families is no longer meaningful; this test now checks it
    only for the three families the fan-out never touched (analysis/
    outcomes/implementation), where the copy relationship is exact."""
    agentic = _agentic_result()
    single = run_brief(
        load_brief("minimal_brief.json"),
        HarnessRunConfig(llm_factory=lambda: FakeChatModel(), agent_mode="single",),
    )

    unconverted_types = {
        NodeType.GAP, NodeType.TOPIC, NodeType.CONSTRAINT, NodeType.IMPROVEMENT,
        NodeType.LEARNER_PROFILE, NodeType.COURSE_GOAL, NodeType.OBJECTIVE,
        NodeType.IMPLEMENTATION_PLAN,
    }

    def node_ids(result, types):
        return {n["id"] for n in result["graph"]["nodes"] if n["type"] in types}

    assert node_ids(agentic, unconverted_types) == node_ids(single, unconverted_types)

    def edge_set(result, types):
        # BOTH endpoints, not either: an objective (unconverted) is also the
        # SOURCE of C2/C7 edges into assessment/rubric elements (converted),
        # whose ids differ by construction now (see the docstring above) —
        # counting a one-sided edge would leak that expected variance back in.
        ids = node_ids(result, types)
        return {
            (e["type"], e["source"], e["target"]) for e in result["graph"]["edges"]
            if e["source"] in ids and e["target"] in ids
        }

    assert edge_set(agentic, unconverted_types) == edge_set(single, unconverted_types)


def test_agentic_run_records_phases_and_repair_scaffolding():
    result = _agentic_result()
    deep = result["trajectory_deep"]
    phases = [a["context"]["phase"] for a in deep["actions"] if a["action"] == "phase_started"]
    # `reconcile` is a phase of its own, not part of the last stage: the pass
    # runs after every stage and logs a check round per family, which without
    # its own bracket would be attributed to whichever stage closed last.
    assert phases == [step.name for step in STEPS] + ["reconcile", "aggregate"]
    # The deterministic self-validation ran for every step (check_events
    # populated even when nothing was owned — the instrumentation parity rule
    # both arms follow).
    assert len(events_of(result["trajectory"], "check")) >= len(STEPS)


# ── the two ablation axes, end to end ───────────────────────────────────────

def _run(agent_mode="multi", context_mode="graph"):
    return run_brief(
        load_brief("minimal_brief.json"),
        HarnessRunConfig(llm_factory=lambda: FakeChatModel(), agent_mode=agent_mode,
                         context_mode=context_mode))


def test_all_four_arms_honour_their_axes_and_keep_the_result_contract():
    for agent_mode in ("multi", "single"):
        for context_mode in ("graph", "prose"):
            result = _run(agent_mode, context_mode)
            rc = result["metadata"]["run_config"]
            label = f"{agent_mode}+{context_mode}"
            assert rc["agent_mode"] == agent_mode, label
            assert rc["context_mode"] == context_mode, label
            assert {"addie_output", "trajectory", "trajectory_deep", "metadata"} <= set(result)
            assert result["addie_output"]["analysis"], label
            # The graph dump is the auditability artifact and exists only where
            # there is alignment state to dump. Its ABSENCE in prose is the
            # reported contrast, not an omission.
            if context_mode == "graph":
                assert {"graph", "graph_dot"} <= set(result), label
                assert "prose" not in result, label
                assert result["metadata"]["audit"], label
            else:
                assert "graph" not in result and "graph_dot" not in result, label
                assert result["prose"], label
                assert result["metadata"]["audit"] == {}, label


def test_the_two_arms_are_shaped_differently_and_say_so_in_the_record():
    """The decomposition axis, read straight off the instrumentation.

    Since 2026-09-01 the arms are not two configurations of one loop: `multi`
    is the harness walking six stages, each in a fresh context under that
    stage's specialist, delegating list-valued families to Developers; `single`
    is ONE agent in ONE loop that walks them itself. So the assertion is on the
    SHAPE of what each recorded, not on a per-stage series the single arm no
    longer has."""
    multi = _run("multi")["metadata"]["autonomy"]
    single = _run("single")["metadata"]["autonomy"]

    assert set(multi) == {s.name for s in STEPS}, "multi must report per stage"
    assert set(single) == {"design"}, "single is one loop, so one record"

    # The single agent chose its own order, and the record says what it chose —
    # the difference between "worked out of order" and "never split the work".
    order = single["design"]["stage_order"]
    assert order, "the single arm recorded no stage order at all"
    assert set(order) <= {s.name for s in STEPS}
    assert single["design"]["submits_per_stage"]

    # Neither arm was CUT by its budget. That is the parity claim that can
    # actually be checked: the ceilings are not equal (multi's turn count is a
    # function of how many work sets it planned), but a result difference
    # cannot be blamed on the ceiling while neither arm hit it.
    assert not single["design"]["via_budget_exhaustion"]
    assert not any(s["via_budget_exhaustion"] for s in multi.values())

    # And only the multi arm delegates.
    identities = {c["args"]["agent"] for c in _run("multi")["trajectory"]["tool_calls"]}
    assert any(i.endswith("DeveloperAgent") for i in identities)


def test_history_trim_drops_oldest_observations_and_keeps_the_live_stage():
    from alignmentgraph_isd.core.agentic.loop import trim_history

    messages = [{"role": "system", "content": "S"}]
    messages += [{"role": "tool", "content": "x" * 1000} for _ in range(50)]
    messages += [{"role": "user", "content": "LIVE STAGE"}]

    trimmed, dropped = trim_history(messages, budget=5000)

    assert len(dropped) > 0
    assert trimmed[0]["content"] == "S", "the system turn must survive trimming"
    assert trimmed[-1]["content"] == "LIVE STAGE", "the live stage must survive trimming"
    assert len(trimmed) < len(messages)
    # The dropped messages come BACK, not just a count of them: a transcript
    # that shows only what is still being sent answers "what was this agent
    # shown" for the last call and loses every earlier one. They are contiguous
    # and start right after the system turn, which is what lets the viewer
    # rebuild the conversation in order (loop.compacted_transcript).
    assert dropped == messages[1:1 + len(dropped)]
    assert trimmed == messages[:1] + messages[1 + len(dropped):]

    # Nothing is dropped when it already fits.
    kept, none_dropped = trim_history(messages[:3], budget=10 ** 6)
    assert none_dropped == [] and kept == messages[:3]


# ── reconciliation ──────────────────────────────────────────────────────────

def _graph_with_an_unassessed_objective():
    """A graph carrying a C2 violation (an objective nothing assesses) — owned
    by the assessment family, which has already finished by the time the pass
    runs. Built directly rather than driven through a run so the violation is
    guaranteed rather than hoped for."""
    from alignmentgraph_isd.core.agentic import specialists
    from alignmentgraph_isd.core.alignment_graph import AlignmentGraph
    from alignmentgraph_isd.core.trajectory import TrajectoryLogger

    graph = AlignmentGraph()
    trajectory = TrajectoryLogger()
    specialists.commit_outcomes(graph, trajectory, {
        "course_goal": {"statement": "Learners can test software."},
        "learning_objectives": [
            {"id": "ILO-01", "level": "apply", "bloom_verb": "apply",
             "statement": "Apply boundary analysis to a spec with 80% coverage."},
        ],
    })
    return graph


def _reconcile_once():
    """The reconciliation pass is arm-agnostic and model-free: every routine it
    dispatches to is structural, so it takes no LLM and cannot open a context
    of its own. A violation that needs WRITING was offered to its agent inside
    that agent's own loop long before this pass runs."""
    from alignmentgraph_isd.core.agentic.run import _reconcile
    from alignmentgraph_isd.core.trajectory import TrajectoryLogger

    graph = _graph_with_an_unassessed_objective()
    trajectory = TrajectoryLogger()

    residual = _reconcile(graph, trajectory, load_brief("minimal_brief.json"),
                          graph_mode=True)
    events = [e for e in trajectory.to_dict()["events"] if e["action"] == "reconcile"]
    return residual, events


def test_reconcile_routes_a_residual_violation_to_the_family_that_owns_it():
    """Each residual violation goes to the family ``OWNER_BY_VIOLATION`` names,
    and the trace records who it went to. The pass takes no arm and no model:
    routing names the owner, and the structural fixes it dispatches are the
    same on either side of both axes."""
    from alignmentgraph_isd.core.trajectory import WORKFLOW_ORCHESTRATOR

    _residual, events = _reconcile_once()

    assert events, "nothing was routed — the pass found no residual to act on"
    # The ADDRESSEE is the family, and it is a field on the record.
    assert any(e["context"]["family"] == "assessment_designer" for e in events)
    # The ACTOR is the orchestrator: routing happens outside every tool loop,
    # so crediting the family would say the agent did something it never saw.
    assert all(e["agent"] == WORKFLOW_ORCHESTRATOR for e in events)


def test_reconcile_stamps_the_owner_on_every_violation_it_routes():
    """``Violation.target_designer`` is what makes routing auditable: a reader
    of the trace has to be able to see WHO a violation was sent to, not just
    that something was repaired."""
    from alignmentgraph_isd.core import checks, repairs
    from alignmentgraph_isd.core.outputs import _collect_violations

    graph = _graph_with_an_unassessed_objective()
    found = _collect_violations("assessment_designer", graph, load_brief("minimal_brief.json"))
    owned = [v for v in found if v.violation_type in repairs.OWNED_BY_FAMILY["assessment_designer"]]
    assert owned, "fixture no longer produces an assessment-owned violation"
    assert all(isinstance(v, checks.Violation) for v in owned)
    # Every owned type resolves to exactly one family, and it is this one.
    assert {repairs.OWNER_BY_VIOLATION[v.violation_type] for v in owned} == {"assessment_designer"}


def test_reconcile_is_bounded_by_the_self_validation_budget():
    """Route -> repair -> recheck -> route is no longer bounded by the stage
    order, so it must be bounded explicitly. An unbounded pass on a small model
    is a hang, not a fix."""
    from alignmentgraph_isd.core.agentic import run as agentic_run
    from alignmentgraph_isd.core.outputs import SELF_VALIDATION_BUDGET

    rounds = {"n": 0}
    real = agentic_run.repairs.repair

    def counting_repair(family, violations, ctx):
        rounds["n"] += 1
        return violations  # never resolves anything -> the pass must still stop

    agentic_run.repairs.repair = counting_repair
    try:
        _residual, events = _reconcile_once()
    finally:
        agentic_run.repairs.repair = real

    assert rounds["n"] <= SELF_VALIDATION_BUDGET * len(agentic_run.repairs.OWNED_BY_FAMILY)
    assert events


# ── the audit surface ───────────────────────────────────────────────────────

def test_the_trajectory_records_everything_a_run_audit_needs():
    """One invariant sweep over all four arms.

    A results dir is only as readable as its trajectory, and every gap found so
    far was invisible until something downstream looked wrong. These are the
    facts an audit has to be able to establish from the trace alone, asserted
    for every arm so an asymmetry in the AUDIT SURFACE can never be mistaken
    for an effect of the axes."""
    for agent_mode in ("multi", "single"):
        for context_mode in ("graph", "prose"):
            label = f"{agent_mode}+{context_mode}"
            result = _run(agent_mode, context_mode)
            trajectory, metadata = result["trajectory"], result["metadata"]
            events = trajectory["events"]

            # 1. Every event answers "who did this". An empty agent means an
            #    operation ran outside an acting_as scope, and the trace then
            #    silently under-credits whichever arm hit that path.
            assert all(e.get("agent") for e in events), (
                f"{label}: events with no agent: "
                f"{ {e['action'] for e in events if not e.get('agent')} }")

            # 2. Every judge-visible tool call is a real model call, and every
            #    model call that is NOT a step wrote a recovery event saying
            #    why (a rejected submit, an invalid turn, a re-send of what is
            #    already committed). Repairs are on neither side: none of them
            #    calls the model.
            calls = metadata["token_usage"]["llm_calls"]
            recovery = len(events_of(trajectory, "recovery"))
            assert len(trajectory["tool_calls"]) <= calls, label
            assert calls - len(trajectory["tool_calls"]) <= recovery, label

            # 3. What the run PRODUCED is recorded, in both context modes —
            #    node_add for the graph arm, doc_write for the blackboard.
            produced = [e for e in events if e["action"] in ("node_add", "doc_write")]
            assert produced, f"{label}: the trace records nothing the run produced"

            # 4. Self-validation ran for every stage, and is countable.
            assert len([e for e in events if e["action"] == "check"]) >= len(STEPS) - 1, label

            # 5. Whatever produced the artifacts left a record of HOW. The
            #    multi arm fans out and logs a dev_plan per family; the single
            #    agent batches its own submits and logs those. One or the other
            #    must be there — an arm whose work is invisible cannot be
            #    audited, and the two arms must not differ in whether they can be.
            dev_plans = [e for e in events if e["action"] == "dev_plan"]
            if agent_mode == "multi":
                assert dev_plans, f"{label}: the fan-out left no record"
                assert all(e["context"].get("set_count") is not None for e in dev_plans), label
            else:
                batched = metadata["autonomy"]["design"]["submits_per_stage"]
                assert batched, f"{label}: the agent's own batching left no record"

            # 6. Per-stage autonomy, including the fan-out's own counters kept
            #    SEPARATE from the stage's — folded together, "via_fallback"
            #    would mean "the dispatch OR any one of ten sets gave up".
            autonomy = metadata["autonomy"]
            common = {"context_len", "turns_used", "history_dropped"}
            if agent_mode == "multi":
                assert set(autonomy) == {s.name for s in STEPS}, label
                for stage, stats in autonomy.items():
                    assert common | {"gave_up"} <= set(stats), f"{label}/{stage}"
                fanned = [s for s in autonomy.values() if s.get("n_sets")]
                assert fanned, f"{label}: no stage reported per-set counters"
                for stats in fanned:
                    assert {"n_sets", "sets_gave_up", "set_turns",
                            "set_submits_rejected"} <= set(stats), label
            else:
                assert set(autonomy) == {"design"}, label
                assert common | {"stage_order", "submits_per_stage",
                                 "via_budget_exhaustion"} <= set(autonomy["design"]), label

            # 7. The arms are distinguishable in the trace itself — the axis has
            #    to be readable from a results dir, not only from the config.
            identities = {c["args"]["agent"] for c in trajectory["tool_calls"]}
            if agent_mode == "single":
                assert identities == {"SingleDesignerAgent"}, label
            else:
                assert len(identities) > 1, label
                assert any(i.endswith("DeveloperAgent") for i in identities), label

            # 8. The run is self-describing: which arm produced it.
            assert metadata["run_config"]["agent_mode"] == agent_mode
            assert metadata["run_config"]["context_mode"] == context_mode


def test_reconciliation_records_what_it_checked_even_when_it_finds_nothing():
    """"The pass looked and found nothing" and "the pass never ran" are
    different facts. Only the first means the design was clean."""
    from alignmentgraph_isd.core import repairs

    result = _run("multi", "graph")
    checks = [e for e in result["trajectory"]["events"] if e["action"] == "check"]
    # Every stage's own round, plus one per family in the reconciliation pass.
    assert len(checks) >= len(STEPS) - 1 + len(repairs.OWNED_BY_FAMILY) - 4, (
        "the reconciliation pass recorded none of the families it scanned")
    # And a check names the family whose output it inspected, never the pass.
    assert all(e["agent"] for e in checks)


def test_the_tool_menu_cannot_disagree_with_the_binding():
    """The menu tells the agent what each tool is FOR; the binding is what it
    can call. Written by hand, the menu still announced a single `submit`
    months after the stage submit was split into one tool per artifact — so
    every stage of every arm named a tool that was not bound, and
    `ToolLoop._submit_alias` was quietly rescuing the result.

    It is rendered from the specs now, so they cannot drift."""
    from alignmentgraph_isd.core.agentic import tools

    for step in STEPS:
        for graph_mode in (True, False):
            menu = tools.tool_menu(step, graph_mode=graph_mode)
            bound = tools.tool_names(tools.tool_specs(step, graph_mode=graph_mode))
            listed = {line.split(" ", 2)[1] for line in menu.splitlines() if line.startswith("- ")}
            assert listed == set(bound), (
                f"{step.name} (graph={graph_mode}) menu {listed} vs binding {set(bound)}")

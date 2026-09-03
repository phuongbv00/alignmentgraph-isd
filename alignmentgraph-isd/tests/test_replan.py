"""A gap goes back to the DESIGNER, and the Designer answers with a plan.

The loop this closes. A Designer divides its family into work sets, its
Developers write them, and the checks then find an objective with no
assessment item. Until 2026-09-03 that gap reached nobody who could act on it:
every Developer loop had closed, the Designer's had closed, and the
deterministic net cannot write instructional content. It was counted as
residual and shipped.

It now goes to the Designer, whose answer is a WORK SET rather than an item —
plan and write stay the two roles the design already has — and the Developer
tier runs it exactly as it ran the first round.
"""
from __future__ import annotations


from alignmentgraph_isd import HarnessRunConfig, run_design_brief
from alignmentgraph_isd.core.agentic import replan, run as run_module
from alignmentgraph_isd.core.dev_plans import WorkSet

from conftest import FakeChatModel, load_brief


class _Gap:
    def __init__(self, vtype: str, **metadata):
        self.violation_type = vtype
        self.metadata = metadata
        self.message = f"{vtype} for {metadata.get('lo_id', '?')}"
        self.node_id = f"objective:{metadata.get('lo_id', '?')}"
        self.edge_type = ""
        self.severity = "error"
        self.target_designer = ""


# ── what a replan is asked for ───────────────────────────────────────────────

def test_only_gaps_new_work_can_close_are_sent_back():
    gaps = [_Gap("C2", lo_id="ILO-01"), _Gap("item_completeness", item_id="AT-01"),
            _Gap("evaluation_quality", section="pilot_data_plan")]

    kept = replan.gaps_for("assessment", gaps)
    assert [g.violation_type for g in kept] == ["C2"], (
        "a malformed item and a thin pilot plan are not answered by planning "
        "more work — they are the artifact's own author's to fix")
    assert replan.gaps_for("content", gaps) == [], (
        "content owns no gap a new module assignment closes")


def test_the_ground_truth_of_a_replan_is_the_gaps_and_nothing_else():
    """Normalizing against the FAMILY would re-derive every set it already
    has, and the round would rewrite work that is already done."""
    gaps = [_Gap("plan_coverage", lo_id="ILO-01", plan_category="diagnostic"),
            _Gap("plan_coverage", lo_id="ILO-01", plan_category="summative")]

    assert replan.gap_targets(gaps) == {"ILO-01": ["diagnostic", "summative"]}


def test_a_coverage_gap_with_no_category_falls_back_to_what_the_plan_promised():
    """`C2` says only "this objective has no item". The categories then come
    from the plan's own promise for it, so the round asks for the work the
    design said it wanted."""
    gaps = [_Gap("C2", lo_id="ILO-02")]

    assert replan.gap_targets(gaps, {"ILO-02": ["formative"]}) == {"ILO-02": ["formative"]}
    assert replan.gap_targets(gaps, {}) == {"ILO-02": ["summative"]}, (
        "an objective with no item at all still needs one")


def test_round_sets_are_tagged_or_they_never_run():
    """Round 0's `AS-01` is committed and `committed_set_ids` reads the
    `plan_set` stamp, so a round-1 set numbered `AS-01` again is treated as
    already done. Without the tag the round runs and produces nothing."""
    tagged = replan.tag_round([WorkSet(set_id="AS-01"), WorkSet(set_id="AS-02")], 1)

    assert [ws.set_id for ws in tagged] == ["AS-01R1", "AS-02R1"]


def test_the_designer_is_told_it_is_planning_not_writing():
    text = replan.request("assessment", [_Gap("C2", lo_id="ILO-01")], 1)

    assert "not writing" in text.lower()
    assert "dev_plan" in text
    assert "C2 for ILO-01" in text


def test_the_replan_step_keeps_the_agent_and_narrows_the_artifact():
    """Same identity, same persona: it is the same agent taking another turn
    in the conversation it is already in. One system prompt per agent is
    guarded in tests/test_one_agent_one_system_prompt.py."""
    from alignmentgraph_isd.core.agentic.specialists import STEPS

    step = {s.name: s for s in STEPS}["assessment"]
    replanned = replan.step_for(step, "assessment", [_Gap("C2", lo_id="ILO-01")], 1)

    assert replanned.identity == step.identity
    assert replanned.persona == step.persona
    assert [f[0] for f in replanned.submit_fields] == ["dev_plan"]
    assert not replanned.done(object()), (
        "its dev_plan field is filled from round 0, so the default guard would "
        "call the step finished before it had been asked anything")
    assert replanned.validate({"dev_plan": {}}), "an empty plan is not an answer"
    assert replanned.validate({"dev_plan": {"instrument_sets": [{"set_id": "X"}]}}) == []


# ── through a real run ───────────────────────────────────────────────────────

def _run_with_one_round_of_gaps(monkeypatch, gaps: list):
    """A run whose assessment family reports `gaps` the first time it is
    checked after its Developers finish, and nothing after that."""
    real = run_module._collect_violations
    seen = {"n": 0}

    def once(family, state, design_brief):
        found = real(family, state, design_brief)
        if family == "assessment_designer" and seen["n"] == 0:
            seen["n"] += 1
            return found + gaps
        return found

    monkeypatch.setattr(run_module, "_collect_violations", once)
    config = HarnessRunConfig(agent_mode="multi")
    config.llm_factory = lambda: FakeChatModel()
    return run_design_brief(load_brief("java_oop_brief.json"), config)


def test_a_gap_produces_a_second_planning_round_and_new_work(monkeypatch):
    result = _run_with_one_round_of_gaps(
        monkeypatch, [_Gap("C2", lo_id="ILO-01")])

    rounds = [p for p in result["plans"] if p["stage"] == "assessment"]
    assert len(rounds) == 2, f"expected a replan round, got {[p['round'] for p in rounds]}"
    second = rounds[1]
    assert second["round"] == 1
    assert "C2" in second["answers"], "the round records which gaps it answers"
    assert second["work_sets"], "a replan that plans no work is not a replan"
    assert all(ws["set_id"].endswith("R1") for ws in second["work_sets"])


def test_the_replan_is_a_turn_in_the_designers_own_transcript(monkeypatch):
    """Not a second conversation. The gap list, the plan and the work that
    followed have to read as one exchange, under the one system prompt that
    agent has."""
    result = _run_with_one_round_of_gaps(
        monkeypatch, [_Gap("C2", lo_id="ILO-01")])

    designer = [c for c in result["contexts"]
                if c["agent"] == "AssessmentDesignerAgent"]
    assert designer
    systems = {c["messages"][0]["content"] for c in designer}
    assert len(systems) == 1, "the Designer was given a second system prompt"
    asked = [c for c in designer
             if any("not writing" in str(m.get("content", "")).lower()
                    for m in c["messages"])]
    assert asked, "the gap request never reached the Designer's transcript"


def test_a_family_with_no_replannable_gap_is_never_replanned():
    """The round costs a Designer call plus a Developer call per set, so a
    family whose gaps a work set cannot close must not pay it. `content` is
    that family: its checks are structural or report-only, and no module
    assignment closes either."""
    config = HarnessRunConfig(agent_mode="multi")
    config.llm_factory = lambda: FakeChatModel()
    result = run_design_brief(load_brief("java_oop_brief.json"), config)

    content = [p for p in result["plans"] if p["stage"] == "content"]
    assert content and all(p["round"] == 0 for p in content)


def test_the_replan_actually_produces_the_missing_work():
    """End to end on the plain fixture, which leaves real `plan_coverage` gaps
    after its first round: the promised (objective, category) pairs that no
    item realised come back as new work sets, and their items are committed
    under round-tagged ids."""
    config = HarnessRunConfig(agent_mode="multi")
    config.llm_factory = lambda: FakeChatModel()
    result = run_design_brief(load_brief("java_oop_brief.json"), config)

    rounds = [p for p in result["plans"] if p["stage"] == "assessment"]
    assert [p["round"] for p in rounds] == [0, 1]
    assert "plan_coverage" in rounds[1]["answers"]

    items = result["addie_output"]["development"]["assessment_tools"]
    from_round_one = [i for i in items if str(i.get("plan_set", "")).endswith("R1")]
    assert from_round_one, "the replan planned work that never got written"


def test_the_round_is_bounded(monkeypatch):
    """A gap that survives a Designer re-plan and a fresh Developer call is one
    the model cannot close. Asking again is how a stage becomes a hang."""
    real = run_module._collect_violations

    def always(family, state, design_brief):
        found = real(family, state, design_brief)
        if family == "assessment_designer":
            return found + [_Gap("C2", lo_id="ILO-01")]
        return found

    monkeypatch.setattr(run_module, "_collect_violations", always)
    config = HarnessRunConfig(agent_mode="multi")
    config.llm_factory = lambda: FakeChatModel()
    result = run_design_brief(load_brief("java_oop_brief.json"), config)

    rounds = [p["round"] for p in result["plans"] if p["stage"] == "assessment"]
    assert max(rounds) <= replan.REPLAN_ROUNDS


def test_a_replan_is_not_a_retry():
    """`attempt` counts REGENS — a stage that came back empty and was run again
    from a fresh context.

    A replan is not that. It continues the Designer's own conversation with new
    work to plan, so it inherits the attempt along with the id, the label and
    the compaction record: everything that describes the CONVERSATION rather
    than the task travels with the message list. Numbered from the round
    instead, a perfectly healthy Designer counted as twice-run — which is a
    wrong number in the record whether or not anything draws it.
    """
    config = HarnessRunConfig(agent_mode="multi")
    config.llm_factory = lambda: FakeChatModel()
    result = run_design_brief(load_brief("java_oop_brief.json"), config)

    replanned = {p["stage"] for p in result["plans"] if p["round"] > 0}
    assert replanned, "this fixture must replan, or the test proves nothing"

    for context in result["contexts"]:
        if context["label"] in replanned:
            assert context["attempt"] == 1, (
                f"{context['agent']} is badged as a retry for having replanned")

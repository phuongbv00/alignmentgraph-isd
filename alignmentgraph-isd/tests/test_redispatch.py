"""A gap dispatches the same work again, with what is missing named.

The loop this closes. A family's work sets are derived from the design, its
Developers write them, and the checks then find an objective with no
assessment item. Without this the gap reaches nobody who can act on it: every
Developer loop has closed and the deterministic net cannot write
instructional content, so it is counted as residual and shipped.

The answer is a second DISPATCH. A set that is new runs because it is new
work; a set that already ran and still owns a gap runs again with the gap
spelled out, because a commit drops a repeat.
"""
from __future__ import annotations


from alignmentgraph_isd import HarnessRunConfig
from alignmentgraph_isd.core import runner as run_module
from alignmentgraph_isd.core.agentic import budget, redispatch
from alignmentgraph_isd.core.dev_plans import WorkSet

from conftest import FakeChatModel, load_brief, run_brief


class _Gap:
    """A stand-in violation. Mirrors `checks.Violation`'s surface INCLUDING
    `key` — the ledger and `_serialize` address a violation by it, so a double
    that lacks it stops standing in for one."""

    def __init__(self, vtype: str, **metadata):
        self.violation_type = vtype
        self.metadata = metadata
        self.message = f"{vtype} for {metadata.get('lo_id', '?')}"
        self.node_id = f"objective:{metadata.get('lo_id', '?')}"
        self.edge_type = ""
        self.severity = "error"
        self.repair_hint = ""
        self.target_designer = ""

    @property
    def key(self) -> str:
        return f"{self.violation_type}|{self.node_id}"


# ── what a re-dispatch is asked for ───────────────────────────────────────────────

def test_only_gaps_new_work_can_close_are_sent_back():
    gaps = [_Gap("C2", lo_id="ILO-01"), _Gap("item_completeness", item_id="AT-01"),
            _Gap("evaluation_quality", section="pilot_data_plan")]

    kept = redispatch.gaps_for("assessment", gaps)
    assert [g.violation_type for g in kept] == ["C2"], (
        "a malformed item and a thin pilot plan are not answered by planning "
        "more work — they are the artifact's own author's to fix")
    assert redispatch.gaps_for("content", gaps) == [], (
        "content owns no gap a new module assignment closes")


def test_only_a_set_that_owns_a_gap_runs_again():
    """Nothing re-runs a set with no gap of its own, so a round can only ask
    for work that is missing."""
    mine = WorkSet(set_id="AS-SET-01", ordinal=1,
                   pairs=(("ILO-01", "diagnostic"),), objectives=("ILO-01",))
    other = WorkSet(set_id="AS-SET-02", ordinal=2,
                    pairs=(("ILO-02", "summative"),), objectives=("ILO-02",))
    gaps = [_Gap("plan_coverage", lo_id="ILO-01", plan_category="diagnostic")]

    redo = redispatch.redo("assessment", gaps, [mine, other],
                       {"AS-SET-01", "AS-SET-02"}, 1)
    assert [ws.set_id for ws in redo] == ["AS-SET-01R1"]
    assert redo[0].payload["still_missing"] == ["plan_coverage for ILO-01"]


def test_a_set_the_state_has_never_seen_runs_because_it_is_new_work():
    """The Designer amended the blueprint during its own repair turns, so an
    set now exists that had no work set in round 0. It is dispatched
    without a `still_missing` note: nothing of it has been written."""
    new = WorkSet(set_id="AS-SET-04", ordinal=4,
                  pairs=(("ILO-09", "diagnostic"),), objectives=("ILO-09",))
    redo = redispatch.redo("assessment", [_Gap("C2", lo_id="ILO-01")], [new], set(), 1)

    assert [ws.set_id for ws in redo] == ["AS-SET-04R1"]
    assert "still_missing" not in redo[0].payload


def test_a_re_run_is_told_what_is_missing_or_it_produces_nothing():
    """A commit drops a repeat (`dev_plans.without_repeats`), so a set told
    only "write this again" writes what it already wrote and lands none of
    it. The note says so in every family the same way."""
    from alignmentgraph_isd.core import dev_plans

    text = dev_plans.render_assessment_set(WorkSet(
        set_id="AS-SET-01R1", ordinal=51, pairs=(("ILO-01", "diagnostic"),),
        payload={"still_missing": ["ILO-01 has no diagnostic item"]}))
    assert "ALREADY BEEN WRITTEN ONCE" in text
    assert "ILO-01 has no diagnostic item" in text


def test_round_sets_are_tagged_or_they_never_run():
    """Round 0's `AS-01` is committed and `committed_set_ids` reads the
    `plan_set` stamp, so a round-1 set numbered `AS-01` again is treated as
    already done. Without the tag the round runs and produces nothing."""
    tagged = redispatch.tag_round([WorkSet(set_id="AS-01"), WorkSet(set_id="AS-02")], 1)

    assert [ws.set_id for ws in tagged] == ["AS-01R1", "AS-02R1"]


def test_a_second_dispatch_costs_no_designer_call():
    """The grouping is derived from the design, so a second round has nothing
    to ask a Designer that its own repair turns did not. This module composes
    no prompt at all."""
    import inspect

    source = inspect.getsource(redispatch)
    assert "ToolLoop" not in source and "intro=" not in source


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
    return run_brief(load_brief("java_oop_brief.json"), config)


def test_a_gap_produces_a_second_planning_round_and_new_work(monkeypatch):
    result = _run_with_one_round_of_gaps(
        monkeypatch, [_Gap("C2", lo_id="ILO-01")])

    rounds = [p for p in result["plans"] if p["stage"] == "assessment"]
    assert len(rounds) == 2, f"expected a re-dispatch round, got {[p['round'] for p in rounds]}"
    second = rounds[1]
    assert second["round"] == 1
    assert "C2" in second["answers"], "the round records which gaps it answers"
    assert second["work_sets"], "a re-dispatch that plans no work is not a re-dispatch"
    assert all(ws["set_id"].endswith("R1") for ws in second["work_sets"])


def test_a_second_dispatch_opens_no_conversation_of_its_own(monkeypatch):
    """The round costs Developer calls and nothing else. The Designer is not
    asked again — its own repair turns already put the family's open issues in
    front of it, inside the one conversation it has."""
    result = _run_with_one_round_of_gaps(
        monkeypatch, [_Gap("C2", lo_id="ILO-01")])

    designer = [c for c in result["contexts"]
                if c["agent"] == "AssessmentDesignerAgent"]
    assert designer
    systems = {c["messages"][0]["content"] for c in designer}
    assert len(systems) == 1, "the Designer was given a second system prompt"
    assert all(":re-dispatch" not in str(c.get("phase", "")) for c in result["contexts"])
    redone = [c for c in result["contexts"] if str(c.get("phase", "")).endswith("R1")]
    assert redone, "the round ran no set at all"
    assert all("Developer" in c["agent"] for c in redone), (
        "a second dispatch is Developer calls and nothing else")


def test_a_family_with_no_replannable_gap_is_never_replanned():
    """The round costs a Designer call plus a Developer call per set, so a
    family whose gaps a work set cannot close must not pay it. `content` is
    that family: its checks are structural or report-only, and no module
    assignment closes either."""
    config = HarnessRunConfig(agent_mode="multi")
    config.llm_factory = lambda: FakeChatModel()
    result = run_brief(load_brief("java_oop_brief.json"), config)

    content = [p for p in result["plans"] if p["stage"] == "content"]
    assert content and all(p["round"] == 0 for p in content)


def test_the_replan_actually_produces_the_missing_work():
    """End to end on the plain fixture, which leaves real `plan_coverage` gaps
    after its first round: the promised (objective, category) pairs that no
    item realised come back as new work sets, and their items are committed
    under round-tagged ids."""
    config = HarnessRunConfig(agent_mode="multi")
    config.llm_factory = lambda: FakeChatModel()
    result = run_brief(load_brief("java_oop_brief.json"), config)

    rounds = [p for p in result["plans"] if p["stage"] == "assessment"]
    assert [p["round"] for p in rounds] == [0, 1]
    assert "plan_coverage" in rounds[1]["answers"]

    items = [one for t in result["addie_output"]["development"]["assessment_tools"]
             for one in (t.get("items") or [])]
    from_round_one = [i for i in items if str(i.get("plan_set", "")).endswith("R1")]
    assert from_round_one, "the re-dispatch planned work that never got written"


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
    result = run_brief(load_brief("java_oop_brief.json"), config)

    rounds = [p["round"] for p in result["plans"] if p["stage"] == "assessment"]
    assert max(rounds) <= budget.REDISPATCH_ROUNDS


def test_a_replan_is_not_a_retry():
    """`attempt` counts REGENS — a stage that came back empty and was run again
    from a fresh context.

    A re-dispatch is not that. It continues the Designer's own conversation with new
    work to plan, so it inherits the attempt along with the id, the label and
    the compaction record: everything that describes the CONVERSATION rather
    than the task travels with the message list. Numbered from the round
    instead, a perfectly healthy Designer counted as twice-run — which is a
    wrong number in the record whether or not anything draws it.
    """
    config = HarnessRunConfig(agent_mode="multi")
    config.llm_factory = lambda: FakeChatModel()
    result = run_brief(load_brief("java_oop_brief.json"), config)

    replanned = {p["stage"] for p in result["plans"] if p["round"] > 0}
    assert replanned, "this fixture must re-dispatch, or the test proves nothing"

    for context in result["contexts"]:
        if context["label"] in replanned:
            assert context["attempt"] == 1, (
                f"{context['agent']} is badged as a retry for having replanned")


def test_a_gap_with_no_objective_is_owned_by_the_set_that_wrote_it():
    """`REDISPATCHABLE` lists C3 for activities, but `_owns` matched only on
    objective ids from the gap's metadata — and an ESTABLISHER gap is about a
    reference that resolves to nothing, so it names no objective and was
    dropped. Measured on run 43c4ca5e: all 12 C3 gaps, every round.

    `plan_set` is stamped on the element at commit, so the set that wrote it
    is always knowable."""
    from alignmentgraph_isd.core import dev_plans
    from alignmentgraph_isd.core.agentic import redispatch
    from alignmentgraph_isd.core.checks import Violation

    gap = Violation(
        node_id="activity:TLA-0203", edge_type="", violation_type="C3", severity="error",
        message="activity:TLA-0203 has no resolvable aligned_objectives.",
        metadata={"node_id": "activity:TLA-0203", "item_id": "TLA-0203",
                  "plan_set": "AB-MOD-02"})
    mine = dev_plans.WorkSet(set_id="AB-MOD-02", objectives=("ILO-003",))
    other = dev_plans.WorkSet(set_id="AB-MOD-01", objectives=("ILO-002",))

    out = redispatch.redo("activities", [gap], [mine, other],
                          {"AB-MOD-02", "AB-MOD-01"}, 1)

    assert [ws.set_id for ws in out] == ["AB-MOD-02R1"], "only the set that wrote it re-runs"
    assert out[0].payload["still_missing"] == [gap.message], \
        "the re-run is told what is missing, in the check's own words"

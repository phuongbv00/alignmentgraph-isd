"""What a run found wrong, followed from first sighting to outcome.

Started from one question about the demo app: a violation labelled "Bloom
level consistent" appeared with no indication of WHY, and answering it meant
opening the trajectory and reading check events by hand. Pulling on that
exposed four separate problems — a violation that did not explain itself, one
that was remembered nowhere, counts that summed the same finding once per
round, and an "open" state that silently conflated four different reasons.
"""
from __future__ import annotations

from collections import Counter

import pytest

from alignmentgraph_isd import HarnessRunConfig
from alignmentgraph_isd.core import checks
from alignmentgraph_isd.core.alignment_graph import AlignmentGraph
from alignmentgraph_isd.core.memory import Finding, Memory

from conftest import FakeChatModel, load_brief, run_brief


def _run(agent_mode: str = "multi", **config):
    cfg = HarnessRunConfig(agent_mode=agent_mode, **config)
    cfg.llm_factory = lambda: FakeChatModel()
    return run_brief(load_brief("java_oop_brief.json"), cfg)


# ── identity ────────────────────────────────────────────────────────────────

def test_the_key_is_the_subject_not_the_evidence():
    """`item_ids` grows as Developers commit while the problem stands. A key
    including it would report the finding closed and a new one opened on every
    commit — which is exactly the mistake a naive hash of all metadata makes."""
    before = checks.Violation(
        node_id="objective:ILO-01", edge_type="", message="…",
        violation_type="bloom_mismatch_assessment",
        metadata={"lo_id": "ILO-01", "item_ids": ["AT-0101"]})
    after = checks.Violation(
        node_id="objective:ILO-01", edge_type="", message="… (reworded)",
        violation_type="bloom_mismatch_assessment",
        metadata={"lo_id": "ILO-01", "item_ids": ["AT-0101", "AT-0102"]})

    assert before.key == after.key


def test_two_findings_on_one_node_stay_two():
    """`actionability` and `evaluation_quality` each emit TWO violations on ONE
    node_id, told apart only by `metadata["section"]`. Without the
    discriminator they are one finding to anything that groups by identity —
    a latent bug the ledger would have inherited."""
    hollow = {"instructor_orientation": {"competency_checklist": [], "materials": []},
              "system_check": {"checklist": []}}
    found = checks.actionability_data("implementation_plan_0", hollow)

    assert len(found) == 2
    assert len({v.key for v in found}) == 2


def test_every_check_in_a_broken_design_is_distinguishable():
    """One key per real problem, over a graph built to provoke every check."""
    import sys
    from pathlib import Path

    sys.path.insert(0, str(Path(__file__).parent / "fixtures"))
    from broken_design import broken_graph

    graph = broken_graph()
    found: list = []
    for name in ("bloom_verbs", "measurability", "rubric_consistency", "plan_coverage",
                 "item_completeness", "evaluation_quality", "activity_engagement",
                 "orphan_content", "evidence_alignment", "actionability",
                 "relation_coverage", "bloom_mismatches"):
        found += getattr(checks, name)(graph)

    collisions = {k for k, n in Counter(v.key for v in found).items() if n > 1}
    # P6 collides on purpose: its establisher says "this material matched no
    # media selection" and the coverage sweep says "it has no P6 coverage" —
    # one fact stated twice by two producers, which the ledger keeps as one
    # finding carrying both wordings.
    assert collisions == {"P6|material:MAT-0101"}, collisions


# ── the ledger ──────────────────────────────────────────────────────────────

def test_a_run_remembers_what_it_found_and_what_became_of_it():
    result = _run()
    findings = result["violations"]
    assert findings, "the run kept no finding"

    for finding in findings:
        assert finding["key"] and finding["messages"]
        assert finding["outcome"] in (
            "open", "repaired_by_harness", "repaired_by_agent")
        # An open finding always says WHY, or the ledger cannot tell a harness
        # limit from a model one.
        if finding["outcome"] == "open":
            assert finding["open_reason"], finding


def test_one_finding_reported_two_ways_keeps_both_wordings():
    memory = Memory(graph=AlignmentGraph())
    for message in ("material matched no media selection", "no P6 coverage"):
        memory.observe_violations(
            [checks.Violation(node_id="material:MAT-01", edge_type="",
                              message=message, violation_type="P6")],
            round=1, phase="content", family="content_designer")

    assert len(memory.findings) == 1
    assert len(memory.findings[0].messages) == 2
    assert memory.findings[0].message == "material matched no media selection"


def test_the_ledger_survives_without_a_graph_to_audit():
    """The prose arm skips the graph audit entirely (`run.py` guards it on
    `graph_mode`), so `metadata.audit.violations` — the only place a residual
    body used to reach — is empty there by construction. The ledger sits on
    memory rather than on the graph, which is what makes the two arms
    comparable on this at all.

    Asserted on the MECHANISM, not on the fixture: this arm runs only the six
    within-artifact checks and the canned payloads are clean against all of
    them, so its run genuinely finds nothing. A test that demanded findings
    here would be asserting that the fixture is broken."""
    from alignmentgraph_isd.core.prose_store import ProseStore

    memory = Memory(store=ProseStore())
    memory.observe_violations(
        [checks.Violation(node_id="AT-01", edge_type="", message="…",
                          violation_type="item_completeness",
                          metadata={"item_id": "AT-01"})],
        round=1, phase="assessment", family="assessment_designer")

    assert [f.as_dict() for f in memory.findings]
    assert memory.as_dict()["findings"]

    # And the prose arm really does run its checks, so the hook is on a live
    # path rather than a dead one.
    result = _run(context_mode="prose")
    rounds = [a for a in result["trajectory_deep"]["actions"] if a["action"] == "check"]
    assert rounds and all(a["context"]["violation_count"] == 0 for a in rounds)


# ── counting ────────────────────────────────────────────────────────────────

def test_the_review_counts_findings_not_sightings():
    """A check round re-finds everything the previous one could not repair, so
    summing `by_type` across rounds counts one violation once per round it
    survived. A measured run reported 28 issues for a set of 7."""
    result = _run()
    summed: Counter = Counter()
    for action in result["trajectory_deep"]["actions"]:
        if action["action"] == "check":
            summed.update(action["context"].get("by_type") or {})

    review = {f["criterion"]: f["issues_found"]
              for f in result["addie_output"]["development"]["expert_review"]["findings"]}
    ledger = Counter(f["type"] for f in result["violations"])

    assert review == dict(ledger), "the review disagrees with the ledger"
    assert sum(review.values()) < sum(summed.values()), (
        "this fixture must re-find something, or the test proves nothing")


# ── convergence ─────────────────────────────────────────────────────────────

def test_a_pass_that_repairs_nothing_stops_and_says_so():
    """Checks are pure functions of state and nothing else writes state between
    the repair and the next look, so "no repair event fired" PROVES the next
    collect is identical. Stopping there is free; re-running it is not."""
    result = _run()
    actions = result["trajectory_deep"]["actions"]

    converged = [a for a in actions if a["action"] == "converge"]
    assert converged, "this fixture must leave something unfixable"
    for action in converged:
        assert action["context"]["unfixable"] > 0
        assert action["context"]["violation_types"]

    reconcile_rounds = [a for a in actions if a["action"] == "check"
                        and a["context"].get("phase") == "reconcile"]
    from alignmentgraph_isd.core.repairs import OWNED_BY_FAMILY
    assert len(reconcile_rounds) <= len(OWNED_BY_FAMILY), (
        "reconcile ran more rounds than it has families — the budget is global "
        "again, so a family clean in round 1 is re-checked because another "
        "family had work")


def test_converged_and_out_of_budget_are_different_answers():
    """The distinction the whole ledger exists for. "The model could not fix
    this" is a finding; "we did not give it another turn" is a harness
    parameter we chose. Reporting them merged is a wrong claim."""
    memory = Memory(graph=AlignmentGraph())
    violation = checks.Violation(node_id="objective:ILO-01", edge_type="",
                                 message="…", violation_type="C2")
    keys = memory.observe_violations([violation], round=1, family="assessment_designer")

    memory.mark_open_reason(keys, reason="budget")
    memory.settle(keys)
    assert memory.findings[0].open_reason == "budget"
    assert memory.findings[0].converged_at_round == 0


def test_a_budget_stop_is_recorded_rather_than_silent():
    """`ToolLoop` used to return in SILENCE when violations were outstanding
    and the repair budget was spent — it said COMMITTED and left — while the
    branch one line below recorded a give-up for running out of part-submits.
    So a run could not tell "the model could not fix this" from "we did not
    give it another turn"."""
    result = _run(agent_mode="multi")
    budget = [e for e in result["trajectory"]["events"]
              if e["action"] == "budget_exhausted"]
    assert budget, "this fixture must exhaust a repair budget"
    for event in budget:
        assert "violation" in event["context"]["input_summary"]

    reasons = {f["open_reason"] for f in result["violations"] if f["outcome"] == "open"}
    assert {"budget", "converged"} <= reasons, (
        "the two must be distinguishable in the ledger, not just in the events")


def test_a_budget_stop_is_not_overwritten_by_a_later_convergence():
    """Reconciliation runs after every stage and converges on anything it
    cannot fix — which is trivially true for a type it is not allowed to touch.
    Letting that overwrite an earlier budget stop would relabel "we cut it
    short" as "the model could not do it", which is the one claim this ledger
    exists to keep apart."""
    memory = Memory(graph=AlignmentGraph())
    violation = checks.Violation(node_id="objective:ILO-01", edge_type="",
                                 message="…", violation_type="C2")
    keys = memory.observe_violations([violation], round=1, family="assessment_designer")

    memory.mark_open_reason(keys, reason="budget")
    memory.mark_open_reason(keys, reason="converged", round=9)

    finding = memory.findings[0]
    assert finding.open_reason == "budget", "the harness's own limit was hidden"
    # The convergence still happened and is still recorded — it is just not the
    # headline reason.
    assert finding.converged_at_round == 9


@pytest.mark.parametrize("agent_mode", ["multi", "single"])
def test_the_ledger_is_not_folded_into_the_trajectory(agent_mode):
    """The judge reads the trajectory and the benchmark compares it across
    arms. A per-finding history there would change what is measured.

    Now that the ledger is also PUBLISHED as it fills, the snapshot must not
    leak into the recorded streams either: it goes out through the consumer
    directly, never through ``TrajectoryLogger``'s recorded actions."""
    result = _run(agent_mode)
    for key in ("trajectory", "trajectory_deep"):
        assert "violations" not in result[key]
    actions = result["trajectory_deep"].get("actions") or []
    assert not any(a.get("action") == "violations_snapshot" for a in actions)


# ── published while the run is still going ──────────────────────────────────

def _snapshots(agent_mode: str = "multi", **config):
    """Run the harness with a watcher and keep every ledger it published."""
    seen: list[list[dict]] = []

    def on_event(kind, payload):
        if kind == "violations_snapshot":
            seen.append(payload["findings"])

    cfg = HarnessRunConfig(agent_mode=agent_mode, **config)
    cfg.llm_factory = lambda: FakeChatModel()
    result = run_brief(load_brief("java_oop_brief.json"), cfg, on_event=on_event)
    return seen, result


@pytest.mark.parametrize("agent_mode", ["multi", "single"])
def test_the_ledger_is_published_while_the_run_is_still_going(agent_mode):
    """The Violations tab used to stay empty for the whole 4-7 minutes and fill
    in at the end. The ledger is state, like the graph and the transcripts, so
    it is published as it is written — a viewer watches findings appear and
    move from open to repaired instead of seeing the result of that.

    The last thing published is what the run returns: `settle` runs inside the
    harness and its frame goes out on the reconcile phase's exit, so a watcher
    that saw every frame ends on the SETTLED ledger and needs no re-fetch.
    """
    seen, result = _snapshots(agent_mode)

    assert len(seen) > 1, "a ledger published once is the behaviour this replaced"
    counts = [len(s) for s in seen]
    assert counts == sorted(counts), (
        "a finding is never removed, only re-outcomed, so the ledger only grows")
    assert seen[-1] == result["violations"], "the last frame is the settled ledger"


def test_a_ledger_that_did_not_change_is_not_republished():
    """What the revision counter buys over a time throttle.

    The producer is hooked to the event stream, which wakes on nearly every
    trajectory event — far more often than a finding is written. Gating on
    `Memory.findings_rev` means a frame is only ever sent for a ledger that
    actually moved, so no two consecutive frames can be identical."""
    seen, _ = _snapshots()
    assert all(a != b for a, b in zip(seen, seen[1:]))


def test_nobody_watching_never_serializes_the_ledger(monkeypatch):
    """The benchmark must not pay to serve a viewer that is not there.

    Emitting is a no-op without a consumer, but BUILDING the payload is not —
    the same rule `emit_context` follows. Here it is stronger than a gate: with
    no consumer the wrapper is never constructed, so `as_dict` is not called
    once. What the run itself returns is built from the findings directly."""
    calls = Counter()
    original = Finding.as_dict
    monkeypatch.setattr(
        Finding, "as_dict",
        lambda self: (calls.update(["as_dict"]), original(self))[1])

    cfg = HarnessRunConfig()
    cfg.llm_factory = lambda: FakeChatModel()
    result = run_brief(load_brief("java_oop_brief.json"), cfg, on_event=None)

    assert result["violations"], "the fixture must actually find something"
    assert calls["as_dict"] == len(result["violations"]), (
        "only the run's own result serialized the ledger; nothing published it")

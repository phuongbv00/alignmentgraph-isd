"""What a run remembers: transcripts per agent, the alignment state, the plans.

Before ``core/memory.py`` these were three unrelated things with three
lifetimes. Transcripts existed only if someone was watching — ``emit_context``
published them to the optional ``on_event`` consumer, so the CLI and the
benchmark ran whole ladders whose contexts existed nowhere afterwards. Plans
existed for the length of one function call: ``_run_fanout`` computed the work
sets, built prompts from them, summarised them into a trajectory event and
dropped them, so nothing could afterwards answer "which Developer was asked for
what". Only the graph was kept.
"""
from __future__ import annotations

import pytest

from alignmentgraph_isd import HarnessRunConfig
from alignmentgraph_isd.core.alignment_graph import AlignmentGraph
from alignmentgraph_isd.core.memory import Memory, Plan, Transcript, new_agent_run_id
from alignmentgraph_isd.core.prose_store import ProseStore

from conftest import FakeChatModel, load_brief, run_brief


def _transcript(agent: str, label: str, run_id: str = "", messages=None) -> Transcript:
    return Transcript(
        id=run_id or new_agent_run_id(), agent=agent, phase=label,
        label=label, attempt=1, messages=messages or [], tools=[])


def test_a_republished_context_replaces_the_one_before_it():
    """A loop publishes after every turn while a run is watched, so the same
    conversation arrives many times, each longer than the last. Appending would
    make `result["contexts"]` a pile of prefixes of itself."""
    memory = Memory(graph=AlignmentGraph())
    run = new_agent_run_id()
    memory.remember_context(_transcript("A", "outcomes", run, messages=[1]))
    memory.remember_context(_transcript("A", "outcomes", run, messages=[1, 2, 3]))
    memory.remember_context(_transcript("A", "outcomes", messages=[9]))

    assert len(memory.transcripts) == 2, "a second agent run is a second context"
    assert memory.transcripts[0].messages == [1, 2, 3], "the latest snapshot wins"


def test_the_identity_belongs_to_the_conversation_not_to_its_description():
    """Learned the hard way. The first version hashed
    `(agent, phase, label, attempt)` — and the re-dispatch round, which continues the
    Designer's OWN message list under a new step name, hashed to a different
    id. The tab then showed one conversation as two rows, the second containing
    the first: the split-block problem the in-loop repair was built to remove.

    No content-derived key can know that two labels are one conversation. An id
    the conversation carries can, which is why it is minted where the
    conversation begins and inherited by whoever continues it."""
    assert new_agent_run_id() != new_agent_run_id()
    assert len(new_agent_run_id()) == 12


def test_exactly_one_substrate_is_live():
    """Which substrate a run has IS the ``context_mode`` axis. A memory
    holding both would make a prose run able to read the graph, and one
    holding neither would make the axis unreadable."""
    assert Memory(graph=AlignmentGraph()).graph is not None
    assert Memory(store=ProseStore()).graph is None
    with pytest.raises(ValueError):
        Memory(graph=AlignmentGraph(), store=ProseStore())
    with pytest.raises(ValueError):
        Memory()


def test_of_wraps_a_bare_substrate_and_passes_a_memory_through():
    graph = AlignmentGraph()
    assert Memory.of(graph).state is graph
    store = ProseStore()
    assert Memory.of(store).state is store
    memory = Memory(graph=graph)
    assert Memory.of(memory) is memory


def test_a_family_is_planned_in_rounds_and_all_of_them_are_kept():
    """A family is planned more than once: the Designer plans, its Developers
    write, the checks find gaps, and the gaps go back to the DESIGNER — whose
    answer is a new plan scoped to them. Keeping only the latest would lose
    what the first plan missed, which is the interesting half."""
    memory = Memory(graph=AlignmentGraph())
    first = Plan(stage="assessment", family="assessment_designer", source="llm")
    second = Plan(stage="assessment", family="assessment_designer", source="llm",
                  round=1, answers=("C2", "plan_coverage"))
    memory.remember_plan(first)
    memory.remember_plan(second)

    assert memory.plans == (first, second), "round by round, first to last"


def test_transcripts_are_kept_per_agent_in_order():
    memory = Memory(graph=AlignmentGraph())
    for agent, label in (("A", "outcomes"), ("B", "assessment"), ("A", "content")):
        memory.remember_context(_transcript(agent, label))

    assert memory.agents == ("A", "B"), "first appearance first"
    assert [t.label for t in memory.transcripts if t.agent == "A"] == ["outcomes", "content"]
    assert len(memory.transcripts) == 3


# ── through a real run ───────────────────────────────────────────────────────

@pytest.mark.parametrize("agent_mode", ["multi", "single"])
def test_a_run_remembers_every_context_with_nobody_watching(agent_mode):
    """No ``on_event`` consumer. Before memory this returned nothing at all:
    the only record of what an agent was shown went to a live viewer, so a
    benchmark run kept none of it."""
    config = HarnessRunConfig(agent_mode=agent_mode)
    config.llm_factory = lambda: FakeChatModel()
    result = run_brief(load_brief("java_oop_brief.json"), config)

    contexts = result["contexts"]
    assert contexts, "the run kept no transcript"
    for context in contexts:
        assert context["agent"] and context["messages"]
        assert context["messages"][0]["role"] == "system"

    agents = {c["agent"] for c in contexts}
    if agent_mode == "single":
        assert len(agents) == 1, "one agent, one context boundary — that is the axis"
    else:
        assert len(agents) > 1


def test_a_run_remembers_what_each_designer_asked_its_developers_for():
    config = HarnessRunConfig(agent_mode="multi")
    config.llm_factory = lambda: FakeChatModel()
    result = run_brief(load_brief("java_oop_brief.json"), config)

    plans = result["plans"]
    assert plans, "the run kept no plan"
    for plan in plans:
        assert plan["stage"] and plan["family"]
        assert plan["source"] == "deterministic", (
            "no family asks the model how to divide its own work")
        assert plan["work_sets"], f"{plan['stage']} planned no work at all"
        # Round 0 is the first division; a later round is the re-dispatch of
        # the sets that still owe work (core/agentic/redispatch.py).
        assert plan["round"] >= 0
        assert bool(plan["answers"]) == (plan["round"] > 0), (
            "a re-dispatch round names the gaps it answers; round 0 answers none")
        # The sets name the work, not just their count: this is what makes
        # "which Developer was asked for what" answerable after the run.
        assert all(ws.get("set_id") for ws in plan["work_sets"])


def test_the_transcripts_are_not_folded_into_the_trajectory():
    """The judge reads the trajectory and the benchmark compares it across
    arms. Transcripts alone would multiply its size by the number of turns and
    change what is measured to serve a viewer."""
    config = HarnessRunConfig()
    config.llm_factory = lambda: FakeChatModel()
    result = run_brief(load_brief("minimal_brief.json"), config)

    for key in ("trajectory", "trajectory_deep"):
        assert "contexts" not in result[key]
        assert "plans" not in result[key]
        assert not any(e["action"] == "context_snapshot"
                       for e in result[key].get("events", []) or
                       result[key].get("actions", []))


def test_concurrent_republishes_of_one_context_leave_exactly_one():
    """A parallel fan-out's workers publish their contexts from their own
    threads; the upsert by id must hold under that, or the row list grows a
    duplicate per race."""
    import threading

    memory = Memory(graph=AlignmentGraph())
    run_id = new_agent_run_id()
    threads = [threading.Thread(target=lambda: [
        memory.remember_context(_transcript("Dev", "content:MU-01", run_id, [{"n": k}]))
        for k in range(100)]) for _ in range(6)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert len(memory.transcripts) == 1
    assert memory.transcripts[0].messages == [{"n": 99}]

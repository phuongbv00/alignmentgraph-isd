"""An agent's identity is one conversation, not several.

2026-09-03. Repairs that needed new text used to be written by a separate
model call the harness composed itself: a persona-free system turn, no tools
bound, two messages long — published under the OWNING AGENT'S NAME. The Context
tab showed it as what it was, a second block for the same agent with a system
prompt it had never otherwise been given, and that is what made the problem
visible.

It was not a display bug. The ``agent_mode`` axis IS the context boundary:
``multi`` starts each stage fresh, ``single`` carries one context across all
six. A repair path that opened its own conversation put a third boundary
inside the treatment, and it did so on only one family of violations, so the
amount of it a run received depended on how badly that run had gone.

Repairs that need writing now go back to the owning agent as a user turn in
the loop it is already running (``ToolLoop._own_violations`` ->
``_repair_request``), so the request, the answer and the artifact are three
consecutive turns of one transcript. These tests hold that shut.

ONE prose call survives, and it is not what this file forbids: the compaction
hook (``core/agentic/compaction.py``, 2026-09-08), which folds the turns a trim
dropped into the note. What makes it a different thing is exactly what was
wrong with the repairs — it runs under ``WORKFLOW_ORCHESTRATOR`` rather than
under the agent whose window filled, and it publishes no context at all, so no
agent is given a second boundary and none of the tests below has anything to
see. That claim needs enforcing rather than asserting, and none of the three
guards here would catch a regression: a two-message conversation slips past
``test_one_conversation_is_one_context``'s four-message filter, its single
system constant would satisfy the first test, and the toolless check only looks
at contexts that were published. So the boundary is held in
``tests/test_compaction.py`` instead, by a guard that ``call_prose`` has
exactly one caller in ``src/`` and that it is the hook.
"""
from __future__ import annotations

import pytest

from alignmentgraph_isd import HarnessRunConfig

from conftest import FakeChatModel, load_brief, run_brief


def _contexts(agent_mode: str, context_mode: str) -> list[dict]:
    """The contexts the run KEPT, not the stream of snapshots it published.

    A loop republishes after every turn while a run is watched, so the event
    stream carries the same conversation many times over — deliberately, so a
    viewer sees it grow. `result["contexts"]` is that stream resolved: one
    entry per agent run, holding its last snapshot."""
    config = HarnessRunConfig(agent_mode=agent_mode, context_mode=context_mode)
    config.llm_factory = lambda: FakeChatModel()
    return run_brief(load_brief("java_oop_brief.json"), config)["contexts"]


@pytest.mark.parametrize("agent_mode,context_mode", [
    ("multi", "graph"), ("multi", "prose"), ("single", "graph"), ("single", "prose"),
])
def test_an_agent_is_never_given_a_second_system_prompt(agent_mode, context_mode):
    by_agent: dict[str, set[str]] = {}
    for ctx in _contexts(agent_mode, context_mode):
        system = (ctx.get("parts") or {}).get("system") or ""
        by_agent.setdefault(ctx["agent"], set()).add(system)

    assert by_agent, "no contexts were published at all"
    multiple = {agent: len(systems) for agent, systems in by_agent.items() if len(systems) > 1}
    assert not multiple, (
        "an agent was run under more than one system prompt — every context "
        f"published in its name must share one: {multiple}")


@pytest.mark.parametrize("agent_mode,context_mode", [
    ("multi", "graph"), ("multi", "prose"), ("single", "graph"), ("single", "prose"),
])
def test_every_published_context_belongs_to_a_tool_loop(agent_mode, context_mode):
    """A context with no tools bound is a model call made outside any agent's
    loop. There is no such call left: the only thing that talks to the model is
    an agent inside its own loop, with its own tools."""
    toolless = [
        f"{c['agent']}/{c.get('label')}"
        for c in _contexts(agent_mode, context_mode)
        if not (c.get("specs") or c.get("schema_tokens"))
    ]
    assert not toolless, f"model calls made outside a tool loop: {toolless}"


@pytest.mark.parametrize("agent_mode,context_mode", [
    ("multi", "graph"), ("multi", "prose"), ("single", "graph"), ("single", "prose"),
])
def test_one_conversation_is_one_context(agent_mode, context_mode):
    """The other half of "one agent, one system prompt", and the half that got
    away.

    A context used to be identified by hashing what it was ABOUT
    (agent, phase, label, attempt). The replan round continues the Designer's
    own message list under a new step name — so it hashed to a different id,
    and the Context tab showed that conversation TWICE, the second row
    containing the first. Same system prompt in both, so the existing guard
    passed it: the split had moved from the prompt to the label.

    A context is now identified by the AGENT RUN it belongs to, minted where
    the conversation starts and inherited by whoever continues it. Two
    published contexts must therefore never share a transcript.
    """
    contexts = _contexts(agent_mode, context_mode)
    assert contexts

    ids = [context["id"] for context in contexts]
    assert len(set(ids)) == len(ids), "two rows published under one agent run"

    # No context's transcript is a prefix of another's: that is what one
    # conversation split across two rows looks like from the outside.
    def opening(context) -> tuple:
        return tuple(str(m.get("content", ""))[:120] for m in context["messages"][:4])

    openings = [opening(context) for context in contexts if len(context["messages"]) >= 4]
    assert len(set(openings)) == len(openings), (
        "two contexts start with the same four messages — one conversation, two rows")

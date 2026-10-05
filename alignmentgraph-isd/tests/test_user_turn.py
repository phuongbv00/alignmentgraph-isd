"""A request always carries a user turn.

``trim_history`` may drop the stage turn, and before any compaction there is no
note, so a request can reach the endpoint as the system turn plus assistant and
tool messages only — which the serving chat template refuses (HTTP 400 "No user
query found in messages"; 31 such refusals on run t1 20261005_205508, most on
the constrained pass). The guard sits in the transport, so both arms get it.
"""
from __future__ import annotations

from alignmentgraph_isd import HarnessRunConfig
from alignmentgraph_isd.core.agentic.client import AgenticLLM
from alignmentgraph_isd.core.agentic.transcript import CONTINUE_TURN, ensure_user_turn
from alignmentgraph_isd.core.trajectory import TrajectoryLogger


class _Recording:
    """Answers with text and remembers every request it was sent."""

    def __init__(self) -> None:
        self.sent: list[list[dict]] = []

    def bind(self, **_kwargs):
        return self

    def bind_tools(self, _specs, **_kwargs):
        return self

    def invoke(self, messages):
        from langchain_core.messages import AIMessage
        self.sent.append([dict(m) if isinstance(m, dict) else m for m in messages])
        return AIMessage(content='{"ok": "yes"}')


_NO_USER = [{"role": "system", "content": "S"},
            {"role": "assistant", "content": "", "tool_calls": [
                {"id": "c1", "type": "function",
                 "function": {"name": "read_node", "arguments": "{}"}}]},
            {"role": "tool", "tool_call_id": "c1", "name": "read_node", "content": "x"}]


def test_a_request_without_a_user_turn_gets_one_after_the_system_turn():
    messages = [dict(m) for m in _NO_USER]
    assert ensure_user_turn(messages)
    assert messages[1] == {"role": "user", "content": CONTINUE_TURN}
    assert not ensure_user_turn(messages), "one is enough"


def test_both_call_paths_send_one_and_record_it_in_the_callers_transcript():
    model = _Recording()
    trajectory = TrajectoryLogger()
    llm = AgenticLLM(HarnessRunConfig(llm_factory=lambda: model), trajectory, "Agent")

    live = [dict(m) for m in _NO_USER]
    llm.call_tools(live, [])
    assert any(m.get("role") == "user" for m in model.sent[-1])
    assert any(m.get("role") == "user" for m in live), "the published transcript is the one sent"

    copy = [dict(m) for m in _NO_USER]
    llm.call_structured(copy, {"type": "object"}, "submit_x")
    assert any(m.get("role") == "user" for m in model.sent[-1])
    assert sum(e["action"] == "user_turn_restored"
               for e in trajectory.to_dict()["events"]) == 2

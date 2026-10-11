"""A refused submit as long as the completion cap still leaves room to answer it.

The prompt budget is the window minus the completion cap, and one submit may be
as long as that cap, so the turn after a refused full-length submit could never
be sent: ``trim_history`` keeps the call and its answer, and the call is the
bulk of the history. MEASURED (run t1 20261011_163858): a Developer's 13 items
with rubrics refused, four HTTP 400s, the set given up. The fix is in the shared
transport, so both arms get it.
"""
from __future__ import annotations

from langchain_core.messages import AIMessage

from alignmentgraph_isd.core.agentic.transcript import (
    ELIDE_CALL_CHARS, message_size, trim_history)


def _history(call):
    return [{"role": "system", "content": "s"},
            {"role": "user", "content": "u" * 3000},
            call,
            {"role": "tool", "tool_call_id": "c1", "name": "submit_x", "content": "REJECTED"}]


def test_an_oversized_call_is_cut_to_fit_and_stays_paired_with_its_answer():
    for call in (
        {"role": "assistant", "content": "", "tool_calls": [{
            "id": "c1", "type": "function",
            "function": {"name": "submit_x", "arguments": '{"x": "' + "a" * 30000 + '"}'}}]},
        AIMessage(content="", tool_calls=[{"id": "c1", "name": "submit_x",
                                           "args": {"x": "a" * 30000}}]),
    ):
        kept, _dropped = trim_history(_history(call), 8000)
        assert sum(message_size(m) for m in kept) <= 8000
        cut = next(m for m in kept if (m.get("tool_calls") if isinstance(m, dict)
                                       else getattr(m, "tool_calls", None)))
        calls = cut["tool_calls"] if isinstance(cut, dict) else cut.tool_calls
        assert calls[0]["id"] == "c1"
        assert "cut to fit the context window" in str(calls)
        assert kept[-1]["tool_call_id"] == "c1"


def test_a_call_that_fits_is_never_cut():
    small = {"role": "assistant", "content": "", "tool_calls": [{
        "id": "c1", "type": "function",
        "function": {"name": "submit_x", "arguments": '{"x": "' + "a" * (ELIDE_CALL_CHARS // 2) + '"}'}}]}
    kept, _dropped = trim_history(_history(small), 8000)
    assert kept[2] is small

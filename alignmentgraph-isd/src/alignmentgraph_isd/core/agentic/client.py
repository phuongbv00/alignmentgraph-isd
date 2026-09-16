"""The model caller, and the shape one model turn comes back in.

Transport is NATIVE tool calling: tools are bound with ``bind_tools`` and each
turn arrives as ``.tool_calls``. The ladder serves this — vLLM with
``--enable-auto-tool-choice --tool-call-parser qwen3_coder`` (see
docs/benchmark_guides.md §3.2) — so the serving-side parser enforces the
argument shape before the text reaches us.

Tool calls are the ONLY way an AGENT reaches the model. The invariant is about
the agent, not about this module: ``call_prose`` is the HARNESS's own call,
made by the compaction hook under ``WORKFLOW_ORCHESTRATOR``, binding no tools
and publishing no context. The two paths share ``_begin``/``_account``, which
is what keeps the hook's tokens on the cost table.
"""
from __future__ import annotations

import time

from ..llm_io import (
    _extract_token_usage,
    _is_truncation_error,
    finish_reason,
    was_truncated,
)
from ..ratelimit import gate_for
from .transcript import prompt_chars, ratio_for
from .turn import ToolTurn


class AgenticLLM:
    """Model caller for the agentic arm: native tool calling, truncation
    salvage, trajectory accounting.

    Tool calls are the ONLY way an AGENT reaches the model. The invariant is
    about the agent, not about this class: the class also carries
    ``call_prose`` — the HARNESS's own call, made by the compaction hook under
    ``WORKFLOW_ORCHESTRATOR``, binding no tools and publishing no context. An
    agent never chooses to compact, so compaction is not an action in its
    protocol and must not be dressed as one; the accounting both paths share
    (``_begin``/``_account``) is what keeps the hook's price on the books.
    Repairs never call the model at all.

    ``call_prose`` must never acquire ``response_format``: a summary written
    under ``response_format=json_object`` comes back as JSON, is rejected as
    non-prose, and costs a full completion every time the window fills —
    measured on run e81b8108, three calls and 11.8k completion tokens for
    nothing kept.
    """

    def __init__(self, config, trajectory, identity: str) -> None:
        self.config = config
        self.trajectory = trajectory
        self.identity = identity

    def call_tools(self, messages: list[dict], tool_specs: list[dict]) -> ToolTurn:
        """One act turn with tools bound. Returns the model's tool call, or an
        empty :class:`ToolTurn` carrying whatever text it produced instead.

        No JSON retry here, deliberately: with native calling a non-call reply
        is not a parse failure to correct, it is the model choosing to talk.
        The loop answers that with a protocol nudge (and, when the text happens
        to BE a valid artifact, accepts it) — which is one turn either way, but
        without a wasted extra request. Truncation salvage stays: the 8192
        completion cap is what truncates a large ``submit``, and that is the
        same failure whatever the transport."""
        if self.config.llm_factory is None:
            self.trajectory.log_llm_call(0, 0)
            self.trajectory.log_recovery_event(
                self.identity, "llm_error", "", "llm_factory not set — cannot call LLM")
            return ToolTurn()
        raw_llm = self.config.llm_factory()
        try:
            # tool_choice="auto" is sent EXPLICITLY. LangChain's bind_tools
            # omits it, and vLLM's --enable-auto-tool-choice is what engages
            # the tool-call parser: without the field the server can hand the
            # call back as raw markup in `content` instead of parsing it into
            # `tool_calls`. Traced by diffing the harness's outgoing payload
            # against a probe that scored 100% well-formed in all four
            # transport x turn-shape cells — tool_choice was the only field
            # that differed.
            bound = raw_llm.bind_tools(tool_specs, tool_choice="auto")
        except TypeError:
            # A backend whose bind_tools does not take tool_choice.
            bound = raw_llm.bind_tools(tool_specs)
        except Exception as exc:  # noqa: BLE001 - a backend without tool support
            self.trajectory.log_recovery_event(
                self.identity, "tool_binding_unavailable", str(exc)[:120], "")
            return ToolTurn(binding_failed=True)
        try:
            return self._invoke_tools(bound, messages)
        except Exception as exc:
            if _is_truncation_error(exc):
                self.trajectory.log_recovery_event(
                    self.identity, "salvage_truncated", str(exc)[:80], "")
            self.trajectory.log_llm_call(0, 0)
            self.trajectory.log_recovery_event(self.identity, "llm_error", "", str(exc))
            return ToolTurn()

    def call_prose(self, messages: list[dict]) -> str:
        """One model call with NO tools bound and NO ``response_format``.

        Not an agent's turn: the ONLY caller is the compaction hook
        (``core/agentic/compaction.py``), which runs under
        ``WORKFLOW_ORCHESTRATOR`` and whose conversation is never published as
        any agent's context — ``tests/test_compaction.py`` enforces the
        one-caller rule. See the class docstring for why ``response_format``
        must never return on this path.
        """
        if self.config.llm_factory is None:
            self.trajectory.log_llm_call(0, 0)
            self.trajectory.log_recovery_event(
                self.identity, "llm_error", "", "llm_factory not set — cannot call LLM")
            return ""
        try:
            raw_llm = self.config.llm_factory()
            started = self._begin(messages)
            with gate_for(self.config).hold():
                result = raw_llm.invoke(messages)
        except Exception as exc:  # noqa: BLE001 - a summary is never load-bearing
            self.trajectory.log_llm_call(0, 0)
            self.trajectory.log_recovery_event(self.identity, "llm_error", "", str(exc))
            return ""
        content, _calls, _cut, _reasoning = self._account(result, messages, started)
        return content

    def _begin(self, messages: list[dict]) -> float:
        """Announce the call and start its clock.

        ``llm_started``/``llm_finished`` bracket every model call the package
        makes and are the only signal during the ~50 s one takes, so a new call
        path has to open with this or a watcher goes quiet for its duration."""
        self.trajectory.emit("llm_started", {
            "agent": self.identity,
            "prompt_chars": prompt_chars(messages),
            "message_count": len(messages),
            "retries_left": 0,
        })
        return time.time()

    def _account(self, result, messages: list[dict],
                 started: float) -> tuple[str, list, bool, str]:
        """Everything a model call must leave behind: its flattened content, its
        tool calls, whether it was cut and its reasoning channel — plus
        ``llm_finished``, the chars-per-token measurement, the ``llm_call``
        action, the token totals and the thinking-only reply.

        ONE copy, so that a second way into the model (the compaction hook)
        cannot quietly leave the cost table."""
        content = getattr(result, "content", "") or ""
        if not isinstance(content, str):
            # Some backends return content as a list of blocks; the loop only
            # ever uses it as fallback text, so flatten rather than branch.
            content = " ".join(
                str(block.get("text", "")) if isinstance(block, dict) else str(block)
                for block in content)
        calls = list(getattr(result, "tool_calls", None) or [])
        prompt_tokens, completion_tokens = _extract_token_usage(result)
        duration_ms = (time.time() - started) * 1000
        self.trajectory.emit("llm_finished", {
            "agent": self.identity, "duration_ms": duration_ms,
            "response_chars": len(content), "tool_calls": len(calls),
            "prompt_tokens": prompt_tokens, "completion_tokens": completion_tokens,
        })
        stopped = finish_reason(result)
        # The tokenizer's own verdict on a prompt whose size we know: this is
        # what calibrates the transcript budget, and it arrives free with every
        # response.
        ratio_for(self.config).observe(prompt_chars(messages), prompt_tokens)
        self.trajectory.log_action(
            "llm_call", agent=self.identity, duration_ms=duration_ms,
            prompt_chars=prompt_chars(messages), response_chars=len(content),
            prompt_tokens=prompt_tokens, completion_tokens=completion_tokens,
            tool_calls=len(calls), finish_reason=stopped, attempt_of_retries_left=0)
        self.trajectory.log_llm_call(prompt_tokens, completion_tokens)
        extra = getattr(result, "additional_kwargs", None) or {}
        reasoning = str(extra.get("reasoning_content") or "") if isinstance(extra, dict) else ""
        if reasoning and not content.strip():
            # MEASURED (run 24343e4d): 12 of 78 calls, 47-405 billed completion
            # tokens each, every one charged a full stage turn as
            # `invalid_action`. Recorded HERE, at the one path EVERY model call
            # goes through — both arms and the compaction hook — so the rate is comparable across the axis and is
            # attributable to the serving posture rather than to the model. The
            # fix is `disable_thinking` on the factory; this is what makes its
            # absence visible when it is not set.
            self.trajectory.log_recovery_event(
                self.identity, "thinking_only_reply",
                f"{completion_tokens} completion tokens, no content, no tool call",
                reasoning[:200])
        return content, calls, was_truncated(result), reasoning

    def _invoke_tools(self, llm, messages: list[dict]) -> ToolTurn:
        started = self._begin(messages)
        with gate_for(self.config).hold():
            result = llm.invoke(messages)
        content, calls, cut, reasoning = self._account(result, messages, started)
        if not calls:
            return ToolTurn(text=content, message=result, truncated=cut,
                            reasoning=reasoning)
        # Raw here; the loop coerces against the SPEC it bound (only it knows
        # which tool this name refers to and what types that tool declares).
        # One ToolTurn per call, all sharing the model's message: the first
        # carries the rest as `calls`, and `truncated` rides on every one
        # because it is the LAST call of a cut batch that is incomplete and
        # only the caller knows which that is.
        turns = [ToolTurn(name=str(call.get("name") or "").strip(), args=call.get("args"),
                          call_id=str(call.get("id") or ""), text=content if i == 0 else "",
                          message=result, sibling=i > 0, truncated=cut)
                 for i, call in enumerate(calls)]
        turns[0].calls = tuple(turns[1:])
        return turns[0]

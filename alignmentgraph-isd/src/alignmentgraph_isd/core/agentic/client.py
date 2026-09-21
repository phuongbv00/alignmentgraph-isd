"""The model caller, and the shape one model turn comes back in.

Transport is NATIVE tool calling: tools are bound with ``bind_tools`` and each
turn arrives as ``.tool_calls``. The ladder serves this — vLLM with
``--enable-auto-tool-choice --tool-call-parser qwen3_coder`` (see
docs/guides/benchmark_guides.md §3.2) — so the serving-side parser enforces the
argument shape before the text reaches us.

Tool calls are the ONLY way an AGENT reaches the model. The invariant is about
the agent, not about this module: ``call_prose`` is the HARNESS's own call,
made by the compaction hook under ``ORCHESTRATOR``, binding no tools
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


#: What every agent turn asks for; see ``AgenticLLM._bind``.
TOOL_CHOICE_DEFAULT = "required"


def _rejects_tool_choice(exc: Exception) -> bool:
    """Whether a failed request was refused FOR its ``tool_choice`` value —
    the one failure that is answered by downgrading rather than reported.
    A truncation is never that, whatever its status code."""
    if _is_truncation_error(exc):
        return False
    msg = str(exc).lower()
    if "tool_choice" in msg or "tool choice" in msg:
        return True
    status = getattr(exc, "status_code", None)
    return status in (400, 422) and "tool" in msg


class AgenticLLM:
    """Model caller for the agentic arm: native tool calling, truncation
    salvage, trajectory accounting.

    Tool calls are the ONLY way an AGENT reaches the model. The invariant is
    about the agent, not about this class: the class also carries
    ``call_prose`` — the HARNESS's own call, made by the compaction hook under
    ``ORCHESTRATOR``, binding no tools and publishing no context. An
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
        choice = self._tool_choice()
        bound = self._bind(raw_llm, tool_specs, choice)
        if bound is None:
            return ToolTurn(binding_failed=True)
        try:
            return self._invoke_tools(bound, messages)
        except Exception as exc:  # noqa: BLE001 - every backend error is recorded below
            if choice == TOOL_CHOICE_DEFAULT and _rejects_tool_choice(exc):
                # The backend will not force a call. Learned ONCE per run:
                # the memo is on the config every agent shares, so no later
                # turn of either arm pays a refused request to find out
                # again. The refused request still left, so it is billed.
                self.trajectory.log_llm_call(0, 0)
                self.trajectory.log_recovery_event(
                    self.identity, "tool_choice_downgraded", str(exc)[:120], "auto")
                self._remember_tool_choice("auto")
                bound = self._bind(raw_llm, tool_specs, "auto")
                if bound is None:
                    return ToolTurn(binding_failed=True)
                try:
                    return self._invoke_tools(bound, messages)
                except Exception as again:  # noqa: BLE001
                    exc = again
            if _is_truncation_error(exc):
                self.trajectory.log_recovery_event(
                    self.identity, "salvage_truncated", str(exc)[:80], "")
            self.trajectory.log_llm_call(0, 0)
            self.trajectory.log_recovery_event(self.identity, "llm_error", "", str(exc))
            return ToolTurn()

    def _tool_choice(self) -> str:
        """The ``tool_choice`` this run sends: the memo if one exists, else
        ``"required"``. ``""`` means the keyword is not passed at all."""
        memo = getattr(self.config, "_tool_choice", None)
        if memo is None:
            memo = getattr(self, "_tool_choice_memo", None)
        return TOOL_CHOICE_DEFAULT if memo is None else memo

    def _remember_tool_choice(self, value: str) -> None:
        try:
            self.config._tool_choice = value
        except (AttributeError, ValueError):  # pragma: no cover - a bare stub config
            self._tool_choice_memo = value

    def _bind(self, raw_llm, tool_specs: list[dict], choice: str):
        """Bind the tools, or None when the backend has no tool support.

        ``tool_choice`` is sent EXPLICITLY. LangChain's bind_tools omits it,
        and vLLM's --enable-auto-tool-choice is what engages the tool-call
        parser: without the field the server can hand the call back as raw
        markup in `content` instead of parsing it into `tool_calls` (traced by
        diffing the outgoing payload against a probe that scored 100%
        well-formed in all four transport x turn-shape cells — tool_choice was
        the only field that differed). It is ``"required"`` rather than
        ``"auto"`` because a reply that calls nothing is a turn that produces
        nothing: measured on run 14a6b4c7, four such turns wrote 9-15k
        characters of prose each, three of them to the completion cap, ~12k
        completion tokens for four protocol nudges. A backend that refuses
        ``"required"`` is downgraded to ``"auto"`` once per run
        (``call_tools``); the nudge stays as the backstop behind both."""
        try:
            if choice == "":
                return raw_llm.bind_tools(tool_specs)
            return raw_llm.bind_tools(tool_specs, tool_choice=choice)
        except TypeError:
            # A backend whose bind_tools does not take tool_choice.
            self._remember_tool_choice("")
            return raw_llm.bind_tools(tool_specs)
        except Exception as exc:  # noqa: BLE001 - a backend without tool support
            self.trajectory.log_recovery_event(
                self.identity, "tool_binding_unavailable", str(exc)[:120], "")
            return None

    def call_prose(self, messages: list[dict], *, max_tokens: int = 0) -> str:
        """One model call with NO tools bound and NO ``response_format``.

        Not an agent's turn: the ONLY caller is the compaction hook
        (``core/agentic/compaction.py``), which runs under
        ``ORCHESTRATOR`` and whose conversation is never published as
        any agent's context — ``tests/test_compaction.py`` enforces the
        one-caller rule. See the class docstring for why ``response_format``
        must never return on this path.

        ``max_tokens`` caps what this call may SPEND. The caller knows how much
        of the answer it can use — the fold truncates to
        ``MAX_SUMMARY_CHARS`` — and without a cap the whole serving reserve is
        available for text that is then thrown away (see
        ``compaction.SUMMARY_MAX_TOKENS`` for the measurement). Bound rather
        than requested, because the 1,200-character limit is already in the
        prompt and a 9B model wrote 24,000 characters anyway. A backend that
        refuses the binding is called unbound rather than not at all: a summary
        is never load-bearing.
        """
        if self.config.llm_factory is None:
            self.trajectory.log_llm_call(0, 0)
            self.trajectory.log_recovery_event(
                self.identity, "llm_error", "", "llm_factory not set — cannot call LLM")
            return ""
        try:
            raw_llm = self.config.llm_factory()
            if max_tokens > 0:
                try:
                    raw_llm = raw_llm.bind(max_tokens=max_tokens)
                except Exception:  # noqa: BLE001 - a backend that cannot be bound
                    pass
            started = self._begin(messages)
            with gate_for(self.config).hold():
                result = raw_llm.invoke(messages)
        except Exception as exc:  # noqa: BLE001 - a summary is never load-bearing
            self.trajectory.log_llm_call(0, 0)
            self.trajectory.log_recovery_event(self.identity, "llm_error", "", str(exc))
            return ""
        content, _calls, _cut = self._account(result, messages, started)
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
                 started: float) -> tuple[str, list, bool]:
        """Everything a model call must leave behind: its flattened content, its
        tool calls and whether it was cut — plus ``llm_finished``, the
        chars-per-token measurement, the ``llm_call`` action, the token totals
        and the thinking-only reply.

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
            # The reply spent its completion budget reasoning and arrived with
            # nothing to act on: no text, no tool call, and `finish_reason`
            # "stop", so truncation salvage cannot see it either. The loop
            # charges it as the empty turn it is; this names it, so the rate is
            # readable rather than hidden inside `invalid_action`. Measured on
            # run 24343e4d: 12 of 78 calls, 47-405 billed completion tokens
            # each. Recorded HERE, at the one path EVERY model call goes
            # through — both arms and the compaction hook — so the rate is
            # comparable across the axis. The reasoning ITSELF is not recorded
            # here: it rides the reply into the transcript (see
            # `transcript.serialize_messages`), and this carries only a prefix
            # so the event is readable on its own.
            self.trajectory.log_recovery_event(
                self.identity, "thinking_only_reply",
                f"{completion_tokens} completion tokens, no content, no tool call",
                reasoning[:200])
        return content, calls, was_truncated(result)

    def _invoke_tools(self, llm, messages: list[dict]) -> ToolTurn:
        started = self._begin(messages)
        with gate_for(self.config).hold():
            result = llm.invoke(messages)
        content, calls, cut = self._account(result, messages, started)
        if not calls:
            return ToolTurn(text=content, message=result, truncated=cut)
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

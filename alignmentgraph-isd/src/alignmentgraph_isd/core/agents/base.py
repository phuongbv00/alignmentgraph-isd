from __future__ import annotations
import json
import re
from abc import ABC, abstractmethod
from ...config import HarnessRunConfig
from ..graph import AlignmentGraph
from ..schema import DesignBrief
from ..trajectory import TrajectoryLogger


def _is_truncation_error(exc: Exception) -> bool:
    """A JSON-mode response cut off at the model's max output length raises
    (rather than returning partial text). Detect that so the caller can retry
    unbound and salvage what was produced."""
    msg = str(exc).lower()
    return (
        "length limit" in msg
        or "max_tokens" in msg
        or ("finish_reason" in msg and "length" in msg)
        or ("could not parse" in msg and "length" in msg)
    )


def _extract_token_usage(result) -> tuple[int, int]:
    """(prompt_tokens, completion_tokens) from a LangChain chat result, robust
    across the two shapes providers actually use:

    - ``usage_metadata`` — a **dict** ``{"input_tokens", "output_tokens", ...}``
      (LangChain's normalized form; the previous code read it with ``getattr``,
      which silently returned 0 for every real backend since a dict has no such
      attribute — that is why token_usage stayed 0 despite real LLM calls).
    - ``response_metadata["token_usage"]`` — the raw provider block, OpenAI-style
      ``{"prompt_tokens", "completion_tokens"}`` (dict or object).
    """
    def _get(obj, key, default=0):
        if obj is None:
            return default
        if isinstance(obj, dict):
            value = obj.get(key, default)
        else:
            value = getattr(obj, key, default)
        return value if isinstance(value, int) else default

    usage = getattr(result, "usage_metadata", None)
    if usage:
        prompt = _get(usage, "input_tokens")
        completion = _get(usage, "output_tokens")
        if prompt or completion:
            return prompt, completion

    response_metadata = getattr(result, "response_metadata", None) or {}
    token_usage = response_metadata.get("token_usage") if isinstance(response_metadata, dict) else None
    if token_usage:
        return _get(token_usage, "prompt_tokens"), _get(token_usage, "completion_tokens")
    return 0, 0


def _fix_json_control_chars(s: str) -> str:
    """Fix literal control characters (newline, tab, etc.) inside JSON string values.

    Only modifies characters that appear inside quoted strings.
    Structural whitespace outside strings is left untouched.
    """
    result = []
    in_string = False
    escape_next = False
    for ch in s:
        if escape_next:
            result.append(ch)
            escape_next = False
        elif in_string and ch == "\\":
            result.append(ch)
            escape_next = True
        elif ch == '"':
            result.append(ch)
            in_string = not in_string
        elif in_string and ch == "\n":
            result.append("\\n")
        elif in_string and ch == "\r":
            result.append("\\r")
        elif in_string and ch == "\t":
            result.append("\\t")
        else:
            result.append(ch)
    return "".join(result)


def _close_unbalanced_json(s: str) -> str:
    """Append missing closing JSON delimiters when a response stops too early."""
    stack: list[str] = []
    in_string = False
    escape_next = False

    for ch in s:
        if escape_next:
            escape_next = False
            continue
        if in_string and ch == "\\":
            escape_next = True
            continue
        if ch == '"':
            in_string = not in_string
            continue
        if in_string:
            continue
        if ch == "{":
            stack.append("}")
        elif ch == "[":
            stack.append("]")
        elif ch in "}]":
            if stack and stack[-1] == ch:
                stack.pop()
            else:
                return s

    if in_string or not stack:
        return s
    return s + "".join(reversed(stack))


def _json_error_hint(raw: str) -> str:
    """A short human hint about why ``raw`` is not parseable JSON, for a retry
    prompt. Empty string if it actually parses or is empty."""
    if not raw:
        return "the response was empty"
    cleaned = re.sub(r"```(?:json)?[ \t]*\n?", "", raw)
    cleaned = re.sub(r"\n?```[ \t]*$", "", cleaned, flags=re.MULTILINE).strip()
    start = cleaned.find("{")
    if start == -1:
        return "no JSON object was found"
    try:
        json.loads(cleaned[start:])
        return ""
    except json.JSONDecodeError as e:
        near = cleaned[start:][max(0, e.pos - 25): e.pos + 15].replace("\n", " ")
        return f"{e.msg} near ...{near}..."


def parse_json_response(raw: str, *, warn: bool = True) -> dict:
    """Robustly parse a JSON dict from an LLM response.

    Handles: markdown fences, leading/trailing prose, literal control
    characters inside string values, and other common LLM JSON issues.
    Logs a warning (does not raise) if all attempts fail.
    """
    if not raw:
        return {}

    # Strip markdown code fences
    cleaned = re.sub(r"```(?:json)?[ \t]*\n?", "", raw)
    cleaned = re.sub(r"\n?```[ \t]*$", "", cleaned, flags=re.MULTILINE).strip()

    last_err: json.JSONDecodeError | None = None

    # Try 1: direct parse (clean JSON)
    try:
        result = json.loads(cleaned)
        if isinstance(result, dict):
            return result
    except json.JSONDecodeError as e:
        last_err = e

    # Try 1b: decode the first complete JSON object and ignore trailing garbage
    # ("Extra data" — the model emitted valid JSON then kept talking, or closed
    # the root object early). Also skips any leading prose before the first '{'.
    brace = cleaned.find("{")
    if brace != -1:
        try:
            obj, _end = json.JSONDecoder().raw_decode(cleaned[brace:])
            if isinstance(obj, dict):
                return obj
        except json.JSONDecodeError as e:
            last_err = e

    # Try 2: extract outermost {} block
    match = re.search(r"\{.*\}", cleaned, re.DOTALL)
    if match:
        candidate = match.group(0)

        try:
            result = json.loads(candidate)
            if isinstance(result, dict):
                return result
        except json.JSONDecodeError as e:
            last_err = e

        # Try 3: fix literal control chars inside string values (stateful)
        try:
            result = json.loads(_fix_json_control_chars(candidate))
            if isinstance(result, dict):
                return result
        except json.JSONDecodeError as e:
            last_err = e

        # Try 4: remove trailing commas (another common LLM issue)
        try:
            no_trailing = re.sub(r",(\s*[}\]])", r"\1", candidate)
            result = json.loads(_fix_json_control_chars(no_trailing))
            if isinstance(result, dict):
                return result
        except json.JSONDecodeError as e:
            last_err = e

        # Try 5: append missing closing braces/brackets for truncated JSON.
        try:
            balanced = _close_unbalanced_json(no_trailing)
            result = json.loads(_fix_json_control_chars(balanced))
            if isinstance(result, dict):
                return result
        except json.JSONDecodeError as e:
            last_err = e

    if not warn:
        return {}

    import warnings
    err_ctx = ""
    if last_err is not None:
        pos = last_err.pos
        snip = cleaned[max(0, pos - 40):pos + 40] if cleaned else ""
        err_ctx = f" | Error at pos {pos}: {last_err.msg!r} near {snip!r}"
    warnings.warn(
        f"parse_json_response: all attempts failed (response len={len(raw)})"
        f"{err_ctx}"
    )
    return {}


# Standing ISD quality guidance appended to every specialist's brief. This is the
# only non-brief content the old ContextPlanner/context_pack carried; it is static,
# so it lives here as a constant rather than being rebuilt per run and JSON-dumped
# (where it sat at the end of a brief-duplicating blob and got truncation-clipped).
_DESIGN_GUIDANCE = """\
Standing design guidance:
- Every objective must be measured by at least one assessment item; preserve \
objective<->assessment<->activity alignment with explicit objective IDs.
- Cover all 33 ADDIE sub-items explicitly.
- Use measurable Bloom verbs; avoid vague verbs such as know, learn, understand, comprehend.
- Include pilot execution evidence, data collection, monitoring, and revision loops."""


def _format_design_brief(design_brief: DesignBrief) -> str:
    """Serialize a DesignBrief (+ standing design guidance) as an LLM user message."""
    lines: list[str] = []
    if design_brief.title:
        lines.append(f"Title: {design_brief.title}")
    context = {k: v for k, v in design_brief.context.model_dump().items() if v not in ("", None, [], {})}
    if context:
        lines.append("Context:")
        for k, v in context.items():
            lines.append(f"  {k}: {v if not isinstance(v, (dict, list)) else json.dumps(v, ensure_ascii=False)}")
    if design_brief.learning_goals:
        lines.append("Learning goals:")
        for g in design_brief.learning_goals:
            lines.append(f"  - {g}")
    constraints = {k: v for k, v in design_brief.constraints.model_dump().items() if v not in ("", None, [], {})}
    if constraints:
        lines.append("Constraints:")
        for k, v in constraints.items():
            lines.append(f"  {k}: {v if not isinstance(v, (dict, list)) else json.dumps(v, ensure_ascii=False)}")
    for key in ("difficulty", "domain", "duration", "target_audience"):
        val = getattr(design_brief, key, "")
        if val:
            lines.append(f"{key.replace('_', ' ').title()}: {val}")
    if design_brief.user_message:
        lines.append(f"User request (this session): {design_brief.user_message}")
    if not lines:
        lines.append(json.dumps(design_brief.model_dump(), ensure_ascii=False))
    return "\n".join(lines) + "\n\n" + _DESIGN_GUIDANCE


# Default execution-strategy hint per ADDIE task for on-demand retrieval. The
# specialist's decision call can override; broad analysis/creation tasks lean
# parallel, narrowly-scoped design tasks lean single.
RETRIEVAL_STRATEGY_HINTS = {
    "needs_context": "parallel",
    "objective_design": "single",
    "assessment_design": "single",
    "activity_material": "parallel",
    "implementation_plan": "single",
    "evaluation_revision": "single",
    "full_design": "parallel",
}

_RETRIEVAL_DECISION_SYSTEM = """You are the retrieval coordinator inside an instructional-design agent.
Decide whether this task needs EXTERNAL domain material beyond the context already available,
and if so, which retrieval agents to use and how to run them.

Retrieve only when domain-specific conventions, rubrics, templates or examples would
materially improve the output. Otherwise skip — retrieval costs time and tokens.

Respond with JSON only:
{"retrieve": false}
or
{"retrieve": true,
 "agents": ["<retrieval agent name>", ...],
 "strategy": "single" | "sequential" | "parallel",
 "queries": {"<agent name>": "<what to fetch, specific>"}}"""


class BaseISDAgent(ABC):
    # Verifier violation types this specialist is responsible for. Each specialist
    # self-checks and repairs its own artifact at the end of its turn (a quality
    # tool it owns), so no separate global verify phase is needed. Overridden per
    # subclass; empty means "no self-check".
    OWNED_VIOLATION_TYPES: frozenset[str] = frozenset()

    def __init__(self, config: HarnessRunConfig, graph: AlignmentGraph, trajectory: TrajectoryLogger) -> None:
        self.config = config
        self.graph = graph
        self.trajectory = trajectory

    @abstractmethod
    def run(self, design_brief: DesignBrief) -> None:
        ...

    @property
    def _graph_coordination(self) -> bool:
        """Whether this run has graph coordination active (traversal-scoped
        context + provenance-relation establishment). Decomposition into
        element nodes and id/type-match establishment (R3,R5,R6,R9,R12, and
        R4's id half) stay unconditional at every ablation rung — they are
        post-hoc bookkeeping on a specialist's own output and need no
        traversal. Only the CONTEXT-BUILDING style and PROVENANCE-relation
        establishment (R1,R2,R7,R8,R10,R11,R13) branch on this flag — that
        branch is what makes the wo_graph vs full ablation contrast real."""
        return bool(self.config.ablation.enable_alignment_graph)

    # Verifier violation types this specialist owns. A workflow's QC node reads
    # this to decide which violations the agent should self-repair. Quality
    # control is driven by the workflow (see core/nodes.py::NodeFactory.qc_node),
    # not by the agent itself — so the agent stays a pure generation module.
    def repair(self, violations: list) -> list:  # noqa: D401 - overridden by specialists
        """Default no-op repair; specialists override to fix owned violations."""
        return violations

    def _graph_context(self, node_types: list[str], max_chars: int = 600) -> str:
        """Pull relevant prior nodes from G_t for injection into this agent's prompt.

        This is graph-context retrieval (core, not RAG): each agent reads what
        earlier agents already deposited in the AlignmentGraph before generating
        its own section.
        Returns empty string when the graph has no relevant content yet.

        Deprecated in favour of ``_element_context``/``_traversal_context``,
        which scope the prompt to the specific element/section nodes a relation
        actually needs instead of every node of a whole type. Kept for any
        specialist that has not been migrated yet.
        """
        return self.graph.get_node_context(node_types, max_chars_per_node=max_chars)

    def _element_context(self, nodes: list[dict], max_chars: int = 600) -> str:
        """Format specific element/section nodes for prompt injection.

        Unlike ``_graph_context`` (which dumps every node of a type), the
        caller passes exactly the nodes a relation calls for — e.g.
        ``self._element_context(self.graph.element_nodes(NodeType.OBJECTIVE))``
        for "every learning objective", or the result of ``graph.traverse(...)``
        for a relation-scoped neighborhood.
        """
        import json
        lines: list[str] = []
        for node in nodes:
            data_str = json.dumps(node.get("data", {}), ensure_ascii=False)
            if len(data_str) > max_chars:
                data_str = data_str[:max_chars] + "…"
            lines.append(f"[{str(node.get('type', '')).upper()}:{node.get('id', '')}]\n{data_str}")
        return "\n\n".join(lines)

    def _traversal_context(
        self,
        start_ids: list[str],
        rel_path: list[str | None],
        *,
        direction: str = "out",
        max_chars: int = 600,
    ) -> str:
        """Relation-scoped context: follow ``rel_path`` from each of
        ``start_ids`` and format the nodes reached. The multi-hop replacement
        for ``_graph_context``'s whole-type blob dump."""
        seen: set[str] = set()
        nodes: list[dict] = []
        for start_id in start_ids:
            for node in self.graph.traverse(start_id, rel_path, direction=direction):
                if node["id"] not in seen:
                    seen.add(node["id"])
                    nodes.append(node)
        return self._element_context(nodes, max_chars=max_chars)

    def _decompose_elements(
        self,
        node_type: str,
        items: object,
        *,
        id_field: str = "id",
    ) -> list[str]:
        """Turn a list of dicts in a just-generated section into first-class
        element nodes (a cheap non-LLM parse — no extra LLM call). Each item
        must carry ``id_field``; items missing it are skipped (the completeness
        tier catches a section that is malformed enough to have no usable ids).
        """
        node_ids: list[str] = []
        if not isinstance(items, list):
            return node_ids
        for item in items:
            if not isinstance(item, dict):
                continue
            raw_id = item.get(id_field)
            if not raw_id:
                continue
            node_ids.append(self.graph.add_element_node(node_type, str(raw_id), dict(item)))
        return node_ids

    def _decompose_auto_id(
        self,
        node_type: str,
        items: object,
        *,
        id_prefix: str,
        text_key: str = "description",
    ) -> list[str]:
        """Decompose a list into element nodes with a positionally-assigned id
        (``{id_prefix}-01``, ``-02``, ...), for output fields the ADDIE schema
        specifies as plain string lists (gaps, topics, modules, action items) —
        keeps the generation schema, and so the judge-visible output shape,
        unchanged, while still giving these items first-class graph nodes for
        provenance edges. A bare string item is wrapped as ``{text_key: item}``;
        a dict item is stored as-is (with the assigned id added).
        """
        node_ids: list[str] = []
        if not isinstance(items, list):
            return node_ids
        for index, item in enumerate(items, start=1):
            element_id = f"{id_prefix}-{index:02d}"
            data = dict(item) if isinstance(item, dict) else {text_key: item}
            data.setdefault("id", element_id)
            node_ids.append(self.graph.add_element_node(node_type, element_id, data))
        return node_ids

    # ── On-demand agentic retrieval (RAG as a tool the specialist decides to use) ──

    def _with_retrieval(self, design_brief: DesignBrief, task_name: str, user_content: str) -> str:
        """Prepend on-demand domain material to the prompt when the agent asks for it."""
        material = self._maybe_retrieve(design_brief, task_name, user_content)
        if material:
            return f"{material}\n\n{user_content}"
        return user_content

    def _maybe_retrieve(self, design_brief: DesignBrief, task_name: str, prior_context: str = "") -> str:
        """Let this specialist decide whether/how to retrieve external domain material.

        Gated hard on ``enable_rag`` + a non-empty registry: on the benchmark path
        this returns immediately with zero LLM calls. When enabled, one small
        decision call chooses the retrieval agents and execution strategy
        (single / sequential / parallel — hinted per ADDIE task, decided by the
        agent), then the retrieval sandbox executes the plan.
        """
        from ..rag.planner import RetrievalPlanner

        planner = RetrievalPlanner(self.config)
        if not planner.enabled():
            return ""
        menu = planner.build_menu(design_brief, task_name)
        if not menu:
            return ""

        agent_name = type(self).__name__
        hint = RETRIEVAL_STRATEGY_HINTS.get(task_name, "single")
        decision_messages = [
            {"role": "system", "content": _RETRIEVAL_DECISION_SYSTEM},
            {"role": "user", "content": (
                f"Task: {task_name}\n"
                f"Design brief: {design_brief.title} | domain: {design_brief.domain} | "
                f"goals: {'; '.join(design_brief.learning_goals[:5])}\n"
                f"Context already available (chars): {len(prior_context)}\n"
                f"Available retrieval agents:\n{json.dumps(menu, ensure_ascii=False, indent=1)}\n"
                f"Suggested strategy for this task type: {hint}"
            )},
        ]
        decision = parse_json_response(self._call_llm(decision_messages, max_retries=0), warn=False)
        if not isinstance(decision, dict) or not decision:
            self.trajectory.log_retrieval_event(agent_name, task_name, "decision_error")
            return ""
        if not decision.get("retrieve"):
            self.trajectory.log_retrieval_event(agent_name, task_name, "skip")
            return ""

        menu_names = {entry["name"] for entry in menu}
        plan = {
            "agents": [a for a in (decision.get("agents") or []) if a in menu_names] or list(menu_names)[:1],
            "strategy": decision.get("strategy") or hint,
            "queries": decision.get("queries") or {},
        }
        results, events = planner.execute_plan(
            design_brief, task_name, plan, log_llm_call=self.trajectory.log_llm_call,
        )
        snippets = sum(len(r.get("content", [])) for r in results)
        self.trajectory.log_retrieval_event(
            agent_name, task_name, "retrieve",
            strategy=plan["strategy"], retrieval_agents=plan["agents"],
            executions=events, snippets=snippets,
        )
        if not results:
            return ""

        lines = ["=== DOMAIN MATERIAL (retrieved on demand) ==="]
        for result in results:
            label = result.get("subagent") or result.get("source", "corpus")
            for snippet in result.get("content", []):
                lines.append(f"[{label}] {snippet}")
            citations = result.get("citations") or []
            if citations:
                lines.append(f"[{label}] citations: {', '.join(citations)}")
        return "\n".join(lines)

    def _log_repair(
        self,
        node_id: str,
        *,
        violation_type: str = "",
        repaired_fields: list[str] | None = None,
    ) -> None:
        """Record that this specialist regenerated ``node_id`` to fix a violation.

        Repair is in-place regeneration + edge re-establishment (the graph dedups
        re-established edges); there is no downstream cascade — the static ADDIE
        order means later artifacts are generated after this one, not before it.
        """
        self.trajectory.log_repair_event(
            agent=type(self).__name__,
            violation_type=violation_type,
            node_id=node_id,
            repaired_fields=repaired_fields or [],
        )

    def _call_llm(self, messages: list[dict], max_retries: int = 2) -> str:
        """Call LLM with automatic retry on empty/invalid response.

        max_retries=N means: try once normally, then up to N correction turns if
        the response is empty or produces no parseable JSON. Generation calls use
        the default; repair calls that have deterministic fallbacks pass 0.
        """
        if self.config.llm_factory is None:
            self.trajectory.log_llm_call(0, 0)
            self.trajectory.log_step(type(self).__name__, "llm_error", "", "llm_factory not set — cannot call LLM")
            return ""
        raw_llm = self.config.llm_factory()
        json_llm = raw_llm
        try:
            json_llm = raw_llm.bind(response_format={"type": "json_object"})
        except Exception:
            pass
        try:
            return self._invoke_with_retry(json_llm, messages, max_retries)
        except Exception as exc:
            # A truncated response under JSON mode is RAISED by ChatOpenAI rather
            # than returned, so we would lose a section entirely on a small model
            # with a hard output cap (e.g. a 2B endpoint capping completion at
            # 4096, on which the large evaluation JSON overflows). Retry once with
            # the UNBOUND model: it hands back the partial text, which
            # parse_json_response salvages via _close_unbalanced_json — a
            # mostly-complete section instead of nothing.
            if _is_truncation_error(exc):
                try:
                    content = self._invoke_with_retry(raw_llm, messages, 0)
                    self.trajectory.log_step(
                        type(self).__name__, "salvage_truncated", str(exc)[:80], content[:100],
                    )
                    if content:
                        return content
                except Exception:
                    pass
            self.trajectory.log_llm_call(0, 0)
            self.trajectory.log_step(type(self).__name__, "llm_error", "", str(exc))
            return ""

    def _invoke_with_retry(self, llm, messages: list[dict], max_retries: int) -> str:
        """Invoke the LLM, retrying once with a correction message if output is empty."""
        result = llm.invoke(messages)
        content = result.content if hasattr(result, "content") else str(result)
        prompt_tokens, completion_tokens = _extract_token_usage(result)
        self.trajectory.log_llm_call(prompt_tokens, completion_tokens)
        if max_retries > 0 and not parse_json_response(content, warn=False):
            # Output was not valid JSON — send a targeted correction turn quoting
            # the exact parse error so the model can fix that specific spot.
            hint = _json_error_hint(content)
            self.trajectory.log_step(type(self).__name__, "retry", hint or "empty/invalid JSON", content[:100])
            correction_messages = messages + [
                {"role": "assistant", "content": content},
                {"role": "user", "content": (
                    "Your previous response was not valid JSON"
                    + (f" ({hint})" if hint else "")
                    + ". Return the COMPLETE corrected object as a SINGLE valid JSON value: "
                    "every '{' '[' must be closed, no trailing commas, no text or extra "
                    "objects before or after it, no markdown fences."
                )},
            ]
            return self._invoke_with_retry(llm, correction_messages, max_retries - 1)
        return content

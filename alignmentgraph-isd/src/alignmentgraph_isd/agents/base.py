from __future__ import annotations
import json
import re
from abc import ABC, abstractmethod
from ..config import HarnessRunConfig
from ..graph import AlignmentGraph, NodeType
from ..schema import DesignBrief
from ..trajectory import TrajectoryLogger


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


def _format_design_brief(design_brief: DesignBrief) -> str:
    """Serialize a DesignBrief into a clean string suitable as an LLM user message."""
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
    return "\n".join(lines)


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
    def __init__(self, config: HarnessRunConfig, graph: AlignmentGraph, trajectory: TrajectoryLogger) -> None:
        self.config = config
        self.graph = graph
        self.trajectory = trajectory

    @abstractmethod
    def run(self, design_brief: DesignBrief, context_pack: dict) -> None:
        ...

    def _graph_context(self, node_types: list[str], max_chars: int = 600) -> str:
        """Pull relevant prior nodes from G_t for injection into this agent's prompt.

        This is graph-context retrieval (core, not RAG): each agent reads what
        earlier agents already deposited in the AlignmentGraph before generating
        its own section.
        Returns empty string when the graph has no relevant content yet.
        """
        return self.graph.get_node_context(node_types, max_chars_per_node=max_chars)

    def _context_pack_text(self, context_pack: dict, max_chars: int = 1600) -> str:
        if not context_pack:
            return ""
        text = json.dumps(context_pack, ensure_ascii=False, indent=2)
        if len(text) > max_chars:
            text = text[:max_chars] + "…"
        return text

    # ── On-demand agentic retrieval (RAG as a tool the specialist decides to use) ──

    def _with_retrieval(self, design_brief: DesignBrief, task_name: str, user_content: str) -> str:
        """Prepend on-demand domain material to the prompt when the agent asks for it."""
        material = self._maybe_retrieve(design_brief, task_name, user_content)
        if material:
            return f"{material}\n\n{user_content}"
        return user_content

    def _maybe_retrieve(self, design_brief: DesignBrief, task_name: str, prior_context: str = "") -> str:
        """Let this specialist decide whether/how to retrieve external domain material.

        Gated hard on ``use_rag`` + a non-empty registry: on the benchmark path
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

    def _add_element_edge(
        self,
        edge_type: str,
        source_id: str,
        lo_id: str,
        *,
        rationale: str = "",
        verified: bool = True,
    ) -> None:
        """Mirror a section-level alignment edge onto the objective element node.

        Element nodes (``objective:LO-01``) are first-class, so alignment edges
        point at the specific objective, not only the aggregate ``objective_0``.
        No-op if the element node does not exist (e.g. before objective design).
        """
        element_id = f"{NodeType.OBJECTIVE}{self.graph.ELEMENT_SEP}{lo_id}"
        if self.graph.get_node(element_id):
            self.graph.add_edge(
                edge_type, source_id, element_id,
                evidence=lo_id, rationale=rationale, verified=verified,
            )

    def _invalidate_impacted(
        self,
        node_id: str,
        reason: str,
        *,
        action: str = "cascade_invalidation",
        changed_fields: list[str] | None = None,
        evidence: str = "",
        violation_type: str = "",
    ) -> dict[str, list]:
        impact = self.graph.invalidate_impacted(
            node_id,
            changed_fields=changed_fields,
            evidence=evidence,
            reason=reason,
        )
        if impact["nodes"] or impact["edges"]:
            self.trajectory.log_step(
                type(self).__name__,
                action,
                node_id,
                f"Marked stale nodes={len(impact['nodes'])} edges={len(impact['edges'])}.",
            )
            self.trajectory.log_cascade_event(node_id, impact["nodes"], impact["edges"], reason)
        if action == "repair_cascade":
            self.trajectory.log_repair_event(
                agent=type(self).__name__,
                violation_type=violation_type,
                node_id=node_id,
                repaired_fields=changed_fields or [],
                cascade={"nodes": len(impact["nodes"]), "edges": len(impact["edges"])},
            )
        return impact

    def _call_llm(self, messages: list[dict], max_retries: int = 1) -> str:
        """Call LLM with automatic retry on empty/invalid response.

        max_retries=1 means: try once normally, if response is empty or produces
        no parseable JSON, send a correction turn and try once more.
        """
        try:
            if self.config.llm_factory is None:
                raise RuntimeError("llm_factory not set — cannot call LLM")
            llm = self.config.llm_factory()
            try:
                llm = llm.bind(response_format={"type": "json_object"})
            except Exception:
                pass
            content = self._invoke_with_retry(llm, messages, max_retries)
            return content
        except Exception as exc:
            self.trajectory.log_llm_call(0, 0)
            self.trajectory.log_step(type(self).__name__, "llm_error", "", str(exc))
            return ""

    def _invoke_with_retry(self, llm, messages: list[dict], max_retries: int) -> str:
        """Invoke the LLM, retrying once with a correction message if output is empty."""
        result = llm.invoke(messages)
        content = result.content if hasattr(result, "content") else str(result)
        usage = getattr(result, "usage_metadata", None)
        self.trajectory.log_llm_call(
            getattr(usage, "input_tokens", 0) if usage else 0,
            getattr(usage, "output_tokens", 0) if usage else 0,
        )
        if max_retries > 0 and not parse_json_response(content, warn=False):
            # Output was not valid JSON — send a correction turn
            self.trajectory.log_step(type(self).__name__, "retry", "empty/invalid JSON", content[:100])
            correction_messages = messages + [
                {"role": "assistant", "content": content},
                {"role": "user", "content": (
                    "Your previous response was not valid JSON or was empty. "
                    "Return ONLY the JSON object with no other text, no markdown fences."
                )},
            ]
            return self._invoke_with_retry(llm, correction_messages, max_retries - 1)
        return content

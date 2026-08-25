from __future__ import annotations
import json
import re
import time
from abc import ABC, abstractmethod
from ...config import HarnessRunConfig
from ..alignment_graph import alignment
from .. import checks
from ..alignment_graph import AlignmentGraph
from ..brief import DesignBrief
from ..ratelimit import gate_for
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


def _salvage_json(text: str) -> dict:
    """Best-effort deterministic repair of malformed LLM JSON via json-repair.

    Returns a non-empty dict on success, ``{}`` otherwise (including when the
    library is unavailable, so callers degrade to the pre-salvage behavior).
    A top-level list — e.g. the model emitted ``[...]`` then a second ``{...}``
    value — is merged dict-by-dict in order, mirroring the section-dict shape
    every specialist expects.
    """
    try:
        import json_repair
    except ImportError:
        return {}
    try:
        repaired = json_repair.loads(text)
    except Exception:
        return {}
    if isinstance(repaired, dict) and repaired:
        return repaired
    if isinstance(repaired, list):
        merged: dict = {}
        for item in repaired:
            if isinstance(item, dict):
                merged.update(item)
        if merged:
            return merged
    return {}


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


def parse_json_response(raw: str, *, warn: bool = True, salvage: bool = True) -> dict:
    """Robustly parse a JSON dict from an LLM response.

    Handles: markdown fences, leading/trailing prose, literal control
    characters inside string values, and other common LLM JSON issues.
    Logs a warning (does not raise) if all attempts fail.

    ``salvage=True`` adds a final deterministic repair pass (json-repair) that
    recovers output no targeted fix above could: invalid escapes, stray quotes,
    multiple top-level values, and cap-truncated responses (keeps the complete
    prefix). ``salvage=False`` keeps the strict behavior — used by the
    correction-turn check in ``_invoke_with_retry`` so the model still gets its
    retry chances before we accept a repaired (possibly lossy) parse.
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

        # Try 5: deterministic salvage via json-repair. Only reached when every
        # targeted fix above failed, so well-formed responses never take this
        # path. Covers the malformed-JSON classes small models (0.8B) emit:
        # invalid escapes (\'), stray quotes after brackets, several top-level
        # values, and mid-string truncation at the completion cap. Runs BEFORE
        # the bracket-closing fallback because json-repair keeps the complete
        # truncated prefix (it closes the string mid-value), whereas closing
        # the regex candidate cuts at the last '}' and drops everything after.
        if salvage:
            salvaged = _salvage_json(cleaned) or _salvage_json(candidate)
            if salvaged:
                return salvaged

        # Try 6: append missing closing braces/brackets for truncated JSON.
        try:
            balanced = _close_unbalanced_json(no_trailing)
            result = json.loads(_fix_json_control_chars(balanced))
            if isinstance(result, dict):
                return result
        except json.JSONDecodeError as e:
            last_err = e

    elif salvage:
        # No '{' block found at all (e.g. a bare top-level array): still give
        # json-repair a chance before giving up.
        salvaged = _salvage_json(cleaned)
        if salvaged:
            return salvaged

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


# Default execution-strategy hint per Designer task for on-demand retrieval. The
# specialist's decision call can override; broad analysis/creation tasks lean
# parallel, narrowly-scoped design tasks lean single.
RETRIEVAL_STRATEGY_HINTS = {
    "outcome_designer": "parallel",
    "assessment_designer": "single",
    "activity_designer": "single",
    "content_designer": "parallel",
    "rubric_designer": "single",
    "implementation_plan": "single",
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


# ── retired: narrative prose rendering ────────────────────────────────────────
# An earlier `prose` arm rendered the SAME graph-selected nodes as sentences
# (per-type templates), which made the arm a costume on the graph: selection,
# docket, checks, routing and aggregation all still ran on the graph, so the
# axis measured surface form only. The current `prose` arm replaces the store
# itself (see core/prose_store.py); the sentence templates were deleted with it.


class BaseISDAgent(ABC):
    # Verifier violation types this specialist is responsible for. Each specialist
    # self-checks and repairs its own artifact at the end of its turn (a quality
    # tool it owns), so no separate global verify phase is needed. Overridden per
    # subclass; empty means "no self-check".
    OWNED_VIOLATION_TYPES: frozenset[str] = frozenset()

    def __init__(self, config: HarnessRunConfig, graph: AlignmentGraph | None,
                 trajectory: TrajectoryLogger, store=None) -> None:
        self.config = config
        # Exactly one of the two context substrates is live per run: the
        # AlignmentGraph in graph mode, the ProseStore blackboard in prose
        # mode. The other is None so an arm can never quietly lean on the
        # substrate it claims not to use.
        self.graph = graph
        self.store = store
        self.trajectory = trajectory

    @property
    def _graph_mode(self) -> bool:
        return getattr(self.config, "context_mode", "graph") == "graph"

    def _store_context(self, keys: tuple[str, ...], max_chars: int = 600) -> str:
        """Prose-arm context injection: the named blackboard documents as
        verbatim JSON text (see ``core/prose_store.py``). The read-list is a static
        design-time decision per step — no selection logic, no derived facts."""
        if self.store is None:
            return ""
        return self.store.context(keys, max_chars=max_chars)

    @abstractmethod
    def run(self, design_brief: DesignBrief) -> None:
        ...

    # Verifier violation types this specialist owns. A Designer's own
    # self-validation step reads this to decide which violations it should
    # repair itself before committing (inline, not a separate QC graph node).
    def repair(self, violations: list) -> list:  # noqa: D401 - overridden by specialists
        """Default no-op repair; specialists override to fix owned violations."""
        return violations

    #: Caps for the alignment-state block. Edges are illustrative (the model
    #: needs the pattern, not the census); gap ids are the actionable
    #: checklist, so their cap is higher. Both caps disclose what they cut.
    _EDGE_LINE_CAP = 12
    _GAP_ID_CAP = 20

    def _alignment_state(self, *, edges: tuple[str, ...] = (),
                         gaps: tuple[str, ...] = (),
                         plan_pairs: bool = False) -> dict:
        """**Alignment-state scaffolding** (canonical mechanism name — see the
        package README): the shared fact source both context representations
        render from.

        Three kinds of facts, all computed deterministically from the graph at
        call time, none of them a restatement of the rules already in the
        system prompt:

        - ``edges``: established links for the named relations — connectivity
          the model otherwise has to reconstruct from ID fields inside node
          JSON.
        - ``gaps``: the named relations' coverage obligations INSTANTIATED
          against current state — "ILO-03 has no assessed_by link yet", not
          "every objective needs one". SLMs apply an enumerated checklist far
          more reliably than a universally-quantified rule; measured on this
          very harness: with the quantified rule alone in the prompt, a 9B
          model produced 16 diagnostic / 1 summative items against a plan
          promising 1 / 5.
        - ``plan_pairs``: the (objective x plan_category) pairs the assessment
          plan promises that no item yet realises (``checks.plan_coverage`` —
          the instantiation of exactly that measured failure).

        The system prompt keeps the LAW (static, stated once, prefix-cache
        friendly, arm-parity guaranteed by the ``_rules`` derivation); this
        block carries the DOCKET (per-run state the system prompt cannot
        contain). Splitting by staticness is the design decision — putting
        rule text here as well would pay its tokens twice.
        """
        facts: dict = {"edges": [], "gaps": [], "plan_pairs": []}
        for rid in edges:
            relation = alignment.REGISTRY[rid]
            for edge in self.graph.get_edges(relation_id=rid):
                facts["edges"].append({
                    "source": edge["source"], "target": edge["target"],
                    "relation": relation.key,
                })
        for rid in gaps:
            relation = alignment.REGISTRY[rid]
            _, uncovered = alignment.relation_coverage(self.graph, rid)
            if uncovered:
                facts["gaps"].append({
                    "relation": relation.key, "label": relation.label,
                    "nodes": uncovered,
                })
        if plan_pairs:
            for violation in checks.plan_coverage(self.graph):
                facts["plan_pairs"].append({
                    "objective": violation.metadata.get("lo_id", ""),
                    "category": violation.metadata.get("plan_category", ""),
                })
        return facts

    def _alignment_state_context(self, *, edges: tuple[str, ...] = (),
                                 gaps: tuple[str, ...] = (),
                                 plan_pairs: bool = False) -> str:
        """The alignment-state block. Graph mode only: the docket is a product
        of the alignment machinery (coverage instantiated against graph
        state), so the prose arm has no equivalent — its prompts carry the LAW
        (the rules in the system prompt, shared by both arms) but never an
        instantiated docket. Call sites sit inside graph-mode branches."""
        facts = self._alignment_state(edges=edges, gaps=gaps, plan_pairs=plan_pairs)
        if not (facts["edges"] or facts["gaps"] or facts["plan_pairs"]):
            return ""
        return self._render_state_structured(facts)

    @staticmethod
    def _bare(node_id: str) -> str:
        return node_id.split(":", 1)[-1]

    def _render_state_structured(self, facts: dict) -> str:
        lines: list[str] = ["=== ALIGNMENT STATE ==="]
        if facts["edges"]:
            lines.append("[EDGES]")
            for edge in facts["edges"][: self._EDGE_LINE_CAP]:
                # bare ids: namespaced ids in prompts leak into model output
                # and break the bare-id matchers (see _node_header).
                lines.append(f"{self._bare(edge['source'])} --{edge['relation']}--> {self._bare(edge['target'])}")
            extra = len(facts["edges"]) - self._EDGE_LINE_CAP
            if extra > 0:
                lines.append(f"... and {extra} more edges")
        if facts["gaps"]:
            lines.append("[GAPS — your output must close these]")
            for gap in facts["gaps"]:
                ids = ", ".join(self._bare(n) for n in gap["nodes"][: self._GAP_ID_CAP])
                extra = len(gap["nodes"]) - self._GAP_ID_CAP
                more = f" (+{extra} more)" if extra > 0 else ""
                lines.append(f"{gap['relation']} missing for: {ids}{more}")
        if facts["plan_pairs"]:
            lines.append("[PLAN-PROMISED PAIRS, NOT YET REALISED — produce exactly these]")
            lines.append("; ".join(f"{p['objective']} x {p['category']}" for p in facts["plan_pairs"]))
        return "\n".join(lines)

    def _element_context(self, nodes: list[dict], max_chars: int = 600) -> str:
        """**Relation-scoped context injection** (canonical mechanism name —
        see the package README): format specific element/section nodes for
        prompt injection, one ``[TYPE:ID]`` block per node, its ``data`` as
        truncated JSON.

        Graph mode only — this is graph-context retrieval (core, not RAG):
        each agent reads what earlier agents already deposited in the
        AlignmentGraph before generating its own section. The caller passes
        exactly the nodes a relation calls for — e.g.
        ``self._element_context(self.graph.element_nodes(NodeType.OBJECTIVE))``
        for "every learning objective", or a list assembled from
        ``get_node``/``get_edges`` for a relation-scoped set. Never pass "the
        whole graph" — each Designer's own docstring/prompt states exactly
        which node types it reads, and that list is the token budget.

        The prose arm never calls this: its counterpart is ``_store_context``,
        which reads whole blackboard documents by a static read-list (no
        selection — that is part of what the axis ablates).
        """
        lines: list[str] = []
        for node in nodes:
            data_str = json.dumps(node.get("data", {}), ensure_ascii=False)
            if len(data_str) > max_chars:
                data_str = data_str[:max_chars] + "…"
            lines.append(f"{self._node_header(node)}\n{data_str}")
        return "\n\n".join(lines)

    @staticmethod
    def _node_header(node: dict) -> str:
        """``[TYPE:BARE-ID]`` — deliberately the BARE element id, never the
        namespaced node id. Rendering ``[OBJECTIVE:objective:ILO-01]`` taught
        models the namespaced form, which they then echoed into reference
        fields ("objective:ILO-01"), silently breaking every bare-id matcher
        (measured: a 2B single-graph run keyed lo_coverage_targets by
        namespaced ids and plan_coverage reported 14/14 false gaps). Section
        nodes render as plain ``[TYPE]``."""
        node_type = str(node.get("type", ""))
        node_id = str(node.get("id", ""))
        if node_id.startswith(f"{node_type}:"):
            return f"[{node_type.upper()}:{node_id[len(node_type) + 1:]}]"
        if node_id == f"{node_type}_0":
            return f"[{node_type.upper()}]"
        return f"[{node_type.upper()}:{node_id}]"

    def _element_context_joined(self, parents: list[dict], children: list[dict],
                                relation_id: str, verb: str, max_chars: int = 600) -> str:
        """**Relation-join context injection**: the same nodes as two flat
        ``_element_context`` lists, but pre-joined along the established
        ``relation_id`` edges — each parent block carries the child blocks its
        edges point at, and children no edge claims are listed under an
        explicit NOT-YET-LINKED header instead of disappearing.

        This is the generation-time work only the graph can do: handing the
        model resolved evidence chains (objective -> its assessment items)
        instead of two parallel lists it must cross-reference by id itself.
        The prose arm has no counterpart by design — re-deriving the join is
        exactly the alignment machinery the axis ablates. Same per-node cap
        as the flat rendering; graph mode only."""
        child_by_id = {child["id"]: child for child in children}
        claimed: set[str] = set()
        blocks: list[str] = []
        for parent in parents:
            kids: list[dict] = []
            for edge in self.graph.get_edges(relation_id=relation_id, source=parent["id"]):
                child = child_by_id.get(edge["target"])
                if child is not None and child["id"] not in {k["id"] for k in kids}:
                    kids.append(child)
                    claimed.add(child["id"])
            block = self._element_context([parent], max_chars=max_chars)
            if kids:
                kid_text = self._element_context(kids, max_chars=max_chars)
                indented = "\n".join(f"    {line}" for line in kid_text.splitlines())
                block += f"\n  {verb}:\n{indented}"
            blocks.append(block)
        orphans = [child for child in children if child["id"] not in claimed]
        if orphans:
            orphan_type = str(orphans[0].get("type", "")).upper() or "CHILD"
            blocks.append(
                f"[{orphan_type} NOT YET LINKED — align these or leave deliberately]\n"
                + self._element_context(orphans, max_chars=max_chars)
            )
        return "\n\n".join(blocks)

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

    # ── fan-out finalize: per-set regen ─────────────────────────────────────

    def _regen_missing_sets(self, work_sets: list, payloads: list[dict], developer,
                            design_brief: DesignBrief, family: str, *,
                            identity: str | None = None) -> list[dict]:
        """Re-invoke ``developer`` for any work set whose payload came back
        with zero items, up to ``config.regen_budget`` attempts — the
        fan-out's per-set retry story, called from a family's ``finalize()``.

        Runs single-threaded inside finalize (not a separate LangGraph node),
        so it needs no ``acting_as`` of its own: the Developer already names
        itself in every log call it makes (``log_step``/``_call_llm``'s
        internal logging both pass ``type(self).__name__`` explicitly), and
        the recovery event below names it too — ``identity`` defaults to
        ``type(developer).__name__`` (every multi-arm Developer class), but
        the single arm passes its OWN identity explicitly since its per-set
        caller is a same-instance adapter method, not a distinct class
        deserving its own name in the trace. Returns ``payloads`` plus
        whatever the regenerated attempts produced — callers merge with
        :func:`core.dev_plans.remap_and_tag`, which is itself indifferent to
        how many payloads named the same set.
        """
        from .. import dev_plans as _dev_plans

        identity = identity or type(developer).__name__
        budget = max(0, int(getattr(self.config, "regen_budget", 2)))
        backoff = max(0.0, float(getattr(self.config, "regen_backoff_seconds", 0.0)))
        payloads = list(payloads)
        by_id = {ws.set_id: ws for ws in work_sets}
        for attempt in range(1, budget + 1):
            pending_ids = _dev_plans.pending_set_ids(work_sets, payloads)
            if not pending_ids:
                break
            if backoff:
                time.sleep(backoff * attempt)
            for set_id in pending_ids:
                work_set = by_id.get(set_id)
                if work_set is None:
                    continue
                self.trajectory.log_recovery_event(
                    identity, "regen_empty_section",
                    f"attempt {attempt}", f"{family}:{set_id}",
                )
                payloads.append(developer.run_worker(work_set, design_brief))
        return payloads

    # ── On-demand agentic retrieval (RAG as a tool the specialist decides to use) ──

    def _with_retrieval(self, design_brief: DesignBrief, task_name: str, user_content: str) -> str:
        """Prepend on-demand domain material to the prompt when the agent asks for it."""
        material = self._maybe_retrieve(design_brief, task_name, user_content)
        if material:
            return f"{material}\n\n{user_content}"
        return user_content

    def _maybe_retrieve(self, design_brief: DesignBrief, task_name: str, prior_context: str = "") -> str:
        """Let this specialist decide whether/how to retrieve external domain material.

        Gated hard on a non-empty registry: on the benchmark path
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
            self.trajectory.log_recovery_event(type(self).__name__, "llm_error", "", "llm_factory not set — cannot call LLM")
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
                    self.trajectory.log_recovery_event(
                        type(self).__name__, "salvage_truncated", str(exc)[:80], content[:100],
                    )
                    if content:
                        return content
                except Exception:
                    pass
            self.trajectory.log_llm_call(0, 0)
            self.trajectory.log_recovery_event(type(self).__name__, "llm_error", "", str(exc))
            return ""

    def _invoke_with_retry(self, llm, messages: list[dict], max_retries: int) -> str:
        """Invoke the LLM, retrying once with a correction message if output is empty."""
        # A single call can run for tens of seconds and nothing is recorded until
        # it returns, so this is the only signal a live viewer has that the
        # harness is working rather than wedged. Progress-only: records nothing.
        self.trajectory.emit("llm_started", {
            "agent": type(self).__name__,
            "prompt_chars": sum(len(m.get("content", "")) for m in messages),
            "message_count": len(messages),
            "retries_left": max_retries,
        })
        started = time.time()
        # One slot from the run's call gate for the duration of the request:
        # the multi arm fans out content/rubric Developer calls in one
        # superstep, and an endpoint that caps concurrent requests per user
        # answers the overflow with 429 (see core/ratelimit.py).
        with gate_for(self.config).hold():
            result = llm.invoke(messages)
        content = result.content if hasattr(result, "content") else str(result)
        prompt_tokens, completion_tokens = _extract_token_usage(result)
        duration_ms = (time.time() - started) * 1000
        self.trajectory.emit("llm_finished", {
            "agent": type(self).__name__,
            "duration_ms": duration_ms,
            "response_chars": len(content or ""),
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
        })
        self.trajectory.log_action(
            "llm_call",
            agent=type(self).__name__,
            duration_ms=duration_ms,
            prompt_chars=sum(len(m.get("content", "")) for m in messages),
            response_chars=len(content or ""),
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            attempt_of_retries_left=max_retries,
        )
        self.trajectory.log_llm_call(prompt_tokens, completion_tokens)
        # salvage=False: judge validity strictly so the correction turns still
        # fire on malformed JSON; the deterministic salvage is only the final
        # net once retries are exhausted (a salvaged parse can be lossy).
        if max_retries > 0 and not parse_json_response(content, warn=False, salvage=False):
            # Output was not valid JSON — send a targeted correction turn quoting
            # the exact parse error so the model can fix that specific spot.
            hint = _json_error_hint(content)
            self.trajectory.log_recovery_event(type(self).__name__, "retry", hint or "empty/invalid JSON", content[:100])
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

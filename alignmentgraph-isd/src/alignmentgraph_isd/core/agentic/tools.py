"""Deterministic tool executors for the agentic arm.

Each tool wraps a read API (graph queries, relation coverage, blackboard
documents) and renders its observation with fixed
caps, so what the model sees is a pure function of graph state — the agency
is in WHICH tools the model calls, never in what a call returns.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from .. import checks
from ..alignment_graph import alignment
from ..alignment_graph.alignment import bare_ref
from ..llm_io import close_unclosed_arrays, parse_json_array, parse_json_response
from .artifact_schemas import ARTIFACT_SCHEMAS, required_floor

if TYPE_CHECKING:  # pragma: no cover - typing only
    from ..alignment_graph import AlignmentGraph
    from .specialists import AgenticStep

#: Rendering caps. Bounded by BYTES, not by a node count: see ``render_nodes``,
#: which explains why a count cap was dropped in favour of the byte budget.
NODE_CHAR_CAP = 600
#: Total characters ONE read may return, in either context mode. Bounds what
#: actually breaks — the prompt — rather than an arbitrary item count.
READ_CHAR_BUDGET = 8000
EDGE_LINE_CAP = 30
GAP_ID_CAP = 20


#: How much of a listing row's LABEL is shown, and how long a value may be to
#: count as a short identifying facet rather than prose.
LISTING_LABEL_CAP = 120
FACET_CHAR_CAP = 24
#: The label of a listing row is the first of these the node carries, in this
#: order. Ordered by SPECIFICITY, not by node type: an activity holds both
#: ``activity_name`` and ``description`` and the name wins; a material holds
#: both ``title`` and ``content`` and the title wins. A type that appears later
#: falls through to ``description``/``content`` rather than rotting, which is
#: why this is a probe and not a per-type table.
_LABEL_FIELDS = ("statement", "question", "activity_name", "title",
                 "description", "purpose", "content")


def _node_header(node: dict) -> str:
    """``TYPE:ID``, with the BARE id. A node's own id is namespaced
    ("objective:ILO-01"), and a model echoes back whatever it is shown — it was
    writing "objective:ILO-01" into aligned_objective fields, which then matched
    nothing. A SECTION node is a singleton, so its id ("assessment_plan_0") says
    nothing the type does not, and it is one more string the model can echo into
    a reference field: header it by type alone."""
    node_id = bare_ref(node.get("id", ""))
    node_type = str(node.get("type", ""))
    if node_id == f"{node_type}_0":
        return node_type.upper()
    return f"{node_type.upper()}:{node_id}"


#: Node keys that are the harness's own bookkeeping and never a row facet.
#: ``plan_set`` names the WORK SET that wrote an element (``AB-01``,
#: ``MU-C-01``); shown beside real ids it reads as one, and a Developer goes
#: and asks for it. MEASURED (runs 14a6b4c7, 9efc3cfa): a list read for ``ids=
#: ["AB-01", "AB-02", "AB-03"])`` on a Material Developer's second or third
#: turn in both, each an ERROR and then a repeat of it.
_HARNESS_FACETS = frozenset({"plan_set"})


def render_listing(nodes: list[dict], budget: int = READ_CHAR_BUDGET) -> str:
    """One LINE per node: id, its short identifying fields, and a label.

    What ``read_alignment_state`` lists its artifacts with, where ``read_node``
    keeps the full dump.
    MEASURED (run 2b9e911a, the implementation stage): listing every activity
    and material as full JSON put 3,590–5,607 tokens of tool results against an
    8,192-token prompt budget with only 352–934 tokens of conversation beside
    them, so the stage crossed the trim line on its ninth turn and compaction
    took the stage brief with it. The planner needed ids to write
    ``activity_ids``/``material_ids``; it was handed every material's whole
    learner-facing script, the longest string the harness produces. That run's
    own eight materials render as 4,968 characters of blocks and 855 of
    listing — 17%, and the ids it actually needed are all in the 17%.

    A row is composed by two data-driven rules rather than a per-type field
    table, which would rot as the schemas move:

    * the LABEL is the first of ``_LABEL_FIELDS`` the node carries;
    * the FACETS are every other key whose value is a SHORT scalar. That one
      rule keeps ``level``, ``plan_category``, ``type``, ``format`` and
      ``linked_module`` — which downstream rules genuinely need, so dropping
      them would trade a compaction bug for a Bloom bug — and drops
      ``rubric``, ``scoring_criteria`` and ``content`` without naming any of
      them. A key repeating the id already in the header is dropped too.
    """
    lines: list[str] = []
    used = 0
    shown = 0
    for node in nodes:
        if used >= budget:
            break
        data = node.get("data") or {}
        node_id = bare_ref(node.get("id", ""))
        label_field, label = "", ""
        for field_name in _LABEL_FIELDS:
            value = data.get(field_name)
            if isinstance(value, str) and value.strip():
                label_field, label = field_name, " ".join(value.split())
                break
        if len(label) > LISTING_LABEL_CAP:
            label = label[:LISTING_LABEL_CAP] + "…"
        facets = [
            f"{key}={value}"
            for key, value in data.items()
            if key != label_field
            and key not in _HARNESS_FACETS
            and isinstance(value, (str, int, float, bool))
            and str(value).strip()
            and len(str(value)) <= FACET_CHAR_CAP
            and str(value) != node_id
        ]
        row = f"[{_node_header(node)}]"
        if facets:
            row += " " + " ".join(facets)
        if label:
            row += f" | {label}"
        lines.append(row)
        used += len(row)
        shown += 1
    omitted = len(nodes) - shown
    if omitted > 0:
        lines.append(f"... and {omitted} more not shown (read budget reached). "
                     "Read them by id if you need them.")
    return "\n".join(lines) if lines else "(no nodes yet)"


def render_nodes(nodes: list[dict], max_chars: int = NODE_CHAR_CAP,
                 budget: int = READ_CHAR_BUDGET) -> str:
    """One ``[TYPE:ID]`` block per node, data as truncated JSON, up to a total
    character budget.

    Bounded by SIZE, never by a node count. A count cap applied per substrate
    — 25 nodes on the graph arm, nothing on the prose arm — reports a design
    with many items in full to one context mode and truncated in the other, an
    asymmetry sitting on the ``context_mode`` axis itself. No cap at all is
    worse: measured on run single_20260901_154303, a prose arm that wrote 10
    objectives and 112 materials pushed one observation to 68,786 characters,
    past the serving window, and 28 of its 32 Developer calls fell back.

    A byte budget is the right unit because bytes are what actually breaks: it
    is the same rule in both modes, it does not pretend 25 of anything is the
    right number, and what it leaves out it says out loud rather than silently.
    """
    lines: list[str] = []
    used = 0
    shown = 0
    for node in nodes:
        if used >= budget:
            break
        data_str = json.dumps(node.get("data", {}), ensure_ascii=False)
        if len(data_str) > max_chars:
            data_str = data_str[:max_chars] + "…"
        block = f"[{_node_header(node)}]\n{data_str}"
        lines.append(block)
        used += len(block)
        shown += 1
    omitted = len(nodes) - shown
    if omitted > 0:
        lines.append(f"... and {omitted} more not shown (read budget reached). "
                     "Read them by id if you need them.")
    return "\n\n".join(lines) if lines else "(no nodes yet)"


# ── tool executors ──────────────────────────────────────────────────────────
# Uniform contract: (graph, step, args) -> observation string. Errors are
# returned as "ERROR: ..." observations — the model gets to correct itself
# inside its turn budget instead of the run failing.


def _resolve_node(graph: "AlignmentGraph", step: "AgenticStep", node_id: str):
    """One id to its node, trying the readable types' namespaces for a bare id
    ("ILO-01" rather than "objective:ILO-01")."""
    node = graph.get_node(node_id)
    if node is None and graph.ELEMENT_SEP not in node_id:
        for node_type in step.readable_types:
            node = graph.get_node(f"{node_type}{graph.ELEMENT_SEP}{node_id}")
            if node is not None:
                break
    if node is None:
        # The row header is ``[GAP:GAP-001]``, and a model asked for ids copies
        # it back as ``GAP:GAP-001`` or fuses it into ``GAP-GAP-001``. Both
        # name exactly one artifact, so both are served. MEASURED (run
        # 9efc3cfa, outcomes): the fused form was refused, and the refusal was
        # followed by the same three-read batch four times over.
        for node_type in step.readable_types:
            for sep in (graph.ELEMENT_SEP, "-"):
                prefix = f"{node_type}{sep}"
                if node_id.lower().startswith(prefix) and len(node_id) > len(prefix):
                    node = graph.get_node(
                        f"{node_type}{graph.ELEMENT_SEP}{node_id[len(prefix):]}")
                    if node is not None:
                        return node
    return node


def _where_ids_are(step) -> str:
    """Where this caller finds the ids that exist: the state read where one is
    bound, the assignment for a work set, which is handed its ids and has no
    list tool to be sent to."""
    if getattr(step, "state_tool", True):
        return f"Call {STATE_TOOL} for the ids that exist."
    return "The ids you may read are the ones your assignment names."


def run_read_node(graph: "AlignmentGraph", step: "AgenticStep", args: dict) -> str:
    """Read artifacts from the design graph in full — SEVERAL per call.

    MEASURED (run single_20260908_111232, content): the Content Designer spent
    27 turns on 24 distinct ``read_node`` calls and the Material Developer 27 on
    16, both walking a list of activity ids one node per turn. At
    ``STAGE_MAX_TURNS`` 24 that exhausts the stage on reading alone, and the
    content stage duly gave up — 41 turns, 35 reads, and a design left with 5
    content modules against 23 activities.

    The counterpart of the state read being a one-line-per-node LISTING:
    without a batched read, the only way to read what the listing names is one
    call per id, so the listing hands the model a bill it pays a turn at a
    time. Batching changes turns, not scope.

    The read budget is SHARED across the ids, never multiplied by them: one id
    gets the whole budget, a batch divides it, with ``NODE_CHAR_CAP`` as the
    floor. What does not fit is named out loud by ``render_nodes``, not
    dropped. An id that does not resolve costs THAT id and not the call — one
    typo taking the whole batch would put back the per-id turn cost.

    ON THE ``context_mode`` AXIS, since this tool is bound in graph mode only.
    It NARROWS an asymmetry already running against the graph arm: a prose
    document IS a whole family (``read_document('activity')`` returns every
    activity in one call) while the graph arm names elements one at a time, so
    on the same design prose reached the same information in 1 turn against 23.
    The axis measures what state each mode holds, not how many turns the
    harness charges to look at it.
    """
    raw = args.get("ids", args.get("id", ""))
    ids = [str(one).strip() for one in (raw if isinstance(raw, list) else [raw])]
    ids = [one for one in ids if one]
    if not ids:
        return ('ERROR: args must carry {"ids": ["<node id>", ...]}. ' + _where_ids_are(step))

    found, missing = [], []
    for node_id in dict.fromkeys(ids):          # de-duplicated, order kept
        node = _resolve_node(graph, step, node_id)
        (found.append(node) if node is not None else missing.append(node_id))

    # Naming what MAY be read, rather than only that this id may not. Measured
    # on the same run: the Material Developer asked for 'MS-001' — a real
    # media_selection node, outside its read scope — was told only "no node
    # with id 'MS-001'", and asked again. The scope is the treatment and is not
    # widened here; what changes is that the refusal says what it is.
    note = ""
    if missing:
        note = ("ERROR: no readable artifact with id "
                + ", ".join(repr(one) for one in missing)
                + ". Readable types here: " + (", ".join(step.readable_types) or "none")
                + ". " + _where_ids_are(step))
    if not found:
        return note
    # "In full" means in full: at NODE_CHAR_CAP this tool truncated a 1,710-char
    # material to 600 and its description was untrue.
    per_node = max(NODE_CHAR_CAP, READ_CHAR_BUDGET // len(found))
    rendered = render_nodes(found, max_chars=per_node)
    return f"{rendered}\n\n{note}" if note else rendered


def unwrap_section(section: dict, validate) -> tuple[dict, list[str]]:
    """Deterministic envelope tolerance: small models often wrap the artifact
    under one extra key ({"artifact": {...}}, {"draft": {...}}, or the
    artifact's own name) despite the protocol. Try the object as given, then
    one level of unwrapping; return the first candidate that validates,
    otherwise the original object with its errors. Measured failure this
    answers: a 2B model wrapped the implementation plan as {"artifact": ...}
    on every attempt, shipped an empty-looking section and scored 0 on the
    whole Implementation phase."""
    if not isinstance(section, dict):
        return {}, validate({})
    errors = validate(section)
    if not errors:
        return section, []
    candidates: list[dict] = []
    for key in ("artifact", "draft", "section", "args"):
        value = section.get(key)
        if isinstance(value, dict) and value:
            candidates.append(value)
    if len(section) == 1:
        only = next(iter(section.values()))
        if isinstance(only, dict) and only:
            candidates.append(only)
    for candidate in candidates:
        if not validate(candidate):
            return candidate, []
    return section, errors


# ── prose-arm executors ─────────────────────────────────────────────────────
# The blackboard has no id index, no relation vocabulary and no derived facts,
# so it can offer only "list what exists" and "read one document whole". That
# poverty is the ``context_mode`` treatment, not an oversight: a prose arm that
# could answer "which objectives are still unassessed" would BE the graph arm.


def run_list_documents(store, step: "AgenticStep", args: dict) -> str:
    available = [key for key in step.readable_docs if store.has(key)]
    if not available:
        return "(no documents from earlier steps yet)"
    return "Documents you can read: " + ", ".join(available)


def run_read_document(store, step: "AgenticStep", args: dict) -> str:
    key = str(args.get("key", "")).strip().lower()
    if key not in step.readable_docs:
        return "ERROR: key must be one of: " + ", ".join(step.readable_docs)
    if not store.has(key):
        return f"(no {key} document has been written yet)"
    # Same byte budget as the graph arm's reads: the two modes differ in what
    # state they hold, not in how much of it one observation may carry.
    rendered = store.context((key,), max_chars=NODE_CHAR_CAP)
    if len(rendered) > READ_CHAR_BUDGET:
        rendered = (rendered[:READ_CHAR_BUDGET]
                    + "\n… (read budget reached; the rest of this document is not shown)")
    return rendered


# No separate "check my artifact" tool: a rejected submit returns the same
# errors at no re-emission cost, and the retry allowance is ``SUBMIT_BUDGET``.
#: ``read_alignment_state`` is not here: it needs the design brief and the
#: ledger, which this ``(graph, step, args)`` contract does not carry, so each
#: loop serves it itself through ``alignment_state.read``.
EXECUTORS = {
    "read_node": run_read_node,
}

PROSE_EXECUTORS = {
    "list_documents": run_list_documents,
    "read_document": run_read_document,
}


def executors_for(*, graph_mode: bool) -> dict:
    return EXECUTORS if graph_mode else PROSE_EXECUTORS


# ── native tool schemas ─────────────────────────────────────────────────────
# The ladder serves vLLM with ``--enable-auto-tool-choice --tool-call-parser
# qwen3_coder``, so tool calls are native: the serving-side parser enforces the
# argument shape before the model's text ever reaches us. That is worth more
# than a text JSON-action protocol at the small end of the ladder, where the
# measured failures are shape failures (a wrapped artifact, a bare artifact on
# turn 1, a truncated object). It removes ONE failure mode and no others: the
# anti-loop guard and the submit budget are needed exactly as much.

def _parameters_from(fields: tuple) -> dict:
    """The submit schema for a set of ``(key, json_type, required)`` fields.

    Each key's shape comes from :data:`artifact_schemas.ARTIFACT_SCHEMAS`,
    under the key itself. Every submit
    field has an entry (``test_every_submit_field_has_an_artifact_schema``),
    so a missing one fails loudly rather than binding a schema-less tool.

    A REQUIRED artifact carries its floor (``artifact_schemas.required_floor``)
    for the reason stated there: an ARRAY artifact — the objectives, the
    modules, the media selections, a Developer's own output — is judged
    non-empty on arrival, and a schema saying only "present" is a contract
    weaker than the one the submit is measured against."""
    properties: dict = {}
    required: list[str] = []
    for key, json_type, is_required in fields:
        detailed = ARTIFACT_SCHEMAS[key]
        shape = ({"type": "array", "items": detailed}
                 if json_type == "array" else dict(detailed))
        properties[key] = required_floor(shape) if is_required else shape
        if is_required:
            required.append(key)
    return {"type": "object", "properties": properties, "required": required}


def submit_parameters(step: "AgenticStep") -> dict:
    """The stage's WHOLE artifact as one schema — every top-level key at once.

    The multi arm binds no tool shaped like this (see :func:`submit_specs`):
    a stage there is one tool per artifact. This is the SINGLE arm's per-stage
    submit, where one agent works the whole brief and picks a stage to advance,
    and it is also the union the transport coercion is defined against."""
    return _parameters_from(step.submit_fields)


def submit_specs(step: "AgenticStep", only: tuple[str, ...] | None = None) -> list[dict]:
    """ONE submit tool per top-level artifact, named after the artifact.

    ``submit_assessment_plan`` and ``submit_assessment_dev_plan``, not one
    ``submit`` carrying both. Three things follow, and the first is the reason:

    * **The model emits one artifact per call.** A whole stage has to fit under
      the 8192-token completion cap in a single call, and ``implementation`` is
      six objects.
    * **A rejected artifact costs that artifact.** The validator judges what
      arrived; the rest stay committed and are not re-emitted.
    * **The tool name states what is being written**, so a plan submitted as a
      dev plan is a wrong tool rather than a mis-keyed object.

    The parameters keep the artifact's own key rather than taking the value
    bare (``{"assessment_plan": {...}}``, not ``{...}``): that key is what
    ``unwrap_section`` and every ``commit`` address the artifact by, and a weak
    model just shown the schema for `assessment_plan` writes it back more
    reliably under that name.

    Every field's shape (types, nesting, enums) comes from
    :data:`artifact_schemas.ARTIFACT_SCHEMAS`, the sole declaration of an
    artifact's SHAPE — the stage prompt does not restate it as text (see
    ``AgenticStep.task_block``). Two things keep that from forking: where
    ``core/validation.py`` type-checks a field, ``artifact_schemas`` DERIVES
    from it rather than retyping it, and every enum list is typed once in
    ``rulebook.py``, read by both the schema and the ``RULES_*`` prose.
    :attr:`AgenticStep.validate` stays the authority on ACCEPTANCE; this only
    rejects earlier, at the transport boundary, what the parser can see is
    malformed — a wrapped or key-less object, a wrong top-level type, a field
    of the wrong shape.

    ``only`` binds a SUBSET, for a loop resuming a stage that already holds
    some of its artifacts. Defaults to None — every artifact — which is what a
    first attempt gets and what ``tests/fixtures/golden_prompts.json`` pins.
    """
    return [
        _fn(f"submit_{key}",
            f"Submit the {key.replace('_', ' ')} artifact. "
            + ("Required." if is_required else "Optional."),
            _parameters_from(((key, json_type, True),)))
        for key, json_type, is_required in step.submit_fields
        if only is None or key in only
    ]


#: The Qwen tool-call markup, as vLLM's ``qwen3_coder`` parser expects to
#: consume it. We parse it ourselves only when the SERVER did not — see
#: :func:`parse_tool_call_markup`.
_MARKUP_CALL_RE = re.compile(r"<function=([^>\s]+)\s*>(.*?)(?:</function>|\Z)", re.S)
_MARKUP_PARAM_RE = re.compile(r"<parameter=([^>\s]+)\s*>(.*?)(?:</parameter>|\Z)", re.S)


def parse_tool_call_markup(text: str) -> tuple[str, dict] | None:
    """Recover a tool call the serving-side parser left as plain text.

    MEASURED FAILURE (run single_20260831_180940): replies arriving as
    ``<tool_call>\n<function=read_nodes>\n<parameter=node_type>…`` in the
    CONTENT, with an empty ``tool_calls``. The model called the tool correctly;
    the server did not reconstruct it. Left alone, each such reply is an
    "invalid turn" — it costs a turn, earns a protocol nudge, and pushes the
    stage toward giving up for a reason that has nothing to do with the
    model's competence.

    So this is a transport-boundary recovery, the same class as
    :func:`coerce_args`: deterministic, cheap, and applied before anything
    downstream can mistake a serving artifact for a model mistake. Returns
    ``None`` when the text carries no call, which is a real text turn.
    """
    if not text or "<function=" not in text:
        return None
    match = _MARKUP_CALL_RE.search(text)
    if not match:
        return None
    name = match.group(1).strip()
    args = {key.strip(): value.strip()
            for key, value in _MARKUP_PARAM_RE.findall(match.group(2))}
    return name, args


def shape_bad_keys(parameters: dict, args: object) -> list[str]:
    """Declared-structured arguments that arrived as text and would not parse."""
    if not isinstance(args, dict):
        return []
    declared = (parameters or {}).get("properties") or {}
    return [
        key for key, value in args.items()
        if isinstance(value, str)
        and (declared.get(key) or {}).get("type") in ("object", "array")
    ]


def shape_errors(parameters: dict, args: object, keys: list[str] | None = None) -> list[str]:
    """One actionable message per argument that arrived as text.

    MEASURED (run single_20260901_171408): a submit arrived as
    ``needs_analysis:str`` and the model was told "needs_analysis.gaps must be a
    non-empty list" — an error about CONTENT for a problem of SHAPE. It
    resubmitted the same string three times and the stage fell back, and the run
    finished missing a required field. The same happened to
    ``instructional_strategies``, ``instructor_orientation`` and
    ``assessment_tools`` in the two multi arms.

    Reported FIRST, ahead of the validator's own complaints, because a value
    that is text cannot be judged on its contents and telling the model about
    its contents sends it to fix the wrong thing.

    But only when the submit FAILS without them. The caller drops the
    unreadable arguments and validates what is left; if that is a valid
    artifact, the submit is accepted and the drop is recorded rather than
    argued about. MEASURED (run single_20260901_205901, AssessmentDeveloper):
    attempt 2 arrived as ``assessment_tools:list, rubric_criteria:str`` — the
    primary output was correct and the validator would have accepted it — and
    a whole set of good items was thrown away over the criteria beside them.
    ``set_step`` already refuses to gate on a secondary output for exactly that
    reason; this was gating on it one layer up.
    """
    if keys is None:
        keys = shape_bad_keys(parameters, args)
    declared = (parameters or {}).get("properties") or {}
    messages = []
    for key in keys:
        expected = (declared.get(key) or {}).get("type")
        kind = "JSON object" if expected == "object" else "JSON array"
        messages.append(
            f"{key} arrived as text, not as a {kind}. Send it as a real "
            f"{kind} in the tool call's arguments — not as a string containing one.")
    return messages


def parse_tool_call_json(text: str) -> tuple[str, dict] | None:
    """Recover a tool call the model wrote as a JSON OBJECT in its content.

    A third transport shape, alongside a parsed ``tool_calls`` entry and the
    ``<function=…>`` markup: MEASURED (run single_20260901_171408) the model
    answered with ``{"name": "submit", "arguments": {"needs_analysis": …}}`` as
    plain content and no tool call at all, which the loop could only treat as
    prose — a turn spent, and a protocol nudge for a model that had in fact
    called the tool."""
    if not text or '"name"' not in text:
        return None
    parsed = parse_json_response(text, warn=False, salvage=False)
    if not isinstance(parsed, dict):
        return None
    name = str(parsed.get("name") or parsed.get("tool") or "").strip()
    args = parsed.get("arguments")
    if args is None:
        args = parsed.get("args")
    return (name, args if isinstance(args, dict) else {}) if name else None


def coerce_args(parameters: dict, args: object, *, salvaged: list | None = None) -> dict:
    """Parse string-encoded structured arguments back into objects/arrays.

    MEASURED FAILURE this answers (run single_20260831_152628, Qwen3.5 on vLLM
    with ``--tool-call-parser qwen3_coder``): the model called ``submit``
    correctly on every stage of every arm, but each structured argument arrived
    as a STRING holding its JSON — ``{"needs_analysis": "{\"problem_definition\"
    ...}"}`` — so the deterministic validator answered "expected list, got str"
    and every one of the 28 stages was rejected. The
    tool-call parser reconstructs the call, not the value types the schema
    declares; a template-driven parser has no obligation to.

    So the coercion belongs here, at the transport boundary, like
    ``unwrap_section`` at the envelope boundary: applied before anything
    downstream can mistake a transport artifact for a model mistake. A value
    that does not parse is left alone — then it IS a model mistake.

    STRICT ``json.loads`` IS NOT ENOUGH (run single_20260901_205901): the same
    parser that hands a value over as text re-serializes it, and the output is
    not always JSON. Measured, one 4,371-character ``instructional_strategies``
    was double-quoted JSON with a single-quoted element spliced in mid-array,
    so ``json.loads`` failed at character 1,979 and the artifact was charged to
    the model as "arrived as text" — the single-graph arm was rejected 61 times
    on one such value, reached 3 of 6 stages, and scored 0.0 on Analysis and
    Implementation. The tolerant ``parse_json_response`` the plain-text path
    uses returns that value complete, so it is applied here too rather than a
    second salvage being invented.

    ``salvaged`` is an optional sink: each argument name that needed the
    tolerant path is appended, so the RATE is reported per stage
    (``autonomy.args_salvaged``) beside ``markup_recovered`` — a recovery
    nobody counts quietly stops being exceptional.
    """
    if isinstance(args, str):
        # Some parsers hand back the whole argument object as one JSON string.
        parsed = _loads(args, salvaged, "<arguments>")
        if not isinstance(parsed, (dict, list)):
            return {}
        args = parsed
    if not isinstance(args, dict):
        return {}
    declared = (parameters or {}).get("properties") or {}
    coerced: dict = {}
    for key, value in args.items():
        expected = (declared.get(key) or {}).get("type")
        if isinstance(value, str) and expected in ("object", "array"):
            wanted = dict if expected == "object" else list
            parsed = _loads(value, salvaged, key, want_array=(wanted is list))
            coerced[key] = parsed if isinstance(parsed, wanted) else value
        else:
            coerced[key] = value
    return coerced


def _only_text_field(item_schema: dict) -> str:
    """The one required string field beside ``id`` of an ``{id, text}`` item
    schema, or ``""`` when the item is anything richer than that — a bare
    string can stand for a labelled sentence and for nothing more."""
    required = [k for k in (item_schema.get("required") or []) if k != "id"]
    props = item_schema.get("properties") or {}
    if "id" not in (item_schema.get("required") or []) or len(required) != 1:
        return ""
    return required[0] if (props.get(required[0]) or {}).get("type") == "string" else ""


def reshape_args(parameters: dict, args: dict, *, reshaped: list,
                 salvaged: list | None = None) -> dict:
    """A scalar string where the schema declares an ARRAY OF STRINGS becomes
    the one-element list holding it, recursively through the declared shape.

    STRUCTURAL, never authorial: the model's text is kept byte for byte and
    only its container changes. Splitting the string into items instead —
    on newlines, on bullets — would decide where one item ends and the next
    begins, which is writing the artifact. MEASURED (run 14a6b4c7,
    implementation): ``operator_manual.operation_procedures`` arrived as one
    paragraph, the validator answered "expected list, got str" three times,
    the artifact spent its submit budget and the whole stage was regenerated
    — ~100 of the run's 285 calls for a container mismatch the text itself
    never had.

    Separate from :func:`coerce_args` because the two answer different
    questions: that one PARSES a structure the transport flattened to text,
    this one RESHAPES a value the model wrote in the wrong container. A text
    that starts with ``[`` is tried as JSON first and, if it is a list, counts
    as a parse (``salvaged``) rather than a reshape. Every reshaped dotted
    path is appended to ``reshaped`` so the rate is reported
    (``autonomy.args_reshaped``) beside ``args_salvaged``.

    Only ``string`` items are wrapped: an array of objects or integers under a
    scalar string is the model's mistake and stays one. A string where an
    OBJECT is declared is likewise left for the validator.

    The converse case is reshaped too: a bare STRING inside an array whose
    items are declared ``{id, <one text field>}`` becomes that object, the
    string as its text and a positional id (``CON-01`` for ``constraints``).
    MEASURED (run aef73e0a): ``context_analysis.constraints`` arrived as five
    plain sentences, the commit keeps only elements that carry an id, and all
    five were dropped without a word — no constraint nodes, P8 at 0.0 and three
    media selections naming constraints that did not exist. The text is the
    model's; only the container and an id the model never needed to invent
    are the harness's.
    """
    def walk(schema: dict, value: object, path: str) -> object:
        kind = (schema or {}).get("type")
        if kind == "array":
            items = (schema or {}).get("items") or {}
            if isinstance(value, str):
                if items.get("type") != "string" or not value.strip():
                    return value
                if value.lstrip().startswith("["):
                    try:
                        parsed = json.loads(value)
                    except (TypeError, ValueError):
                        parsed = None
                    if isinstance(parsed, list):
                        if salvaged is not None:
                            salvaged.append(path)
                        return parsed
                reshaped.append(path)
                return [value]
            if isinstance(value, list) and items.get("type") == "object":
                text_field = _only_text_field(items)
                out = []
                for i, one in enumerate(value):
                    if isinstance(one, str) and one.strip() and text_field:
                        reshaped.append(f"{path}[{i}]")
                        prefix = path.rsplit(".", 1)[-1][:3].upper()
                        one = {"id": f"{prefix}-{i + 1:02d}", text_field: one}
                    out.append(walk(items, one, f"{path}[{i}]"))
                return out
            return value
        if kind == "object" and isinstance(value, dict):
            props = (schema or {}).get("properties") or {}
            extra = (schema or {}).get("additionalProperties")
            out = {}
            for key, one in value.items():
                sub = props.get(key) or (extra if isinstance(extra, dict) else None)
                out[key] = walk(sub, one, f"{path}.{key}" if path else key) if sub else one
            return out
        return value

    if not isinstance(args, dict):
        return args
    args = _unwrap_self_named(parameters, args, salvaged)
    args = _fold_siblings(parameters, args, reshaped)
    return walk({"type": "object", **(parameters or {})}, args, "")


def _fold_siblings(parameters: dict, args: dict, reshaped: list) -> dict:
    """``{"system_check": {"checklist": [...]}, "technical_validation": ...,
    "contingency_plans": ...}`` means one ``system_check`` with three fields.

    A tool that takes ONE object artifact is sometimes called with that object
    closed after its first field and the rest of its fields written beside it,
    one level too high. The content is whole and the model's; only the closing
    brace is early. MEASURED (runs aef73e0a, 40856c96, b8576814, 53a9cd1a):
    ``system_check`` in three of four and ``operator_manual`` in three of four
    arrived this way — the first field inside, ``technical_validation`` /
    ``contingency_plans`` / ``operation_procedures`` / ``escalation_process``
    outside — and each was refused as "required field is missing or empty" for
    fields the same call was carrying.

    Folded only when it cannot be anything else: the tool declares exactly one
    field, that field is an object, and a sibling key is one of ITS declared
    properties that the object does not already hold. Anything else beside the
    artifact is left where the model put it."""
    declared = (parameters or {}).get("properties") or {}
    if len(declared) != 1 or not isinstance(args, dict):
        return args
    (name, schema), = declared.items()
    inner_fields = (schema or {}).get("properties") or {}
    artifact = args.get(name)
    if (schema or {}).get("type") != "object" or not isinstance(artifact, dict):
        return args
    stray = [key for key in args if key != name and key in inner_fields
             and artifact.get(key) in (None, "", [], {})]
    if not stray:
        return args
    reshaped.extend(f"{name}.{key} (written beside {name})" for key in stray)
    folded = {**artifact, **{key: args[key] for key in stray}}
    return {name: folded, **{k: v for k, v in args.items() if k != name and k not in stray}}


def _unwrap_self_named(parameters: dict, args: dict, salvaged: list | None) -> dict:
    """``{"operator_manual": {"operator_manual": {...}}}`` means
    ``{"operator_manual": {...}}``.

    A model told to send the artifact under its own name sometimes names it
    twice. The inner key is not a field of the artifact, so the gate would
    reject it — or, dropped as undeclared, take the whole artifact with it.
    MEASURED (run 1c0a4e81): ``operator_manual`` on its third and last submit,
    and ``improvement_plan``. Unwrapped only when the artifact does not itself
    declare a field by that name; fields written beside the inner copy win."""
    declared = (parameters or {}).get("properties") or {}
    out = dict(args)
    for key, value in args.items():
        schema = declared.get(key) or {}
        if schema.get("type") != "object" or not isinstance(value, dict):
            continue
        inner = value.get(key)
        if not isinstance(inner, dict) or key in (schema.get("properties") or {}):
            continue
        out[key] = {**inner, **{k: v for k, v in value.items() if k != key}}
        if salvaged is not None:
            salvaged.append(f"{key} (named twice)")
    return out


def _loads(text: str, salvaged: list | None = None, name: str = "",
           *, want_array: bool = False) -> object:
    """Strict JSON first, then the tolerant parser for the DECLARED shape.

    Order matters: a well-formed payload must never take the salvage path,
    because salvage can only ever be a best effort and a run where it silently
    handles the ordinary case is a run whose transport health is unmeasurable.

    The shape matters just as much. ``parse_json_response`` returns a dict from
    every path, including one that decodes the first complete object and stops
    — so on a malformed ARRAY it hands back element one. MEASURED (a 2B
    submit): an array of three assessment items closing ``..."]}`` instead of
    ``..."}]`` came back as a single dict holding item 1, and only the caller's
    type check kept it from being committed as the whole set. An argument the
    schema declares as an array is salvaged as an array.
    """
    try:
        return json.loads(text)
    except (TypeError, ValueError):
        pass
    if not want_array:
        # One structural repair before the tolerant parser, which would keep
        # only the fields BEFORE the break: an array that lost its `]`.
        try:
            repaired = json.loads(close_unclosed_arrays(text))
        except (TypeError, ValueError):
            repaired = None
        if isinstance(repaired, dict) and repaired:
            if salvaged is not None:
                salvaged.append(name)
            return repaired
    if want_array:
        items, dropped = parse_json_array(text)
        if not items:
            return None
        if salvaged is not None:
            # The dropped count travels in the name, so a partial recovery
            # cannot be read as a clean one: recovering 2 of 3 and saying
            # nothing is the same failure as recovering 1.
            salvaged.append(f"{name} (-{dropped})" if dropped else name)
        return items
    # warn=False: a near-JSON tool argument is the case this function exists
    # for, not something to shout about in the run log.
    recovered = parse_json_response(text, warn=False)
    if not recovered:
        return None
    if salvaged is not None:
        salvaged.append(name)
    return recovered


def _fn(name: str, description: str, parameters: dict) -> dict:
    return {"type": "function",
            "function": {"name": name, "description": description, "parameters": parameters}}


def _enum_param(field: str, values: tuple[str, ...], description: str) -> dict:
    return {"type": "object",
            "properties": {field: {"type": "string", "enum": list(values),
                                   "description": description}},
            "required": [field]}


def tool_specs(step: "AgenticStep", *, graph_mode: bool = True,
               retrieval_available: bool = False,
               only: tuple[str, ...] | None = None) -> list[dict]:
    """The tools bound for this step, in OpenAI function-calling shape.

    Only tools whose allowlists are non-empty are bound -- an offered tool that
    can only answer "ERROR" costs a small model a turn to discover that."""
    specs: list[dict] = []
    if graph_mode:
        if getattr(step, "state_tool", True) and (step.readable_types or step.docket):
            specs.append(_fn(STATE_TOOL, _state_description(step),
                             {"type": "object", "properties": {}}))
        if step.readable_types:
            specs.append(_fn(
                "read_node",
                "Read artifacts from the design graph in full. Ask for every id "
                "you need in ONE call — each call costs a turn.",
                {"type": "object",
                 "properties": {"ids": {
                     "type": "array",
                     "items": {"type": "string"},
                     "description": "The node ids, e.g. ['ILO-01', 'ILO-02']."}},
                 "required": ["ids"]}))
    else:
        if step.readable_docs:
            specs.append(_fn(
                "list_documents",
                "Which documents earlier steps have written and you can read.",
                {"type": "object", "properties": {}}))
            specs.append(_fn(
                "read_document",
                "Read one document an earlier step wrote, in full.",
                _enum_param("key", step.readable_docs, "Which document to read.")))
    if retrieval_available:
        specs.append(_fn(
            "retrieve",
            "Fetch external domain material (templates, conventions, examples).",
            {"type": "object",
             "properties": {"query": {"type": "string",
                                      "description": "What to fetch, specific."}},
             "required": ["query"]}))
    specs += submit_specs(step, only)
    return specs


#: The one list-shaped read of the graph arm; see ``alignment_state``.
STATE_TOOL = "read_alignment_state"


def _state_description(step) -> str:
    """What ``read_alignment_state`` covers FOR THIS ROLE — the scope is fixed
    by the binding and stated here, so the tool takes no arguments and cannot
    be asked for something out of scope."""
    if not getattr(step, "name", ""):
        return ("The alignment state of the stage you are ON — the first one not yet "
                "complete; the result's first line names it: the artifacts it builds on "
                "(id, key fields, label), what its output must still close, and the open "
                "issues in what you have committed to it. Takes no arguments. Call it when "
                "a stage comes up, and again after each submit.")
    closes = ", ".join(alignment.REGISTRY[rid].label
                       for rid in (step.docket or {}).get("gaps", ()))
    return (f"The alignment state of the {step.name} stage: the "
            f"{', '.join(step.readable_types) or 'earlier'} artifacts it builds on (id, key "
            "fields, label), what your output must still close"
            + (f" ({closes})" if closes else "")
            + ", and the open issues in what you have committed. Takes no arguments. "
              "Call it before you write, and again after each submit.")


def react_specs(steps: tuple, done: frozenset, *, graph_mode: bool = True,
                retrieval_available: bool = False) -> list[dict]:
    """Tools for the ONE agent that runs the whole brief itself.

    Two differences from :func:`tool_specs`, both of which are what makes the
    single arm a ReAct loop rather than six loops in a trench coat:

    * the read allowlists are the UNION over every step, because this agent is
      not scoped to a stage — it decides what to look at;
    * there is one ``submit_<stage>`` per stage NOT yet complete, so the agent
      chooses what to work on and in what order. The menu shrinks as stages
      land: that is state being reported, not the harness steering. When the
      menu is empty the job is done, which is also the loop's exit condition.

    A submit is ADDITIVE and may be called again for the same stage: that is
    what lets the agent split a large family across several calls instead of
    trying to fit it under one 8192-token completion. The rule is stated in the
    prompt too — an affordance the agent is not told about is not an option it
    has, and any output lost for want of it would be our design failing, not
    the agent choosing."""
    read_types: tuple[str, ...] = ()
    read_relations: tuple[str, ...] = ()
    read_docs: tuple[str, ...] = ()
    for step in steps:
        read_types += tuple(t for t in step.readable_types if t not in read_types)
        read_relations += tuple(r for r in step.relations if r not in read_relations)
        read_docs += tuple(d for d in step.readable_docs if d not in read_docs)

    union = _ReadScope(read_types, read_relations, read_docs)
    specs = tool_specs(union, graph_mode=graph_mode, retrieval_available=retrieval_available)
    # Lazy: `fanout` imports this module for the Developer tier's own
    # submit specs, so a module-level import here would close the loop.
    from .fanout import SPECS as _FANOUT

    for step in steps:
        if step.name in done:
            continue
        # A fan-out family's stage submit carries only the PLAN, because in the
        # multi arm its items come from Developers. This agent has no
        # Developers: it writes the items itself, so its submit has to accept
        # them. That is the axis, not a shortcut — "single agent" means one
        # agent does the work, including the part multi delegates.
        spec = _FANOUT.get(step.name)
        params = (submit_parameters(step) if spec is None else _parameters_from(
            tuple(step.submit_fields)
            + tuple((o.schema_key, "array", False) for o in spec.outputs)))
        specs.append(_fn(
            f"submit_{step.name}",
            f"Submit {step.name} artifacts. You may call this again to add more.",
            params))
    return specs


@dataclass(frozen=True)
class _ReadScope:
    """The union allowlist, in the shape ``tool_specs`` reads. No submit
    fields: ``react_specs`` appends a per-stage submit instead."""

    readable_types: tuple[str, ...]
    relations: tuple[str, ...]
    readable_docs: tuple[str, ...]
    submit_fields: tuple = ()
    #: No stage of its own: the state tool is bound with the stage-agnostic
    #: description, and the loop serves it for whichever stage is current.
    name: str = ""
    docket: dict = field(default_factory=dict)
    state_tool: bool = True


def tool_names(specs: list[dict]) -> tuple[str, ...]:
    return tuple(spec["function"]["name"] for spec in specs)


def arg_shape(args: object) -> str:
    """``key:type`` for each argument, for the rejection record."""
    if not isinstance(args, dict):
        return type(args).__name__
    return ",".join(f"{k}:{type(v).__name__}" for k, v in sorted(args.items()))[:160]


def spec_parameters(specs: list[dict], name: str) -> dict:
    """The declared parameter schema for one bound tool, or ``{}`` for a name we
    never offered (which the dispatcher answers with an ERROR observation)."""
    for spec in specs:
        function = spec.get("function") or {}
        if function.get("name") == name:
            return function.get("parameters") or {}
    return {}


def merge_specs(seen: list, bound: list) -> list:
    """Tool schemas in first-seen order, deduped by name."""
    by_name = {(spec.get("function") or {}).get("name"): spec for spec in seen}
    merged = list(seen)
    for spec in bound:
        name = (spec.get("function") or {}).get("name")
        if name not in by_name:
            by_name[name] = spec
            merged.append(spec)
    return merged


def tool_menu(step: "AgenticStep", *, retrieval_available: bool = False,
              graph_mode: bool = True) -> str:
    """A one-line-per-tool summary, DERIVED from the binding.

    With native tool calling the binding (:func:`tool_specs`) is what the model
    can actually call; this block tells it what each tool is for and which
    allowlist values are legal. It is rendered from those same specs, so the
    two cannot disagree about which tools exist.

    A menu written by hand drifted (it announced a single ``submit`` after
    the per-artifact split, and ``ToolLoop._submit_alias`` was quietly
    rescuing the result); one computed from the binding cannot.
    """
    return "\n".join(
        _menu_line(spec) for spec in tool_specs(
            step, graph_mode=graph_mode, retrieval_available=retrieval_available))


def _menu_line(spec: dict) -> str:
    """``- name (param: one of a, b) — description``, from the spec itself."""
    function = spec.get("function") or {}
    properties = ((function.get("parameters") or {}).get("properties") or {})
    arguments = []
    for name, schema in properties.items():
        enum = schema.get("enum")
        arguments.append(f"{name}: one of {', '.join(enum)}" if enum else name)
    signature = f" ({'; '.join(arguments)})" if arguments else ""
    return f"- {function.get('name', '?')}{signature} — {function.get('description', '')}"

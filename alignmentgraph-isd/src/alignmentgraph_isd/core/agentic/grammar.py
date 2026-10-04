"""The artifact contract, tightened with THIS design's own vocabulary.

``artifact_schemas.ARTIFACT_SCHEMAS`` declares an artifact's SHAPE once, for
every run. What it cannot say is which ids exist in the design being written:
that an item's ``aligned_objective`` must be one of the objectives the
outcomes stage committed, that a session guide may schedule only the
activities its block was handed, that a light work set writes exactly the
rows its assignment fixed. Those facts are checked after the submit
(``fanout.reference_errors``, ``fanout.item_level_errors``,
``dev_plans.trim_to_quota``) and were, until now, told to the model in prose
only — which a small model follows some of the time. MEASURED (run
``train_10_benchmark_Qwen3.5-2B_t1_20260924_125606``): 30 of 51 submit
rejections were a reference that resolved to nothing or a level below the
objective's, and every one cost a turn and a share of the submit budget.

This module writes the same facts INTO the schema: every reference becomes an
``enum`` over the ids that exist, every fixed row of a light assignment a
``const``, every stated count a ``minItems``/``maxItems``. The schema is then
what the constrained pass (``turn.constrained_pass``) decodes under, and what
the bound ``submit_*`` tool declares — so a backend that enforces a tool's
parameters gets the same contract the recovery pass does.

Three rules keep this an engineering step and not a second validator:

* **It only ever TIGHTENS.** A value the base schema accepts and this one
  refuses is one the submit-time check would refuse anyway
  (``tests/test_grammar.py``). A pool that is empty — the objectives before
  the outcomes stage wrote them — leaves the field as the base declares it,
  exactly where ``reference_errors`` stands down.
* **It reads the design, never the substrate.** Everything here goes through
  the substrate-neutral readers in :mod:`fanout` (``known_ids``,
  ``objective_levels``, ``course_modules``, …), so the same design yields the
  same schema on an ``AlignmentGraph`` and a ``ProseStore``, and nothing the
  ``context_mode`` axis ablates — relations, coverage, the docket — is read.
  The constrained pass therefore sits on the transport, not on either axis.
* **It decides nothing.** Which objective an item measures, which activity a
  session delivers, what an activity says: the model's, still. The schema
  narrows a reference to the ids that exist and a level to the ones the
  objective's own declared level allows, and that is the whole of it.

Constrained decoding fixes STRUCTURE — a wrong-shaped, key-less or dangling
artifact — and not semantics: an activity naming a real objective it has
nothing to do with still passes, and the relation checks still measure that.
The literature is explicit that this is the line (constrained decoding on
small models removes structural failures and leaves a scale-dependent
semantic gap), and the panel this study reports reads the semantic side.

The keywords used are the ones the serving stack's grammar backend compiles:
``enum``, ``const``, ``prefixItems`` with ``items: false``, ``minItems`` /
``maxItems``, ``maxLength`` on its own, ``additionalProperties``.
:func:`xgrammar_safe` is the guard that nothing outside that set reaches a
request; ``uniqueItems`` in particular is not compiled, which is why a repeated
task id is deduplicated at commit (``dev_plans.dedupe_task_ids``) rather than
refused by the grammar.
"""
from __future__ import annotations

import copy
import json
from dataclasses import dataclass, field

from .. import dev_plans
from ..alignment_graph import NodeType
from ..trajectory import ORCHESTRATOR
from .artifact_schemas import ARTIFACT_SCHEMAS, required_floor
from .fanout import (
    constraints,
    course_modules,
    known_ids,
    media_selections,
    objective_levels,
    topics,
)

#: Keywords the grammar backend does not compile. A schema carrying one is a
#: request the server refuses whole, so it is caught here — in the tests that
#: build every schema this module can produce — and never at run time.
UNSUPPORTED_KEYWORDS = frozenset({"uniqueItems", "contains", "multipleOf",
                                  "minContains", "maxContains", "dependentRequired",
                                  "dependentSchemas", "if", "then", "else",
                                  "unevaluatedProperties", "unevaluatedItems"})


@dataclass(frozen=True)
class Vocabulary:
    """Every id and every fact of a design that a schema may name, read once
    per binding from either substrate."""

    objectives: tuple[str, ...] = ()
    #: objective id -> its declared Bloom level (lower-case, "" when unreadable)
    levels: dict = field(default_factory=dict)
    modules: tuple[dict, ...] = ()
    #: the assessment TASKS of the plan, flat, each with its module
    tasks: tuple[dict, ...] = ()
    activities: tuple[str, ...] = ()
    materials: tuple[str, ...] = ()
    topics: tuple[str, ...] = ()
    constraints: tuple[str, ...] = ()
    media: tuple[dict, ...] = ()
    #: the course's length in instructional hours, 0.0 when the brief does not
    #: say — the module ceiling's third bound
    course_hours: float = 0.0

    @classmethod
    def of(cls, state, *, course_hours: float = 0.0) -> "Vocabulary":
        """Read from ``state`` as a HARNESS probe — under the orchestrator on
        the graph substrate (``AlignmentGraph.reads_as``), like every other
        read the harness makes inside an agent's scope — so binding a schema
        is never recorded as the agent having read the design."""
        if state is None:
            return cls(course_hours=course_hours)
        reads_as = getattr(state, "reads_as", None)
        if reads_as is None:
            return cls._read(state, course_hours)
        with reads_as(ORCHESTRATOR):
            return cls._read(state, course_hours)

    @classmethod
    def _read(cls, state, course_hours: float) -> "Vocabulary":
        ids = known_ids(state)
        plan_tasks = tuple(
            t for t in dev_plans.plan_tasks(_plan(state)) if isinstance(t.get("id"), str))
        return cls(
            objectives=tuple(ids.get(NodeType.OBJECTIVE, ())),
            levels=objective_levels(state),
            modules=tuple(m for m in course_modules(state) if m.get("id")),
            tasks=plan_tasks,
            activities=tuple(ids.get(NodeType.ACTIVITY, ())),
            materials=tuple(ids.get(NodeType.MATERIAL, ())),
            topics=tuple(str(t.get("id")) for t in topics(state) if t.get("id")),
            constraints=tuple(str(c.get("id")) for c in constraints(state) if c.get("id")),
            media=tuple(m for m in media_selections(state) if m.get("id")),
            course_hours=course_hours,
        )

    @property
    def module_ids(self) -> tuple[str, ...]:
        return tuple(str(m["id"]) for m in self.modules)

    @property
    def task_ids(self) -> tuple[str, ...]:
        return tuple(str(t["id"]) for t in self.tasks)


def _plan(state) -> dict:
    if hasattr(state, "element_nodes"):
        node = state.get_node(state.section_id(NodeType.ASSESSMENT_PLAN))
        return dict((node or {}).get("data") or {})
    return dict(state.get("assessment_plan") or {})


# ── the public surface ──────────────────────────────────────────────────────

def tighten_specs(specs: list[dict], vocab: Vocabulary, *, work_set=None,
                  mode: str = "full") -> list[dict]:
    """The bound tool specs with every ``submit_*`` tool's parameters
    tightened. Read tools pass through untouched; the base specs are not
    mutated (they are what the golden fixture pins)."""
    out: list[dict] = []
    for spec in specs:
        function = spec.get("function") or {}
        name = str(function.get("name") or "")
        if not name.startswith("submit_"):
            out.append(spec)
            continue
        tightened = dict(function)
        tightened["parameters"] = tighten_parameters(
            function.get("parameters") or {}, vocab, work_set=work_set, mode=mode)
        out.append({**spec, "function": tightened})
    return out


def tighten_parameters(params: dict, vocab: Vocabulary, *, work_set=None,
                       mode: str = "full") -> dict:
    """A submit tool's ``parameters`` object, each artifact property replaced
    by :func:`artifact_property` and every object stamped open."""
    properties = dict(params.get("properties") or {})
    required = list(params.get("required") or [])
    defs: dict = dict(params.get("$defs") or {})
    for key, prop in list(properties.items()):
        if key not in ARTIFACT_SCHEMAS:
            continue
        json_type = "array" if (prop or {}).get("type") == "array" else "object"
        tightened = artifact_property(
            key, json_type, key in required, vocab, work_set=work_set, mode=mode)
        # A shared sub-schema is declared ONCE at the root, where `$ref`
        # resolves it: the assessment plan names its task schema per module
        # and a copy per module made the spec twice its size (measured: 10k
        # characters for five modules against 4.5k declared), which is
        # prompt the transcript then has to make room for.
        defs.update(tightened.pop("$defs", {}) if isinstance(tightened, dict) else {})
        properties[key] = tightened
    out = {**params, "type": "object", "properties": properties, "required": required}
    if defs:
        out["$defs"] = defs
    return _open(out)


def artifact_property(key: str, json_type: str, is_required: bool, vocab: Vocabulary, *,
                      work_set=None, mode: str = "full") -> dict:
    """The schema of one submit field — the artifact under ``key`` — tightened.

    ``json_type`` says whether the field is the artifact itself (``object``) or
    a list of them (``array``), the same distinction ``tools._parameters_from``
    draws from ``AgenticStep.submit_fields``."""
    base = copy.deepcopy(ARTIFACT_SCHEMAS[key])
    builder = _BUILDERS.get(key)
    if json_type != "array":
        shape = builder(base, vocab, work_set, mode) if builder else base
        return required_floor(shape) if is_required else shape
    rows = builder(base, vocab, work_set, mode) if builder else None
    if isinstance(rows, list):
        # A fixed assignment: one schema per row, in the row's order, and
        # nothing beside them.
        return {"type": "array", "prefixItems": rows, "items": False,
                "minItems": len(rows), "maxItems": len(rows)}
    item = rows if isinstance(rows, dict) else base
    shape: dict = {"type": "array", "items": item}
    count = _stated_count(key, work_set, vocab)
    if count:
        shape["minItems"] = shape["maxItems"] = count
    if key == "course_modules" and vocab.objectives:
        shape["maxItems"] = dev_plans.module_ceiling(
            len(vocab.objectives), len(vocab.topics), vocab.course_hours)
    return required_floor(shape) if is_required else shape


def xgrammar_safe(schema: object) -> list[str]:
    """Every keyword in ``schema`` the grammar backend would refuse, as
    ``path: keyword`` strings; empty when the schema compiles."""
    found: list[str] = []

    def walk(node: object, path: str) -> None:
        if isinstance(node, dict):
            for kw, value in node.items():
                if kw in UNSUPPORTED_KEYWORDS:
                    found.append(f"{path or '$'}: {kw}")
                if kw == "pattern" and ("minLength" in node or "maxLength" in node):
                    found.append(f"{path or '$'}: pattern with a length bound")
                walk(value, f"{path}/{kw}")
        elif isinstance(node, list):
            for index, value in enumerate(node):
                walk(value, f"{path}[{index}]")

    walk(schema, "")
    return found


# ── per-artifact builders ───────────────────────────────────────────────────
# Each takes the base (item) schema, the vocabulary, the work set (None for a
# stage agent and for the single arm) and the development mode, and returns
# either the tightened item schema (a dict) or, for a fixed assignment, one
# schema per row (a list). A builder never adds a field the base does not
# declare and never widens one.

def _enum(values: tuple[str, ...]) -> dict | None:
    values = tuple(dict.fromkeys(str(v) for v in values if str(v).strip()))
    return {"type": "string", "enum": list(values)} if values else None


def _ref(prop: dict, values: tuple[str, ...]) -> dict:
    """A string field narrowed to ``values``; unchanged when there are none."""
    narrowed = _enum(values)
    return {**prop, **narrowed} if narrowed else prop


def _ref_list(prop: dict, values: tuple[str, ...]) -> dict:
    narrowed = _enum(values)
    return {**prop, "items": narrowed} if narrowed else prop


def _levels_from(level: str) -> tuple[str, ...]:
    """Bloom levels at or above ``level``; all six when it is unreadable."""
    index = dev_plans._level_index(level)
    return dev_plans.BLOOM_ORDER[index:] if index is not None else dev_plans.BLOOM_ORDER


def _with(base: dict, **props: dict) -> dict:
    out = dict(base)
    out["properties"] = {**base.get("properties", {}), **props}
    return out


def _course_modules(base: dict, vocab: Vocabulary, work_set, mode: str) -> dict:
    props = base["properties"]
    return _with(base,
                 objectives=_ref_list(props["objectives"], vocab.objectives),
                 covers_topics=_ref_list(props["covers_topics"], vocab.topics))


def _assessment_plan(base: dict, vocab: Vocabulary, work_set, mode: str) -> dict:
    props = base["properties"]
    set_schema = props["sets"]["items"]
    task_schema = set_schema["properties"]["assessment_tasks"]["items"]
    task_schema = _with(task_schema, covers_objectives=_ref_list(
        task_schema["properties"]["covers_objectives"], vocab.objectives))
    out = dict(base)
    if vocab.modules:
        # ONE set per module, in course order, each holding at most the tasks
        # the module's allowance gives it — the ceiling the plan is told
        # (`checks.blueprint_consistency`, kind `too_many_tasks`), in the
        # shape of the request. The task schema is written once, under
        # `$defs` (hoisted to the root by `tighten_parameters`), and each
        # row refers to it.
        out["$defs"] = {"assessment_task": task_schema}
        rows = []
        for index, module in enumerate(vocab.modules):
            tasks = {**set_schema["properties"]["assessment_tasks"],
                     "items": {"$ref": "#/$defs/assessment_task"}, "minItems": 1,
                     "maxItems": dev_plans.task_allowance(module, index)}
            rows.append(_with(set_schema,
                              module_id={**set_schema["properties"]["module_id"],
                                         "const": str(module["id"])},
                              assessment_tasks=tasks))
        out["properties"] = {**props, "sets": {
            "type": "array", "prefixItems": rows, "items": False,
            "minItems": len(rows), "maxItems": len(rows)}}
    else:
        out["properties"] = {**props, "sets": {
            **props["sets"], "items": _with(
                set_schema, module_id=_ref(set_schema["properties"]["module_id"],
                                           vocab.module_ids),
                assessment_tasks={**set_schema["properties"]["assessment_tasks"],
                                  "items": task_schema})}}
    if vocab.objectives:
        # Keyed by the objectives that exist and nothing else: a key here that
        # names no objective is a promise about nothing (`plan_coverage`).
        # NOT required per objective: a promise the decoder forces is one the
        # blueprint does not keep — measured with every objective required,
        # 39 `unassessed_pair` findings over ten runs, and the Designer's
        # repair turns spent on them; which objectives the plan promises stays
        # the model's, and `objective_without_set` reports the ones it leaves.
        timing = props["lo_coverage_targets"]["additionalProperties"]
        out["properties"]["lo_coverage_targets"] = {
            "type": "object",
            "description": props["lo_coverage_targets"].get("description", ""),
            "properties": {lo: {**timing, "minItems": 1} for lo in vocab.objectives},
            "minProperties": 1,
            "additionalProperties": False,
        }
    return out


def _assessment_tools(base: dict, vocab: Vocabulary, work_set, mode: str):
    props = base["properties"]
    rows = [r for r in ((work_set.payload.get("assigned_items") if work_set else None) or [])
            if isinstance(r, dict)]
    if not rows:
        return _with(base,
                     aligned_objective=_ref(props["aligned_objective"], vocab.objectives),
                     task_id=_ref(props["task_id"], vocab.task_ids))
    out = []
    for row in rows:
        fixed: dict = {
            "aligned_objective": {**props["aligned_objective"], "const": str(row["objective"])},
            "plan_category": {**props["plan_category"], "const": str(row["plan_category"])},
            "required_cognitive_process": {
                **props["required_cognitive_process"],
                "enum": list(_levels_from(str(row.get("level") or "")))},
        }
        if row.get("task_id"):
            fixed["task_id"] = {**props["task_id"], "const": str(row["task_id"])}
        if row.get("type"):
            fixed["type"] = {**props["type"], "const": str(row["type"])}
        out.append(_with(base, **fixed))
    return out


def _learning_activities(base: dict, vocab: Vocabulary, work_set, mode: str):
    props = base["properties"]
    task_ids = tuple(str(t) for t in (
        (work_set.payload.get("assessment_task_ids") if work_set else None) or vocab.task_ids))
    common = {
        "aligned_objectives": _ref_list(props["aligned_objectives"], vocab.objectives),
        "prepares_for_assessment": _ref_list(props["prepares_for_assessment"], task_ids),
        "module_id": _ref(props["module_id"], vocab.module_ids),
    }
    if task_ids:
        # Required whenever there is a task to name (``fanout.required_refs``):
        # a pass that may leave it empty writes it empty.
        common["prepares_for_assessment"] = {**common["prepares_for_assessment"], "minItems": 1}
        base = {**base, "required": list(dict.fromkeys(
            [*(base.get("required") or ()), "prepares_for_assessment"]))}
    rows = [r for r in ((work_set.payload.get("assigned_activities") if work_set else None) or [])
            if isinstance(r, dict)]
    if not rows:
        return _with(base, **common)
    module = work_set.module_id if work_set else ""
    out = []
    for row in rows:
        fixed = dict(common)
        lo = str(row.get("objective") or "")
        if lo:
            # The row's objective FIRST; the block may name more of its own
            # objectives after it. `contains` is not compiled, and this is the
            # same fact in a form that is.
            fixed["aligned_objectives"] = {
                **props["aligned_objectives"], "prefixItems": [{"const": lo}],
                **({"items": _enum(vocab.objectives)} if vocab.objectives else {}),
                "minItems": 1}
        if module:
            fixed["module_id"] = {**props["module_id"], "const": module}
        fixed["learner_cognitive_process"] = {
            **props["learner_cognitive_process"],
            "enum": list(_levels_from(str(row.get("level") or "")))}
        out.append(_with(base, **fixed))
    return out


def _media_selections(base: dict, vocab: Vocabulary, work_set, mode: str) -> dict:
    props = base["properties"]
    return _with(base,
                 for_modules=_ref_list(props["for_modules"], vocab.module_ids),
                 respects_constraints=_ref_list(props["respects_constraints"],
                                                vocab.constraints))


def _learner_materials(base: dict, vocab: Vocabulary, work_set, mode: str) -> dict:
    props = base["properties"]
    fixed: dict = {"linked_module": _ref(props["linked_module"], vocab.module_ids)}
    media = [m for m in ((work_set.payload.get("media_selections") if work_set else None) or [])
             if isinstance(m, dict)]
    types = tuple(str(m.get("media_type") or "").strip().lower() for m in media)
    if types:
        # The types THIS module chose (`render_material_set` names the same
        # list): P6 holds a material to the media selection it realizes.
        fixed["type"] = _ref(props["type"], types)
    if work_set and work_set.module_id:
        fixed["linked_module"] = {**props["linked_module"], "const": work_set.module_id}
    # A light material's DEPTH is told (`dev_plans.LIGHT_MATERIAL_OUTLINE_CHARS`,
    # in the assignment's note) and never decoded: a `maxLength` on `content`
    # is a hard stop the decoder enforces mid-word — measured, seven of ten
    # runs shipped materials of exactly the cap, cut mid-sentence. `mode` is
    # accepted so every builder has one signature.
    return _with(base, **fixed)


def _session_guides(base: dict, vocab: Vocabulary, work_set, mode: str) -> dict:
    props = base["properties"]
    activities, materials = (dev_plans._scheduled(work_set) if work_set
                             else (list(vocab.activities), list(vocab.materials)))
    return _with(base,
                 activity_ids=_ref_list(props["activity_ids"], tuple(activities)),
                 material_ids=_ref_list(props["material_ids"], tuple(materials)))


_BUILDERS = {
    "course_modules": _course_modules,
    "assessment_plan": _assessment_plan,
    "assessment_tools": _assessment_tools,
    "learning_activities": _learning_activities,
    "media_selections": _media_selections,
    "learner_materials": _learner_materials,
    "session_guides": _session_guides,
}


def _stated_count(key: str, work_set, vocab: Vocabulary) -> int:
    """How many of ``key`` a work set was told to write, or 0 when its
    assignment states no count (a stage agent, the single arm's own batches,
    a session block whose session count is the writer's)."""
    if work_set is None:
        return 0
    payload = work_set.payload
    if key == "assessment_tools" and work_set.pairs:
        return dev_plans._expected_items(payload.get("expected_items"), len(work_set.pairs))
    if key == "learning_activities":
        return int(payload.get("expected_activities") or 0)
    if key == "learner_materials":
        media = payload.get("media_selections") or []
        return dev_plans._expected_materials(payload.get("expected_materials"), len(media))
    return 0


#: The pass-2 decoder's backstops, before the budget: the longest string and
#: the longest list it may write where the schema states no bound of its own.
DECODER_MAX_STRING = 6000
DECODER_MAX_ITEMS = 20
#: What a backstop is never shrunk below: a string still holds a sentence, a
#: list still holds four entries (or its own ``minItems``) — a multiple-choice
#: item's options, a rubric's criteria.
DECODER_MIN_STRING = 80
DECODER_MIN_ITEMS = 4
#: Characters per completion token the budget assumes. Pessimistic on purpose:
#: the budget is what guarantees the decoder can END before the cap, and an
#: estimate that is too generous is exactly the reply that never closes.
DECODER_CHARS_PER_TOKEN = 2.5
#: Share of the completion cap the artifact may take; the rest is the
#: reasoning prefix and the JSON's own whitespace.
DECODER_CAP_SHARE = 0.9
#: How many entries an open map (``additionalProperties`` with a value
#: schema) is assumed to hold. JSON Schema can bound it (``maxProperties``) but
#: the grammar backend is not relied on for it, so the estimate carries it.
DECODER_OPEN_MAP_ENTRIES = 12


def decoder_budget_chars(completion_tokens: int) -> int:
    """The characters one constrained pass may write, from the completion cap
    the client sends."""
    return int((completion_tokens or 8192) * DECODER_CAP_SHARE * DECODER_CHARS_PER_TOKEN)


def worst_case_chars(schema: object, root: object | None = None) -> int:
    """An upper bound on the serialized JSON a decoder may emit under
    ``schema``: every string at its ``maxLength``, every list at its
    ``maxItems``, every declared property present. Unbounded means a number far
    past any cap, so an unbudgeted schema never passes for a budgeted one."""
    root = schema if root is None else root
    if not isinstance(schema, dict):
        return 0
    if "$ref" in schema:
        name = str(schema["$ref"]).rsplit("/", 1)[-1]
        return worst_case_chars(((root or {}).get("$defs") or {}).get(name, {}), root)
    if "const" in schema:
        return len(json.dumps(schema["const"], ensure_ascii=False))
    if "enum" in schema:
        return max((len(json.dumps(v, ensure_ascii=False)) for v in schema["enum"]), default=2)
    kind = schema.get("type")
    unbounded = 10 ** 9
    if kind == "string":
        return schema.get("maxLength", unbounded) + 2
    if kind in ("integer", "number"):
        return 16
    if kind == "boolean":
        return 5
    if kind == "array":
        prefix = schema.get("prefixItems")
        fixed = sum(worst_case_chars(one, root) + 1 for one in prefix) if isinstance(prefix, list) else 0
        if schema.get("items") is False:
            return fixed + 2
        rest = schema.get("maxItems", unbounded) - (len(prefix) if isinstance(prefix, list) else 0)
        return fixed + max(rest, 0) * (worst_case_chars(schema.get("items") or {}, root) + 1) + 2
    if kind == "object":
        total = sum(len(json.dumps(k, ensure_ascii=False)) + 1 + worst_case_chars(v, root) + 1
                    for k, v in (schema.get("properties") or {}).items())
        extra = schema.get("additionalProperties")
        if isinstance(extra, dict):
            total += DECODER_OPEN_MAP_ENTRIES * (40 + worst_case_chars(extra, root))
        elif extra is not False:
            return unbounded
        return total + 2
    return unbounded


def for_decoder(schema: object, *, budget_chars: int | None = None) -> object:
    """The schema the CONSTRAINED PASS decodes under: every object CLOSED
    (``additionalProperties: false``) except an open map, every string and
    list with no bound of its own given one, and — with ``budget_chars`` —
    those added bounds shrunk together until the WHOLE artifact fits the
    completion cap (:func:`worst_case_chars` <= ``budget_chars``).

    The bound tool's contract stays open and unbounded; this is what a
    decoder needs to be able to END. MEASURED (tune-10, 2B): with objects left
    open, four of five ``operator_manual`` passes ran to the 8,192-token cap
    and came back as nothing (2026-09-24); with objects closed and each string
    and list capped on its own, five more did (2026-09-25), because twenty
    entries of six thousand characters in each of several fields is still an
    artifact no cap can hold — the worst case of the three artifacts that failed
    was 1.5x to 90x the cap. Budgeting the total is what makes an end certain.

    Only bounds this function ADDED shrink, uniformly and never below
    :data:`DECODER_MIN_STRING` or a list's own ``minItems``; a ``const``, an
    ``enum``, a fixed row count and a bound the schema states itself are the
    design's and stay. Where the design's own fixed part is larger than the
    budget the floors hold and the schema is returned as small as it goes."""
    added: list[dict] = []

    def close(node: object) -> object:
        if isinstance(node, dict):
            out = {k: (close(v) if k != "additionalProperties" or isinstance(v, dict) else v)
                   for k, v in node.items()}
            if out.get("type") == "object" and not isinstance(out.get("additionalProperties"), dict):
                out["additionalProperties"] = False
            if out.get("type") == "string" and not {"enum", "const", "maxLength"} & set(out):
                out["maxLength"] = DECODER_MAX_STRING
                added.append(out)
            if out.get("type") == "array" and "maxItems" not in out \
                    and out.get("items") is not False:
                out["maxItems"] = DECODER_MAX_ITEMS
                added.append(out)
            return out
        if isinstance(node, list):
            return [close(v) for v in node]
        return node

    closed = close(schema)
    if not budget_chars:
        return closed
    # Strings and lists shrink TOGETHER, each toward its floor: shrinking
    # strings alone left an assessment item's question at 80 characters while
    # its rubric could still hold nine criteria; shrinking lists alone takes an
    # item to one option. A string keeps a sentence and a list four entries.
    # Last, and only where the design's own shape is larger than the cap (the
    # single arm's one submit carrying a whole plan AND its items), a list of
    # OBJECTS may go below four, never below its own ``minItems``; a list of
    # strings — an item's options — keeps four.
    def objects(n: dict) -> bool:
        return isinstance(n.get("items"), dict) and n["items"].get("type") == "object"

    def floor_of(node: dict, last: bool) -> int:
        if node.get("type") == "string":
            return DECODER_MIN_STRING
        own = int(node.get("minItems") or 0)
        return max(1, own) if last and objects(node) else max(DECODER_MIN_ITEMS, own)

    for last in (False, True):
        for _round in range(80):
            if worst_case_chars(closed) <= budget_chars:
                return closed
            moved = False
            for node in added:
                key = "maxLength" if node.get("type") == "string" else "maxItems"
                smaller = max(floor_of(node, last), int(node[key] * 0.85))
                if smaller < node[key]:
                    node[key], moved = smaller, True
            if not moved:
                break
    return closed


def _open(schema: object) -> object:
    """Every object without an ``additionalProperties`` of its own declared
    open, recursively. The ADDIE shape is a floor, not a mould
    (``artifact_schemas._obj``), and a grammar backend in strict mode reads a
    missing keyword as closed — the opposite of the package's rule."""
    if isinstance(schema, dict):
        out = {k: _open(v) for k, v in schema.items()}
        if out.get("type") == "object" and "additionalProperties" not in out:
            out["additionalProperties"] = True
        return out
    if isinstance(schema, list):
        return [_open(v) for v in schema]
    return schema


__all__ = ["Vocabulary", "artifact_property", "decoder_budget_chars", "for_decoder",
           "worst_case_chars", "tighten_parameters",
           "tighten_specs", "xgrammar_safe", "UNSUPPORTED_KEYWORDS"]

"""The deep, per-field JSON Schema for every submit-able artifact.

This module is the SOLE declaration of an artifact's field-level SHAPE
(types, nesting, enums): the ``submit_*`` tool's ``parameters`` schema is
built from here and the stage prompt does not restate it as text — only the
RULES_* prose (cross-field, referential and judgment-call constraints no JSON
Schema can express) travels in the prompt. Restating the shape as a JSON
example in the prompt cost double the tokens for the same information. Two
things keep this from forking:

* Where ``core/validation.py`` already type-checks a field (today, the six
  ``implementation_plan`` sub-artifacts), the schema here is DERIVED from
  ``validation._NESTED_FIELDS`` via :func:`_from_validation` rather than
  retyped by hand — ``validation.py`` stays the one upstream source, this is
  a projection of it, and the two cannot disagree about a field's presence
  or type.
* Every enum value list is typed exactly once, in ``rulebook.py``
  (``MEDIA_TYPES``, ``BLOOM_LEVELS``, ``BLOOM_VERBS``, ``EVIDENCE_TYPES``,
  ``PLAN_CATEGORIES``), and both this module's ``enum`` arrays and
  ``rulebook``'s own ``%``-interpolated ``RULES_*`` prose read the same
  constant.

Everything else here (assessment items, activities, content modules and
media, learner materials, every dev-plan, session guides, the analysis and
outcomes artifacts) has no formal shape declared anywhere else — this is
filling that gap, not duplicating one.

Keyed by the exact string each artifact uses as its ``AgenticStep.submit_fields``
/ ``fanout.SetOutput.schema_key`` key. Three keys (``assessment_dev_plan``,
``activity_dev_plan``, ``implementation_dev_plan``) exist because the raw
field name ``dev_plan`` is reused across three stages for three different
shapes — see ``AgenticStep.schema_keys``, which resolves the collision.
"""
from __future__ import annotations

from .. import rulebook as rules
from .. import validation

_TYPE_TO_JSON = {str: "string", list: "array", dict: "object"}


def _from_validation(field_key: str, *, exclude: tuple[str, ...] = ()) -> dict:
    """A JSON Schema for one ``implementation_plan`` sub-artifact, read
    straight off ``validation._NESTED_FIELDS`` rather than retyped — the
    piece that keeps this module from forking away from the validator for
    the artifacts it already type-checks. List fields are typed as arrays of
    string: ``validation.py`` checks no deeper than "is a list"."""
    spec = validation._NESTED_FIELDS["implementation_plan"][field_key]
    properties: dict = {}
    required: list[str] = []
    for name, (py_type, is_required) in spec.items():
        if name in exclude:
            continue
        json_type = _TYPE_TO_JSON[py_type]
        prop: dict = {"type": json_type}
        if json_type == "array":
            prop["items"] = {"type": "string"}
        properties[name] = prop
        if is_required:
            required.append(name)
    return {"type": "object", "properties": properties, "required": required}


def _obj(properties: dict, required: tuple[str, ...] = ()) -> dict:
    """An artifact's declared fields and which of them are REQUIRED. Extra
    keys are allowed, and kept.

    The ADDIE shape is a floor, not a mould: what an artifact must carry is
    checked (``required`` here, ``core/validation.py`` for acceptance), and
    what a model writes beside it travels with the artifact — into the design
    state and out through the aggregator into ``addie_output.json``. Refusing
    or dropping undeclared keys was measured to cost the artifact's SUBSTANCE
    on a small model, which often writes real content under a name of its
    own: on run 1c0a4e81 ``context_analysis`` shipped ``constraints: []`` and
    ``task_analysis`` ``topics: []`` with 31 keys of analysis discarded beside
    them, and on runs 14a6b4c7/9efc3cfa ``prototype_execution`` was rejected
    three times over two keys and shipped invalid. A missing required field
    is a fault; an extra one is not."""
    return {"type": "object", "properties": properties, "required": list(required)}


def _arr(items: str = "string") -> dict:
    return {"type": "array", "items": {"type": items}}


def _arr_of(item_schema: dict) -> dict:
    return {"type": "array", "items": item_schema}


_BLOOM = {"type": "string", "enum": list(rules.BLOOM_LEVELS)}
_BLOOM_VERB = {"type": "string", "enum": list(rules.BLOOM_VERBS)}
_EVIDENCE = {"type": "string", "enum": list(rules.EVIDENCE_TYPES)}
_MEDIA = {"type": "string", "enum": list(rules.MEDIA_TYPES)}
_PLAN_CATEGORY = {"type": "string", "enum": list(rules.PLAN_CATEGORIES)}


ARTIFACT_SCHEMAS: dict[str, dict] = {
    # ── analysis (submitted piecemeal, one of these five per call) ─────────
    "needs_analysis": _obj({
        "problem_definition": {"type": "string"},
        "gaps": _arr_of(_obj({
            "id": {"type": "string"}, "description": {"type": "string"},
            "evidence": {"type": "string"}}, ("id", "description"))),
        "performance_analysis": {"type": "string"},
        "priority_matrix": _obj({
            "high": _arr(), "medium": _arr(), "low": _arr()}),
    }, ("gaps",)),
    "learner_analysis": _obj({
        "target_audience": {"type": "string"},
        "characteristics": _arr(),
        "prior_knowledge": {"type": "string"},
        "learning_preferences": _arr(),
        "motivation": {"type": "string"},
        "challenges": _arr(),
    }),
    "context_analysis": _obj({
        "constraints": _arr_of(_obj({
            "id": {"type": "string"}, "description": {"type": "string"}},
            ("id", "description"))),
        "environment": {"type": "string"},
        "duration": {"type": "string"},
        "resources": _arr(),
    }),
    "task_analysis": _obj({
        "topics": _arr_of(_obj({
            "id": {"type": "string"}, "topic": {"type": "string"},
            "subtopics": _arr()}, ("id", "topic"))),
        "prerequisites": _arr(),
        "entry_behaviors": _arr(),
        "initial_objectives": _arr_of(_obj({
            "draft": {"type": "string"}, "critique": {"type": "string"},
            "revision": {"type": "string"}})),
        "review_summary": {"type": "string"},
    }),
    "improvement_plan": _obj({
        "feedback_summary": {"type": "string"},
        "improvements": _arr_of(_obj({
            "id": {"type": "string"},
            "addresses_gap": {"type": "string",
                              "description": "an existing gap id from needs_analysis.gaps"},
            "action": {"type": "string"}}, ("id", "addresses_gap", "action"))),
        "next_iteration_goals": _arr(),
        "feedback_loop": {"type": "string"},
    }, ("improvements",)),

    # ── outcomes ─────────────────────────────────────────────────────────
    "course_goal": _obj({"statement": {"type": "string"}}, ("statement",)),
    #: Item schema — ``learning_objectives`` is an ARRAY field.
    "learning_objectives": _obj({
        "id": {"type": "string"}, "level": _BLOOM,
        "statement": {"type": "string"}, "bloom_verb": _BLOOM_VERB,
    }, ("id", "level", "statement", "bloom_verb")),

    # ── assessment ───────────────────────────────────────────────────────
    # No "diagnostic"/"formative"/"summative" buckets. Declared here they are
    # optional and named by no rule, so a model leaves them empty and any
    # establisher reading them cannot fire (see
    # `alignment._promised_categories`). The plan states its categories ONCE,
    # in `lo_coverage_targets`, per objective; an optional second place to say
    # the same thing only invites a small model to guess.
    "assessment_plan": _obj({
        "lo_coverage_targets": {"type": "object",
            "description": "objective id -> list of plan categories covering it",
            "additionalProperties": {"type": "array", "items": _PLAN_CATEGORY}},
        "expected_evidence": {"type": "object",
            "description": "objective id -> what evidence would demonstrate mastery of it",
            "additionalProperties": {"type": "string"}},
        "formative_methods": _arr(),
        "pilot_data_plan": _obj({
            "collection_points": _arr(),
            "anticipated_difficulties": _arr_of(_obj({
                "area": {"type": "string"}, "rationale": {"type": "string"},
                "detected_by": {"type": "string"}, "first_revision": {"type": "string"}},
                ("area", "rationale", "detected_by", "first_revision"))),
        }, ("anticipated_difficulties",)),
    }, ("lo_coverage_targets", "pilot_data_plan")),
    "assessment_dev_plan": _obj({
        "instrument_sets": _arr_of(_obj({
            "set_id": {"type": "string"}, "objectives": _arr(),
            "plan_categories": {"type": "array", "items": _PLAN_CATEGORY},
            "expected_items": {"type": "integer"},
            "instrument_hint": {"type": "string"}, "rationale": {"type": "string"}},
            ("set_id", "objectives", "plan_categories", "expected_items"))),
    }, ("instrument_sets",)),
    #: Item schema — the fan-out's ``assessment_tools`` (assessment items).
    "assessment_tools": _obj({
        "type": _EVIDENCE, "question": {"type": "string"},
        "options": _arr(), "correct_answer": {"type": "string"},
        "aligned_objective": {"type": "string"}, "plan_category": _PLAN_CATEGORY,
        "required_cognitive_process": _BLOOM, "scoring_criteria": {"type": "string"},
        "rubric": _arr_of(_obj({
            "id": {"type": "string"}, "description": {"type": "string"},
            "evidence_type": _EVIDENCE,
            "levels": _obj({"excellent": {"type": "string"},
                            "satisfactory": {"type": "string"},
                            "needs_improvement": {"type": "string"}})},
            ("id", "description", "evidence_type"))),
    }, ("type", "question", "aligned_objective", "plan_category",
        "required_cognitive_process", "rubric")),

    # ── activities ───────────────────────────────────────────────────────
    "instructional_strategies": _obj({
        "model": {"type": "string"},
        "sequence": _arr_of(_obj({
            "event": {"type": "string"}, "activity": {"type": "string"},
            "duration": {"type": "string"}, "resources": _arr()},
            ("event", "activity"))),
        "methods": _arr(), "rationale": {"type": "string"},
    }, ("sequence",)),
    "non_instructional_strategies": _obj({
        "motivation_strategies": _arr(), "self_directed_learning": _arr(),
        "support_strategies": _arr(),
    }),
    "activity_dev_plan": _obj({
        "contact_hours": {"type": "number",
            "description": "scheduled learner time the whole course has, in hours"},
        "activity_blocks": _arr_of(_obj({
            "set_id": {"type": "string"}, "objectives": _arr(),
            "block_theme": {"type": "string"},
            "block_minutes": {"type": "integer",
                "description": "this block's share of contact_hours, in minutes"},
            "expected_activities": {"type": "integer"},
            "rationale": {"type": "string"}},
            ("set_id", "objectives", "block_minutes", "expected_activities"))),
    }, ("contact_hours", "activity_blocks")),
    #: Item schema — the fan-out's ``learning_activities``.
    "learning_activities": _obj({
        "activity_name": {"type": "string"}, "duration": {"type": "string"},
        "description": {"type": "string"},
        "materials_needed": {"type": "string",
            "description": "free text describing what content/resource this activity "
                           "needs, not an id"},
        "aligned_objectives": _arr(), "prepares_for_assessment": _arr(),
        "learner_cognitive_process": _BLOOM,
        "prerequisite_activities": {"type": "array", "items": {"type": "integer"},
            "description": "1-based positions of earlier activities in this same submission"},
    }, ("activity_name", "description", "aligned_objectives", "learner_cognitive_process")),

    # ── content ──────────────────────────────────────────────────────────
    #: Item schema — ``content_modules`` is an ARRAY field.
    "content_modules": _obj({
        "id": {"type": "string"}, "title": {"type": "string"},
        "description": {"type": "string"}, "supports_activities": _arr(),
        "covers_topics": _arr(), "expected_materials": {"type": "integer"},
    }, ("id", "title", "description")),
    #: Item schema — ``media_selections`` is an ARRAY field.
    "media_selections": _obj({
        "id": {"type": "string"}, "media_type": _MEDIA,
        "purpose": {"type": "string"}, "rationale": {"type": "string"},
        "respects_constraints": _arr(), "for_modules": _arr(),
    }, ("id", "media_type", "for_modules")),
    #: Item schema — the fan-out's ``learner_materials``.
    "learner_materials": _obj({
        "title": {"type": "string"},
        "type": _MEDIA | {"description":
            "the media_type of the media selection this material realizes"},
        "format": {"type": "string"}, "content": {"type": "string"},
        "linked_module": {"type": "string"},
    }, ("title", "type", "format", "content", "linked_module")),

    # ── implementation: six framing artifacts, derived from validation.py ──
    "instructor_orientation": _from_validation("instructor_orientation"),
    "system_check": _from_validation("system_check"),
    "prototype_execution": _from_validation("prototype_execution"),
    "monitoring": _from_validation("monitoring"),
    # session_guides is excluded: validate_implementation rejects a submit
    # that carries it (it is written by a separate tool, see below).
    "instructor_guide": _from_validation("instructor_guide", exclude=("session_guides",)),
    "operator_manual": _from_validation("operator_manual"),
    "implementation_dev_plan": _obj({
        "session_blocks": _arr_of(_obj({
            "set_id": {"type": "string"}, "expected_sessions": {"type": "integer"},
            "activity_ids": _arr(), "material_ids": _arr(),
            "block_theme": {"type": "string"}, "rationale": {"type": "string"}},
            ("set_id", "expected_sessions", "activity_ids"))),
    }, ("session_blocks",)),
    #: Item schema — the fan-out's ``session_guides``.
    "session_guides": _obj({
        "session": {"type": "integer"}, "objectives": _arr(),
        "activities": {"type": "array", "items": {"type": "string"},
            "description": "prose describing what happens in the session, not ids"},
        "activity_ids": _arr(), "material_ids": _arr(), "notes": {"type": "string"},
    }, ("session", "activity_ids")),
}

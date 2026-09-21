"""Structural schema validation for graph sections and the ADDIE aggregate.

This is deliberately separate from ``core/checks.py``: this module only checks
*structure* (required fields present, correct JSON types, well-formed ids),
while the checks module checks *pedagogy* (alignment, Bloom, coverage,
feasibility). Schema errors found here reach the residual audit exactly like a
coverage gap.
"""
from __future__ import annotations

import re
from typing import Any

# field -> expected python type; the second element marks the field as required.
# ``additionalProperties`` is implicitly allowed: unknown keys never error, so an
# LLM that adds extra detail is fine. Only declared fields are type-checked.
_SECTION_FIELDS: dict[str, dict[str, tuple[type | tuple[type, ...], bool]]] = {
    # Validated over a virtual section: the objectives live on element nodes.
    # CourseGoal is its own singleton node ({"statement": str}, no schema).
    "objective": {
        "learning_objectives": (list, True),
    },
    "assessment_plan": {
        "sets": (list, True),
        "lo_coverage_targets": (dict, True),
        "formative_methods": (list, False),
    },
    "activity_plan": {
        "instructional_strategies": (dict, True),
    },
    "assessment": {
        "assessment_tools": (list, True),
    },
    "activity": {
        "learning_activities": (list, True),
    },
    "implementation_plan": {
        "instructor_orientation": (dict, True),
        "system_check": (dict, True),
        "prototype_execution": (dict, True),
        "monitoring": (dict, True),
        "instructor_guide": (dict, True),
        "operator_manual": (dict, True),
    },
}

#: Inner keys of the section fields that are DOCUMENTS with a fixed shape —
#: today the six implementation artifacts. Checked exactly like the top level
#: (presence, type, placeholder), one level down. This is the upstream
#: source for those six artifacts' deep tool-call schema too
#: (``core/agentic/artifact_schemas.py``) — read from here to build the ``submit_*`` tool's ``parameters``, never retyped by hand, so
#: the two cannot disagree about a field's presence or type.
#:
#: MEASURED (run e81b8108): with only the top level declared, an
#: ``instructor_guide`` written under invented keys (``instructor_role``,
#: ``responsibilities``…) was a non-empty dict of the right type and passed
#: the submit, the stage check, the audit and ``validate_addie`` — and since
#: ``session_guides`` was not there, no P10/P11 edge was ever established:
#: every activity and material in the design ended unscheduled. The prompt
#: says "EXACT schema"; this is what makes that true.
_NESTED_FIELDS: dict[str, dict[str, dict[str, tuple[type | tuple[type, ...], bool]]]] = {
    "implementation_plan": {
        "instructor_orientation": {
            "orientation_objectives": (list, True), "schedule": (str, True),
            "materials": (list, True), "competency_checklist": (list, True),
        },
        "system_check": {
            "checklist": (list, True), "technical_validation": (str, True),
            "contingency_plans": (list, True),
        },
        "prototype_execution": {
            "pilot_scope": (str, True), "participants": (str, True),
            "execution_log": (list, True), "issues_encountered": (list, True),
        },
        "monitoring": {
            "monitoring_criteria": (list, True), "support_channels": (list, True),
            "issue_resolution_log": (list, True), "real_time_adjustments": (list, True),
        },
        "instructor_guide": {
            "overview": (str, True), "session_guides": (list, True),
            "facilitation_tips": (list, True), "troubleshooting": (list, True),
        },
        "operator_manual": {
            "system_setup": (str, True), "operation_procedures": (list, True),
            "support_procedures": (list, True), "escalation_process": (str, True),
        },
    },
}

#: Shape of the items of a nested LIST field — ``session_guides`` is the one:
#: its ``activity_ids`` are what P10 reads, so a guide whose sessions carry
#: prose but no ids schedules nothing. ``material_ids`` may legitimately be
#: empty (a session that hands nothing out) and is only type-checked.
_NESTED_LIST_ITEM_FIELDS: dict[str, dict[str, dict[str, tuple[type | tuple[type, ...], bool]]]] = {
    "implementation_plan": {
        "instructor_guide.session_guides": {
            "activity_ids": (list, True), "material_ids": (list, False),
        },
    },
}

#: The ADDIE phase each implementation artifact is surfaced under by the
#: aggregator, so ``validate_addie`` can hold the assembled output to the same
#: inner shape the section validator holds the submit to.
_ADDIE_NESTED_SOURCE = {
    ("development", "instructor_guide"): ("implementation_plan", "instructor_guide"),
    ("development", "operator_manual"): ("implementation_plan", "operator_manual"),
    ("implementation", "instructor_orientation"): ("implementation_plan", "instructor_orientation"),
    ("implementation", "system_check"): ("implementation_plan", "system_check"),
    ("implementation", "prototype_execution"): ("implementation_plan", "prototype_execution"),
    ("implementation", "monitoring"): ("implementation_plan", "monitoring"),
}

_ID_PATTERN = re.compile(r"^[A-Za-z][A-Za-z0-9_:\-]*$")

# A leaf string that IS a schema placeholder copied verbatim into the output
# (e.g. "<detailed system setup guide>", "<obj>"). Whole-string match only, and
# no nested angle brackets, so real content that merely contains markup
# ("<p>…</p>", "a < b") never matches. Small models copy these out of the
# prompt schemas; the value is then non-empty, so the plain required-field
# check waves it through while the judge scores the field as absent (measured:
# an operator_manual shipping "<detailed system setup guide>").
_PLACEHOLDER_TOKEN = re.compile(r"^<[^<>]{1,80}>$")

#: Suffix shared by every placeholder error, so the regen loop can filter for
#: them exactly like `required field is missing or empty` (see outputs.py).
PLACEHOLDER_FIELD_MARKER = "schema placeholder text left unfilled"
#: The other way a required field can be "there but not really there".
EMPTY_FIELD_MARKER = "required field is missing or empty"

_PLACEHOLDER_SCAN_DEPTH = 6
_PLACEHOLDER_REPORT_CAP = 3  # errors per field; one is enough to trigger regen


def _placeholder_paths(value: Any, path: str = "", depth: int = _PLACEHOLDER_SCAN_DEPTH) -> list[str]:
    """Dotted paths of every leaf string under ``value`` that is a bare
    schema placeholder token."""
    if depth < 0:
        return []
    if isinstance(value, str):
        return [path] if _PLACEHOLDER_TOKEN.match(value.strip()) else []
    found: list[str] = []
    if isinstance(value, dict):
        for key, item in value.items():
            found.extend(_placeholder_paths(item, f"{path}.{key}" if path else str(key), depth - 1))
    elif isinstance(value, list):
        for index, item in enumerate(value):
            found.extend(_placeholder_paths(item, f"{path}[{index}]", depth - 1))
    return found


def _placeholder_errors(node_type: str, field: str, value: Any) -> list[str]:
    paths = _placeholder_paths(value)
    errors = []
    for p in paths[:_PLACEHOLDER_REPORT_CAP]:
        path = f"{node_type}.{field}" + ("" if not p else p if p.startswith("[") else f".{p}")
        errors.append(f"{path}: {PLACEHOLDER_FIELD_MARKER}")
    return errors

# The id field of each section list's ENTRIES, validated for non-empty
# well-formed ids. ``assessment_tools`` holds assessment TASKS, whose id field
# is ``id`` like every other element's; ``item_id`` belongs to the questions
# one level down, inside a task's own ``items``.
_LIST_ITEM_ID_FIELD = {
    "objective": ("learning_objectives", "id"),
    "assessment": ("assessment_tools", "id"),
    "activity": ("learning_activities", "id"),
}


def _type_name(expected: type | tuple[type, ...]) -> str:
    if isinstance(expected, tuple):
        return "/".join(t.__name__ for t in expected)
    return expected.__name__


def _check_fields(prefix: str, data: dict, spec: dict, errors: list[str]) -> None:
    """Presence, type and placeholder checks for one level of ``spec`` over
    ``data``, every error path rooted at ``prefix``."""
    for field, (expected_type, required) in spec.items():
        if field not in data or data[field] in (None, "", [], {}):
            if required:
                errors.append(f"{prefix}.{field}: {EMPTY_FIELD_MARKER}")
            continue
        if not isinstance(data[field], expected_type):
            errors.append(
                f"{prefix}.{field}: expected {_type_name(expected_type)}, "
                f"got {type(data[field]).__name__}"
            )
        elif required:
            errors.extend(_placeholder_errors(prefix, field, data[field]))


def _check_nested(node_type: str, field: str, value: Any, errors: list[str],
                  prefix: str | None = None) -> None:
    """One level down: the declared inner keys of ``field``, and the shape of
    the items of any declared inner list."""
    inner = (_NESTED_FIELDS.get(node_type) or {}).get(field)
    if inner is None or not isinstance(value, dict):
        return
    root = prefix or f"{node_type}.{field}"
    _check_fields(root, value, inner, errors)
    for path, item_spec in (_NESTED_LIST_ITEM_FIELDS.get(node_type) or {}).items():
        parent, _, list_key = path.partition(".")
        if parent != field:
            continue
        items = value.get(list_key)
        if not isinstance(items, list):
            continue
        for index, item in enumerate(items):
            if not isinstance(item, dict):
                errors.append(f"{root}.{list_key}[{index}]: expected object item")
                continue
            _check_fields(f"{root}.{list_key}[{index}]", item, item_spec, errors)


def validate_section(node_type: str, data: Any) -> list[str]:
    """Return structural error strings for one specialist section payload."""
    errors: list[str] = []
    spec = _SECTION_FIELDS.get(node_type)
    if spec is None:
        return errors
    if not isinstance(data, dict):
        return [f"{node_type}: section payload must be a JSON object, got {type(data).__name__}"]

    _check_fields(node_type, data, spec, errors)
    for field in spec:
        _check_nested(node_type, field, data.get(field), errors)

    list_field_id = _LIST_ITEM_ID_FIELD.get(node_type)
    if list_field_id:
        field, id_key = list_field_id
        items = data.get(field)
        if isinstance(items, list):
            for index, item in enumerate(items):
                if not isinstance(item, dict):
                    errors.append(f"{node_type}.{field}[{index}]: expected object item")
                    continue
                item_id = str(item.get(id_key, "")).strip()
                if not item_id:
                    errors.append(f"{node_type}.{field}[{index}].{id_key}: missing id")
                elif not _ID_PATTERN.match(item_id):
                    errors.append(f"{node_type}.{field}[{index}].{id_key}: malformed id {item_id!r}")
    return errors


_ADDIE_PHASE_FIELDS: dict[str, dict[str, tuple[type | tuple[type, ...], bool]]] = {
    "analysis": {
        "needs_analysis": (dict, True),
        "learner_analysis": (dict, True),
        "context_analysis": (dict, True),
        "task_analysis": (dict, True),
    },
    "design": {
        "learning_objectives": (list, True),
        "instructional_strategies": (dict, True),
    },
    "development": {
        "learner_materials": (list, True),
        "assessment_tools": (list, True),
        "expert_review": (dict, False),
        "instructor_guide": (dict, True),
        "operator_manual": (dict, True),
    },
    "implementation": {
        "instructor_orientation": (dict, True),
        "system_check": (dict, True),
        "prototype_execution": (dict, True),
        "monitoring": (dict, True),
    },
    "evaluation": {
        "formative": (dict, True),
        "summative": (dict, True),
        "improvement_plan": (dict, True),
    },
}


def validate_addie(addie_output: Any) -> list[str]:
    """Return structural error strings for an assembled ADDIE output."""
    errors: list[str] = []
    if not isinstance(addie_output, dict):
        return [f"addie_output must be a JSON object, got {type(addie_output).__name__}"]

    for phase, spec in _ADDIE_PHASE_FIELDS.items():
        section = addie_output.get(phase)
        if section is None:
            errors.append(f"{phase}: required ADDIE phase is missing")
            continue
        if not isinstance(section, dict):
            errors.append(f"{phase}: expected object, got {type(section).__name__}")
            continue
        _check_fields(phase, section, spec, errors)
        for field in spec:
            source = _ADDIE_NESTED_SOURCE.get((phase, field))
            if source is not None and section.get(field) not in (None, "", [], {}):
                _check_nested(source[0], source[1], section[field], errors,
                              prefix=f"{phase}.{field}")
    return errors

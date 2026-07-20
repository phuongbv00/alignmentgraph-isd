"""Structural schema validation for graph sections and the ADDIE aggregate.

This is deliberately separate from ``PedagogicalVerifierAgent``: this module
only checks *structure* (required fields present, correct JSON types, well-formed
ids), while the verifier checks *pedagogy* (alignment, Bloom, coverage,
feasibility). Schema errors found here are routed back to the owning specialist
agent through the auditor, exactly like a coverage gap.
"""
from __future__ import annotations

import re
from typing import Any

# field -> expected python type; the second element marks the field as required.
# ``additionalProperties`` is implicitly allowed: unknown keys never error, so an
# LLM that adds extra detail is fine. Only declared fields are type-checked.
_SECTION_FIELDS: dict[str, dict[str, tuple[type | tuple[type, ...], bool]]] = {
    "needs_context": {
        "needs_analysis": (dict, True),
        "learner_analysis": (dict, True),
        "context_analysis": (dict, True),
        "task_analysis": (dict, True),
    },
    # Design is now decomposed across several singleton nodes (see
    # objective_design.py's 2-call split) — objective_0 only holds
    # learning_objectives; the rest live in their own node types below.
    "objective": {
        "learning_objectives": (list, True),
    },
    "assessment_plan": {
        "diagnostic": (list, False),
        "formative": (list, False),
        "summative": (list, False),
    },
    "instructional_strategies": {
        "model": (str, False),
        "sequence": (list, True),
    },
    "content_structure": {
        "modules": (list, True),
    },
    "assessment": {
        "assessment_tools": (list, True),
        "expert_review": (dict, False),
    },
    "activity": {
        "learning_activities": (list, True),
        "instructor_guide": (dict, False),
    },
    "material": {
        "learner_materials": (list, True),
    },
    "implementation_plan": {
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

_ID_PATTERN = re.compile(r"^[A-Za-z][A-Za-z0-9_:\-]*$")

# Item-level id fields per section list, validated for non-empty well-formed ids.
_LIST_ITEM_ID_FIELD = {
    "objective": ("learning_objectives", "id"),
    "assessment": ("assessment_tools", "item_id"),
    "activity": ("learning_activities", "id"),
    "material": ("learner_materials", "id"),
}


def _type_name(expected: type | tuple[type, ...]) -> str:
    if isinstance(expected, tuple):
        return "/".join(t.__name__ for t in expected)
    return expected.__name__


def validate_section(node_type: str, data: Any) -> list[str]:
    """Return structural error strings for one specialist section payload."""
    errors: list[str] = []
    spec = _SECTION_FIELDS.get(node_type)
    if spec is None:
        return errors
    if not isinstance(data, dict):
        return [f"{node_type}: section payload must be a JSON object, got {type(data).__name__}"]

    for field, (expected_type, required) in spec.items():
        if field not in data or data[field] in (None, "", [], {}):
            if required:
                errors.append(f"{node_type}.{field}: required field is missing or empty")
            continue
        if not isinstance(data[field], expected_type):
            errors.append(
                f"{node_type}.{field}: expected {_type_name(expected_type)}, "
                f"got {type(data[field]).__name__}"
            )

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
        for field, (expected_type, required) in spec.items():
            if field not in section or section[field] in (None, "", [], {}):
                if required:
                    errors.append(f"{phase}.{field}: required field is missing or empty")
                continue
            if not isinstance(section[field], expected_type):
                errors.append(
                    f"{phase}.{field}: expected {_type_name(expected_type)}, "
                    f"got {type(section[field]).__name__}"
                )
    return errors

"""Turning user input into a valid ``DesignBrief``.

Three jobs: import a benchmark scenario file, merge a patch proposed by the
planner, and produce the truncated view the UI shows above the run.

The one thing to keep in mind throughout: ``DesignBrief`` is deliberately
permissive — every field is optional and ``extra="allow"``. That is right for
the harness (a scenario carries keys the brief has no opinion about) but it
means validation will not catch a model inventing structure. So anything coming
from an LLM is whitelisted here first.
"""
from __future__ import annotations

from typing import Any

from pydantic import ValidationError

from ..core.brief import DesignBrief, DesignBriefConstraints, DesignBriefContext

# Fields the planner may write. `id` is ours to assign and `refinement_request`
# is not part of this flow.
_PATCHABLE_TOP_LEVEL = frozenset(DesignBrief.model_fields) - {"id", "refinement_request"}
_NESTED_MODELS = {"context": DesignBriefContext, "constraints": DesignBriefConstraints}

# Scenario keys that are not DesignBrief fields but are worth keeping: they show
# up in the inspector and would otherwise silently vanish on import.
_KNOWN_EXTRA_CONTEXT = frozenset({"additional_context", "institution_type"})

MAX_IMPORT_BYTES = 1_000_000


class BriefImportError(ValueError):
    """The uploaded file is not usable as a brief."""


def scenario_to_brief_dict(payload: Any) -> tuple[dict, list[str]]:
    """Map a benchmark scenario onto the design-brief contract.

    Same single translation point the benchmark adapter uses: ``scenario_id``
    becomes ``id`` and everything else keeps its name. Returns the dict plus any
    warnings worth surfacing.
    """
    if not isinstance(payload, dict):
        raise BriefImportError("Expected a JSON object at the top level of the file.")

    data = dict(payload)
    warnings: list[str] = []

    if "id" not in data and "scenario_id" in data:
        data["id"] = data.pop("scenario_id")
    if not data.get("id"):
        warnings.append("No 'id' or 'scenario_id' in the file; the program id will be used instead.")

    try:
        brief = DesignBrief.model_validate(data)
    except ValidationError as exc:
        raise BriefImportError(f"File is not a valid design brief: {_summarize(exc)}") from exc

    dumped = brief.model_dump()
    # `None` values are stripped during validation (see schema._LenientModel), so
    # a key present-but-null in the file is simply absent here. Say so rather
    # than letting someone wonder where it went.
    dropped = [k for k, v in payload.items() if v is None]
    dropped += [f"context.{k}" for k, v in (payload.get("context") or {}).items() if v is None]
    dropped += [f"constraints.{k}" for k, v in (payload.get("constraints") or {}).items() if v is None]
    if dropped:
        warnings.append(f"Null fields ignored: {', '.join(sorted(dropped))}.")

    return dumped, warnings


def merge_patch(brief: dict, patch: Any) -> tuple[dict, list[str]]:
    """Apply a planner-proposed patch to the working brief.

    Scalars and lists are replaced wholesale (the planner is told to send
    complete lists, not deltas); `context` and `constraints` merge key by key so
    a turn about the audience does not erase the constraints.
    """
    warnings: list[str] = []
    if not isinstance(patch, dict):
        return dict(brief), ["Ignored a patch that was not an object."]

    merged = dict(brief)
    rejected: list[str] = []

    for key, value in patch.items():
        if key not in _PATCHABLE_TOP_LEVEL:
            rejected.append(key)
            continue
        if key in _NESTED_MODELS:
            if not isinstance(value, dict):
                rejected.append(key)
                continue
            allowed = set(_NESTED_MODELS[key].model_fields)
            if key == "context":
                allowed |= _KNOWN_EXTRA_CONTEXT
            nested = dict(merged.get(key) or {})
            for nested_key, nested_value in value.items():
                if nested_key in allowed:
                    nested[nested_key] = nested_value
                else:
                    rejected.append(f"{key}.{nested_key}")
            merged[key] = nested
        else:
            merged[key] = value

    if rejected:
        warnings.append(f"Ignored unknown fields: {', '.join(sorted(rejected))}.")

    try:
        validated = DesignBrief.model_validate(merged).model_dump()
    except ValidationError as exc:
        # Keep what was already good rather than losing the turn entirely.
        warnings.append(f"Patch partly rejected: {_summarize(exc)}.")
        return dict(brief), warnings

    return validated, warnings


def validate_brief(payload: Any) -> tuple[dict, list[str]]:
    """Validate a brief supplied wholesale (the manual-edit path)."""
    if not isinstance(payload, dict):
        raise BriefImportError("Expected a JSON object.")
    try:
        return DesignBrief.model_validate(payload).model_dump(), []
    except ValidationError as exc:
        raise BriefImportError(_summarize(exc)) from exc


def is_runnable(brief: dict) -> bool:
    """Enough signal for the harness to do something meaningful.

    Not a quality bar — the harness tolerates a sparse brief. This only stops a
    run being launched against an entirely blank one.
    """
    if not brief:
        return False
    return bool(
        brief.get("title")
        or brief.get("user_message")
        or brief.get("learning_goals")
        or brief.get("domain")
    )


def preview(brief: dict, *, goal_limit: int = 3) -> dict:
    """The truncated view shown above the run.

    Returns counts rather than the values themselves for `context`/`constraints`
    so the card stays a card; the inspector shows the rest on click.
    """
    brief = brief or {}
    goals = brief.get("learning_goals") or []
    context = brief.get("context") or {}
    constraints = brief.get("constraints") or {}

    return {
        "id": brief.get("id", ""),
        "title": brief.get("title", ""),
        "domain": brief.get("domain", ""),
        "difficulty": brief.get("difficulty", ""),
        "duration": brief.get("duration") or context.get("duration", ""),
        "target_audience": brief.get("target_audience", ""),
        "user_message": _truncate(brief.get("user_message", ""), 280),
        "learning_goals": [_truncate(g, 160) for g in goals[:goal_limit]],
        "learning_goals_total": len(goals),
        "context_filled": _count_filled(context),
        "context_total": len(DesignBriefContext.model_fields),
        "constraints_filled": _count_filled(constraints),
        "constraints_total": len(DesignBriefConstraints.model_fields),
        "is_runnable": is_runnable(brief),
    }


def missing_core_fields(brief: dict) -> list[str]:
    """Fields the planner should still be asking about."""
    brief = brief or {}
    missing = []
    if not brief.get("title"):
        missing.append("title")
    if not brief.get("domain"):
        missing.append("domain")
    if len(brief.get("learning_goals") or []) < 2:
        missing.append("learning_goals")
    if not brief.get("target_audience"):
        missing.append("target_audience")
    if not (brief.get("duration") or (brief.get("context") or {}).get("duration")):
        missing.append("duration")
    return missing


def _count_filled(section: Any) -> int:
    if not isinstance(section, dict):
        return 0
    return sum(1 for value in section.values() if value not in ("", None, [], {}))


def _truncate(text: Any, limit: int) -> str:
    text = str(text or "")
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"


def _summarize(exc: ValidationError, limit: int = 3) -> str:
    parts = []
    for error in exc.errors()[:limit]:
        location = ".".join(str(p) for p in error.get("loc", ())) or "(root)"
        parts.append(f"{location}: {error.get('msg', 'invalid')}")
    return "; ".join(parts)

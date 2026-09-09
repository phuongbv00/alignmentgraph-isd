"""The planning conversation that builds a design brief before a run.

A demo affordance, not part of the harness: the brief it produces is an ordinary
``DesignBrief``, identical to one imported from a file.

The whole design problem here is that a small self-hosted model asked for JSON
will regularly not return JSON. The ladder in ``_parse`` mirrors what
the harness's own model IO already does for the specialists: constrained
decoding, then fences, then repair, then a correction turn, then a plain-text
fallback. A planning turn must never fail — the person is mid-sentence.
"""
from __future__ import annotations

import json
import logging
import re
from typing import Any

from . import briefs, llm_settings

logger = logging.getLogger(__name__)

MAX_HISTORY_MESSAGES = 12

_SYSTEM = """\
You are an instructional-design intake assistant. You interview a designer to \
fill in a design brief for a training program, one or two questions at a time.

Reply with a SINGLE JSON object and nothing else:

{"reply": string, "brief_patch": object, "missing_fields": [string], "ready": boolean}

- "reply": your message to the designer. One short question or acknowledgement, \
at most 3 sentences. Ask about at most TWO missing fields at a time. Write in \
the same language the designer is using.
- "brief_patch": ONLY the fields the designer has just supplied, using exactly \
these paths and no others:
    title, domain, difficulty, duration, target_audience, learning_goals,
    context.duration, context.learning_environment, context.class_size,
    context.learner_age, context.learner_education, context.learner_role,
    context.domain_expertise, context.prior_knowledge,
    constraints.resources, constraints.budget, constraints.tech_requirements,
    constraints.assessment_type, constraints.accessibility, constraints.language
  learning_goals and constraints.resources are lists: send the COMPLETE list \
each time, never a delta. Send {} when the designer supplied nothing new. \
Never invent a value the designer did not give you.
- "missing_fields": important fields still unknown.
- "ready": true once title, domain and at least two learning_goals are set.

Learning goals should be observable and measurable where the designer gives you \
enough to make them so. Do not write the brief for them: ask.
"""

_FALLBACK_REPLY = (
    "Sorry — I did not manage to structure that. Could you tell me the program "
    "title and its subject domain?"
)


def plan_turn(history: list[dict], brief: dict, user_message: str) -> dict:
    """One planning turn.

    Returns ``{reply, brief, brief_patch, missing_fields, ready, warnings}``.
    Raises ``RuntimeError`` only when no model is configured at all.
    """
    error = llm_settings.probe()
    if error:
        raise RuntimeError(error)
    factory = llm_settings.build_factory()
    if factory is None:
        raise RuntimeError("No model configured.")

    messages = _build_messages(history, brief, user_message)
    llm = factory()
    raw = _invoke(llm, messages)
    parsed = _parse(raw, llm, messages)

    patch = parsed.get("brief_patch")
    merged, warnings = briefs.merge_patch(brief, patch if isinstance(patch, dict) else {})

    # The model's own `missing_fields` is advisory and often optimistic; the
    # computed one is what the UI shows.
    missing = briefs.missing_core_fields(merged)

    return {
        "reply": str(parsed.get("reply") or "").strip() or _FALLBACK_REPLY,
        "brief": merged,
        "brief_patch": patch if isinstance(patch, dict) else {},
        "missing_fields": missing,
        # `ready` is a hint for the UI, never a trigger: the person presses Run.
        "ready": bool(parsed.get("ready")) and briefs.is_runnable(merged),
        "warnings": warnings,
    }


def _build_messages(history: list[dict], brief: dict, user_message: str) -> list[dict]:
    messages: list[dict] = [{"role": "system", "content": _SYSTEM}]
    messages.append({
        "role": "system",
        "content": "Design brief so far (JSON):\n" + json.dumps(brief or {}, ensure_ascii=False),
    })
    for message in history[-MAX_HISTORY_MESSAGES:]:
        role = message.get("role")
        if role in ("user", "assistant") and message.get("content"):
            messages.append({"role": role, "content": message["content"]})
    messages.append({"role": "user", "content": user_message})
    return messages


def _invoke(llm, messages: list[dict], *, json_mode: bool = True) -> str:
    """Call the model, preferring constrained JSON decoding where supported."""
    target = llm
    if json_mode:
        try:
            target = llm.bind(response_format={"type": "json_object"})
        except Exception:  # noqa: BLE001 - not every backend supports binding
            target = llm
    try:
        result = target.invoke(messages)
    except Exception as exc:  # noqa: BLE001
        if json_mode:
            # Some OpenAI-compatible servers reject response_format outright.
            logger.info("planner: retrying without json_object mode (%s)", exc)
            return _invoke(llm, messages, json_mode=False)
        logger.warning("planner: model call failed: %s", exc)
        return ""
    return result.content if hasattr(result, "content") else str(result)


_FENCE = re.compile(r"```(?:json)?\s*(.*?)\s*```", re.DOTALL)


def _parse(raw: str, llm, messages: list[dict]) -> dict:
    """Coax a response object out of whatever the model returned."""
    parsed = _try_parse(raw)
    if parsed is not None:
        return parsed

    # One correction turn, quoting the model back to itself.
    correction = messages + [
        {"role": "assistant", "content": raw or "(empty)"},
        {"role": "user", "content": (
            "That was not a single JSON object. Reply with ONLY a JSON object "
            'with the keys "reply", "brief_patch", "missing_fields" and "ready". '
            "No prose, no markdown fences."
        )},
    ]
    retried = _try_parse(_invoke(llm, correction))
    if retried is not None:
        return retried

    # Last resort: show the designer whatever the model said rather than an error.
    logger.info("planner: falling back to raw text (len=%d)", len(raw or ""))
    text = _strip_fences(raw).strip()
    return {
        "reply": text[:800] if text else _FALLBACK_REPLY,
        "brief_patch": {},
        "missing_fields": [],
        "ready": False,
    }


def _try_parse(raw: str) -> dict | None:
    text = _strip_fences(raw or "").strip()
    if not text:
        return None

    for candidate in (text, _first_object(text)):
        if not candidate:
            continue
        for loader in (json.loads, _repair_loads):
            try:
                value = loader(candidate)
            except Exception:  # noqa: BLE001
                continue
            normalized = _normalize(value)
            if normalized is not None:
                return normalized
    return None


def _normalize(value: Any) -> dict | None:
    """Accept the shapes a model actually produces, reject the rest."""
    if isinstance(value, list):
        # A top-level array wrapping the object is a common small-model slip.
        value = next((v for v in value if isinstance(v, dict)), None)
    if not isinstance(value, dict):
        return None
    # A parse that found no recognisable key is not a response object; better to
    # fall through to the correction turn than to silently drop the turn.
    if not any(k in value for k in ("reply", "brief_patch", "missing_fields", "ready")):
        return None
    return value


def _repair_loads(text: str):
    from json_repair import loads  # hard dependency of the core package

    return loads(text)


def _strip_fences(text: str) -> str:
    match = _FENCE.search(text or "")
    return match.group(1) if match else (text or "")


def _first_object(text: str) -> str:
    """The outermost brace-balanced object, for output with prose around it."""
    start = text.find("{")
    if start < 0:
        return ""
    depth, in_string, escaped = 0, False, False
    for index in range(start, len(text)):
        char = text[index]
        if in_string:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
            continue
        if char == '"':
            in_string = True
        elif char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return text[start : index + 1]
    # Unbalanced (truncated output): hand the tail to the repair loader.
    return text[start:]

from __future__ import annotations

import json

from pydantic import BaseModel, model_validator


class _LenientModel(BaseModel):
    """Base for the design brief input contract: tolerant of messy upstream JSON.

    ``extra="allow"`` keeps unmodelled fields valid, and the before-validator
    drops explicit ``null``s so a JSON ``null`` falls back to the typed default
    ("" / []) instead of failing validation. Normalising here is the whole
    point — callers downstream get a clean typed object instead of a dict that
    may carry ``None`` anywhere.
    """

    model_config = {"extra": "allow"}

    @model_validator(mode="before")
    @classmethod
    def _drop_nulls(cls, data: object) -> object:
        if isinstance(data, dict):
            return {key: value for key, value in data.items() if value is not None}
        return data


class DesignBriefContext(_LenientModel):
    """Learner/environment context, rendered into every prompt by ``_format_design_brief``."""

    duration: str = ""
    learning_environment: str = ""
    class_size: str = ""
    learner_age: str = ""
    learner_education: str = ""
    learner_role: str = ""
    domain_expertise: str = ""
    prior_knowledge: str = ""


class DesignBriefConstraints(_LenientModel):
    resources: list[str] = []
    budget: str = ""
    tech_requirements: str = ""
    assessment_type: str = ""
    accessibility: str = ""
    language: str = ""


class DesignBrief(_LenientModel):
    """The user/benchmark input contract for one harness run.

    ``alignmentgraph-isd`` receives a design brief: either a structured brief
    (title/domain/learning_goals/...) or, on the sparse app path, just a
    ``user_message``. Callers that come from other vocabularies (e.g. the benchmark's "scenario") map their
    fields onto this envelope at the boundary.
    """

    # identity
    id: str = ""
    title: str = ""

    # app intent (sparse path) — only this turn's input; the app keeps the
    # conversation history itself (``server/planner.py``).
    user_message: str = ""

    # refinement session (app path) — an explicit edit request against the loaded
    # program graph. Declared for the app; nothing reads its contents yet, and
    # the benchmark never sets it.
    refinement_request: dict = {}

    # structured design inputs (all optional)
    domain: str = ""
    difficulty: str = ""
    duration: str = ""
    target_audience: str = ""
    learning_goals: list[str] = []
    context: DesignBriefContext = DesignBriefContext()
    constraints: DesignBriefConstraints = DesignBriefConstraints()


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


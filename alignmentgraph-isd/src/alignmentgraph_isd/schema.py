from __future__ import annotations

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
    """Learner/environment context. Fields match what RetrievalPlanner reads."""

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
    ``user_message``. Internal orchestration work is represented separately as
    ``PlannedTask`` instances produced by the task planner/router. Callers that
    come from other vocabularies (e.g. the benchmark's "scenario") map their
    fields onto this envelope at the boundary.
    """

    # identity
    id: str = ""
    title: str = ""

    # app intent (sparse path) — only this turn's input. Prior turns are loaded
    # internally from working memory on a resumed session, never re-sent here.
    user_message: str = ""

    # structured design inputs (all optional)
    domain: str = ""
    difficulty: str = ""
    duration: str = ""
    target_audience: str = ""
    learning_goals: list[str] = []
    context: DesignBriefContext = DesignBriefContext()
    constraints: DesignBriefConstraints = DesignBriefConstraints()

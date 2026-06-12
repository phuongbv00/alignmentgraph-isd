from __future__ import annotations

from pydantic import BaseModel


class ScenarioContext(BaseModel):
    """Learner/environment context. Fields match what RetrievalPlanner reads."""

    duration: str = ""
    learning_environment: str = ""
    class_size: str = ""
    learner_age: str = ""
    learner_education: str = ""
    learner_role: str = ""
    domain_expertise: str = ""
    prior_knowledge: str = ""

    model_config = {"extra": "allow"}


class ScenarioConstraints(BaseModel):
    resources: list[str] = []
    budget: str = ""
    tech_requirements: str = ""
    assessment_type: str = ""
    accessibility: str = ""
    language: str = ""

    model_config = {"extra": "allow"}


class TaskRequest(BaseModel):
    """Documented input contract for a single harness run.

    Benchmark scenarios are rich (title/domain/learning_goals/...); an app call
    can be as sparse as a single ``user_message``. Both share this envelope, so
    integrators have one typed shape to target instead of an opaque dict.

    ``extra="allow"`` keeps benchmark scenarios with extra fields valid; the
    pipeline still consumes a plain dict, so this model is a contract/validation
    gateway, not a new internal data structure.
    """

    # identity
    scenario_id: str = ""
    id: str = ""
    title: str = ""

    # app intent (sparse path) — only this turn's input. Prior turns are loaded
    # internally from working memory on a resumed session, never re-sent here.
    user_message: str = ""

    # structured design inputs (benchmark / app, all optional)
    domain: str = ""
    difficulty: str = ""
    duration: str = ""
    target_audience: str = ""
    learning_goals: list[str] = []
    context: ScenarioContext = ScenarioContext()
    constraints: ScenarioConstraints = ScenarioConstraints()

    model_config = {"extra": "allow"}


def as_payload(request: "TaskRequest | dict") -> dict:
    """Normalise a run input to the plain dict the pipeline consumes.

    A ``TaskRequest`` is validated/dumped; a raw dict is passed through unchanged
    so existing benchmark scenarios keep working without re-validation.
    """
    if isinstance(request, TaskRequest):
        return request.model_dump()
    if isinstance(request, dict):
        return request
    raise TypeError(f"run() expects a dict or TaskRequest, got {type(request).__name__}")

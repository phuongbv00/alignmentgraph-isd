from __future__ import annotations

from pydantic import BaseModel, model_validator


class _LenientModel(BaseModel):
    """Base for the task-input contract: tolerant of messy upstream JSON.

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


class TaskContext(_LenientModel):
    """Learner/environment context. Fields match what RetrievalPlanner reads."""

    duration: str = ""
    learning_environment: str = ""
    class_size: str = ""
    learner_age: str = ""
    learner_education: str = ""
    learner_role: str = ""
    domain_expertise: str = ""
    prior_knowledge: str = ""


class TaskConstraints(_LenientModel):
    resources: list[str] = []
    budget: str = ""
    tech_requirements: str = ""
    assessment_type: str = ""
    accessibility: str = ""
    language: str = ""


class TaskRequest(_LenientModel):
    """The single input contract for one harness run.

    ``alignmentgraph-isd`` speaks only in terms of a *task*: a rich design task
    (title/domain/learning_goals/...) or, on the sparse app path, just a
    ``user_message``. Callers that come from other vocabularies (e.g. the
    benchmark's "scenario") map their fields onto this envelope at the boundary;
    inside the package there is only ``TaskRequest``. It is both the
    validation/normalisation gateway and the internal data structure.
    """

    # identity
    task_id: str = ""
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
    context: TaskContext = TaskContext()
    constraints: TaskConstraints = TaskConstraints()

    def messages(self) -> list[dict[str, str]]:
        """This turn's input as chat messages (sparse app path).

        Conversation history is loaded from working memory, not re-sent by the
        caller, so only the current-turn ``user_message`` is surfaced here.
        """
        text = (self.user_message or getattr(self, "message", "") or "").strip()
        return [{"role": "user", "content": text}] if text else []

    @property
    def identifier(self) -> str:
        """Stable id for this task, preferring explicit ids over the title."""
        return self.task_id or self.id or self.title or "unknown"

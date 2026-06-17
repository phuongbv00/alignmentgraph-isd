from __future__ import annotations
from ..config import HarnessRunConfig
from ..schema import TaskRequest


class RetrievalPlanner:
    def __init__(self, config: HarnessRunConfig) -> None:
        self.config = config

    def retrieve(self, task: TaskRequest) -> dict:
        """Return a compact context pack for downstream ADDIE agents.

        This is deterministic local retrieval over the task itself plus the
        rubric focus. It gives the "full" ablation a real context object without
        adding external dependencies or network calls.
        """
        if not self.config.ablation.use_rag:
            return {}

        context = task.context
        constraints = task.constraints
        resources = constraints.resources if isinstance(constraints.resources, list) else [constraints.resources]

        return {
            "task_focus": {
                "title": task.title,
                "domain": task.domain,
                "difficulty": task.difficulty,
                "duration": context.duration or task.duration,
                "learning_environment": context.learning_environment,
                "class_size": context.class_size,
                "learner_profile": {
                    "age": context.learner_age,
                    "education": context.learner_education,
                    "role": context.learner_role,
                    "domain_expertise": context.domain_expertise,
                    "prior_knowledge": context.prior_knowledge,
                },
            },
            "available_resources": resources,
            "constraints": {
                "budget": constraints.budget,
                "technology": constraints.tech_requirements,
                "assessment_type": constraints.assessment_type,
                "accessibility": constraints.accessibility,
                "language": constraints.language,
            },
            "alignment_requirements": [
                f"Every objective must be measured by at least one assessment item: {goal}"
                for goal in task.learning_goals
            ],
            "rubric_focus": [
                "Cover all 33 ADDIE sub-items explicitly.",
                "Use measurable Bloom verbs and avoid vague verbs such as know, learn, understand, or comprehend.",
                "Preserve objective-assessment-activity alignment with explicit objective IDs.",
                "Include pilot execution evidence, data collection, monitoring, and revision loops.",
            ],
        }

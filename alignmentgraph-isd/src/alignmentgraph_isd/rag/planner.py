from __future__ import annotations
from ..config import HarnessRunConfig
from ..schema import DesignBrief


class RetrievalPlanner:
    def __init__(self, config: HarnessRunConfig) -> None:
        self.config = config

    def retrieve(self, design_brief: DesignBrief) -> dict:
        """Return a compact context pack for downstream ADDIE agents.

        This core planner always returns internal context derived from the design
        brief. ``use_ext_corpus`` only controls optional external corpus retrieval
        add-ons; internal graph/memory context is a core harness behavior.
        """
        context = design_brief.context
        constraints = design_brief.constraints
        resources = constraints.resources if isinstance(constraints.resources, list) else [constraints.resources]

        return {
            "design_brief_focus": {
                "title": design_brief.title,
                "domain": design_brief.domain,
                "difficulty": design_brief.difficulty,
                "duration": context.duration or design_brief.duration,
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
                for goal in design_brief.learning_goals
            ],
            "rubric_focus": [
                "Cover all 33 ADDIE sub-items explicitly.",
                "Use measurable Bloom verbs and avoid vague verbs such as know, learn, understand, or comprehend.",
                "Preserve objective-assessment-activity alignment with explicit objective IDs.",
                "Include pilot execution evidence, data collection, monitoring, and revision loops.",
            ],
            "external_corpus": {
                "enabled": self.config.ablation.use_ext_corpus,
                "sources": [],
            },
        }

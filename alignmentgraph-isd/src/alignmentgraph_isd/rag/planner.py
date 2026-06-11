from __future__ import annotations
from ..config import HarnessRunConfig


class RetrievalPlanner:
    def __init__(self, config: HarnessRunConfig) -> None:
        self.config = config

    def retrieve(self, scenario: dict) -> dict:
        """Return a compact context pack for downstream ADDIE agents.

        This is deterministic local retrieval over the scenario itself plus the
        benchmark rubric focus. It gives the "full" ablation a real context
        object without adding external dependencies or network calls.
        """
        if not self.config.ablation.use_rag:
            return {}

        context = scenario.get("context", {}) if isinstance(scenario.get("context"), dict) else {}
        constraints = scenario.get("constraints", {}) if isinstance(scenario.get("constraints"), dict) else {}
        raw_goals = scenario.get("learning_goals", []) or []
        learning_goals = raw_goals if isinstance(raw_goals, list) else [raw_goals]
        raw_resources = constraints.get("resources", []) or []
        resources = raw_resources if isinstance(raw_resources, list) else [raw_resources]

        return {
            "scenario_focus": {
                "title": scenario.get("title", ""),
                "domain": scenario.get("domain", ""),
                "difficulty": scenario.get("difficulty", ""),
                "duration": context.get("duration") or scenario.get("duration", ""),
                "learning_environment": context.get("learning_environment", ""),
                "class_size": context.get("class_size", ""),
                "learner_profile": {
                    "age": context.get("learner_age", ""),
                    "education": context.get("learner_education", ""),
                    "role": context.get("learner_role", ""),
                    "domain_expertise": context.get("domain_expertise", ""),
                    "prior_knowledge": context.get("prior_knowledge", ""),
                },
            },
            "available_resources": resources,
            "constraints": {
                "budget": constraints.get("budget", ""),
                "technology": constraints.get("tech_requirements", ""),
                "assessment_type": constraints.get("assessment_type", ""),
                "accessibility": constraints.get("accessibility", ""),
                "language": constraints.get("language", ""),
            },
            "alignment_requirements": [
                f"Every objective must be measured by at least one assessment item: {goal}"
                for goal in learning_goals
            ],
            "rubric_focus": [
                "Cover all 33 ADDIE sub-items explicitly.",
                "Use measurable Bloom verbs and avoid vague verbs such as know, learn, understand, or comprehend.",
                "Preserve objective-assessment-activity alignment with explicit objective IDs.",
                "Include pilot execution evidence, data collection, monitoring, and revision loops.",
            ],
        }

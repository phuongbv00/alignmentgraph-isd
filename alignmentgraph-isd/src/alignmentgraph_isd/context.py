"""Context preparation from the design brief — this is NOT retrieval/RAG.

`ContextPlanner` only restructures the design brief into focus/alignment/rubric
guidance for the specialist agents. It does not read any store. The harness has
three distinct retrieval paths, none of which live here:

- graph-context retrieval (`BaseISDAgent._graph_context`) — core, always on
- memory retrieval (`MemorySession.augment_context_pack`) — core, always on
- RAG = external-corpus retrieval (`RetrievalPlanner`) — case-study add-on, gated

The context pack these pieces produce is assembled in `MetaAgent.run`.
"""
from __future__ import annotations

from .schema import DesignBrief


class ContextPlanner:
    def build(self, design_brief: DesignBrief) -> dict:
        """Restructure the design brief into a compact context pack for agents."""
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
        }

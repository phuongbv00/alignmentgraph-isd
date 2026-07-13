"""Brief elicitation: a Q&A front-door that turns a vague request into a DesignBrief.

Case-study/app add-on, peer to the ``rag`` module: the benchmark never uses it,
and the loop deliberately lives OUTSIDE ``MetaAgent`` — ``MetaAgent.run`` is one
complete pass over an approved brief, while elicitation is a human-in-the-loop
conversation. The caller owns the loop: feed each user message to ``step``; the
agent either asks the next clarifying question or proposes a draft brief. Only
after the user approves does the caller hand the brief to ``MetaAgent.run`` as a
normal init session.
"""
from __future__ import annotations

from .agents.base import parse_json_response
from ..config import HarnessRunConfig
from .schema import DesignBrief

ELICITATION_SYSTEM_PROMPT = """You are an instructional-design intake assistant for corporate training programs.
Your job is to turn a vague training request into a concrete design brief through a short dialogue.

A complete design brief needs: title, domain, difficulty, duration, target_audience,
learning_goals (3-6 measurable goals), context (learning_environment, class_size,
learner_role, prior_knowledge), and constraints (resources, tech_requirements,
assessment_type, language).

Rules:
- Ask AT MOST ONE question per turn, targeting the most important missing information.
- Prefer concrete options over open questions when reasonable.
- When you have enough to draft a sensible brief (do not interrogate endlessly —
  3-5 questions is typical), propose the draft instead of asking more.
- Respond with JSON only, in one of two forms:
  {"action": "ask", "question": "<your single question>"}
  {"action": "propose", "summary": "<1-2 sentence summary of the program>", "brief": {<DesignBrief JSON>}}
"""


class ElicitationTurn:
    """One agent turn: either a clarifying question or a proposed draft brief."""

    def __init__(self, kind: str, message: str, draft_brief: DesignBrief | None = None) -> None:
        self.kind = kind  # "question" | "draft"
        self.message = message
        self.draft_brief = draft_brief


class BriefElicitationAgent:
    def __init__(self, config: HarnessRunConfig) -> None:
        if config.llm_factory is None:
            raise RuntimeError("BriefElicitationAgent requires config.llm_factory")
        self._llm = config.llm_factory()

    def step(self, history: list[dict], user_message: str) -> ElicitationTurn:
        """Advance the dialogue one turn.

        ``history`` is the prior conversation as ``{"role": ..., "content": ...}``
        dicts (caller-owned; persist it via working memory if the session should
        be resumable). The new ``user_message`` is appended by this call's prompt
        but NOT mutated into ``history`` — the caller decides what to keep.
        """
        messages = [{"role": "system", "content": ELICITATION_SYSTEM_PROMPT}]
        messages.extend(history)
        messages.append({"role": "user", "content": user_message})

        response = self._llm.invoke(messages)
        parsed = parse_json_response(getattr(response, "content", ""))

        if parsed.get("action") == "propose" and isinstance(parsed.get("brief"), dict):
            brief_payload = dict(parsed["brief"])
            brief_payload.setdefault("id", _slugify(brief_payload.get("title", "training-program")))
            draft = DesignBrief.model_validate(brief_payload)
            summary = parsed.get("summary", "Draft design brief ready.")
            return ElicitationTurn("draft", summary, draft)

        question = parsed.get("question") or "Could you tell me more about what this training program should achieve?"
        return ElicitationTurn("question", question)


def _slugify(title: str) -> str:
    slug = "".join(ch.lower() if ch.isalnum() else "-" for ch in title).strip("-")
    while "--" in slug:
        slug = slug.replace("--", "-")
    return f"brief-{slug or 'training-program'}"


__all__ = ["BriefElicitationAgent", "ElicitationTurn", "ELICITATION_SYSTEM_PROMPT"]

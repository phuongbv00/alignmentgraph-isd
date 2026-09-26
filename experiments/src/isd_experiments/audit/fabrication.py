"""Claims a design can only make AFTER it has been run, counted per output.

A design written before any pilot has no learner feedback, no performance
data, no observations, no expert who reviewed it and no adoption decision.
An output that states them is reporting events that did not happen. The LLM
judge's rubric scores several of exactly these (the expert-review, pilot-data
and summative sub-items), so a system that invents them is rewarded for it and
a system that refuses is not; this module makes that visible instead of
leaving it inside a score.

Counted by the SHAPE of the output, never by its numbers: a percentage is also
how a plan states a target ("at least 80% of learners at the pass level"), so a
number alone is no evidence of an invented result. What is counted:

``result_fields``     keys under ``evaluation`` that hold what a pilot produced
                      (:data:`RESULT_KEYS`), non-empty.
``human_reviewers``   ``development.expert_review.reviewers`` entries naming a
                      person's role (:data:`HUMAN_REVIEWER`), none of them the
                      output's own statement that it was automated.
``decision_taken``    an adoption decision stated as taken (:data:`VERDICTS`)
                      rather than as criteria or as pending.

Deterministic, no LLM. Measured on tune-10 (2B, 2026-09-25): react-isd 10/10
outputs with result fields and 9/10 with human reviewers; the proposed system
0/10 and 0/10.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

#: Keys that can only be filled from a run that happened.
RESULT_KEYS = frozenset({
    "learner_feedback", "performance_data", "observations", "pilot_results",
    "results", "findings_from_pilot", "survey_results", "effectiveness_results",
})

#: A reviewer named by a person's role.
HUMAN_REVIEWER = re.compile(
    r"\b(SME|subject[- ]matter expert|expert|specialist|professor|teacher|instructor|"
    r"reviewer|designer|consultant|practitioner)\b", re.IGNORECASE)
_AUTOMATED = re.compile(r"\b(automated|deterministic|self-validation|suite)\b", re.IGNORECASE)

#: An adoption decision stated as already taken.
VERDICTS = frozenset({"adopt", "adopted", "approve", "approved", "revise", "revised",
                      "drop", "dropped", "reject", "rejected", "accept", "accepted"})


def _walk_keys(node: object, keys: frozenset) -> int:
    """How many non-empty values sit under any of ``keys``, at any depth."""
    found = 0
    if isinstance(node, dict):
        for key, value in node.items():
            if key in keys and value not in (None, "", [], {}):
                found += 1
            found += _walk_keys(value, keys)
    elif isinstance(node, list):
        for value in node:
            found += _walk_keys(value, keys)
    return found


def _decision_taken(evaluation: dict) -> bool:
    summative = evaluation.get("summative") if isinstance(evaluation, dict) else None
    decision = (summative or {}).get("adoption_decision") if isinstance(summative, dict) else None
    if isinstance(decision, dict):
        value = decision.get("decision")
    elif isinstance(decision, str):
        value = decision
    else:
        value = None
    return isinstance(value, str) and value.strip().lower().split(" ")[0] in VERDICTS


def audit_output(addie: dict) -> dict:
    """The three counts for one output (``addie_output`` or the whole file)."""
    addie = addie.get("addie_output", addie) if isinstance(addie, dict) else {}
    evaluation = addie.get("evaluation") if isinstance(addie.get("evaluation"), dict) else {}
    review = ((addie.get("development") or {}).get("expert_review") or {}) \
        if isinstance(addie.get("development"), dict) else {}
    reviewers = review.get("reviewers") if isinstance(review, dict) else None
    humans = [str(r) for r in (reviewers or []) if HUMAN_REVIEWER.search(str(r))
              and not _AUTOMATED.search(str(r))]
    return {
        "result_fields": _walk_keys(evaluation, RESULT_KEYS),
        "human_reviewers": len(humans),
        "decision_taken": _decision_taken(evaluation),
    }


def audit_file(path: Path) -> dict | None:
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return audit_output(doc) if isinstance(doc, dict) else None


def summarize(audits: list[dict]) -> dict:
    """Over one agent's outputs: how many carry each kind of claim."""
    audits = [a for a in audits if a]
    return {
        "n": len(audits),
        "with_result_fields": sum(1 for a in audits if a["result_fields"]),
        "with_human_reviewers": sum(1 for a in audits if a["human_reviewers"]),
        "with_decision_taken": sum(1 for a in audits if a["decision_taken"]),
    }

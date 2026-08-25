"""Shared test fixtures: a network-free fake LLM and ready-made run configs.

The fake model inspects the system prompt of each Designer agent and returns
a canned, schema-valid JSON payload. This lets the whole harness run end-to-end
with no network or API key, so smoke tests stay deterministic and fast.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from alignmentgraph_isd import DesignBrief, HarnessRunConfig

FIXTURES = Path(__file__).parent / "fixtures"


# ── Canned, schema-valid Designer payloads (5 Designers, new relation ontology) ──

_ANALYZE = {
    "needs_analysis": {
        "problem_definition": "Fresher developers cannot apply OOP concepts in real code.",
        "gaps": [
            {"id": "GAP-01", "description": "No OOP modeling skill", "evidence": "Code review findings"},
            {"id": "GAP-02", "description": "Weak abstraction habits", "evidence": "Design review feedback"},
        ],
        "performance_analysis": "An instructional solution combining concepts and hands-on labs is appropriate.",
        "priority_matrix": {"high": ["GAP-01"], "medium": ["GAP-02"], "low": []},
    },
    "learner_analysis": {
        "target_audience": "Junior backend engineers",
        "characteristics": ["Recent graduates", "Java syntax familiarity", "Limited design experience"],
        "prior_knowledge": "Basic Java syntax and data structures.",
        "learning_preferences": ["Hands-on", "Pair work"],
        "motivation": "High; tied to job performance.",
        "challenges": ["Abstraction", "Design trade-offs"],
    },
    "context_analysis": {
        "constraints": [
            {"id": "CON-01", "description": "Fixed 2-day schedule"},
            {"id": "CON-02", "description": "Shared lab machines"},
        ],
        "environment": "Instructor-led classroom with lab machines",
        "duration": "2 days",
        "resources": ["IDE", "Git repository"],
    },
    "task_analysis": {
        "topics": [
            {"id": "TOP-01", "topic": "Encapsulation", "subtopics": ["Classes", "Interfaces"]},
            {"id": "TOP-02", "topic": "Inheritance", "subtopics": ["Hierarchies", "Overriding"]},
        ],
        "prerequisites": ["Java syntax", "Basic data structures"],
        "entry_behaviors": ["Can write a Java class with fields and methods"],
        "initial_objectives": [
            {"draft": "Understand OOP", "critique": "Not observable or measurable.",
             "revision": "Apply inheritance to a domain model with 80% of tests passing."},
        ],
        "review_summary": "Learners progress from concepts to applied class design with feedback loops.",
    },
    "improvement_plan": {
        "feedback_summary": "Address the OOP modeling and abstraction gaps directly.",
        "improvements": [
            {"id": "IMP-01", "addresses_gap": "GAP-01", "action": "Add a guided modeling lab."},
            {"id": "IMP-02", "addresses_gap": "GAP-02", "action": "Add worked abstraction examples."},
        ],
        "next_iteration_goals": ["Measure design quality improvement"],
    },
}

_DESIGN = {
    "course_goal": {"statement": "Learners can design and justify OOP-based solutions."},
    "learning_objectives": [
        {"id": "ILO-01", "level": "remember", "statement": "List the four pillars of OOP.", "bloom_verb": "recall"},
        {"id": "ILO-02", "level": "understand", "statement": "Explain encapsulation with an example.", "bloom_verb": "explain"},
        {"id": "ILO-03", "level": "apply", "statement": "Apply inheritance to a given domain model with at least 80% of unit tests passing.", "bloom_verb": "apply"},
        {"id": "ILO-04", "level": "analyze", "statement": "Analyze a provided class design and identify at least three coupling issues.", "bloom_verb": "analyze"},
        {"id": "ILO-05", "level": "evaluate", "statement": "Evaluate composition versus inheritance for a given scenario, justifying the choice against two criteria.", "bloom_verb": "evaluate"},
    ],
}

_ASSESSMENT_PLAN = {
    "assessment_plan": {
        "diagnostic": ["Pre-quiz on OOP terms"],
        "formative": ["Weekly design critique"],
        "summative": ["Final design project"],
        "lo_coverage_targets": {f"ILO-0{i}": ["formative", "summative"] for i in range(1, 6)},
        "expected_evidence": {f"ILO-0{i}": "A working code artifact with justification." for i in range(1, 6)},
        "formative_methods": ["Weekly design critique with rubric", "Exit tickets after each module"],
        "pilot_data_plan": {
            "collection_points": ["After module 1", "After the design review lab"],
            "anticipated_difficulties": [
                {"area": "ILO-04", "rationale": "Analyzing coupling needs design vocabulary these learners lack.",
                 "detected_by": "Weekly design critique with rubric",
                 "first_revision": "Insert a worked coupling walkthrough before the critique."},
                {"area": "MOD-02", "rationale": "Inheritance hierarchies are the densest module.",
                 "detected_by": "Exit tickets after each module",
                 "first_revision": "Split MOD-02 into two shorter sessions with a checkpoint."},
            ],
        },
    },
}


_ASSESSMENT_DEV_PLAN = {
    "instrument_sets": [
        {"set_id": f"SET-0{i}", "objectives": [f"ILO-0{i}"], "plan_categories": ["formative", "summative"],
         "instrument_hint": "Combined formative/summative check for this objective.",
         "rationale": "One instrument per objective keeps scope contained."}
        for i in range(1, 6)
    ],
}


def _assessment_tools() -> list[dict]:
    los = [f"ILO-0{i}" for i in range(1, 6)]
    types = ["multiple_choice", "short_answer", "performance_task"]
    categories = ["diagnostic", "formative", "summative"]
    cognitive = ["remember", "understand", "apply", "analyze", "evaluate"]
    tools = []
    for i in range(10):
        lo_idx = i % 5
        item = {
            "item_id": f"AT-{i + 1:02d}",
            "type": types[i % 3],
            "question": f"Demonstrate mastery of {los[lo_idx]} in a realistic scenario.",
            "aligned_objective": los[lo_idx],
            "plan_category": categories[i % 3],
            "required_cognitive_process": cognitive[lo_idx],
            "scoring_criteria": "Rubric scores correctness, design quality, and explanation against observable criteria (0-4 each).",
            "difficulty": ["easy", "medium", "hard"][i % 3],
        }
        if item["type"] == "multiple_choice":
            # a well-formed model response ships the response set + answer key
            # (the item_completeness check flags a choice item without them)
            item["options"] = [
                "The correct realistic application", "A plausible near-miss",
                "A common misconception", "An unrelated approach",
            ]
            item["correct_answer"] = "The correct realistic application"
        tools.append(item)
    return tools


_ASSESSMENT_ITEMS = {
    "assessment_tools": _assessment_tools(),
}

_ACTIVITY_PLAN = {
    "instructional_strategies": {
        "model": "Gagné's 9 Events",
        "sequence": [{"event": e, "activity": "Guided lab", "duration": "30m", "resources": ["IDE"]} for e in [
            "Gain attention", "Inform learners of objectives", "Stimulate recall of prior learning",
            "Present content", "Provide learning guidance", "Elicit performance",
            "Provide feedback", "Assess performance", "Enhance retention and transfer"]],
        "methods": ["Live coding", "Pair programming", "Code review"],
        "rationale": "Active, scaffolded practice aligns with applied objectives.",
    },
    "non_instructional_strategies": {
        "motivation_strategies": ["Real tasks"], "self_directed_learning": ["Reading"], "support_strategies": ["Mentor"],
    },
}

_ACTIVITY_DEV_PLAN = {
    "activity_blocks": [
        {"set_id": "BLOCK-01", "objectives": ["ILO-01", "ILO-02"], "block_theme": "Encapsulation foundations",
         "rationale": "Both are introduced together in the same module."},
        {"set_id": "BLOCK-02", "objectives": ["ILO-03"], "block_theme": "Applied inheritance",
         "rationale": "Needs its own hands-on lab."},
        {"set_id": "BLOCK-03", "objectives": ["ILO-04", "ILO-05"], "block_theme": "Design review",
         "rationale": "Both are exercised via the same critique session."},
    ],
}

_ACTIVITIES = {
    "learning_activities": [
        {"id": "TLA-01", "activity_name": "Encapsulation lab", "duration": "60m",
         "description": "Build a class with invariants.", "materials_needed": "A starter repo with a class skeleton for encapsulation.",
         "aligned_objectives": ["ILO-01", "ILO-02"], "prepares_for_assessment": ["AT-01", "AT-06"],
         "learner_cognitive_process": "understand", "prerequisite_activities": []},
        {"id": "TLA-02", "activity_name": "Inheritance lab", "duration": "60m",
         "description": "Model a class hierarchy and refactor for reuse.", "materials_needed": "A starter repo with a partial class hierarchy.",
         "aligned_objectives": ["ILO-03"], "prepares_for_assessment": ["AT-03", "AT-08"],
         "learner_cognitive_process": "apply", "prerequisite_activities": ["TLA-01"]},
        {"id": "TLA-03", "activity_name": "Design review", "duration": "60m",
         "description": "Critique a provided design against SOLID principles.", "materials_needed": "A design checklist and a sample design to critique.",
         "aligned_objectives": ["ILO-04", "ILO-05"], "prepares_for_assessment": ["AT-04", "AT-05", "AT-09", "AT-10"],
         "learner_cognitive_process": "evaluate", "prerequisite_activities": ["TLA-02"]},
    ],
}

_MODULES = {
    "content_modules": [
        {"id": "MOD-01", "title": "Encapsulation Concepts", "description": "Covers classes and interfaces.",
         "supports_activities": ["TLA-01"], "covers_topics": ["TOP-01"]},
        {"id": "MOD-02", "title": "Inheritance and Design", "description": "Covers hierarchies and SOLID.",
         "supports_activities": ["TLA-02", "TLA-03"], "covers_topics": ["TOP-02"]},
    ],
    "media_selections": [
        {"id": "MED-01", "media_type": "slides", "purpose": "Explain concepts", "rationale": "Clarity for visual learners", "respects_constraints": ["CON-01"]},
        {"id": "MED-02", "media_type": "document", "purpose": "Reference checklist", "rationale": "Reusable across sessions", "respects_constraints": ["CON-02"]},
    ],
}

_MATERIALS = {
    "learner_materials": [
        {"id": "MAT-01", "title": "OOP concepts handout", "type": "document", "format": "pdf",
         "content": "Covers the four pillars with examples.", "linked_module": "MOD-01"},
        {"id": "MAT-02", "title": "Starter repository", "type": "document", "format": "pdf",
         "content": "Lab scaffolding with TODOs and tests.", "linked_module": "MOD-01"},
        {"id": "MAT-03", "title": "Design checklist", "type": "document", "format": "pdf",
         "content": "SOLID review checklist with concrete prompts.", "linked_module": "MOD-02"},
    ],
}

_RUBRICS = {
    "rubric_criteria": [
        {"id": f"RC-{i:02d}", "aligned_assessment": f"AT-{i:02d}", "aligned_objective": f"ILO-0{(i - 1) % 5 + 1}",
         "description": "Full marks require correct application with justification citing concrete evidence, scored 0-3.",
         "evidence_type": _assessment_tools()[i - 1]["type"]}
        for i in range(1, 11)
    ],
}

_IMPLEMENTATION = {
    "instructor_orientation": {
        "orientation_objectives": [
            "Instructors can prepare the lab environment and assign learner roles.",
            "Instructors can facilitate labs and apply the scoring rubric consistently.",
        ],
        "schedule": "90-minute facilitator orientation plus a 30-minute delivery rehearsal.",
        "materials": ["Facilitator runbook", "Rubric pack"],
        "competency_checklist": ["Launch and reset the lab", "Score a sample with the rubric"],
    },
    "system_check": {
        "checklist": ["Verify lab machines, IDE, and Git access before each session.", "Confirm learner grouping and submission channels."],
        "technical_validation": "Platform, access, network, and fallback checks completed before launch.",
        "contingency_plans": ["Switch to cloud IDE on failure"],
    },
    "prototype_execution": {
        "pilot_scope": "One cohort of 16 learners across two days.",
        "participants": "16 fresher developers",
        "execution_log": ["Day 1 labs ran on time", "Day 2 design review extended 15 minutes"],
        "issues_encountered": ["Two IDE setup failures"],
    },
    "monitoring": {
        "monitoring_criteria": ["Lab completion rate", "Rubric score distribution"],
        "support_channels": ["Lab chat", "Floating mentor"],
        "issue_resolution_log": ["IDE failures resolved via cloud lab"],
        "real_time_adjustments": ["Extended design review"],
    },
    "instructor_guide": {
        "overview": "Three-session flow from concepts to applied design.",
        "session_guides": [
            {"session": 1, "objectives": ["ILO-01"],
             "activities": ["Guided encapsulation lab with pair feedback"],
             "activity_ids": ["TLA-01", "TLA-02", "TLA-03"],
             "material_ids": ["MAT-01", "MAT-02", "MAT-03"],
             "notes": "Pair learners by level."},
        ],
        "facilitation_tips": ["Circulate during labs"],
        "troubleshooting": ["IDE setup failures: use the cloud lab"],
    },
    "operator_manual": {
        "system_setup": "Provision lab machines with JDK 17 and clone the starter repo.",
        "operation_procedures": ["Verify access", "Distribute repo"],
        "support_procedures": ["Escalate IDE failures"],
        "escalation_process": "Notify lab support within 5 minutes of a blocking issue.",
    },
}


#: Which canned payload a system prompt is asking for, keyed on a JSON key
#: unique to that prompt's SCHEMA.
#:
#: Deliberately not keyed on the persona sentence ("...performing the Analysis
#: phase of ADDIE"): the `single` arm replaces that sentence with one generalist
#: persona, so a fixture keyed on it silently stops recognising every step in
#: that arm, returns {} and turns the whole single-mode suite into a test of the
#: regen loop. Every key below is asserted unique across the ten prompts.
#: Each entry is (required schema keys, payload). MERGED entries come first:
#: the single-agent arm's DISPATCH call asks for a plan/strategy AND its
#: dev-plan grouping together (2026-08-28: items/activities/materials moved
#: to the per-set Developer calls, matched by _sliced_payload_for_set
#: instead), so its prompt contains BOTH keys and must not match the
#: multi-agent arm's half-payload on the first key it happens to share.
_PAYLOAD_BY_SCHEMA_KEY = (
    (('"pilot_data_plan"', '"instrument_sets"'), {**_ASSESSMENT_PLAN, **_ASSESSMENT_DEV_PLAN}),
    (('"non_instructional_strategies"', '"activity_blocks"'), {**_ACTIVITY_PLAN, **_ACTIVITY_DEV_PLAN}),
    # core/agentic/specialists.py's merged schemas are manual copies of the
    # single arm's PRE-fan-out tasks (plan+items/activities/materials all in
    # one call each) that the 2026-08-28 dev-plan fan-out deliberately did
    # not convert (see CLAUDE.md's "Agentic experimental arm" note) — kept
    # alive here so the agentic arm's own tests stay meaningful without
    # touching its generation logic.
    (('"pilot_data_plan"', '"assessment_tools"'), {**_ASSESSMENT_PLAN, **_ASSESSMENT_ITEMS}),
    (('"non_instructional_strategies"', '"learning_activities"'), {**_ACTIVITY_PLAN, **_ACTIVITIES}),
    (('"media_selections"', '"learner_materials"'), {**_MODULES, **_MATERIALS}),
    (('"needs_analysis"',), _ANALYZE),
    # course_goal alone (single arm's merged outcomes call, and the multi
    # arm's own Hop B1) vs. learning_objectives alone (the multi arm's Hop
    # B2, 2026-08-28 split) — both draw from the SAME canned _DESIGN, which
    # already carries both fields; each hop reads only the one it asked for.
    (('"course_goal"',), _DESIGN),
    (('"learning_objectives"',), _DESIGN),
    (('"pilot_data_plan"',), _ASSESSMENT_PLAN),
    (('"instrument_sets"',), _ASSESSMENT_DEV_PLAN),
    (('"assessment_tools"',), _ASSESSMENT_ITEMS),
    (('"non_instructional_strategies"',), _ACTIVITY_PLAN),
    (('"activity_blocks"',), _ACTIVITY_DEV_PLAN),
    (('"learning_activities"',), _ACTIVITIES),
    (('"media_selections"',), _MODULES),
    (('"learner_materials"',), _MATERIALS),
    (('"rubric_criteria"',), _RUBRICS),
    (('"instructor_orientation"',), _IMPLEMENTATION),
)


def _payload_for_system(system_prompt: str) -> dict:
    """The canned payload a prompt is asking for.

    Keyed on the prompt's SCHEMA, never on its persona sentence: the single
    arm replaces that sentence, so a persona-keyed fixture silently stops
    recognising every step there, returns {} and turns the whole single-mode
    suite into a test of the regen loop."""
    for keys, payload in _PAYLOAD_BY_SCHEMA_KEY:
        if all(key in system_prompt for key in keys):
            return payload
    return {}


# ── dev-plan fan-out: per-set canned slices ─────────────────────────────────
# A Developer's prompt carries "=== YOUR ASSIGNED SET/BLOCK ===" naming
# exactly the pairs/objectives it must cover. Without set-aware slicing every
# worker in a fan-out would get the SAME full canned list back (there being
# only one canned payload per family), inflating item counts and exercising
# the id-collision remap on every single test instead of only the tests that
# mean to. A real model only ever sees -- and only ever answers for -- its
# own slice, so the fake one should too.
_ASSIGNED_PAIRS_RE = re.compile(
    r"pairs \(objective x plan_category\) YOU must cover, one item each:\n((?:  - .+\n?)+)")
_ASSIGNED_OBJECTIVES_RE = re.compile(r"objectives YOU must cover:\n((?:  - .+\n?)+)")
_ASSIGNED_MODULES_RE = re.compile(r"\[MODULE:([^\]]+)\]")
_ASSIGNED_ASSESSMENT_ITEM_LINE_RE = re.compile(r"\[ASSESSMENT:[^\]]*\] (\{.*\})")


def _parse_assigned_assessment_items(raw_prompt: str) -> list[dict]:
    items = []
    for match in _ASSIGNED_ASSESSMENT_ITEM_LINE_RE.finditer(raw_prompt):
        try:
            items.append(json.loads(match.group(1)))
        except json.JSONDecodeError:
            continue
    return items


def _parse_assigned_pairs(raw_prompt: str) -> list[tuple[str, str]] | None:
    match = _ASSIGNED_PAIRS_RE.search(raw_prompt)
    if not match:
        return None
    pairs = []
    for line in match.group(1).splitlines():
        line = line.strip().lstrip("- ").strip()
        if " x " in line:
            lo, category = line.split(" x ", 1)
            pairs.append((lo.strip(), category.strip()))
    return pairs


def _parse_assigned_objectives(raw_prompt: str) -> list[str] | None:
    match = _ASSIGNED_OBJECTIVES_RE.search(raw_prompt)
    if not match:
        return None
    return [line.strip().lstrip("- ").strip() for line in match.group(1).splitlines() if line.strip()]


def _sliced_payload_for_set(raw_prompt: str) -> dict | None:
    """A Developer's own slice of the family's canned items, or ``None`` if
    this prompt isn't a Developer's (falls through to schema-key matching)."""
    if "=== YOUR ASSIGNED SET ===" in raw_prompt and '"assessment_tools"' in raw_prompt:
        pairs = _parse_assigned_pairs(raw_prompt)
        if pairs is not None:
            by_pair = {(t["aligned_objective"], t["plan_category"]): t for t in _assessment_tools()}
            items = []
            for index, (lo, category) in enumerate(pairs, start=1):
                if (lo, category) in by_pair:
                    items.append(by_pair[(lo, category)])
                else:
                    # A singleton fallback set (e.g. the single arm's, or any
                    # dev plan that groups differently from the canned
                    # _ASSESSMENT_DEV_PLAN fixture) can ask for a
                    # (objective, category) combo _assessment_tools()'s fixed
                    # cycling distribution never produced -- write a
                    # generic-but-valid item rather than nothing, exactly as
                    # a real model would for a combo it has no worked
                    # example of.
                    items.append({
                        "item_id": f"AT-{category[:1].upper()}{index}-{lo}",
                        "type": "short_answer",
                        "question": f"Demonstrate mastery of {lo} in a realistic scenario.",
                        "aligned_objective": lo, "plan_category": category,
                        "required_cognitive_process": "apply",
                        "scoring_criteria": ("Rubric scores correctness and justification against "
                                             "observable criteria (0-3)."),
                    })
            return {"assessment_tools": items}
    if "=== YOUR ASSIGNED BLOCK ===" in raw_prompt and '"learning_activities"' in raw_prompt:
        objectives = _parse_assigned_objectives(raw_prompt)
        if objectives is not None:
            by_objective: dict[str, list[dict]] = {}
            for activity in _ACTIVITIES["learning_activities"]:
                for lo in activity.get("aligned_objectives", []):
                    by_objective.setdefault(lo, []).append(activity)
            items, seen_ids = [], set()
            for lo in objectives:
                matches = by_objective.get(lo, [])
                if matches:
                    for activity in matches:
                        if activity["id"] not in seen_ids:
                            seen_ids.add(activity["id"])
                            items.append(activity)
                else:
                    # Same reasoning as the assessment branch above: an
                    # objective grouping the canned _ACTIVITIES fixture never
                    # covers gets a generic-but-valid activity instead of
                    # nothing.
                    items.append({
                        "id": f"TLA-{lo}", "activity_name": f"Practice activity for {lo}",
                        "duration": "30m", "description": f"Guided practice targeting {lo}.",
                        "materials_needed": "A worked example relevant to this objective.",
                        "aligned_objectives": [lo], "prepares_for_assessment": [],
                        "learner_cognitive_process": "apply", "prerequisite_activities": [],
                    })
            return {"learning_activities": items}
    if "=== YOUR ASSIGNED MODULE ===" in raw_prompt and '"learner_materials"' in raw_prompt:
        modules = set(_ASSIGNED_MODULES_RE.findall(raw_prompt))
        if modules:
            items = [m for m in _MATERIALS["learner_materials"] if m.get("linked_module") in modules]
            return {"learner_materials": items}
    if "=== YOUR ASSIGNED ITEM ===" in raw_prompt and '"rubric_criteria"' in raw_prompt:
        assigned_items = _parse_assigned_assessment_items(raw_prompt)
        if assigned_items:
            by_assessment_id = {rc["aligned_assessment"]: rc for rc in _RUBRICS["rubric_criteria"]}
            criteria = []
            for item in assigned_items:
                item_id = str(item.get("item_id", ""))
                if item_id in by_assessment_id:
                    criteria.append(by_assessment_id[item_id])
                else:
                    # A repair-synthesized assessment item (e.g. "AT-F-ILO-01"
                    # from repairs.repair_plan_coverage) has no entry in the
                    # canned fixture above -- write a generic-but-valid
                    # criterion from the item itself rather than returning
                    # nothing, exactly as a real model would for an item it
                    # has never seen a worked example of.
                    criteria.append({
                        "id": f"RC-{item_id}", "aligned_assessment": item_id,
                        "aligned_objective": str(item.get("aligned_objective", "")),
                        "description": ("Full marks require correct application with "
                                        "justification citing concrete evidence, scored 0-3."),
                        "evidence_type": str(item.get("type") or "short_answer"),
                    })
            return {"rubric_criteria": criteria}
    return None


class _Result:
    def __init__(self, content: str) -> None:
        self.content = content
        self.usage_metadata = None


class FakeChatModel:
    """Network-free chat model that returns canned, schema-valid JSON."""

    def bind(self, **_kwargs) -> "FakeChatModel":
        return self

    def invoke(self, messages):
        # The WHOLE conversation, not just the system turn: the single-agent
        # arm keeps one stable persona in `system` and varies the task and
        # schema in `user`, so a system-only fixture sees no schema at all and
        # returns {} for every one of its steps.
        raw_prompt = "\n".join(
            m.get("content", "") for m in messages
            if isinstance(m, dict) and isinstance(m.get("content"), str)
        )
        # A Developer's own work-set slice, read from the RAW prompt (the
        # generic stripping below would remove "=== YOUR ASSIGNED SET/BLOCK
        # ===" along with every other non-SCENARIO header) — checked first so
        # a fan-out worker gets only the items its own set asked for, never
        # the whole family's canned list.
        sliced = _sliced_payload_for_set(raw_prompt)
        if sliced is not None:
            return _Result(json.dumps(sliced, ensure_ascii=False))
        # Strip injected prior-artifact context ("=== <HEADER> ===\n...\n\n===
        # SCENARIO ===") before matching: the prose arm injects earlier
        # documents as VERBATIM JSON, so their schema keys would otherwise
        # out-match the schema this step is actually asking for (the graph
        # arm's plan-node JSON leaks keys the same way — it just happened to
        # land on merged entries). Only the task/schema text may key payloads.
        prompt = re.sub(r"=== (?!SCENARIO)[^=]+? ===.*?(?==== SCENARIO ===)", "", raw_prompt, flags=re.S)
        payload = _payload_for_system(prompt)
        return _Result(json.dumps(payload, ensure_ascii=False))


@pytest.fixture
def fake_llm_factory():
    return lambda: FakeChatModel()


@pytest.fixture
def fake_config(fake_llm_factory):
    config = HarnessRunConfig()
    config.llm_factory = fake_llm_factory
    return config


def load_brief(name: str) -> DesignBrief:
    payload = json.loads((FIXTURES / name).read_text(encoding="utf-8"))
    return DesignBrief.model_validate(payload)


_EVENT_ACTIONS = {
    "recovery": {
        "retry", "regen_empty_section", "agent_error", "llm_error", "salvage_truncated",
        "invalid_action", "submit_rejected", "submit_invalid_final", "repeated_tool_call",
        "commit_invalid_section", "agentic_fallback", "repair", "revision",
    },
    "node_edit": {"node_add", "node_update"},
    "validation": {"validate"},
    "check": {"check"},
    "repair": {"repair"},
    "retrieval": {"retrieval"},
}


def events_of(trajectory: dict, event_type: str) -> list[dict]:
    """Filter the unified event log by a named taxonomy group for tests."""
    return [e for e in trajectory["events"] if e["action"] in _EVENT_ACTIONS[event_type]]

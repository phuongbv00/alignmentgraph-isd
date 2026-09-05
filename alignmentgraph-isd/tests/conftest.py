"""Shared test fixtures: a network-free fake LLM and ready-made run configs.

The fake model inspects the system prompt of each Designer agent and returns
a canned, schema-valid JSON payload. This lets the whole harness run end-to-end
with no network or API key, so smoke tests stay deterministic and fast.
"""
from __future__ import annotations

import copy
import json
import re
from pathlib import Path

import pytest

from alignmentgraph_isd import DesignBrief, HarnessRunConfig, MetaAgent

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
            # The criterion is written INSIDE the item it marks (2026-09-02):
            # no `aligned_assessment`/`aligned_objective` back-references, and
            # no separate `rubric_criteria` list.
            "rubric": [{
                "id": f"RC-{i + 1:02d}",
                "description": ("Full marks require correct application with justification "
                                "citing concrete evidence, scored 0-3."),
                "evidence_type": types[i % 3],
                "levels": {"excellent": "all criteria met", "satisfactory": "most met",
                           "needs_improvement": "few met"},
            }],
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
         "learner_cognitive_process": "apply", "prerequisite_activities": [1]},   # by POSITION: the harness names the ids
        {"id": "TLA-03", "activity_name": "Design review", "duration": "60m",
         "description": "Critique a provided design against SOLID principles.", "materials_needed": "A design checklist and a sample design to critique.",
         "aligned_objectives": ["ILO-04", "ILO-05"], "prepares_for_assessment": ["AT-04", "AT-05", "AT-09", "AT-10"],
         "learner_cognitive_process": "evaluate", "prerequisite_activities": [2]},
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
    # The single arm's ReAct blocks come FIRST: that agent has no Developers,
    # so its stage block shows the plan schema AND the item schemas, and the
    # dispatch-only entries below would otherwise out-match and answer with a
    # plan the loop can never close the stage on.
    (('"pilot_data_plan"', '"instrument_sets"', '"assessment_tools"'),
     {**_ASSESSMENT_PLAN, **_ASSESSMENT_DEV_PLAN, **_ASSESSMENT_ITEMS}),
    (('"non_instructional_strategies"', '"activity_blocks"', '"learning_activities"'),
     {**_ACTIVITY_PLAN, **_ACTIVITY_DEV_PLAN, **_ACTIVITIES}),
    (('"media_selections"', '"learner_materials"', '"content_modules"'),
     {**_MODULES, **_MATERIALS}),
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
    (('"instructor_orientation"',), _IMPLEMENTATION),
)


def _payload_for_system(system_prompt: str, whole: str = "") -> dict:
    """The canned payload a prompt is asking for.

    Keyed on the prompt's SCHEMA, never on its persona sentence: the single
    arm replaces that sentence, so a persona-keyed fixture silently stops
    recognising every step there, returns {} and turns the whole single-mode
    suite into a test of the regen loop."""
    for keys, payload in _PAYLOAD_BY_SCHEMA_KEY:
        if all(key in system_prompt for key in keys):
            # Ids are scraped from the WHOLE conversation, not from the slice
            # the schema was matched in: the schema arrives as a `stage_brief`
            # tool result now, and the ids a plan refers to are back in the
            # stage turn's docket.
            return _named_from_prompt(payload, whole or system_prompt)
    return {}


#: `*_ids` fields whose values a real model can only get by READING the
#: artifacts it is referring to, and the prefix those artifacts carry.
_ID_REFERENCE_FIELDS = {"activity_ids": "TLA", "material_ids": "MAT"}


def _named_from_prompt(payload: dict, prompt: str) -> dict:
    """Replace canned id references with ids this prompt actually showed.

    The implementation plan names the activities it schedules and the
    materials it hands out (P10/P11), and the canned payload names ``TLA-01``
    because that is what the rulebook's schema example shows. A real
    ImplementationPlanner does not work from the example: it can read
    ACTIVITY and MATERIAL, and its docket lists the P10/P11 gaps by id, so it
    names ids it has been shown.

    The distinction started mattering when artifact ids became composite
    (``TLA-0203`` = third artifact of the second work set, see
    ``dev_plans._composite_id``): a fixture that answers with the schema
    example is then referring to something that does not exist, and the test
    reports a harness failure that is really a fixture one."""
    found = {
        field: re.findall(rf"\b{prefix}-\d+\b", prompt)
        for field, prefix in _ID_REFERENCE_FIELDS.items()
    }
    if not any(found.values()):
        return payload

    def named(value):
        if isinstance(value, dict):
            return {key: (list(dict.fromkeys(found[key]))[:len(value[key])] or value[key])
                    if key in found and isinstance(value.get(key), list)
                    else named(value[key])
                    for key in value}
        if isinstance(value, list):
            return [named(item) for item in value]
        return value

    return named(payload)


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
            # ...each with the criterion that marks it, INSIDE the item: an
            # Assessment Developer writes both in one answer, and since
            # 2026-09-02 a criterion is a field of its item rather than a
            # parallel list with back-references. A fixture returning bare
            # items would leave that half of the design untested and silently
            # exercised by the repair net instead.
            for item in items:
                item["rubric"] = [{
                    "id": f"RC-{item['item_id']}",
                    "description": ("Full marks require correct application with justification "
                                    "citing concrete evidence, scored 0-3."),
                    "evidence_type": item["type"],
                    "levels": {"excellent": "0 absent", "satisfactory": "1 partial",
                               "needs_improvement": "2 full"},
                }]
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
    return None


class _Result:
    def __init__(self, content: str = "", tool_calls: list | None = None) -> None:
        self.content = content
        self.tool_calls = tool_calls or []
        self.usage_metadata = None


class FakeChatModel:
    """Network-free chat model that returns canned, schema-valid JSON.

    Speaks BOTH transports: bound with tools (every stage loop) it answers
    with one ``submit`` call carrying the canned payload; unbound (a caller
    that binds nothing) it answers with the same payload as JSON text."""

    def __init__(self) -> None:
        self._tools_bound = False
        self._calls = 0

    def bind(self, **_kwargs) -> "FakeChatModel":
        return self

    def bind_tools(self, specs, **_kwargs) -> "FakeChatModel":
        bound = copy.copy(self)
        bound._tools_bound = True
        # Which submits the caller is offering. A stage loop binds one
        # `submit_<artifact>` per top-level artifact of that stage; the single
        # arm's ReAct loop binds a `submit_<stage>` per INCOMPLETE stage. The
        # names have the same shape either way, so the arms are told apart by
        # `stage_brief`'s SIGNATURE — see below.
        names = tuple(str(spec.get("function", {}).get("name", ""))
                      for spec in (specs or []))
        bound._bound = names
        bound._submits = tuple(n for n in names if n.startswith("submit"))
        # BOTH arms bind `stage_brief` now — the artifact contract is fetched,
        # not pushed. They are told apart by its parameters: the ReAct loop
        # works all six stages so its version takes one, while a stage loop is
        # already in its stage and takes none.
        bound._react = any(
            spec.get("function", {}).get("name") == "stage_brief"
            and (spec.get("function", {}).get("parameters", {}).get("properties"))
            for spec in (specs or []))
        return bound

    def invoke(self, messages):
        # The WHOLE conversation, not just the system turn: the single-agent
        # arm keeps one stable persona in `system` and varies the task and
        # schema in `user`, so a system-only fixture sees no schema at all and
        # returns {} for every one of its steps.
        raw_prompt = "\n".join(
            m.get("content", "") for m in messages
            if isinstance(m, dict) and isinstance(m.get("content"), str)
        )
        #: Kept untruncated: the schema is matched in the slice from the last
        #: stage marker, but the ids a plan refers to live in the stage turn's
        #: docket, which is behind it.
        raw_all = raw_prompt
        # ...but only from the CURRENT stage onward when the transcript carries
        # several. The agentic single arm accumulates every stage in one
        # conversation, so matching over the whole thing makes the earliest
        # stage's schema out-match the live one and the fake answers the wrong
        # artifact — a fixture artifact that would masquerade as exactly the
        # context degradation the decomposition axis is meant to measure.
        marker = raw_prompt.rfind("--- STAGE:")
        if marker != -1:
            raw_prompt = raw_prompt[marker:]
        # A Developer's own work-set slice, read from the RAW prompt (the
        # generic stripping below would remove "=== YOUR ASSIGNED SET/BLOCK
        # ===" along with every other non-SCENARIO header) — checked first so
        # a fan-out worker gets only the items its own set asked for, never
        # the whole family's canned list.
        sliced = _sliced_payload_for_set(raw_prompt)
        if sliced is not None:
            name, args = self._stage_submit(sliced, messages)
            return self._respond(args, name)
        # Strip injected prior-artifact context ("=== <HEADER> ===\n...\n\n===
        # SCENARIO ===") before matching: the prose arm injects earlier
        # documents as VERBATIM JSON, so their schema keys would otherwise
        # out-match the schema this step is actually asking for (the graph
        # arm's plan-node JSON leaks keys the same way — it just happened to
        # land on merged entries). Only the task/schema text may key payloads.
        stage = self._react_stage()
        if stage is not None:
            whole = "\n".join(str(m.get("content", "")) for m in messages
                               if isinstance(m, dict))
            if f"--- STAGE: {stage} ---" not in whole:
                # The schema lives behind `stage_brief` now, so ask for it —
                # which is what the loop's protocol tells a real agent to do.
                self._calls += 1
                return _Result(tool_calls=[{"name": "stage_brief",
                                            "args": {"stage": stage},
                                            "id": f"c{self._calls}"}])
            # ReAct mode: the whole workflow is in the system turn, so match on
            # the chosen stage's block alone. Matching the lot would let the
            # first stage's schema answer for every one of them.
            block = re.search(rf"--- STAGE: {stage} ---(.*?)(?=--- STAGE: |=== SCENARIO ===|\Z)",
                              whole, flags=re.S)
            payload = _payload_for_system(block.group(1) if block else raw_prompt)
            return self._respond(payload, f"submit_{stage}")
        prompt = re.sub(r"=== (?!SCENARIO)[^=]+? ===.*?(?==== SCENARIO ===)", "", raw_prompt, flags=re.S)
        payload = _payload_for_system(prompt, raw_all)
        if not payload and "stage_brief" in getattr(self, "_bound", ()):
            # The schema is behind a tool now, for both arms: a stage turn
            # carries the task and the contract is fetched. A real agent is
            # told to call `stage_brief` before it submits, so the fixture does
            # the same rather than answering a prompt it has not read yet.
            self._calls += 1
            return _Result(tool_calls=[{"name": "stage_brief", "args": {},
                                        "id": f"c{self._calls}"}])
        name, args = self._stage_submit(payload, messages)
        return self._respond(args, name)

    def _react_stage(self):
        """The first still-open stage, or None when this is a stage loop."""
        if not getattr(self, "_react", False):
            return None
        staged = [n[len("submit_"):] for n in getattr(self, "_submits", ())
                  if n.startswith("submit_")]
        return staged[0] if staged else None

    def _stage_submit(self, payload: dict, messages: list) -> tuple[str, dict]:
        """ONE artifact per call, which is what a stage loop now binds.

        The fixture answers like an agent working through the list: the first
        offered ``submit_<key>`` whose artifact this payload carries and which
        this conversation has not already sent. Sending them all at once is
        exactly what the split exists to stop, so the fake must not do it
        either — otherwise every parts-completion path goes untested."""
        already = {m.get("name") for m in messages
                   if isinstance(m, dict) and m.get("role") == "tool"}
        for name in getattr(self, "_submits", ()):
            key = name[len("submit_"):]
            if key in payload and name not in already:
                return name, {key: payload[key]}
        # Nothing left to add: answer the first offered submit with what it
        # asks for, so the loop still gets a well-formed call to judge.
        name = (getattr(self, "_submits", ()) or ("submit",))[0]
        key = name[len("submit_"):]
        return name, ({key: payload[key]} if key in payload else payload)

    def _respond(self, payload, tool: str = "submit") -> _Result:
        if not self._tools_bound:
            return _Result(content=json.dumps(payload, ensure_ascii=False))
        self._calls += 1
        return _Result(tool_calls=[{"name": tool, "args": payload,
                                    "id": f"c{self._calls}"}])


@pytest.fixture
def fake_llm_factory():
    return lambda: FakeChatModel()


@pytest.fixture
def fake_config(fake_llm_factory):
    config = HarnessRunConfig()
    config.llm_factory = fake_llm_factory
    return config


def run_brief(brief: DesignBrief, config: HarnessRunConfig, *, on_event=None) -> dict:
    """Run one brief through the public entry point.

    A terse call site for the ~70 places this suite runs the harness, and
    nothing more: the package's entry point is ``MetaAgent`` and this calls
    exactly it. It is deliberately NOT a re-export of the old
    ``run_design_brief``, which was removed from the package 2026-09-05
    for being a passthrough — a convenience the tests want is not a reason to keep
    one in the shipped API.
    """
    return MetaAgent(config).run(brief, on_event=on_event)


def load_brief(name: str) -> DesignBrief:
    payload = json.loads((FIXTURES / name).read_text(encoding="utf-8"))
    return DesignBrief.model_validate(payload)


_EVENT_ACTIONS = {
    # Mirrors `_RECOVERY_ACTIONS` in core/trajectory.py.
    "recovery": {
        "retry", "regen_empty_section", "agent_error", "llm_error", "salvage_truncated",
        "invalid_action", "submit_rejected", "submit_invalid_final", "repeated_tool_call",
        "commit_invalid_section", "agentic_fallback", "agentic_gave_up", "budget_exhausted",
        "tool_binding_unavailable", "tool_call_markup_recovered", "repair_unfilled",
    "duplicate_submit", "bare_artifact_wrapped", "context_compacted",
    "duplicate_element_dropped",
        "dropped_argument", "repair",
    },
    #: A generative repair that asked the model for the missing artifact and got
    #: nothing usable, so it wrote nothing. Its own group: it is the opposite of
    #: a `repair`, and counting the two together would hide exactly the number
    #: this distinction exists to expose.
    "repair_unfilled": {"repair_unfilled"},
    "reconcile": {"reconcile"},
    "converge": {"converge"},
    "node_edit": {"node_add", "node_update"},
    "validation": {"validate"},
    "check": {"check"},
    "repair": {"repair"},
    "retrieval": {"retrieval"},
}


def events_of(trajectory: dict, event_type: str) -> list[dict]:
    """Filter the unified event log by a named taxonomy group for tests."""
    return [e for e in trajectory["events"] if e["action"] in _EVENT_ACTIONS[event_type]]


class RepairActor:
    """The surface ``repairs.context_for`` needs, without a full agent object.

    The six specialist Designers went with the StateGraph pipeline on
    2026-09-01, but a handful of verifier tests only ever used one as a way to
    build a :class:`RepairContext` and name an actor. This is that, and nothing
    else: the repair toolbox itself is unchanged and shared by both context
    modes."""

    def __init__(self, name: str, config=None, graph=None, store=None, trajectory=None):
        self._name = name
        self.graph = graph
        self.store = store
        self.trajectory = trajectory

    def ctx(self):
        """A :class:`RepairContext` naming this actor. Built directly rather
        than through ``repairs.context_for``, which reads the actor off the
        class name — a real agent's identity, which this is standing in for."""
        from alignmentgraph_isd.core.repairs import RepairContext

        return RepairContext(graph=self.graph, store=self.store,
                             trajectory=self.trajectory, actor=self._name)

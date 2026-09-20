"""A deliberately broken design, built to make every check speak.

Its only job is to be the fixed input the golden fixture pins check MESSAGES
against (``tests/regen_golden_prompts.py``). Those messages are rendered
verbatim into a user turn by ``loop.repair_request`` for both arms, so they
are prompt surface exactly like a persona or a tool schema — and until
2026-09-04 they were the only prompt surface nothing pinned. A reworded check
could change what every agent was asked to fix without turning a single test
red.

Every flaw here is deliberate and is annotated with the check it provokes.
Keep it broken.
"""
from __future__ import annotations

from alignmentgraph_isd.core.alignment_graph import AlignmentGraph, NodeType, alignment


def broken_graph() -> AlignmentGraph:
    graph = AlignmentGraph()

    # ── objectives: one clean, four each breaking a different Bloom rule ─────
    graph.add_element_node(NodeType.OBJECTIVE, "ILO-01", {
        "id": "ILO-01", "level": "apply", "bloom_verb": "apply",
        "statement": "Apply inheritance to a domain model, given a starter "
                     "codebase, with at least 80% of unit tests passing.",
    })
    # bloom: no verb at all
    graph.add_element_node(NodeType.OBJECTIVE, "ILO-02", {
        "id": "ILO-02", "level": "analyze",
        "statement": "Analyze a class design and identify coupling issues.",
    })
    # bloom: a verb in none of the six levels
    graph.add_element_node(NodeType.OBJECTIVE, "ILO-03", {
        "id": "ILO-03", "level": "evaluate", "bloom_verb": "grok",
        "statement": "Grok the trade-offs between composition and inheritance.",
    })
    # bloom: a level outside the taxonomy
    graph.add_element_node(NodeType.OBJECTIVE, "ILO-04", {
        "id": "ILO-04", "level": "synthesis", "bloom_verb": "design",
        "statement": "Design a module boundary for a given service.",
    })
    # bloom: verb and level name different processes; measurability: no criterion
    graph.add_element_node(NodeType.OBJECTIVE, "ILO-05", {
        "id": "ILO-05", "level": "create", "bloom_verb": "recall",
        "statement": "Recall the four pillars of OOP.",
    })

    # ── assessment: a plan promising more than the items realise ─────────────
    graph.add_node(NodeType.ASSESSMENT_PLAN, graph.section_id(NodeType.ASSESSMENT_PLAN), {
        "summative": ["Final design project"],
        # evaluation_quality: formative intent with no method, and no pilot plan
        "formative": ["Weekly critique"],
        "formative_methods": [],
        "pilot_data_plan": {},
        # plan_coverage: two promises, one item
        "lo_coverage_targets": {"ILO-01": ["summative", "diagnostic"]},
        # blueprint_consistency: a formative quiz the targets never promised,
        # in a module that does not exist, covering an objective that does not
        "sets": [
            {"id": "SET-01", "module_id": "MOD-01", "timing": "summative", "format": "quiz",
             "item_counts": {"multiple_choice": 10}, "covers_objectives": ["ILO-01"]},
            {"id": "SET-02", "module_id": "MOD-07", "timing": "formative", "format": "quiz",
             "item_counts": {"short_answer": 3}, "covers_objectives": ["ILO-01", "ILO-09"]},
        ],
    })
    # bloom_mismatch_assessment: an Apply objective measured by an item that
    # only claims Remember. (Note `_item_capability` lets the item's own claim
    # WIN over its format, so a multiple_choice item asserting "apply" passes
    # this check — the honest low claim is what makes the mismatch visible.)
    # item_completeness: a choice item with no options and no answer key
    # The assessment ELEMENT is the TASK; the item lives inside it, so its
    # membership and its plan category cannot be wrong any more.
    graph.add_element_node(NodeType.ASSESSMENT, "AT-01", {
        "id": "AT-01", "module_id": "MOD-01", "timing": "summative",
        "items": [{
        "item_id": "ATI-0101", "type": "multiple_choice",
        "question": "Which of these is inheritance?",
        "aligned_objective": "ILO-01", "plan_category": "summative",
        "required_cognitive_process": "remember",
        "scoring_criteria": "One mark for the correct option.",
        # evidence_alignment: a criterion asking for evidence the item cannot give
        "rubric": [{"id": "RC-01", "description": "Learner justifies the design in prose.",
                    "evidence_type": "performance_task",
                    "levels": {"excellent": "full", "satisfactory": "partial",
                               "needs_improvement": "none"}}],
        }],
    })

    # ── activities: one, at the wrong level, leaving objectives unpractised ──
    graph.add_node(NodeType.ACTIVITY_PLAN, graph.section_id(NodeType.ACTIVITY_PLAN), {
        "instructional_strategies": {"model": "Gagné's 9 Events"},
    })
    # bloom_mismatch_activity: an Apply objective rehearsed by a lecture
    graph.add_element_node(NodeType.ACTIVITY, "TLA-0101", {
        "id": "TLA-0101", "activity_name": "Lecture on inheritance",
        "description": "The instructor presents inheritance.",
        "aligned_objectives": ["ILO-01"], "learner_cognitive_process": "understand",
        # P13: an activity naming a module that does not exist
        "module_id": "MOD-99",
    })

    # ── modules: one that groups a single objective and that nothing is taught
    # or assessed in (P12 for the other four objectives, P13, P14, P7) ────────
    graph.add_element_node(NodeType.MODULE, "MOD-01", {
        "id": "MOD-01", "title": "Inheritance", "objectives": ["ILO-01"], "minutes": 120,
    })
    alignment.record_provenance(graph, "P12", ["module:MOD-01"], "objective:ILO-01")
    # P5: a material whose module does not exist
    graph.add_element_node(NodeType.MATERIAL, "MAT-0101", {
        "id": "MAT-0101", "title": "Slides", "type": "slides",
        "linked_module": "MOD-99",
    })

    # ── implementation: present but empty where it has to be concrete ────────
    graph.add_node(NodeType.IMPLEMENTATION_PLAN, graph.section_id(NodeType.IMPLEMENTATION_PLAN), {
        # actionability: two sections, both hollow — and note they land on ONE
        # node_id, told apart only by metadata["section"].
        "instructor_orientation": {"competency_checklist": [], "materials": []},
        "system_check": {"checklist": []},
    })

    # The relations the design DOES support, so relation_coverage reports the
    # real gaps rather than "nothing was ever established".
    alignment.match_id_reverse(graph, "C2", field="aligned_objective")
    # C3 is an id-LIST relation ("id-list-reverse" in REGISTRY), so it needs
    # match_list_reverse — match_id_reverse reads the field as a scalar and
    # silently establishes nothing.
    alignment.match_list_reverse(graph, "C3", field="aligned_objectives")
    return graph

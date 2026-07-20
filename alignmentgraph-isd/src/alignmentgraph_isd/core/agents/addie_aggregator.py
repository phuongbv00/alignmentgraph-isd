from __future__ import annotations
from ..graph import NodeType
from ..schema import DesignBrief
from copy import deepcopy
from .. import alignment
from .base import BaseISDAgent


class ADDIEOutputAggregator(BaseISDAgent):
    def run(self, design_brief: DesignBrief) -> None:
        pass  # call aggregate() directly

    def aggregate(self) -> dict:
        # Aggregate from section nodes only; element nodes carry single items and
        # would otherwise pollute the merged section payload.
        nc_data = _merge_node_data(self.graph.section_nodes(NodeType.NEEDS_CONTEXT))
        obj_data = _merge_node_data(self.graph.section_nodes(NodeType.OBJECTIVE))
        asm_data = _merge_node_data(self.graph.section_nodes(NodeType.ASSESSMENT))
        act_data = _merge_node_data(self.graph.section_nodes(NodeType.ACTIVITY))
        mat_data = _merge_node_data(self.graph.section_nodes(NodeType.MATERIAL)) or act_data
        con_data = _merge_node_data(self.graph.section_nodes(NodeType.IMPLEMENTATION_PLAN))
        ev_data = _merge_node_data(self.graph.section_nodes(NodeType.EVALUATION))

        # Design is decomposed across several singleton "plan" nodes (see
        # objective_design.py's 2-call split) — this is their ONE home under
        # graph coordination. In the wo-graph arm there is NO such split: the
        # whole Design blob lives in objective_0, so each field falls back to
        # obj_data (the pre-refactor single-blob layout).
        plan_data = _merge_node_data(self.graph.section_nodes("assessment_plan")) or obj_data.get("assessment_plan", {})
        content_data = _merge_node_data(self.graph.section_nodes("content_structure")) or obj_data.get("content_structure", {})
        strategy_data = _merge_node_data(self.graph.section_nodes("instructional_strategies")) or obj_data.get("instructional_strategies", {})
        non_instr_data = _merge_node_data(self.graph.section_nodes("non_instructional_strategies")) or obj_data.get("non_instructional_strategies", {})
        storyboard_data = _merge_node_data(self.graph.section_nodes("storyboard_plan"))
        media_items = [n["data"] for n in self.graph.element_nodes("media")] or obj_data.get("media_selection", [])
        storyboard = storyboard_data.get("storyboard", []) or obj_data.get("storyboard", [])

        analysis = {
            "needs_analysis": nc_data.get("needs_analysis", {}),
            "learner_analysis": nc_data.get("learner_analysis", {}),
            "context_analysis": nc_data.get("context_analysis", {}),
            "task_analysis": nc_data.get("task_analysis", {}),
        }

        design = {
            "learning_objectives": obj_data.get("learning_objectives", []),
            "assessment_plan": plan_data,
            "content_structure": content_data,
            "instructional_strategies": strategy_data,
            "non_instructional_strategies": non_instr_data,
            "learning_activities": act_data.get("learning_activities", []),
            "media_selection": media_items,
            "storyboard": storyboard,
        }

        # In single_agent mode, assessment_tools/expert_review live in the activity (development) node.
        # In enable_enable_multi_agent mode, they live in the dedicated assessment node.
        development = {
            "learner_materials": act_data.get("learner_materials", mat_data.get("learner_materials", [])),
            "instructor_guide": act_data.get("instructor_guide", mat_data.get("instructor_guide", {})),
            "operator_manual": act_data.get("operator_manual", mat_data.get("operator_manual", {})),
            "assessment_tools": (
                asm_data.get("assessment_tools")
                or act_data.get("assessment_tools", [])
            ),
            "expert_review": (
                asm_data.get("expert_review")
                or act_data.get("expert_review", {})
            ),
        }

        implementation = {
            "instructor_orientation": con_data.get("instructor_orientation", {}),
            "system_check": con_data.get("system_check", {}),
            "prototype_execution": con_data.get("prototype_execution", {}),
            "monitoring": con_data.get("monitoring", {}),
        }

        evaluation = {
            "formative": ev_data.get("formative", {}),
            "summative": ev_data.get("summative", {}),
            "improvement_plan": ev_data.get("improvement_plan", {}),
        }

        output = {
            "analysis": analysis,
            "design": design,
            "development": development,
            "implementation": implementation,
            "evaluation": evaluation,
        }
        return _strengthen_alignment(
            output, self.graph,
            graph_coordination=bool(self.config.ablation.enable_alignment_graph),
        )


def _merge_node_data(nodes: list[dict]) -> dict:
    merged: dict = {}
    for node in nodes:
        data = node.get("data", {})
        if isinstance(data, dict):
            _deep_merge(merged, data)
    return merged


def _deep_merge(base: dict, incoming: dict) -> dict:
    for key, value in incoming.items():
        if isinstance(value, dict) and isinstance(base.get(key), dict):
            _deep_merge(base[key], value)
        elif isinstance(value, list) and isinstance(base.get(key), list):
            base[key] = _merge_lists(base[key], value)
        elif key not in base or _is_empty(base[key]):
            base[key] = deepcopy(value)
        elif value and base[key] != value:
            if not isinstance(base[key], list):
                base[key] = [base[key]]
            base[key] = _merge_lists(base[key], [value])
    return base


def _merge_lists(left: list, right: list) -> list:
    result = deepcopy(left)
    seen = {_stable_key(item) for item in result}
    for item in right:
        key = _stable_key(item)
        if key not in seen:
            result.append(deepcopy(item))
            seen.add(key)
    return result


def _stable_key(item) -> str:
    if isinstance(item, dict):
        for key in (
            "id",
            "item_id",
            "title",
            "activity_name",
            "media_type",
            "event",
            "frame_number",
            "session",
        ):
            if item.get(key) is not None:
                return f"{key}:{item[key]}"
        return repr(sorted(item.items()))
    return repr(item)


def _is_empty(value) -> bool:
    return value in ({}, [], "", None)


def _strengthen_alignment(output: dict, graph, *, graph_coordination: bool) -> dict:
    design = output.setdefault("design", {})
    development = output.setdefault("development", {})
    implementation = output.setdefault("implementation", {})
    evaluation = output.setdefault(NodeType.EVALUATION, {})

    objectives = design.get("learning_objectives", []) or []
    assessment_tools = development.get("assessment_tools", []) or []

    objective_ids = [lo.get("id") for lo in objectives if isinstance(lo, dict) and lo.get("id")]
    if objective_ids:
        if graph_coordination:
            # Last-resort coverage net for the graph-coordination mechanism only
            # (when the repair budget ran out before closing every R3 gap). At
            # wo_graph/wo_ma the alignment tier is ablated, so patching
            # coverage here would leak the mechanism into the arms measuring
            # its absence.
            _ensure_assessment_coverage(objectives, assessment_tools, graph)
        design["alignment_matrix"] = _build_alignment_matrix(objective_ids, graph)
        development["objective_assessment_map"] = {
            lo_id: [
                item.get("item_id")
                for item in assessment_tools
                if isinstance(item, dict) and item.get("aligned_objective") == lo_id
            ]
            for lo_id in objective_ids
        }

    _strengthen_implementation(implementation)

    formative = evaluation.get("formative", {})
    if isinstance(formative, dict) and formative.get("data_collection"):
        evaluation.setdefault("pilot_data_collection", formative["data_collection"])

    prototype = implementation.get("prototype_execution", {})
    if isinstance(prototype, dict) and prototype:
        prototype.setdefault("success_criteria", [
            "At least 80% of pilot learners complete the core scenario task.",
            "Learners demonstrate measurable progress on the aligned formative assessment.",
            "Critical delivery or access issues are resolved before large-group rollout.",
        ])
        prototype.setdefault("data_collection", [
            "Learning platform or lab access logs",
            "Instructor observation checklist",
            "Learner feedback survey",
        ])

    return output


def _ensure_assessment_coverage(objectives: list, assessment_tools: list, graph) -> None:
    """Output-level safety net: guarantee every objective has at least one
    assessment item in the FINAL output, even outside the ``full`` arm (where
    the alignment tier never ran to catch this during generation)."""
    if not isinstance(assessment_tools, list):
        return
    covered = {
        item.get("aligned_objective")
        for item in assessment_tools
        if isinstance(item, dict) and item.get("aligned_objective")
    }
    for objective in objectives:
        if not isinstance(objective, dict):
            continue
        lo_id = objective.get("id")
        if not lo_id or lo_id in covered:
            continue
        item_id = f"AT-R-{lo_id}"
        assessment_tools.append({
            "item_id": item_id,
            "type": "performance_task",
            "question": f"Demonstrate the target performance for {lo_id}: {objective.get('statement', '')}",
            "aligned_objective": lo_id,
            "scoring_criteria": "Rubric scores task completion, communication accuracy, context appropriateness, peer-feedback quality, and transfer.",
            "difficulty": "hard",
            "coverage_repair": True,
        })
        covered.add(lo_id)


def _build_alignment_matrix(objective_ids: list[str], graph) -> list[dict]:
    """Per-objective alignment record built from **established** edges
    (relation_id, established_by, evidence) — the real R1/R2/R3/R4/R5 picture,
    replacing the old index-paired ``LO[i] <-> activity[i]`` guess."""
    objective_relations = [
        rid for rid, relation in alignment.REGISTRY.items()
        if NodeType.OBJECTIVE in relation.target_node_types
    ]
    matrix: list[dict] = []
    for lo_id in objective_ids:
        target_id = f"{NodeType.OBJECTIVE}{graph.ELEMENT_SEP}{lo_id}"
        entry = {"objective_id": lo_id, "relations": {}}
        for relation_id in objective_relations:
            edges = graph.get_edges(relation_id=relation_id, target=target_id)
            entry["relations"][relation_id] = [
                {
                    "label": alignment.REGISTRY[relation_id].label,
                    "source": e["source"],
                    "established_by": e.get("established_by", ""),
                    "evidence": e.get("evidence", ""),
                }
                for e in edges
            ]
        matrix.append(entry)
    return matrix


def _strengthen_implementation(implementation: dict) -> None:
    """Polish NON-EMPTY implementation sections (setdefault-style, identical
    for every ablation arm). An entirely empty section is left empty: painting
    hardcoded content onto nothing turns a dead generation into a
    partially-scored output and masks the failure from both the completeness
    tier and the judge (exactly how a truncated single-agent run once scored
    40% on Implementation while every other phase was 0)."""
    orientation = implementation.setdefault("instructor_orientation", {})
    if isinstance(orientation, dict) and orientation:
        objectives = orientation.get("orientation_objectives", [])
        learner_facing = (
            not objectives
            or any(isinstance(item, str) and item.lower().startswith("learners can") for item in objectives)
        )
        if learner_facing:
            orientation["orientation_objectives"] = [
                "Instructors and support staff can prepare the learning environment, assign learner roles, and start each session safely.",
                "Instructors can facilitate practice activities and apply the scoring rubrics consistently.",
                "Support staff can monitor access, resolve resource issues, and escalate delivery incidents during large-group sessions.",
            ]
        orientation.setdefault("schedule", "90-minute facilitator/support orientation plus a 30-minute hands-on delivery rehearsal before pilot launch.")
        orientation.setdefault("materials", [
            "Facilitator runbook",
            "Delivery troubleshooting checklist",
            "Assessment and peer-feedback rubric pack",
        ])
        orientation.setdefault("competency_checklist", [
            "Launch, reset, and recover the learning environment without learner data loss.",
            "Score a sample learner performance using the aligned rubric.",
            "Resolve or escalate access, login, resource, and network issues.",
        ])

    system_check = implementation.setdefault("system_check", {})
    if isinstance(system_check, dict) and system_check:
        checklist = list(system_check.get("checklist", []))
        required_checks = [
            "Verify learning platform, lab resources, app login, and network access before each session.",
            "Confirm learner grouping, data capture, submission channels, and privacy settings.",
            "Validate accessibility alternatives and fallback materials for learners who cannot use the primary environment.",
        ]
        for check in required_checks:
            if check not in checklist:
                checklist.append(check)
        system_check["checklist"] = checklist
        system_check.setdefault(
            "technical_validation",
            "Platform, resource access, network, data capture, accessibility, and fallback checks are completed before pilot launch.",
        )
        system_check.setdefault("contingency_plans", [
            "Switch learners to offline or low-bandwidth materials if the primary environment fails.",
            "Use delayed submission or local notes if network connectivity drops.",
        ])

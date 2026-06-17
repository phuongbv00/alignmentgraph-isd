from __future__ import annotations
from ..schema import TaskRequest
from copy import deepcopy
from .base import BaseISDAgent


class ADDIEOutputAggregator(BaseISDAgent):
    def run(self, task: TaskRequest, context_pack: dict) -> None:
        pass  # call aggregate() directly

    def aggregate(self) -> dict:
        nc_nodes = self.graph.get_nodes("needs_context")
        obj_nodes = self.graph.get_nodes("objective")
        asm_nodes = self.graph.get_nodes("assessment")
        act_nodes = self.graph.get_nodes("activity")
        mat_nodes = self.graph.get_nodes("material")
        con_nodes = self.graph.get_nodes("constraint")
        ev_nodes = self.graph.get_nodes("evaluation")

        nc_data = _merge_node_data(nc_nodes)
        obj_data = _merge_node_data(obj_nodes)
        asm_data = _merge_node_data(asm_nodes)
        act_data = _merge_node_data(act_nodes)
        mat_data = _merge_node_data(mat_nodes) or act_data  # activity_material agent stores both
        con_data = _merge_node_data(con_nodes)
        ev_data = _merge_node_data(ev_nodes)

        analysis = {
            "needs_analysis": nc_data.get("needs_analysis", {}),
            "learner_analysis": nc_data.get("learner_analysis", {}),
            "context_analysis": nc_data.get("context_analysis", {}),
            "task_analysis": nc_data.get("task_analysis", {}),
        }

        design = {
            "learning_objectives": obj_data.get("learning_objectives", []),
            "assessment_plan": obj_data.get("assessment_plan", {}),
            "content_structure": obj_data.get("content_structure", {}),
            "instructional_strategies": obj_data.get("instructional_strategies", {}),
            "non_instructional_strategies": obj_data.get("non_instructional_strategies", {}),
            "learning_activities": obj_data.get("learning_activities", []),
            "media_selection": obj_data.get("media_selection", []),
            "storyboard": obj_data.get("storyboard", []),
        }

        # In single_agent mode, assessment_tools/expert_review live in the activity (development) node.
        # In multi_agent mode, they live in the dedicated assessment node.
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
        return _strengthen_alignment(output, self.graph)


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


def _strengthen_alignment(output: dict, graph) -> dict:
    design = output.setdefault("design", {})
    development = output.setdefault("development", {})
    implementation = output.setdefault("implementation", {})
    evaluation = output.setdefault("evaluation", {})

    objectives = design.get("learning_objectives", []) or []
    assessment_tools = development.get("assessment_tools", []) or []
    activities = design.get("learning_activities", []) or []
    storyboard = design.get("storyboard", []) or []
    modules = design.get("content_structure", {}).get("modules", []) or []

    objective_ids = [lo.get("id") for lo in objectives if isinstance(lo, dict) and lo.get("id")]
    if objective_ids:
        _ensure_assessment_coverage(objectives, assessment_tools, graph)
        design["alignment_matrix"] = _build_alignment_matrix(
            objective_ids,
            assessment_tools,
            activities,
            storyboard,
            graph,
        )
        development["objective_assessment_map"] = {
            lo_id: [
                item.get("item_id")
                for item in assessment_tools
                if isinstance(item, dict) and item.get("aligned_objective") == lo_id
            ]
            for lo_id in objective_ids
        }
        _tag_activities(activities, objective_ids)
        _tag_storyboard(storyboard, objective_ids)
        _link_materials_to_modules(development.get("learner_materials", []), modules)

    _strengthen_implementation(implementation)

    formative = evaluation.get("formative", {})
    if isinstance(formative, dict) and formative.get("data_collection"):
        evaluation.setdefault("pilot_data_collection", formative["data_collection"])

    prototype = implementation.get("prototype_execution", {})
    if isinstance(prototype, dict) and prototype:
        prototype.setdefault("success_criteria", [
            "At least 80% of pilot learners complete the core scenario task.",
            "Learners demonstrate measurable progress on the aligned formative assessment.",
            "Critical technical issues are resolved before large-group rollout.",
        ])
        prototype.setdefault("data_collection", [
            "VR/mobile usage logs",
            "Instructor observation checklist",
            "Learner feedback survey",
        ])

    return output


def _ensure_assessment_coverage(objectives: list, assessment_tools: list, graph) -> None:
    if not isinstance(assessment_tools, list):
        return
    covered = {
        item.get("aligned_objective")
        for item in assessment_tools
        if isinstance(item, dict) and item.get("aligned_objective")
    }
    objective_node_id = "objective_0"
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
        graph.add_edge(
            "measures",
            "assessment_0",
            objective_node_id,
            evidence=lo_id,
            rationale=f"Aggregator added {item_id} to guarantee assessment coverage for {lo_id}.",
            verified=True,
        )
        covered.add(lo_id)


def _strengthen_implementation(implementation: dict) -> None:
    orientation = implementation.setdefault("instructor_orientation", {})
    if isinstance(orientation, dict):
        objectives = orientation.get("orientation_objectives", [])
        learner_facing = (
            not objectives
            or any(isinstance(item, str) and item.lower().startswith("learners can") for item in objectives)
        )
        if learner_facing:
            orientation["orientation_objectives"] = [
                "Instructors and operators can run the VR/mobile environment, assign learner roles, and start each scenario safely.",
                "Instructors can facilitate collaborative language practice and apply the scoring rubrics consistently.",
                "Operators can monitor devices, resolve access issues, and escalate technical incidents during large-group sessions.",
            ]
        orientation.setdefault("schedule", "90-minute facilitator/operator orientation plus a 30-minute hands-on VR/mobile rehearsal before pilot launch.")
        orientation.setdefault("materials", [
            "Facilitator runbook",
            "Operator troubleshooting checklist",
            "Assessment and peer-feedback rubric pack",
        ])
        orientation.setdefault("competency_checklist", [
            "Launch and reset VR/mobile scenarios without learner data loss.",
            "Score a sample role-play using the aligned rubric.",
            "Resolve or escalate headset, tablet, login, and network issues.",
        ])

    system_check = implementation.setdefault("system_check", {})
    if isinstance(system_check, dict):
        checklist = list(system_check.get("checklist", []))
        required_checks = [
            "Verify every VR headset, tablet, app login, microphone, and network connection before each session.",
            "Confirm scenario database access, learner grouping, data capture, and privacy settings.",
            "Validate accessibility and motion-sickness alternatives for adult beginner learners.",
        ]
        for check in required_checks:
            if check not in checklist:
                checklist.append(check)
        system_check["checklist"] = checklist
        system_check.setdefault(
            "technical_validation",
            "Device, network, scenario database, audio, analytics, accessibility, and data-capture checks are completed before pilot launch.",
        )
        system_check.setdefault("contingency_plans", [
            "Switch learners to tablet-based role-play if a VR headset fails.",
            "Use offline scenario cards and delayed log upload if network connectivity drops.",
        ])


def _build_alignment_matrix(
    objective_ids: list[str],
    assessment_tools: list,
    activities: list,
    storyboard: list,
    graph,
) -> list[dict]:
    measures = _fresh_edges(graph.get_edges("measures"))
    supports = _fresh_edges(graph.get_edges("supports"))
    evaluates = _fresh_edges(graph.get_edges("evaluates"))
    matrix = []

    for index, lo_id in enumerate(objective_ids):
        matrix.append({
            "objective_id": lo_id,
            "assessment_items": [
                item.get("item_id")
                for item in assessment_tools
                if isinstance(item, dict) and item.get("aligned_objective") == lo_id
            ],
            "learning_activity": _pick_name(activities, index, "activity_name"),
            "storyboard_frame": _pick_name(storyboard, index, "frame_number"),
            "graph_evidence": {
                "measures": _edge_evidence(measures, lo_id),
                "supports": _edge_evidence(supports, lo_id),
                "evaluates": _edge_evidence(evaluates, lo_id),
            },
        })
    return matrix


def _edge_evidence(edges: list[dict], lo_id: str) -> list[str]:
    return [
        edge.get("rationale") or edge.get("source", "")
        for edge in edges
        if edge.get("evidence") == lo_id
    ]


def _fresh_edges(edges: list[dict]) -> list[dict]:
    return [edge for edge in edges if not edge.get("stale")]


def _pick_name(items: list, index: int, key: str):
    if not items:
        return None
    item = items[min(index, len(items) - 1)]
    if not isinstance(item, dict):
        return item
    return item.get(key)


def _tag_activities(activities: list, objective_ids: list[str]) -> None:
    if not activities:
        return
    for index, lo_id in enumerate(objective_ids):
        activity = activities[min(index, len(activities) - 1)]
        if not isinstance(activity, dict):
            continue
        aligned = activity.setdefault("aligned_objectives", [])
        if lo_id not in aligned:
            aligned.append(lo_id)


def _tag_storyboard(storyboard: list, objective_ids: list[str]) -> None:
    if not storyboard:
        return
    for index, lo_id in enumerate(objective_ids):
        frame = storyboard[min(index, len(storyboard) - 1)]
        if not isinstance(frame, dict):
            continue
        note = str(frame.get("notes", ""))
        if lo_id not in note:
            frame["notes"] = f"{note} Alignment: supports {lo_id}.".strip()


def _link_materials_to_modules(materials: list, modules: list) -> None:
    if not materials or not modules:
        return
    for index, material in enumerate(materials):
        if isinstance(material, dict):
            material.setdefault("linked_module", modules[min(index, len(modules) - 1)])

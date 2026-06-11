from __future__ import annotations
from .base import BaseISDAgent


class ADDIEOutputAggregator(BaseISDAgent):
    def run(self, scenario: dict, context_pack: dict) -> None:
        pass  # call aggregate() directly

    def aggregate(self) -> dict:
        nc_nodes = self.graph.get_nodes("needs_context")
        obj_nodes = self.graph.get_nodes("objective")
        asm_nodes = self.graph.get_nodes("assessment")
        act_nodes = self.graph.get_nodes("activity")
        mat_nodes = self.graph.get_nodes("material")
        con_nodes = self.graph.get_nodes("constraint")
        ev_nodes = self.graph.get_nodes("evaluation")

        nc_data = nc_nodes[0]["data"] if nc_nodes else {}
        obj_data = obj_nodes[0]["data"] if obj_nodes else {}
        asm_data = asm_nodes[0]["data"] if asm_nodes else {}
        act_data = act_nodes[0]["data"] if act_nodes else {}
        mat_data = mat_nodes[0]["data"] if mat_nodes else act_data  # activity_material agent stores both
        con_data = con_nodes[0]["data"] if con_nodes else {}
        ev_data = ev_nodes[0]["data"] if ev_nodes else {}

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

        return {
            "analysis": analysis,
            "design": design,
            "development": development,
            "implementation": implementation,
            "evaluation": evaluation,
        }

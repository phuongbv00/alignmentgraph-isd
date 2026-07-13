"""Reusable LangGraph node factories shared by every workflow.

A ``NodeFactory`` captures the per-run objects (config, graph, trajectory,
context pack, design brief) and exposes each ISD step as a node function. The
per-arm workflow modules (``workflows/full.py`` etc.) wire these nodes into a
StateGraph explicitly — the factory contains NO ablation branching, so which
mechanisms run is decided entirely by which nodes a workflow wires.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Annotated, TypedDict
import operator

from .audit import GraphAuditor
from .planner import ISDTaskPlanner
from .task_graph import TaskGraphBuilder
from .validation import validate_addie
from .agents.needs_context import NeedsContextAgent
from .agents.objective_design import ObjectiveDesignAgent
from .agents.assessment_design import AssessmentDesignAgent
from .agents.activity_material import ActivityMaterialAgent
from .agents.implementation_plan import ImplementationPlanAgent
from .agents.evaluation_revision import EvaluationRevisionAgent
from .agents.single_agent import SingleAgent
from .agents.pedagogical_verifier import PedagogicalVerifierAgent
from .agents.addie_aggregator import ADDIEOutputAggregator

_SCHEMA_PATH = Path(__file__).parent / "schema" / "addie_output.json"


# ── LangGraph state ────────────────────────────────────────────────────────────
# Only plain JSON-serializable types live here so MemorySaver can checkpoint them.
# Non-serializable objects (config, graph, trajectory, brief) are captured by the
# NodeFactory and never placed in state.

class ISDState(TypedDict):
    violations: list[dict]          # serialized VerifierViolation dicts
    addie_output: dict
    errors: Annotated[list[str], operator.add]
    audit: dict
    pending_tasks: list[dict]
    next_task: str
    task_attempts: dict[str, int]
    planner_decisions: Annotated[list[dict], operator.add]
    needs_verification: bool
    repair_rounds: int
    validation_errors: list[str]


# Generation specialists in fixed ADDIE order (node name -> agent class).
GENERATION_AGENTS: dict[str, type] = {
    "needs_context": NeedsContextAgent,
    "objective_design": ObjectiveDesignAgent,
    "assessment_design": AssessmentDesignAgent,
    "activity_material": ActivityMaterialAgent,
    "implementation_plan": ImplementationPlanAgent,
    "evaluation_revision": EvaluationRevisionAgent,
}


class NodeFactory:
    """Builds node functions bound to one run's objects. No ablation flags."""

    def __init__(self, config, graph, trajectory, context_pack, design_brief) -> None:
        self.config = config
        self.graph = graph
        self.trajectory = trajectory
        self.context_pack = context_pack
        self.design_brief = design_brief
        self.task_planner = ISDTaskPlanner.from_config(config)

    # ── shared helpers ──────────────────────────────────────────────────────
    def _args(self):
        return self.config, self.graph, self.trajectory

    @staticmethod
    def _bump_attempt(state: ISDState, task_name: str) -> dict[str, int]:
        attempts = dict(state.get("task_attempts", {}) or {})
        attempts[task_name] = attempts.get(task_name, 0) + 1
        return attempts

    def _generation_done(self, state: ISDState, task_name: str) -> dict:
        return {"task_attempts": self._bump_attempt(state, task_name), "needs_verification": True}

    @staticmethod
    def _violation_to_dict(v) -> dict:
        return {
            "node_id": v.node_id, "edge_type": v.edge_type, "type": v.violation_type,
            "msg": v.message, "severity": v.severity, "repair_hint": v.repair_hint,
            "metadata": v.metadata,
        }

    def _violations_from_state(self, state: ISDState):
        from .agents.pedagogical_verifier import VerifierViolation
        return [
            VerifierViolation(
                node_id=v["node_id"], edge_type=v.get("edge_type", ""), message=v["msg"],
                violation_type=v["type"], severity=v["severity"],
                repair_hint=v.get("repair_hint", ""), metadata=v.get("metadata", {}),
            )
            for v in state.get("violations", [])
        ]

    # ── generation nodes ────────────────────────────────────────────────────
    def generation_node(self, node_name: str):
        agent_cls = GENERATION_AGENTS[node_name]

        def _node(state: ISDState) -> dict:
            try:
                agent_cls(*self._args()).run(self.design_brief, self.context_pack)
            except Exception as exc:
                return {"errors": [f"{agent_cls.__name__}: {exc}"],
                        "task_attempts": self._bump_attempt(state, node_name)}
            return self._generation_done(state, node_name)
        return _node

    def single_agent_node(self):
        def _node(state: ISDState) -> dict:
            try:
                SingleAgent(*self._args()).run(self.design_brief, self.context_pack)
            except Exception as exc:
                return {"errors": [f"SingleAgent: {exc}"],
                        "task_attempts": self._bump_attempt(state, "single_agent")}
            return self._generation_done(state, "single_agent")
        return _node

    # ── per-agent quality-control node (verify owned types + repair) ─────────
    def qc_node(self, agent_cls, task_name: str, budget: int = 2):
        """Verify the checks ``agent_cls`` owns and let it repair them, in place,
        up to ``budget`` rounds. This is the quality-control tool a specialist
        owns; a workflow includes it (full/wo_ma) or omits it (wo_qc)."""
        owned_types = agent_cls.OWNED_VIOLATION_TYPES

        def _node(state: ISDState) -> dict:
            agent = agent_cls(*self._args())
            for _ in range(max(1, budget)):
                violations = PedagogicalVerifierAgent(*self._args()).verify(self.design_brief)
                owned = [v for v in violations if v.violation_type in owned_types]
                self.trajectory.log_verifier_result([
                    {"node_id": v.node_id, "type": v.violation_type, "msg": v.message,
                     "severity": v.severity, "owner": agent_cls.__name__}
                    for v in owned
                ])
                if not owned:
                    break
                agent.repair(owned)
            return {"task_attempts": self._bump_attempt(state, task_name)}
        return _node

    # ── aggregation (+ silent residual audit) ───────────────────────────────
    def aggregate_node(self):
        def _node(state: ISDState) -> dict:
            try:
                addie_output = ADDIEOutputAggregator(*self._args()).aggregate()
            except Exception:
                addie_output = empty_addie()
            validation_errors = validate_addie(addie_output)
            jsonschema_validate_addie(addie_output)
            self.trajectory.log_validation_result("addie_output", validation_errors)
            result: dict = {"addie_output": addie_output, "validation_errors": validation_errors}
            if not state.get("audit"):
                residual = GraphAuditor(self.graph).audit(state.get("violations", []))
                result["audit"] = residual.to_dict()
            return result
        return _node

    # ── dynamic-planner branch nodes (used only by workflows/dynamic.py) ─────
    def audit_node(self):
        def _node(state: ISDState) -> dict:
            return {"audit": GraphAuditor(self.graph).audit(state.get("violations", [])).to_dict()}
        return _node

    def task_planner_node(self):
        def _node(state: ISDState) -> dict:
            audit = GraphAuditor(self.graph).audit(state.get("violations", []))
            decision = self.task_planner.decide(audit, state, self.config)
            decision_dict = decision.to_dict()
            decision_dict["audit_summary"] = audit.summary
            decision_dict["task_graph"] = TaskGraphBuilder.build(audit, decision, state)
            self.trajectory.log_planner_decision(decision_dict)
            return {
                "audit": audit.to_dict(),
                "next_task": decision.next_task,
                "pending_tasks": [t.to_dict() for t in decision.pending_tasks],
                "planner_decisions": [decision_dict],
            }
        return _node

    def verifier_node(self):
        def _node(state: ISDState) -> dict:
            try:
                violations = PedagogicalVerifierAgent(*self._args()).verify(self.design_brief)
                violation_dicts = [self._violation_to_dict(v) for v in violations]
                self.trajectory.log_verifier_result(violation_dicts)
                return {"violations": violation_dicts, "needs_verification": False,
                        "task_attempts": self._bump_attempt(state, "verifier")}
            except Exception as exc:
                return {"violations": [], "needs_verification": False,
                        "task_attempts": self._bump_attempt(state, "verifier"),
                        "errors": [f"PedagogicalVerifier: {exc}"]}
        return _node

    def specialist_repair_node(self, agent_cls, task_name: str):
        def _node(state: ISDState) -> dict:
            try:
                remaining = agent_cls(*self._args()).repair(self._violations_from_state(state))
            except Exception as exc:
                return {"errors": [f"{agent_cls.__name__}: {exc}"],
                        "task_attempts": self._bump_attempt(state, task_name),
                        "repair_rounds": int(state.get("repair_rounds", 0) or 0) + 1}
            return {"violations": [self._violation_to_dict(v) for v in remaining],
                    "task_attempts": self._bump_attempt(state, task_name),
                    "repair_rounds": int(state.get("repair_rounds", 0) or 0) + 1,
                    "needs_verification": True}
        return _node


def initial_state() -> ISDState:
    return {
        "violations": [], "addie_output": {}, "errors": [], "audit": {},
        "pending_tasks": [], "next_task": "", "task_attempts": {},
        "planner_decisions": [], "needs_verification": True, "repair_rounds": 0,
        "validation_errors": [],
    }


def jsonschema_validate_addie(addie_output: dict) -> None:
    try:
        import jsonschema
        with _SCHEMA_PATH.open() as f:
            schema = json.load(f)
        jsonschema.validate(instance=addie_output, schema=schema)
    except Exception as exc:
        import warnings
        warnings.warn(f"ADDIE output schema validation warning: {exc}")


def empty_addie() -> dict:
    return {
        "analysis": {"needs_analysis": {}, "learner_analysis": {}, "context_analysis": {}, "task_analysis": {}},
        "design": {"learning_objectives": [], "instructional_strategies": {}},
        "development": {"learner_materials": [], "assessment_tools": [], "expert_review": {}},
        "implementation": {"instructor_orientation": {}, "system_check": {}, "prototype_execution": {}, "monitoring": {}},
        "evaluation": {"formative": {}, "summative": {}, "improvement_plan": {}},
    }

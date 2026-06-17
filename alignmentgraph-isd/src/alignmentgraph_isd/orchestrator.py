from __future__ import annotations
import json
import uuid
from pathlib import Path
from typing import TypedDict, Annotated
import operator

from .config import HarnessRunConfig
from .graph import AlignmentGraph
from .trajectory import TrajectoryLogger
from .audit import GraphAuditor
from .planner import ISDTaskPlanner
from .memory import HarnessMemory
from .schema import DesignBrief
from .rag.planner import RetrievalPlanner
from .agents.needs_context import NeedsContextAgent
from .agents.objective_design import ObjectiveDesignAgent
from .agents.assessment_design import AssessmentDesignAgent
from .agents.activity_material import ActivityMaterialAgent
from .agents.implementation_constraint import ImplementationConstraintAgent
from .agents.evaluation_revision import EvaluationRevisionAgent
from .agents.single_agent import SingleAgent
from .agents.pedagogical_verifier import PedagogicalVerifierAgent
from .agents.addie_aggregator import ADDIEOutputAggregator

_SCHEMA_PATH = Path(__file__).parent / "schema" / "addie_output.json"

# ── LangGraph state ────────────────────────────────────────────────────────────
# Only plain JSON-serializable types live here so MemorySaver can checkpoint them.
# Non-serializable objects (config, AlignmentGraph, TrajectoryLogger, the DesignBrief)
# are captured as closures at graph-build time and never placed in state.

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


# ── Graph builder (called once per run, captures per-run objects as closures) ──

def _build_graph_for_run(
    config: HarnessRunConfig,
    graph: AlignmentGraph,
    trajectory: TrajectoryLogger,
    context_pack: dict,
    design_brief: DesignBrief,
):
    """Build and compile a fresh LangGraph StateGraph for one design brief run.

    Non-serializable objects (config, graph, trajectory, design_brief) are captured in
    closures so they never touch the LangGraph state — allowing MemorySaver to
    checkpoint the state without serialization errors. The design brief is
    constant for the run, so it lives as a closure rather than in state.
    """
    from langgraph.graph import StateGraph, START, END

    def _args():
        return config, graph, trajectory

    task_planner = ISDTaskPlanner.from_config(config)

    def _bump_attempt(state: ISDState, task_name: str) -> dict[str, int]:
        attempts = dict(state.get("task_attempts", {}) or {})
        attempts[task_name] = attempts.get(task_name, 0) + 1
        return attempts

    def _generation_done(state: ISDState, task_name: str) -> dict:
        return {
            "task_attempts": _bump_attempt(state, task_name),
            "needs_verification": True,
        }

    def _violations_from_state(state: ISDState):
        from .agents.pedagogical_verifier import VerifierViolation
        return [
            VerifierViolation(
                node_id=v["node_id"],
                edge_type=v.get("edge_type", ""),
                message=v["msg"],
                violation_type=v["type"],
                severity=v["severity"],
                repair_hint=v.get("repair_hint", ""),
                metadata=v.get("metadata", {}),
            )
            for v in state.get("violations", [])
        ]

    def _violations_to_state(violations) -> list[dict]:
        return [
            {
                "node_id": v.node_id,
                "edge_type": v.edge_type,
                "type": v.violation_type,
                "msg": v.message,
                "severity": v.severity,
                "repair_hint": v.repair_hint,
                "metadata": v.metadata,
            }
            for v in violations
        ]

    def _specialist_repair_node(state: ISDState, agent_cls, task_name: str) -> dict:
        if not config.ablation.use_repair:
            return {
                "task_attempts": _bump_attempt(state, task_name),
                "needs_verification": False,
            }
        try:
            remaining = agent_cls(*_args()).repair(_violations_from_state(state))
        except Exception as exc:
            return {
                "errors": [f"{agent_cls.__name__}: {exc}"],
                "task_attempts": _bump_attempt(state, task_name),
                "repair_rounds": int(state.get("repair_rounds", 0) or 0) + 1,
            }
        return {
            "violations": _violations_to_state(remaining),
            "task_attempts": _bump_attempt(state, task_name),
            "repair_rounds": int(state.get("repair_rounds", 0) or 0) + 1,
            "needs_verification": True,
        }

    # ── Node functions ─────────────────────────────────────────────────────────

    def _audit_node(state: ISDState) -> dict:
        audit = GraphAuditor(graph).audit(state.get("violations", []))
        return {"audit": audit.to_dict()}

    def _task_planner_node(state: ISDState) -> dict:
        audit = GraphAuditor(graph).audit(state.get("violations", []))
        decision = task_planner.decide(audit, state, config)
        decision_dict = decision.to_dict()
        decision_dict["audit_summary"] = audit.summary
        trajectory.log_planner_decision(decision_dict)
        return {
            "audit": audit.to_dict(),
            "next_task": decision.next_task,
            "pending_tasks": [planned_task.to_dict() for planned_task in decision.pending_tasks],
            "planner_decisions": [decision_dict],
        }

    def _needs_context_node(state: ISDState) -> dict:
        try:
            NeedsContextAgent(*_args()).run(design_brief, context_pack)
        except Exception as exc:
            return {
                "errors": [f"NeedsContextAgent: {exc}"],
                "task_attempts": _bump_attempt(state, "needs_context"),
            }
        return _generation_done(state, "needs_context")

    def _objective_design_node(state: ISDState) -> dict:
        try:
            ObjectiveDesignAgent(*_args()).run(design_brief, context_pack)
        except Exception as exc:
            return {
                "errors": [f"ObjectiveDesignAgent: {exc}"],
                "task_attempts": _bump_attempt(state, "objective_design"),
            }
        return _generation_done(state, "objective_design")

    def _assessment_design_node(state: ISDState) -> dict:
        try:
            AssessmentDesignAgent(*_args()).run(design_brief, context_pack)
        except Exception as exc:
            return {
                "errors": [f"AssessmentDesignAgent: {exc}"],
                "task_attempts": _bump_attempt(state, "assessment_design"),
            }
        return _generation_done(state, "assessment_design")

    def _activity_material_node(state: ISDState) -> dict:
        try:
            ActivityMaterialAgent(*_args()).run(design_brief, context_pack)
        except Exception as exc:
            return {
                "errors": [f"ActivityMaterialAgent: {exc}"],
                "task_attempts": _bump_attempt(state, "activity_material"),
            }
        return _generation_done(state, "activity_material")

    def _implementation_constraint_node(state: ISDState) -> dict:
        try:
            ImplementationConstraintAgent(*_args()).run(design_brief, context_pack)
        except Exception as exc:
            return {
                "errors": [f"ImplementationConstraintAgent: {exc}"],
                "task_attempts": _bump_attempt(state, "implementation_constraint"),
            }
        return _generation_done(state, "implementation_constraint")

    def _evaluation_revision_node(state: ISDState) -> dict:
        try:
            EvaluationRevisionAgent(*_args()).run(design_brief, context_pack)
        except Exception as exc:
            return {
                "errors": [f"EvaluationRevisionAgent: {exc}"],
                "task_attempts": _bump_attempt(state, "evaluation_revision"),
            }
        return _generation_done(state, "evaluation_revision")

    def _single_agent_node(state: ISDState) -> dict:
        try:
            SingleAgent(*_args()).run(design_brief, context_pack)
        except Exception as exc:
            return {
                "errors": [f"SingleAgent: {exc}"],
                "task_attempts": _bump_attempt(state, "single_agent"),
            }
        return _generation_done(state, "single_agent")

    def _verifier_node(state: ISDState) -> dict:
        if not config.ablation.use_verifier:
            return {
                "violations": [],
                "needs_verification": False,
                "task_attempts": _bump_attempt(state, "verifier"),
            }
        try:
            violations = PedagogicalVerifierAgent(*_args()).verify()
            return {
                "violations": [
                    {
                        "node_id": v.node_id,
                        "edge_type": v.edge_type,
                        "type": v.violation_type,
                        "msg": v.message,
                        "severity": v.severity,
                        "repair_hint": v.repair_hint,
                        "metadata": v.metadata,
                    }
                    for v in violations
                ],
                "needs_verification": False,
                "task_attempts": _bump_attempt(state, "verifier"),
            }
        except Exception as exc:
            return {
                "violations": [],
                "needs_verification": False,
                "task_attempts": _bump_attempt(state, "verifier"),
                "errors": [f"PedagogicalVerifier: {exc}"],
            }

    def _objective_repair_node(state: ISDState) -> dict:
        return _specialist_repair_node(state, ObjectiveDesignAgent, "objective_repair")

    def _assessment_repair_node(state: ISDState) -> dict:
        return _specialist_repair_node(state, AssessmentDesignAgent, "assessment_repair")

    def _activity_repair_node(state: ISDState) -> dict:
        return _specialist_repair_node(state, ActivityMaterialAgent, "activity_repair")

    def _implementation_repair_node(state: ISDState) -> dict:
        return _specialist_repair_node(state, ImplementationConstraintAgent, "implementation_repair")

    def _evaluation_repair_node(state: ISDState) -> dict:
        return _specialist_repair_node(state, EvaluationRevisionAgent, "evaluation_repair")

    def _aggregate_node(state: ISDState) -> dict:
        try:
            addie_output = ADDIEOutputAggregator(*_args()).aggregate()
        except Exception:
            addie_output = _empty_addie()
        _validate_addie(addie_output)
        return {"addie_output": addie_output}

    # ── Conditional routing ────────────────────────────────────────────────────

    def _route_orchestration(state: ISDState) -> str:
        return "multi_agent" if config.ablation.multi_agent else "single_agent"

    # ── Wire the graph ─────────────────────────────────────────────────────────

    wf = StateGraph(ISDState)

    wf.add_node("router", lambda _: {})
    wf.add_node("audit", _audit_node)
    wf.add_node("task_planner", _task_planner_node)
    wf.add_node("needs_context", _needs_context_node)
    wf.add_node("objective_design", _objective_design_node)
    wf.add_node("assessment_design", _assessment_design_node)
    wf.add_node("activity_material", _activity_material_node)
    wf.add_node("implementation_constraint", _implementation_constraint_node)
    wf.add_node("evaluation_revision", _evaluation_revision_node)
    wf.add_node("single_agent", _single_agent_node)
    wf.add_node("verifier", _verifier_node)
    wf.add_node("objective_repair", _objective_repair_node)
    wf.add_node("assessment_repair", _assessment_repair_node)
    wf.add_node("activity_repair", _activity_repair_node)
    wf.add_node("implementation_repair", _implementation_repair_node)
    wf.add_node("evaluation_repair", _evaluation_repair_node)
    wf.add_node("aggregate", _aggregate_node)

    if config.ablation.dynamic_graph:
        wf.add_edge(START, "audit")
        wf.add_edge("audit", "task_planner")
        wf.add_conditional_edges(
            "task_planner",
            lambda state: state.get("next_task", "aggregate"),
            {
                "needs_context": "needs_context",
                "objective_design": "objective_design",
                "assessment_design": "assessment_design",
                "activity_material": "activity_material",
                "implementation_constraint": "implementation_constraint",
                "evaluation_revision": "evaluation_revision",
                "single_agent": "single_agent",
                "verifier": "verifier",
                "objective_repair": "objective_repair",
                "assessment_repair": "assessment_repair",
                "activity_repair": "activity_repair",
                "implementation_repair": "implementation_repair",
                "evaluation_repair": "evaluation_repair",
                "aggregate": "aggregate",
            },
        )
        for node_name in (
            "needs_context",
            "objective_design",
            "assessment_design",
            "activity_material",
            "implementation_constraint",
            "evaluation_revision",
            "single_agent",
            "verifier",
            "objective_repair",
            "assessment_repair",
            "activity_repair",
            "implementation_repair",
            "evaluation_repair",
        ):
            wf.add_edge(node_name, "audit")
        wf.add_edge("aggregate", END)
        from langgraph.checkpoint.memory import MemorySaver
        return wf.compile(checkpointer=MemorySaver())

    wf.add_edge(START, "router")
    wf.add_conditional_edges(
        "router",
        _route_orchestration,
        {"multi_agent": "needs_context", "single_agent": "single_agent"},
    )

    wf.add_edge("needs_context", "objective_design")
    wf.add_edge("objective_design", "assessment_design")
    wf.add_edge("assessment_design", "activity_material")
    wf.add_edge("activity_material", "implementation_constraint")
    wf.add_edge("implementation_constraint", "evaluation_revision")
    wf.add_edge("evaluation_revision", "verifier")
    wf.add_edge("single_agent", "verifier")
    wf.add_edge("verifier", "aggregate")
    wf.add_edge("aggregate", END)
    return wf.compile()


# ── MetaAgent (public API) ─────────────────────────────────────────────────────

class MetaAgent:
    def __init__(self, config: HarnessRunConfig) -> None:
        self.config = config

    def run(self, design_brief: DesignBrief) -> dict:
        memory = HarnessMemory(self.config)
        memory_session = memory.begin_session(design_brief)
        graph = memory_session.graph
        trajectory = TrajectoryLogger()
        planner = RetrievalPlanner(self.config)
        try:
            context_pack = planner.retrieve(design_brief)
        except Exception:
            context_pack = {}
        context_pack = memory_session.augment_context_pack(context_pack)

        compiled = _build_graph_for_run(self.config, graph, trajectory, context_pack, design_brief)

        initial_state: ISDState = {
            "violations": [],
            "addie_output": {},
            "errors": [],
            "audit": {},
            "pending_tasks": [],
            "next_task": "",
            "task_attempts": {},
            "planner_decisions": [],
            "needs_verification": True,
            "repair_rounds": 0,
        }

        invoke_config = {"recursion_limit": 80}
        if self.config.ablation.dynamic_graph:
            invoke_config["configurable"] = {"thread_id": str(uuid.uuid4())}
        final_state = compiled.invoke(initial_state, invoke_config)

        addie_output = final_state.get("addie_output") or _empty_addie()
        trajectory_payload = trajectory.finalize()
        memory_metadata = memory_session.commit(
            design_brief=design_brief,
            graph=graph,
            trajectory=trajectory_payload,
            final_state=final_state,
            addie_output=addie_output,
        )
        return {
            "addie_output": addie_output,
            "trajectory": trajectory_payload,
            "metadata": {
                "ablation": self.config.ablation.model_dump(),
                "llm": self.config.llm.model_dump(),
                "memory": memory_metadata,
                "design_brief_id": design_brief.id,
                "violations": final_state.get("violations", []),
                "errors": final_state.get("errors", []),
                "audit": final_state.get("audit", {}),
                "pending_tasks": final_state.get("pending_tasks", []),
                "task_attempts": final_state.get("task_attempts", {}),
                "planner_decisions": final_state.get("planner_decisions", []),
                "repair_rounds": final_state.get("repair_rounds", 0),
            },
        }


# ── Helpers ────────────────────────────────────────────────────────────────────

def _validate_addie(addie_output: dict) -> None:
    try:
        import jsonschema
        with _SCHEMA_PATH.open() as f:
            schema = json.load(f)
        jsonschema.validate(instance=addie_output, schema=schema)
    except Exception as exc:
        import warnings
        warnings.warn(f"ADDIE output schema validation warning: {exc}")


def _empty_addie() -> dict:
    return {
        "analysis": {"needs_analysis": {}, "learner_analysis": {}, "context_analysis": {}, "task_analysis": {}},
        "design": {"learning_objectives": [], "instructional_strategies": {}},
        "development": {"learner_materials": [], "assessment_tools": [], "expert_review": {}},
        "implementation": {"instructor_orientation": {}, "system_check": {}, "prototype_execution": {}, "monitoring": {}},
        "evaluation": {"formative": {}, "summative": {}, "improvement_plan": {}},
    }

from __future__ import annotations
import json
import uuid
from pathlib import Path
from typing import TypedDict, Annotated
import operator

from .config import HarnessRunConfig
from .graph import AlignmentGraph
from .trajectory import TrajectoryLogger
from .rag.planner import RetrievalPlanner
from .agents.needs_context import NeedsContextAgent
from .agents.objective_design import ObjectiveDesignAgent
from .agents.assessment_design import AssessmentDesignAgent
from .agents.activity_material import ActivityMaterialAgent
from .agents.implementation_constraint import ImplementationConstraintAgent
from .agents.evaluation_revision import EvaluationRevisionAgent
from .agents.single_agent import SingleAgent
from .agents.pedagogical_verifier import PedagogicalVerifierAgent
from .agents.repair import RepairAgent
from .agents.addie_aggregator import ADDIEOutputAggregator

_SCHEMA_PATH = Path(__file__).parent / "schema" / "addie_output.json"

# ── LangGraph state ────────────────────────────────────────────────────────────
# Only plain JSON-serializable types live here so MemorySaver can checkpoint them.
# Non-serializable objects (config, AlignmentGraph, TrajectoryLogger) are captured
# as closures at graph-build time and never placed in state.

class ISDState(TypedDict):
    scenario: dict
    violations: list[dict]          # serialized VerifierViolation dicts
    addie_output: dict
    errors: Annotated[list[str], operator.add]


# ── Graph builder (called once per run, captures per-run objects as closures) ──

def _build_graph_for_run(
    config: HarnessRunConfig,
    graph: AlignmentGraph,
    trajectory: TrajectoryLogger,
    context_pack: dict,
):
    """Build and compile a fresh LangGraph StateGraph for one scenario run.

    Non-serializable objects (config, graph, trajectory) are captured in
    closures so they never touch the LangGraph state — allowing MemorySaver to
    checkpoint the state without serialization errors.
    """
    from langgraph.graph import StateGraph, START, END

    def _args():
        return config, graph, trajectory

    # ── Node functions ─────────────────────────────────────────────────────────

    def _needs_context_node(state: ISDState) -> dict:
        try:
            NeedsContextAgent(*_args()).run(state["scenario"], context_pack)
        except Exception as exc:
            return {"errors": [f"NeedsContextAgent: {exc}"]}
        return {}

    def _objective_design_node(state: ISDState) -> dict:
        try:
            ObjectiveDesignAgent(*_args()).run(state["scenario"], context_pack)
        except Exception as exc:
            return {"errors": [f"ObjectiveDesignAgent: {exc}"]}
        return {}

    def _assessment_design_node(state: ISDState) -> dict:
        try:
            AssessmentDesignAgent(*_args()).run(state["scenario"], context_pack)
        except Exception as exc:
            return {"errors": [f"AssessmentDesignAgent: {exc}"]}
        return {}

    def _activity_material_node(state: ISDState) -> dict:
        try:
            ActivityMaterialAgent(*_args()).run(state["scenario"], context_pack)
        except Exception as exc:
            return {"errors": [f"ActivityMaterialAgent: {exc}"]}
        return {}

    def _implementation_constraint_node(state: ISDState) -> dict:
        try:
            ImplementationConstraintAgent(*_args()).run(state["scenario"], context_pack)
        except Exception as exc:
            return {"errors": [f"ImplementationConstraintAgent: {exc}"]}
        return {}

    def _evaluation_revision_node(state: ISDState) -> dict:
        try:
            EvaluationRevisionAgent(*_args()).run(state["scenario"], context_pack)
        except Exception as exc:
            return {"errors": [f"EvaluationRevisionAgent: {exc}"]}
        return {}

    def _single_agent_node(state: ISDState) -> dict:
        try:
            SingleAgent(*_args()).run(state["scenario"], context_pack)
        except Exception as exc:
            return {"errors": [f"SingleAgent: {exc}"]}
        return {}

    def _verifier_node(state: ISDState) -> dict:
        if not config.ablation.use_verifier:
            return {"violations": []}
        try:
            violations = PedagogicalVerifierAgent(*_args()).verify()
            return {"violations": [
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
            ]}
        except Exception as exc:
            return {"violations": [], "errors": [f"PedagogicalVerifier: {exc}"]}

    def _repair_node(state: ISDState) -> dict:
        if not config.ablation.use_repair:
            return {}
        try:
            from .agents.pedagogical_verifier import VerifierViolation
            violations = [
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
            RepairAgent(*_args()).repair(violations)
        except Exception as exc:
            return {"errors": [f"RepairAgent: {exc}"]}
        return {}

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

    def _route_after_verifier(state: ISDState) -> str:
        if state.get("violations") and config.ablation.use_repair:
            return "repair"
        return "aggregate"

    # ── Wire the graph ─────────────────────────────────────────────────────────

    wf = StateGraph(ISDState)

    wf.add_node("router", lambda _: {})
    wf.add_node("needs_context", _needs_context_node)
    wf.add_node("objective_design", _objective_design_node)
    wf.add_node("assessment_design", _assessment_design_node)
    wf.add_node("activity_material", _activity_material_node)
    wf.add_node("implementation_constraint", _implementation_constraint_node)
    wf.add_node("evaluation_revision", _evaluation_revision_node)
    wf.add_node("single_agent", _single_agent_node)
    wf.add_node("verifier", _verifier_node)
    wf.add_node("repair", _repair_node)
    wf.add_node("aggregate", _aggregate_node)

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

    wf.add_conditional_edges(
        "verifier",
        _route_after_verifier,
        {"repair": "repair", "aggregate": "aggregate"},
    )
    wf.add_edge("repair", "aggregate")
    wf.add_edge("aggregate", END)

    if config.ablation.dynamic_graph:
        from langgraph.checkpoint.memory import MemorySaver
        return wf.compile(checkpointer=MemorySaver())
    return wf.compile()


# ── MetaAgent (public API) ─────────────────────────────────────────────────────

class MetaAgent:
    def __init__(self, config: HarnessRunConfig) -> None:
        self.config = config

    def run(self, scenario: dict) -> dict:
        graph = AlignmentGraph()
        trajectory = TrajectoryLogger()
        planner = RetrievalPlanner(self.config)
        try:
            context_pack = planner.retrieve(scenario)
        except Exception:
            context_pack = {}

        compiled = _build_graph_for_run(self.config, graph, trajectory, context_pack)

        initial_state: ISDState = {
            "scenario": scenario,
            "violations": [],
            "addie_output": {},
            "errors": [],
        }

        invoke_config = (
            {"configurable": {"thread_id": str(uuid.uuid4())}}
            if self.config.ablation.dynamic_graph
            else {}
        )
        final_state = compiled.invoke(initial_state, invoke_config)

        addie_output = final_state.get("addie_output") or _empty_addie()
        return {
            "addie_output": addie_output,
            "trajectory": trajectory.finalize(),
            "metadata": {
                "ablation": self.config.ablation.model_dump(),
                "llm": self.config.llm.model_dump(),
                "scenario_id": scenario.get("scenario_id") or scenario.get("id", "unknown"),
                "violations": final_state.get("violations", []),
                "errors": final_state.get("errors", []),
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

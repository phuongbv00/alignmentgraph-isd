"""LangGraph node factories + the single graph builder.

A ``NodeFactory`` captures the per-run objects (config, graph, trajectory,
context pack, design brief) and exposes each ISD step as a node function.
``build_graph`` wires those nodes into a StateGraph, branching once on
``config.ablation.multi_agent`` (multi-agent ADDIE pipeline vs single-agent) —
there is no workflow-per-arm registry.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Annotated, TypedDict
import operator

from .audit import GraphAuditor
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
    task_attempts: dict[str, int]
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

# Fixed ADDIE order the multi-agent arm generates in.
GENERATION_ORDER = [
    "needs_context", "objective_design", "assessment_design",
    "activity_material", "implementation_plan", "evaluation_revision",
]


class NodeFactory:
    """Builds node functions bound to one run's objects. No ablation flags."""

    def __init__(self, config, graph, trajectory, design_brief) -> None:
        self.config = config
        self.graph = graph
        self.trajectory = trajectory
        self.design_brief = design_brief

    # ── shared helpers ──────────────────────────────────────────────────────
    def _args(self):
        return self.config, self.graph, self.trajectory

    @staticmethod
    def _bump_attempt(state: ISDState, task_name: str) -> dict[str, int]:
        attempts = dict(state.get("task_attempts", {}) or {})
        attempts[task_name] = attempts.get(task_name, 0) + 1
        return attempts

    def _generation_done(self, state: ISDState, task_name: str) -> dict:
        return {"task_attempts": self._bump_attempt(state, task_name)}

    # ── generation nodes ────────────────────────────────────────────────────
    def generation_node(self, node_name: str):
        agent_cls = GENERATION_AGENTS[node_name]

        def _node(state: ISDState) -> dict:
            try:
                agent_cls(*self._args()).run(self.design_brief)
            except Exception as exc:
                return {"errors": [f"{agent_cls.__name__}: {exc}"],
                        "task_attempts": self._bump_attempt(state, node_name)}
            return self._generation_done(state, node_name)
        return _node

    def single_agent_node(self):
        def _node(state: ISDState) -> dict:
            try:
                SingleAgent(*self._args()).run(self.design_brief)
            except Exception as exc:
                return {"errors": [f"SingleAgent: {exc}"],
                        "task_attempts": self._bump_attempt(state, "single_agent")}
            return self._generation_done(state, "single_agent")
        return _node

    # ── per-agent quality-control node (verify owned types + repair) ─────────
    def qc_node(self, agent_cls, task_name: str, budget: int = 2):
        """Verify the checks ``agent_cls`` owns and let it repair them, in place,
        up to ``budget`` rounds. This is the quality-control tool each specialist
        owns; it runs after every generation node in both arms (QC is always on)."""
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


def initial_state() -> ISDState:
    return {
        "violations": [], "addie_output": {}, "errors": [], "audit": {},
        "task_attempts": {}, "validation_errors": [],
    }


def build_graph(config, graph, trajectory, design_brief):
    """Assemble the LangGraph StateGraph for this run.

    A single builder, branching on ``config.ablation.multi_agent`` — there is no
    workflow-per-arm registry. Both arms end in the same aggregate node and run
    per-agent QC after every generation node (QC is always on):

    - multi-agent (``full``/``wo_graph``): the six specialists in fixed ADDIE
      order, each followed by its QC node. ``full`` vs ``wo_graph`` differ only
      at runtime inside the specialists (``use_graph_coordination``), not in
      graph shape.
    - single-agent (``wo_ma``): one blob-generating agent + its QC node.
    """
    from langgraph.graph import StateGraph, START, END

    nf = NodeFactory(config, graph, trajectory, design_brief)
    wf = StateGraph(ISDState)
    wf.add_node("aggregate", nf.aggregate_node())

    if config.ablation.multi_agent:
        prev = START
        for name in GENERATION_ORDER:
            wf.add_node(name, nf.generation_node(name))
            wf.add_edge(prev, name)
            agent_cls = GENERATION_AGENTS[name]
            if agent_cls.OWNED_VIOLATION_TYPES:  # only agents with checks get a QC node
                qc = f"{name}_qc"
                wf.add_node(qc, nf.qc_node(agent_cls, qc))
                wf.add_edge(name, qc)
                prev = qc
            else:
                prev = name
        wf.add_edge(prev, "aggregate")
    else:
        wf.add_node("single_agent", nf.single_agent_node())
        wf.add_node("single_agent_qc", nf.qc_node(SingleAgent, "single_agent_qc"))
        wf.add_edge(START, "single_agent")
        wf.add_edge("single_agent", "single_agent_qc")
        wf.add_edge("single_agent_qc", "aggregate")

    wf.add_edge("aggregate", END)
    return wf.compile()


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

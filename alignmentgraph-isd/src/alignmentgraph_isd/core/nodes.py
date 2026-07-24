"""LangGraph node factories + the single graph builder.

A ``NodeFactory`` captures the per-run objects (config, graph, trajectory,
design brief) and exposes each ISD step as a node function. ``build_graph``
wires those nodes into one fixed StateGraph: the six ADDIE specialists in
order, each followed by its QC node, then aggregation.
"""
from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Annotated, TypedDict
import operator

from .audit import GraphAuditor
from .graph import NodeType
from .validation import validate_addie, validate_section
from .agents.needs_context import NeedsContextAgent
from .agents.objective_design import ObjectiveDesignAgent
from .agents.assessment_design import AssessmentDesignAgent
from .agents.activity_material import ActivityMaterialAgent
from .agents.implementation_plan import ImplementationPlanAgent
from .agents.evaluation_revision import EvaluationRevisionAgent
from .agents.pedagogical_verifier import PedagogicalVerifierAgent
from .agents.addie_aggregator import ADDIEOutputAggregator, _merge_node_data

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

# Fixed ADDIE order the specialists generate in.
GENERATION_ORDER = [
    "needs_context", "objective_design", "assessment_design",
    "activity_material", "implementation_plan", "evaluation_revision",
]

# Section nodes each specialist is responsible for filling, keyed by the
# ``validate_section`` type (== the graph section-node type). The regen loop
# re-runs a specialist while ANY of these still has a required field
# missing/empty — so a specialist that generates in several calls (e.g.
# objective_design's learning-objectives call + its strategies/media/storyboard
# "rest" call) is re-run when EITHER call comes back empty, not only the primary
# one. Every phase-required field (see validation._ADDIE_PHASE_FIELDS) must be
# covered here or a partial failure would slip past regen and score 0 at the judge.
GENERATION_SECTIONS: dict[str, tuple[str, ...]] = {
    "needs_context": (NodeType.NEEDS_CONTEXT,),
    # design.learning_objectives (objective_0) + design.instructional_strategies
    # (its own singleton node) are both phase-required and come from separate calls.
    "objective_design": (NodeType.OBJECTIVE, "instructional_strategies"),
    "assessment_design": (NodeType.ASSESSMENT,),
    # development.learner_materials (material) is phase-required but lives in a
    # sibling node to activity's learning_activities.
    "activity_material": (NodeType.ACTIVITY, NodeType.MATERIAL),
    "implementation_plan": (NodeType.IMPLEMENTATION_PLAN,),
    "evaluation_revision": (NodeType.EVALUATION,),
}

# How many extra fresh regenerations to attempt when a specialist's primary
# section comes back with a required field missing/empty (0 = disabled). A small
# model (e.g. a 2B endpoint) intermittently returns an empty/unparseable payload;
# a clean re-run recovers it, whereas shipping the empty skeleton scores that
# whole ADDIE phase 0 at the judge.
EMPTY_SECTION_REGEN_BUDGET = 2

_EMPTY_FIELD_MARKER = "required field is missing or empty"


def _empty_required_fields(section_type: str, data: dict) -> list[str]:
    """Required fields of ``section_type`` that are missing or empty in ``data``.

    A subset of ``validate_section`` (only the empty-required errors) — malformed
    ids and type mismatches are left to downstream repair/aggregator safety nets;
    only a substantially empty section is worth a full regeneration."""
    return [e for e in validate_section(section_type, data) if e.endswith(_EMPTY_FIELD_MARKER)]


class NodeFactory:
    """Builds node functions bound to one run's objects."""

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

    def _empty_sections(self, section_types: tuple[str, ...]) -> list[str]:
        """Required fields missing/empty across every section a specialist owns."""
        missing: list[str] = []
        for section_type in section_types:
            data = _merge_node_data(self.graph.section_nodes(section_type))
            missing.extend(_empty_required_fields(section_type, data))
        return missing

    # ── generation nodes ────────────────────────────────────────────────────
    def generation_node(self, node_name: str):
        agent_cls = GENERATION_AGENTS[node_name]
        section_types = GENERATION_SECTIONS[node_name]

        def _node(state: ISDState) -> dict:
            errors: list[str] = []
            budget = max(0, int(getattr(self.config, "regen_budget", EMPTY_SECTION_REGEN_BUDGET)))
            backoff = max(0.0, float(getattr(self.config, "regen_backoff_seconds", 0.0)))
            # One initial generation plus up to ``budget`` fresh re-runs while the
            # specialist's primary section is still empty. Re-running is a clean
            # attempt (new prompt, node overwritten by deterministic section id),
            # unlike the in-conversation correction retry inside _call_llm. A
            # per-attempt backoff (config-sourced from the benchmark rate posture)
            # lets a 429 concurrency window drain instead of being hammered — an
            # immediate re-run on a rate-limit just makes the throttling worse.
            for attempt in range(budget + 1):
                if attempt > 0 and backoff:
                    time.sleep(backoff * attempt)
                try:
                    agent_cls(*self._args()).run(self.design_brief)
                except Exception as exc:
                    errors.append(f"{agent_cls.__name__}: {exc}")
                    continue
                missing = self._empty_sections(section_types)
                if not missing:
                    break
                self.trajectory.log_step(
                    agent_cls.__name__, "regen_empty_section",
                    f"attempt {attempt + 1}", "; ".join(missing),
                )
            result = self._generation_done(state, node_name)
            if errors:
                result["errors"] = errors
            return result
        return _node

    # ── per-agent quality-control node (verify owned types + repair) ─────────
    def qc_node(self, agent_cls, task_name: str, budget: int = 2):
        """Verify the checks ``agent_cls`` owns and let it repair them, in place,
        up to ``budget`` rounds. This is the quality-control tool each specialist
        owns; it runs after every generation node whenever
        ``config.enable_verifier`` is on (the default — off only in ablation arms)."""
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
    """Assemble the LangGraph StateGraph for this run: the six specialists in
    fixed ADDIE order, each followed by its QC node (per-agent verify + repair)
    unless ``config.enable_verifier`` is off, ending in the shared aggregate node.

    With QC off (ablation arm), the alignment-tier edges the verifier normally
    re-establishes during repair rounds are never created, so edge coverage in the
    graph dump may drop — that reduction is part of the measured ablation effect,
    not a bug. Zero verifier/repair activity in the metadata is likewise expected
    there; the residual GraphAuditor audit in the aggregate node still runs."""
    from langgraph.graph import StateGraph, START, END

    nf = NodeFactory(config, graph, trajectory, design_brief)
    wf = StateGraph(ISDState)
    wf.add_node("aggregate", nf.aggregate_node())

    prev = START
    for name in GENERATION_ORDER:
        wf.add_node(name, nf.generation_node(name))
        wf.add_edge(prev, name)
        agent_cls = GENERATION_AGENTS[name]
        # Only agents with checks get a QC node, and none do when the verifier is
        # ablated away.
        if agent_cls.OWNED_VIOLATION_TYPES and getattr(config, "enable_verifier", True):
            qc = f"{name}_qc"
            wf.add_node(qc, nf.qc_node(agent_cls, qc))
            wf.add_edge(name, qc)
            prev = qc
        else:
            prev = name
    wf.add_edge(prev, "aggregate")

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

"""The repair toolbox writes no instructional content of its own.

Every repair is structural: it rearranges what the design already holds. The
generative kind — which asked the model to write a missing artifact — went on
2026-09-03, and ``test_no_repair_routine_can_reach_the_model`` below is the
guard that it cannot come back.
Templated stand-ins used to close the gap — a "Guided practice for ILO-01"
activity, a "Support module for TLA-01", one fixed rubric sentence, a canned
list of formative methods — and every one of them satisfied its own check by
existing. That is the objection that has always kept P6 audit-only; these tests
hold it for the rest.

The cost is deliberate and is what these tests pin: some violations now have no
repair at all, and are reported instead of closed.
"""
from __future__ import annotations

import inspect

from alignmentgraph_isd.core import checks, repairs
from alignmentgraph_isd.core.alignment_graph import AlignmentGraph, NodeType
from alignmentgraph_isd.core.trajectory import TrajectoryLogger


def _ctx(graph, llm_response: str = "") -> repairs.RepairContext:
    """A context whose model answers with nothing usable — the case every
    generative repair has to survive without inventing."""
    return repairs.RepairContext(
        graph=graph, store=None, trajectory=TrajectoryLogger(), actor="Test")


def test_no_module_level_template_constant_comes_back():
    """The templates all had the same shape — a module-level constant holding a
    sentence (or a list of them) that a repair dropped into an artifact:
    ``OBSERVABLE_RUBRIC``, ``OBSERVABLE_DESCRIPTION``, ``FALLBACK_METHODS``.
    A guard on that shape, because a behavioural test only catches the paths it
    happens to exercise."""
    import ast

    tree = ast.parse(inspect.getsource(repairs))

    def _long_prose(node) -> str:
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            text = node.value
            return text if len(text) > 40 and text.count(" ") >= 6 else ""
        return ""

    offenders: list[str] = []
    for node in tree.body:
        if not isinstance(node, (ast.Assign, ast.AnnAssign)):
            continue
        value = node.value
        candidates = value.elts if isinstance(value, (ast.List, ast.Tuple)) else [value]
        for candidate in candidates:
            prose = _long_prose(candidate)
            if prose:
                offenders.append(prose[:60])
    assert not offenders, f"a canned-content constant is back in repairs.py: {offenders}"

    for gone in ("OBSERVABLE_RUBRIC", "OBSERVABLE_DESCRIPTION", "FALLBACK_METHODS",
                 "_fallback_item_text", "_fallback_pilot_data_plan"):
        assert not hasattr(repairs, gone), f"{gone} is back"


def test_a_report_only_violation_is_handed_back_untouched():
    """These types stay in OWNED_BY_FAMILY so reconciliation names an owner,
    and come straight back so the audit counts them as residual. Silently
    'handling' them was what a template did."""
    assert repairs.REPORT_ONLY <= set(repairs.OWNER_BY_VIOLATION), (
        "a report-only type with no owner cannot be routed or reported")

    class _V:
        def __init__(self, vtype):
            self.violation_type = vtype
            self.message = f"{vtype} stands"
            self.metadata = {}
            self.node_id = ""
            self.edge_type = ""

    for vtype in sorted(repairs.REPORT_ONLY):
        family = repairs.OWNER_BY_VIOLATION[vtype]
        violation = _V(vtype)
        graph = AlignmentGraph()
        trajectory = TrajectoryLogger()
        ctx = repairs.RepairContext(
            graph=graph, store=None, trajectory=trajectory, actor="Test")

        remaining = repairs.repair(family, [violation], ctx)

        # P6 is the one long-standing exception: it is dropped rather than
        # returned, and has been audit-only since before this rule.
        if vtype != "P6":
            assert violation in remaining, f"{vtype} was swallowed by {family}"
        assert not trajectory.repair_events, f"{vtype} logged a repair that never happened"
        created = graph.to_full_dict().get("nodes") or []
        assert not created, f"{vtype} manufactured a node: {[n['id'] for n in created]}"


def test_an_uncovered_objective_gets_no_activity_when_nobody_writes_one():
    graph = AlignmentGraph()
    graph.add_element_node(NodeType.OBJECTIVE, "ILO-01", {
        "id": "ILO-01", "level": "apply", "statement": "Apply X."})

    # `checks.relation_coverage`, not a `hasattr` guard on a name that does not
    # exist: the guard was False, so `violations` was always [] and `repair`
    # was never called — the assertion held on a graph nothing had touched.
    violations = [v for v in checks.relation_coverage(graph)
                  if v.violation_type == "C3"]
    assert violations, "the fixture no longer produces the C3 gap under test"
    repairs.repair("activity_designer", violations, _ctx(graph))
    assert not graph.element_nodes(NodeType.ACTIVITY)


def test_no_repair_routine_can_reach_the_model():
    """The rule, enforced by construction rather than by review (2026-09-03).

    A repair used to be allowed to call the model through
    ``RepairContext.call_llm``, and the generative ones did — one persona-free
    prompt, a system turn that was not the agent's own, no tools bound, in the
    agent's name. The recorded context then showed a second conversation the
    agent had never been part of, under an identity that had one system prompt
    everywhere else. Since the context boundary IS the ``agent_mode`` axis,
    that path put a boundary of its own inside the treatment.

    Violations needing new text go back to their owning agent as a repair turn
    in its own tool loop instead. So the repair toolbox has no model handle at
    all, and there is nowhere for one to come back."""
    import inspect

    fields = set(repairs.RepairContext.__dataclass_fields__)
    assert fields == {"graph", "store", "trajectory", "actor"}, (
        f"RepairContext grew a field; a model handle must not be one: {fields}")

    source = inspect.getsource(repairs)
    for forbidden in ("call_llm", "ChatOpenAI", ".invoke(", "AgenticLLM"):
        assert forbidden not in source, (
            f"repairs.py reaches for the model via {forbidden!r}")

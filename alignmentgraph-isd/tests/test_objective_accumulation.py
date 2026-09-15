"""Both substrates must accumulate learning objectives the same way.

``commit_outcomes`` appends each objective as its own element node and drops a
repeated ``statement``; ``commit_outcomes_prose`` used to go through
``_merge_document``, which REPLACES its key. So a regen or a second accepted
submit left the graph arm and the prose arm holding different designs — a data
loss sitting on the ``context_mode`` axis ITSELF rather than on the alignment
machinery that axis exists to ablate, which is how it would have been read.

There were three behaviours, not two: ``ReactLoop._commit`` re-merges prose
list fields, so single+prose appended with no dedup while multi+prose replaced.
Both halves are held here.
"""
from __future__ import annotations

from alignmentgraph_isd.core.agentic.specialists import STEPS

_OUTCOMES = next(s for s in STEPS if s.name == "outcomes")


def _two_submits() -> list[dict]:
    """Two instalments that overlap — a regen re-sending what it already
    wrote is the ordinary way this happens."""
    first = {"learning_objectives": [
        {"id": "ILO-01", "statement": "Explain X", "level": "understand",
         "bloom_verb": "explain"},
        {"id": "ILO-02", "statement": "Apply Y", "level": "apply",
         "bloom_verb": "apply"},
    ]}
    second = {"learning_objectives": [
        {"id": "ILO-02", "statement": "apply y", "level": "apply",
         "bloom_verb": "apply"},                      # the same one, recased
        {"id": "ILO-03", "statement": "Analyse Z", "level": "analyze",
         "bloom_verb": "analyze"},
    ]}
    return [first, second]


def _statements(items) -> list[str]:
    return [str(i.get("statement") or "") for i in items]


def test_both_substrates_accumulate_the_same_objectives():
    """``commit_outcomes`` APPENDS element nodes while ``_merge_document``
    REPLACES its key, so a regen or a second accepted submit used to leave the
    two substrates holding different designs. That is a data loss on the
    ``context_mode`` axis itself, not on the alignment machinery that axis
    ablates."""
    from alignmentgraph_isd.core.agentic import specialists
    from alignmentgraph_isd.core.alignment_graph import AlignmentGraph, NodeType
    from alignmentgraph_isd.core.prose_store import ProseStore
    from alignmentgraph_isd.core.trajectory import TrajectoryLogger

    graph, store = AlignmentGraph(), ProseStore()
    for section in _two_submits():
        specialists.commit_outcomes(graph, TrajectoryLogger(), section)
        specialists.commit_outcomes_prose(store, TrajectoryLogger(), section)

    from_graph = _statements(n.get("data") or {}
                             for n in graph.element_nodes(NodeType.OBJECTIVE))
    from_prose = _statements(store.items(str(NodeType.OBJECTIVE), "learning_objectives"))

    assert from_graph == from_prose
    # ...and the repeat was dropped on BOTH, not kept on one.
    assert from_graph == ["Explain X", "Apply Y", "Analyse Z"]


def test_the_single_arm_does_not_append_an_already_additive_document():
    """``ReactLoop._commit`` re-merges prose list fields because a prose commit
    replaces its key. A commit that appends for itself would otherwise land
    ``previous + (previous + new)``."""
    from alignmentgraph_isd.core.agentic import react, specialists
    from alignmentgraph_isd.core.alignment_graph import NodeType

    assert str(NodeType.OBJECTIVE) in specialists.ADDITIVE_PROSE_DOC_KEYS
    assert str(NodeType.OBJECTIVE) not in react._doc_keys(_OUTCOMES)

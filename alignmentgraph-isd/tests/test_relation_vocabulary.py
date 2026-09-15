"""A relation is named in ONE place, and every renderer uses those words.

`alignment.REGISTRY` gives each relation an ``edge_type`` verb (``assessed_by``)
and a ``label`` sentence (``learning outcome assessed by assessment task``).
The graph this system is about is made of those relations, so a second set of
words for them is a second account of what the system does.

There was one. `webapp/src/lib/violations.ts` held all sixteen under a comment
saying they "take their wording from `alignment.REGISTRY`" — and not one did.
Every entry was a paraphrase and most reversed the direction: C1 `decomposes_to`
read "objective derived from the course goal", P10 `delivers` read "activity
scheduled by a session guide", P5 `covers` read "material traceable to a
module". `viz.py` had a smaller version of the same drift: a comment calling a
C2 edge a "measures edge", a verb this system does not have.

These tests are cheap and the failure they prevent is not: a paraphrase reads
fine in review, and only turns up when a reader compares the app with the DOT
export, or the paper with either.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

from alignmentgraph_isd.core.alignment_graph import alignment, viz

WEBAPP_SRC = Path(__file__).resolve().parents[1] / "src/alignmentgraph_isd/webapp/src"
RELATION_IDS = set(alignment.REGISTRY)

#: `C7` is retired: it has no registry entry to take wording from, so the one
#: place that still shows it (an archived payload's rubric flag) writes its own
#: words and says "retired" in them. The only hand-written relation label left.
RETIRED_EXEMPT = {"C7", "C6"}


def _webapp_sources() -> list[Path]:
    return [p for p in WEBAPP_SRC.rglob("*.ts*")
            if "node_modules" not in p.parts and not p.name.endswith(".d.ts")]


def test_the_webapp_keeps_no_table_of_relation_wording():
    """A `C2: '...'` / `"P10": "..."` entry is the shape the old table had."""
    pattern = re.compile(r"""["']?\b(C\d{1,2}|P\d{1,2})\b["']?\s*:\s*['"]([^'"]{4,})['"]""")
    offenders: list[str] = []
    for path in _webapp_sources():
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            for relation_id, text in pattern.findall(line):
                if relation_id in RETIRED_EXEMPT or relation_id not in RELATION_IDS:
                    continue
                offenders.append(f"{path.relative_to(WEBAPP_SRC)}:{number}: {relation_id} -> {text!r}")
    assert not offenders, (
        "relation wording must come from the payload (`relation_coverage[id].label`), "
        "not from a table in the app:\n" + "\n".join(offenders))


def test_every_registry_verb_is_the_one_the_edge_carries():
    """The edge `type` IS `"<id>-<verb>"`, so the words on a rendered edge are
    the registry's own and cannot be restated anywhere."""
    for relation_id, relation in alignment.REGISTRY.items():
        assert relation.key == f"{relation_id}-{relation.edge_type}"


@pytest.mark.parametrize("verb", ["measures", "evaluates", "scores", "derived_from",
                                  "traceable_to", "scheduled_by"])
def test_no_retired_or_invented_verb_survives_in_the_graph_package(verb):
    """Words that name no relation. `measures` is the one that was actually
    there, in `viz._INVALID_EDGE`'s comment, outliving the relation it named."""
    package = Path(viz.__file__).parent
    live = {relation.edge_type for relation in alignment.REGISTRY.values()}
    assert verb not in live  # guard the guard
    for path in package.glob("*.py"):
        text = path.read_text(encoding="utf-8")
        assert not re.search(rf"\b{verb}\b\s+edge", text), f"{path.name} names a '{verb}' edge"


def test_a_leg_is_named_only_by_its_relation():
    """`ALIGNMENT_LEGS` is JUST THE IDS. Everything a leg is called — the verb
    it is reported under, the sentence the inspector shows — is looked up, so
    the table cannot grow a third name for C2/C3/C4. It had: `key` spelled them
    "measured"/"supported"/"prepares" and `letter` spelled them M/S/P."""
    assert all(isinstance(relation_id, str) for relation_id in alignment.ALIGNMENT_LEGS)
    for relation_id in alignment.ALIGNMENT_LEGS:
        assert relation_id in RELATION_IDS
        assert alignment.leg_verb(relation_id) == alignment.REGISTRY[relation_id].edge_type


def test_the_legend_says_the_same_words_in_both_renderers():
    """One list in the payload, so the DOT legend and the app's cannot drift —
    they had: this one listed six node rows to the DOT export's two, and never
    mentioned the alignment legs at all."""
    entries = viz._legend_entries()
    dot = "\n".join(viz._legend(entries))
    drawn = [e for e in entries["edges"] + entries["nodes"]
             if e["key"] in viz._LEGEND_DOT_EDGE_COLOR or e["key"] in viz._LEGEND_DOT_NODE_FILL]
    assert drawn, "the DOT legend draws nothing at all"
    for entry in drawn:
        assert entry["label"] in dot
    # And the aligned row names the legs rather than hardcoding "(M/S ok)",
    # which is how it went stale when the C4 leg was added.
    aligned = next(e for e in entries["nodes"] if e["key"] == "objective_aligned")
    for relation_id in alignment.ALIGNMENT_LEGS:
        assert relation_id in aligned["label"]


def test_the_legs_carry_no_third_name_for_their_relations():
    """The scalars an objective's alignment is reported under are the relations'
    own verbs, and the leg list adds no name of its own.

    `measured`/`supported`/`prepares` and the glyphs `M`/`S`/`P` were exactly
    that third naming, living inside the table whose job is to prevent a second
    one. They survive in ONE place, `viz._LEGACY_LEG_FLAGS`, which only reads
    them off an archived dump."""
    from alignmentgraph_isd.core.alignment_graph import viz as viz_module

    graph = _objective_with_full_triad()
    flags = viz_module.objective_annotations(graph)["objective:ILO-01"]

    verbs = {alignment.leg_verb(r) for r in alignment.ALIGNMENT_LEGS}
    assert verbs == {"assessed_by", "practiced_by", "prepares_for"}
    assert verbs <= set(flags)
    assert not ({"measured", "supported", "prepares"} & set(flags))
    # A leg names its relation and repeats nothing else.
    for leg in flags["legs"]:
        assert set(leg) == {"relation_id", "verb", "label", "ok"}

    source = Path(viz_module.__file__).read_text(encoding="utf-8")
    legacy = source.count('"measured"') + source.count('"supported"') + source.count('"prepares"')
    assert legacy == 3, "the old leg names belong only in _LEGACY_LEG_FLAGS"


def _objective_with_full_triad():
    from alignmentgraph_isd.core.alignment_graph import AlignmentGraph, NodeType

    graph = AlignmentGraph()
    graph.add_element_node(NodeType.OBJECTIVE, "ILO-01", {"id": "ILO-01", "level": "apply"})
    graph.add_element_node(NodeType.ASSESSMENT, "AT-01", {"item_id": "AT-01"})
    graph.add_element_node(NodeType.ACTIVITY, "TLA-01", {"activity_name": "practice"})
    graph.add_edge("C2-assessed_by", "objective:ILO-01", "assessment:AT-01",
                   relation_id="C2", established_by="id")
    graph.add_edge("C3-practiced_by", "objective:ILO-01", "activity:TLA-01",
                   relation_id="C3", established_by="id")
    graph.add_edge("C4-prepares_for", "activity:TLA-01", "assessment:AT-01",
                   relation_id="C4", established_by="id")
    return graph

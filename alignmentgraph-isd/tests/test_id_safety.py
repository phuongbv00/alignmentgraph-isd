"""An artifact's name must not depend on who committed first.

Developers self-commit since 2026-09-03: each deposits its own work set as it
finishes, so the family's output is visible to the checks while its Designer's
loop is still open. That changed what decides an id. The old rule was "keep the
model's id, rename it only if someone already took it" — fine while the whole
family landed in one batch, where the winner was plan order and deterministic;
under per-set commits the winner became whoever arrived first.

Ids are not a detail to leave to scheduling. Every cross-artifact edge in this
system is a model-written id reference — an item names its objective, an
activity names the item it prepares for, the implementation plan names the
activities it schedules — and the ids are written into the graph dump the
auditability claim rests on.

The answer is a composite id: the SET's ordinal paired with the artifact's own
(``AT-0203`` = third artifact of the second work set). The set's half is fixed
when the plan is numbered — before any Developer runs — so no two sets can name
the same artifact, and each set counts its own from 1 so the numbering stays
dense.
"""
from __future__ import annotations

from alignmentgraph_isd.core import dev_plans
from alignmentgraph_isd.core.alignment_graph import AlignmentGraph, NodeType
from alignmentgraph_isd.core.dev_plans import WorkSet

_SETS = [WorkSet(set_id="AS-01", ordinal=1), WorkSet(set_id="AS-02", ordinal=2)]

#: Both Developers independently name their first item AT-01, which is exactly
#: what workers that never coordinate do.
_PAYLOADS = [
    {"set_id": "AS-01", "items": [{"item_id": "AT-01", "question": "one"},
                                  {"item_id": "AT-02", "question": "two"}]},
    {"set_id": "AS-02", "items": [{"item_id": "AT-01", "question": "three"}]},
]


def _merge(payloads, taken=frozenset(), sets=None):
    return dev_plans.remap_and_tag(
        sets or _SETS, payloads, id_field="item_id", id_prefix="AT", taken=taken)


def test_two_developers_naming_the_same_item_do_not_collide():
    merged = _merge(_PAYLOADS)

    ids = [item["item_id"] for item in merged]
    assert len(set(ids)) == len(ids) == 3, f"ids collided: {ids}"
    assert ids == ["AT-0101", "AT-0102", "AT-0201"], (
        "set ordinal, then the artifact's own within that set")
    assert [item["question"] for item in merged] == ["one", "two", "three"], (
        "renumbering must not reorder or drop the work")


def test_the_ids_do_not_depend_on_which_set_commits_first():
    """The property the reserved block exists for. Same plan, payloads
    arriving in the other order — and the same artifact keeps the same name."""
    forward = {item["question"]: item["item_id"] for item in _merge(_PAYLOADS)}
    reversed_arrival = {item["question"]: item["item_id"]
                        for item in _merge(list(reversed(_PAYLOADS)))}

    assert forward == reversed_arrival == {
        "one": "AT-0101", "two": "AT-0102", "three": "AT-0201"}


def test_a_set_committed_on_its_own_lands_where_it_would_have_in_a_batch():
    """Per-set commits must produce the state a batched commit produced, or
    the change of commit granularity would silently change the artifact."""
    batched = _merge(_PAYLOADS)

    one_at_a_time: list = []
    taken: set[str] = set()
    for payload in _PAYLOADS:
        merged = _merge([payload], taken=frozenset(taken))
        one_at_a_time += merged
        taken |= {item["item_id"] for item in merged}

    assert [i["item_id"] for i in one_at_a_time] == [i["item_id"] for i in batched]


def test_a_prolific_set_never_reaches_the_next_sets_numbers():
    """The composition is what makes this structural rather than budgeted: a
    set's artifacts all sit under its own ordinal, so however many it writes it
    cannot walk into its neighbour's."""
    big = [{"set_id": "AS-01", "items": [{"item_id": f"AT-{n:02d}"} for n in range(1, 25)]}]
    merged = _merge(big + [_PAYLOADS[1]])

    first = [i["item_id"] for i in merged if i.get("plan_set") == "AS-01"]
    second = [i["item_id"] for i in merged if i.get("plan_set") == "AS-02"]
    assert len(set(first)) == len(first) == 24
    assert all(i.startswith("AT-01") for i in first), "a set left its own ordinal"
    assert not set(first) & set(second)


def test_ids_stay_short_and_conventional():
    """Deliberate, and measured. A namespacing scheme (`AT-01-AS-02`) is also
    collision-free, and it broke P10/P11 outright: the implementation plan
    names the activities it schedules by id, and a longer, less guessable id
    raises the failure rate of every model-written cross-reference — on
    exactly the small models this study is about."""
    from alignmentgraph_isd.core.validation import _ID_PATTERN

    for item in _merge(_PAYLOADS):
        item_id = item["item_id"]
        assert _ID_PATTERN.match(item_id)
        assert len(item_id) <= 8, f"{item_id} is longer than an id a model writes"


def test_the_numbering_is_dense_within_a_set():
    """No gaps to explain. A single reserved range per set leaves them — set 1
    stops at AT-10 and set 2 starts at AT-21 — and that gap is a block boundary
    showing through into the deliverable."""
    merged = _merge([{"set_id": "AS-02", "items": [
        {"item_id": "X"}, {"item_id": "Y"}, {"item_id": "Z"}]}],
        sets=[WorkSet(set_id="AS-02", ordinal=2)])

    assert [i["item_id"] for i in merged] == ["AT-0201", "AT-0202", "AT-0203"]


def test_a_within_set_reference_is_a_position_and_resolves():
    """The model writes no ids, so a reference to another activity in its own
    block is the position it wrote it at. Cross-family references are left
    alone: they name an upstream family the Developer read in committed form."""
    merged = dev_plans.remap_and_tag(
        [WorkSet(set_id="AB-02", ordinal=2)],
        [{"set_id": "AB-02", "items": [
            {"prepares_for_assessment": ["AT-0103"]},
            {"prerequisite_activities": [1]},
        ]}],
        id_field="id", self_ref_fields=("prerequisite_activities",), id_prefix="TLA")

    assert [i["id"] for i in merged] == ["TLA-0201", "TLA-0202"]
    assert merged[1]["prerequisite_activities"] == ["TLA-0201"], "same-set ref dangled"
    assert merged[0]["prepares_for_assessment"] == ["AT-0103"], (
        "a cross-family ref must not be rewritten")


def test_the_deposit_holds_the_graph_lock():
    """Reading the ids in play and then writing nodes chosen from what was read
    is only correct if nothing lands in between. The commits run one at a time
    on the driver's thread; the transaction is what keeps that true while the
    Developers run on several (``fanout_workers``)."""
    graph = AlignmentGraph()
    with graph.transaction():
        graph.add_element_node(NodeType.ASSESSMENT, "AT-01", {"item_id": "AT-01"})
        # Re-entrant: a caller already inside one costs nothing.
        with graph.transaction():
            graph.add_element_node(NodeType.ASSESSMENT, "AT-02", {"item_id": "AT-02"})
    assert len(graph.element_nodes(NodeType.ASSESSMENT)) == 2


# ── the model does not name these artifacts at all ───────────────────────────

def test_an_id_the_model_writes_anyway_is_ignored():
    """The schemas no longer ask for one, but a model that writes an id from
    habit must not get it committed — that would put half the family back on
    model-chosen names and reopen the collision the block closes."""
    merged = _merge([{"set_id": "AS-02", "items": [
        {"item_id": "AT-99", "question": "written from habit"}]}],
        sets=[WorkSet(set_id="AS-02", ordinal=2)])

    assert merged[0]["item_id"] == "AT-0201"


def test_an_artifact_with_no_id_still_gets_one():
    """The normal case now: the model submits questions, the harness names
    them. Before, an item with no id was committed WITHOUT one — and an
    element with no id is unreachable by every relation in the registry."""
    merged = _merge([{"set_id": "AS-01", "items": [
        {"question": "one"}, {"question": "two"}]}],
        sets=[WorkSet(set_id="AS-01", ordinal=1)])

    assert [i["item_id"] for i in merged] == ["AT-0101", "AT-0102"]


def test_material_units_carry_ordinals_the_way_every_other_family_does():
    """The gap this closes, and why nothing caught it.

    ``material_work_units`` is the only work-set builder that does not go
    through ``_cap_and_number``, which was the sole place ``ordinal`` was
    assigned — so every material set kept the dataclass default of 1, ids came
    out MAT-0101..MAT-0108 across SIX different modules, and uniqueness rested
    on the ``taken`` scan: the "whoever commits first" scheme this file exists
    to rule out. Every other test here hand-builds its WorkSets with distinct
    ordinals, so none of them could see it. This one uses the real builder.
    """
    modules = [{"id": f"MOD-{i:02d}"} for i in range(1, 4)]
    media = [{"id": f"MED-{i:02d}", "media_type": "slides",
              "for_modules": [f"MOD-{i:02d}"]} for i in range(1, 4)]

    sets = dev_plans.material_work_units(modules, media, [])
    assert [ws.ordinal for ws in sets] == [1, 2, 3]
    assert [ws.set_id for ws in sets] == ["MU-MOD-01", "MU-MOD-02", "MU-MOD-03"], (
        "module-derived set ids are read by plan_set, the regen and the graph "
        "dump — numbering must not rename them")

    merged = dev_plans.remap_and_tag(
        sets,
        [{"set_id": ws.set_id, "items": [{"title": "a"}, {"title": "b"}]} for ws in sets],
        id_field="id", id_prefix="MAT")
    ids = [item["id"] for item in merged]
    assert ids == ["MAT-0101", "MAT-0102", "MAT-0201", "MAT-0202",
                   "MAT-0301", "MAT-0302"]
    assert len(set(ids)) == len(ids)

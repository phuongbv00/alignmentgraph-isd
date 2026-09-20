"""core/dev_plans.py: dev-plan normalization is pure, deterministic, and
never lets a fan-out shape depend on unvalidated LLM output — every ground
truth obligation must survive into exactly one WorkSet regardless of what
(if anything) the LLM proposed."""
from __future__ import annotations

from alignmentgraph_isd.core import dev_plans as dp


# ── assessment ───────────────────────────────────────────────────────────

def test_assessment_llm_plan_covers_everything_kept_verbatim():
    targets = {"ILO-01": ["formative"], "ILO-02": ["formative"]}
    parsed = {"sets": [
        {"set_id": "X", "objectives": ["ILO-01", "ILO-02"], "plan_categories": ["formative"],
         "set_hint": "integrated case", "rationale": "shared scenario"},
    ]}
    sets, stats = dp.assessment_work_sets(parsed, ["ILO-01", "ILO-02"], targets)
    assert len(sets) == 1
    assert sets[0].set_id == "AS-01"
    assert set(sets[0].pairs) == {("ILO-01", "formative"), ("ILO-02", "formative")}
    assert stats["fallback_used"] is False
    assert stats["appended_sets"] == 0
    assert stats["dropped_pairs"] == 0


def test_assessment_filler_pairs_dropped_not_kept():
    """The 0.8B ballooning failure mode: a set claims a category the plan
    never promised for that objective. It must be silently dropped, not
    accepted as an extra obligation."""
    targets = {"ILO-01": ["formative"]}
    parsed = {"sets": [
        {"objectives": ["ILO-01"], "plan_categories": ["formative", "summative", "diagnostic"]},
    ]}
    sets, stats = dp.assessment_work_sets(parsed, ["ILO-01"], targets)
    all_pairs = {p for ws in sets for p in ws.pairs}
    assert all_pairs == {("ILO-01", "formative")}
    assert stats["dropped_pairs"] == 2


def test_assessment_unknown_objective_dropped():
    targets = {"ILO-01": ["formative"]}
    parsed = {"sets": [{"objectives": ["ILO-99"], "plan_categories": ["formative"]}]}
    sets, stats = dp.assessment_work_sets(parsed, ["ILO-01"], targets)
    assert stats["dropped_lo_refs"] == 1
    # ILO-99's set contributes nothing real; ILO-01/formative still gets a
    # set via the uncovered-pair top-up.
    assert {p for ws in sets for p in ws.pairs} == {("ILO-01", "formative")}
    assert stats["fallback_used"] is True  # zero valid LLM sets survived


def test_assessment_uncovered_pair_appended_not_fallback():
    targets = {"ILO-01": ["formative"], "ILO-02": ["summative"]}
    parsed = {"sets": [{"objectives": ["ILO-01"], "plan_categories": ["formative"]}]}
    sets, stats = dp.assessment_work_sets(parsed, ["ILO-01", "ILO-02"], targets)
    assert stats["fallback_used"] is False
    assert stats["appended_sets"] == 1
    sources = {ws.source for ws in sets}
    assert "llm" in sources and "appended" in sources


def test_assessment_empty_or_garbage_plan_is_pure_fallback():
    targets = {"ILO-01": ["formative"], "ILO-02": ["summative"]}
    for parsed in ({}, None, {"sets": "not a list"}, {"sets": []}):
        sets, stats = dp.assessment_work_sets(parsed, ["ILO-01", "ILO-02"], targets)
        assert stats["fallback_used"] is True
        assert {p for ws in sets for p in ws.pairs} == {("ILO-01", "formative"), ("ILO-02", "summative")}
        assert all(ws.source == "fallback" for ws in sets)


def test_assessment_empty_targets_defaults_to_lo_x_summative():
    sets, stats = dp.assessment_work_sets({}, ["ILO-01", "ILO-02"], {})
    assert {p for ws in sets for p in ws.pairs} == {("ILO-01", "summative"), ("ILO-02", "summative")}
    assert stats["pair_count"] == 2


def test_assessment_no_objectives_at_all_returns_no_sets():
    sets, stats = dp.assessment_work_sets({}, [], {})
    assert sets == []
    assert stats["pair_count"] == 0


def test_assessment_namespaced_ids_are_normalized():
    targets = {"objective:ILO-01": ["formative"]}
    parsed = {"sets": [{"objectives": ["objective:ILO-01"], "plan_categories": ["formative"]}]}
    sets, stats = dp.assessment_work_sets(parsed, ["ILO-01"], targets)
    assert {p for ws in sets for p in ws.pairs} == {("ILO-01", "formative")}
    assert stats["dropped_pairs"] == 0


def test_assessment_overflow_capped_and_merged_never_drops_a_pair():
    lo_ids = [f"ILO-{i:02d}" for i in range(1, 6)]  # 5 pairs -> cap = min(5, MAX_SETS_HARD_CAP) = 5
    targets = {lo: ["summative"] for lo in lo_ids}
    # 20 singleton LLM sets, one per pair repeated 4x with junk duplicates collapsed by pair dedup
    parsed = {"sets": [
        {"objectives": [lo_ids[i % 5]], "plan_categories": ["summative"]} for i in range(20)
    ]}
    sets, stats = dp.assessment_work_sets(parsed, lo_ids, targets)
    assert len(sets) <= 5
    all_pairs = {p for ws in sets for p in ws.pairs}
    assert all_pairs == {(lo, "summative") for lo in lo_ids}
    # ids are stable AS-01.. renumbering
    assert [ws.set_id for ws in sets] == [f"AS-{i:02d}" for i in range(1, len(sets) + 1)]


# ── activity ─────────────────────────────────────────────────────────────

def test_activity_llm_blocks_carry_items_by_lo():
    items_by_lo = {"ILO-01": ["AT-01"], "ILO-02": ["AT-02"]}
    parsed = {"activity_blocks": [
        {"objectives": ["ILO-01", "ILO-02"], "block_theme": "intro"},
    ]}
    sets, stats = dp.activity_work_sets(parsed, ["ILO-01", "ILO-02"], items_by_lo)
    assert len(sets) == 1
    assert sets[0].objectives == ("ILO-01", "ILO-02")
    assert sets[0].payload["assessment_items"] == ["AT-01", "AT-02"]
    assert stats["fallback_used"] is False


def test_activity_fallback_when_plan_missing():
    sets, stats = dp.activity_work_sets(None, ["ILO-01"], {})
    assert stats["fallback_used"] is True
    assert len(sets) == 1
    assert sets[0].objectives == ("ILO-01",)


def test_activity_uncovered_lo_appended():
    parsed = {"activity_blocks": [{"objectives": ["ILO-01"]}]}
    sets, stats = dp.activity_work_sets(parsed, ["ILO-01", "ILO-02"], {})
    covered = {lo for ws in sets for lo in ws.objectives}
    assert covered == {"ILO-01", "ILO-02"}
    assert stats["appended_sets"] == 1


# ── content (deterministic) ─────────────────────────────────────────────

def test_material_units_one_per_module_media_sliced_by_for_modules():
    modules = [{"id": "MOD-01"}, {"id": "MOD-02"}]
    media = [
        {"id": "MED-01", "for_modules": ["MOD-01"], "respects_constraints": ["CON-01"]},
        {"id": "MED-02", "for_modules": ["MOD-02"]},
    ]
    constraints = [{"id": "CON-01", "statement": "low bandwidth"}]
    sets = dp.material_work_units(modules, media, constraints)
    assert {ws.set_id for ws in sets} == {"MU-MOD-01", "MU-MOD-02"}
    by_id = {ws.set_id: ws for ws in sets}
    assert [m["id"] for m in by_id["MU-MOD-01"].payload["media_selections"]] == ["MED-01"]
    assert by_id["MU-MOD-01"].payload["constraints"][0]["id"] == "CON-01"
    assert [m["id"] for m in by_id["MU-MOD-02"].payload["media_selections"]] == ["MED-02"]


def test_material_units_unassigned_media_reaches_every_module():
    modules = [{"id": "MOD-01"}, {"id": "MOD-02"}]
    media = [{"id": "MED-01"}]  # no for_modules -> attaches to all
    sets = dp.material_work_units(modules, media, [])
    for ws in sets:
        assert [m["id"] for m in ws.payload["media_selections"]] == ["MED-01"]


def test_material_units_zero_modules_degenerates_to_whole_pool():
    sets = dp.material_work_units([], [{"id": "MED-01"}], [])
    assert len(sets) == 1
    assert sets[0].set_id == "MU-ALL"
    assert sets[0].payload["modules"] == []


def test_material_units_overflow_is_merged_then_split_back_to_answerable_size():
    """The count cap merges the overflow into one tail; the SIZE bound then
    splits that tail back down. Order matters: the cap on calls used to make
    the calls unanswerable — a tail carrying every leftover module, and learner
    materials are the longest element the harness produces (~1,240 chars mean,
    1,710 max, measured on run single_20260901_205901).

    So the set COUNT may now exceed MAX_MATERIAL_UNITS a little. That is the
    trade, stated: an oversized set costs everything it was going to produce,
    an extra call costs one call."""
    modules = [{"id": f"MOD-{i:02d}"} for i in range(1, 20)]
    sets = dp.material_work_units(modules, [], [])

    limit = dp.max_units("material")
    assert all(len(ws.payload["modules"]) <= limit for ws in sets), (
        f"a unit exceeds what one call can answer: "
        f"{[len(ws.payload['modules']) for ws in sets]}")
    all_modules = [m["id"] for ws in sets for m in ws.payload["modules"]]
    assert set(all_modules) == {m["id"] for m in modules}, "no module was dropped"
    assert len(all_modules) == len(set(all_modules)), "no module was duplicated"
    # Still bounded, and still far below one call per module.
    assert len(sets) < len(modules)
    assert len({ws.set_id for ws in sets}) == len(sets), "set ids stay unique"


# ── fan-in helpers ───────────────────────────────────────────────────────

def test_two_workers_that_propose_the_same_id_still_get_distinct_ones():
    """Every production caller passes an ``id_prefix`` (`fanout.SPECS`: AT / TLA
    / MAT), so ids are COMPOSED from the set ordinal and the model's own id is
    discarded. Called without a prefix this takes a branch nothing reaches, and
    the old version of this test pinned that branch's output (``AT-01-AS-02``)
    — an id shape `test_id_safety` records as having broken P10/P11."""
    sets = [dp.WorkSet(set_id="AS-01", ordinal=1), dp.WorkSet(set_id="AS-02", ordinal=2)]
    payloads = [
        {"set_id": "AS-01", "items": [{"item_id": "AT-01", "question": "q1"}]},
        {"set_id": "AS-02", "items": [{"item_id": "AT-01", "question": "q2"}]},
    ]
    merged = dp.remap_and_tag(sets, payloads, id_field="item_id", id_prefix="AT")
    ids = [i["item_id"] for i in merged]
    assert len(set(ids)) == 2, f"two workers collided: {ids}"
    assert ids == ["AT-0101", "AT-0201"], ids
    assert [i["plan_set"] for i in merged] == ["AS-01", "AS-02"]
    # The questions must not have been swapped by the renaming.
    assert [i["question"] for i in merged] == ["q1", "q2"]


def test_remap_and_tag_self_refs_are_positions_resolved_to_assigned_ids():
    """The model writes no id at all (the harness names its artifacts), so a
    reference to another activity in its own block is the POSITION it wrote
    it at: [1] is the first."""
    sets = [dp.WorkSet(set_id="AB-01", ordinal=1), dp.WorkSet(set_id="AB-02", ordinal=2)]
    payloads = [
        {"set_id": "AB-01", "items": [{"activity_name": "warm-up"}]},
        {"set_id": "AB-02", "items": [
            {"activity_name": "lab"},
            {"activity_name": "debrief", "prerequisite_activities": [1]},
        ]},
    ]
    merged = dp.remap_and_tag(sets, payloads, id_field="id", id_prefix="TLA",
                              self_ref_fields=("prerequisite_activities",))
    by_name = {i["activity_name"]: i for i in merged}
    assert by_name["warm-up"]["id"] == "TLA-0101"
    assert by_name["lab"]["id"] == "TLA-0201"
    assert by_name["debrief"]["id"] == "TLA-0202"
    assert by_name["debrief"]["prerequisite_activities"] == ["TLA-0201"], (
        "[1] means the first activity of THIS set, not of the family")


def test_a_self_reference_that_resolves_to_nothing_is_dropped():
    """A dangling id in the graph is invisible; a dropped reference shows up in
    the coverage numbers. `_establish` builds `precedes` edges from this field,
    so a reference that names nothing manufactures an edge to nowhere."""
    merged = dp.remap_and_tag(
        [dp.WorkSet(set_id="AB-01", ordinal=1)],
        [{"set_id": "AB-01", "items": [{"prerequisite_activities": [9, "TLA-01", True]}]}],
        id_field="id", id_prefix="TLA", self_ref_fields=("prerequisite_activities",))

    assert merged[0]["prerequisite_activities"] == []


def test_an_artifact_with_no_id_is_named_by_the_harness():
    """The model writes no id at all since 2026-09-03 — the field is gone from
    the schemas — so "no id here" is the NORMAL case, not an edge case. The old
    version of this test asserted the item was committed WITHOUT an id, which
    is how an element becomes unreachable in the graph."""
    sets = [dp.WorkSet(set_id="AS-01", ordinal=1)]
    payloads = [{"set_id": "AS-01", "items": [{"question": "no id here"}]}]
    merged = dp.remap_and_tag(sets, payloads, id_field="item_id", id_prefix="AT")
    assert merged == [{"question": "no id here", "item_id": "AT-0101",
                       "plan_set": "AS-01"}]


def test_remap_and_tag_order_follows_dev_plan_order_not_payload_order():
    sets = [dp.WorkSet(set_id="AS-01", ordinal=1), dp.WorkSet(set_id="AS-02", ordinal=2)]
    payloads = [
        {"set_id": "AS-02", "items": [{"question": "second"}]},
        {"set_id": "AS-01", "items": [{"question": "first"}]},
    ]
    merged = dp.remap_and_tag(sets, payloads, id_field="item_id", id_prefix="AT")
    assert [i["item_id"] for i in merged] == ["AT-0101", "AT-0201"]


# ── round-trip ───────────────────────────────────────────────────────────

def test_work_set_dict_carries_the_ordinal():
    # ordinal=3, not the default: it is the first half of every id this set's
    # artifacts commit under, and a dump that drops it reads as set 1.
    ws = dp.WorkSet(set_id="AS-01", objectives=("ILO-01",), pairs=(("ILO-01", "formative"),),
                     payload={"a": 1}, source="llm", ordinal=3)
    assert ws.as_dict()["ordinal"] == 3


# ── set SIZE, not just set count ────────────────────────────────────────────
# Splitting by objective alone says nothing about how much a set asks for.
# Three objectives is a small activity block and a large assessment set,
# because an assessment obligation produces an item AND the criterion that
# marks it. Estimated output length is what the two have in common, and it is
# what the Developer's one call actually has to fit.

def test_the_budget_is_derived_from_measured_element_sizes():
    assert dp.max_units("assessment") == dp.SET_OUTPUT_BUDGET // dp.UNIT_CHARS["assessment"]
    # The longest element gets the smallest set, which is the whole point of
    # sizing by length rather than by count.
    assert dp.max_units("material") < dp.max_units("activity")
    # An unknown family is never split into single units by accident.
    assert dp.max_units("nonexistent") == 1


def test_an_oversized_assessment_set_is_split_by_pair_not_by_objective():
    """One objective carrying three plan categories is THREE obligations —
    three items and three criteria. Counting objectives would call that a set
    of one."""
    targets = {"ILO-01": ["diagnostic", "formative", "summative"],
               "ILO-02": ["diagnostic", "formative", "summative"]}
    lo_ids = ["ILO-01", "ILO-02"]
    parsed = {"sets": [
        {"objectives": lo_ids, "plan_categories": ["diagnostic", "formative", "summative"]},
    ]}
    sets, stats = dp.assessment_work_sets(parsed, lo_ids, targets)

    limit = dp.max_units("assessment")
    assert all(len(ws.pairs) <= limit for ws in sets), [len(ws.pairs) for ws in sets]
    # Every promised pair survives the split, exactly once.
    all_pairs = [p for ws in sets for p in ws.pairs]
    assert len(all_pairs) == len(set(all_pairs)) == 6
    assert set(all_pairs) == {(lo, c) for lo in lo_ids
                              for c in ("diagnostic", "formative", "summative")}
    assert stats["set_count"] == len(sets)
    assert [ws.set_id for ws in sets] == [f"AS-{i:02d}" for i in range(1, len(sets) + 1)]


def test_the_count_cap_can_no_longer_produce_an_unanswerable_tail():
    """A 33-objective scenario. The cap on the number of CALLS used to merge the
    overflow into one tail set, so the cap on calls made the calls
    unanswerable. Size is applied after the merge and wins."""
    lo_ids = [f"ILO-{i:02d}" for i in range(1, 34)]
    targets = {lo: ["summative"] for lo in lo_ids}
    sets, _stats = dp.assessment_work_sets({}, lo_ids, targets)

    limit = dp.max_units("assessment")
    assert all(len(ws.pairs) <= limit for ws in sets), (
        f"an unanswerable tail survived: {sorted(len(ws.pairs) for ws in sets)[-3:]}")
    all_pairs = [p for ws in sets for p in ws.pairs]
    assert set(all_pairs) == {(lo, "summative") for lo in lo_ids}
    assert len(all_pairs) == len(set(all_pairs))


def test_an_oversized_activity_block_is_split_and_keeps_its_item_slice():
    los = [f"ILO-{i:02d}" for i in range(1, 21)]
    items_by_lo = {lo: [f"AT-{lo}"] for lo in los}
    parsed = {"activity_blocks": [{"objectives": los, "block_theme": "everything"}]}
    sets, _stats = dp.activity_work_sets(parsed, los, items_by_lo)

    limit = dp.max_units("activity")
    assert all(len(ws.objectives) <= limit for ws in sets)
    assert {lo for ws in sets for lo in ws.objectives} == set(los)
    # Each piece is handed the items for ITS objectives, not the whole pool:
    # a Developer told to prepare learners for items it is not writing for
    # would align its activities to the wrong things.
    for ws in sets:
        assert set(ws.payload["assessment_items"]) == {f"AT-{lo}" for lo in ws.objectives}


def test_a_set_that_already_fits_is_left_exactly_as_it_was():
    """Splitting is a backstop, not a policy: a grouping the agent chose and
    that fits must survive untouched, or the fan-out width stops being the
    agent's decision."""
    targets = {"ILO-01": ["formative"], "ILO-02": ["formative"]}
    parsed = {"sets": [
        {"objectives": ["ILO-01", "ILO-02"], "plan_categories": ["formative"],
         "set_hint": "integrated case", "rationale": "shared scenario"},
    ]}
    sets, _stats = dp.assessment_work_sets(parsed, ["ILO-01", "ILO-02"], targets)
    assert len(sets) == 1
    assert sets[0].payload["set_hint"] == "integrated case"
    assert sets[0].source == "llm"


# ── the planned quantity, not the objective count ───────────────────────────

def test_an_objective_keeps_its_own_pairs_when_a_set_is_split():
    """The user's shape: two objectives, one planned set, and each objective
    needs more items than one call can write. Chunking the FLAT pair list
    would hand a piece the tail of ILO-01 and the head of ILO-02, throwing away
    the grouping the plan chose."""
    lo_ids = [f"ILO-{i:02d}" for i in range(1, 5)]          # 4 x 3 = 12 pairs
    cats = ["diagnostic", "formative", "summative"]
    targets = {lo: cats for lo in lo_ids}
    parsed = {"sets": [{"objectives": lo_ids, "plan_categories": cats}]}
    sets, _stats = dp.assessment_work_sets(parsed, lo_ids, targets)

    assert len(sets) > 1, "12 pairs does not fit one call"
    for ws in sets:
        owners = {lo for lo, _ in ws.pairs}
        assert len(owners) == 1, f"a piece spans objectives {owners}"
        assert ws.objectives == tuple(owners)
    all_pairs = [p for ws in sets for p in ws.pairs]
    assert len(all_pairs) == len(set(all_pairs)) == 12


def test_activity_splits_on_the_planned_count_not_the_objective_count():
    """One objective needing a six-step progression is a bigger job than three
    objectives needing one activity each. Counting objectives cannot tell them
    apart, so the planner states the count and the split uses it."""
    limit = dp.max_units("activity")

    small = {"activity_blocks": [
        {"objectives": ["ILO-01", "ILO-02", "ILO-03"], "expected_activities": 3}]}
    sets, _ = dp.activity_work_sets(
        small, ["ILO-01", "ILO-02", "ILO-03"], {})
    assert len(sets) == 1, "three light objectives are one call"

    planned = limit + 2
    assert planned <= dp.MAX_EXPECTED_PER_SET, "keep the case inside the clamp"
    big = {"activity_blocks": [{"objectives": ["ILO-01"], "expected_activities": planned}]}
    sets, _ = dp.activity_work_sets(big, ["ILO-01"], {})
    assert len(sets) == 2, "one heavy objective is two"
    quotas = [ws.payload["expected_activities"] for ws in sets]
    assert sum(quotas) == planned, "the plan is divided across batches, not repeated"
    assert all(q <= limit for q in quotas)


def test_a_backstop_split_still_gives_each_piece_a_distinct_scope():
    """When the planner does NOT scope an oversized block itself, the pieces
    must still not be interchangeable: two developers handed the same
    assignment write the same activities twice, and the id remap keeps both."""
    limit = dp.max_units("activity")
    parsed = {"activity_blocks": [
        {"objectives": ["ILO-01"], "expected_activities": limit + 2, "block_theme": "ramp"}]}
    sets, _ = dp.activity_work_sets(parsed, ["ILO-01"], {})

    rendered = [dp.render_activity_set(ws) for ws in sets]
    assert "part 1 of 2 of 'ramp'" in rendered[0]
    assert "part 2 of 2 of 'ramp'" in rendered[1]
    assert rendered[0] != rendered[1]
    assert all("how many activities to write:" in r for r in rendered)


def test_a_planned_count_is_clamped_not_trusted():
    """The planner is asked, not obeyed: a 2B model that writes 40 would turn
    one block into a dozen calls, and one that writes nothing usable must not
    collapse the estimate to zero."""
    assert dp._expected(40, 1) == dp.MAX_EXPECTED_PER_SET
    assert dp._expected(None, 2) == 2 * dp.ACTIVITIES_PER_OBJECTIVE
    assert dp._expected("not a number", 1) == dp.ACTIVITIES_PER_OBJECTIVE
    assert dp._expected(0, 1) == dp.ACTIVITIES_PER_OBJECTIVE
    assert dp._expected(2, 5) == 2, "a real number is used as given"


def test_a_module_with_many_media_selections_is_split_by_them():
    """A material realizes one of the module's media selections, so the media
    count IS the planned quantity — and materials are the longest element the
    harness writes. One unit per module said nothing about that."""
    limit = dp.max_units("material")
    modules = [{"id": "MOD-01"}]
    media = [{"id": f"MED-{i:02d}", "for_modules": ["MOD-01"]} for i in range(1, limit * 2 + 1)]
    sets = dp.material_work_units(modules, media, [])

    assert len(sets) == 2
    assert all(len(ws.payload["media_selections"]) <= limit for ws in sets)
    seen = [m["id"] for ws in sets for m in ws.payload["media_selections"]]
    assert len(seen) == len(set(seen)) == limit * 2, "no media selection lost or duplicated"
    assert len({ws.set_id for ws in sets}) == 2


def test_blocks_the_planner_scoped_itself_survive_intact():
    """Scoping a set is the PLANNER's job: it is told the budget and asked to
    emit several blocks with distinct themes when an objective needs more than
    one call's worth, so two developers can never be handed the same ground.

    The count cap used to undo exactly that. Based on the OBJECTIVE count, a
    single objective allowed a single block, so two correctly scoped blocks for
    ILO-01 were merged back into one and the themes that kept them apart were
    discarded. You never need more blocks than activities."""
    parsed = {"activity_blocks": [
        {"objectives": ["ILO-01"], "block_theme": "first contact with the tool",
         "expected_activities": 5},
        {"objectives": ["ILO-01"], "block_theme": "unaided practice on a real case",
         "expected_activities": 5},
    ]}
    sets, stats = dp.activity_work_sets(parsed, ["ILO-01"], {})

    assert len(sets) == 2
    assert [ws.payload["block_theme"] for ws in sets] == [
        "first contact with the tool", "unaided practice on a real case"]
    assert stats["oversized_splits"] == 0, "nothing needed cutting"
    # No batch marker: these carry the planner's own scope, not an ordinal.
    assert all("batch" not in ws.payload for ws in sets)


def test_the_harness_records_when_it_had_to_cut_a_planned_set():
    """The only number that separates a plan doing its job from one the
    backstop is carrying."""
    limit = dp.max_units("activity")
    parsed = {"activity_blocks": [
        {"objectives": ["ILO-01"], "block_theme": "pipeline", "expected_activities": limit + 2}]}
    sets, stats = dp.activity_work_sets(parsed, ["ILO-01"], {})

    assert stats["oversized_splits"] == 1
    assert len(sets) == 2
    # The fallback scope names the theme it is a part OF, so the developer is
    # at least told what whole it is carving up.
    rendered = dp.render_activity_set(sets[1])
    assert "part 2 of 2 of 'pipeline'" in rendered
    assert "do not repeat" in rendered


# ── cross-set duplication and the planner's item count (2026-09-05) ────────

def test_assessment_a_pair_named_in_two_sets_is_written_once():
    """MEASURED (run e81b8108): the plan put ILO-02 x formative in two sets,
    each Developer was told to write "the" item for it, and two items landed
    for one obligation. The pair stays in the set that named it first."""
    targets = {"ILO-01": ["diagnostic", "summative"], "ILO-02": ["formative", "summative"],
               "ILO-03": ["summative"]}
    parsed = {"sets": [
        {"objectives": ["ILO-01", "ILO-02", "ILO-03"], "plan_categories": ["summative"]},
        {"objectives": ["ILO-01", "ILO-02"], "plan_categories": ["formative"]},
        {"objectives": ["ILO-02", "ILO-03"], "plan_categories": ["formative"]},
    ]}
    sets, stats = dp.assessment_work_sets(parsed, ["ILO-01", "ILO-02", "ILO-03"], targets)
    pairs = [p for ws in sets for p in ws.pairs]
    assert len(pairs) == len(set(pairs)), f"a pair is written twice: {pairs}"
    assert set(pairs) == {("ILO-01", "diagnostic"), ("ILO-01", "summative"),
                          ("ILO-02", "formative"), ("ILO-02", "summative"),
                          ("ILO-03", "summative")}
    assert stats["duplicate_pairs"] == 1
    assert stats["dropped_pairs"] == 2      # ILO-01 x formative, ILO-03 x formative
    assert stats["appended_sets"] == 1      # ILO-01 x diagnostic
    # The third set lost its only surviving pair and runs no Developer.
    assert len(sets) == 3


def test_assessment_expected_items_is_the_planners_count_within_bounds():
    targets = {"ILO-01": ["formative"], "ILO-02": ["formative"]}
    limit = dp.max_units("assessment")

    def one(expected):
        parsed = {"sets": [{"objectives": ["ILO-01", "ILO-02"],
                                       "plan_categories": ["formative"],
                                       "expected_items": expected}]}
        sets, _ = dp.assessment_work_sets(parsed, ["ILO-01", "ILO-02"], targets)
        return sets[0]

    assert one(4).payload["expected_items"] == 4
    assert one(1).payload["expected_items"] == 2, "never below one per pair"
    assert one(None).payload["expected_items"] == 2, "missing -> one per pair"
    assert one("lots").payload["expected_items"] == 2
    assert one(limit + 10).payload["expected_items"] == limit, "never above one call's worth"

    text = dp.render_assessment_set(one(4))
    assert "write exactly 4 items" in text and "at least once" in text
    text = dp.render_assessment_set(one(None))
    assert "write exactly 2 items — one for each" in text


def test_assessment_fallback_sets_carry_a_count_too():
    targets = {"ILO-01": ["formative", "summative"]}
    sets, _ = dp.assessment_work_sets({}, ["ILO-01"], targets)
    assert sets[0].payload["expected_items"] == 2
    assert "write exactly 2 items" in dp.render_assessment_set(sets[0])


def test_activity_an_objective_in_two_untitled_blocks_is_written_once():
    parsed = {"activity_blocks": [
        {"objectives": ["ILO-01", "ILO-02"]},
        {"objectives": ["ILO-02"]},
    ]}
    sets, stats = dp.activity_work_sets(parsed, ["ILO-01", "ILO-02"])
    covered = [lo for ws in sets for lo in ws.objectives]
    assert sorted(covered) == ["ILO-01", "ILO-02"]
    assert stats["duplicate_pairs"] == 1


def test_activity_a_themed_second_block_for_one_objective_is_the_planner_splitting_it():
    parsed = {"activity_blocks": [
        {"objectives": ["ILO-01"], "block_theme": "first contact"},
        {"objectives": ["ILO-01"], "block_theme": "unaided practice"},
    ]}
    sets, stats = dp.activity_work_sets(parsed, ["ILO-01"])
    assert len(sets) == 2 and stats["duplicate_pairs"] == 0


def test_material_expected_count_is_the_planners_within_bounds():
    """A broad module may need more materials than it has media selections;
    the planner says so on the module. Floor: one per media selection."""
    limit = dp.max_units("material")
    media = [{"id": "MED-01", "for_modules": ["MOD-01"]}, {"id": "MED-02", "for_modules": ["MOD-01"]}]

    def one(expected):
        module = {"id": "MOD-01"}
        if expected is not None:
            module["expected_materials"] = expected
        return dp.material_work_units([module], media, [])[0]

    assert one(None).payload["expected_materials"] == 2
    assert one(4).payload["expected_materials"] == 4
    assert one(1).payload["expected_materials"] == 2, "never below one per media selection"
    assert one("many").payload["expected_materials"] == 2
    assert one(limit + 5).payload["expected_materials"] == limit

    assert "write exactly 4 materials" in dp.render_material_set(one(4))
    assert "at least one" in dp.render_material_set(one(4))
    assert "write exactly 2 materials — one realizing each" in dp.render_material_set(one(None))
    # A module with no media still gets a count, and the planner's still counts.
    bare = dp.material_work_units([{"id": "MOD-02", "expected_materials": 3}], [], [])[0]
    assert bare.payload["expected_materials"] == 3
    assert "write exactly 3 materials for this module" in dp.render_material_set(bare)


# ── the activity plan is bounded by the time the planner says the course has ─

def _blocks(counts, minutes=None):
    return [{"set_id": f"B{i}", "objectives": [f"ILO-0{i % 5 + 1}"], "block_theme": f"theme {i}",
             "expected_activities": count,
             **({"block_minutes": minutes[i]} if minutes else {})}
            for i, count in enumerate(counts)]


def _planned(sets):
    return sum(ws.payload["expected_activities"] for ws in sets)


def _one_module(minutes, los):
    return [{"id": "MOD-01", "title": "All of it", "objectives": list(los), "minutes": minutes}]


def test_a_counting_sequence_is_cut_to_the_time_its_module_has():
    """MEASURED (run 1c0a4e81): the planner wrote `expected_activities` as a
    running number — 2, 3, 4 … across 33 blocks — and the per-block clamp let
    94 activities through for 5 objectives: a third of the run's calls, and 88
    activities downstream that no content supported. What bounds an activity
    plan is the learner time its MODULE has, which the Outcome Designer states;
    the harness holds the plan to it and says how much it cut."""
    from alignmentgraph_isd.core import dev_plans

    los = [f"ILO-0{i}" for i in range(1, 6)]
    plan = {"activity_blocks": _blocks(list(range(2, 35)))}
    sets, stats = dev_plans.activity_work_sets(
        plan, los, modules=_one_module(600, los))

    ceiling = max(len(sets), 600 // dev_plans.MIN_ACTIVITY_MINUTES)
    assert _planned(sets) <= ceiling
    assert stats["time_budget"]["module_minutes"] == 600
    assert stats["planned_activities"] > ceiling, "what the planner asked for is on the record"
    assert stats["time_budget"]["trimmed"] >= stats["planned_activities"] - ceiling > 0
    assert {lo for ws in sets for lo in ws.objectives} == set(los), "every objective keeps a block"
    assert {ws.module_id for ws in sets} == {"MOD-01"}


def test_a_block_plans_no_more_than_fits_in_its_own_minutes():
    from alignmentgraph_isd.core import dev_plans

    plan = {"activity_blocks": _blocks([8, 8], minutes=[45, 240])}
    sets, _stats = dev_plans.activity_work_sets(
        plan, ["ILO-01", "ILO-02"], modules=_one_module(285, ["ILO-01", "ILO-02"]))
    by_theme = {ws.payload["block_theme"]: ws.payload["expected_activities"] for ws in sets}
    assert by_theme["theme 0"] == 45 // dev_plans.MIN_ACTIVITY_MINUTES
    assert by_theme["theme 1"] == 8, "a block that fits is left as the planner wrote it"


def test_the_blocks_of_a_module_share_all_of_its_time_not_just_what_they_declared():
    """MEASURED (run 40856c96): each module's only block declared 15 of its
    module's 100-120 minutes, the block was held to one activity, and a
    three-module course shipped three activities. Block minutes are
    PROPORTIONS of the module's time, scaled up as well as down."""
    from alignmentgraph_isd.core import dev_plans

    plan = {"activity_blocks": _blocks([6], minutes=[15])}
    sets, _stats = dev_plans.activity_work_sets(
        plan, ["ILO-01"], modules=_one_module(120, ["ILO-01"]))
    assert sets[0].payload["block_minutes"] == 120
    assert sets[0].payload["expected_activities"] == 6

    sampled, _stats = dev_plans.activity_work_sets(
        plan, ["ILO-01"], modules=_one_module(120, ["ILO-01"]), mode="sample")
    assert sampled[0].payload["expected_activities"] == dev_plans.SAMPLE_ACTIVITIES_PER_MODULE_FLOOR


def test_a_set_that_writes_fewer_than_it_was_asked_for_is_not_finished():
    """MEASURED (run 40856c96): three sets told "write exactly 3 items" each
    submitted one and were answered COMMITTED."""
    from alignmentgraph_isd.core import dev_plans

    ws = dev_plans.WorkSet(set_id="AS-01", payload={"expected_items": 3})
    owed = dev_plans.short_of_quota(ws, "assessment_tools", [{}])
    assert owed.startswith("KEPT: 1 of the 3") and "ONLY 2 more" in owed
    assert dev_plans.short_of_quota(ws, "assessment_tools", [{}, {}, {}]) == ""
    guides = dev_plans.WorkSet(set_id="SB-01", payload={"expected_sessions": 2})
    assert dev_plans.short_of_quota(guides, "session_guides", [{}]) == "", (
        "how many sessions a block takes is the writer's to say; what it owes is every id")


def test_a_module_that_states_no_time_is_left_alone_and_the_record_says_so():
    """The harness holds a plan to the DESIGN's number, never to one it made
    up: the brief states duration as a band, not as hours."""
    from alignmentgraph_isd.core import dev_plans

    sets, stats = dev_plans.activity_work_sets(
        {"activity_blocks": _blocks([4, 4])}, ["ILO-01", "ILO-02"],
        modules=_one_module(None, ["ILO-01", "ILO-02"]))
    assert _planned(sets) == 8
    assert stats["time_budget"]["unbudgeted_sets"] == len(sets)


def test_a_block_never_spans_two_modules_and_the_sets_come_out_in_course_order():
    """The module is the key every family divides by. A block the planner drew
    across a module boundary is cut there, its count divided between the pieces
    rather than repeated; an objective two modules serve is practised in both;
    and one no module serves is written with the course's last module."""
    from alignmentgraph_isd.core import dev_plans

    modules = [{"id": "MOD-01", "title": "Basics", "objectives": ["ILO-01", "ILO-02"], "minutes": 120},
               {"id": "MOD-02", "title": "Practice", "objectives": ["ILO-02", "ILO-03"], "minutes": 240}]
    plan = {"activity_blocks": [
        {"set_id": "B1", "objectives": ["ILO-03", "ILO-01"], "block_theme": "across",
         "block_minutes": 120, "expected_activities": 4}]}
    sets, stats = dev_plans.activity_work_sets(
        plan, ["ILO-01", "ILO-02", "ILO-03", "ILO-04"], modules=modules)

    assert [ws.module_id for ws in sets] == sorted(ws.module_id for ws in sets)
    by_module = {m: [ws for ws in sets if ws.module_id == m] for m in ("MOD-01", "MOD-02")}
    assert {lo for ws in by_module["MOD-01"] for lo in ws.objectives} == {"ILO-01", "ILO-02"}
    assert {lo for ws in by_module["MOD-02"] for lo in ws.objectives} == {"ILO-02", "ILO-03", "ILO-04"}
    across = [ws for ws in sets if ws.payload.get("block_theme") == "across"]
    assert sorted(ws.objectives for ws in across) == [("ILO-01",), ("ILO-03",)]
    assert sum(ws.payload["expected_activities"] for ws in across) == 4, "divided, not repeated"
    assert all(ws.as_dict()["module_id"] == ws.module_id for ws in sets)
    assert stats["set_count"] == len(sets)


def test_assessment_sets_follow_the_sets_module_by_module():
    from alignmentgraph_isd.core import dev_plans

    modules = [{"id": "MOD-01", "objectives": ["ILO-01"], "minutes": 60},
               {"id": "MOD-02", "objectives": ["ILO-01", "ILO-02"], "minutes": 60}]
    sets = [
        {"id": "SET-01", "module_id": "MOD-01", "timing": "formative", "format": "quiz",
         "item_counts": {"multiple_choice": 10}, "covers_objectives": ["ILO-01"]},
        {"id": "SET-02", "module_id": "MOD-02", "timing": "summative", "format": "practical",
         "item_counts": {"performance_task": 2}, "covers_objectives": ["ILO-01", "ILO-02"]}]
    targets = {"ILO-01": ["formative", "summative"], "ILO-02": ["summative"]}
    sets, _stats = dev_plans.assessment_work_sets(
        None, ["ILO-01", "ILO-02"], targets, modules=modules, blueprint=sets,
        mode="sample")

    assert [(ws.module_id, ws.pairs) for ws in sets] == [
        ("MOD-01", (("ILO-01", "formative"),)),
        ("MOD-02", (("ILO-01", "summative"), ("ILO-02", "summative")))]
    assert [i["id"] for i in sets[1].payload["sets"]] == ["SET-02"]
    text = dev_plans.render_assessment_set(sets[1])
    assert "module: MOD-02" in text and "SET-02: summative practical" in text
    assert "full scale: 2 performance_task" in text


def test_a_session_block_is_delivered_inside_one_module():
    from alignmentgraph_isd.core import dev_plans

    modules = [{"id": "MOD-01", "objectives": ["ILO-01"], "minutes": 60},
               {"id": "MOD-02", "objectives": ["ILO-02"], "minutes": 60}]
    module_of = {"TLA-0101": "MOD-01", "TLA-0201": "MOD-02", "MAT-0101": "module:MOD-01"}
    plan = {"session_blocks": [{"set_id": "SB", "expected_sessions": 3,
                                "activity_ids": ["TLA-0201", "TLA-0101"], "material_ids": []}]}
    sets, _stats = dev_plans.session_work_sets(
        plan, ["TLA-0101", "TLA-0201", "TLA-0301"], ["MAT-0101"],
        modules=modules, module_of=module_of)

    assert [ws.module_id for ws in sets] == sorted(ws.module_id for ws in sets)
    scheduled = [a for ws in sets for a in ws.payload["activity_ids"] + ws.payload["material_ids"]]
    assert sorted(scheduled) == ["MAT-0101", "TLA-0101", "TLA-0201", "TLA-0301"], "each exactly once"
    first = next(ws for ws in sets if "TLA-0101" in ws.payload["activity_ids"])
    assert first.module_id == "MOD-01"
    orphan = next(ws for ws in sets if "TLA-0301" in ws.payload["activity_ids"])
    assert orphan.module_id == "MOD-02", "an activity naming no module goes with the last one"


def test_the_written_activities_are_checked_against_their_module_s_minutes():
    from alignmentgraph_isd.core import checks, repairs
    from alignmentgraph_isd.core.alignment_graph import AlignmentGraph, NodeType

    assert checks.duration_minutes("1.5 hours") == 90
    assert checks.duration_minutes("2 h 30 min") == 150
    assert checks.duration_minutes("a while") == 0

    graph = AlignmentGraph()
    graph.add_element_node(NodeType.MODULE, "MOD-01", {"id": "MOD-01", "minutes": 120})
    graph.add_element_node(NodeType.MODULE, "MOD-02", {"id": "MOD-02", "minutes": 120})
    for i in range(3):
        graph.add_element_node(NodeType.ACTIVITY, f"TLA-0{i}", {
            "id": f"TLA-0{i}", "duration": "60 minutes", "module_id": "MOD-01"})
    found = checks.time_budget(graph)
    assert [(v.violation_type, v.node_id) for v in found] == [("time_budget", "module:MOD-01")]
    assert "180 minutes" in found[0].message and "120 minutes" in found[0].message
    assert "time_budget" in repairs.REPORT_ONLY, "which activity to cut is a design judgment"
    assert repairs.OWNER_BY_VIOLATION["time_budget"] == "activity_designer"

    graph.update_node("module:MOD-01", {"minutes": 180})
    assert checks.time_budget(graph) == []


def test_a_work_set_written_one_item_at_a_time_accumulates_and_a_repeat_adds_nothing():
    """MEASURED (run ae81359a): with a short submit REFUSED, a 2B model that
    writes one item per call resent its one item — 14 such refusals, sets
    giving up after four calls and regenerated up to three times. An
    instalment is kept and joined to the next; a repeat is not an instalment."""
    from alignmentgraph_isd.core import dev_plans
    from alignmentgraph_isd.core.agentic import fanout, turn as turn_mod
    from alignmentgraph_isd.core.agentic.specialists import STEPS

    def item(question, lo="ILO-01"):
        return {"question": question, "aligned_objective": lo, "plan_category": "formative",
                "task_id": "AT-01"}

    work_set = dev_plans.WorkSet(set_id="AS-01", pairs=(("ILO-01", "formative"),),
                                 payload={"expected_items": 3})
    step = fanout.set_step(fanout.SPECS["assessment"], work_set,
                           next(s for s in STEPS if s.name == "assessment"))
    kept: dict = {}

    first = {"assessment_tools": [item("Which tool fits?"), item("which  tool FITS?")]}
    assert step.validate(first) == [], "a short submit is valid — it is an instalment"
    assert step.owes(first).startswith("KEPT: 1 of the 3"), "the repeat inside it does not count"
    assert turn_mod.keep_items(kept, first) == 1

    again, _ = turn_mod.carry_over(kept, {"assessment_tools": [item("Which tool fits?")]})
    assert len(again["assessment_tools"]) == 1 and turn_mod.keep_items(kept, again) == 0, (
        "resending what is kept gains nothing, which is the one thing the loop charges")

    more, carried = turn_mod.carry_over(kept, {"assessment_tools": [
        item("Justify the choice."), item("Which tool fits?", lo="ILO-02")]})
    assert carried == ["assessment_tools[:1]"]
    assert [i["question"] for i in more["assessment_tools"]] == [
        "Which tool fits?", "Justify the choice.", "Which tool fits?"], (
        "the same words asked of another objective are another item")
    assert step.owes(more) == ""


def test_an_objective_two_modules_serve_is_practised_in_both():
    """Only a second block of the SAME module writes the same activities
    twice. Keyed on the objective alone the second MODULE lost its block
    whole and ended with no activity at all (P13), its objectives
    unpractised (C3) — which is what a derived plan produces every time an
    objective is shared, because a block is a module now."""
    across = {"activity_blocks": [{"module_id": "MOD-01", "objectives": ["ILO-01"]},
                                  {"module_id": "MOD-02", "objectives": ["ILO-01"]}]}
    sets, stats = dp.activity_work_sets(across, ["ILO-01"])
    assert len(sets) == 2 and stats["duplicate_pairs"] == 0

    twice = {"activity_blocks": [{"module_id": "MOD-01", "objectives": ["ILO-01"]}] * 2}
    sets, stats = dp.activity_work_sets(twice, ["ILO-01"])
    assert len(sets) == 1 and stats["duplicate_pairs"] == 1

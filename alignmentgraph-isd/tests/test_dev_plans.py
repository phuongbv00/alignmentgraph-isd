"""core/dev_plans.py: dev-plan normalization is pure, deterministic, and
never lets a fan-out shape depend on unvalidated LLM output — every ground
truth obligation must survive into exactly one WorkSet regardless of what
(if anything) the LLM proposed."""
from __future__ import annotations

from alignmentgraph_isd.core import dev_plans as dp


# ── assessment ───────────────────────────────────────────────────────────

def test_assessment_llm_plan_covers_everything_kept_verbatim():
    targets = {"ILO-01": ["formative"], "ILO-02": ["formative"]}
    parsed = {"instrument_sets": [
        {"set_id": "X", "objectives": ["ILO-01", "ILO-02"], "plan_categories": ["formative"],
         "instrument_hint": "integrated case", "rationale": "shared scenario"},
    ]}
    sets, stats = dp.normalize_assessment_dev_plan(parsed, ["ILO-01", "ILO-02"], targets)
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
    parsed = {"instrument_sets": [
        {"objectives": ["ILO-01"], "plan_categories": ["formative", "summative", "diagnostic"]},
    ]}
    sets, stats = dp.normalize_assessment_dev_plan(parsed, ["ILO-01"], targets)
    all_pairs = {p for ws in sets for p in ws.pairs}
    assert all_pairs == {("ILO-01", "formative")}
    assert stats["dropped_pairs"] == 2


def test_assessment_unknown_objective_dropped():
    targets = {"ILO-01": ["formative"]}
    parsed = {"instrument_sets": [{"objectives": ["ILO-99"], "plan_categories": ["formative"]}]}
    sets, stats = dp.normalize_assessment_dev_plan(parsed, ["ILO-01"], targets)
    assert stats["dropped_lo_refs"] == 1
    # ILO-99's set contributes nothing real; ILO-01/formative still gets a
    # set via the uncovered-pair top-up.
    assert {p for ws in sets for p in ws.pairs} == {("ILO-01", "formative")}
    assert stats["fallback_used"] is True  # zero valid LLM sets survived


def test_assessment_uncovered_pair_appended_not_fallback():
    targets = {"ILO-01": ["formative"], "ILO-02": ["summative"]}
    parsed = {"instrument_sets": [{"objectives": ["ILO-01"], "plan_categories": ["formative"]}]}
    sets, stats = dp.normalize_assessment_dev_plan(parsed, ["ILO-01", "ILO-02"], targets)
    assert stats["fallback_used"] is False
    assert stats["appended_sets"] == 1
    sources = {ws.source for ws in sets}
    assert "llm" in sources and "appended" in sources


def test_assessment_empty_or_garbage_plan_is_pure_fallback():
    targets = {"ILO-01": ["formative"], "ILO-02": ["summative"]}
    for parsed in ({}, None, {"instrument_sets": "not a list"}, {"instrument_sets": []}):
        sets, stats = dp.normalize_assessment_dev_plan(parsed, ["ILO-01", "ILO-02"], targets)
        assert stats["fallback_used"] is True
        assert {p for ws in sets for p in ws.pairs} == {("ILO-01", "formative"), ("ILO-02", "summative")}
        assert all(ws.source == "fallback" for ws in sets)


def test_assessment_empty_targets_defaults_to_lo_x_summative():
    sets, stats = dp.normalize_assessment_dev_plan({}, ["ILO-01", "ILO-02"], {})
    assert {p for ws in sets for p in ws.pairs} == {("ILO-01", "summative"), ("ILO-02", "summative")}
    assert stats["pair_count"] == 2


def test_assessment_no_objectives_at_all_returns_no_sets():
    sets, stats = dp.normalize_assessment_dev_plan({}, [], {})
    assert sets == []
    assert stats["pair_count"] == 0


def test_assessment_namespaced_ids_are_normalized():
    targets = {"objective:ILO-01": ["formative"]}
    parsed = {"instrument_sets": [{"objectives": ["objective:ILO-01"], "plan_categories": ["formative"]}]}
    sets, stats = dp.normalize_assessment_dev_plan(parsed, ["ILO-01"], targets)
    assert {p for ws in sets for p in ws.pairs} == {("ILO-01", "formative")}
    assert stats["dropped_pairs"] == 0


def test_assessment_overflow_capped_and_merged_never_drops_a_pair():
    lo_ids = [f"ILO-{i:02d}" for i in range(1, 6)]  # 5 pairs -> cap = min(10, 24) = 10
    targets = {lo: ["summative"] for lo in lo_ids}
    # 20 singleton LLM sets, one per pair repeated 4x with junk duplicates collapsed by pair dedup
    parsed = {"instrument_sets": [
        {"objectives": [lo_ids[i % 5]], "plan_categories": ["summative"]} for i in range(20)
    ]}
    sets, stats = dp.normalize_assessment_dev_plan(parsed, lo_ids, targets)
    assert len(sets) <= 10
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
    sets, stats = dp.normalize_activity_dev_plan(parsed, ["ILO-01", "ILO-02"], items_by_lo)
    assert len(sets) == 1
    assert sets[0].objectives == ("ILO-01", "ILO-02")
    assert sets[0].payload["assessment_items"] == ["AT-01", "AT-02"]
    assert stats["fallback_used"] is False


def test_activity_fallback_when_plan_missing():
    sets, stats = dp.normalize_activity_dev_plan(None, ["ILO-01"], {})
    assert stats["fallback_used"] is True
    assert len(sets) == 1
    assert sets[0].objectives == ("ILO-01",)


def test_activity_uncovered_lo_appended():
    parsed = {"activity_blocks": [{"objectives": ["ILO-01"]}]}
    sets, stats = dp.normalize_activity_dev_plan(parsed, ["ILO-01", "ILO-02"], {})
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


def test_material_units_overflow_merged():
    modules = [{"id": f"MOD-{i:02d}"} for i in range(1, 20)]
    sets = dp.material_work_units(modules, [], [])
    assert len(sets) <= dp.MAX_MATERIAL_UNITS
    all_modules = [m["id"] for ws in sets for m in ws.payload["modules"]]
    assert set(all_modules) == {m["id"] for m in modules}


# ── rubric (deterministic) ───────────────────────────────────────────────

def test_rubric_units_one_per_item():
    items = [{"item_id": "AT-01"}, {"item_id": "AT-02"}]
    sets = dp.rubric_work_units(items)
    assert [ws.set_id for ws in sets] == ["RB-AT-01", "RB-AT-02"]
    assert sets[0].payload["items"] == [items[0]]


def test_rubric_units_overflow_merged_never_drops_an_item():
    items = [{"item_id": f"AT-{i:02d}"} for i in range(1, 40)]
    sets = dp.rubric_work_units(items)
    assert len(sets) <= dp.MAX_RUBRIC_UNITS
    all_items = [it["item_id"] for ws in sets for it in ws.payload["items"]]
    assert set(all_items) == {it["item_id"] for it in items}


# ── fan-in helpers ───────────────────────────────────────────────────────

def test_pending_set_ids_flags_sets_with_no_items():
    sets = [dp.WorkSet(set_id="AS-01"), dp.WorkSet(set_id="AS-02")]
    payloads = [{"set_id": "AS-01", "items": [{"item_id": "AT-01"}]},
                {"set_id": "AS-02", "items": []}]
    assert dp.pending_set_ids(sets, payloads) == ["AS-02"]


def test_pending_set_ids_missing_payload_counts_as_pending():
    sets = [dp.WorkSet(set_id="AS-01")]
    assert dp.pending_set_ids(sets, []) == ["AS-01"]


def test_remap_and_tag_collision_across_sets_renamed_not_dropped():
    sets = [dp.WorkSet(set_id="AS-01"), dp.WorkSet(set_id="AS-02")]
    payloads = [
        {"set_id": "AS-01", "items": [{"item_id": "AT-01", "question": "q1"}]},
        {"set_id": "AS-02", "items": [{"item_id": "AT-01", "question": "q2"}]},
    ]
    merged = dp.remap_and_tag(sets, payloads, id_field="item_id")
    ids = [i["item_id"] for i in merged]
    assert ids == ["AT-01", "AT-01-AS-02"]
    assert [i["plan_set"] for i in merged] == ["AS-01", "AS-02"]


def test_remap_and_tag_ref_fields_follow_the_rename():
    sets = [dp.WorkSet(set_id="AS-01"), dp.WorkSet(set_id="AB-02")]
    payloads = [
        {"set_id": "AS-01", "items": [{"id": "TLA-01", "prerequisite_activities": []}]},
        {"set_id": "AB-02", "items": [
            {"id": "TLA-01", "prerequisite_activities": ["TLA-01"]},  # self-ref within its own set
        ]},
    ]
    merged = dp.remap_and_tag(sets, payloads, id_field="id", ref_fields=("prerequisite_activities",))
    by_set = {i["plan_set"]: i for i in merged}
    assert by_set["AS-01"]["id"] == "TLA-01"
    assert by_set["AB-02"]["id"] == "TLA-01-AB-02"
    assert by_set["AB-02"]["prerequisite_activities"] == ["TLA-01-AB-02"]


def test_remap_and_tag_missing_id_field_kept_untouched():
    sets = [dp.WorkSet(set_id="AS-01")]
    payloads = [{"set_id": "AS-01", "items": [{"question": "no id here"}]}]
    merged = dp.remap_and_tag(sets, payloads, id_field="item_id")
    assert merged == [{"question": "no id here", "plan_set": "AS-01"}]


def test_remap_and_tag_order_follows_dev_plan_order_not_payload_order():
    sets = [dp.WorkSet(set_id="AS-01"), dp.WorkSet(set_id="AS-02")]
    payloads = [
        {"set_id": "AS-02", "items": [{"item_id": "AT-02"}]},
        {"set_id": "AS-01", "items": [{"item_id": "AT-01"}]},
    ]
    merged = dp.remap_and_tag(sets, payloads, id_field="item_id")
    assert [i["item_id"] for i in merged] == ["AT-01", "AT-02"]


# ── round-trip ───────────────────────────────────────────────────────────

def test_work_set_dict_round_trip():
    ws = dp.WorkSet(set_id="AS-01", objectives=("ILO-01",), pairs=(("ILO-01", "formative"),),
                     payload={"a": 1}, source="llm")
    back = dp.work_set_from_dict(ws.as_dict())
    assert back == ws

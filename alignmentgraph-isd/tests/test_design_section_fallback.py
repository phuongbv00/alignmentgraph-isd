"""``design.storyboard`` is no longer written by a Designer at all — it is
computed deterministically by ``ADDIEOutputAggregator`` from the committed
instructional_strategies sequence (one frame per Gagné event), falling back
to one frame per content module when the sequence is unusable. This is the
direct descendant of a retired per-Designer fallback (small-model robustness
against a dropped storyboard section), now the PRIMARY path rather than a
fallback — see ``ADDIEOutputAggregator``'s own docstring.

(``non_instructional_strategies`` has no such deterministic path: the
`activities` stage produces it in the same call as instructional_strategies,
and if the model drops it nothing writes one — by design, since a harness-
written stand-in would satisfy its own check by existing.)
"""
from __future__ import annotations

from alignmentgraph_isd import HarnessRunConfig
from alignmentgraph_isd.core.aggregate import _compute_storyboard

from conftest import FakeChatModel, _ACTIVITY_PLAN, load_brief, run_brief


# ── unit: deterministic synthesis helper ─────────────────────────────────────

def test_compute_storyboard_from_gagne_sequence():
    strategies = _ACTIVITY_PLAN["instructional_strategies"]
    frames = _compute_storyboard(strategies, content_modules=[])
    # One frame per Gagné event, sequentially numbered, grounded in the activity.
    assert len(frames) == len(strategies["sequence"])
    assert [f["frame_number"] for f in frames] == list(range(1, len(frames) + 1))
    assert frames[0]["screen_title"] == "Gain attention"
    assert all(f["visual_description"] for f in frames)


def test_compute_storyboard_falls_back_to_modules_when_sequence_unusable():
    modules = [{"id": "MOD-01", "title": "Concepts"}, {"id": "MOD-02", "title": "Inheritance"}]
    frames = _compute_storyboard({}, content_modules=modules)
    assert [f["screen_title"] for f in frames] == ["Concepts", "Inheritance"]


def test_compute_storyboard_empty_when_no_source():
    assert _compute_storyboard({}, content_modules=[]) == []


# ── integration: storyboard is always present when the sequence parsed ──────

def test_storyboard_present_end_to_end_without_a_dedicated_llm_call():
    config = HarnessRunConfig()
    config.llm_factory = lambda: FakeChatModel()
    result = run_brief(load_brief("minimal_brief.json"), config)

    design = result["addie_output"]["design"]
    assert design["storyboard"], "storyboard must be computed, not empty"
    assert design["storyboard"][0]["screen_title"] == "Gain attention"

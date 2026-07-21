"""When the (small-model) Design "rest" call drops the storyboard or the
non-instructional strategies, the specialist synthesizes them deterministically
from content already generated in the same call, instead of shipping an empty
section that scores the D3/D2 rubric items 0/ABSENT at the judge.

Reproduces the observed 2B failure mode where instructional_strategies parses
fine but storyboard/non_instructional_strategies come back empty.
"""
from __future__ import annotations

import json

from alignmentgraph_isd import HarnessRunConfig, run_design_brief
from alignmentgraph_isd.core.agents.objective_design import ObjectiveDesignAgent

from conftest import FakeChatModel, _DESIGN, load_brief


# ── unit: deterministic synthesis helpers ────────────────────────────────────

def test_fallback_storyboard_from_gagne_sequence():
    frames = ObjectiveDesignAgent._fallback_storyboard(_DESIGN)
    # One frame per Gagné event, sequentially numbered, grounded in the activity.
    assert len(frames) == len(_DESIGN["instructional_strategies"]["sequence"])
    assert [f["frame_number"] for f in frames] == list(range(1, len(frames) + 1))
    assert frames[0]["screen_title"] == "Gain attention"
    assert all(f["visual_description"] for f in frames)


def test_fallback_storyboard_falls_back_to_modules():
    parsed = {"content_structure": {"modules": ["Concepts", "Inheritance", "Design"]}}
    frames = ObjectiveDesignAgent._fallback_storyboard(parsed)
    assert [f["screen_title"] for f in frames] == ["Concepts", "Inheritance", "Design"]


def test_fallback_storyboard_empty_when_no_source():
    assert ObjectiveDesignAgent._fallback_storyboard({}) == []


def test_fallback_non_instructional_is_grounded_and_complete():
    brief = load_brief("java_oop_brief.json")
    ni = ObjectiveDesignAgent._fallback_non_instructional(brief)
    assert set(ni) == {"motivation_strategies", "self_directed_learning", "support_strategies"}
    assert all(isinstance(v, list) and v for v in ni.values())
    # Scenario-grounded, not boilerplate: the domain appears in the copy.
    assert brief.domain.lower() in " ".join(ni["motivation_strategies"]).lower()


# ── integration: dropped sections are recovered end-to-end ────────────────────

class _DesignMissingSubsections(FakeChatModel):
    """Returns the Design rest payload WITHOUT storyboard / non_instructional
    (instructional_strategies still present) — the real 2B partial-parse case."""

    def invoke(self, messages):
        system = ""
        for message in messages:
            if isinstance(message, dict) and message.get("role") == "system":
                system = message.get("content", "")
                break
        if "remaining Design section" in system:
            from conftest import _Result

            payload = {k: v for k, v in _DESIGN.items()
                       if k not in ("storyboard", "non_instructional_strategies")}
            return _Result(json.dumps(payload, ensure_ascii=False))
        return super().invoke(messages)


def test_dropped_design_subsections_recovered_without_extra_llm_call():
    config = HarnessRunConfig()
    config.llm_factory = _DesignMissingSubsections
    result = run_design_brief(load_brief("minimal_brief.json"), config)

    design = result["addie_output"]["design"]
    assert design["storyboard"], "storyboard must be synthesized, not empty"
    assert design["non_instructional_strategies"], "non-instructional strategies must be synthesized"
    # The synthesized storyboard reflects the instructional sequence that DID parse.
    assert design["storyboard"][0]["screen_title"] == "Gain attention"
    assert set(design["non_instructional_strategies"]) == {
        "motivation_strategies", "self_directed_learning", "support_strategies",
    }

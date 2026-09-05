"""Milestone 1 smoke: the public API runs end-to-end on a fake LLM."""
from __future__ import annotations

import pytest

from alignmentgraph_isd import HarnessRunConfig

from conftest import load_brief, run_brief

ALL_BRIEFS = ["minimal_brief.json", "java_oop_brief.json", "software_testing_brief.json"]


@pytest.mark.parametrize("brief_name", ALL_BRIEFS)
def test_public_api_returns_contract(brief_name, fake_config):
    brief = load_brief(brief_name)
    result = run_brief(brief, fake_config)

    assert set(result) >= {"addie_output", "trajectory", "metadata"}
    addie = result["addie_output"]
    assert set(addie) == {"analysis", "design", "development", "implementation", "evaluation"}
    assert addie["design"]["learning_objectives"], "expected learning objectives"
    assert addie["development"]["assessment_tools"], "expected assessment tools"


def test_run_requires_llm_factory():
    brief = load_brief("minimal_brief.json")
    config = HarnessRunConfig()
    with pytest.raises(RuntimeError, match="llm_factory"):
        run_brief(brief, config)


def test_no_hardcoded_vr_mobile_language(fake_config):
    brief = load_brief("minimal_brief.json")
    result = run_brief(brief, fake_config)
    blob = repr(result["addie_output"]).lower()
    for banned in ("vr headset", "mobile app", "language practice", "collaborative language"):
        assert banned not in blob, f"unexpected hard-coded domain artifact: {banned}"

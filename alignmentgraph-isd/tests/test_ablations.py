"""Each ablation preset still produces a stable ADDIE/trajectory/metadata contract."""
from __future__ import annotations

import pytest

from alignmentgraph_isd import HarnessRunConfig, run_design_brief

from conftest import FakeChatModel, load_brief

ABLATIONS = ["full", "no_verifier", "no_repair", "single_agent", "linear_addie_only", "case_study"]


@pytest.mark.parametrize("ablation", ABLATIONS)
def test_ablation_produces_contract(ablation):
    config = HarnessRunConfig.from_ablation(ablation, memory={"enabled": False})
    config.llm_factory = lambda: FakeChatModel()
    result = run_design_brief(load_brief("minimal_brief.json"), config)

    assert set(result) >= {"addie_output", "trajectory", "metadata"}
    addie = result["addie_output"]
    assert set(addie) == {"analysis", "design", "development", "implementation", "evaluation"}
    assert addie["design"]["learning_objectives"]
    assert result["metadata"]["ablation"]["use_verifier"] in (True, False)

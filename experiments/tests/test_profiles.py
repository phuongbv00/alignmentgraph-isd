"""What each launch profile actually launches.

The design the roadmap fixed is a set of facts about these profiles -- which
split, how many rungs, how many runs per cell, which roster. Asserting them
here is cheap, and it is the difference between a launcher that is configured
correctly and one that merely runs.

The hazard this replaces: the launcher sourced `.env` and let it override the
experiment's own identity, so a `DATASET=train_30` left behind by a tuning
session would silently run an official experiment on the tuning split with the
wrong agent list, and nothing would say so except a banner nobody re-reads.
With the profile authoritative, that cannot happen -- these tests pin it.
"""

from __future__ import annotations

import shutil
import subprocess

import pytest

from isd_experiments import paths
from isd_experiments.config import current
from isd_experiments.launch import INFORMAL, profile_env


@pytest.fixture(scope="module")
def envs():
    return {name: profile_env(current().profile(name))
            for name in ("comparison", "ablation", "tune", "canary")}


class TestOfficialExperiments:
    def test_comparison_runs_the_whole_ladder_on_the_reporting_split(self, envs):
        e = envs["comparison"]
        assert e["DATASET"] == "test_90"
        assert len(e["_SLOTS_LIST"].split()) == 4
        assert len(e["_RUN_TAGS_LIST"].split()) == 1, "one deterministic run per cell"
        assert "alignmentgraph-isd" in e["AGENTS"].split(",")

    def test_ablation_runs_four_arms_at_both_ends(self, envs):
        e = envs["ablation"]
        assert e["DATASET"] == "test_30"
        assert len(e["_SLOTS_LIST"].split()) == 2
        assert len(e["AGENTS"].split(",")) == 4

    def test_both_ask_before_spending_and_record_a_manifest(self, envs):
        for name in ("comparison", "ablation"):
            assert envs[name]["CONFIRM"] == "1", f"{name} must confirm before launching"
            assert envs[name]["MANIFEST"] == "1", f"{name} must record what it ran"

    def test_tag_namespaces_do_not_overlap(self, envs):
        """Pools are globbed by tag; a shared namespace would let one
        experiment's runs drift into the other's pool."""
        a = set(envs["comparison"]["_RUN_TAGS_LIST"].split())
        b = set(envs["ablation"]["_RUN_TAGS_LIST"].split())
        assert not a & b


class TestInformalRuns:
    def test_tune_and_canary_neither_confirm_nor_record(self, envs):
        """Their results never enter the paper, so a manifest would assert a
        provenance that means nothing -- and a cost prompt on a 3-scenario
        canary is friction without a purpose."""
        for name in INFORMAL:
            assert envs[name]["CONFIRM"] == "0"
            assert envs[name]["MANIFEST"] == "0"

    def test_they_run_on_the_training_split(self, envs):
        for name in INFORMAL:
            assert envs[name]["DATASET"] == "train_30"

    def test_canary_is_small_and_judge_free(self):
        p = current().profile("canary")
        assert p.judge is False
        assert p.scenario_limit == 3
        assert len(p.rungs) == 1


class TestLadderIsConfiguration:
    def test_slot_env_quads_are_exported_from_the_declaration(self, envs):
        """The launcher carried four hard-coded blocks naming one model family;
        a different ladder meant editing shell."""
        e = envs["comparison"]
        for slot in e["_SLOTS_LIST"].split():
            prefix = slot.upper()
            assert e[f"{prefix}_AGENT_MODEL_NAME"]
            assert e[f"{prefix}_AGENT_MODEL_API_KEY_ENVS"]

    def test_a_foreign_ladder_produces_a_valid_launch_plan(self, tmp_path):
        cfg = tmp_path / "experiment.toml"
        cfg.write_text((paths.exp_root() / "tests" / "fixtures" / "two_rung.toml")
                       .read_text(encoding="utf-8"), encoding="utf-8")
        import os
        env = dict(os.environ, ISD_EXPERIMENT_CONFIG=str(cfg))
        out = subprocess.run(
            [str(paths.exp_root() / ".venv" / "bin" / "python"),
             "-m", "isd_experiments.cli", "comparison", "run", "--dry-run"],
            capture_output=True, text=True, env=env, cwd=str(paths.exp_root()))
        assert out.returncode == 0, out.stderr
        assert "tiny big" in out.stdout
        assert "nothing launched" in out.stdout


class TestShellIsValid:
    @pytest.mark.skipif(shutil.which("bash") is None, reason="bash not available")
    @pytest.mark.parametrize("script", ["_matrix.sh", "launch.sh"])
    def test_launcher_parses(self, script):
        path = paths.exp_root() / "bin" / script
        assert subprocess.run(["bash", "-n", str(path)]).returncode == 0

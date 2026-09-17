"""experiment.toml is the whole configuration surface.

The point of these tests is that a *different* study -- another ladder, another
serving host, another set of arms -- is a config edit and nothing else. Each
test below would have required a code change under the arrangement this
replaces, where the ladder was four hard-coded shell variables, the sizes a
literal dict in four generators, and the host a REST base URL in a script.
"""

from __future__ import annotations

import textwrap

import pytest

from isd_experiments import config

TWO_RUNG = """
[models]
family = ""

[serving]
provider = "static"
api_spec = "openai_compatible"
key_env = "MY_KEY"

[[ladder]]
slot = "tiny"
model = "meta-llama/Llama-3.2-1B-Instruct"
params_b = 1.0
display = "1B"
base_url = "http://localhost:8000/v1"

[[ladder]]
slot = "big"
model = "google/gemma-2-27b-it"
params_b = 27.0
display = "27B"

[experiment.comparison]
dataset = "test_90"
rungs = "all"
tags = ["c1"]
agents = ["alignmentgraph-isd", "react-isd"]
proposed = "alignmentgraph-isd"
"""


def write(tmp_path, body: str):
    p = tmp_path / "experiment.toml"
    p.write_text(textwrap.dedent(body), encoding="utf-8")
    return p


class TestShippedConfig:
    """The config in the repo must describe the study the roadmap fixed."""

    def test_two_official_experiments_exist(self):
        e = config.load()
        assert "comparison" in e.profiles and "ablation" in e.profiles

    def test_comparison_is_the_ladder_on_the_large_split(self):
        p = config.load().profile("comparison")
        assert p.dataset == "test_90"
        assert p.proposed == "alignmentgraph-isd"
        assert p.proposed in p.agents
        assert len(p.agents) == 7, "the proposed system plus six benchmark agents"
        assert p.tags == ("c1",), "one deterministic run per cell"

    def test_ablation_is_a_full_two_by_two(self):
        p = config.load().profile("ablation")
        assert p.dataset == "test_30"
        assert len(p.rungs) == 2, "both ends of the deployment envelope"
        cells = {(a.agent_mode, a.context_mode) for a in p.arms}
        assert cells == {("multi", "graph"), ("multi", "prose"),
                         ("single", "graph"), ("single", "prose")}

    def test_reference_arm_leads_the_roster(self):
        """Every delta is taken against it; leading with it puts that in the
        banner and the manifest rather than in a reader's head."""
        p = config.load().profile("ablation")
        assert p.arms[0].id == p.reference

    def test_ablation_tags_cannot_collide_with_comparison(self):
        """The two pools are globbed by tag. A shared namespace would let one
        experiment's runs drift into the other's pool silently."""
        e = config.load()
        assert not set(e.profile("comparison").tags) & set(e.profile("ablation").tags)

    def test_canary_does_not_call_a_judge(self):
        """Its whole point is reading harness behaviour before spending money."""
        p = config.load().profile("canary")
        assert p.llm_judge is False and p.confirm is False

    def test_tune_is_on_the_training_split(self):
        """Tuning results never enter the paper, so they must never touch the
        splits the paper reports on."""
        e = config.load()
        assert e.profile("tune").dataset == "train_30"
        assert e.profile("tune").dataset != e.profile("comparison").dataset


class TestAnyLadder:
    """Not four rungs, not one family, not one vendor."""

    def test_two_rungs_of_a_different_family(self, tmp_path):
        e = config.load(write(tmp_path, TWO_RUNG))
        assert [r.slot for r in e.ladder] == ["tiny", "big"]
        assert e.profile("comparison").slots == ("tiny", "big")

    def test_macro_words_are_generated_not_tabulated(self, tmp_path):
        """A size the old hard-coded table never listed still gets a valid
        LaTeX macro name -- digits are illegal in one, so this cannot be the
        number itself."""
        e = config.load(write(tmp_path, TWO_RUNG))
        assert [r.macro for r in e.ladder] == ["OneB", "TwoSevenB"]
        assert all(not any(ch.isdigit() for ch in r.macro) for r in e.ladder)

    def test_shipped_macro_words_match_the_retired_hard_coded_table(self):
        """Generating these must not change any macro name in the manuscript."""
        assert config.load().macro_words == {
            0.8: "ZeroEightB", 2.0: "TwoB", 4.0: "FourB", 9.0: "NineB"}

    def test_family_is_display_only_and_may_be_empty(self, tmp_path):
        e = config.load(write(tmp_path, TWO_RUNG))
        assert e.family == ""
        assert e.size_display == {1.0: "1B", 27.0: "27B"}

    def test_env_prefix_derives_from_the_slot(self, tmp_path):
        """<SLOT>_AGENT_MODEL_* is the provider-neutral contract shared/llm
        speaks; the slot is a free label, not a vendor name."""
        e = config.load(write(tmp_path, TWO_RUNG))
        assert [r.env_prefix for r in e.ladder] == ["TINY", "BIG"]

    def test_unknown_label_falls_back_to_itself(self, tmp_path):
        e = config.load(write(tmp_path, TWO_RUNG))
        assert e.display_for("something-else-3b") == "something-else-3b"


class TestAnyHost:
    def test_static_provider_is_the_default(self, tmp_path):
        body = TWO_RUNG.replace('provider = "static"\n', "")
        assert config.load(write(tmp_path, body)).serving.provider == "static"

    def test_endpoint_can_be_declared_inline(self, tmp_path):
        """No pod API, no discovery call -- a self-hosted server is just a URL."""
        e = config.load(write(tmp_path, TWO_RUNG))
        assert e.rung("tiny").base_url == "http://localhost:8000/v1"

    def test_key_env_is_named_not_assumed(self, tmp_path):
        assert config.load(write(tmp_path, TWO_RUNG)).serving.key_env == "MY_KEY"


class TestValidation:
    """Config errors are caught at the door, named, and fatal.

    A misconfigured experiment that starts anyway spends money before failing.
    """

    def test_unknown_rung_is_named(self, tmp_path):
        body = TWO_RUNG.replace('rungs = "all"', 'rungs = ["nope"]')
        with pytest.raises(SystemExit, match="nope"):
            config.load(write(tmp_path, body))

    def test_empty_ladder_is_rejected(self, tmp_path):
        body = "\n".join(l for l in TWO_RUNG.splitlines()
                         if not l.startswith(("slot", "model", "params_b", "display",
                                              "base_url", "[[ladder]]")))
        with pytest.raises(SystemExit, match="ladder"):
            config.load(write(tmp_path, body))

    def test_duplicate_slot_is_rejected(self, tmp_path):
        body = TWO_RUNG.replace('slot = "big"', 'slot = "tiny"')
        with pytest.raises(SystemExit, match="duplicate"):
            config.load(write(tmp_path, body))

    def test_profile_with_no_roster_is_rejected(self, tmp_path):
        body = TWO_RUNG.replace(
            'agents = ["alignmentgraph-isd", "react-isd"]\n', "")
        with pytest.raises(SystemExit, match="agents"):
            config.load(write(tmp_path, body))

    def test_missing_file_names_the_override(self, tmp_path):
        with pytest.raises(SystemExit, match="ISD_EXPERIMENT_CONFIG"):
            config.load(tmp_path / "absent.toml")

    def test_unknown_profile_lists_the_known_ones(self):
        with pytest.raises(SystemExit, match="comparison"):
            config.load().profile("nope")


class TestArmFlags:
    def test_expected_flags_come_from_the_declaration(self):
        """Pooling hard-fails when a run's recorded run_config disagrees with
        the arm it is filed under -- a mis-filed run is a silently wrong
        factorial, which nothing downstream can recover."""
        arm = next(a for a in config.load().profile("ablation").arms
                   if a.id == "alignmentgraph-isd-single-graph")
        assert arm.expected_flags == {"agent_mode": "single", "context_mode": "graph"}

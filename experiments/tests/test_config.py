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
[serving]
api_spec = "openai_compatible"
key_env = "MY_KEY"

[[serving.slots]]
slot = "tiny"
model = "meta-llama/Llama-3.2-1B-Instruct"
display = "1B"
base_urls = ["http://localhost:8000/v1"]

[[serving.slots]]
slot = "big"
model = "google/gemma-2-27b-it"
display = "27B"

[experiment.comparison]
dataset = "test_90"
slots = "all"
tags = ["c1"]
agents = ["alignmentgraph-isd", "react-isd"]
proposed = "alignmentgraph-isd"
"""


def write(tmp_path, body: str):
    p = tmp_path / "experiment.toml"
    p.write_text(textwrap.dedent(body), encoding="utf-8")
    return p


class TestShippedConfig:
    """What must hold of the config in the repo WHATEVER its values.

    Nothing here pins a split, a rung count, a tag or a roster: those are the
    study's settings and change with it. Only relations between profiles that
    the code relies on are checked.
    """

    def test_two_official_experiments_exist(self):
        e = config.load()
        assert "comparison" in e.profiles and "ablation" in e.profiles

    def test_reference_arm_leads_the_roster(self):
        """Every delta is taken against it; leading with it puts that in the
        banner and the manifest rather than in a reader's head."""
        p = config.load().profile("ablation")
        assert p.arms[0].id == p.reference

    def test_tune_never_runs_on_the_reporting_split(self):
        """Tuning results never enter the paper, so they must never touch the
        split the paper reports on."""
        e = config.load()
        assert e.profile("tune").dataset != e.profile("comparison").dataset


class TestAnyLadder:
    """Not four rungs, not one family, not one vendor."""

    def test_two_rungs_of_a_different_family(self, tmp_path):
        e = config.load(write(tmp_path, TWO_RUNG))
        assert [r.slot for r in e.models] == ["tiny", "big"]
        assert e.profile("comparison").slots == ("tiny", "big")

    def test_macro_words_are_generated_not_tabulated(self, tmp_path):
        """A model the old hard-coded table never listed still gets a valid
        LaTeX macro name -- digits are illegal in one, so this cannot be the
        number itself."""
        e = config.load(write(tmp_path, TWO_RUNG))
        assert [m.macro for m in e.models] == ["Tiny", "Big"]
        assert all(not any(ch.isdigit() for ch in m.macro) for m in e.models)

    def test_macro_words_are_keyed_and_spelled_by_slot(self, tmp_path):
        """The invariant that replaced "match the old table": two models can
        share a size, so a macro name derived from size is not a name. Derived
        from the slot it is unique, because the slots are."""
        body = TWO_RUNG.replace('display = "27B"', 'display = "1B"')
        e = config.load(write(tmp_path, body))
        assert e.macro_words == {"tiny": "Tiny", "big": "Big"}
        assert len(set(e.macro_words.values())) == len(e.models), (
            "two models of one size must not collapse to one macro name")

    def test_a_digit_in_the_slot_becomes_a_word(self, tmp_path):
        body = TWO_RUNG.replace('slot = "tiny"', 'slot = "small08b"')
        e = config.load(write(tmp_path, body))
        assert e.by_slot("small08b").macro == "SmallZeroEightB"

    def test_family_is_display_only_and_may_be_empty(self, tmp_path):
        """A model with no family shows its bare display, and nothing looks a
        family up to decide anything -- so omitting it stays valid."""
        e = config.load(write(tmp_path, TWO_RUNG))
        assert all(m.family == "" for m in e.models)
        assert [m.full_display() for m in e.models] == ["1B", "27B"]

    def test_family_is_declared_per_model(self, tmp_path):
        """The point of the flat list: two models, two families, one file, and
        no global prefix deciding what either of them is called."""
        body = TWO_RUNG.replace('model = "meta-llama/Llama-3.2-1B-Instruct"',
                                'model = "meta-llama/Llama-3.2-1B-Instruct"\n'
                                'family = "Llama-3.2"')
        body = body.replace('model = "google/gemma-2-27b-it"',
                            'model = "google/gemma-2-27b-it"\nfamily = "Gemma-2"')
        e = config.load(write(tmp_path, body))
        assert [m.full_display() for m in e.models] == ["Llama-3.2-1B", "Gemma-2-27B"]

    def test_two_models_of_one_size_stay_distinct(self, tmp_path):
        """The case the old schema could not express: same size, two families.

        Under the retired size-keyed tables one of these disappeared without a
        word -- the dict simply kept the last one written.
        """
        body = TWO_RUNG.replace('display = "27B"', 'display = "1B"')
        e = config.load(write(tmp_path, body))
        labels = {e.slot_of_label("Llama-3.2-1B-Instruct"),
                  e.slot_of_label("gemma-2-27b-it")}
        assert labels == {"tiny", "big"}
        assert len(e.macro_words) == 2

    def test_env_prefix_derives_from_the_slot(self, tmp_path):
        """<SLOT>_AGENT_MODEL_* is the provider-neutral contract shared/llm
        speaks; the slot is a free label, not a vendor name."""
        e = config.load(write(tmp_path, TWO_RUNG))
        assert [r.env_prefix for r in e.models] == ["TINY", "BIG"]

    def test_unknown_label_falls_back_to_itself(self, tmp_path):
        e = config.load(write(tmp_path, TWO_RUNG))
        assert e.display_for("something-else-3b") == "something-else-3b"


class TestAnyHost:
    def test_endpoint_is_declared_not_discovered(self, tmp_path):
        """No host API, no discovery call -- a served rung is just a URL."""
        e = config.load(write(tmp_path, TWO_RUNG))
        assert e.by_slot("tiny").base_urls == ("http://localhost:8000/v1",)

    def test_a_rung_with_no_endpoint_is_declarable(self, tmp_path):
        """Declaring the ladder must not require the servers to exist yet."""
        assert config.load(write(tmp_path, TWO_RUNG)).by_slot("big").base_urls == ()

    def test_several_endpoints_serve_one_rung(self, tmp_path):
        """Same model on two servers: the agents round-robin across them."""
        body = TWO_RUNG.replace('base_urls = ["http://localhost:8000/v1"]',
                                'base_urls = ["http://a/v1", "http://b/v1"]')
        assert config.load(write(tmp_path, body)).by_slot("tiny").base_urls == (
            "http://a/v1", "http://b/v1")

    def test_a_rung_falls_back_to_the_serving_key(self, tmp_path):
        e = config.load(write(tmp_path, TWO_RUNG))
        assert e.key_env_for(e.by_slot("tiny")) == "MY_KEY"
        assert e.api_spec_for(e.by_slot("tiny")) == "openai_compatible"

    def test_a_rung_can_name_its_own_key(self, tmp_path):
        """A hybrid ladder: a hosted rung authenticates with that provider's
        credential while the self-hosted rungs share the serving key. One
        global key would make the mixed ladder undeclarable."""
        body = TWO_RUNG.replace(
            'display = "27B"',
            'display = "27B"\nbase_urls = ["https://hosted.test/v1"]\n'
            'key_env = "HOSTED_KEY"')
        e = config.load(write(tmp_path, body))
        assert e.key_env_for(e.by_slot("big")) == "HOSTED_KEY"
        assert e.key_env_for(e.by_slot("tiny")) == "MY_KEY", "the others are untouched"

    def test_a_rung_can_name_its_own_api_spec(self, tmp_path):
        body = TWO_RUNG.replace('display = "27B"',
                                'display = "27B"\napi_spec = "something_else"')
        e = config.load(write(tmp_path, body))
        assert e.api_spec_for(e.by_slot("big")) == "something_else"
        assert e.api_spec_for(e.by_slot("tiny")) == "openai_compatible"

    def test_a_malformed_endpoint_list_is_named(self, tmp_path):
        body = TWO_RUNG.replace('base_urls = ["http://localhost:8000/v1"]',
                                'base_urls = 8000')
        with pytest.raises(SystemExit, match="base_urls"):
            config.load(write(tmp_path, body))

    def test_key_env_is_named_not_assumed(self, tmp_path):
        assert config.load(write(tmp_path, TWO_RUNG)).serving.key_env == "MY_KEY"


class TestValidation:
    """Config errors are caught at the door, named, and fatal.

    A misconfigured experiment that starts anyway spends money before failing.
    """

    def test_an_unknown_slot_is_named(self, tmp_path):
        body = TWO_RUNG.replace('slots = "all"', 'slots = ["nope"]')
        with pytest.raises(SystemExit, match="nope"):
            config.load(write(tmp_path, body))

    def test_an_empty_declaration_is_rejected(self, tmp_path):
        body = "\n".join(l for l in TWO_RUNG.splitlines()
                         if not l.startswith(("slot", "model", "display",
                                              "base_urls", "[[serving.slots]]")))
        with pytest.raises(SystemExit, match=r"\[\[serving\.slots\]\]"):
            config.load(write(tmp_path, body))

    @pytest.mark.parametrize("old, where", [
        ("[[model]]", r"\[\[model\]\] -> \[\[serving\.slots\]\]"),
        ("[alignment]", r"\[alignment\.\.\.\] -> \[judge\.alignment"),
        ("[judge]\nprovider = \"x\"", r"\[judge\] provider -> \[judge\.llm\]"),
    ])
    def test_a_table_in_the_wrong_place_is_refused_with_its_move(self, tmp_path, old, where):
        """Read silently, `[alignment]` would be no arms and `[[model]]` no
        ladder -- an error far from the cause."""
        body = TWO_RUNG + "\n" + old + ("\nslot = \"x\"\n" if old == "[[model]]" else "\n")
        with pytest.raises(SystemExit, match=where):
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
        for arm in config.load().profile("ablation").arms:
            assert arm.expected_flags == {"agent_mode": arm.agent_mode,
                                          "context_mode": arm.context_mode}


class TestGenerationSettings:
    """How every call of every agent is made, declared once for the whole ladder.

    They live in `[generation]` and not on a rung or an agent because applying
    them uniformly is the fairness argument the comparison rests on; the window
    stays in `[serving]`, since it is a property of the endpoints.
    """

    @staticmethod
    def _gen(tmp_path, lines):
        return config.load(write(tmp_path, TWO_RUNG + "\n[generation]\n" + lines + "\n"))

    def test_the_declared_settings_are_read(self):
        cfg = config.load()
        assert cfg.serving.context_window and cfg.generation.max_output_tokens
        assert cfg.generation.streaming is True
        assert cfg.generation.temperature is not None

    def test_they_are_optional(self, tmp_path):
        """A foreign ladder must still load; the pressure to declare them comes
        from `audit preflight`, which fails on an undeclared setting, not from
        the parser, which would make every other config unusable."""
        cfg = config.load(write(tmp_path, TWO_RUNG))
        g = cfg.generation
        assert (cfg.serving.context_window, g.max_output_tokens, g.streaming) == (None,) * 3
        assert g.thinking_budget is None and g.temperature is None

    def test_a_clamp_that_leaves_no_room_for_a_prompt_is_rejected(self, tmp_path):
        body = TWO_RUNG.replace('key_env = "MY_KEY"',
                                'key_env = "MY_KEY"\ncontext_window = 8192')
        body += "\n[generation]\nmax_output_tokens = 8192\n"
        with pytest.raises(SystemExit, match="no room for a prompt"):
            config.load(write(tmp_path, body))

    def test_structured_outputs_is_a_boolean_posture(self, tmp_path):
        """Declared like streaming: absent keeps the reader's default, a bool
        is published as 1/0, anything else is refused."""
        assert self._gen(tmp_path, "").generation.structured_outputs is None
        assert self._gen(tmp_path, "structured_outputs = true").generation.structured_outputs is True
        assert self._gen(tmp_path, "structured_outputs = false").generation.structured_outputs is False
        with pytest.raises(SystemExit, match="structured_outputs"):
            self._gen(tmp_path, 'structured_outputs = "yes"')

    def test_a_non_boolean_streaming_is_rejected(self, tmp_path):
        with pytest.raises(SystemExit, match="true or false"):
            self._gen(tmp_path, 'streaming = "yes"')

    def test_a_zero_window_is_rejected(self, tmp_path):
        body = TWO_RUNG.replace('key_env = "MY_KEY"',
                                'key_env = "MY_KEY"\ncontext_window = 0')
        with pytest.raises(SystemExit, match="positive integer"):
            config.load(write(tmp_path, body))

    def test_a_zero_thinking_budget_is_a_posture_not_an_omission(self, tmp_path):
        """0 means "serve with thinking off", which is a declaration like any
        other -- so it must not go through the positive-integer parser, whose
        whole job is to reject 0 as a missing value."""
        assert self._gen(tmp_path, "thinking_budget = 0").generation.thinking_budget == 0

    def test_a_negative_thinking_budget_is_rejected(self, tmp_path):
        with pytest.raises(SystemExit, match="non-negative integer"):
            self._gen(tmp_path, "thinking_budget = -1")

    @pytest.mark.parametrize("value", ["-0.1", "2.5", '"hot"', "true"])
    def test_a_temperature_out_of_range_is_rejected(self, tmp_path, value):
        with pytest.raises(SystemExit, match=r"temperature must be a number in \[0, 2\]"):
            self._gen(tmp_path, f"temperature = {value}")

    def test_an_integer_temperature_reads_as_a_float(self, tmp_path):
        assert self._gen(tmp_path, "temperature = 1").generation.temperature == 1.0

    def test_a_misspelt_key_is_refused(self, tmp_path):
        """Every key reaches every agent's calls: a typo is a posture written
        down and never applied."""
        with pytest.raises(SystemExit, match="unknown key"):
            self._gen(tmp_path, "temprature = 0.7")

    @pytest.mark.parametrize("key, value", [("max_output_tokens", "8192"),
                                            ("streaming", "true"),
                                            ("thinking_budget", "0"),
                                            ("temperature", "0.7"),
                                            ("structured_outputs", "true")])
    def test_a_generation_key_in_serving_is_refused_with_its_move(self, tmp_path, key, value):
        body = TWO_RUNG.replace('key_env = "MY_KEY"', f'key_env = "MY_KEY"\n{key} = {value}')
        with pytest.raises(SystemExit, match=r"belong\(s\) in \[generation\]"):
            config.load(write(tmp_path, body))

    def test_options_still_collect_the_remainder(self, tmp_path):
        """Popping the new keys must not swallow the table a provider reads."""
        body = TWO_RUNG.replace(
            'key_env = "MY_KEY"',
            'key_env = "MY_KEY"\ncontext_window = 4096\n\n[serving.somehost]\nrest_base = "https://x/v1"')
        s = config.load(write(tmp_path, body)).serving
        assert s.context_window == 4096
        assert s.options["somehost"]["rest_base"] == "https://x/v1"


class TestHarnessPosture:
    """The Developer worker count is declared once, like a serving limit, and a
    value the adapter could not apply is refused here rather than dropped."""

    def test_the_declared_count_is_read(self):
        assert config.load().harness.fanout_workers >= 1

    def test_it_is_optional(self, tmp_path):
        assert config.load(write(tmp_path, TWO_RUNG)).harness.fanout_workers is None

    @pytest.mark.parametrize("value", ["0", "-1", "true", '"4"'])
    def test_anything_but_a_positive_integer_is_rejected(self, tmp_path, value):
        body = TWO_RUNG + f"\n[harness]\nfanout_workers = {value}\n"
        with pytest.raises(SystemExit, match="positive integer"):
            config.load(write(tmp_path, body))

    def test_an_unknown_key_is_rejected(self, tmp_path):
        """Every key here is published to the proposed system, so a misspelt
        one would be a posture written down and never applied."""
        body = TWO_RUNG + "\n[harness]\nfanout_worker = 2\n"
        with pytest.raises(SystemExit, match="unknown key"):
            config.load(write(tmp_path, body))

    def test_the_development_mode_is_declared_and_read(self):
        """How much of the plan the proposed system writes out is a posture of
        the run like the worker count: declared once, recorded in the freeze
        manifest, and the same for every arm and rung."""
        assert config.load().harness.development_mode in config.DEVELOPMENT_MODES

    def test_the_development_mode_is_optional(self, tmp_path):
        assert config.load(write(tmp_path, TWO_RUNG)).harness.development_mode is None

    @pytest.mark.parametrize("value", ['"sample"', '"Light"', "1", "true"])
    def test_anything_but_light_or_full_is_rejected(self, tmp_path, value):
        body = TWO_RUNG + f"\n[harness]\ndevelopment_mode = {value}\n"
        with pytest.raises(SystemExit, match="development_mode"):
            config.load(write(tmp_path, body))


class TestJudgeDeclaration:
    """The judge roster decides what every reported LLM judge score means, so it
    belongs in the file the freeze manifest fingerprints rather than in a .env a
    tuning session can leave behind."""

    JUDGE = textwrap.dedent("""
        [judge.llm]
        provider = "somehost"
        base_url = "https://somehost.test/v1"
        key_env = "SOMEHOST_API_KEY"

        [[judge.llm.models]]
        name = "vendor/model-a"

        [[judge.llm.models]]
        name = "vendor/model-b"
        key_envs = ["SOMEHOST_API_KEY", "SOMEHOST_API_KEY2"]
        """)

    def _judge(self, tmp_path, body=None):
        return config.load(write(tmp_path, TWO_RUNG + (body or self.JUDGE))).judge

    def test_an_absent_section_leaves_the_reader_to_answer(self, tmp_path):
        """Undeclared must stay usable: the benchmark and the evaluator run with
        no experiment.toml at all, and the launcher then passes no judge flag."""
        from isd_experiments.judge import judge_env, judge_flags

        judge = config.load(write(tmp_path, TWO_RUNG)).judge
        assert judge.declared is False
        assert judge_env(judge) == {}
        assert judge_flags(judge) == []

    def test_every_emitted_list_is_index_aligned_to_the_names(self, tmp_path):
        """`JUDGE_MODEL_NAMES` is the master list and the evaluator reads every
        other plural by position against it."""
        from isd_experiments.judge import judge_env

        env = judge_env(self._judge(tmp_path))
        names = env["JUDGE_MODEL_NAMES"].split(",")
        for key, value in env.items():
            if key.endswith("S") and key != "JUDGE_MODEL_NAMES":
                assert len(value.split(",")) == len(names), key

    def test_a_plural_the_declaration_does_not_state_is_left_out(self, tmp_path):
        """An absent plural is not a gap. The reader falls back per index to the
        singular, so writing that same default into every slot would assert
        nothing -- except for `provider`, whose fallback is DERIVED from each
        judge's `vendor/model` slug. That derived value is what lands in the
        comparison report and in the roster identity a re-judge is checked
        against, so filling it in would relabel both."""
        from isd_experiments.judge import judge_env

        env = judge_env(self._judge(tmp_path))
        assert "JUDGE_MODEL_PROVIDERS" not in env
        assert "JUDGE_MODEL_BASE_URLS" not in env

    def test_the_plural_provider_is_all_or_nothing(self, tmp_path):
        from isd_experiments.judge import judge_env

        body = self.JUDGE.replace('name = "vendor/model-a"',
                                  'name = "vendor/model-a"\nprovider = "somehost"')
        partly = judge_env(self._judge(tmp_path, body))
        assert "JUDGE_MODEL_PROVIDERS" not in partly, "one judge naming a provider is not all"

        body = body.replace('name = "vendor/model-b"',
                            'name = "vendor/model-b"\nprovider = "otherhost"')
        fully = judge_env(self._judge(tmp_path, body))
        assert fully["JUDGE_MODEL_PROVIDERS"] == "somehost,otherhost"

    def test_the_singular_names_are_emitted_too(self, tmp_path):
        """Two auxiliary evaluators read only the singular names as their own
        fallback chain. A declaration that set the plurals alone would leave
        them on a default the declaration never mentions."""
        from isd_experiments.judge import judge_env

        env = judge_env(self._judge(tmp_path))
        assert env["JUDGE_MODEL_PROVIDER"] == "somehost"
        assert env["JUDGE_MODEL_BASE_URL"] == "https://somehost.test/v1"
        assert env["JUDGE_MODEL_API_KEY_ENV"] == "SOMEHOST_API_KEY"

    def test_several_credentials_for_one_judge_rotate(self, tmp_path):
        from isd_experiments.judge import judge_env

        env = judge_env(self._judge(tmp_path))
        assert env["JUDGE_MODEL_API_KEY_ENVS"] == \
            "SOMEHOST_API_KEY,SOMEHOST_API_KEY|SOMEHOST_API_KEY2"
        assert env["JUDGE_MODEL_CREDENTIAL_STRATEGIES"] == "first,round_robin"

    def test_the_declaration_emits_no_more_than_it_states(self):
        """It replaced four lines of an environment file. Anything beyond those
        four is an assertion the environment never made -- and for `provider`,
        one that would relabel every judge in every report."""
        from isd_experiments.judge import judge_env

        assert set(judge_env(config.load().judge)) == {
            "JUDGE_MODEL_NAMES", "JUDGE_MODEL_PROVIDER",
            "JUDGE_MODEL_BASE_URL", "JUDGE_MODEL_API_KEY_ENV",
        }

    def test_no_key_value_can_reach_the_environment(self, tmp_path):
        from isd_experiments.judge import judge_env

        env = judge_env(self._judge(tmp_path))
        assert "JUDGE_MODEL_API_KEY" not in env
        assert "JUDGE_MODEL_API_KEYS" not in env

    def test_a_literal_key_is_refused_at_the_door(self, tmp_path):
        body = self.JUDGE.replace('name = "vendor/model-a"',
                                  'name = "vendor/model-a"\napi_key = "sk-live-secret"')
        with pytest.raises(SystemExit, match="key VALUE"):
            self._judge(tmp_path, body)

    def test_a_separator_in_a_value_is_refused(self, tmp_path):
        """These values are joined on ',' and '|' and quoted into one command,
        so a stray separator is a misaligned roster rather than a parse error."""
        body = self.JUDGE.replace('name = "vendor/model-a"', 'name = "vendor/a,b"')
        with pytest.raises(SystemExit, match="may not contain"):
            self._judge(tmp_path, body)

    def test_a_key_envs_entry_that_is_not_a_variable_name_is_refused(self, tmp_path):
        body = self.JUDGE.replace('key_envs = ["SOMEHOST_API_KEY", "SOMEHOST_API_KEY2"]',
                                  'key_envs = ["sk-live-secret"]')
        with pytest.raises(SystemExit, match="environment variable name"):
            self._judge(tmp_path, body)

    def test_a_section_with_no_models_is_refused(self, tmp_path):
        with pytest.raises(SystemExit, match="no \\[\\[judge.llm.models\\]\\]"):
            self._judge(tmp_path, "\n[judge.llm]\nprovider = \"somehost\"\n")

    def test_the_flags_carry_the_same_roster_as_the_environment(self, tmp_path):
        """One renderer, because a re-judge scored by a different roster than the
        original run is rejected as a roster change."""
        from isd_experiments.judge import judge_env, judge_flags

        judge = self._judge(tmp_path)
        flags = judge_flags(judge)
        pairs = dict(zip(flags[::2], flags[1::2]))
        assert pairs["--judge-model-names"] == judge_env(judge)["JUDGE_MODEL_NAMES"]
        assert not any(f.startswith("--judge-model-api-key") and "env" not in f
                       for f in flags)

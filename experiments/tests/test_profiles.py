"""What each launch profile actually launches.

The design the roadmap fixed is a set of facts about these profiles -- which
split, how many rungs, how many runs per cell, which roster. Asserting them
here is cheap, and it is the difference between a launcher that is configured
correctly and one that merely runs.

The hazard this replaces: the launcher sourced `.env` and let it override the
experiment's own identity, so a `DATASET=train_10` left behind by a tuning
session would silently run an official experiment on the tuning split with the
wrong agent list, and nothing would say so except a banner nobody re-reads.
With the profile authoritative, that cannot happen -- these tests pin it.
"""

from __future__ import annotations

import shutil
import subprocess
import textwrap

import pytest

from isd_experiments import paths
from isd_experiments.config import current
from isd_experiments.launch import INFORMAL, profile_env


@pytest.fixture(scope="module")
def envs():
    return {name: profile_env(current().profile(name))
            for name in ("comparison", "ablation", "tune")}


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
    def test_tune_neither_confirms_nor_records(self, envs):
        """Its results never enter the paper, so a manifest would assert a
        provenance that means nothing."""
        for name in INFORMAL:
            assert envs[name]["CONFIRM"] == "0"
            assert envs[name]["MANIFEST"] == "0"

    def test_they_run_on_the_training_split(self, envs):
        for name in INFORMAL:
            assert envs[name]["DATASET"] == "train_10"


class TestLadderIsConfiguration:
    def test_slot_env_quads_are_exported_from_the_declaration(self, envs):
        """The launcher carried four hard-coded blocks naming one model family;
        a different ladder meant editing shell.

        The names are UNDERSCORED: the launcher sources .env after reading
        these, so a quad published under the name the benchmark reads is taken
        back by any stale line in that file.
        """
        e = envs["comparison"]
        for slot in e["_SLOTS_LIST"].split():
            prefix = slot.upper()
            assert e[f"_{prefix}_AGENT_MODEL_NAME"]
            assert e[f"_{prefix}_AGENT_MODEL_API_KEY_ENVS"]

    def test_a_hybrid_ladder_reaches_the_benchmark_with_each_key(self, tmp_path):
        """Not every rung lives on the same host, so not every rung
        authenticates with the same credential.

        End to end through the launcher rather than through profile_env alone:
        the value has to survive experiment.toml -> the underscored export ->
        `source .env` -> the flag string, and it is the middle step that used
        to lose it.
        """
        import os
        src = (paths.exp_root() / "tests" / "fixtures" / "two_rung.toml").read_text()
        cfg = tmp_path / "experiment.toml"
        # On the FIRST rung: a dry run prints the first slot's command, and it
        # is the printed command this test is about.
        cfg.write_text(
            src.replace('base_urls = ["http://localhost:8000/v1"]',
                        'base_urls = ["https://hosted.test/v1"]\n'
                        'key_env = "HOSTED_KEY"'),
            encoding="utf-8")
        out = subprocess.run(
            [str(paths.exp_root() / ".venv" / "bin" / "python"),
             "-m", "isd_experiments.cli", "comparison", "run", "--dry-run"],
            capture_output=True, text=True, cwd=str(paths.exp_root()),
            env=dict(os.environ, ISD_EXPERIMENT_CONFIG=str(cfg)))
        assert out.returncode == 0, out.stderr
        assert "--agent-model-api-key-envs 'HOSTED_KEY'" in out.stdout, (
            "the hosted rung lost its own key on the way to the benchmark")
        assert "--agent-model-base-url 'https://hosted.test/v1'" in out.stdout

    def test_no_slot_quad_is_published_under_a_shadowable_name(self, envs):
        """A plain name here is one `source .env` away from being overridden."""
        e = envs["comparison"]
        for slot in e["_SLOTS_LIST"].split():
            prefix = slot.upper()
            for suffix in ("NAME", "API_KEY_ENVS", "API_SPEC", "BASE_URLS"):
                assert f"{prefix}_AGENT_MODEL_{suffix}" not in e, (
                    f"{prefix}_AGENT_MODEL_{suffix} is published unprotected")

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


@pytest.fixture(scope="module")
def plan():
    """The launch plan for the shipped declaration, command included."""
    return _dry_run()


def _dry_run(config_path=None):
    """The launch plan, including the command the child would actually run."""
    import os

    env = dict(os.environ)
    if config_path is not None:
        env["ISD_EXPERIMENT_CONFIG"] = str(config_path)
    out = subprocess.run(
        [str(paths.exp_root() / ".venv" / "bin" / "python"),
         "-m", "isd_experiments.cli", "comparison", "run", "--dry-run"],
        capture_output=True, text=True, env=env, cwd=str(paths.exp_root()))
    assert out.returncode == 0, out.stderr
    return out.stdout


class TestTheChildCommandCarriesTheDeclaration:
    """A summary of the flags is not the flags.

    Assembling the child command in its own function is what lets a dry run
    print the thing that would really be executed -- and what makes the three
    channels checkable without spending a benchmark run: an argument the parent
    quotes, a flag list that beats the environment, and an assignment prefix
    that sits after the child re-reads .env.
    """

    def test_the_api_spec_is_passed_and_the_vendor_label_is_gone(self, plan):
        """`api_spec` is what the benchmark dispatches the client on. The label
        that used to travel in its place carried the endpoint-discovery
        provider, which is a different question with different values."""
        assert "--agent-model-api-spec 'openai_compatible'" in plan
        assert "--agent-model-provider" not in plan

    def test_the_serving_limits_prefix_the_interpreter(self, plan):
        """After the child sources .env and ahead of the benchmark's own dotenv
        load, so neither can take them back."""
        command = plan.split("command (first slot):", 1)[1]
        names = ("AGENT_MODEL_CONTEXT_WINDOW", "AGENT_MODEL_MAX_OUTPUT_TOKENS",
                 "AGENT_MODEL_STREAMING", "AGENT_MODEL_THINKING_BUDGET",
                 "HARNESS_FANOUT_WORKERS")
        for name in names:
            assert f"{name}='" in command
        # Nothing between the LAST assignment and the interpreter: an exported
        # variable would sit before the child re-reads .env, which is the whole
        # difference between this and an export. Found by position rather than
        # by name, so adding a limit does not silently stop this from checking
        # the thing it is named after.
        last = max(command.index(f"{name}='") for name in names)
        after = command[last:].split("='", 1)[1]
        assert after.split("'", 1)[1].strip().startswith("'"), after[:80]
        assert "run_benchmark.py" in after.split(";", 1)[0]

    def test_every_parent_expanded_value_is_quoted(self, plan):
        """An unquoted empty expansion disappears and shifts the next flag's
        value onto this one -- the failure matrix_resolve_slots fails fast on."""
        command = plan.split("command (first slot):", 1)[1]
        for flag in ("--dataset", "--agents", "--rate-limit", "--agent-model-api-spec",
                     "--agent-model-base-url", "--agent-model-name",
                     "--agent-model-api-key-envs"):
            after = command.split(f"{flag} ", 1)[1]
            assert after.startswith("'"), f"{flag} is not quoted"

    def test_an_undeclared_judge_contributes_no_flag(self, tmp_path):
        """Undeclared has to leave the command unshifted, not empty-argumented:
        the benchmark and the evaluator must still answer for the roster the way
        they do with no experiment.toml at all."""
        cfg = tmp_path / "experiment.toml"
        cfg.write_text((paths.exp_root() / "tests" / "fixtures" / "two_rung.toml")
                       .read_text(encoding="utf-8"), encoding="utf-8")
        command = _dry_run(cfg).split("command (first slot):", 1)[1]
        assert "--judge-model" not in command
        assert "AGENT_MODEL_MAX_OUTPUT_TOKENS='" not in command

    def test_a_declared_judge_reaches_the_command(self, tmp_path):
        cfg = tmp_path / "experiment.toml"
        cfg.write_text(
            (paths.exp_root() / "tests" / "fixtures" / "two_rung.toml")
            .read_text(encoding="utf-8")
            + textwrap.dedent("""
                [judge]
                provider = "somehost"
                key_env = "SOMEHOST_API_KEY"

                [[judge.models]]
                name = "vendor/model-a"
                """),
            encoding="utf-8")
        command = _dry_run(cfg).split("command (first slot):", 1)[1]
        assert "--judge-model-names 'vendor/model-a'" in command
        assert "--judge-model-api-key-env 'SOMEHOST_API_KEY'" in command
        # A key VALUE has no spelling in the declaration and none on the command.
        assert "--judge-model-api-key '" not in command
        assert "--judge-model-api-keys" not in command


class TestNoDeclaredFieldIsInert:
    """A field the TOML declares must reach the launcher, or it is decoration.

    The defect this guards: `scenario_limit` and `llm_judge` were both parsed
    into `Profile` and read by nobody. `profile_env` never emitted them and
    run_benchmark.py had no flag to receive them, so a profile declaring a
    three-scenario judge-free smoke run in fact launched the whole tuning split
    with the LLM judge attached. Config that describes a run nobody makes is
    worse than no config, because it is read as documentation.

    Fields that deliberately stay on the Python side are listed with the reason,
    so adding one is a decision rather than an omission.
    """

    #: Consumed in Python, never handed to the shell.
    PYTHON_ONLY = {
        "name": "used to build EXPERIMENT and the pool hint",
        "title": "exported as EXPERIMENT_TITLE, under a different key",
        "models": "expanded into per-slot env quads and _SLOTS_LIST",
        "arms": "read by the ablation pooling, never launched directly",
        "proposed": "read by comparison pooling to name the reference column",
        "reference": "read by ablation pooling to name the reference arm",
        "confirm": "folded into CONFIRM together with the INFORMAL set",
        "dataset": "exported as DATASET and CANONICAL_DATASET",
        "tags": "exported as _RUN_TAGS_LIST",
        "agents": "exported as AGENTS",
        "rate_limit": "exported as RATE_LIMIT",
        "session_prefix": "exported as SESSION_PREFIX",
    }

    def test_every_profile_field_is_read_by_someone(self, envs):
        import dataclasses

        from isd_experiments.config import Profile
        from isd_experiments.launch import profile_env

        emitted = set(profile_env(current().profile("tune")))
        for field in dataclasses.fields(Profile):
            name = field.name
            if name in self.PYTHON_ONLY:
                continue
            assert name.upper() in emitted, (
                f"Profile.{name!r} is declared in experiment.toml but never "
                f"reaches the launcher. Either wire it through profile_env "
                f"and the child command, or delete it -- do not leave it as a "
                f"claim about a run nobody makes. If it is read only in "
                f"Python, say where in PYTHON_ONLY."
            )

    def test_the_python_only_list_has_no_stale_entries(self):
        import dataclasses

        from isd_experiments.config import Profile

        declared = {f.name for f in dataclasses.fields(Profile)}
        assert set(self.PYTHON_ONLY) <= declared, (
            f"PYTHON_ONLY names fields that no longer exist: "
            f"{sorted(set(self.PYTHON_ONLY) - declared)}"
        )

    #: Serving fields consumed in Python, never handed to the shell.
    SERVING_PYTHON_ONLY = {
        "key_env": "emitted as `<SLOT>_AGENT_MODEL_API_KEY_ENVS`, the plural name "
                   "the agents read",
        "options": "the un-popped remainder of [serving] -- a bag for a provider, "
                   "not a field",
    }

    def test_every_serving_field_is_read_by_someone(self, envs):
        """The defect this guards: `api_spec` was declared, parsed, and emitted
        by nobody, while the value actually shipped under
        `<SLOT>_AGENT_MODEL_PROVIDER` came from a different question entirely
        (which host discovers the endpoints). One field was documentation and
        the other was wrong, and the Profile-only walk saw neither."""
        import dataclasses

        from isd_experiments.config import Serving

        emitted = set(profile_env(current().profile("tune")))
        for field in dataclasses.fields(Serving):
            name = field.name
            if name in self.SERVING_PYTHON_ONLY:
                continue
            upper = name.upper()
            assert any(key == upper or key.endswith(f"_AGENT_MODEL_{upper}")
                       for key in emitted), (
                f"Serving.{name!r} is declared in experiment.toml but never reaches "
                f"the launcher. Either wire it through profile_env and the child "
                f"command, or delete it. If it is read only in Python, say where in "
                f"SERVING_PYTHON_ONLY."
            )

    def test_the_serving_python_only_list_has_no_stale_entries(self):
        import dataclasses

        from isd_experiments.config import Serving

        declared = {f.name for f in dataclasses.fields(Serving)}
        assert set(self.SERVING_PYTHON_ONLY) <= declared

    def test_every_emitted_agent_model_name_appears_in_the_launcher(self, envs):
        """Exporting into a void is the same defect from the other side: a value
        `profile_env` publishes that no line of the launcher reads changes
        nothing about the run it claims to describe."""
        script = (paths.exp_root() / "bin" / "_matrix.sh").read_text(encoding="utf-8")
        script += (paths.exp_root() / "bin" / "launch.sh").read_text(encoding="utf-8")
        suffixes = {key.split("_AGENT_MODEL_", 1)[1]
                    for key in profile_env(current().profile("comparison"))
                    if "_AGENT_MODEL_" in key}
        for suffix in sorted(suffixes):
            assert f"_AGENT_MODEL_{suffix}" in script, (
                f"profile_env publishes <SLOT>_AGENT_MODEL_{suffix}, which the "
                f"launcher never reads."
            )

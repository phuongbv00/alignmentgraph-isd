"""What each launch profile actually launches.

Which split, how many rungs, how many runs per cell and which roster are the
study's settings and are NOT pinned here -- they change with the study. What is
checked is how a profile becomes a launch: the profile is authoritative, an
official experiment confirms and records, and the pools cannot mix.

The hazard this replaces: the launcher sourced `.env` and let it override the
experiment's own identity, so a `DATASET=train_10` left behind by a tuning
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
            for name in ("comparison", "ablation", "tune")}


class TestOfficialExperiments:
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

    def test_a_hybrid_ladder_reaches_each_rung_with_its_own_key(self, tmp_path):
        """Not every rung lives on the same host, so not every rung
        authenticates with the same credential.

        Asserted on the config the runner builds for the rung, which is what
        every agent of that run is handed.
        """
        from isd_experiments.config import load
        from isd_experiments.runner.llm import slot_config

        src = (paths.exp_root() / "tests" / "fixtures" / "two_rung.toml").read_text()
        cfg_path = tmp_path / "experiment.toml"
        cfg_path.write_text(
            src.replace('base_urls = ["http://localhost:8000/v1"]',
                        'base_urls = ["https://hosted.test/v1"]\n'
                        'key_env = "HOSTED_KEY"'),
            encoding="utf-8")
        cfg = load(cfg_path)
        first, second = cfg.models[0], cfg.models[1]
        hosted = slot_config(cfg, first)
        assert hosted.api_key_envs == ("HOSTED_KEY",), (
            "the hosted rung lost its own key on the way to the agents")
        assert hosted.all_base_urls == ("https://hosted.test/v1",)
        assert slot_config(cfg, second).api_key_envs == (cfg.serving.key_env,)

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
             "-m", "isd_experiments.cli", "run", "comparison", "--dry-run"],
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
         "-m", "isd_experiments.cli", "run", "comparison", "--dry-run"],
        capture_output=True, text=True, env=env, cwd=str(paths.exp_root()))
    assert out.returncode == 0, out.stderr
    return out.stdout


class TestTheChildCommandCarriesTheDeclaration:
    """A summary of the flags is not the flags.

    Each tmux session runs `isd-exp run <experiment> --foreground` for one slot
    and one tag, and that run reads the declaration itself. So the command
    carries the declaration's PATH and what a launch may override for this
    invocation, and nothing the declaration already says -- a model, an
    endpoint, a serving limit or a judge on the command line would be a second
    copy that can disagree with the first.
    """

    @staticmethod
    def _command(plan: str) -> str:
        # The first slot's command: the plan prints one per slot.
        return plan.split("commands:", 1)[1].split("# --- tmux session", 2)[1]

    def test_each_session_runs_the_experiment_in_the_foreground(self, plan):
        command = self._command(plan)
        assert "-m isd_experiments.cli" in command
        assert "run 'comparison' --foreground" in command
        assert "run_benchmark.py" not in command

    def test_the_child_reads_the_same_declaration(self, plan):
        from isd_experiments.config import current
        assert f"ISD_EXPERIMENT_CONFIG='{current().source}'" in self._command(plan)

    def test_nothing_the_declaration_says_travels_on_the_command(self, plan):
        command = self._command(plan)
        for leaked in ("--agent-model", "--judge-model", "AGENT_MODEL_",
                       "HARNESS_FANOUT_WORKERS", "HARNESS_DEVELOPMENT_MODE"):
            assert leaked not in command, leaked

    def test_every_parent_expanded_value_is_quoted(self, plan):
        """An unquoted empty expansion disappears and shifts the next flag's
        value onto this one."""
        command = self._command(plan)
        for flag in ("--slots", "--agents", "--rate-limit"):
            after = command.split(f"{flag} ", 1)[1]
            assert after.startswith("'"), f"{flag} is not quoted"

    def test_judging_is_off_unless_asked_for(self, plan):
        assert "--judge" not in self._command(plan)
        assert "judges  : off" in plan

    def test_judge_reaches_every_session(self):
        import os

        out = subprocess.run(
            [str(paths.exp_root() / ".venv" / "bin" / "python"),
             "-m", "isd_experiments.cli", "run", "comparison", "--dry-run",
             "--judge"],
            capture_output=True, text=True, env=dict(os.environ),
            cwd=str(paths.exp_root()))
        assert out.returncode == 0, out.stderr
        assert "--judge" in self._command(out.stdout)
        assert "judges  : after each run" in out.stdout
        from isd_experiments.alignment.presets import current as arms
        from isd_experiments.config import current as cfg
        judged = arms()
        assert f"* llm       : {','.join(m.name for m in cfg().judge.models)}" in out.stdout
        assert (f"* alignment : {judged.primary_encoder},{judged.primary_bloom}"
                in out.stdout)


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


def test_an_unpooled_profile_says_why_instead_of_printing_nothing():
    """`tune` has no pool command; the plan line said `pool    : ` and nothing."""
    import os

    out = subprocess.run(
        [str(paths.exp_root() / ".venv" / "bin" / "python"),
         "-m", "isd_experiments.cli", "run", "tune", "--dry-run"],
        capture_output=True, text=True, env=dict(os.environ), cwd=str(paths.exp_root()))
    assert out.returncode == 0, out.stderr
    line = next(ln for ln in out.stdout.splitlines() if ln.strip().startswith("pool"))
    assert "not pooled" in line

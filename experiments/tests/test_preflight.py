"""The pre-flight audit, in the part that needs no endpoint.

`check_protection` is separated from the network checks precisely so it can be
exercised here: the question it answers -- does exactly one place declare each
serving limit -- is decided by two files on disk and nothing else.
"""

from __future__ import annotations

from isd_experiments import config
from isd_experiments.audit import preflight

DECLARED = """
[serving]
provider = "static"
api_spec = "openai_compatible"
key_env = "MY_KEY"
context_window = 16384
max_output_tokens = 8192
streaming = true

[[ladder]]
slot = "tiny"
model = "vendor/model-1b"
params_b = 1.0

[experiment.comparison]
dataset = "test_90"
rungs = "all"
tags = ["c1"]
agents = ["alignmentgraph-isd"]
"""


def _cfg(tmp_path, body=DECLARED):
    path = tmp_path / "experiment.toml"
    path.write_text(body, encoding="utf-8")
    return config.load(path)


def _findings(tmp_path, env_text="", body=DECLARED):
    env_path = tmp_path / "dotenv"
    env_path.write_text(env_text, encoding="utf-8")
    return {label: (ok, detail)
            for ok, label, detail in preflight.check_protection(_cfg(tmp_path, body), env_path)}


class TestServingLimitsAreDeclaredOnce:
    def test_a_clean_declaration_passes(self, tmp_path):
        assert all(ok for ok, _ in _findings(tmp_path).values())

    def test_an_undeclared_limit_fails_and_names_the_source(self, tmp_path):
        """Undeclared means the launcher passes nothing and the benchmark falls
        back to its own default -- which is not the run anyone wrote down."""
        body = DECLARED.replace("max_output_tokens = 8192\n", "")
        found = _findings(tmp_path, body=body)
        ok, detail = found["[serving].max_output_tokens declared"]
        assert not ok and "experiment.toml" in detail

    def test_a_limit_also_set_in_the_env_file_fails(self, tmp_path):
        """Two sources for a limit that has to be uniform across every agent and
        every rung is how a comparison loses its fairness argument quietly. Only
        one of the two is fingerprinted, so the duplicate is the dangerous one."""
        found = _findings(tmp_path, "AGENT_MODEL_STREAMING=1\n")
        ok, detail = found["AGENT_MODEL_STREAMING absent from .env"]
        assert not ok and "experiment.toml owns" in detail

    def test_an_exported_assignment_counts_as_setting_it(self, tmp_path):
        found = _findings(tmp_path, "export AGENT_MODEL_CONTEXT_WINDOW='16384'\n")
        assert not found["AGENT_MODEL_CONTEXT_WINDOW absent from .env"][0]

    def test_a_comment_does_not(self, tmp_path):
        found = _findings(tmp_path, "# AGENT_MODEL_CONTEXT_WINDOW=16384\n")
        assert found["AGENT_MODEL_CONTEXT_WINDOW absent from .env"][0]

    def test_it_reads_the_file_rather_than_the_process(self, tmp_path, monkeypatch):
        """The question is what .env says on its own account. Loading it first
        would make an ambient variable look like a duplicate declaration."""
        monkeypatch.setenv("AGENT_MODEL_STREAMING", "1")
        assert all(ok for ok, _ in _findings(tmp_path).values())


class TestEnvFileParsing:
    def test_quotes_and_export_are_stripped(self, tmp_path):
        path = tmp_path / "dotenv"
        path.write_text('export A="1"\nB=\'two\'\n# C=3\n\nD=\n', encoding="utf-8")
        assert preflight.env_file_assignments(path) == {"A": "1", "B": "two", "D": ""}

    def test_a_missing_file_assigns_nothing(self, tmp_path):
        assert preflight.env_file_assignments(tmp_path / "absent") == {}

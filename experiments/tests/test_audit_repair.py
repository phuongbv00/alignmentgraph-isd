"""`audit repair` is reachable, and its scope pass spends nothing.

The defect this guards: `cli.py` called `repair.run(...)` and the module defined
no `run` at all, so the stage raised `AttributeError` before it could read a
single report. Every other function in it was written, tested by hand and
unreachable -- which is the worst shape for a stage that exists to rescue a run
after a transient judge failure, because it is needed exactly when nobody has
time to discover it does not work.
"""

from __future__ import annotations

import inspect

import pytest

from isd_experiments import cli
from isd_experiments.audit import repair


def test_the_stage_the_cli_calls_exists():
    assert callable(getattr(repair, "run", None))


def test_the_cli_passes_every_flag_it_accepts():
    """The parser and the call are two hand-written lists of the same options."""
    args = cli.build_parser().parse_args(["audit", "repair"])
    params = set(inspect.signature(repair.run).parameters)
    for name in vars(args):
        if name in {"command", "sub", "config"}:
            continue
        assert name in params, (
            f"`isd-exp audit repair` accepts --{name.replace('_', '-')}, which "
            f"repair.run has no parameter for."
        )


def test_arguments_are_owned_by_the_cli():
    """A second parser inside the stage is a second set of defaults that can
    disagree with the one the user actually types against."""
    source = inspect.getsource(repair)
    assert "argparse" not in source


class TestTheScopePassSpendsNothing:
    def test_an_empty_scope_reports_and_stops(self, tmp_path, capsys):
        assert repair.run(run_dirs=[str(tmp_path)], dry_run=True) == 0
        assert "Nothing to repair" in capsys.readouterr().out

    def test_a_dry_run_never_reaches_the_evaluator(self, tmp_path, monkeypatch):
        def explode(*_args, **_kwargs):
            raise AssertionError("a dry run must not evaluate anything")

        monkeypatch.setattr(repair, "evaluate_target", explode)
        monkeypatch.setattr(repair, "run_postrun_audit", explode)
        assert repair.run(run_dirs=[str(tmp_path)], dry_run=True) == 0

    @pytest.mark.parametrize("bad", [{"max_attempts": 0}, {"backup_suffix": ""}])
    def test_a_setting_that_cannot_work_is_refused_before_any_write(self, bad, tmp_path):
        with pytest.raises(SystemExit):
            repair.run(run_dirs=[str(tmp_path)], dry_run=True, **bad)

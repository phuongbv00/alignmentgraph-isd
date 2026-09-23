"""Each judge's options, held equal to what the CLI passes and what it reads.

The alignment judge builds one `SimpleNamespace` and hands it to helpers that
resolve an encoder spec from a dozen interacting flags -- the right shape for
them, and the reason the bag exists. What it cost was a silent asymmetry: the
namespace was built from `locals()`, so the set of attributes a helper could
read and the set a caller could set looked identical while one was a strict
subset of the other. Seventeen attributes were read, nine could be passed, and
two of the nine were spelled differently on each side. The first line of the
first arm raised `AttributeError`, and nothing at the call site said which
option was missing.

The test is cheap because the question is structural: parse the module, collect
every `args.<name>`, and compare against the signature. The two judges then
share one further guard: the parser and the call are two hand-written lists of
the same options, so every flag either judge accepts must reach its `run`.
"""

from __future__ import annotations

import ast
import inspect

import pytest

from isd_experiments import cli, paths
from isd_experiments.judge import alignment, llm

#: Passed to `run` and consumed by its own body rather than by a helper, so they
#: never appear as `args.<name>`. Listed with the reason, so adding one is a
#: decision rather than an omission.
BODY_ONLY = {
    "run_dirs": "resolved by judge.rundirs in the body before any helper runs",
    "require_all": "turns a skipped arm into an exit, decided before scoring",
    "sweep_csv": "the roster's destination, written after every arm is done",
    "dry_run": "prints the scope and returns before anything is contacted",
    "yes": "skips the overwrite prompt, asked once in the body before any arm",
}


def _attributes_read() -> set[str]:
    source = (paths.exp_root() / "src" / "isd_experiments" / "judge"
              / "alignment.py").read_text(encoding="utf-8")
    return {node.attr for node in ast.walk(ast.parse(source))
            if isinstance(node, ast.Attribute)
            and isinstance(node.value, ast.Name) and node.value.id == "args"}


def test_every_attribute_a_helper_reads_can_be_passed():
    params = set(inspect.signature(alignment.run).parameters)
    missing = sorted(_attributes_read() - params)
    assert not missing, (
        f"judge/alignment.py reads args.{{{', '.join(missing)}}} off the options "
        f"bag, but no caller can set them. Add each as a parameter of run with "
        f"its default."
    )


def test_every_parameter_is_read_by_someone():
    params = set(inspect.signature(alignment.run).parameters)
    unread = sorted(params - _attributes_read() - set(BODY_ONLY))
    assert not unread, (
        f"alignment.run declares {unread} that nothing reads. Wire each through "
        f"or delete it; if the body consumes it directly, say so in BODY_ONLY."
    )


def test_the_body_only_list_has_no_stale_entries():
    params = set(inspect.signature(alignment.run).parameters)
    assert set(BODY_ONLY) <= params


@pytest.mark.parametrize("name, module", [("alignment", alignment), ("llm", llm)])
def test_the_cli_passes_every_option(name, module):
    """A flag the parser accepts but the call drops is silently ignored."""
    args = cli.build_parser().parse_args(["judge", name, "somewhere"])
    params = set(inspect.signature(module.run).parameters)
    for option in vars(args):
        if option in {"command", "sub", "config"}:
            continue
        assert option in params, (
            f"`isd-exp judge {name}` accepts --{option.replace('_', '-')}, which "
            f"judge.{name}.run has no parameter for."
        )


def test_both_judges_share_one_shape():
    """Same verbs, same names: a reader who knows one judge knows the other."""
    shared = {"run_dirs", "agents", "overwrite", "dry_run", "limit", "scenario_root"}
    for module in (alignment, llm):
        assert shared <= set(inspect.signature(module.run).parameters), module.__name__


@pytest.mark.parametrize("module", [alignment, llm])
def test_a_run_dir_is_required(module):
    """An empty roster used to reach `run_dirs[0]` and raise IndexError after
    every arm had already been resolved and probed."""
    with pytest.raises(SystemExit, match="at least one run dir"):
        module.run(run_dirs=())

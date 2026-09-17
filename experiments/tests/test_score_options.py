"""The scorer's options bag, held equal to what its helpers read off it.

`score.run` builds one `SimpleNamespace` and hands it to helpers that resolve an
encoder spec from a dozen interacting flags -- the right shape for them, and the
reason the bag exists. What it cost was a silent asymmetry: the namespace was
built from `locals()`, so the set of attributes a helper could read and the set
a caller could set looked identical while one was a strict subset of the other.
Seventeen attributes were read, nine could be passed, and two of the nine were
spelled differently on each side. The first line of the first arm raised
`AttributeError`, and nothing at the call site said which option was missing.

The test is cheap because the question is structural: parse the module, collect
every `args.<name>`, and compare against the signature.
"""

from __future__ import annotations

import ast
import inspect

from isd_experiments import paths
from isd_experiments.alignment import score

#: Passed to `run` and consumed by its own body rather than by a helper, so they
#: never appear as `args.<name>`. Listed with the reason, so adding one is a
#: decision rather than an omission.
BODY_ONLY = {
    "run_dirs": "globbed and resolved in the body before any helper runs",
    "require_all": "turns a skipped arm into an exit, decided before scoring",
    "sweep_csv": "the roster's destination, written after every arm is done",
}


def _attributes_read() -> set[str]:
    source = (paths.exp_root() / "src" / "isd_experiments" / "alignment"
              / "score.py").read_text(encoding="utf-8")
    return {node.attr for node in ast.walk(ast.parse(source))
            if isinstance(node, ast.Attribute)
            and isinstance(node.value, ast.Name) and node.value.id == "args"}


def test_every_attribute_a_helper_reads_can_be_passed():
    params = set(inspect.signature(score.run).parameters)
    missing = sorted(_attributes_read() - params)
    assert not missing, (
        f"score.py reads args.{{{', '.join(missing)}}} off the options bag, but "
        f"no caller can set them. Add each as a parameter of score.run with its "
        f"default."
    )


def test_every_parameter_is_read_by_someone():
    params = set(inspect.signature(score.run).parameters)
    unread = sorted(params - _attributes_read() - set(BODY_ONLY))
    assert not unread, (
        f"score.run declares {unread} that nothing reads. Wire each through or "
        f"delete it; if the body consumes it directly, say so in BODY_ONLY."
    )


def test_the_body_only_list_has_no_stale_entries():
    params = set(inspect.signature(score.run).parameters)
    assert set(BODY_ONLY) <= params


def test_the_cli_passes_every_option():
    """The parser and the call are two hand-written lists of the same options,
    and a flag the parser accepts but the call drops is silently ignored."""
    from isd_experiments import cli

    parser = cli.build_parser()
    args = parser.parse_args(["score", "somewhere"])
    params = set(inspect.signature(score.run).parameters)
    for name in vars(args):
        if name in {"command", "sub", "config"}:
            continue
        assert name in params, (
            f"`isd-exp score` accepts --{name.replace('_', '-')}, which score.run "
            f"has no parameter for."
        )


def test_a_run_dir_is_required():
    """An empty roster used to reach `run_dirs[0]` and raise IndexError after
    every arm had already been resolved and probed."""
    import pytest

    with pytest.raises(SystemExit, match="at least one run dir"):
        score.run(run_dirs=())

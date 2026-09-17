"""The seam to the benchmark submodule.

Dependency direction is one-way and enforced: this package imports the
benchmark, and nothing in isd-agent-benchmark/ or alignmentgraph-isd/ may
import isd_experiments. ``tests/test_architecture.py`` is the guard.

Three different kinds of thing live over there, and they need three different
answers:

* ``isd_evaluator`` is a real installable package -- so it is installed
  (``pip install -e ../isd-agent-benchmark/evaluator``) and imported normally.
  The scripts this replaces reached it with ``sys.path.insert``, which was only
  ever a workaround for sitting in the wrong repository.
* ``isd-evaluator`` is a console script, invoked as a subprocess.
* ``run_benchmark.py`` is a 67 KB top-level module at the benchmark root with
  no install route (its pyproject declares ``py-modules = []``), and importing
  it executes the whole file. One function is needed from it, so it is loaded
  by spec -- and this is the ONLY spec_from_file_location in the package.
"""

from __future__ import annotations

import importlib.util
import os
import shutil
import sys
from pathlib import Path
from types import ModuleType

from . import paths


def bench_python() -> Path:
    """The interpreter that can import the seven agents.

    Not the one running this process. `isd-exp` lives in experiments/.venv,
    whose core install deliberately has no LLM dependency at all; the agents
    live in the benchmark's own venv. Launching run_benchmark.py with a bare
    `python` inherits whichever interpreter happens to be active, and when that
    is the wrong one the failure is an ImportError deep inside an agent
    registry -- which reads like an agent bug, not a venv bug.
    """
    override = os.environ.get("ISD_BENCH_PYTHON")
    if override:
        return Path(override)
    root = paths.bench_root()
    for candidate in (root / "venv" / "bin" / "python", root / ".venv" / "bin" / "python"):
        if candidate.exists():
            return candidate
    raise SystemExit(
        f"No benchmark interpreter under {root} (looked for venv/ and .venv/).\n"
        f"  Create it with `./scripts/1_setup.sh` in {root}, or set ISD_BENCH_PYTHON."
    )


def bench_env(extra: dict[str, str] | None = None) -> dict[str, str]:
    """Environment for a benchmark subprocess.

    RESULTS_DIR is how run_benchmark.py is told to write into the experiment's
    results tree instead of its own -- the same variable this package reads,
    passed straight through rather than relayed under a second name. Its
    default is unchanged, so a standalone benchmark run still writes where it
    always did.
    """
    env = dict(os.environ)
    env["RESULTS_DIR"] = str(paths.results_root())
    if extra:
        env.update(extra)
    return env


def evaluator_bin() -> Path:
    """The isd-evaluator console script.

    Resolution order matches what the repair script did: PATH first, then
    beside the running interpreter (the usual layout for an editable install
    into a venv).
    """
    found = shutil.which("isd-evaluator")
    if found:
        return Path(found)
    beside = Path(sys.executable).with_name("isd-evaluator")
    if beside.exists():
        return beside
    raise SystemExit(
        "isd-evaluator not found on PATH.\n"
        f"  Install it: {paths.pip()} install -e "
        f"{paths.bench_root() / 'evaluator'}"
    )


def load_run_benchmark() -> ModuleType:
    """Import run_benchmark.py by path.

    THE ONLY spec_from_file_location in this package, and it stays one: the
    benchmark root is not an installable package, so there is no import path to
    it. Only `audit repair` needs this, for generate_summary_report -- a pure
    dict-to-file function. Importing executes the module body, which puts the
    seven agent src/ directories on sys.path; that is the benchmark's own
    doing, and the reason this is called lazily rather than at module import.
    """
    root = paths.bench_root()
    path = root / "run_benchmark.py"
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))
    spec = importlib.util.spec_from_file_location("run_benchmark", path)
    if spec is None or spec.loader is None:
        raise SystemExit(f"Cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module

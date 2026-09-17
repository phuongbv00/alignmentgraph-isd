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

import importlib.metadata as metadata
import importlib.util
import os
import shutil
import subprocess
import sys
import tomllib
from collections.abc import Sequence
from pathlib import Path
from types import ModuleType

from . import paths


def bench_python() -> Path:
    """The interpreter that runs run_benchmark.py: this one.

    ONE environment holds both sides -- isd-exp and the seven agents -- so the
    subprocess inherits the interpreter rather than hunting for a second venv.
    Launching it with a bare `python` would instead inherit whichever
    interpreter happens to be active, and when that is the wrong one the
    failure is an ImportError deep inside an agent registry, which reads like
    an agent bug rather than an install one.

    `ISD_BENCH_PYTHON` points the subprocess at a different environment, for a
    checkout that keeps the two apart. ``bin/_matrix.sh`` honours the same
    variable, and defaults to the same place.
    """
    override = os.environ.get("ISD_BENCH_PYTHON")
    return Path(override) if override else Path(sys.executable)


def bench_packages() -> list[Path]:
    """Every editable install run_benchmark.py needs in this environment.

    Four kinds of thing, for four different reasons:

    * the benchmark root installs no importable module at all
      (``py-modules = []``) -- it is there for its dependency list;
    * the seven agents are seven separate distributions, which
      ``_get_agent_runner`` imports by class;
    * ``alignmentgraph-isd`` is what the adapter agent depends on, and is the
      thesis contribution itself;
    * ``isd-evaluator`` is the console script the benchmark runs as a
      subprocess of its own, and that ``audit repair`` imports.

    Discovered from the agents directory rather than listed, so adding an agent
    is a directory and not also an edit here.
    """
    root = paths.bench_root()
    agents = sorted(p for p in (root / "agents").iterdir()
                    if (p / "pyproject.toml").exists())
    return [root, paths.harness_root(), root / "evaluator", *agents]


def dist_name(package: Path) -> str:
    """The distribution a source directory installs as.

    Read from the directory's own pyproject rather than derived from its name,
    because for one agent the two differ: ``agents/alignmentgraph-isd``
    installs as ``alignmentgraph-isd-agent``, beside the top-level
    ``alignmentgraph-isd`` it depends on.
    """
    with (package / "pyproject.toml").open("rb") as fh:
        return tomllib.load(fh)["project"]["name"]


def missing_packages() -> list[Path]:
    """Which of :func:`bench_packages` this environment does not have.

    By DISTRIBUTION rather than by import: the benchmark root exposes no module
    to import, and an agent that imports cleanly from a stale sys.path entry
    would answer for an install that is no longer there.
    """
    absent = []
    for package in bench_packages():
        try:
            metadata.distribution(dist_name(package))
        except metadata.PackageNotFoundError:
            absent.append(package)
    return absent


def install_packages(packages: Sequence[Path]) -> int:
    """Install them editable, into the environment this process is running in.

    ``sys.executable -m pip`` rather than a `pip` off PATH, for the reason
    ``paths.pip`` spells out: the shell the reader is standing in is often not
    the environment the code runs in, and an install into the wrong one changes
    nothing and reports success.
    """
    cmd = [sys.executable, "-m", "pip", "install"]
    for package in packages:
        cmd += ["-e", str(package)]
    return subprocess.call(cmd)


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

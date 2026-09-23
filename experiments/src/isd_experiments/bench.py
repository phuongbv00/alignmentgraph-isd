"""The seam to the benchmark submodule.

Dependency direction is one-way and enforced: this package imports the
benchmark, and nothing in isd-agent-benchmark/ or alignmentgraph-isd/ may
import isd_experiments. ``tests/test_architecture.py`` is the guard.

Only the benchmark's COMPONENTS are used, never its entry point: the six
baseline agents, ``shared`` (the model configuration every agent is built
from), the scenarios and the evaluator. Each is an installed package imported
normally, and ``isd-evaluator`` is a console script run as a subprocess. The
orchestration -- what runs, under which model, into which directory -- is
this package's own (``runner/``).
"""

from __future__ import annotations

import importlib.metadata as metadata
import os
import shutil
import subprocess
import sys
import tomllib
from collections.abc import Sequence
from pathlib import Path

from . import paths


def bench_python() -> Path:
    """The interpreter every run is generated in: this one.

    ONE environment holds both sides -- isd-exp and the seven agents -- so a
    launched run inherits the interpreter rather than hunting for a second
    venv. A bare `python` would instead inherit whichever interpreter happens
    to be active, and when that is the wrong one the failure is an ImportError
    deep inside an agent registry, which reads like an agent bug rather than
    an install one.

    `ISD_BENCH_PYTHON` points a launch at a different environment.
    ``bin/_matrix.sh`` honours the same variable, and defaults to the same place.
    """
    override = os.environ.get("ISD_BENCH_PYTHON")
    return Path(override) if override else Path(sys.executable)


def bench_packages() -> list[Path]:
    """Every editable install a run needs in this environment.

    Four kinds of thing, for four different reasons:

    * the benchmark root installs ``shared``, the model configuration every
      agent imports, together with the dependencies the agents share;
    * the six baseline agents are six separate distributions, which
      ``runner.agents`` imports by class;
    * ``alignmentgraph-isd`` is the thesis contribution, which the runner's own
      adapter drives;
    * ``isd-evaluator`` is the LLM judge's console script, which `audit repair`
      also imports.

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
    because the two need not agree.
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
    """Environment for an evaluator subprocess.

    RESULTS_DIR is the one results location, the same variable this package
    reads, passed straight through rather than relayed under a second name.
    """
    env = dict(os.environ)
    env["RESULTS_DIR"] = str(paths.results_root())
    if extra:
        env.update(extra)
    return env


def evaluator_bin() -> Path:
    """The isd-evaluator console script installed WITH the agents.

    Beside the running interpreter first, PATH only as a fallback: the
    evaluator that scores a run has to be the one installed in the run's own
    environment, not whichever one a shim on PATH happens to offer.
    """
    beside = Path(sys.executable).with_name("isd-evaluator")
    if beside.exists():
        return beside
    found = shutil.which("isd-evaluator")
    if found:
        return Path(found)
    raise SystemExit(
        "isd-evaluator not found on PATH.\n"
        f"  Install it: {paths.pip()} install -e "
        f"{paths.bench_root() / 'evaluator'}"
    )

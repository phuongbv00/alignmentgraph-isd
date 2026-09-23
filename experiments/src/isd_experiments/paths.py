"""Every path this package resolves, resolved once.

The scripts this package replaces each located themselves by counting
``Path(__file__).resolve().parents[N]`` -- N being 2 or 3 depending on how deep
the file sat, under two different names for the same directory. Twenty copies of
a fragile convention, and every one of them wrong the moment a file moves. This
module is the one anchor; ``tests/test_no_sys_path_hacks.py`` asserts no other
module in the package spells ``parents[``.

Layout this assumes::

    master-thesis/                 <- thesis_root()
      experiments/                 <- exp_root()
      isd-agent-benchmark/         <- bench_root()   (git submodule)
      alignmentgraph-isd/          <- harness_root()
      EDM2022CLO/                  <- edm_root()     (git submodule)
      docs/                        <- docs_root()

Overrides, for a checkout that is laid out differently or a results volume
somewhere else:

    ISD_BENCH_ROOT          where isd-agent-benchmark lives
    RESULTS_DIR             where run dirs and generated artifacts are written
    ISD_EXPERIMENT_CONFIG   which experiment.toml to read
"""

from __future__ import annotations

import os
from pathlib import Path

#: experiments/ -- src/isd_experiments/paths.py -> up three.
EXP_ROOT = Path(__file__).resolve().parents[2]

#: The monorepo. experiments/ is a plain directory inside it, not a submodule.
THESIS_ROOT = EXP_ROOT.parent


def _env_path(name: str) -> Path | None:
    raw = os.environ.get(name)
    return Path(raw).expanduser().resolve() if raw else None


def exp_root() -> Path:
    return EXP_ROOT


def thesis_root() -> Path:
    return THESIS_ROOT


def bench_root() -> Path:
    """The benchmark submodule, validated.

    Validated rather than assumed because everything downstream -- scenarios,
    the agents, the evaluator -- hangs off it, and a wrong value here
    surfaces hundreds of lines later as a FileNotFoundError naming some leaf
    file, which says nothing about the actual cause.
    """
    root = _env_path("ISD_BENCH_ROOT") or (THESIS_ROOT / "isd-agent-benchmark")
    missing = [n for n in ("agents", "evaluator", "shared", "scenarios")
               if not (root / n).exists()]
    if missing:
        raise SystemExit(
            f"Not a benchmark checkout: {root}\n"
            f"  missing: {', '.join(missing)}\n"
            f"  Set ISD_BENCH_ROOT to the isd-agent-benchmark directory, or run\n"
            f"  `git submodule update --init` in {THESIS_ROOT}."
        )
    return root


def harness_root() -> Path:
    """The thesis contribution package (alignmentgraph-isd)."""
    return THESIS_ROOT / "alignmentgraph-isd"


def edm_root() -> Path:
    """EDM2022CLO -- the expert-labelled Bloom corpus, reference material."""
    return THESIS_ROOT / "EDM2022CLO"


def docs_root() -> Path:
    return THESIS_ROOT / "docs"


def docs_generated() -> Path:
    """Where the manuscript reads its generated tables and figures from."""
    return docs_root() / "generated"


def results_root() -> Path:
    """Run dirs, pooled JSON and generated artifacts.

    Owned by the experiment, not by the benchmark: the benchmark is a tool and
    a tool does not own the results of the study that uses it.

    ONE variable, read here and handed to every subprocess unchanged (see
    ``bench.bench_env``): a second name for one fact is a second thing to keep
    in step.
    """
    return _env_path("RESULTS_DIR") or (EXP_ROOT / "results")


def generated_dir() -> Path:
    return results_root() / "generated"


def figures_dir() -> Path:
    return generated_dir() / "figures"


def models_dir() -> Path:
    """Local model checkpoints -- the 6-way Bloom head lives here."""
    return EXP_ROOT / "models"


def env_file() -> Path:
    """Credentials, and nothing else -- endpoints are declared in the config.

    Canonically ``experiments/.env`` -- the experiment owns its configuration.
    Until that move happens, an existing benchmark-side ``.env`` is still
    honoured. Moving a credentials file is the user's to do, and the pipeline
    working from either location is better than it failing on a path.
    """
    mine = EXP_ROOT / ".env"
    if mine.exists():
        return mine
    legacy = bench_root() / ".env"
    return legacy if legacy.exists() else mine


def config_file() -> Path:
    """The declarative experiment config: ladder, serving, datasets, arms."""
    return _env_path("ISD_EXPERIMENT_CONFIG") or (EXP_ROOT / "experiment.toml")


def cli() -> str:
    """How to invoke this CLI, in a form that works right now.

    Messages that say "run X" have to name something the reader can type. The
    console script ``isd-exp`` exists only on the PATH of an environment the
    package was installed into, so on a machine that just uses the wrapper it
    is `command not found` -- which is exactly the error a helpful message
    should not produce.

    So: the bare name when it resolves, and the wrapper path otherwise.
    Checked per call rather than cached, because it is a PATH lookup and a
    message is printed rarely.
    """
    import shutil

    if shutil.which("isd-exp"):
        return "isd-exp"
    wrapper = EXP_ROOT / "isd-exp"
    if wrapper.exists():
        try:
            # Relative when the reader is standing in experiments/, absolute
            # otherwise -- either way it is something they can paste.
            rel = wrapper.relative_to(Path.cwd())
            return f"./{rel}"
        except ValueError:
            return str(wrapper)
    return "isd-exp"


def pip() -> str:
    """The pip that installs into the environment this process is running in.

    Same hazard as :func:`cli`, and it bit for the same reason: a hint saying
    ``pip install ...`` gets run in whatever shell the reader has open, which
    on a machine using the wrapper is NOT the environment the code runs in. The
    install then succeeds, changes nothing this process can see, and the same
    warning prints again -- the most confusing possible outcome, because the
    reader did exactly what they were told.

    So hints name the interpreter's own pip, resolved from ``sys.executable``.
    """
    import sys

    candidate = Path(sys.executable).with_name("pip")
    if candidate.exists():
        try:
            return f"./{candidate.relative_to(Path.cwd())}"
        except ValueError:
            return str(candidate)
    # No pip beside the interpreter (a system python, say): `-m pip` always
    # targets the right environment even when the script is absent.
    return f"{sys.executable} -m pip"


def scenarios_dir() -> Path:
    """The scenario corpus, which stays with the benchmark.

    Derived splits are written back here too, beside the splits the benchmark
    ships, so every split is found by one lookup.
    """
    return bench_root() / "scenarios"

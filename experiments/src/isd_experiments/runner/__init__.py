"""The experiment's own runner: generate, then (optionally) judge.

ISD-Agent-Bench supplies the components -- its scenarios, its six baseline
agents, its rubric and its evaluator -- and this package supplies the
orchestration. One run is one model slot x one run tag over a profile's
roster and split (:func:`execute.generate`); `isd-exp run <experiment>` fans
that out over slots and tags in tmux, and `--foreground` runs one of them here.

Judging is a separate step on a finished run (`isd-exp judge llm`, `isd-exp
judge alignment`), and ``judge`` only chains the two so a launch can do
both, scoring alignment on every arm experiment.toml declares. A judge that fails never costs the generation: the run dir is complete
either way, and the failure prints the command that finishes it.
"""

from __future__ import annotations

import sys
from pathlib import Path

from .. import paths
from ..config import current as current_config


def run_one(*, experiment: str, slot: str, tag: str, agents: list[str] | None = None,
            rate_limit: str | None = None, judge: bool = False) -> int:
    """Generate one run, and judge it when asked."""
    from . import execute

    cfg = current_config()
    run_dir = execute.generate(cfg, experiment=experiment, slot=slot, tag=tag,
                               agents=agents, rate_limit=rate_limit)
    if not judge:
        print(f"\nGenerated, not judged. Judge it with:\n"
              f"  {paths.cli()} judge llm {run_dir}\n"
              f"  {paths.cli()} judge alignment {run_dir}")
        return 0

    status = 0
    for name, score in (("llm", _judge_llm), ("alignment", _judge_alignment)):
        print(f"\n=== judge {name}: {run_dir.name}", flush=True)
        try:
            code = score(run_dir)
        except SystemExit as exc:                  # a judge refusing, with a reason
            code = exc.code if isinstance(exc.code, int) else 1
            if isinstance(exc.code, str):
                print(exc.code, file=sys.stderr)
        except Exception as exc:                   # never costs the generation
            print(f"judge {name} failed: {exc}", file=sys.stderr)
            code = 1
        if code:
            status = 1
            print(f"judge {name} did not finish; finish it with:\n"
                  f"  {paths.cli()} judge {name} {run_dir}", file=sys.stderr)
    return status


def _judge_llm(run_dir: Path) -> int:
    from ..judge import llm
    return llm.run(run_dirs=[str(run_dir)])


def _judge_alignment(run_dir: Path) -> int:
    from ..judge import alignment
    # Unattended: a tmux session is a terminal, so the overwrite prompt would
    # otherwise wait there for nobody.
    return alignment.run(run_dirs=[str(run_dir)], yes=True)

"""The LLM judge: ISD-Agent-Bench's own evaluator over finished runs.

Nothing about the scoring is ours. Every scenario is judged by one call of the
benchmark's evaluator, ``isd-evaluator compare --no-run``, over every agent that
left an output in that scenario -- the call the benchmark made after each
scenario, with the same rubric, the same multi-judge path and the roster
declared in ``[judge]``. What moved is only WHEN it runs: after generation
rather than interleaved with it, so a run can be generated once and judged,
re-judged or repaired without regenerating anything.

It writes what the benchmark wrote: ``comparison_report.json`` and
``comparison_report.md`` in each scenario dir, and the scenario's evaluation
into the run's ``benchmark_summary.json``.

The same shape as the alignment judge (:mod:`.alignment`): run dirs resolved by
:mod:`.rundirs`, the same ``agents`` filter, ``overwrite`` to re-judge what is
already judged, ``dry_run`` to print the scope and spend nothing.

A scenario is judged whenever at least one agent produced an output. The
benchmark judged only when two had, a rule for a leaderboard of several agents;
an ablation or a tuning run of one agent still needs its scores.
"""

from __future__ import annotations

import json
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path

from .. import bench, paths
from ..config import current as current_config
from ..runner import summary
from ..runner.llm import load_credentials
from . import judge_env, rundirs

REPORT = "comparison_report.json"

#: The fields a ranking row must carry for the row to count as judged. The
#: post-run audit and `audit repair` hold rows to the same list.
REQUIRED_METRICS = ("total_score", "addie_median", "trajectory_score", "phase_scores")


@dataclass(frozen=True)
class Job:
    run_dir: Path
    scenario_dir: Path
    agents: tuple[str, ...]
    #: Why this scenario is (re-)judged; None when it is already complete.
    reason: str | None


def report_gaps(scenario_dir: Path, agents: tuple[str, ...]) -> str | None:
    """Why the scenario's report does not already judge these agents, or None."""
    path = scenario_dir / REPORT
    if not path.exists():
        return "not judged"
    try:
        rankings = json.loads(path.read_text(encoding="utf-8"))["comparison"]["rankings"]
    except (json.JSONDecodeError, OSError, KeyError, TypeError) as exc:
        return f"unreadable report ({exc})"
    rows = {row.get("agent_id"): row for row in rankings}
    absent = [a for a in agents if a not in rows]
    if absent:
        return f"report lacks {', '.join(absent)}"
    incomplete = [a for a in agents
                  if any(rows[a].get(k) in (None, {}, "") for k in REQUIRED_METRICS)]
    if incomplete:
        return f"missing metrics for {', '.join(incomplete)}"
    return None


def plan(run_dirs: list[Path], only: set[str] | None, overwrite: bool,
         limit: int | None) -> list[Job]:
    jobs = []
    for run_dir in run_dirs:
        dirs = rundirs.scenario_dirs(run_dir)
        if limit is not None:
            dirs = dirs[:limit]
        for scenario_dir in dirs:
            agents = tuple(rundirs.produced_agents(scenario_dir, only))
            if not agents:
                continue
            reason = "overwrite" if overwrite else report_gaps(scenario_dir, agents)
            jobs.append(Job(run_dir, scenario_dir, agents, reason))
    return jobs


def command(scenario_file: Path, job: Job) -> list[str]:
    """The evaluator call. ``--multi-judge`` is the path the benchmark always
    took: it scores with every judge the roster declares, one or several."""
    return [str(bench.evaluator_bin()), "compare",
            "--scenario", str(scenario_file),
            "--output-dir", str(job.scenario_dir),
            "--agents", ",".join(job.agents),
            "--no-run", "--use-llm", "--multi-judge"]


def judge_one(job: Job, scenario_root: Path, env: dict[str, str]) -> tuple[Job, str | None]:
    """Judge one scenario; returns an error message, or None on success."""
    scenario_file = rundirs.scenario_path(job.scenario_dir, job.run_dir, scenario_root)
    if scenario_file is None:
        return job, f"scenario file for {job.scenario_dir.name} not found under {scenario_root}"
    done = subprocess.run(command(scenario_file, job), env=env, cwd=paths.bench_root(),
                          capture_output=True, text=True, check=False)
    if done.returncode != 0:
        tail = (done.stderr or done.stdout or "").strip().splitlines()[-3:]
        return job, f"evaluator exited {done.returncode}: {' | '.join(tail)}"
    report_path = job.scenario_dir / REPORT
    if not report_path.exists():
        return job, "evaluator wrote no comparison_report.json"
    report = json.loads(report_path.read_text(encoding="utf-8"))
    variant = job.scenario_dir.parent.name if job.scenario_dir != job.run_dir else ""
    summary.record_evaluation(job.run_dir, variant, job.scenario_dir.name, report)
    return job, None


def print_scope(jobs: list[Job]) -> None:
    pending = [j for j in jobs if j.reason]
    print(f"== LLM judge — {len(pending)} of {len(jobs)} scenario(s) to judge")
    by_run: dict[Path, list[Job]] = {}
    for job in jobs:
        by_run.setdefault(job.run_dir, []).append(job)
    for run_dir, run_jobs in by_run.items():
        todo = [j for j in run_jobs if j.reason]
        agents = sorted({a for j in run_jobs for a in j.agents})
        print(f"  {run_dir.name}: {len(todo)}/{len(run_jobs)} to judge; "
              f"agents {', '.join(agents)}")
        for job in todo[:5]:
            print(f"    - {job.scenario_dir.name}: {job.reason}")
        if len(todo) > 5:
            print(f"    ... and {len(todo) - 5} more")


def run(*, run_dirs: list[str] | tuple[str, ...] = (), agents: str = "",
        workers: int = 4, overwrite: bool = False, dry_run: bool = False,
        limit: int | None = None, scenario_root: Path | None = None) -> int:
    """Judge every unjudged scenario of the named runs with the LLM judge.

    Re-running after an interruption continues where it stopped: a scenario
    whose report already ranks every agent it holds, with every metric filled,
    is skipped. ``overwrite`` re-judges those too. A judge that answered with
    an error inside an otherwise complete report is `audit repair`'s to fix,
    one row at a time, rather than a reason to re-judge the whole scenario.
    """
    resolved = rundirs.resolve(run_dirs)
    scenario_root = (scenario_root or paths.scenarios_dir()).resolve()
    jobs = plan(resolved, rundirs.agent_filter(agents), overwrite, limit)
    print_scope(jobs)
    pending = [j for j in jobs if j.reason]
    if dry_run or not pending:
        if not dry_run:
            print("Nothing to judge.")
        return 0

    load_credentials()
    env = bench.bench_env(judge_env(current_config().judge))
    failures: list[tuple[Job, str]] = []
    with ThreadPoolExecutor(max_workers=max(1, workers)) as pool:
        futures = [pool.submit(judge_one, job, scenario_root, env) for job in pending]
        for n, future in enumerate(as_completed(futures), 1):
            job, error = future.result()
            # Words, not the ✅/❌ a generation line carries: `audit inflight`
            # counts those in the slot log, and a chained judge writes there too.
            mark = "FAILED" if error else "judged"
            print(f"  [{n}/{len(pending)}] {mark} {job.run_dir.name}/{job.scenario_dir.name}"
                  + (f": {error}" if error else ""), flush=True)
            if error:
                failures.append((job, error))

    print(f"\nJudged {len(pending) - len(failures)} of {len(pending)} scenario(s).")
    if failures:
        print(f"{len(failures)} failed; re-run the same command to retry them.",
              file=sys.stderr)
        return 1
    return 0

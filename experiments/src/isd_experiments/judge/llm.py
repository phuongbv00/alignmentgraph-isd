"""The LLM judge: ISD-Agent-Bench's own evaluator over finished runs.

Nothing about the scoring is ours. Every scenario is judged by one call of the
benchmark's evaluator, ``isd-evaluator compare --no-run``, over every agent that
left an output in that scenario -- the call the benchmark made after each
scenario, with the same rubric, the same multi-judge path and the roster
declared in ``[judge.llm]``. What moved is only WHEN it runs: after generation
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
import threading
from collections import Counter
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


#: What every LLM judge must have returned for a row to count as judged.
JUDGE_METRICS = ("addie_score", "trajectory_score")


def report_gaps(scenario_dir: Path, agents: tuple[str, ...],
                roster: tuple[str, ...] = ()) -> str | None:
    """Why the scenario's report does not already judge these agents, or None.

    ``roster`` is the declared LLM judge models. A row scored by any other set
    of models is not judged: kept, it would be pooled beside rows scored by the
    declared roster, and the median of two judges is not the median of three.
    """
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
    for agent in agents:
        # A judge that errored (a refused or failed call) leaves the row scored
        # by the others alone, under the same roster names: MEASURED (run t1
        # 20261012_090924), a router out of credit answered 402 mid-run, and
        # four rows carried a trajectory score from one or two judges of three
        # while their ADDIE score had all three.
        failed = sorted({str(j.get("model")) for j in rows[agent].get("judges") or []
                         if j.get("error") or any(j.get(k) is None for k in JUDGE_METRICS)})
        if failed:
            return f"LLM judge failed for {agent} ({', '.join(failed)})"
    if roster:
        for agent in agents:
            models = [str(j.get("model")) for j in rows[agent].get("judges") or []]
            if Counter(models) != Counter(roster):
                return (f"judged by another LLM judge roster "
                        f"({', '.join(sorted(models)) or 'none recorded'})")
    return None


def plan(run_dirs: list[Path], only: set[str] | None, overwrite: bool,
         limit: int | None, roster: tuple[str, ...] = ()) -> list[Job]:
    jobs = []
    for run_dir in run_dirs:
        dirs = rundirs.scenario_dirs(run_dir)
        if limit is not None:
            dirs = dirs[:limit]
        for scenario_dir in dirs:
            agents = tuple(rundirs.produced_agents(scenario_dir, only))
            if not agents:
                continue
            reason = ("overwrite" if overwrite
                      else report_gaps(scenario_dir, agents, roster))
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


#: The evaluator prints one line per finished LLM judge call when this is set:
#: ``__EVAL_PROGRESS__ <done> <total> <agent_id> <judge_model>``.
PROGRESS_ENV = "ISD_EVAL_PROGRESS"
PROGRESS_MARK = "__EVAL_PROGRESS__"


def progress_line(scenario: str, line: str) -> str | None:
    """A progress marker as a log line, or None for any other output."""
    if not line.startswith(PROGRESS_MARK):
        return None
    parts = line.rstrip("\n").split("\t")
    if len(parts) < 3:
        return None
    detail = f" -- {parts[3]} / {parts[4]}" if len(parts) > 4 else ""
    return f"  [{scenario}] LLM judge call {parts[1]}/{parts[2]}{detail}"


def evaluate(cmd: list[str], env: dict[str, str], scenario: str) -> tuple[int, str]:
    """Run the evaluator, echoing its progress as it goes.

    Streamed rather than captured: one scenario is several LLM judge calls, and
    captured output leaves the log silent for minutes, which reads as a hang.
    Everything that is not a progress marker is kept for the error message.
    """
    proc = subprocess.Popen(cmd, env={**env, PROGRESS_ENV: "1"}, cwd=paths.bench_root(),
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    errors: list[str] = []
    # Drained on its own thread, or a full stderr pipe blocks the child while
    # this thread waits on stdout.
    drain = threading.Thread(target=lambda: errors.extend(proc.stderr), daemon=True)
    drain.start()
    other: list[str] = []
    for line in proc.stdout:
        shown = progress_line(scenario, line)
        if shown is not None:
            print(shown, flush=True)
        else:
            other.append(line)
    code = proc.wait()
    drain.join()
    return code, "".join(errors) or "".join(other)


def judge_one(job: Job, scenario_root: Path, env: dict[str, str]) -> tuple[Job, str | None]:
    """Judge one scenario; returns an error message, or None on success."""
    scenario_file = rundirs.scenario_path(job.scenario_dir, job.run_dir, scenario_root)
    if scenario_file is None:
        return job, f"scenario file for {job.scenario_dir.name} not found under {scenario_root}"
    print(f"  [{job.scenario_dir.name}] judging {', '.join(job.agents)}", flush=True)
    code, output = evaluate(command(scenario_file, job), env, job.scenario_dir.name)
    if code != 0:
        tail = output.strip().splitlines()[-3:]
        return job, f"evaluator exited {code}: {' | '.join(tail)}"
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
    roster = tuple(m.name for m in current_config().judge.models)
    jobs = plan(resolved, rundirs.agent_filter(agents), overwrite, limit, roster)
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

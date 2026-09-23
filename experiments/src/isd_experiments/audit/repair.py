#!/usr/bin/env python3
"""Repair transient multi-LLM-judge failures without rerunning agent generation.

The evaluator's ``compare --agents AGENT`` command rewrites the complete
``comparison_report`` with only the selected agent.  This script therefore
evaluates each affected agent in a temporary directory, validates the result,
and merges only that repaired ranking row back into the original report.

It also keeps the run-level ``benchmark_summary.json`` / ``SUMMARY.md`` in
sync, creates one-time ``.pre-llm-judge-repair`` backups, and runs the post-run
audit when finished.

The LLM judge roster comes from the experiment declaration, so a repaired row
is scored by the same judges as the run it is merged back into -- a different
roster is what ``validate_repaired_entry`` rejects.

Usage:
  # Inspect the repair scope; no LLM judge calls and no writes.
  ./isd-exp audit repair --dry-run

  # Repair every ladder run found by the default glob, then audit.
  ./isd-exp audit repair

  # Non-interactive use with an explicit set of run dirs.
  ./isd-exp audit repair --yes \
      'results/test_90_benchmark_<model>_r[123]_*'

The evaluator is always invoked with ``--no-run --multi-judge``.  Existing
agent output and trajectory files are read but never regenerated.
"""
from __future__ import annotations

import copy
import glob
import json
import shutil
import subprocess
import sys
import tempfile
from collections import Counter
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from .. import bench, paths
from ..config import current as current_config
from ..judge import judge_env
from ..runner import summary as run_summary

DEFAULT_RUN_GLOB = "results/test_90_benchmark_*_r*"
DEFAULT_BACKUP_SUFFIX = ".pre-llm-judge-repair"
REQUIRED_METRICS = (
    "total_score",
    "addie_median",
    "trajectory_score",
    "phase_scores",
)


@dataclass(frozen=True)
class RepairTarget:
    """One agent ranking whose stored LLM judge evaluation is incomplete."""

    run_dir: Path
    variant: str
    scenario_id: str
    scenario_dir: Path
    report_path: Path
    agent_id: str
    llm_judge_error_count: int
    missing_metrics: tuple[str, ...]


def read_json(path: Path) -> dict[str, Any]:
    """Read one UTF-8 JSON object."""
    return json.loads(path.read_text(encoding="utf-8"))


def write_json_atomic(path: Path, payload: dict[str, Any]) -> None:
    """Replace a JSON file only after its complete replacement is on disk."""
    write_text_atomic(
        path,
        json.dumps(payload, ensure_ascii=False, indent=2, default=str),
    )


def write_text_atomic(path: Path, content: str) -> None:
    """Replace a text file only after its complete replacement is on disk."""
    temp_path = path.with_name(f".{path.name}.repair-tmp")
    temp_path.write_text(content, encoding="utf-8")
    temp_path.replace(path)


def backup_once(path: Path, suffix: str) -> Path | None:
    """Keep the first pre-repair version; never overwrite that evidence."""
    if not path.exists():
        return None
    backup = path.with_name(f"{path.stem}{suffix}{path.suffix}")
    if not backup.exists():
        shutil.copy2(path, backup)
    return backup


def resolve_run_dirs(patterns: list[str]) -> list[Path]:
    """Expand quoted globs and explicit run directories, preserving order."""
    raw_patterns = patterns or [DEFAULT_RUN_GLOB]
    resolved: list[Path] = []
    seen: set[Path] = set()
    for pattern in raw_patterns:
        absolute_pattern = (
            pattern if Path(pattern).is_absolute() else str(paths.exp_root() / pattern)
        )
        for match in sorted(glob.glob(absolute_pattern)):
            path = Path(match).resolve()
            if path.is_dir() and path not in seen:
                resolved.append(path)
                seen.add(path)
    return resolved


def missing_metrics(row: dict[str, Any]) -> tuple[str, ...]:
    """Return metric fields that the post-run audit treats as missing."""
    return tuple(
        key for key in REQUIRED_METRICS if row.get(key) in (None, {}, "")
    )


def discover_targets(run_dirs: list[Path]) -> list[RepairTarget]:
    """Find ranking rows containing at least one LLM judge error."""
    targets: list[RepairTarget] = []
    for run_dir in run_dirs:
        for report_path in sorted(run_dir.glob("*/*/comparison_report.json")):
            scenario_dir = report_path.parent
            variant = scenario_dir.parent.name
            report = read_json(report_path)
            rankings = report.get("comparison", {}).get("rankings", [])
            for row in rankings:
                error_count = sum(
                    1 for j in row.get("judges", []) if j.get("error")
                )
                if not error_count:
                    continue
                targets.append(
                    RepairTarget(
                        run_dir=run_dir,
                        variant=variant,
                        scenario_id=scenario_dir.name,
                        scenario_dir=scenario_dir,
                        report_path=report_path,
                        agent_id=str(row.get("agent_id", "unknown")),
                        llm_judge_error_count=error_count,
                        missing_metrics=missing_metrics(row),
                    )
                )
    return targets


def llm_judge_signature(row: dict[str, Any]) -> list[tuple[Any, Any]]:
    """Return LLM judge identities in their recorded completion order."""
    return [
        (j.get("provider"), j.get("model"))
        for j in row.get("judges", [])
    ]


def validate_repaired_entry(
    old_entry: dict[str, Any],
    new_entry: dict[str, Any],
) -> list[str]:
    """Return validation errors for a newly evaluated ranking row."""
    errors: list[str] = []
    if new_entry.get("agent_id") != old_entry.get("agent_id"):
        errors.append(
            f"agent mismatch: {old_entry.get('agent_id')} -> "
            f"{new_entry.get('agent_id')}"
        )
    old_roster = Counter(llm_judge_signature(old_entry))
    new_roster = Counter(llm_judge_signature(new_entry))
    if new_roster != old_roster:
        errors.append(
            f"LLM judge roster changed: {llm_judge_signature(old_entry)} -> "
            f"{llm_judge_signature(new_entry)}"
        )
    failed_llm_judges = [
        j for j in new_entry.get("judges", [])
        if j.get("error") or j.get("addie_score") is None
    ]
    if failed_llm_judges:
        errors.append(f"{len(failed_llm_judges)} LLM judge(s) still failed")
    missing = missing_metrics(new_entry)
    if missing:
        errors.append(f"missing metrics: {', '.join(missing)}")
    return errors


def merge_repaired_entry(
    report: dict[str, Any],
    repaired_entry: dict[str, Any],
) -> dict[str, Any]:
    """Replace one agent row, then restore ranking and best-agent metadata."""
    merged = copy.deepcopy(report)
    rankings = merged["comparison"]["rankings"]
    agent_id = repaired_entry["agent_id"]
    matches = [
        index for index, row in enumerate(rankings)
        if row.get("agent_id") == agent_id
    ]
    if len(matches) != 1:
        raise ValueError(
            f"expected one ranking row for {agent_id}, found {len(matches)}"
        )
    rankings[matches[0]] = repaired_entry
    rankings.sort(
        key=lambda row: (
            row.get("total_score")
            if row.get("total_score") is not None
            else float("-inf")
        ),
        reverse=True,
    )
    for rank, row in enumerate(rankings, 1):
        row["rank"] = rank
    merged["comparison"]["rankings"] = rankings
    merged["comparison"]["best_agent"] = rankings[0]["agent_id"]
    merged["generated_at"] = datetime.now().isoformat()
    return merged


def evaluate_target(
    target: RepairTarget,
    original_report: dict[str, Any],
    evaluator_bin: Path,
    max_attempts: int,
    verbose: bool,
) -> dict[str, Any]:
    """Evaluate one affected agent in isolation and return its clean row."""
    old_rows = [
        row for row in original_report["comparison"]["rankings"]
        if row.get("agent_id") == target.agent_id
    ]
    if len(old_rows) != 1:
        raise ValueError(
            f"{target.report_path}: expected one {target.agent_id} row"
        )
    old_entry = old_rows[0]
    output_path = target.scenario_dir / f"{target.agent_id}_output.json"
    trajectory_path = (
        target.scenario_dir / f"{target.agent_id}_trajectory.json"
    )
    if not output_path.exists():
        raise FileNotFoundError(f"missing agent output: {output_path}")
    scenario = original_report.get("scenario")
    if not isinstance(scenario, dict):
        raise ValueError(f"missing embedded scenario: {target.report_path}")

    last_errors: list[str] = []
    with tempfile.TemporaryDirectory(prefix="isd-llm-judge-repair-") as temp:
        temp_dir = Path(temp)
        shutil.copy2(output_path, temp_dir / output_path.name)
        if trajectory_path.exists():
            shutil.copy2(trajectory_path, temp_dir / trajectory_path.name)
        scenario_path = temp_dir / f"{target.scenario_id}.json"
        write_json_atomic(scenario_path, scenario)

        command = [
            str(evaluator_bin),
            "compare",
            "--scenario",
            str(scenario_path),
            "--output-dir",
            str(temp_dir),
            "--agents",
            target.agent_id,
            "--no-run",
            "--use-llm",
            "--multi-judge",
        ]
        if verbose:
            command.append("--verbose")

        for attempt in range(1, max_attempts + 1):
            print(f"    LLM judge attempt {attempt}/{max_attempts}", flush=True)
            # The declared roster, or nothing when none is declared. A re-judge
            # scored by a different roster than the original run is rejected by
            # validate_repaired_entry, so it has to be named here rather than
            # left to whatever the ambient environment happens to carry.
            completed = subprocess.run(
                command, cwd=paths.bench_root(), check=False,
                env=bench.bench_env(judge_env(current_config().judge)),
            )
            temp_report_path = temp_dir / "comparison_report.json"
            if completed.returncode != 0:
                last_errors = [
                    f"evaluator exited with code {completed.returncode}"
                ]
                continue
            if not temp_report_path.exists():
                last_errors = ["evaluator did not write comparison_report.json"]
                continue
            temp_report = read_json(temp_report_path)
            rows = temp_report.get("comparison", {}).get("rankings", [])
            if len(rows) != 1:
                last_errors = [
                    f"temporary report contains {len(rows)} ranking rows"
                ]
                continue
            last_errors = validate_repaired_entry(old_entry, rows[0])
            if not last_errors:
                return rows[0]
            print(f"    retry: {'; '.join(last_errors)}", flush=True)

    raise RuntimeError(
        f"no clean evaluation after {max_attempts} attempt(s): "
        f"{'; '.join(last_errors) or 'unknown evaluator failure'}"
    )


def sync_reports(
    target: RepairTarget,
    merged_report: dict[str, Any],
    backup_suffix: str,
    reporter,
) -> None:
    """Write scenario and run-level reports from one merged evaluation."""
    scenario_md = target.scenario_dir / "comparison_report.md"
    scenario_markdown = reporter.generate_markdown(
        merged_report["comparison"],
        merged_report["scenario"],
    )

    summary_path = target.run_dir / "benchmark_summary.json"
    summary_md = target.run_dir / "SUMMARY.md"
    summary: dict[str, Any] | None = None
    summary_markdown: str | None = None
    if summary_path.exists():
        summary = read_json(summary_path)
        scenario_slot = (
            summary.get("scenarios", {})
            .get(target.variant, {})
            .get(target.scenario_id)
        )
        if not isinstance(scenario_slot, dict):
            raise KeyError(
                f"{summary_path}: no "
                f"scenarios/{target.variant}/{target.scenario_id}"
            )
        scenario_slot["evaluation"] = merged_report
        scenario_slot.pop("evaluation_deferred", None)
        summary_markdown = run_summary.render_markdown(summary)
    else:
        print(
            f"    warning: {summary_path} is missing; scenario report repaired "
            "but run summary could not be synchronized",
            flush=True,
        )

    # Everything above is validation/rendering only. Start mutating the run
    # after every replacement artifact has been prepared successfully.
    backup_once(target.report_path, backup_suffix)
    backup_once(scenario_md, backup_suffix)
    write_json_atomic(target.report_path, merged_report)
    write_text_atomic(scenario_md, scenario_markdown)
    if summary is None or summary_markdown is None:
        return
    backup_once(summary_path, backup_suffix)
    backup_once(summary_md, backup_suffix)
    write_json_atomic(summary_path, summary)
    write_text_atomic(summary_md, summary_markdown)


def run_postrun_audit(run_dirs: list[Path]) -> int:
    """Run the canonical audit over exactly the repaired input run dirs."""
    from . import postrun
    print("\nRunning post-run audit...", flush=True)
    return postrun.run(run_dirs=run_dirs)


def print_scope(targets: list[RepairTarget]) -> None:
    """Print a concise, deterministic repair manifest."""
    llm_judge_errors = sum(target.llm_judge_error_count for target in targets)
    missing_count = sum(len(target.missing_metrics) for target in targets)
    print(
        f"Repair scope: {len(targets)} agent×scenario entries, "
        f"{llm_judge_errors} errored LLM judge records, "
        f"{missing_count} missing metric fields."
    )
    print(
        "Note: post-run audit counts RED findings per run/category; "
        "that total is not the number of repair targets."
    )
    for target in targets:
        missing = (
            f"; missing={','.join(target.missing_metrics)}"
            if target.missing_metrics
            else ""
        )
        print(
            f"  {target.run_dir.name}/{target.variant}/"
            f"{target.scenario_id}: {target.agent_id} "
            f"({target.llm_judge_error_count} LLM judge error(s){missing})"
        )


def run(*, run_dirs: list[str] | None = None, dry_run: bool = False,
        yes: bool = False, max_attempts: int = 3,
        backup_suffix: str = DEFAULT_BACKUP_SUFFIX,
        skip_audit: bool = False, verbose: bool = False) -> int:
    """Re-judge the cells a transient LLM judge failure cost, and nothing else.

    The order is fixed by what is recoverable. Scope is printed before anything
    is judged, because a repair that turns out to be larger than expected is a
    signal about the run rather than work to get on with. Each entry is then
    evaluated in isolation, merged, and written -- the evaluator rewrites a
    whole report with only the agent it was given, so the merge is the step that
    keeps the other agents' rows. A failure stops that entry and leaves the run
    as it was; the ones already repaired stay repaired, and re-running skips
    them because they no longer carry an error.
    """
    from isd_evaluator.reporters import ComparisonReporter

    if max_attempts < 1:
        raise SystemExit("max-attempts must be >= 1")
    if not backup_suffix:
        raise SystemExit("backup-suffix must not be empty")

    resolved = resolve_run_dirs(list(run_dirs or []))
    targets = discover_targets(resolved)
    print_scope(targets)
    if not targets:
        print("Nothing to repair.")
        return 0
    if dry_run:
        print("\n--dry-run: no LLM judge calls, nothing written.")
        return 0

    # Every entry costs real LLM judge calls, so the scope above is shown first
    # and this asks against it.
    if not yes and sys.stdin.isatty():
        if input(f"Re-judge {len(targets)} entr(y/ies)? [y/N] ").strip().lower() != "y":
            print("Aborted. Nothing written.")
            return 1

    reporter = ComparisonReporter()
    binary = bench.evaluator_bin()
    repaired = 0
    failures: list[str] = []
    for index, target in enumerate(targets, 1):
        label = (f"{target.run_dir.name}/{target.variant}/"
                 f"{target.scenario_id}: {target.agent_id}")
        print(f"\n[{index}/{len(targets)}] {label}", flush=True)
        report = read_json(target.report_path)
        try:
            entry = evaluate_target(target, report, binary, max_attempts, verbose)
            merged = merge_repaired_entry(report, entry)
            validate_repaired_entry(report, merged, target)
            sync_reports(target, merged, backup_suffix, reporter)
        except Exception as exc:                      # noqa: BLE001 - reported, not swallowed
            print(f"    FAILED: {exc}", flush=True)
            failures.append(f"{label}: {exc}")
            continue
        repaired += 1
        print("    repaired", flush=True)

    print(f"\nRepaired {repaired}/{len(targets)} entr(y/ies).")
    for failure in failures:
        print(f"  ! {failure}")

    # The audit reads what was just written, so a partial repair is still worth
    # auditing -- its findings are how the remaining damage is counted.
    audit_status = 0 if skip_audit else run_postrun_audit(resolved)
    return 1 if failures else audit_status

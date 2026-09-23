"""The run-level record: ``benchmark_summary.json`` and its ``SUMMARY.md``.

The JSON keeps the shape the benchmark wrote (``scenarios[<dataset>][<scenario>]``
with each agent's outcome and, once judged, the scenario's ``evaluation``),
because pooling and the audits already read it in that shape. The runner writes
it once generation finishes; `judge llm` and `audit repair` write each
scenario's evaluation into it as they produce one.
"""

from __future__ import annotations

import json
import os
import tempfile
import threading
from pathlib import Path
from typing import Any

SUMMARY_JSON = "benchmark_summary.json"
SUMMARY_MD = "SUMMARY.md"

#: Several scenarios are judged at once; each write is read-modify-write of one
#: file, so they are serialized per process.
_LOCK = threading.Lock()


def write_json_atomic(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, ensure_ascii=False, indent=2, default=str)
        fh.write("\n")
    os.replace(tmp, path)


def write_text_atomic(path: Path, text: str) -> None:
    fd, tmp = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        fh.write(text)
    os.replace(tmp, path)


def render_markdown(results: dict) -> str:
    """The human-readable summary of a run, judged or not."""
    config = results.get("config", {})
    lines = [
        "# ISD Agent Benchmark results summary",
        "",
        f"Run time: {results.get('timestamp', '')}",
        "",
        "## Configuration",
        f"- Variant: {', '.join(config.get('variants', []))}",
        f"- Agent: {', '.join(config.get('agents', []))}",
        "",
        "## Results summary",
        "",
    ]

    total_scenarios = 0
    agent_stats: dict[str, dict[str, int]] = {}

    for variant, scenarios in results.get("scenarios", {}).items():
        lines.append(f"### {variant.upper()}")
        lines.append("")

        for scenario_id, scenario_result in scenarios.items():
            total_scenarios += 1
            lines.append(f"#### {scenario_id}")
            lines.append("")

            for agent_id, agent_result in scenario_result.get("agents", {}).items():
                stats = agent_stats.setdefault(agent_id, {"success": 0, "failed": 0})
                if agent_result.get("success"):
                    stats["success"] += 1
                    status = "success"
                else:
                    stats["failed"] += 1
                    status = f"failed: {agent_result.get('error', 'Unknown')[:50]}"
                lines.append(f"- {agent_id}: {status}")

            if "evaluation" in scenario_result:
                rankings = sorted(
                    scenario_result["evaluation"].get("comparison", {}).get("rankings", []),
                    key=lambda row: row.get("rank", 999),
                )
                lines.append("")
                lines.append("**Evaluation scores:**")
                for row in rankings:
                    score = f"{row.get('total_score', 0):.1f}/100"
                    if row.get("process_score") is not None:
                        score += f" (process: {row['process_score']:.1f})"
                    lines.append(f"- {row.get('agent_id', 'unknown')}: {score}")
            elif scenario_result.get("evaluation_deferred"):
                lines.append("")
                lines.append("**Evaluation:** not judged yet")

            lines.append("")

    lines.append("## Agent statistics")
    lines.append("")
    lines.append("| Agent | Success | Failed | Success rate |")
    lines.append("|-------|---------|--------|--------------|")
    for agent_id, stats in agent_stats.items():
        total = stats["success"] + stats["failed"]
        rate = (stats["success"] / total * 100) if total else 0
        lines.append(f"| {agent_id} | {stats['success']} | {stats['failed']} | {rate:.1f}% |")

    lines.append("")
    lines.append("---")
    lines.append(f"Total scenarios: {total_scenarios}")
    return "\n".join(lines)


def write(run_dir: Path, results: dict) -> None:
    write_json_atomic(run_dir / SUMMARY_JSON, results)
    write_text_atomic(run_dir / SUMMARY_MD, render_markdown(results))


def read(run_dir: Path) -> dict | None:
    path = run_dir / SUMMARY_JSON
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def record_evaluation(run_dir: Path, variant: str, scenario_id: str,
                      report: dict) -> bool:
    """File one scenario's LLM judge report into the run summary.

    Returns False when the run has no summary or the summary has no slot for
    this scenario -- the scenario's own ``comparison_report.json`` is still the
    record then, and pooling reads that.
    """
    with _LOCK:
        results = read(run_dir)
        if results is None:
            return False
        slot = results.get("scenarios", {}).get(variant, {}).get(scenario_id)
        if not isinstance(slot, dict):
            return False
        slot["evaluation"] = report
        slot.pop("evaluation_deferred", None)
        write(run_dir, results)
        return True

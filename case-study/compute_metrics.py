"""Compute the RQ2 process metrics from case-study run artifacts (4 conditions).

Reads ``results/manifest.json``, per-session result JSONs, committed graph
versions (harness conditions), and — when present — judge scores produced by
``score_alignment.py`` under ``results/scores/``. Writes ``results/metrics.csv``
and ``results/metrics.md``. Network-free.

Metrics per refinement round:

1. cascade_scope       stale set / nodes in the base graph version — harness
                       conditions only (react has no graph).
2. edit locality       two instruments:
                       - ``output_locality`` (ALL conditions): changed
                         addie_output subsections / total, via sha256 of each
                         phase's top-level keys between consecutive rounds of
                         the same chain;
                       - ``graph_locality`` (harness only): changed graph nodes
                         between committed versions (plus ``touched_locality``
                         from ``node_edits``).
3. cost per round      prompt/completion tokens, llm_calls, latency — unified
                       across the harness trajectory format and the react
                       metadata format; ratios vs the same chain's init round.
4. alignment           - harness: audit coverage (measures/supports/evaluates),
     preservation        residual verifier violations (internal instrument);
                       - ALL conditions: evaluator ADDIE score + Design
                         alignment item (D1) merged from ``results/scores/``
                         (shared cross-agent instrument).
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
from pathlib import Path

CASE_STUDY_DIR = Path(__file__).resolve().parent
HARNESS_CONDITIONS = ("harness_targeted_refine", "harness_full_regen")


# ── Shared hashing helpers ─────────────────────────────────────────────────────

def _sha(payload) -> str:
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, ensure_ascii=False).encode("utf-8")
    ).hexdigest()


def output_subsection_hashes(addie_output: dict) -> dict[str, str]:
    """Fingerprint every phase.sub_key of an ADDIE output (schema shared by all agents)."""
    hashes: dict[str, str] = {}
    for phase, section in (addie_output or {}).items():
        if isinstance(section, dict) and section:
            for key, value in section.items():
                hashes[f"{phase}.{key}"] = _sha(value)
        else:
            hashes[phase] = _sha(section)
    return hashes


def diff_hashes(before: dict[str, str], after: dict[str, str]) -> dict:
    changed = sorted(k for k, h in after.items() if before.get(k) != h)
    return {
        "changed": changed,
        "unchanged": sorted(k for k, h in after.items() if before.get(k) == h),
        "removed": sorted(set(before) - set(after)),
        "total_after": len(after),
    }


# ── Graph version access (harness conditions) ──────────────────────────────────

def load_graph_version(memory_dir: Path, storage_id: str, version: int) -> dict:
    path = memory_dir / "programs" / storage_id / "graph_versions" / f"alignment_graph_v{version:04d}.json"
    return json.loads(path.read_text(encoding="utf-8"))["graph"]


def graph_node_hashes(graph: dict) -> dict[str, str]:
    return {node["id"]: _sha(node.get("data", {})) for node in graph["nodes"]}


# ── Per-session readings ───────────────────────────────────────────────────────

def audit_coverage(audit: dict) -> dict:
    count = audit.get("objective_count", 0) or 0

    def coverage(key: str) -> float | None:
        if not count:
            return None
        return round(1 - len(audit.get(key, [])) / count, 4)

    return {
        "coverage_measures": coverage("unmeasured_objectives"),
        "coverage_supports": coverage("unsupported_objectives"),
        "coverage_evaluates": coverage("unevaluated_objectives"),
        "ready_to_aggregate": audit.get("ready_to_aggregate"),
    }


def session_cost(result: dict) -> dict:
    """Unified cost extraction across the two result formats."""
    trajectory = result.get("trajectory", {})
    metadata = result.get("metadata", {})
    if "token_usage" in trajectory:  # harness format
        tokens = trajectory.get("token_usage", {})
        return {
            "prompt_tokens": tokens.get("prompt_tokens", 0),
            "completion_tokens": tokens.get("completion_tokens", 0),
            "total_tokens": tokens.get("prompt_tokens", 0) + tokens.get("completion_tokens", 0),
            "llm_calls": trajectory.get("llm_calls", 0),
            "latency_ms": round(trajectory.get("latency_ms", 0.0), 1),
        }
    tokens = metadata.get("token_usage", {})  # react format
    return {
        "prompt_tokens": tokens.get("prompt_tokens", 0),
        "completion_tokens": tokens.get("completion_tokens", 0),
        "total_tokens": metadata.get("total_tokens", 0),
        "llm_calls": metadata.get("llm_calls", 0),
        "latency_ms": round(metadata.get("execution_time_seconds", 0.0) * 1000, 1),
    }


def refinement_cascade_event(result: dict) -> dict | None:
    events = [
        e for e in result.get("trajectory", {}).get("cascade_events", [])
        if e.get("reason", "").startswith("refinement_request:")
    ]
    return events[0] if events else None


def judge_scores(case_study_dir: Path, entry: dict) -> dict:
    """Merge evaluator scores written by score_alignment.py, if any."""
    path = case_study_dir / "results" / "scores" / entry["condition"] / entry["program_id"] / f"session_{entry['round']:02d}.json"
    if not path.exists():
        return {}
    payload = json.loads(path.read_text(encoding="utf-8"))
    return {
        "judge_addie_score": payload.get("addie_score"),
        "judge_alignment_item": payload.get("alignment_item_score"),
    }


# ── Metric assembly ────────────────────────────────────────────────────────────

def compute_rows(case_study_dir: Path) -> list[dict]:
    memory_dir = case_study_dir / "memory"
    manifest = json.loads((case_study_dir / "results" / "manifest.json").read_text(encoding="utf-8"))
    sessions = {(m["condition"], m["program_id"], m["round"]): m for m in manifest}

    def result_of(entry: dict) -> dict:
        return json.loads((case_study_dir / entry["result_file"]).read_text(encoding="utf-8"))

    rows: list[dict] = []
    for entry in manifest:
        condition, pid, k = entry["condition"], entry["program_id"], entry["round"]
        result = result_of(entry)
        metadata = result.get("metadata", {})
        row: dict = {
            "program": pid,
            "condition": condition,
            "round": k,
            "refinement_id": "",
            **session_cost(result),
            **judge_scores(case_study_dir, entry),
            "residual_violations": len(metadata.get("violations", [])) if condition in HARNESS_CONDITIONS else None,
        }
        if condition in HARNESS_CONDITIONS:
            row.update(audit_coverage(metadata.get("audit", {})))

        init_entry = sessions.get((condition, pid, 0))
        if init_entry:
            init_cost = session_cost(result_of(init_entry))
            if init_cost["total_tokens"]:
                row["token_ratio_vs_init"] = round(row["total_tokens"] / init_cost["total_tokens"], 3)
            if init_cost["latency_ms"]:
                row["latency_ratio_vs_init"] = round(row["latency_ms"] / init_cost["latency_ms"], 3)

        if k == 0:
            rows.append(row)
            continue

        # Output-level locality: shared instrument across all four conditions.
        prev_entry = sessions.get((condition, pid, k - 1))
        if prev_entry:
            before_out = output_subsection_hashes(result_of(prev_entry).get("addie_output", {}))
            after_out = output_subsection_hashes(result.get("addie_output", {}))
            diff = diff_hashes(before_out, after_out)
            row["output_locality"] = round(len(diff["changed"]) / diff["total_after"], 4) if diff["total_after"] else None
            row["output_changed_subsections"] = diff["changed"]
        if entry.get("unchanged_phases") is not None and condition == "react_targeted_refine":
            row["unchanged_phases"] = entry.get("unchanged_phases", [])

        # Graph-level instruments: harness conditions only.
        if condition in HARNESS_CONDITIONS:
            before = load_graph_version(memory_dir, entry["storage_id"], entry["base_graph_version"])
            after = load_graph_version(memory_dir, entry["storage_id"], entry["committed_graph_version"])
            event = refinement_cascade_event(result)
            row["refinement_id"] = (event["reason"].split(":", 2)[1].strip() if event else "")
            row["cascade_scope"] = round(event["node_count"] / len(before["nodes"]), 4) if event else None
            fp_before, fp_after = graph_node_hashes(before), graph_node_hashes(after)
            gdiff = diff_hashes(fp_before, fp_after)
            row["graph_locality"] = round(len(gdiff["changed"]) / gdiff["total_after"], 4) if gdiff["total_after"] else None
            touched = {e["node_id"] for e in result.get("trajectory", {}).get("node_edits", [])}
            row["touched_locality"] = round(len(touched) / gdiff["total_after"], 4) if gdiff["total_after"] else None
        rows.append(row)
    return rows


# ── Output ─────────────────────────────────────────────────────────────────────

CSV_COLUMNS = [
    "program", "condition", "round", "refinement_id",
    "cascade_scope", "output_locality", "graph_locality", "touched_locality",
    "prompt_tokens", "completion_tokens", "total_tokens", "llm_calls", "latency_ms",
    "token_ratio_vs_init", "latency_ratio_vs_init",
    "coverage_measures", "coverage_supports", "coverage_evaluates",
    "ready_to_aggregate", "residual_violations",
    "judge_addie_score", "judge_alignment_item",
]


def _fmt(value) -> str:
    if value is None or value == "":
        return "-"
    if isinstance(value, float):
        return f"{value:.2f}"
    return str(value)


def write_csv(rows: list[dict], path: Path) -> None:
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_COLUMNS, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def write_markdown(rows: list[dict], path: Path) -> None:
    lines = ["# RQ2 process metrics (4 conditions)", ""]
    lines.append("| Program | Round | Condition | Cascade | Out.loc | Graph.loc | Tokens | ×init | Latency (ms) | Judge ADDIE | Judge align | Cov. M/S/E | Resid. |")
    lines.append("|---|---|---|---|---|---|---|---|---|---|---|---|---|")
    for r in sorted((r for r in rows if r["round"] != 0), key=lambda r: (r["program"], r["round"], r["condition"])):
        cov = "/".join(
            _fmt(r.get(c)) for c in ("coverage_measures", "coverage_supports", "coverage_evaluates")
        ) if r["condition"] in HARNESS_CONDITIONS else "-"
        lines.append(
            f"| {r['program']} | {r['round']} | {r['condition']} "
            f"| {_fmt(r.get('cascade_scope'))} | {_fmt(r.get('output_locality'))} | {_fmt(r.get('graph_locality'))} "
            f"| {r['total_tokens']} | {_fmt(r.get('token_ratio_vs_init'))} | {r['latency_ms']} "
            f"| {_fmt(r.get('judge_addie_score'))} | {_fmt(r.get('judge_alignment_item'))} "
            f"| {cov} | {_fmt(r.get('residual_violations'))} |"
        )
    init_rows = [r for r in rows if r["round"] == 0]
    if init_rows:
        lines += ["", "## Init sessions (cost reference)", ""]
        lines.append("| Program | Condition | Tokens | LLM calls | Latency (ms) | Judge ADDIE |")
        lines.append("|---|---|---|---|---|---|")
        for r in sorted(init_rows, key=lambda r: (r["program"], r["condition"])):
            lines.append(
                f"| {r['program']} | {r['condition']} | {r['total_tokens']} | {r['llm_calls']} "
                f"| {r['latency_ms']} | {_fmt(r.get('judge_addie_score'))} |"
            )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--case-study-dir", default=str(CASE_STUDY_DIR))
    args = parser.parse_args(argv)

    case_study_dir = Path(args.case_study_dir)
    rows = compute_rows(case_study_dir)
    out_csv = case_study_dir / "results" / "metrics.csv"
    out_md = case_study_dir / "results" / "metrics.md"
    write_csv(rows, out_csv)
    write_markdown(rows, out_md)
    print(f"Wrote {out_csv} and {out_md} ({len(rows)} session rows)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

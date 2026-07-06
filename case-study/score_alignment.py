"""Score every case-study session with the benchmark evaluator (LLM judge).

This is the shared cross-agent instrument for the alignment-preservation
metric: the evaluator's ADDIE rubric (with the Design alignment item D1) scores
harness and react outputs on the same scale. Run it AFTER run_case_study.py and
BEFORE compute_metrics.py, using the benchmark repo's virtualenv (it imports
``isd_evaluator``) and judge credentials in the environment:

    cd /Users/phuongbv/Projects/master-thesis
    isd-agent-benchmark/venv/bin/python case-study/score_alignment.py [--programs ...] [--force]

Writes one score file per session to ``results/scores/{condition}/{program}/``;
``compute_metrics.py`` merges them when present. Sessions already scored are
skipped unless --force is given, so interrupted runs resume cheaply.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

CASE_STUDY_DIR = Path(__file__).resolve().parent
REPO_ROOT = CASE_STUDY_DIR.parent
BENCHMARK_ROOT = REPO_ROOT / "isd-agent-benchmark"

sys.path.insert(0, str(BENCHMARK_ROOT))
sys.path.insert(0, str(BENCHMARK_ROOT / "evaluator" / "src"))


def brief_to_scenario(brief: dict) -> dict:
    context = dict(brief.get("context", {}))
    context.setdefault("target_audience", brief.get("target_audience", ""))
    context.setdefault("duration", brief.get("duration", ""))
    return {
        "scenario_id": brief.get("id", "unknown"),
        "title": brief.get("title", ""),
        "context": context,
        "learning_goals": brief.get("learning_goals", []),
    }


def apply_overlay(brief: dict, overlay: dict) -> dict:
    merged = json.loads(json.dumps(brief))
    for key, value in overlay.items():
        if key == "learning_goals_append":
            merged.setdefault("learning_goals", []).extend(value)
        elif isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key].update(value)
        else:
            merged[key] = value
    return merged


def scenario_for_round(program: dict, round_index: int) -> dict:
    brief = json.loads((CASE_STUDY_DIR / program["brief"]).read_text(encoding="utf-8"))
    for r in program["rounds"][:round_index]:
        brief = apply_overlay(brief, r.get("brief_overlay", {}))
    return brief_to_scenario(brief)


def alignment_item_score(addie_score) -> float | None:
    for item in addie_score.design.items:
        if item.item_id == "D1" or "alignment" in (item.name or "").lower():
            return item.score
    return None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--programs", default="", help="Comma-separated program ids (default: all).")
    parser.add_argument("--conditions", default="", help="Comma-separated conditions (default: all).")
    parser.add_argument("--force", action="store_true", help="Re-score sessions that already have score files.")
    parser.add_argument("--judge-model", default="", help="Judge model override (else evaluator env defaults).")
    args = parser.parse_args(argv)

    from isd_evaluator.metrics import CompositeEvaluator

    evaluator = CompositeEvaluator(
        model=args.judge_model or None,
        use_llm=True,
        temperature=0.0,
    )

    scenarios_spec = json.loads((CASE_STUDY_DIR / "scenarios.json").read_text(encoding="utf-8"))
    programs = {p["program_id"]: p for p in scenarios_spec["programs"]}
    manifest = json.loads((CASE_STUDY_DIR / "results" / "manifest.json").read_text(encoding="utf-8"))

    wanted_programs = {p.strip() for p in args.programs.split(",") if p.strip()}
    wanted_conditions = {c.strip() for c in args.conditions.split(",") if c.strip()}

    scored = skipped = failed = 0
    for entry in manifest:
        pid, condition, k = entry["program_id"], entry["condition"], entry["round"]
        if wanted_programs and pid not in wanted_programs:
            continue
        if wanted_conditions and condition not in wanted_conditions:
            continue

        score_path = CASE_STUDY_DIR / "results" / "scores" / condition / pid / f"session_{k:02d}.json"
        if score_path.exists() and not args.force:
            skipped += 1
            continue

        result = json.loads((CASE_STUDY_DIR / entry["result_file"]).read_text(encoding="utf-8"))
        scenario = scenario_for_round(programs[pid], k)
        print(f"[score] {condition} {pid} round {k}", flush=True)
        try:
            score = evaluator.evaluate(addie_output=result["addie_output"], scenario=scenario)
        except Exception as e:
            print(f"[score] FAILED {condition} {pid} round {k}: {e}", flush=True)
            failed += 1
            continue

        score_path.parent.mkdir(parents=True, exist_ok=True)
        score_path.write_text(json.dumps({
            "addie_score": score.addie_score,
            "alignment_item_score": alignment_item_score(score.addie),
            "total": score.total,
            "judge_model": args.judge_model or "env-default",
        }, ensure_ascii=False, indent=2), encoding="utf-8")
        scored += 1

    print(f"Scored {scored}, skipped {skipped} (already scored), failed {failed}.")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())

"""Build a synthetic run tree that looks exactly like a real one.

Why this exists: ``results/`` is empty and no ``pooled_*.json`` survives, so
the artifacts currently in ``docs/generated/`` cannot be regenerated and there
is no real-data oracle for the migration. A fixture run tree is the
replacement, and it is a better one than the ``--demo`` mode it retires --
``demo_pooled()`` fabricated a pooled dict by hand, which can drift from the
schema the pooler actually emits, whereas pooling a fixture run tree cannot.

The numbers are invented. The *shapes* are taken from the readers:
``comparison_report.json`` from ``load_run``, ``alignment_scores.json`` from
the scorer's own payload literal, and the trajectory from what the cost table
reads. Three pathologies are planted on purpose, because a fixture where
everything succeeds tests only the happy path:

* one agent missing an output entirely   -> the failure-policy layers
* one scenario recording evaluation_error -> what `audit repair` looks for
* one stub output                         -> what `audit postrun` flags
"""

from __future__ import annotations

import json
import random
from pathlib import Path

#: Mirrors evaluator alignment.ALIGNMENT_SIGNALS. Duplicated rather than imported
#: so the fixture keeps building while the protocol module is being moved.
PANEL = (
    "objective_assessment_similarity",
    "objective_activity_similarity",
    "activity_assessment_similarity",
    "objective_cognitive_congruence",
    "porter_mean",
    "webb_bloom_consistency",
)

#: Two rungs is enough to exercise every size-dependent path (ordering, macro
#: words, the interaction tests) without making the fixture slow to regenerate.
RUNGS = [("qwen3.5-0.8b", 0.8), ("qwen3.5-4b", 4.0)]
AGENTS = ["alignmentgraph-isd", "react-isd", "baseline"]
N_SCENARIOS = 6
DATASET = "test_90"

MISSING = ("scenario_03", "baseline")          # no output at all
EVAL_ERROR = ("scenario_04", "react-isd")      # transient LLM judge failure
STUB = ("scenario_05", "baseline")             # produced, but empty


def _quality(agent: str, params_b: float, rng: random.Random) -> float:
    """A plausible score surface: better agents score higher, and the gap
    narrows as the model grows -- the direction the study predicts, so the
    fixture exercises a non-degenerate interaction rather than noise."""
    base = {"alignmentgraph-isd": 74.0, "react-isd": 66.0, "baseline": 58.0}[agent]
    edge = {"alignmentgraph-isd": 6.0, "react-isd": 2.0, "baseline": 0.0}[agent]
    return base + edge * (1.0 - params_b / 9.0) + params_b * 0.8 + rng.gauss(0, 2.5)


def _addie_output(agent: str, scenario_id: str, stub: bool) -> dict:
    if stub:
        return {"analysis": {}, "design": {}, "development": {},
                "implementation": {}, "evaluation": {}}
    return {
        "analysis": {"gap_analysis": [{"id": "g1", "description": "Learners cannot apply X."}],
                     "learner_profile": {"prior_knowledge": "novice"}},
        "design": {
            "learning_objectives": [
                {"id": "ILO-01", "statement": "Apply X to solve routine problems.",
                 "level": "apply"},
                {"id": "ILO-02", "statement": "Analyse tradeoffs between X and Y.",
                 "level": "analyze"},
            ],
            "assessment_items": [
                {"id": "AT-0101", "objective_id": "ILO-01", "plan_category": "formative",
                 "question": "Given a case, apply X and justify each step.",
                 "required_cognitive_process": "apply"},
                {"id": "AT-0102", "objective_id": "ILO-02", "plan_category": "summative",
                 "question": "Compare X and Y for the scenario and defend a choice.",
                 "required_cognitive_process": "analyze"},
            ],
            "learning_activities": [
                {"id": "TLA-0101", "objective_id": "ILO-01",
                 "activity_name": "Worked example then guided practice on X",
                 "learner_cognitive_process": "apply"},
                {"id": "TLA-0102", "objective_id": "ILO-02",
                 "activity_name": "Structured comparison of X and Y",
                 "learner_cognitive_process": "analyze"},
            ],
        },
        "development": {"learner_materials": [{"id": "MAT-0101", "type": "slides",
                                               "content": f"Slides for {scenario_id}."}]},
        "implementation": {"instructor_guide": {"session_guides": [
            {"session": 1, "activity_ids": ["TLA-0101"], "material_ids": ["MAT-0101"]}]}},
        "evaluation": {"improvement_plan": [{"id": "i1", "action": "Revise the rubric."}]},
    }


def _trajectory(agent: str, params_b: float, rng: random.Random) -> dict:
    """Cost and process record. The proposed system is deliberately the
    expensive one -- that asymmetry is a real finding the cost table reports,
    and a fixture that hid it would let a regression there pass unnoticed."""
    calls = {"alignmentgraph-isd": 180, "react-isd": 6, "baseline": 3}[agent]
    calls = int(calls * (1.0 + 0.1 * rng.random()))
    prompt = calls * 3200
    completion = calls * 620
    return {
        "metadata": {
            "token_usage": {"prompt_tokens": prompt, "completion_tokens": completion,
                            "total_tokens": prompt + completion},
            "execution_time_seconds": round(calls * 1.9 + rng.uniform(0, 20), 2),
            "model_calls": calls,
            "run_config": {"agent_mode": "multi", "context_mode": "graph"}
            if agent == "alignmentgraph-isd" else {},
        },
        "events": [{"action": "tool_call", "agent": agent, "tool": f"step_{i}"}
                   for i in range(min(calls, 40))],
    }


def _alignment(agent: str, params_b: float, rng: random.Random) -> dict:
    lift = {"alignmentgraph-isd": 0.12, "react-isd": 0.04, "baseline": 0.0}[agent]
    out = {}
    for sig in PANEL:
        val = 0.42 + lift + params_b * 0.012 + rng.gauss(0, 0.04)
        out[sig] = round(min(1.0, max(0.0, val)), 6)
    out["details"] = {"sanity": {"bloom_vs_declared_agreement": round(0.7 + rng.random() * 0.2, 4)}}
    out["counts"] = {"objectives": 2, "assessment_items": 2, "activities": 2}
    return out


def build(root: Path, tag: str = "c1", seed: int = 42) -> list[Path]:
    """Create one run dir per rung under ``root``. Returns the run dirs."""
    run_dirs = []
    for model_safe, params_b in RUNGS:
        rng = random.Random(f"{seed}-{model_safe}")
        run_dir = root / f"test_90_benchmark_{model_safe}_{tag}_20260101_000000"
        run_dirs.append(run_dir)
        # Real layout is run_dir/<variant>/<scenario>/. The pooler tolerates a
        # flat tree too, but the cost table assumes the nested one, so the
        # fixture uses what the benchmark actually writes.
        variant = run_dir / DATASET
        for i in range(1, N_SCENARIOS + 1):
            sid = f"scenario_{i:02d}"
            scen = variant / sid
            scen.mkdir(parents=True, exist_ok=True)

            rankings, scores, missing = [], {}, {}
            for agent in AGENTS:
                if (sid, agent) == MISSING:
                    # {agent: reason} -- the shape pool_alignment reads.
                    missing[agent] = "no output produced"
                    continue
                stub = (sid, agent) == STUB
                total = round(_quality(agent, params_b, rng), 4)
                addie = round(total + rng.gauss(1.5, 1.0), 4)
                traj = round(total - rng.gauss(4.0, 1.5), 4)
                row = {"agent_id": agent, "total_score": total,
                       "addie_median": addie, "trajectory_score": traj}
                if (sid, agent) == EVAL_ERROR:
                    # Scored cell lost to a transient LLM judge failure: the exact
                    # shape `audit repair` re-judges without regenerating output.
                    row = {"agent_id": agent, "total_score": None,
                           "addie_median": None, "trajectory_score": None,
                           "evaluation_error": "LLM judge timeout"}
                rankings.append(row)
                (scen / f"{agent}_output.json").write_text(
                    json.dumps(_addie_output(agent, sid, stub), indent=2), encoding="utf-8")
                (scen / f"{agent}_trajectory.json").write_text(
                    json.dumps(_trajectory(agent, params_b, rng), indent=2), encoding="utf-8")
                scores[agent] = _alignment(agent, params_b, rng)

            (scen / "comparison_report.json").write_text(
                json.dumps({"scenario_id": sid, "comparison": {"rankings": rankings}}, indent=2),
                encoding="utf-8")
            (scen / "alignment_scores.json").write_text(
                json.dumps({"scenario_dir": sid, "scenario_id": sid,
                            "encoder": "tfidf-char", "encoder_revision": "",
                            "bloom_classifier": "lexicon",
                            "agents": scores, "missing_outputs": missing}, indent=2),
                encoding="utf-8")

        # `model` is an object, not a string: the cost table reads
        # model.name and model.base_urls off it.
        (run_dir / "benchmark_summary.json").write_text(
            json.dumps({
                "dataset": DATASET,
                "model": {"name": model_safe, "base_urls": ["http://localhost:8000/v1"]},
                "config": {"rate_limit": "turbo"},
                "run_tag": tag, "agents": AGENTS, "n_scenarios": N_SCENARIOS,
            }, indent=2),
            encoding="utf-8")
        (run_dir / "benchmark_progress.log").write_text(
            "\n".join(f"[{i}/{N_SCENARIOS}] scenario_{i:02d} done" for i in range(1, N_SCENARIOS + 1)),
            encoding="utf-8")
    return run_dirs


#: The four ablation arms, as the config declares them. The reference arm
#: leads, because every delta is taken against it.
ARMS = [
    "alignmentgraph-isd",
    "alignmentgraph-isd-multi-prose",
    "alignmentgraph-isd-single-graph",
    "alignmentgraph-isd-single-prose",
]

ARM_FLAGS = {
    "alignmentgraph-isd": ("multi", "graph"),
    "alignmentgraph-isd-multi-prose": ("multi", "prose"),
    "alignmentgraph-isd-single-graph": ("single", "graph"),
    "alignmentgraph-isd-single-prose": ("single", "prose"),
}


def build_ablation(root: Path, tag: str = "a1", seed: int = 7) -> list[Path]:
    """A 2x2 ablation run tree: 4 arms x 2 rungs x 6 scenarios.

    Each arm's trajectory records the run_config it was launched with, because
    pooling hard-fails when a run's recorded axes disagree with the arm it is
    filed under -- a mis-filed run is a silently wrong factorial.
    """
    global AGENTS, DATASET, N_SCENARIOS
    saved = (AGENTS, DATASET)
    AGENTS, DATASET = ARMS, "test_30"
    run_dirs = []
    try:
        for model_safe, params_b in RUNGS:
            rng = random.Random(f"{seed}-{model_safe}")
            run_dir = root / f"test_30_benchmark_{model_safe}_{tag}_20260101_000000"
            run_dirs.append(run_dir)
            variant = run_dir / "test_30"
            for i in range(1, N_SCENARIOS + 1):
                sid = f"scenario_{i:02d}"
                scen = variant / sid
                scen.mkdir(parents=True, exist_ok=True)
                rankings, scores = [], {}
                for arm in ARMS:
                    # The full architecture leads; removing either mechanism
                    # costs, and removing both costs most.
                    mode, ctx = ARM_FLAGS[arm]
                    penalty = (0.0 if mode == "multi" else 3.0) + (0.0 if ctx == "graph" else 2.0)
                    total = round(_quality("alignmentgraph-isd", params_b, rng) - penalty, 4)
                    rankings.append({"agent_id": arm, "total_score": total,
                                     "addie_median": round(total + rng.gauss(1.5, 1.0), 4),
                                     "trajectory_score": round(total - rng.gauss(4.0, 1.5), 4)})
                    (scen / f"{arm}_output.json").write_text(
                        json.dumps(_addie_output(arm, sid, False), indent=2), encoding="utf-8")
                    traj = _trajectory("alignmentgraph-isd", params_b, rng)
                    traj["metadata"]["run_config"] = {"agent_mode": mode, "context_mode": ctx}
                    (scen / f"{arm}_trajectory.json").write_text(
                        json.dumps(traj, indent=2), encoding="utf-8")
                    scores[arm] = _alignment("alignmentgraph-isd", params_b, rng)
                (scen / "comparison_report.json").write_text(
                    json.dumps({"scenario_id": sid, "comparison": {"rankings": rankings}}, indent=2),
                    encoding="utf-8")
                (scen / "alignment_scores.json").write_text(
                    json.dumps({"scenario_dir": sid, "scenario_id": sid,
                                "encoder": "tfidf-char", "encoder_revision": "",
                                "bloom_classifier": "lexicon",
                                "agents": scores, "missing_outputs": {}}, indent=2),
                    encoding="utf-8")
            (run_dir / "benchmark_summary.json").write_text(
                json.dumps({"dataset": "test_30",
                            "model": {"name": model_safe, "base_urls": ["http://localhost:8000/v1"]},
                            "config": {"rate_limit": "turbo"},
                            "run_tag": tag, "agents": ARMS, "n_scenarios": N_SCENARIOS}, indent=2),
                encoding="utf-8")
            (run_dir / "benchmark_progress.log").write_text(
                "\n".join(f"[{i}/{N_SCENARIOS}] scenario_{i:02d} done"
                          for i in range(1, N_SCENARIOS + 1)), encoding="utf-8")
    finally:
        AGENTS, DATASET = saved
    return run_dirs


if __name__ == "__main__":
    import sys
    target = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("tests/fixtures/mini_run")
    dirs = build(target) + build_ablation(target)
    print(f"built {len(dirs)} run dir(s) under {target}")
    for d in dirs:
        print("  ", d.name)

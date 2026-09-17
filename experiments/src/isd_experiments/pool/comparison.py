"""Pool the comparison experiment: the proposed system against baselines,
across the model ladder.

Two things rather than a page of flags: the experiment profile (who is
compared, on which split, under which tags) comes from ``experiment.toml``, and
only the genuinely per-invocation choices stay as arguments.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from .. import paths, runs, schema
from ..config import LLM_JUDGE_SCORES, Profile
from ..config import current as current_config
from ..stats import BOOT_SEED, N_BOOT
from .arms import resolve_sensitivity_arms
from .inference import failure_tests, interaction_tests
from .llm_judge import compare_model, pool_model
from .panel import SUMMARY_SIGNAL, pool_alignment, pool_alignment_sensitivity
from .report import print_report
from .tokens import pool_tokens

#: How the LLM judge scores are described in the pooled config block, so a reader
#: of the JSON alone knows what was measured and what was not claimed.
SCORE_FIELD_NOTE = (
    "LLM judge scores reported side by side, no composite as headline: "
    "addie_median (LEAD — instructional-design content quality, the construct "
    "the research question is about), trajectory_score (process conformance), "
    "total_score (= 0.7*ADDIE + 0.3*Traj, the benchmark's own composite, kept "
    "for comparability). All from comparison_report.json, per scenario."
)


def default_glob(profile: Profile) -> str:
    """Run dirs this profile would have written, as a glob.

    Built from the profile rather than typed at the prompt, which is what
    prevents the classic mismatch: the comparison pools one tag namespace and
    a tuning run wrote another, so the pattern silently matches nothing.
    """
    tags = "".join(sorted({t.rstrip("0123456789") or t for t in profile.tags})) or "*"
    return f"{profile.dataset}_benchmark_*_{tags}*"


def discover(patterns: list[str], profile: Profile) -> dict[str, list[Path]]:
    """Group run dirs by model label, failing with something actionable."""
    grouped: dict[str, list[Path]] = {}
    for pattern in patterns:
        for label, dirs in runs.group_by_glob(pattern).items():
            grouped.setdefault(label, []).extend(dirs)
    if grouped:
        return grouped

    # Distinguish "you passed nothing" from "what you passed matched nothing":
    # telling someone who just used a glob to use a glob sends them hunting for
    # a bug in the tool. The usual cause is a tag mismatch.
    present = sorted(d.name for d in paths.results_root().glob("*_benchmark_*") if d.is_dir())
    detail = ("\n  run dirs present:\n    " + "\n    ".join(present[:8])
              if present else f"\n  no run dirs under {paths.results_root()}")
    raise SystemExit(
        f"No run dirs matched {patterns!r} for experiment {profile.name!r}."
        + detail
        + "\n  Names must look like <dataset>_benchmark_<model>_<tag>_<YYYYmmdd_HHMMSS>."
    )


def pool(profile: Profile, run_dirs_by_model: dict[str, list[Path]], *,
         sweep_arms: list[tuple[str, str]] | None = None,
         summary_signal: str = SUMMARY_SIGNAL,
         agents: list[str] | None = None) -> dict:
    """Build the pooled document. Pure: no printing, no writing.

    ``agents`` overrides the profile roster. It exists because the roster fixes
    the Holm family size, so it must be stated rather than inferred from which
    agents happen to have produced output -- an agent that crashed everywhere
    would otherwise shrink the correction and inflate every remaining result.
    Used for re-pooling a subset deliberately, and by the fixtures.
    """
    roster = list(agents or profile.agents)
    proposed = profile.proposed if profile.proposed in roster else roster[0]
    baselines = [a for a in roster if a != proposed]
    scored = baselines + [proposed]
    cfg = current_config()

    models = []
    for label, dirs in run_dirs_by_model.items():
        model = pool_model(label, dirs, scored)
        model["comparisons"] = compare_model(model, proposed, baselines)
        models.append(model)

    arms = sweep_arms or []
    alignment = pool_alignment(models, run_dirs_by_model, scored, proposed,
                               baselines, return_scenario_maps=bool(arms))
    sensitivity = pool_alignment_sensitivity(
        models, run_dirs_by_model, scored, proposed, baselines, arms,
        alignment, cfg.alignment_raw.get("primary_encoder", ""), summary_signal,
    ) if arms else None
    if alignment is not None:
        alignment.pop("_align_maps", None)

    pooled = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "config": {
            "experiment": profile.name,
            "dataset": profile.dataset,
            "proposed": proposed,
            "baselines": baselines,
            "score_field": SCORE_FIELD_NOTE,
            "pooling": "mean across runs per (model, agent, scenario)",
            "primary_failure_policy": "complete_case",
            "alignment_failure_policies": (
                "complete_case (primary) + zero; the panel has no min_score "
                "policy because its endpoints already floor at 0.0"
            ),
            "n_boot": N_BOOT,
            "bootstrap_seed": BOOT_SEED,
            "size_order": [m["label"] for m in models],
        },
        "models": models,
        "interaction": interaction_tests(models, proposed, baselines),
        "interaction_by_score": {
            m: interaction_tests(models, proposed, baselines, metric=m)
            for m in LLM_JUDGE_SCORES
        },
        "failure_rates": failure_tests(models, proposed, baselines),
        "alignment": alignment,
        "token_usage": pool_tokens(run_dirs_by_model, scored),
    }
    if sensitivity is not None:
        pooled["config"]["primary_encoder"] = cfg.alignment_raw.get("primary_encoder", "")
        pooled["config"]["sensitivity_arms"] = [k for k, _s in arms]
        pooled["alignment_sensitivity"] = sensitivity
    return pooled


def run(*, experiment: str = "comparison", patterns: list[str] | None = None,
        out: Path | None = None, encoders: str = "", auto_encoders: bool = False,
        auto_bloom: bool = False, summary_signal: str = SUMMARY_SIGNAL,
        agents: list[str] | None = None, quiet: bool = False) -> Path:
    """Discover, pool, report and write. Returns the output path."""
    profile = current_config().profile(experiment)
    run_dirs_by_model = discover(patterns or [default_glob(profile)], profile)

    if not quiet:
        for label, dirs in run_dirs_by_model.items():
            print(f"model {label!r}: {len(dirs)} run(s)")
            for d in dirs:
                print(f"  - {d}")

    arms = resolve_sensitivity_arms(run_dirs_by_model, explicit=encoders,
                                    auto_encoders=auto_encoders, auto_bloom=auto_bloom)
    pooled = pool(profile, run_dirs_by_model, sweep_arms=arms,
                  summary_signal=summary_signal, agents=agents)

    if not quiet:
        print_report(pooled, pooled["config"]["proposed"], pooled["config"]["baselines"])

    # Per-scenario series are an implementation detail of the inferential layer
    # and would multiply the file size for no consumer.
    for model in pooled["models"]:
        model.pop("_scores", None)

    out_path = out or (paths.results_root() / f"pooled_{experiment}.json")
    schema.write(out_path, pooled)
    if not quiet:
        print(f"\nPooled JSON written: {out_path}")
    return out_path

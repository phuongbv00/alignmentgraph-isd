"""`isd-exp` -- the experiment, one command per stage.

Stages are verbs, and the experiment is what a verb acts on (`run comparison`,
`pool ablation`). They are listed to read down the roadmap, so the order you
run them is the order they appear in `--help`:

    doctor                    once per machine
    data / bloom              inputs
    freeze / audit preflight  lock the version, verify the endpoints
    run                       generate: tune, comparison, ablation
    judge / trajectory        score finished runs, no regeneration
    pool                      pool the scored runs of one experiment
    report / audit artifacts  the manuscript's numbers
    expert                    human validation
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


def _p(value: str) -> Path:
    return Path(value).expanduser()


#: The launchable experiments, with the line `help run` shows for each.
EXPERIMENTS = {
    "tune": "cost and budget calibration on the training split",
    "comparison": "the proposed system against baselines, across the ladder",
    "ablation": "the 2x2 factorial over decomposition and substrate",
}

#: The rate presets a run accepts (runner/llm.py::RATE_PRESETS), spelled here
#: so the parser can build without importing the runner.
RATE_LIMITS = ("conservative", "moderate", "aggressive", "turbo")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="isd-exp",
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--config", type=_p, default=None, metavar="TOML",
                        help="experiment declaration (default: experiments/experiment.toml)")
    sub = parser.add_subparsers(dest="command", required=True, metavar="<stage>")

    # ── once per machine ─────────────────────────────────────────────────
    d = sub.add_parser("doctor", help="check the checkout, venvs and .env wiring")
    d.add_argument("--fix", action="store_true", help="repair what can be repaired")

    # ── inputs ───────────────────────────────────────────────────────────
    data = sub.add_parser("data", help="build the scenario splits").add_subparsers(
        dest="sub", required=True)
    sp = data.add_parser("split", help="carve a stratified subset")
    sp.add_argument("preset", nargs="?", default=None,
                    help="named split from the config, or omit and pass --source/--target")
    sp.add_argument("--source", type=_p), sp.add_argument("--target", type=_p)
    sp.add_argument("--per-cell", type=int, default=3)
    sp.add_argument("--max-total", type=int, default=None,
                    help="cap the total, down-sampling the filled cells round-robin; "
                         "the only way to a subset smaller than the 30-cell grid")
    sp.add_argument("--disjoint-from", type=_p, action="append", default=[])
    sp.add_argument("--seed", type=int, default=42)

    bloom = sub.add_parser("bloom", help="the Bloom classifier arm").add_subparsers(
        dest="sub", required=True)
    bt = bloom.add_parser("train", help="fine-tune the 6-way head")
    bt.add_argument("--train", type=_p, required=True), bt.add_argument("--output-dir", type=_p)
    bv = bloom.add_parser("validate", help="score an arm against expert labels")
    bv.add_argument("labels", type=_p, nargs="?")
    bv.add_argument("--bloom-checkpoint", type=_p), bv.add_argument("--out", type=_p)

    # ── freeze ───────────────────────────────────────────────────────────
    fr = sub.add_parser("freeze", help="record the version an experiment ran on").add_subparsers(
        dest="sub", required=True)
    fw = fr.add_parser("write", help="write the manifest")
    fw.add_argument("--tag"), fw.add_argument("--out", type=_p)
    fr.add_parser("verify", help="compare the working tree against a manifest")

    # ── generate ─────────────────────────────────────────────────────────
    # The experiments are fixed here rather than read from the config: `help`
    # has to work on a checkout whose config does not load, which is exactly
    # when someone reaches for it. Whether the profile exists is checked when
    # the command runs.
    run = sub.add_parser("run", help="generate an experiment's runs (no scoring unless asked)"
                         ).add_subparsers(dest="sub", required=True, metavar="<experiment>")
    for name, helptext in EXPERIMENTS.items():
        r = run.add_parser(name, help=helptext)
        r.add_argument("--dry-run", action="store_true",
                       help="print the launch plan and exit")
        r.add_argument("--slots", help="comma-separated model slots (default: the profile's)")
        r.add_argument("--tags", help="comma-separated run tags (default: the profile's)")
        r.add_argument("--agents", help="comma-separated roster override")
        r.add_argument("--judge", action="store_true",
                       help="judge each run once generated: `judge llm`, then "
                            "`judge alignment` on every declared arm")
        r.add_argument("--foreground", action="store_true",
                       help="run ONE slot x ONE tag in this process instead of "
                            "launching tmux sessions (what each session runs)")
        r.add_argument("--rate-limit", choices=RATE_LIMITS,
                       help="rate preset (default: the profile's, or <SLOT>_RATE_LIMIT)")

    # ── score finished runs ──────────────────────────────────────────────
    jd = sub.add_parser("judge", help="score finished runs (no regeneration)").add_subparsers(
        dest="sub", required=True)
    jl = jd.add_parser("llm", help="the benchmark's LLM judge (ADDIE rubric + trajectory)")
    jl.add_argument("run_dirs", nargs="*", metavar="RUN_DIR")
    jl.add_argument("--agents", default="", help="comma-separated roster filter")
    jl.add_argument("--workers", type=int, default=4, help="scenarios judged at once")
    jl.add_argument("--overwrite", action="store_true",
                    help="re-judge scenarios that are already judged")
    jl.add_argument("--dry-run", action="store_true",
                    help="print what would be judged; no LLM judge calls")
    jl.add_argument("--limit", type=int)
    jl.add_argument("--scenario-root", type=_p)

    sc = jd.add_parser("alignment", help="the alignment panel (no LLM)")
    sc.add_argument("run_dirs", nargs="*", metavar="RUN_DIR")
    # Arm selection. With no flag the primary configuration runs alone; the
    # sweep is a star, so an arm deviating on both axes at once is an error
    # rather than a silent cross-product.
    sc.add_argument("--encoder-preset", default=""), sc.add_argument("--encoder-presets", default="")
    sc.add_argument("--all-encoders", action="store_true")
    sc.add_argument("--bloom-preset", default=""), sc.add_argument("--bloom-presets", default="")
    sc.add_argument("--bloom-checkpoint", type=_p)
    sc.add_argument("--primary-only", action="store_true",
                    help="the primary configuration alone (default: every arm "
                         "declared in experiment.toml)")
    # Where each served arm is embedded, and how. Endpoints are per arm on
    # purpose: the cache key does not record the backend, so one shared URL
    # would mix two numerically different sources under one key.
    sc.add_argument("--embed-base-urls-for", action="append", default=[], metavar="SLOT=URL,URL")
    sc.add_argument("--embed-revision-for", action="append", default=[], metavar="SLOT=REV")
    sc.add_argument("--embed-cache-only", action="store_true")
    sc.add_argument("--embed-api-key-env", default="",
                    help="fallback name of the token variable for a served arm "
                         "(default: [serving].key_env)")
    sc.add_argument("--tfidf-ngram-range", default="2-3", metavar="LO-HI")
    sc.add_argument("--local-device")
    # What to score.
    sc.add_argument("--agents", default="", help="comma-separated roster filter")
    sc.add_argument("--scenario-root", type=_p)
    sc.add_argument("--limit", type=int)
    sc.add_argument("--reaggregate", action="store_true")
    sc.add_argument("--overwrite", action="store_true",
                    help="re-judge scenarios that are already judged")
    sc.add_argument("--dry-run", action="store_true",
                    help="print the arms and the scope; nothing contacted or written")
    sc.add_argument("--yes", "-y", action="store_true",
                    help="do not ask before overwriting alignment_scores.json")
    sc.add_argument("--require-all", action="store_true",
                    help="fail instead of skipping an arm that cannot run")
    sc.add_argument("--sweep-csv", type=_p)

    tr = sub.add_parser("trajectory", help="re-score saved trajectories").add_subparsers(
        dest="sub", required=True)
    trs = tr.add_parser("rescore", help="diagnostic layer at a higher tool-call cap")
    trs.add_argument("run_dirs", nargs="*", metavar="RUN_DIR")
    trs.add_argument("--cap", type=int, default=120)

    # ── pool ─────────────────────────────────────────────────────────────
    pool = sub.add_parser("pool", help="pool an experiment's scored runs into one JSON"
                          ).add_subparsers(dest="sub", required=True, metavar="<experiment>")
    for name in ("comparison", "ablation"):
        pl = pool.add_parser(name, help=EXPERIMENTS[name])
        pl.add_argument("patterns", nargs="*", metavar="GLOB")
        pl.add_argument("--out", type=_p)
        pl.add_argument("--agents", help="comma-separated roster override "
                                         "(this fixes the Holm family size)")
        if name == "comparison":
            pl.add_argument("--encoders", default="")
            pl.add_argument("--auto-encoders", action="store_true")
            pl.add_argument("--auto-bloom", action="store_true")
        else:
            pl.add_argument("--comparison-pooled", type=_p)

    # ── the manuscript's numbers ─────────────────────────────────────────
    rep = sub.add_parser("report", help="generate tables, figures and notes").add_subparsers(
        dest="sub", required=True)
    for name in ("tables", "figures", "cost", "sensitivity",
                 "ablation-tables", "ablation-figures", "facts", "sync", "all"):
        r = rep.add_parser(name)
        r.add_argument("--pooled", type=_p), r.add_argument("--ablation-pooled", type=_p)
        r.add_argument("--outdir", type=_p), r.add_argument("--runs-glob")
        if name == "all":
            r.add_argument("--no-sync", action="store_true")
        if name == "facts":
            r.add_argument("--brief", action="store_true")

    aud = sub.add_parser("audit", help="checks before, during and after a run").add_subparsers(
        dest="sub", required=True)
    pre = aud.add_parser("preflight", help="endpoints, auth, serving limits, disk")
    pre.add_argument("--skip-smoke", action="store_true",
                     help="check reachability only; do not spend a completion per pod")
    pre.add_argument("--min-disk-gb", type=int, default=20,
                     help="fail below this much free space for results (default: 20)")
    ai = aud.add_parser("inflight", help="red flags in the live logs")
    ai.add_argument("--experiment", default=None)
    ap_ = aud.add_parser("postrun", help="completeness and integrity of finished runs")
    ap_.add_argument("run_dirs", nargs="*", metavar="RUN_DIR")
    ar = aud.add_parser("repair", help="re-run the LLM judge on cells lost to a transient failure")
    ar.add_argument("run_dirs", nargs="*", metavar="RUN_DIR",
                    help="run dirs or quoted globs; default: the ladder glob")
    ar.add_argument("--dry-run", action="store_true",
                    help="print the scope; no LLM judge calls and no writes")
    ar.add_argument("--yes", "-y", action="store_true",
                    help="skip the confirmation (this stage spends LLM judge calls)")
    ar.add_argument("--max-attempts", type=int, default=3)
    ar.add_argument("--backup-suffix", default=None,
                    help="one-time backup suffix inserted before the extension")
    ar.add_argument("--skip-audit", action="store_true",
                    help="do not run the post-run audit afterwards")
    ar.add_argument("--verbose", "-v", action="store_true")
    aa = aud.add_parser("artifacts", help="the final gate on generated artifacts")
    aa.add_argument("--strict", action="store_true"), aa.add_argument("--no-docs", action="store_true")

    ex = sub.add_parser("expert", help="human validation package").add_subparsers(
        dest="sub", required=True)
    ex.add_parser("sample", help="draw a blinded subset for expert review")
    ex.add_parser("aggregate", help="combine returned score sheets")

    h = sub.add_parser("help", help="show help for a stage, e.g. `help pool comparison`")
    h.add_argument("topic", nargs="*", metavar="STAGE",
                   help="stage, optionally with its subcommand; omit for the overview")

    return parser


def subparsers(parser: argparse.ArgumentParser) -> dict[str, argparse.ArgumentParser]:
    """Every subcommand, keyed by the words you type to reach it.

    Built by walking the parser rather than kept as a second list, so it cannot
    fall out of step with what actually exists.
    """
    found: dict[str, argparse.ArgumentParser] = {}
    for action in parser._actions:
        for name, stage in (getattr(action, "choices", None) or {}).items():
            found[name] = stage
            for inner in getattr(stage, "_actions", []):
                for sub_name, leaf in (getattr(inner, "choices", None) or {}).items():
                    found[f"{name} {sub_name}"] = leaf
    return found


def show_help(topic: list[str]) -> int:
    """`isd-exp help [stage [sub]]`.

    A subcommand as well as a flag: `help <thing>` is what people type, and
    `--help` after a stage you have not learned yet means guessing the stage
    name correctly on the first try.
    """
    parser = build_parser()
    if not topic:
        parser.print_help()
        return 0

    known = subparsers(parser)
    key = " ".join(topic)
    if key in known:
        known[key].print_help()
        return 0

    # A stage named with an unknown subcommand: show the stage, which lists
    # the subcommands that do exist.
    if len(topic) > 1 and topic[0] in known:
        print(f"No subcommand {topic[1]!r} under {topic[0]!r}.\n", file=sys.stderr)
        known[topic[0]].print_help()
        return 1

    stages = sorted(k for k in known if " " not in k)
    print(f"Unknown stage {key!r}.\n\nStages: {', '.join(stages)}", file=sys.stderr)
    return 1


def main(argv: list[str] | None = None) -> int:
    # Line by line even when piped: a launched run writes through `tee`, where
    # a block-buffered stdout holds a judge's whole log back for minutes.
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(line_buffering=True)
        except (AttributeError, ValueError):       # not a text stream
            pass
    args = build_parser().parse_args(argv)
    if args.command == "help":
        # Before the config is touched: help must work on a broken checkout,
        # which is exactly when someone reaches for it.
        return show_help(args.topic)
    if args.config:
        import os
        os.environ["ISD_EXPERIMENT_CONFIG"] = str(args.config)

    try:
        return _dispatch(args)
    except SystemExit as exc:                     # a stage refusing, with a reason
        if isinstance(exc.code, str):
            print(exc.code, file=sys.stderr)
            return 1
        return exc.code or 0


def _dispatch(args) -> int:
    command, sub = args.command, getattr(args, "sub", None)

    if command == "doctor":
        from .doctor import run as doctor_run
        return doctor_run(fix=args.fix)

    if command == "data" and sub == "split":
        from .data.sample import run as split_run
        return split_run(preset=args.preset, source=args.source, target=args.target,
                         per_cell=args.per_cell, disjoint_from=args.disjoint_from,
                         seed=args.seed, max_total=args.max_total)

    if command == "bloom":
        from .alignment import bloom
        if sub == "train":
            return bloom.train(train_csv=args.train, output_dir=args.output_dir)
        return bloom.validate(labels=args.labels, checkpoint=args.bloom_checkpoint,
                              out=args.out)

    if command == "run":
        return _run(args)

    if command == "pool" and sub == "comparison":
        from .pool import comparison
        comparison.run(experiment="comparison", patterns=args.patterns or None,
                       out=args.out, encoders=args.encoders,
                       auto_encoders=args.auto_encoders, auto_bloom=args.auto_bloom,
                       agents=args.agents.split(",") if args.agents else None)
        return 0

    if command == "pool" and sub == "ablation":
        from .pool import ablation
        ablation.run(patterns=args.patterns or None, out=args.out,
                     comparison_pooled=args.comparison_pooled)
        return 0

    if command == "freeze":
        from .freeze import manifest
        if sub == "write":
            manifest.write(tag=args.tag, out=args.out)
        else:
            return manifest.verify()
        return 0

    if command == "judge" and sub == "llm":
        from .judge import llm
        return llm.run(run_dirs=args.run_dirs, agents=args.agents, workers=args.workers,
                       overwrite=args.overwrite, dry_run=args.dry_run, limit=args.limit,
                       scenario_root=args.scenario_root)

    if command == "judge" and sub == "alignment":
        from .judge import alignment
        # Every option the scorer's helpers read is a parameter of `run`, and a
        # test holds the two sets equal -- a helper reaching for an attribute no
        # caller can set fails at the first line of the first arm.
        return alignment.run(
            run_dirs=args.run_dirs,
            encoder_preset=args.encoder_preset, encoder_presets=args.encoder_presets,
            all_encoders=args.all_encoders,
            bloom_preset=args.bloom_preset, bloom_presets=args.bloom_presets,
            bloom_checkpoint=args.bloom_checkpoint, primary_only=args.primary_only,
            embed_base_urls_for=args.embed_base_urls_for,
            embed_revision_for=args.embed_revision_for,
            embed_cache_only=args.embed_cache_only,
            embed_api_key_env=args.embed_api_key_env,
            tfidf_ngram_range=args.tfidf_ngram_range, local_device=args.local_device,
            agents=args.agents, scenario_root=args.scenario_root, limit=args.limit,
            reaggregate=args.reaggregate, overwrite=args.overwrite,
            require_all=args.require_all, sweep_csv=args.sweep_csv,
            dry_run=args.dry_run, yes=args.yes,
        )

    if command == "trajectory" and sub == "rescore":
        from . import trajectory
        return trajectory.rescore(run_dirs=args.run_dirs, cap=args.cap)

    if command == "report":
        return _report(args)

    if command == "audit":
        return _audit(args)

    if command == "expert":
        from .expert import rubric, sample
        return (sample.run() if args.sub == "sample" else rubric.aggregate())

    raise SystemExit(f"Unhandled command: {command} {sub}")


def _one(value: str | None, default: tuple[str, ...], what: str) -> str:
    """The single slot or tag a foreground run takes."""
    items = [v for v in (value.replace(",", " ").split() if value else default) if v]
    if len(items) != 1:
        raise SystemExit(
            f"--foreground runs exactly one {what}; got {items or 'none'}. "
            f"Name it with --{what}s."
        )
    return items[0]


def _run(args) -> int:
    """`run <experiment>`: launch tmux sessions, or one run in this process."""
    if not args.foreground:
        from .launch import launch
        return launch(args.sub, dry_run=args.dry_run, slots=args.slots, tags=args.tags,
                      agents=args.agents, judge=args.judge)

    from .config import current
    from .runner import run_one
    profile = current().profile(args.sub)
    slot = _one(args.slots, profile.slots, "slot")
    tag = _one(args.tags, profile.tags, "tag")
    if args.dry_run:
        print(f"would generate: {args.sub} slot={slot} tag={tag} "
              f"agents={args.agents or ','.join(profile.agents)} "
              f"judge={'on' if args.judge else 'off'}")
        return 0
    agents = [a.strip() for a in args.agents.split(",") if a.strip()] if args.agents else None
    return run_one(experiment=args.sub, slot=slot, tag=tag, agents=agents,
                   rate_limit=args.rate_limit, judge=args.judge)


def _report(args) -> int:
    from . import report
    out = args.outdir
    if args.sub == "all":
        report.run_all(comparison_pooled=args.pooled, ablation_pooled=args.ablation_pooled,
                       outdir=out, runs_glob=args.runs_glob, do_sync=not args.no_sync)
    elif args.sub == "tables":
        report.tables.run(pooled_path=args.pooled, outdir=out)
    elif args.sub == "figures":
        report.figures.run(pooled_path=args.pooled, outdir=out, runs_glob=args.runs_glob)
    elif args.sub == "cost":
        report.cost.run(runs_glob=args.runs_glob, outdir=out)
    elif args.sub == "sensitivity":
        report.sensitivity.run(pooled_path=args.pooled, outdir=out)
    elif args.sub == "ablation-tables":
        report.ablation_tables.run(pooled_path=args.ablation_pooled, outdir=out)
    elif args.sub == "ablation-figures":
        report.ablation_figures.run(pooled_path=args.ablation_pooled, outdir=out)
    elif args.sub == "facts":
        report.facts.run(comparison_pooled=args.pooled, ablation_pooled=args.ablation_pooled,
                         outdir=out, brief=args.brief)
    elif args.sub == "sync":
        report.sync.run(srcdir=out)
    return 0


def _audit(args) -> int:
    # One at a time: `audit repair` is the only stage that needs the evaluator
    # (and through it openai and langchain), so importing the set eagerly would
    # make every other audit require a dependency it has no use for.
    if args.sub == "preflight":
        from .audit import preflight
        return preflight.run(skip_smoke=args.skip_smoke, min_disk_gb=args.min_disk_gb)
    if args.sub == "inflight":
        from .audit import inflight
        return inflight.run(experiment=args.experiment)
    if args.sub == "postrun":
        from .audit import postrun
        return postrun.run(run_dirs=args.run_dirs)
    if args.sub == "repair":
        from .audit import repair
        return repair.run(
            run_dirs=args.run_dirs, dry_run=args.dry_run, yes=args.yes,
            max_attempts=args.max_attempts, skip_audit=args.skip_audit,
            verbose=args.verbose,
            **({"backup_suffix": args.backup_suffix} if args.backup_suffix else {}),
        )
    from .audit import artifacts
    return artifacts.run(strict=args.strict, check_docs=not args.no_docs)


if __name__ == "__main__":
    sys.exit(main())

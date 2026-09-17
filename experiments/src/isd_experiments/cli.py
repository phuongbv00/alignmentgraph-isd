"""`isd-exp` -- the experiment, one command per stage.

Subcommands are grouped to read down the roadmap, so the order you run them is
the order they appear in `--help`, and a stage nobody has built yet is visible
as a gap rather than absent:

    setup / doctor            once per machine
    data / serve / bloom      inputs and serving
    tune                      cheap check before spending
    freeze / audit preflight  lock the version, verify the endpoints
    comparison / ablation     the two official experiments
    score / trajectory        offline scoring, no regeneration
    report / audit artifacts  the manuscript's numbers
    expert                    human validation
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import paths


def _p(value: str) -> Path:
    return Path(value).expanduser()


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

    serve = sub.add_parser("serve", help="write serving endpoints into .env").add_subparsers(
        dest="sub", required=True)
    for name, helptext in (("sync-agents", "agent model endpoints"),
                           ("sync-embed", "embedding endpoints for the alignment panel")):
        s = serve.add_parser(name, help=helptext)
        s.add_argument("--dry-run", action="store_true", help="print the block, write nothing")

    bloom = sub.add_parser("bloom", help="the Bloom classifier arm").add_subparsers(
        dest="sub", required=True)
    bt = bloom.add_parser("train", help="fine-tune the 6-way head")
    bt.add_argument("--train", type=_p, required=True), bt.add_argument("--output-dir", type=_p)
    bv = bloom.add_parser("validate", help="score an arm against expert labels")
    bv.add_argument("labels", type=_p, nargs="?")
    bv.add_argument("--bloom-checkpoint", type=_p), bv.add_argument("--out", type=_p)

    # ── cheap check ──────────────────────────────────────────────────────
    g = sub.add_parser(
        "tune", help="cost and budget calibration on the training split",
    ).add_subparsers(dest="sub", required=True)
    r = g.add_parser("run", help="launch")
    r.add_argument("--dry-run", action="store_true",
                   help="print the launch plan and exit")
    r.add_argument("--slots"), r.add_argument("--tags"), r.add_argument("--agents")

    # ── freeze ───────────────────────────────────────────────────────────
    fr = sub.add_parser("freeze", help="record the version an experiment ran on").add_subparsers(
        dest="sub", required=True)
    fw = fr.add_parser("write", help="write the manifest")
    fw.add_argument("--tag"), fw.add_argument("--out", type=_p)
    fr.add_parser("verify", help="compare the working tree against a manifest")

    # ── the two official experiments ─────────────────────────────────────
    for name, helptext in (
        ("comparison", "the proposed system against baselines, across the ladder"),
        ("ablation", "the 2x2 factorial over decomposition and substrate"),
    ):
        g = sub.add_parser(name, help=helptext).add_subparsers(dest="sub", required=True)
        r = g.add_parser("run", help="launch")
        r.add_argument("--dry-run", action="store_true")
        r.add_argument("--slots"), r.add_argument("--tags"), r.add_argument("--agents")
        pl = g.add_parser("pool", help="pool the runs into a single JSON")
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

    # ── offline scoring ──────────────────────────────────────────────────
    sc = sub.add_parser("score", help="score the alignment panel (no LLM, no regeneration)")
    sc.add_argument("run_dirs", nargs="*", metavar="RUN_DIR")
    sc.add_argument("--encoder-presets", default=""), sc.add_argument("--bloom-presets", default="")
    sc.add_argument("--all-arms", action="store_true", help="the whole sensitivity star")
    sc.add_argument("--reaggregate", action="store_true"), sc.add_argument("--overwrite", action="store_true")
    sc.add_argument("--embed-cache-only", action="store_true")
    sc.add_argument("--limit", type=int)

    tr = sub.add_parser("trajectory", help="re-score saved trajectories").add_subparsers(
        dest="sub", required=True)
    trs = tr.add_parser("rescore", help="diagnostic layer at a higher tool-call cap")
    trs.add_argument("run_dirs", nargs="*", metavar="RUN_DIR")
    trs.add_argument("--cap", type=int, default=120)

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
    aud.add_parser("preflight", help="endpoints, auth, flags, disk")
    ai = aud.add_parser("inflight", help="red flags in the live logs")
    ai.add_argument("--experiment", default=None)
    ap_ = aud.add_parser("postrun", help="completeness and integrity of finished runs")
    ap_.add_argument("run_dirs", nargs="*", metavar="RUN_DIR")
    ar = aud.add_parser("repair", help="re-run the LLM judge on cells lost to a transient failure")
    ar.add_argument("run_dirs", nargs="*", metavar="RUN_DIR")
    ar.add_argument("--dry-run", action="store_true")
    aa = aud.add_parser("artifacts", help="the final gate on generated artifacts")
    aa.add_argument("--strict", action="store_true"), aa.add_argument("--no-docs", action="store_true")

    ex = sub.add_parser("expert", help="human validation package").add_subparsers(
        dest="sub", required=True)
    ex.add_parser("sample", help="draw a blinded subset for expert review")
    ex.add_parser("aggregate", help="combine returned score sheets")

    h = sub.add_parser("help", help="show help for a stage, e.g. `help comparison pool`")
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

    if command == "serve":
        from .serve import agents as serve_agents
        from .serve import embed as serve_embed
        mod = serve_agents if sub == "sync-agents" else serve_embed
        return mod.run(dry_run=args.dry_run)

    if command == "bloom":
        from .alignment import bloom
        if sub == "train":
            return bloom.train(train_csv=args.train, output_dir=args.output_dir)
        return bloom.validate(labels=args.labels, checkpoint=args.bloom_checkpoint,
                              out=args.out)

    if command in {"tune", "comparison", "ablation"} and sub == "run":
        from .launch import launch
        return launch(command, dry_run=args.dry_run, slots=args.slots,
                      tags=args.tags, agents=args.agents)

    if command == "comparison" and sub == "pool":
        from .pool import comparison
        comparison.run(experiment="comparison", patterns=args.patterns or None,
                       out=args.out, encoders=args.encoders,
                       auto_encoders=args.auto_encoders, auto_bloom=args.auto_bloom,
                       agents=args.agents.split(",") if args.agents else None)
        return 0

    if command == "ablation" and sub == "pool":
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

    if command == "score":
        from .alignment import score
        return score.run(run_dirs=args.run_dirs, encoder_presets=args.encoder_presets,
                         bloom_presets=args.bloom_presets, all_arms=args.all_arms,
                         reaggregate=args.reaggregate, overwrite=args.overwrite,
                         cache_only=args.embed_cache_only, limit=args.limit)

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
        return preflight.run()
    if args.sub == "inflight":
        from .audit import inflight
        return inflight.run(experiment=args.experiment)
    if args.sub == "postrun":
        from .audit import postrun
        return postrun.run(run_dirs=args.run_dirs)
    if args.sub == "repair":
        from .audit import repair
        return repair.run(run_dirs=args.run_dirs, dry_run=args.dry_run)
    from .audit import artifacts
    return artifacts.run(strict=args.strict, check_docs=not args.no_docs)


if __name__ == "__main__":
    sys.exit(main())

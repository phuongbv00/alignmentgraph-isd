from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import DesignBrief, HarnessRunConfig, MemoryConfig, run_design_brief


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="alignmentgraph-isd",
        description="Run AlignmentGraph-ISD on a canonical DesignBrief JSON file.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    run_parser = subparsers.add_parser("run", help="Run one DesignBrief through the harness.")
    run_parser.add_argument("--input", required=True, help="Path to a DesignBrief-shaped JSON file.")
    run_parser.add_argument("--output", required=True, help="Path for the full harness result JSON.")
    run_parser.add_argument("--trajectory", help="Optional path for trajectory JSON only.")
    run_parser.add_argument("--ablation", default="full", help="Ablation preset key.")
    run_parser.add_argument("--training-program-id", default="", help="Persistent app graph id.")
    run_parser.add_argument("--session-id", default="", help="Persistent app session id.")

    args = parser.parse_args(argv)
    if args.command == "run":
        return _run(args)
    parser.error(f"Unsupported command: {args.command}")
    return 2


def _run(args: argparse.Namespace) -> int:
    payload = json.loads(Path(args.input).read_text(encoding="utf-8"))
    design_brief = DesignBrief.model_validate(payload)
    config = HarnessRunConfig.from_ablation(
        args.ablation,
        memory=MemoryConfig(
            training_program_id=args.training_program_id,
            session_id=args.session_id,
        ),
    )

    if config.llm_factory is None:
        sys.stderr.write(
            "alignmentgraph-isd run requires a configured llm_factory. "
            "For benchmark integration, map the scenario to DesignBrief outside "
            "the harness and call run_design_brief(..., config) directly.\n"
        )
        return 2

    result = run_design_brief(design_brief, config)
    Path(args.output).write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    if args.trajectory:
        Path(args.trajectory).write_text(
            json.dumps(result.get("trajectory", {}), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

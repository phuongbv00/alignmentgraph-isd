from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import DesignBrief, HarnessRunConfig, llm_factory_from_env, run_design_brief


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
    # Model selection (falls back to AGENT_MODEL_* env vars). Requires the
    # optional [llm] extra: pip install 'alignmentgraph-isd[llm]'.
    run_parser.add_argument("--model-name", default="", help="Chat model name (env: AGENT_MODEL_NAME).")
    run_parser.add_argument(
        "--api-spec",
        default="",
        help="API contract: openai_compatible | anthropic (env: AGENT_MODEL_API_SPEC, default openai_compatible).",
    )
    run_parser.add_argument("--base-url", default="", help="OpenAI-compatible base URL (env: AGENT_MODEL_BASE_URL).")
    run_parser.add_argument("--api-key", default="", help="API key (env: AGENT_MODEL_API_KEY).")
    run_parser.add_argument("--temperature", type=float, default=None, help="Sampling temperature (env: AGENT_MODEL_TEMPERATURE).")
    run_parser.add_argument("--max-tokens", type=int, default=None, help="Max output tokens (env: AGENT_MODEL_MAX_TOKENS).")

    args = parser.parse_args(argv)
    if args.command == "run":
        return _run(args)
    parser.error(f"Unsupported command: {args.command}")
    return 2


def _run(args: argparse.Namespace) -> int:
    payload = json.loads(Path(args.input).read_text(encoding="utf-8"))
    design_brief = DesignBrief.model_validate(payload)
    config = HarnessRunConfig.from_ablation(args.ablation)
    config.llm_factory = llm_factory_from_env(
        model_name=args.model_name,
        api_spec=args.api_spec,
        base_url=args.base_url,
        api_key=args.api_key,
        temperature=args.temperature,
        max_tokens=args.max_tokens,
    )

    if config.llm_factory is None:
        sys.stderr.write(
            "alignmentgraph-isd run requires a model. Pass --model-name (and "
            "--api-key/--base-url as needed) or set AGENT_MODEL_NAME / "
            "AGENT_MODEL_API_KEY / AGENT_MODEL_BASE_URL. Provider clients install "
            "with: pip install 'alignmentgraph-isd[llm]'.\n"
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

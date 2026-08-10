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
    run_parser.add_argument(
        "--graph",
        help="Optional path stem for the alignment-graph dump (writes <stem>.json + <stem>.dot).",
    )
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

    serve_parser = subparsers.add_parser(
        "serve", help="Run the demo web app. Requires: pip install 'alignmentgraph-isd[server]'."
    )
    serve_parser.add_argument("--host", default="127.0.0.1", help="Bind address (default 127.0.0.1).")
    serve_parser.add_argument("--port", type=int, default=8000, help="Port (default 8000).")
    serve_parser.add_argument("--reload", action="store_true", help="Reload on code changes (development).")
    serve_parser.add_argument(
        "--data-root",
        default="",
        help="Where runs and the database are stored (env: AGISD_SERVER_DATA_ROOT).",
    )
    serve_parser.add_argument(
        "--serve-spa",
        action="store_true",
        help="Also serve the built webapp, so the demo is one process on one URL "
             "(build it first: cd src/alignmentgraph_isd/webapp && npm run build).",
    )

    args = parser.parse_args(argv)
    if args.command == "run":
        return _run(args)
    if args.command == "serve":
        return _serve(args)
    parser.error(f"Unsupported command: {args.command}")
    return 2


def _serve(args: argparse.Namespace) -> int:
    import os

    # Settings are read from the environment, so flags are applied by setting it
    # — one source of configuration rather than two that can disagree.
    if args.data_root:
        os.environ["AGISD_SERVER_DATA_ROOT"] = args.data_root
    if args.serve_spa:
        os.environ["AGISD_SERVER_SERVE_SPA"] = "1"

    # Imported here, not at module scope: the benchmark installs this package
    # without the [server] extra and must never pay for FastAPI on import.
    try:
        import uvicorn
    except ImportError:
        sys.stderr.write(
            "alignmentgraph-isd serve needs the web app dependencies.\n"
            "Install them with: pip install 'alignmentgraph-isd[server]'\n"
        )
        return 2

    # Single process by design: live runs and their event buffers are in-process
    # state, so a second worker would not find them. No --workers flag exists.
    uvicorn.run(
        "alignmentgraph_isd.server.app:get_app",
        factory=True,
        host=args.host,
        port=args.port,
        reload=args.reload,
        log_level="info",
    )
    return 0


def _run(args: argparse.Namespace) -> int:
    payload = json.loads(Path(args.input).read_text(encoding="utf-8"))
    design_brief = DesignBrief.model_validate(payload)
    config = HarnessRunConfig()
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
    if args.graph:
        stem = Path(args.graph)
        stem.parent.mkdir(parents=True, exist_ok=True)
        stem.with_suffix(".json").write_text(
            json.dumps(result.get("graph", {}), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        stem.with_suffix(".dot").write_text(result.get("graph_dot", ""), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

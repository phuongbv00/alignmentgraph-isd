"""RQ2 refinement-session runner: 4 conditions over the IT/SE case-study programs.

Conditions (all receive the same prior design + cumulative brief + edit request;
they differ only in the refinement mechanism):

* ``harness_targeted_refine``  — AlignmentGraph-ISD, targeted cascade + repair.
* ``harness_full_regen``       — AlignmentGraph-ISD, ``scope=regenerate_all``
                                 (isolates the scoping mechanism within the harness).
* ``react_full_regen``         — ReAct-ADDIE baseline clone, full ``run()`` on the
                                 cumulative scenario each round (dilemma horn 1).
* ``react_targeted_refine``    — ReAct-ADDIE clone's ``refine()``: previous output +
                                 edit request, no alignment control (dilemma horn 2).

Artifacts: per-session result JSON under ``results/{condition}/{program}/``,
graph versions under ``memory/`` (harness conditions), ``results/manifest.json``.
``compute_metrics.py`` turns these into the four process metrics.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

CASE_STUDY_DIR = Path(__file__).resolve().parent
REPO_ROOT = CASE_STUDY_DIR.parent
PACKAGE_ROOT = REPO_ROOT / "alignmentgraph-isd"  # for --fake-llm test fixtures

from alignmentgraph_isd import (  # noqa: E402
    DesignBrief,
    HarnessRunConfig,
    MemoryConfig,
    llm_factory_from_env,
    run_design_brief,
)
from alignmentgraph_isd.rag.agent import RetrievalAgent, RetrievalTool  # noqa: E402

HARNESS_CONDITIONS = ("harness_targeted_refine", "harness_full_regen")
REACT_CONDITIONS = ("react_full_regen", "react_targeted_refine")
ALL_CONDITIONS = HARNESS_CONDITIONS + REACT_CONDITIONS


# ── Brief assembly ─────────────────────────────────────────────────────────────

def apply_overlay(brief: dict, overlay: dict) -> dict:
    """Apply one round's brief_overlay: append goals, deep-merge dicts, replace scalars."""
    merged = json.loads(json.dumps(brief))  # deep copy
    for key, value in overlay.items():
        if key == "learning_goals_append":
            merged.setdefault("learning_goals", []).extend(value)
        elif isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key].update(value)
        else:
            merged[key] = value
    return merged


def cumulative_brief(base_brief: dict, rounds: list[dict], upto: int) -> dict:
    """Brief for round ``upto``: base brief + overlays of rounds 1..upto (1-based)."""
    brief = base_brief
    for r in rounds[:upto]:
        brief = apply_overlay(brief, r.get("brief_overlay", {}))
    return brief


def brief_to_react_scenario(brief: dict) -> dict:
    """Map a DesignBrief JSON onto the react agent's scenario contract."""
    context = dict(brief.get("context", {}))
    context.setdefault("target_audience", brief.get("target_audience", ""))
    context.setdefault("duration", brief.get("duration", ""))
    return {
        "scenario_id": brief.get("id", "unknown"),
        "title": brief.get("title", ""),
        "context": context,
        "learning_goals": brief.get("learning_goals", []),
    }


# ── Config / model assembly ────────────────────────────────────────────────────

def _parse_agent_frontmatter(text: str) -> tuple[dict, str]:
    """Parse YAML-ish frontmatter from AGENT.md. Returns (meta dict, system_prompt body)."""
    import re
    if not text.startswith("---"):
        return {}, text
    parts = text.split("---", 2)
    if len(parts) < 3:
        return {}, text
    meta: dict = {}
    for line in parts[1].strip().splitlines():
        if ":" not in line:
            continue
        key, _, val = line.partition(":")
        val = val.strip()
        if val.startswith("["):
            meta[key.strip()] = [
                s.strip().strip("\"'")
                for s in re.split(r",\s*", val.strip("[] "))
                if s.strip()
            ]
        else:
            meta[key.strip()] = val
    return meta, parts[2].strip()


def _load_tool(tool_path: Path) -> "RetrievalTool | None":
    import importlib.util
    spec = importlib.util.spec_from_file_location(tool_path.stem, tool_path)
    mod = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(mod)
    except Exception as exc:
        sys.stderr.write(f"[warn] failed to load tool {tool_path}: {exc}\n")
        return None
    fn = getattr(mod, "invoke", None)
    if not callable(fn):
        return None
    return RetrievalTool(
        name=getattr(mod, "NAME", tool_path.stem),
        description=getattr(mod, "DESCRIPTION", ""),
        fn=fn,
    )


def load_retrieval_subagents() -> list:
    """Load each agents/<agent_id>/ directory as a plug-and-play RetrievalAgent.

    Each directory must contain AGENT.md (YAML frontmatter + system prompt) and
    optionally tools/ (Python scripts) and/or corpus/ (topic .md files).
    - tools/ present → agentic LLM loop (system_prompt required)
    - corpus/ present, no tools → deterministic keyword search via generated tool
    - neither → agent is skipped
    """
    subagents = []
    for agent_dir in sorted((CASE_STUDY_DIR / "agents").iterdir()):
        if not agent_dir.is_dir():
            continue
        agent_md = agent_dir / "AGENT.md"
        if not agent_md.exists():
            continue
        meta, system_prompt = _parse_agent_frontmatter(agent_md.read_text(encoding="utf-8"))
        tools: list[RetrievalTool] = []
        tools_dir = agent_dir / "tools"
        if tools_dir.exists():
            for tool_path in sorted(tools_dir.glob("*.py")):
                tool = _load_tool(tool_path)
                if tool:
                    tools.append(tool)
        if system_prompt and tools:
            subagents.append(RetrievalAgent(
                meta.get("name", agent_dir.name),
                meta.get("source_type", "corpus"),
                description=meta.get("description", ""),
                domains=meta.get("domains"),
                keywords=meta.get("keywords"),
                system_prompt=system_prompt,
                tools=tools,
            ))
        elif (agent_dir / "corpus").exists():
            corpus_dir = agent_dir / "corpus"
            corpus: dict = {}
            for f in sorted(corpus_dir.glob("*.md")):
                topic = f.stem.replace("_", " ")
                corpus[topic] = [s.strip() for s in f.read_text(encoding="utf-8").split("\n\n") if s.strip()]
            if corpus:
                def _make_search(c: dict):
                    def search(query: str = "") -> list[str]:
                        needle = query.lower()
                        return [s for k, v in c.items() for s in v if not needle or needle in k.lower() or needle in s.lower()]
                    return search
                subagents.append(RetrievalAgent(
                    meta.get("name", agent_dir.name),
                    meta.get("source_type", "corpus"),
                    description=meta.get("description", ""),
                    domains=meta.get("domains"),
                    keywords=meta.get("keywords"),
                    tools=[RetrievalTool("search_corpus", "Search corpus snippets", _make_search(corpus))],
                ))
    return subagents


def build_harness_llm_factory(args: argparse.Namespace):
    if args.fake_llm:
        sys.path.insert(0, str(PACKAGE_ROOT / "tests"))
        from conftest import FakeChatModel

        class _FakeHarnessModel(FakeChatModel):
            """Extends the canned model so rehearsals exercise on-demand retrieval:
            the retrieval coordinator opts in (single, first agent) and the
            retrieval-agent loop answers with one canned snippet."""

            def invoke(self, messages):
                system = ""
                for message in messages:
                    role = message.get("role") if isinstance(message, dict) else ""
                    if role == "system":
                        system = message.get("content", "")
                        break

                class R:
                    usage_metadata = None

                if "retrieval coordinator" in system:
                    r = R()
                    r.content = json.dumps({
                        "retrieve": True, "agents": [], "strategy": "single", "queries": {},
                    })
                    return r
                if "retrieval agent" in system.lower():
                    r = R()
                    r.content = json.dumps({
                        "content": ["canned domain snippet (rehearsal)"],
                        "citations": ["corpus:rehearsal"],
                    })
                    return r
                return super().invoke(messages)

        return lambda: _FakeHarnessModel()
    factory = llm_factory_from_env(
        model_name=args.model_name,
        api_spec=args.api_spec,
        base_url=args.base_url,
        api_key=args.api_key,
        temperature=args.temperature,
        max_tokens=args.max_tokens,
    )
    if factory is None:
        sys.stderr.write(
            "A model is required: pass --model-name/--api-key/--base-url or set "
            "AGENT_MODEL_NAME / AGENT_MODEL_API_KEY / AGENT_MODEL_BASE_URL "
            "(or use --fake-llm for a dress rehearsal).\n"
        )
        raise SystemExit(2)
    return factory


def build_react_agent(args: argparse.Namespace):
    from react_isd_baseline import ReActISDBaselineAgent, settings_from_env

    if args.fake_llm:
        import react_isd_baseline.agent as react_agent_mod
        from react_isd_baseline.llm import LLMSettings, TrackedChatModel
        sys.path.insert(0, str(PACKAGE_ROOT / "tests"))
        from conftest import FakeChatModel

        class _FakeReactModel:
            """Adapt the harness test fake to the react prompt-string interface."""

            _SECTION_KEYS = {
                "A-1~4": "analysis", "D-11": "design", "Dev-19": "development",
                "I-24": "implementation", "E-28": "evaluation",
            }

            def invoke(self, prompt: str):
                import conftest

                class R:
                    usage_metadata = None

                r = R()
                if "EDIT REQUEST" in prompt:
                    r.content = json.dumps({"unchanged": True})
                    return r
                for marker, section in self._SECTION_KEYS.items():
                    if marker in prompt:
                        payload = conftest._single_agent_payload()[section]
                        r.content = json.dumps(payload, ensure_ascii=False)
                        return r
                r.content = "{}"
                return r

        def _fake_create(settings, tracker):
            return TrackedChatModel(_FakeReactModel(), tracker)

        react_agent_mod.create_chat_model = _fake_create
        return ReActISDBaselineAgent(LLMSettings(model_name="fake"))

    return ReActISDBaselineAgent(settings_from_env(
        model_name=args.model_name,
        api_spec=args.api_spec,
        base_url=args.base_url,
        api_key=args.api_key,
        temperature=args.temperature,
        max_tokens=args.max_tokens,
    ))


def build_harness_config(args, training_program_id: str, llm_factory) -> HarnessRunConfig:
    config = HarnessRunConfig.from_ablation(args.ablation, memory=MemoryConfig(
        enabled=True,
        persist=True,
        root_dir=str(CASE_STUDY_DIR / "memory"),
        training_program_id=training_program_id,
    ))
    config.llm_factory = llm_factory
    config.retrieval_subagents = load_retrieval_subagents()
    return config


# ── Result bookkeeping ─────────────────────────────────────────────────────────

def write_result(condition: str, program_id: str, round_index: int, result: dict) -> Path:
    out_dir = CASE_STUDY_DIR / "results" / condition / program_id
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"session_{round_index:02d}.json"
    out_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    return out_path


def manifest_row(*, condition, program_id, round_index, result_path, args, extra=None) -> dict:
    row = {
        "program_id": program_id,
        "condition": condition,
        "round": round_index,
        "result_file": str(result_path.relative_to(CASE_STUDY_DIR)),
        "ablation": args.ablation if condition in HARNESS_CONDITIONS else "",
        "model": "fake" if args.fake_llm else (args.model_name or "env:AGENT_MODEL_NAME"),
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    row.update(extra or {})
    return row


# ── Harness conditions ─────────────────────────────────────────────────────────

def run_harness_session(
    args, llm_factory, *,
    program_id, condition, round_index, brief_payload,
    expected_session_type, expected_version,
) -> dict:
    label = f"[{condition}] {program_id} round {round_index}"
    print(f"{label}: session starting", flush=True)
    brief = DesignBrief.model_validate(brief_payload)
    training_program_id = f"{program_id}-{condition}"
    config = build_harness_config(args, training_program_id, llm_factory)
    result = run_design_brief(brief, config)

    memory_meta = result["metadata"]["memory"]
    if memory_meta["session_type"] != expected_session_type:
        raise RuntimeError(f"{label}: expected session_type={expected_session_type!r}, got {memory_meta['session_type']!r}")
    if memory_meta["committed_graph_version"] != expected_version:
        raise RuntimeError(f"{label}: expected committed version {expected_version}, got {memory_meta['committed_graph_version']}")
    if not memory_meta["persisted"]:
        raise RuntimeError(f"{label}: graph version was not persisted: {memory_meta['persist_error']}")

    out_path = write_result(condition, program_id, round_index, result)
    tokens = result["trajectory"].get("token_usage", {})
    print(
        f"{label}: done — v{memory_meta['committed_graph_version']}, "
        f"llm_calls={result['trajectory'].get('llm_calls', 0)}, "
        f"tokens={tokens.get('prompt_tokens', 0)}+{tokens.get('completion_tokens', 0)}, "
        f"latency={result['trajectory'].get('latency_ms', 0):.0f}ms",
        flush=True,
    )
    return manifest_row(
        condition=condition, program_id=program_id, round_index=round_index,
        result_path=out_path, args=args,
        extra={
            "training_program_id": training_program_id,
            "storage_id": memory_meta["storage_id"],
            "session_id": memory_meta["session_id"],
            "session_type": memory_meta["session_type"],
            "base_graph_version": memory_meta["base_graph_version"],
            "committed_graph_version": memory_meta["committed_graph_version"],
        },
    )


def run_harness_condition(args, llm_factory, program: dict, condition: str, manifest: list[dict]) -> None:
    pid = program["program_id"]
    base_brief = json.loads((CASE_STUDY_DIR / program["brief"]).read_text(encoding="utf-8"))
    rounds = program["rounds"][: args.rounds_limit] if args.rounds_limit else program["rounds"]

    manifest.append(run_harness_session(
        args, llm_factory,
        program_id=pid, condition=condition, round_index=0,
        brief_payload=base_brief,
        expected_session_type="init", expected_version=1,
    ))
    for k, round_spec in enumerate(rounds, start=1):
        brief = cumulative_brief(base_brief, rounds, k)
        brief["refinement_request"] = dict(round_spec["refinement_request"])
        if condition == "harness_full_regen":
            brief["refinement_request"]["scope"] = "regenerate_all"
        manifest.append(run_harness_session(
            args, llm_factory,
            program_id=pid, condition=condition, round_index=k,
            brief_payload=brief,
            expected_session_type="refinement", expected_version=k + 1,
        ))


# ── React conditions ───────────────────────────────────────────────────────────

def run_react_conditions(args, program: dict, wanted: set[str], manifest: list[dict]) -> None:
    """Run the react baseline chains. Round 0 (full generation of the base brief)
    is executed once and shared by both react conditions."""
    pid = program["program_id"]
    base_brief = json.loads((CASE_STUDY_DIR / program["brief"]).read_text(encoding="utf-8"))
    rounds = program["rounds"][: args.rounds_limit] if args.rounds_limit else program["rounds"]
    agent = build_react_agent(args)

    print(f"[react] {pid} round 0: shared init run", flush=True)
    init_result = agent.run(brief_to_react_scenario(base_brief))
    for condition in wanted:
        out_path = write_result(condition, pid, 0, init_result)
        manifest.append(manifest_row(
            condition=condition, program_id=pid, round_index=0,
            result_path=out_path, args=args,
            extra={"mode": "run", "shared_init": True},
        ))

    if "react_full_regen" in wanted:
        for k in range(1, len(rounds) + 1):
            print(f"[react_full_regen] {pid} round {k}", flush=True)
            scenario = brief_to_react_scenario(cumulative_brief(base_brief, rounds, k))
            result = agent.run(scenario)
            out_path = write_result("react_full_regen", pid, k, result)
            manifest.append(manifest_row(
                condition="react_full_regen", program_id=pid, round_index=k,
                result_path=out_path, args=args, extra={"mode": "run"},
            ))

    if "react_targeted_refine" in wanted:
        previous_output = init_result["addie_output"]
        for k, round_spec in enumerate(rounds, start=1):
            print(f"[react_targeted_refine] {pid} round {k}", flush=True)
            # The practitioner flow: the brief the previous output was built from,
            # the previous output itself, and the new edit request.
            scenario = brief_to_react_scenario(cumulative_brief(base_brief, rounds, k - 1))
            edit_request = round_spec["refinement_request"].get("instruction") or round_spec["refinement_request"].get("summary", "")
            result = agent.refine(scenario, previous_output, edit_request)
            out_path = write_result("react_targeted_refine", pid, k, result)
            manifest.append(manifest_row(
                condition="react_targeted_refine", program_id=pid, round_index=k,
                result_path=out_path, args=args,
                extra={"mode": "refine", "unchanged_phases": result["metadata"].get("unchanged_phases", [])},
            ))
            previous_output = result["addie_output"]


# ── Entrypoint ─────────────────────────────────────────────────────────────────

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--scenarios", default=str(CASE_STUDY_DIR / "scenarios"))
    parser.add_argument("--programs", default="", help="Comma-separated program ids (default: all).")
    parser.add_argument(
        "--conditions", default="all",
        help=f"Comma-separated conditions or 'all'. Valid: {', '.join(ALL_CONDITIONS)}",
    )
    parser.add_argument("--rounds-limit", type=int, default=0, help="Run only the first N refinement rounds per program.")
    parser.add_argument("--ablation", default="case_study", help="Harness ablation preset (case_study = full + RAG).")
    parser.add_argument("--fake-llm", action="store_true", help="Use canned fake models (no network).")
    parser.add_argument("--dry-run", action="store_true", help="Print the planned sessions and exit.")
    parser.add_argument("--model-name", default="", help="Chat model name (env: AGENT_MODEL_NAME).")
    parser.add_argument("--api-spec", default="", help="openai_compatible | anthropic (env: AGENT_MODEL_API_SPEC).")
    parser.add_argument("--base-url", default="", help="OpenAI-compatible base URL (env: AGENT_MODEL_BASE_URL).")
    parser.add_argument("--api-key", default="", help="API key (env: AGENT_MODEL_API_KEY).")
    parser.add_argument("--temperature", type=float, default=None)
    parser.add_argument("--max-tokens", type=int, default=None)
    args = parser.parse_args(argv)

    wanted_conditions = (
        set(ALL_CONDITIONS) if args.conditions == "all"
        else {c.strip() for c in args.conditions.split(",") if c.strip()}
    )
    unknown = wanted_conditions - set(ALL_CONDITIONS)
    if unknown:
        sys.stderr.write(f"Unknown condition(s): {sorted(unknown)}. Valid: {', '.join(ALL_CONDITIONS)}\n")
        return 2

    scenarios_path = Path(args.scenarios)
    all_programs = [
        json.loads(p.read_text(encoding="utf-8"))
        for p in sorted(scenarios_path.glob("*.json"))
    ]
    wanted_programs = {p.strip() for p in args.programs.split(",") if p.strip()}
    programs = [p for p in all_programs if not wanted_programs or p["program_id"] in wanted_programs]
    if not programs:
        sys.stderr.write(f"No programs matched {sorted(wanted_programs)!r}.\n")
        return 2

    if args.dry_run:
        for program in programs:
            rounds = program["rounds"][: args.rounds_limit] if args.rounds_limit else program["rounds"]
            for condition in ALL_CONDITIONS:
                if condition in wanted_conditions:
                    print(f"[{condition}] {program['program_id']}: init + {len(rounds)} round(s)")
        return 0

    harness_wanted = wanted_conditions & set(HARNESS_CONDITIONS)
    react_wanted = wanted_conditions & set(REACT_CONDITIONS)
    harness_factory = build_harness_llm_factory(args) if harness_wanted else None

    manifest_path = CASE_STUDY_DIR / "results" / "manifest.json"
    manifest: list[dict] = json.loads(manifest_path.read_text(encoding="utf-8")) if manifest_path.exists() else []

    try:
        for program in programs:
            for condition in HARNESS_CONDITIONS:
                if condition in harness_wanted:
                    run_harness_condition(args, harness_factory, program, condition, manifest)
            if react_wanted:
                run_react_conditions(args, program, react_wanted, manifest)
    finally:
        manifest_path.parent.mkdir(parents=True, exist_ok=True)
        manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"Manifest: {manifest_path} ({len(manifest)} session(s) total)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

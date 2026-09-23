"""Generate one run: every agent of a profile, on every scenario of its split,
under one model.

What a run directory holds, and what its files are called, is fixed by what
reads it -- the LLM judge, the alignment scorer, pooling, the audits -- so it is
kept exactly as the benchmark laid it out::

    <results>/<dataset>_benchmark_<model>_<tag>_<timestamp>/
        benchmark_summary.json   SUMMARY.md   benchmark_progress.log
        <dataset>/<scenario_id>/
            <agent>_output.json      the ADDIE deliverable
            <agent>_trajectory.json  trajectory + metadata (token_usage, time)
            <agent>_graph.json       the proposed system's graph dump, if any
            <agent>_prose.json       a prose arm's blackboard, if any
            <agent>_log.txt

Generation only. Scoring is `isd-exp judge llm` and `isd-exp judge alignment`,
which read a finished run and never regenerate it; a run records that it has
not been judged yet (``evaluation_deferred``) so the audits can tell "not judged"
from "judging failed".
"""

from __future__ import annotations

import json
import os
import threading
import time
import traceback
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path

from .. import paths
from ..config import Experiment
from . import agents as registry
from . import llm, summary


class Progress:
    """Console lines and ``benchmark_progress.log``, in the forms the in-flight
    audit counts (a ``✅``/``❌`` per agent, a fresh log while a run is alive)."""

    def __init__(self, log_file: Path, total_scenarios: int, total_agents: int):
        self.log_file = log_file
        self.total_scenarios = total_scenarios
        self.total_agents = total_agents
        self.completed = 0
        self.start = time.time()
        self.lock = threading.Lock()
        self._write(
            f"ISD run log\nStart time: {datetime.now():%Y-%m-%d %H:%M:%S}\n"
            f"Total scenarios: {total_scenarios}\nTotal agents: {total_agents}\n\n",
            mode="w",
        )

    def _write(self, text: str, mode: str = "a") -> None:
        with open(self.log_file, mode, encoding="utf-8") as fh:
            fh.write(text)

    def _stamp(self) -> str:
        return datetime.now().strftime("%H:%M:%S")

    def scenario_started(self, scenario_id: str, index: int) -> None:
        with self.lock:
            print(f"\n[{index + 1}/{self.total_scenarios}] {scenario_id}", flush=True)
            self._write(f"\n[{self._stamp()}] Start: {scenario_id} "
                        f"({index + 1}/{self.total_scenarios})\n")

    def agent_finished(self, scenario_id: str, agent_id: str, ok: bool) -> None:
        status = "success" if ok else "failed"
        with self.lock:
            print(f"[{scenario_id}]     {'✅' if ok else '❌'} {agent_id}: {status}", flush=True)
            self._write(f"  - {agent_id}: {status}\n")

    def scenario_finished(self, scenario_id: str, elapsed: float, successes: int) -> None:
        with self.lock:
            self.completed += 1
            line = (f"Done: {scenario_id} ({elapsed:.1f}s, success: {successes}/"
                    f"{self.total_agents}) [{self.completed}/{self.total_scenarios} "
                    f"scenarios completed]")
            print(f"[{scenario_id}] {line}", flush=True)
            self._write(f"[{self._stamp()}] {line}\n")

    def finished(self, results: dict) -> None:
        outcomes = [agent.get("success")
                    for scenarios in results.get("scenarios", {}).values()
                    for scenario in scenarios.values()
                    for agent in scenario.get("agents", {}).values()]
        ok = sum(1 for o in outcomes if o)
        minutes = (time.time() - self.start) / 60
        text = (f"\nRun complete: {self.completed} scenarios, {len(outcomes)} tasks, "
                f"{ok} succeeded, {len(outcomes) - ok} failed, {minutes:.1f} min.\n"
                f"Results: {results.get('output_dir')}\n")
        print(text, flush=True)
        self._write(text)


def run_agent(agent_id: str, scenario_path: Path, output_dir: Path,
              base_config, cfg: Experiment) -> dict:
    """Run one agent on one scenario and write what it produced.

    A raised exception is the agent's failure and is recorded as such (no
    output file, a FAILED log with the traceback); it never stops the run.
    """
    output_path = output_dir / f"{agent_id}_output.json"
    trajectory_path = output_dir / f"{agent_id}_trajectory.json"
    log_path = output_dir / f"{agent_id}_log.txt"
    output_dir.mkdir(parents=True, exist_ok=True)

    try:
        scenario = json.loads(scenario_path.read_text(encoding="utf-8"))
        run_config = llm.uniform_config(base_config)
        start = time.time()
        result = registry.build(agent_id, run_config, cfg)(scenario)
        elapsed = time.time() - start
        # Read AFTER the agent returns, from the counter the run's config
        # carried: every model the agent built, in any thread and through any
        # copy of the config, reported into it.
        token_usage = run_config._token_counter.snapshot()
        if isinstance(result, dict):
            result.setdefault("metadata", {})
            if isinstance(result["metadata"], dict):
                result["metadata"]["token_usage"] = token_usage
                result["metadata"]["execution_time_seconds"] = elapsed

        with open(output_path, "w", encoding="utf-8") as fh:
            json.dump(result.get("addie_output", result), fh,
                      ensure_ascii=False, indent=2, default=str)
        with open(trajectory_path, "w", encoding="utf-8") as fh:
            json.dump({
                "scenario_id": scenario.get("scenario_id", "unknown"),
                "agent_id": agent_id,
                "timestamp": datetime.now().isoformat(),
                "trajectory": result.get("trajectory", {}),
                "metadata": result.get("metadata", {"execution_time_seconds": elapsed}),
            }, fh, ensure_ascii=False, indent=2, default=str)

        # The proposed system's own artifacts, each in a file of its own: the
        # graph dump on a graph run, the raw blackboard on a prose run.
        graph_dump = result.get("graph")
        if isinstance(graph_dump, dict) and graph_dump:
            with open(output_dir / f"{agent_id}_graph.json", "w", encoding="utf-8") as fh:
                json.dump(graph_dump, fh, ensure_ascii=False, indent=2, default=str)
        prose_dump = result.get("prose")
        if isinstance(prose_dump, dict) and prose_dump.get("documents"):
            with open(output_dir / f"{agent_id}_prose.json", "w", encoding="utf-8") as fh:
                json.dump(prose_dump, fh, ensure_ascii=False, indent=2, default=str)

        log_path.write_text(
            f"=== {agent_id} execution log ===\nScenario: {scenario_path}\n"
            f"Elapsed: {elapsed:.2f}s\nStatus: SUCCESS\n", encoding="utf-8")
        return {"success": True, "output_path": str(output_path),
                "trajectory_path": str(trajectory_path), "log_path": str(log_path)}

    except Exception as exc:                     # the agent's failure, recorded
        log_path.write_text(
            f"=== {agent_id} execution log ===\nScenario: {scenario_path}\n"
            f"Status: FAILED\nError: {exc}\n\n=== Traceback ===\n{traceback.format_exc()}",
            encoding="utf-8")
        return {"success": False, "error": str(exc)[:500], "log_path": str(log_path)}


def run_scenario(scenario_path: Path, output_dir: Path, roster: list[str],
                 base_config, cfg: Experiment, preset: llm.RatePreset,
                 progress: Progress) -> dict:
    """Every agent of the roster on one scenario, ``preset.agents`` at a time."""
    scenario_id = scenario_path.stem
    record = {"scenario": scenario_path.name, "agents": {},
              "timestamp": datetime.now().isoformat(), "evaluation_deferred": True}
    gate = threading.Semaphore(preset.agents)

    def gated(agent_id: str) -> dict:
        with gate:
            return run_agent(agent_id, scenario_path, output_dir, base_config, cfg)

    with ThreadPoolExecutor(max_workers=len(roster)) as pool:
        futures = {}
        for agent_id in roster:
            futures[pool.submit(gated, agent_id)] = agent_id
            time.sleep(preset.delay)
        for future in as_completed(futures):
            agent_id = futures[future]
            outcome = future.result()
            record["agents"][agent_id] = outcome
            progress.agent_finished(scenario_id, agent_id, outcome["success"])
    return record


def scenario_files(dataset: str) -> list[Path]:
    split = paths.scenarios_dir() / dataset
    files = sorted(split.glob("*.json"))
    if not files:
        raise SystemExit(f"No scenarios in {split}/ -- build the split first "
                         f"(`{paths.cli()} data split`).")
    return files


def run_dir_for(dataset: str, model_id: str, tag: str, stamp: str,
                root: Path | None = None) -> Path:
    label = llm.model_dir_label(model_id)
    tag_part = f"_{tag}" if tag else ""
    return (root or paths.results_root()) / f"{dataset}_benchmark_{label}{tag_part}_{stamp}"


def slot_rate_limit(slot: str, default: str) -> str:
    """A per-slot override from ``<SLOT>_RATE_LIMIT``, else the profile's."""
    return os.environ.get(f"{slot.upper().replace('-', '_')}_RATE_LIMIT") or default


def generate(cfg: Experiment, *, experiment: str, slot: str, tag: str,
             agents: list[str] | None = None, rate_limit: str | None = None,
             results_root: Path | None = None) -> Path:
    """Generate one run and return its directory. Scores nothing."""
    profile = cfg.profile(experiment)
    model = cfg.by_slot(slot)
    roster = list(agents or profile.agents)
    unknown = [a for a in roster if a not in registry.known_agents(cfg)]
    if unknown:
        raise SystemExit(f"Unknown agent(s) {unknown}. Known: "
                         f"{', '.join(registry.known_agents(cfg))}")

    # Credentials first: a per-slot rate override may live in .env.
    llm.load_credentials()
    rate = rate_limit or slot_rate_limit(slot, profile.rate_limit)
    preset = llm.rate_preset(rate)
    llm.pin_posture(cfg, rate)

    scenarios = scenario_files(profile.dataset)
    base_config = llm.slot_config(cfg, model)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    run_dir = run_dir_for(profile.dataset, model.model, tag, stamp, results_root)
    run_dir.mkdir(parents=True, exist_ok=True)
    progress = Progress(run_dir / "benchmark_progress.log", len(scenarios), len(roster))

    print(f"\n{'=' * 78}\n  {profile.title}\n{'=' * 78}")
    print(f"  Model:     {model.model} (slot {slot}, api_spec {base_config.api_spec})")
    print(f"  Dataset:   {profile.dataset} ({len(scenarios)} scenarios)")
    print(f"  Agents:    {', '.join(roster)}")
    print(f"  Posture:   {rate} ({preset.scenarios} scenarios x {preset.agents} agents)")
    print(f"  Output:    {run_dir}\n{'=' * 78}", flush=True)

    results = {
        "timestamp": stamp,
        "output_dir": str(run_dir),
        "model": {
            "name": model.model,
            "slot": slot,
            "api_spec": base_config.api_spec,
            "base_url": base_config.base_url,
            "base_urls": list(base_config.all_base_urls),
            "endpoint_strategy": base_config.endpoint_strategy,
        },
        "config": {
            "experiment": experiment,
            "variants": [profile.dataset],
            "dataset": profile.dataset,
            "agents": roster,
            "run_tag": tag,
            "rate_limit": rate,
            "max_workers": preset.agents,
            "scenario_max_workers": preset.scenarios,
            "serving": llm.serving_env(cfg),
        },
        "scenarios": {profile.dataset: {}},
    }

    def one(index: int, path: Path) -> tuple[str, dict]:
        start = time.time()
        progress.scenario_started(path.stem, index)
        record = run_scenario(path, run_dir / profile.dataset / path.stem, roster,
                              base_config, cfg, preset, progress)
        ok = sum(1 for a in record["agents"].values() if a.get("success"))
        progress.scenario_finished(path.stem, time.time() - start, ok)
        return path.stem, record

    with ThreadPoolExecutor(max_workers=preset.scenarios) as pool:
        futures = {}
        for index, path in enumerate(scenarios):
            futures[pool.submit(one, index, path)] = path.stem
            time.sleep(preset.delay)
        for future in as_completed(futures):
            scenario_id = futures[future]
            try:
                _, record = future.result()
            except Exception as exc:              # a harness error, not an agent's
                record = {"scenario": scenario_id, "error": str(exc)}
                print(f"  !! {scenario_id}: {exc}", flush=True)
            results["scenarios"][profile.dataset][scenario_id] = record

    # Stable order in the record, whatever order the scenarios finished in.
    results["scenarios"][profile.dataset] = dict(
        sorted(results["scenarios"][profile.dataset].items()))
    summary.write(run_dir, results)
    progress.finished(results)
    return run_dir

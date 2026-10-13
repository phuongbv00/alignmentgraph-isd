#!/usr/bin/env python3
"""Generate agents again on named scenarios of an EXISTING run dir.

For attempts that failed or ran for a reason outside the agents -- the endpoint
dropped the connection, or the scenario file itself was defective and has been
restored -- so the cells can be scored instead of counting against the agents.
It calls the runner's own ``execute.run_scenario`` with the same slot, the same
pinned posture and the same rate preset the run was launched with, and writes
into the scenario's own directory, so the result is indistinguishable in shape
from a first attempt.

Guards, each refusing rather than guessing:
* the run's recorded ``pinned_env`` must equal what experiment.toml pins now: a
  re-run under a different posture would not be the same experiment;
* an agent that already produced an output in a scenario is skipped there
  unless ``--force``;
* a scenario dir that is absent (its earlier attempt archived elsewhere) is
  created only with ``--fresh``, so a typo cannot conjure an empty scenario;
* each re-run agent's previous log is kept beside the new one
  (``<agent>_log.failed.txt``) and the summary records the re-run.

It generates only. Judge afterwards:
  ./isd-exp judge llm <run_dir>                          # re-judges what lacks a row
  ./isd-exp judge alignment <run_dir> --primary-only --yes

Usage (from experiments/):
  .venv/bin/python bin/rerun_agent.py <run_dir> --agents eduplanner \\
      --scenarios scenario_idld_4498_v,scenario_idld_5750_v [--dry-run]
  .venv/bin/python bin/rerun_agent.py <run_dir> --agents all \\
      --scenarios scenario_bal_large2_0077 --fresh --reason "restored scenario file"
"""
from __future__ import annotations

import argparse
import shutil
import sys
from datetime import datetime
from pathlib import Path

from isd_experiments.config import current as current_config
from isd_experiments.runner import execute, llm, summary


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("run_dir", type=Path)
    ap.add_argument("--agents", required=True,
                    help="comma-separated agent ids, or 'all' for the run's roster")
    ap.add_argument("--scenarios", required=True,
                    help="comma-separated scenario ids (directory names)")
    ap.add_argument("--reason", default="endpoint connection error on the first attempt")
    ap.add_argument("--force", action="store_true",
                    help="re-run even where an agent already has an output")
    ap.add_argument("--fresh", action="store_true",
                    help="create a scenario dir that is absent from the run")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    run_dir = args.run_dir.resolve()
    record = summary.read(run_dir)
    if record is None:
        sys.exit(f"{run_dir}: no benchmark_summary.json -- not a run dir")
    conf = record["config"]
    dataset, rate = conf["dataset"], conf["rate_limit"]
    slot = record["model"]["slot"]

    cfg = current_config()
    pinned_then, pinned_now = conf.get("pinned_env", {}), llm.pinned_env(cfg)
    if pinned_then != pinned_now:
        diff = {k: (pinned_then.get(k), pinned_now.get(k))
                for k in set(pinned_then) | set(pinned_now)
                if pinned_then.get(k) != pinned_now.get(k)}
        sys.exit(f"posture differs from the run's (recorded, now): {diff}\n"
                 "Restore experiment.toml to what the run was launched with first.")
    roster = list(conf["agents"])
    agents = roster if args.agents.strip() == "all" else [
        a.strip() for a in args.agents.split(",") if a.strip()]
    unknown = [a for a in agents if a not in roster]
    if unknown:
        sys.exit(f"{unknown} not in this run's roster {roster}")

    by_stem = {p.stem: p for p in execute.scenario_files(dataset)}
    todo: list[tuple[str, Path, Path, list[str]]] = []
    for sid in [s.strip() for s in args.scenarios.split(",") if s.strip()]:
        if sid not in by_stem:
            sys.exit(f"{sid}: no scenario file in {dataset}")
        scen_dir = run_dir / dataset / sid
        if not scen_dir.is_dir() and not args.fresh:
            sys.exit(f"{sid}: no dir in the run (pass --fresh to create it)")
        these = [a for a in agents
                 if args.force or not (scen_dir / f"{a}_output.json").exists()]
        for a in sorted(set(agents) - set(these)):
            print(f"  skip {sid}/{a}: already has an output (use --force)")
        if these:
            todo.append((sid, by_stem[sid], scen_dir, these))

    print(f"Run       {run_dir.name}\nSlot      {slot} ({record['model']['name']})\n"
          f"Posture   {rate}, pinned env matches the run")
    for sid, _, scen_dir, these in todo:
        new = "" if scen_dir.is_dir() else "  [new dir]"
        print(f"  {sid}: {', '.join(these)}{new}")
    if args.dry_run or not todo:
        print("(nothing generated)")
        return 0

    llm.load_credentials()
    llm.pin_posture(cfg, rate)
    preset = llm.rate_preset(rate)
    base_config = llm.slot_config(cfg, cfg.by_slot(slot))
    progress = execute.Progress(run_dir / "rerun_progress.log", len(todo),
                                max(len(t[3]) for t in todo))

    status = 0
    for sid, scenario_path, scen_dir, these in todo:
        scen_dir.mkdir(parents=True, exist_ok=True)
        for a in these:
            log = scen_dir / f"{a}_log.txt"
            if log.exists():
                shutil.copy2(log, scen_dir / f"{a}_log.failed.txt")
        print(f"\n== {sid}: generating {', '.join(these)} ...", flush=True)
        rec = execute.run_scenario(scenario_path, scen_dir, these, base_config, cfg,
                                   preset, progress)
        stamp = {"timestamp": datetime.now().isoformat(), "reason": args.reason}
        for a, outcome in rec["agents"].items():
            outcome["rerun"] = stamp
            ok = outcome.get("success")
            print(f"   {a}: {'SUCCESS' if ok else 'FAILED: ' + outcome.get('error', '')}")
            status |= 0 if ok else 1

        results = summary.read(run_dir)
        cells = results["scenarios"].setdefault(dataset, {})
        cell = cells.get(sid)
        if not isinstance(cell, dict):
            cell = cells[sid] = {"scenario": scenario_path.name, "agents": {}}
        cell.setdefault("agents", {}).update(rec["agents"])
        cell["evaluation_deferred"] = True
        cell.pop("evaluation", None)
        summary.write(run_dir, results)

    print("\nNext:\n"
          f"  ./isd-exp judge llm {run_dir}\n"
          f"  ./isd-exp judge alignment {run_dir} --primary-only --yes")
    return status


if __name__ == "__main__":
    sys.exit(main())

"""Pooling the tune slice: what the ceilings and quotas are set from.

The tune experiment never enters the paper. What it is FOR is fixing the
harness parameters before ``isd-exp freeze`` -- the turn ceilings, the light
development quotas, the task ceiling, the thinking budget -- from what the
model actually did, and seeing the quality they buy next to it. So this pool is
descriptive only: no Holm family, no bootstrap, no failure policies. Every
agent of the profile is read; a baseline carries cost and scores and nothing
else, because it keeps no harness records.

Two files, both under the results root:

``pooled_tune.json``      per RUN DIR, per agent: run health, cost,
                          per-stage autonomy (mean/median/p90/max, % given up,
                          % CUT by the turn ceiling), relation coverage, the
                          violation ledger, work-set sizes, the ceilings the
                          runs were held to, and the scores where judged.
``tune_diagnostics.csv``  one row per (run, scenario, agent), to sort and
                          filter when a single scenario needs looking at.

Each run dir is its own entry, never merged with another of the same model:
successive tune runs are successive calibrations, and the point is to read one
beside the next.

It reads a run whether or not it has been judged: scores are filled in where
``comparison_report.json`` / ``alignment_scores.json`` exist and left blank
where they do not.
"""

from __future__ import annotations

import csv
import json
from datetime import datetime
from pathlib import Path

from .. import paths
from ..alignment.protocol import ALIGNMENT_SIGNALS
from ..config import LLM_JUDGE_SCORES
from ..config import current as current_config
from ..util import json_safe
from ..util import mean as _mean
from . import diagnostics
from .comparison import default_glob, discover

#: run_config keys that are the ceilings and postures a tune slice calibrates;
#: the pool reports every distinct value it saw, so a slice that mixed two
#: postures says so instead of averaging across them.
CALIBRATED = ("max_turns", "submit_budget", "regen_budget", "development_mode",
              "fanout_workers", "history_char_budget", "protocol_rev")

PANEL = tuple(sig for sig, _family in ALIGNMENT_SIGNALS)


def _scores(scen_dir: Path, agent: str) -> dict:
    """LLM judge scores and alignment signals for one cell, where judged."""
    out: dict = {}
    report = diagnostics.load_json(scen_dir / "comparison_report.json")
    if isinstance(report, dict):
        for r in (report.get("comparison") or {}).get("rankings") or []:
            if r.get("agent_id") == agent:
                for score in LLM_JUDGE_SCORES:
                    out[score] = diagnostics.number(r.get(score))
    align = diagnostics.load_json(scen_dir / "alignment_scores.json")
    if isinstance(align, dict):
        sc = (align.get("agents") or {}).get(agent) or {}
        for sig in PANEL:
            out[sig] = diagnostics.number(sc.get(sig))
    return out


def _row(label: str, run_dir: Path, sid: str, agent: str, cell: dict,
         scores: dict) -> dict:
    """One flat CSV row. Per-stage columns are named ``<field>_<stage>``."""
    row = {"model": label, "run_dir": run_dir.name, "scenario": sid, "agent": agent}
    for f in ("total_tokens", "prompt_tokens", "completion_tokens", "llm_calls", "seconds",
              "n_errors", "stopped", "ready_to_aggregate", "objectives_aligned"):
        row[f] = cell.get(f)
    cov = cell.get("relation_coverage") or {}
    for rel in diagnostics.CORE_RELATIONS:
        row[f"coverage_{rel}"] = cov.get(rel)
    lg = cell.get("ledger") or {}
    row["findings"] = lg.get("n_findings")
    row["open"] = (lg.get("by_outcome") or {}).get("open") if lg else None
    row["open_types"] = ";".join(f"{t}:{n}" for t, n in (lg.get("open_by_type") or {}).items())
    autonomy = cell.get("autonomy") or {}
    row["stages_gave_up"] = ";".join(s for s, st in autonomy.items() if st.get("gave_up"))
    row["stages_cut"] = ";".join(s for s, st in autonomy.items()
                                 if st.get("via_budget_exhaustion"))
    for stage, st in autonomy.items():
        for f in ("turns_used", "context_len", "submits_rejected", "set_turns",
                  "sets_gave_up", "compactions"):
            if f in st:
                row[f"{f}_{stage}"] = st[f]
    row.update(scores)
    return row


def _calibrated(records: list[dict]) -> dict:
    seen: dict[str, list] = {}
    for rec in records:
        for key in CALIBRATED:
            v = (rec.get("run_config") or {}).get(key)
            if v is not None and v not in seen.setdefault(key, []):
                seen[key].append(v)
    return seen


def _score_summary(rows: list[dict]) -> dict:
    out = {}
    for key in (*LLM_JUDGE_SCORES, *PANEL):
        vals = [r[key] for r in rows if isinstance(r.get(key), float)]
        if vals:
            out[key] = {"n": len(vals), "mean": _mean(vals)}
    return out


def pool(run_dirs_by_model: dict[str, list[Path]], agents: list[str]) -> tuple[dict, list[dict]]:
    """(pooled document, CSV rows). Pure: no printing, no writing."""
    entries, rows = [], []
    ordered = sorted(((label, d) for label, dirs in run_dirs_by_model.items() for d in dirs),
                     key=lambda ld: ld[1].name[-15:])        # the timestamp: oldest first
    for label, run_dir in ordered:
        cells: dict[str, dict[str, list[dict]]] = {a: {} for a in agents}
        agent_rows: dict[str, list[dict]] = {a: [] for a in agents}
        for sid, scen_dir in diagnostics.scenario_dirs(run_dir):
            for a in agents:
                cell = diagnostics.read_cell(scen_dir, a)
                if cell is None:
                    continue
                cells[a].setdefault(sid, []).append(cell)
                row = _row(label, run_dir, sid, a, cell, _scores(scen_dir, a))
                agent_rows[a].append(row)
                rows.append(row)
        per_agent = {}
        for a in agents:
            if not cells[a]:
                continue
            summary = diagnostics.summarize(cells[a], diagnostics.STAGE_ORDER)
            summary["run_config"] = _calibrated(
                [rec for recs in cells[a].values() for rec in recs])
            summary["scores"] = _score_summary(agent_rows[a])
            per_agent[a] = summary
        entries.append({"run_dir": run_dir.name, "model": label, "agents": per_agent})
    doc = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "config": {
            "experiment": "tune",
            "agents": agents,
            "purpose": ("descriptive calibration of harness ceilings and quotas before "
                        "freeze; never enters the paper, carries no inference"),
            "cut": ("pct_via_budget_exhaustion = % of stage runs ended by the turn "
                    "ceiling; a ceiling that cuts is inside the treatment"),
        },
        "runs": entries,
    }
    return doc, rows


def print_report(doc: dict) -> None:
    print("\n" + "=" * 78)
    print("TUNE DIAGNOSTICS")
    print("=" * 78)
    for entry in doc["runs"]:
        print(f"\n[{entry['run_dir']}]")
        for agent, s in entry["agents"].items():
            h = s["health"]
            print("  " + diagnostics.one_line(agent, s))
            sc = s.get("scores") or {}
            if sc:
                print("      scores: " + "  ".join(
                    f"{k}={v['mean']:.3g}(n={v['n']})" for k, v in sc.items()))
            mixed = {k: v for k, v in (s.get("run_config") or {}).items() if len(v) > 1}
            if mixed:
                print(f"      ! this run dir mixes postures: {mixed}")
            if h.get("pct_stopped") or h.get("pct_with_errors"):
                print(f"      stopped {h.get('pct_stopped') or 0:.0f}%  "
                      f"with errors {h.get('pct_with_errors') or 0:.0f}%  "
                      f"ready_to_aggregate {h.get('pct_ready_to_aggregate') or 0:.0f}%")
            au = s.get("autonomy")
            if au:
                ceiling = "/".join(str(c) for c in
                                   (s.get("run_config") or {}).get("max_turns") or ["?"])
                print(f"      turns by stage (mean/p90/max, ceiling {ceiling}), "
                      f"% gave up, % cut:")
                for stage, st in au["by_stage"].items():
                    t = st.get("turns_used") or {}
                    if not t.get("n"):
                        continue
                    print(f"        {stage:<15} {t['mean']:5.1f} / {t['p90']:5.1f} / "
                          f"{t['max']:4.0f}   gave_up {st.get('pct_gave_up', 0):3.0f}%  "
                          f"cut {st.get('pct_via_budget_exhaustion', 0):3.0f}%")
            lg = s.get("ledger")
            if lg and lg.get("open_by_type"):
                top = list(lg["open_by_type"].items())[:6]
                print("      open findings by type: " + ", ".join(f"{t} {n}" for t, n in top))


def write_csv(rows: list[dict], path: Path) -> None:
    fields: list[str] = []
    for row in rows:
        for k in row:
            if k not in fields:
                fields.append(k)
    with open(path, "w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            writer.writerow({k: ("" if row.get(k) is None else row.get(k)) for k in fields})


def run(*, patterns: list[str] | None = None, out: Path | None = None,
        agents: list[str] | None = None, quiet: bool = False) -> Path:
    """Discover, pool, report and write. Returns the JSON path."""
    profile = current_config().profile("tune")
    roster = agents or list(profile.agents)
    run_dirs_by_model = discover(patterns or [default_glob(profile)], profile)
    doc, rows = pool(run_dirs_by_model, roster)
    if not quiet:
        print_report(doc)
    target = out or (paths.results_root() / "pooled_tune.json")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(json_safe(doc), ensure_ascii=False, indent=2) + "\n",
                      encoding="utf-8")
    csv_path = target.with_name("tune_diagnostics.csv")
    write_csv(rows, csv_path)
    if not quiet:
        print(f"\nwrote {target}\nwrote {csv_path}")
    return target

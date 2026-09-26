"""What a run of the proposed system says about ITSELF, per scenario.

The LLM judge and the alignment panel score the DELIVERABLE. This module reads
the other half of a run directory -- what the harness recorded about how the
deliverable came to be -- and turns it into one flat record per (scenario,
agent). Two consumers read it:

* ``pool ablation``, where these are the mechanism readout the factorial is
  about (does context grow by stage in ``single``? does a stage end because it
  was CUT? which relations does each arm establish? which findings stay open,
  and why?);
* ``pool tune``, where they are what the ceilings and quotas are set from
  before ``isd-exp freeze``.

Sources, all written by ``runner/execute.py`` beside the deliverable:

``<agent>_trajectory.json``  ``metadata``: token_usage, execution time,
                             ``autonomy`` (per stage), ``repair_metrics``,
                             ``audit``, ``errors``, ``run_config``; plus the
                             ``work_sets`` events of the trajectory.
``<agent>_graph.json``       ``relation_coverage`` and ``objective_alignment``.
                             Graph substrate only -- a prose run builds none.
``<agent>_violations.json``  the violation ledger, on either substrate.

A baseline agent carries only token usage and time; every other field is
``None`` for it, never zero, because "this agent keeps no ledger" is not "this
agent had no findings".

A scenario is read whether or not it has been judged: diagnostics are a
property of generation, and a tune slice is usually read before it is scored.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Iterable, Optional

from ..util import mean as _mean

#: The instructed stage order, which is the STAGE POSITION the directional
#: prediction is about. Reading is driven by what a run actually recorded; a
#: stage this tuple does not name is appended after these rather than dropped,
#: and ``rubrics`` stays so a results dir from when it was a stage still reads in
#: the order it ran.
STAGE_ORDER = ("analysis", "outcomes", "assessment", "activities", "content",
               "rubrics", "implementation")

#: Per-stage counters carried by ``metadata.autonomy`` that are described.
AUTONOMY_FIELDS = ("context_len", "turns_used", "submits_rejected", "repeated_calls",
                   "history_dropped", "reads", "batched_calls", "compactions",
                   "compaction_summaries", "tool_errors", "truncated_turns",
                   "repair_turns", "set_turns", "set_submits_rejected", "sets_gave_up",
                   "n_sets")

#: Per-stage booleans, reported as a percentage of stage runs.
AUTONOMY_FLAGS = ("gave_up", "via_budget_exhaustion")

#: The core relations: the three edges of the Biggs triad.
CORE_RELATIONS = ("C2", "C3", "C4")

#: The package's marker for a run that stopped after outcomes (runner.NO_MODULES).
STOPPED_MARKER = "run stopped"

LEDGER_OUTCOMES = ("open", "repaired_by_harness", "repaired_by_agent")
OPEN_REASONS = ("converged", "budget", "unowned", "unseen", "unexplained")


def number(v) -> Optional[float]:
    return float(v) if isinstance(v, (int, float)) and not isinstance(v, bool) else None


def load_json(path: Path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None


def scenario_dirs(run_dir: Path) -> Iterable[tuple[str, Path]]:
    """(scenario_id, dir) for every scenario that holds any agent's trajectory.

    Unlike ``runs.iter_scenario_dirs`` this does not require a
    ``comparison_report.json``: a scenario that has not been judged yet still
    has everything this module reads.
    """
    def holds_run(d: Path) -> bool:
        return any(d.glob("*_trajectory.json"))

    for child in sorted(p for p in run_dir.iterdir() if p.is_dir()):
        if holds_run(child):
            yield child.name, child
            continue
        for scen in sorted(p for p in child.iterdir() if p.is_dir()):
            if holds_run(scen):
                yield scen.name, scen


def summarize_ledger(findings: list) -> dict:
    """Counts over one run's violation ledger."""
    findings = [f for f in findings if isinstance(f, dict)]
    by_outcome = {o: 0 for o in LEDGER_OUTCOMES}
    open_by_reason = {r: 0 for r in OPEN_REASONS}
    open_by_type: dict[str, int] = {}
    shown = report_only = 0
    for f in findings:
        outcome = f.get("outcome") or "open"
        by_outcome[outcome] = by_outcome.get(outcome, 0) + 1
        if (f.get("shown_to_agent") or 0) > 0:
            shown += 1
        if f.get("report_only"):
            report_only += 1
        if outcome == "open":
            reason = f.get("open_reason") or "unexplained"
            open_by_reason[reason] = open_by_reason.get(reason, 0) + 1
            t = str(f.get("type") or "?")
            open_by_type[t] = open_by_type.get(t, 0) + 1
    return {"n_findings": len(findings), "by_outcome": by_outcome,
            "open_by_reason": open_by_reason,
            "open_by_type": dict(sorted(open_by_type.items(), key=lambda kv: -kv[1])),
            "shown_to_agent": shown, "report_only": report_only}


def read_cell(scen_dir: Path, agent: str) -> Optional[dict]:
    """One (scenario, agent) record, or None when the agent left no trajectory."""
    doc = load_json(scen_dir / f"{agent}_trajectory.json")
    if not isinstance(doc, dict):
        return None
    md = doc.get("metadata") or {}
    tu = md.get("token_usage") or {}
    errors = md.get("errors")
    audit = md.get("audit") if isinstance(md.get("audit"), dict) else None

    autonomy = None
    if isinstance(md.get("autonomy"), dict):
        autonomy = {
            stage: {f: stats.get(f) for f in (*AUTONOMY_FIELDS, *AUTONOMY_FLAGS)
                    if f in stats}
            for stage, stats in md["autonomy"].items() if isinstance(stats, dict)
        }

    work_sets = None
    events = ((doc.get("trajectory") or {}).get("events") or []) \
        if isinstance(doc.get("trajectory"), dict) else []
    harness = harness_counts(events) if autonomy is not None else None
    for event in events:
        if isinstance(event, dict) and event.get("action") == "work_sets":
            ctx = event.get("context") or {}
            phase = ctx.get("phase") or "?"
            work_sets = work_sets or {}
            entry = work_sets.setdefault(phase, {"rounds": 0})
            entry["rounds"] += 1
            for key in ("set_count", "pair_count", "appended_sets", "oversized_splits",
                        "tasks_planned", "task_ceiling"):
                v = number(ctx.get(key))
                if v is not None:
                    entry[key] = v

    coverage = aligned = node_counts = None
    graph = load_json(scen_dir / f"{agent}_graph.json")
    if isinstance(graph, dict):
        coverage = {rel: number((entry or {}).get("coverage"))
                    for rel, entry in (graph.get("relation_coverage") or {}).items()}
        objectives = graph.get("objective_alignment") or {}
        if objectives:
            aligned = sum(1 for o in objectives.values()
                          if isinstance(o, dict) and o.get("aligned")) / len(objectives)
        node_counts = (graph.get("metadata") or {}).get("node_counts_by_type")

    ledger = None
    findings = load_json(scen_dir / f"{agent}_violations.json")
    if isinstance(findings, list):
        ledger = summarize_ledger(findings)

    run_config = md.get("run_config") if isinstance(md.get("run_config"), dict) else None
    return {
        "prompt_tokens": number(tu.get("prompt_tokens")),
        "completion_tokens": number(tu.get("completion_tokens")),
        "total_tokens": number(tu.get("total_tokens")),
        "llm_calls": number(tu.get("llm_calls")),
        "seconds": number(md.get("execution_time_seconds")),
        "n_errors": len(errors) if isinstance(errors, list) else None,
        "stopped": (any(STOPPED_MARKER in str(e) for e in errors)
                    if isinstance(errors, list) else None),
        "ready_to_aggregate": audit.get("ready_to_aggregate") if audit else None,
        "repair_metrics": md.get("repair_metrics") if isinstance(
            md.get("repair_metrics"), dict) else None,
        "run_config": run_config,
        "autonomy": autonomy,
        "harness": harness,
        "work_sets": work_sets,
        "relation_coverage": coverage,
        "objectives_aligned": aligned,
        "node_counts": node_counts,
        "ledger": ledger,
    }


#: Why a model call failed, from the message the client recorded. The two that
#: are the harness's to prevent: a prompt past the serving window, and a reply
#: run to the completion cap. The third is the endpoint's.
_ERROR_KINDS = (("context_overflow", "maximum context length"),
                ("completion_cap", "length limit was reached"),
                ("connection", "connection error"))


def harness_counts(events: list) -> dict:
    """What the harness did on the model's behalf, from one trajectory's events:
    the counts a tune run is read for before any LLM judge has scored it.

    ``pass_empty`` is a constrained pass that came back with nothing (the
    decoder ran out, or the endpoint refused); ``pass_refused`` one the
    validator still refused. ``rejected_empty_args`` is a submit that arrived
    with no arguments at all -- the transport failure the constrained pass
    exists for -- apart from every other rejection."""
    out = {"passes": 0, "pass_accepted": 0, "pass_empty": 0, "pass_refused": 0,
           "rejected": 0, "rejected_empty_args": 0, "gave_up": 0, "repeats_refused": 0,
           "schema_keywords_dropped": 0,
           **{kind: 0 for kind, _ in _ERROR_KINDS}}
    for event in events:
        if not isinstance(event, dict):
            continue
        action = event.get("action")
        ctx = event.get("context") or {}
        said = str(ctx.get("output_summary") or "")
        asked = str(ctx.get("input_summary") or "")
        if action == "constrained_pass":
            out["passes"] += 1
            if said == "accepted":
                out["pass_accepted"] += 1
            elif "no artifact came back" in said:
                out["pass_empty"] += 1
            else:
                out["pass_refused"] += 1
        elif action == "submit_rejected":
            out["rejected"] += 1
            if "| args= " in asked or asked.rstrip().endswith("| args="):
                out["rejected_empty_args"] += 1
        elif action == "agentic_gave_up":
            out["gave_up"] += 1
        elif action == "repeated_tool_call":
            out["repeats_refused"] += 1
        elif action == "argument_reshaped" and "schema keyword dropped" in asked:
            out["schema_keywords_dropped"] += asked.count("schema keyword dropped")
        elif action == "llm_error":
            lowered = said.lower()
            for kind, marker in _ERROR_KINDS:
                if marker in lowered:
                    out[kind] += 1
                    break
    return out


def collect(run_dirs: list[Path], agents: list[str]) -> dict[str, dict[str, list[dict]]]:
    """agent -> scenario -> [one record per run that has it]."""
    out: dict[str, dict[str, list[dict]]] = {a: {} for a in agents}
    for run_dir in run_dirs:
        for sid, scen_dir in scenario_dirs(run_dir):
            for a in agents:
                cell = read_cell(scen_dir, a)
                if cell is not None:
                    out[a].setdefault(sid, []).append(cell)
    return out


def _quantile(values: list[float], q: float) -> Optional[float]:
    """Linear-interpolated quantile (numpy's default), stdlib only."""
    if not values:
        return None
    xs = sorted(values)
    pos = (len(xs) - 1) * q
    lo = int(pos)
    hi = min(lo + 1, len(xs) - 1)
    return xs[lo] + (xs[hi] - xs[lo]) * (pos - lo)


def describe(values: list[float]) -> dict:
    """mean / median / p90 / max over whatever arrived."""
    values = [v for v in values if v is not None]
    if not values:
        return {"n": 0}
    return {"n": len(values), "mean": _mean(values), "median": _quantile(values, 0.5),
            "p90": _quantile(values, 0.9), "max": max(values)}


def _records(by_scenario: dict[str, list[dict]]) -> list[dict]:
    return [rec for recs in by_scenario.values() for rec in recs]


# ── summaries over one agent's records ──────────────────────────────────────


def autonomy_summary(records: list[dict], stage_order: tuple[str, ...]) -> Optional[dict]:
    """Per stage: every counter described, every flag as a percentage."""
    per_stage: dict[str, dict[str, list[float]]] = {}
    for rec in records:
        for stage, stats in (rec.get("autonomy") or {}).items():
            slot = per_stage.setdefault(stage, {})
            for f in AUTONOMY_FIELDS:
                v = number(stats.get(f))
                if v is not None:
                    slot.setdefault(f, []).append(v)
            for f in AUTONOMY_FLAGS:
                if f in stats:
                    slot.setdefault(f, []).append(1.0 if stats.get(f) else 0.0)
    if not per_stage:
        return None
    known = [s for s in stage_order if s in per_stage]
    ordered = known + [s for s in per_stage if s not in stage_order]
    series = {}
    for stage in ordered:
        slot = per_stage[stage]
        entry = {f: describe(slot[f]) for f in AUTONOMY_FIELDS if f in slot}
        for f in AUTONOMY_FLAGS:
            if f in slot:
                entry[f"pct_{f}"] = 100.0 * _mean(slot[f])
        series[stage] = entry
    ctx = [series[s]["context_len"]["mean"] for s in ordered
           if series[s].get("context_len", {}).get("n")]
    return {
        "by_stage": series,
        "context_growth_first_to_last": (ctx[-1] / ctx[0] if len(ctx) >= 2 and ctx[0]
                                         else None),
        "peak_context_len": max(ctx) if ctx else None,
        "pct_stages_gave_up": _mean([series[s]["pct_gave_up"] for s in ordered
                                     if "pct_gave_up" in series[s]]),
        "pct_stages_via_budget_exhaustion": _mean(
            [series[s]["pct_via_budget_exhaustion"] for s in ordered
             if "pct_via_budget_exhaustion" in series[s]]),
    }


def coverage_summary(records: list[dict]) -> Optional[dict]:
    """Mean relation coverage over the scenario runs that shipped a graph."""
    graphed = [r for r in records if r.get("relation_coverage") is not None]
    if not graphed:
        return None
    by_rel: dict[str, list[float]] = {}
    for rec in graphed:
        for rel, v in rec["relation_coverage"].items():
            if v is not None:
                by_rel.setdefault(rel, []).append(v)
    per_rel = {rel: _mean(vs) for rel, vs in by_rel.items()}
    core = [per_rel[r] for r in CORE_RELATIONS if r in per_rel]
    aligned = [r["objectives_aligned"] for r in graphed if r.get("objectives_aligned") is not None]
    perfect_core = sum(1 for r in graphed
                       if all((r["relation_coverage"].get(c) or 0.0) >= 1.0
                              for c in CORE_RELATIONS))
    return {"n_with_graph": len(graphed),
            "relation_coverage_mean": dict(sorted(per_rel.items(),
                                                  key=lambda kv: _rel_key(kv[0]))),
            "core_coverage_mean": _mean(core) if core else None,
            "objectives_aligned_mean": _mean(aligned) if aligned else None,
            "pct_runs_core_complete": 100.0 * perfect_core / len(graphed)}


def _rel_key(rel: str) -> tuple:
    head, digits = rel[:1], rel[1:]
    return (head != "C", int(digits) if digits.isdigit() else 999, rel)


def ledger_summary(records: list[dict]) -> Optional[dict]:
    """Findings per run, and what became of them, pooled over every finding."""
    ledgers = [r["ledger"] for r in records if r.get("ledger") is not None]
    if not ledgers:
        return None
    total = sum(lg["n_findings"] for lg in ledgers)
    outcome = {o: sum(lg["by_outcome"].get(o, 0) for lg in ledgers) for o in LEDGER_OUTCOMES}
    n_open = outcome["open"]
    reasons = {r: sum(lg["open_by_reason"].get(r, 0) for lg in ledgers) for r in OPEN_REASONS}
    types: dict[str, int] = {}
    for lg in ledgers:
        for t, n in lg["open_by_type"].items():
            types[t] = types.get(t, 0) + n
    return {
        "n_with_ledger": len(ledgers),
        "findings_per_run": describe([float(lg["n_findings"]) for lg in ledgers]),
        "open_per_run": describe([float(lg["by_outcome"].get("open", 0)) for lg in ledgers]),
        "pct_of_findings": ({o: 100.0 * n / total for o, n in outcome.items()}
                            if total else None),
        "pct_of_open_by_reason": ({r: 100.0 * n / n_open for r, n in reasons.items()}
                                  if n_open else None),
        "pct_shown_to_agent": (100.0 * sum(lg["shown_to_agent"] for lg in ledgers) / total
                               if total else None),
        "open_by_type": dict(sorted(types.items(), key=lambda kv: -kv[1])),
        "pct_runs_with_open": 100.0 * sum(1 for lg in ledgers
                                          if lg["by_outcome"].get("open", 0)) / len(ledgers),
    }


def cost_summary(records: list[dict]) -> dict:
    return {f: describe([r.get(f) for r in records])
            for f in ("total_tokens", "prompt_tokens", "completion_tokens", "llm_calls",
                      "seconds")}


def run_health(records: list[dict]) -> dict:
    """How many scenario runs stopped early, carried errors, or failed the gate."""
    def pct(field: str, truth=lambda v: bool(v)) -> Optional[float]:
        vals = [r.get(field) for r in records if r.get(field) is not None]
        return 100.0 * sum(1 for v in vals if truth(v)) / len(vals) if vals else None
    return {"n_runs": len(records),
            "pct_stopped": pct("stopped"),
            "pct_with_errors": pct("n_errors", lambda v: v > 0),
            "pct_ready_to_aggregate": pct("ready_to_aggregate")}


def work_set_summary(records: list[dict]) -> Optional[dict]:
    per_phase: dict[str, dict[str, list[float]]] = {}
    for rec in records:
        for phase, entry in (rec.get("work_sets") or {}).items():
            slot = per_phase.setdefault(phase, {})
            for k, v in entry.items():
                slot.setdefault(k, []).append(float(v))
    if not per_phase:
        return None
    return {phase: {k: describe(vs) for k, vs in slot.items()}
            for phase, slot in per_phase.items()}


def summarize(by_scenario: dict[str, list[dict]], stage_order: tuple[str, ...]) -> dict:
    """Every summary for one agent's records."""
    records = _records(by_scenario)
    return {
        "n_scenarios": len(by_scenario),
        "health": run_health(records),
        "cost": cost_summary(records),
        "autonomy": autonomy_summary(records, stage_order),
        "relation_coverage": coverage_summary(records),
        "ledger": ledger_summary(records),
        "work_sets": work_set_summary(records),
    }


def one_line(agent: str, summary: dict) -> str:
    """The summary an operator reads at the terminal: one line per agent."""
    def fmt(v, spec):
        return format(v, spec) if isinstance(v, (int, float)) else "--"
    au = summary.get("autonomy") or {}
    cov = summary.get("relation_coverage") or {}
    lg = summary.get("ledger") or {}
    cost = summary.get("cost") or {}
    return (f"{agent:<36} ctx x{fmt(au.get('context_growth_first_to_last'), '.1f'):>5} "
            f"cut {fmt(au.get('pct_stages_via_budget_exhaustion'), '.0f'):>3}% "
            f"gave_up {fmt(au.get('pct_stages_gave_up'), '.0f'):>3}% "
            f"core {fmt(cov.get('core_coverage_mean'), '.2f'):>4} "
            f"open/run {fmt((lg.get('open_per_run') or {}).get('mean'), '.1f'):>4} "
            f"tok {fmt((cost.get('total_tokens') or {}).get('mean'), ',.0f'):>9} "
            f"s {fmt((cost.get('seconds') or {}).get('mean'), '.0f'):>5}")

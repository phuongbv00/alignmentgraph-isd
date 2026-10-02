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

The alignment signals come from the PRIMARY encoder's artifact unless
``encoder`` names another declared arm. The primary is served, and a tune slice
may be scored without its endpoint (the arm is skipped as unreachable), so
``--encoder bgem3`` reads ``alignment_scores.bgem3.json`` instead. The pooled
document records which artifact the panel was read from.
"""

from __future__ import annotations

import csv
import json
from datetime import datetime
from pathlib import Path

from .. import paths
from ..alignment import presets
from ..alignment.protocol import ALIGNMENT_SIGNALS
from ..config import LLM_JUDGE_SCORES
from ..config import current as current_config
from ..audit import fabrication
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


def _scores(scen_dir: Path, agent: str,
            panel_artifact: str = presets.PRIMARY_ARTIFACT) -> dict:
    """LLM judge scores and alignment signals for one cell, where judged."""
    out: dict = {}
    report = diagnostics.load_json(scen_dir / "comparison_report.json")
    if isinstance(report, dict):
        for r in (report.get("comparison") or {}).get("rankings") or []:
            if r.get("agent_id") == agent:
                for score in LLM_JUDGE_SCORES:
                    out[score] = diagnostics.number(r.get(score))
    align = diagnostics.load_json(scen_dir / panel_artifact)
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
    triad = cell.get("triad_references") or {}
    for f in diagnostics.TRIAD_REFERENCE_FIELDS:
        row[f"triad_{f}"] = triad.get(f)
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


# ── reading a tune run without reading it by hand ───────────────────────────
#
# A tune-10 run is ten paired scenarios scored by every LLM judge of the roster
# (two when this was measured). MEASURED over
# six runs (2026-09-23..25): the paired gap between two agents has a standard
# error of 0.9-1.4 Total points, a baseline whose code did not change moved
# 84.7-85.8, and the two LLM judges disagreed on which agent was better in 17 of
# 40 scenario pairs. A change worth 0.5-1.5 points cannot be seen in one run,
# so every gap below is reported WITH its standard error and flagged when it is
# inside the noise; and the harness is read first from its own counters, which
# need no judge and do not move with one.

#: A gap inside this many standard errors is reported as not detected.
DETECTION_SE = 2.0

#: Harness counters that should be zero on a healthy run; any that is not is
#: named on the report's attention line.
ATTENTION = ("gave_up", "pass_empty", "context_overflow", "completion_cap",
             "required_empty", "stopped")

#: What the per-scenario gap is computed on: the three LLM judge scores.
GAP_SCORES = ("total_score", "addie_median", "trajectory_score")


def _judge_view(scen_dir: Path) -> dict:
    """``agent -> {score: value, "judges": {model: {"addie", "traj", items}}}``
    for one judged scenario; ``{}`` when it has not been judged."""
    report = diagnostics.load_json(scen_dir / "comparison_report.json")
    out: dict = {}
    if not isinstance(report, dict):
        return out
    for r in (report.get("comparison") or {}).get("rankings") or []:
        agent = r.get("agent_id")
        if not agent:
            continue
        view = {score: diagnostics.number(r.get(score)) for score in GAP_SCORES}
        judges: dict = {}
        for j in r.get("judges") or []:
            model = str(j.get("model") or "?")
            items = {}
            for phase in ((j.get("details") or {}).get("phases") or {}).values():
                for it in phase.get("items") or []:
                    if it.get("item_id") is not None:
                        items[it["item_id"]] = diagnostics.number(it.get("score"))
            judges[model] = {"addie": diagnostics.number(j.get("addie_score")),
                             "traj": diagnostics.number(j.get("trajectory_score")),
                             "items": items}
        view["judges"] = judges
        out[agent] = view
    return out


def _mean_se(values: list[float]) -> dict:
    n = len(values)
    if not n:
        return {"n": 0}
    m = sum(values) / n
    if n < 2:
        return {"n": n, "mean": m}
    var = sum((v - m) ** 2 for v in values) / (n - 1)
    se = (var / n) ** 0.5
    return {"n": n, "mean": m, "se": se, "detected": abs(m) >= DETECTION_SE * se}


def paired_gap(views: dict[str, dict], proposed: str, baseline: str) -> dict:
    """``proposed - baseline`` per scenario, summarised with its standard error:
    the three LLM judge scores, then ADDIE and Trajectory per judge, then each
    rubric item per judge. ``views`` is scenario -> :func:`_judge_view`."""
    diffs: dict[str, list[float]] = {}

    def add(key: str, a, b) -> None:
        if isinstance(a, float) and isinstance(b, float):
            diffs.setdefault(key, []).append(a - b)

    for view in views.values():
        mine, theirs = view.get(proposed), view.get(baseline)
        if not mine or not theirs:
            continue
        for score in GAP_SCORES:
            add(score, mine.get(score), theirs.get(score))
        for model, j in (mine.get("judges") or {}).items():
            other = (theirs.get("judges") or {}).get(model)
            if not other:
                continue
            add(f"addie@{model}", j.get("addie"), other.get("addie"))
            add(f"traj@{model}", j.get("traj"), other.get("traj"))
            for item, value in (j.get("items") or {}).items():
                add(f"{item}@{model}", value, (other.get("items") or {}).get(item))
    return {key: _mean_se(values) for key, values in diffs.items()}


def gap_shift(before: dict[str, dict], after: dict[str, dict], proposed: str,
              baseline: str) -> dict:
    """How the ``proposed - baseline`` gap moved from one run to the next, over
    the scenarios both runs judged: per scenario, gap(after) - gap(before). The
    baseline's own drift between the runs cancels, which is what makes a
    before/after comparison of the proposed system readable at all."""
    shifts: dict[str, list[float]] = {}
    for sid in sorted(set(before) & set(after)):
        b, a = before[sid], after[sid]
        for score in GAP_SCORES:
            vals = [(v.get(proposed) or {}).get(score) for v in (b, a)] + \
                   [(v.get(baseline) or {}).get(score) for v in (b, a)]
            if all(isinstance(x, float) for x in vals):
                shifts.setdefault(score, []).append((vals[1] - vals[3]) - (vals[0] - vals[2]))
    return {key: _mean_se(values) for key, values in shifts.items()}


def _required_empty(output_path: Path) -> int | None:
    """Fields the proposed system's contract declares REQUIRED that its output
    left empty, counted over every artifact the output carries. ``None`` when
    the package is not installed here: a machine that only scores and reports
    carries no inference stack, and this one count is the only thing here that
    needs it."""
    try:
        from alignmentgraph_isd.core.agentic.artifact_schemas import ARTIFACT_SCHEMAS
        from alignmentgraph_isd.core.agentic.specialists import HARNESS_SETTLED_FIELDS
    except ImportError:
        return None
    doc = diagnostics.load_json(output_path)
    if not isinstance(doc, dict):
        return None
    doc = doc.get("addie_output", doc)
    # Not ``evaluation``: it restates artifacts the other phases own (a
    # formative instrument there is a one-row summary, not an item), and
    # counting it would charge the summary with the item's fields.
    doc = {phase: body for phase, body in doc.items() if phase != "evaluation"}
    empty = 0

    def instances(node, key):
        if isinstance(node, dict):
            for k, v in node.items():
                if k == key:
                    for one in (v if isinstance(v, list) else [v]):
                        if isinstance(one, dict):
                            yield from (one.get("items") if key == "assessment_tools"
                                        and isinstance(one.get("items"), list) else [one])
                else:
                    yield from instances(v, key)
        elif isinstance(node, list):
            for v in node:
                yield from instances(v, key)

    for key, schema in ARTIFACT_SCHEMAS.items():
        required = [f for f in schema.get("required", ()) if f not in HARNESS_SETTLED_FIELDS]
        for one in instances(doc, key):
            if isinstance(one, dict):
                empty += sum(1 for f in required if one.get(f) in (None, "", [], {}))
    return empty


def run_health(cells: dict[str, list[dict]], outputs: list[Path]) -> dict:
    """The proposed system's harness counters summed over one run dir, plus the
    fields its output left empty and what needs attention."""
    totals: dict[str, float] = {}
    for recs in cells.values():
        for rec in recs:
            for key, value in (rec.get("harness") or {}).items():
                totals[key] = totals.get(key, 0) + (value or 0)
            if rec.get("stopped"):
                totals["stopped"] = totals.get("stopped", 0) + 1
    empties = [e for e in (_required_empty(p) for p in outputs) if e is not None]
    if empties:
        totals["required_empty"] = sum(empties)
    totals["attention"] = [k for k in ATTENTION if totals.get(k)]
    return totals


def pool(run_dirs_by_model: dict[str, list[Path]], agents: list[str],
         panel_artifact: str = presets.PRIMARY_ARTIFACT) -> tuple[dict, list[dict]]:
    """(pooled document, CSV rows). Pure: no printing, no writing."""
    entries, rows = [], []
    ordered = sorted(((label, d) for label, dirs in run_dirs_by_model.items() for d in dirs),
                     key=lambda ld: ld[1].name[-15:])        # the timestamp: oldest first
    for label, run_dir in ordered:
        cells: dict[str, dict[str, list[dict]]] = {a: {} for a in agents}
        agent_rows: dict[str, list[dict]] = {a: [] for a in agents}
        views: dict[str, dict] = {}
        outputs: dict[str, list[Path]] = {a: [] for a in agents}
        for sid, scen_dir in diagnostics.scenario_dirs(run_dir):
            view = _judge_view(scen_dir)
            if view:
                views[sid] = view
            for a in agents:
                if (scen_dir / f"{a}_output.json").exists():
                    outputs[a].append(scen_dir / f"{a}_output.json")
                cell = diagnostics.read_cell(scen_dir, a)
                if cell is None:
                    continue
                cells[a].setdefault(sid, []).append(cell)
                row = _row(label, run_dir, sid, a, cell,
                           _scores(scen_dir, a, panel_artifact))
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
            summary["fabrication"] = fabrication.summarize(
                [fabrication.audit_file(p) for p in outputs[a]])
            if summary.get("autonomy"):
                summary["harness"] = run_health(cells[a], outputs[a])
            per_agent[a] = summary
        proposed = [a for a in per_agent if (per_agent[a].get("autonomy"))]
        gaps = {f"{p} - {b}": paired_gap(views, p, b)
                for p in proposed for b in per_agent if b not in proposed}
        entries.append({"run_dir": run_dir.name, "model": label, "agents": per_agent,
                        "gaps": gaps, "_views": views})
    doc = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "config": {
            "experiment": "tune",
            "agents": agents,
            "purpose": ("descriptive calibration of harness ceilings and quotas before "
                        "freeze; never enters the paper, carries no inference"),
            "cut": ("pct_via_budget_exhaustion = % of stage runs ended by the turn "
                    "ceiling; a ceiling that cuts is inside the treatment"),
            "panel_artifact": panel_artifact,
        },
        "runs": entries,
    }
    return doc, rows


def _fmt_gap(g: dict | None) -> str:
    if not g or "mean" not in g:
        return "--"
    if "se" not in g:
        return f"{g['mean']:+.1f}"
    return f"{g['mean']:+.1f}±{g['se']:.1f}" + ("" if g["detected"] else "~")


def print_report(doc: dict) -> None:
    print("\n" + "=" * 78)
    print("TUNE DIAGNOSTICS")
    print("=" * 78)
    print(f"alignment signals from {doc['config'].get('panel_artifact')}")
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
            hh = s.get("harness")
            if hh:
                print(f"      harness: passes {hh.get('passes', 0):.0f} (ok {hh.get('pass_accepted', 0):.0f}"
                      f", empty {hh.get('pass_empty', 0):.0f}, refused {hh.get('pass_refused', 0):.0f}"
                      f", skipped {hh.get('pass_skipped', 0):.0f})"
                      f"  rejected {hh.get('rejected', 0):.0f} (no args {hh.get('rejected_empty_args', 0):.0f})"
                      f"  gave_up {hh.get('gave_up', 0):.0f}  overflow {hh.get('context_overflow', 0):.0f}"
                      f"  cap {hh.get('completion_cap', 0):.0f}  conn {hh.get('connection', 0):.0f}"
                      f"  required_empty {hh.get('required_empty', '--')}")
                print("      ATTENTION: " + (", ".join(hh["attention"]) if hh.get("attention")
                                             else "none"))
            fb = s.get("fabrication") or {}
            if fb.get("n"):
                print(f"      post-pilot claims: result fields {fb['with_result_fields']}/{fb['n']}"
                      f"  human reviewers {fb['with_human_reviewers']}/{fb['n']}"
                      f"  decision taken {fb['with_decision_taken']}/{fb['n']}")
        for pair, g in (entry.get("gaps") or {}).items():
            if not g:
                continue
            print(f"  gap {pair}  (mean±se; ~ = inside {DETECTION_SE:g} se, not detected)")
            print("      Total " + _fmt_gap(g.get("total_score")) + "  ADDIE "
                  + _fmt_gap(g.get("addie_median")) + "  Traj " + _fmt_gap(g.get("trajectory_score")))
            models = sorted({k.split("@", 1)[1] for k in g if "@" in k})
            for model in models:
                print(f"      {model:<34} ADDIE {_fmt_gap(g.get(f'addie@{model}'))}  "
                      f"Traj {_fmt_gap(g.get(f'traj@{model}'))}")
            items = sorted({k.split("@", 1)[0] for k in g if "@" in k}
                           - {"addie", "traj"})
            detected = []
            for item in items:
                per = [g.get(f"{item}@{m}") for m in models]
                if all(x and x.get("detected") for x in per) and len(
                        {x["mean"] > 0 for x in per}) == 1:
                    detected.append(f"{item} " + "/".join(f"{x['mean']:+.1f}" for x in per))
            print("      items every LLM judge separates: " + (", ".join(detected) or "none"))


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


def views_of(run_dir: Path) -> dict[str, dict]:
    """``scenario -> _judge_view`` for every judged scenario of one run dir."""
    views = {}
    for sid, scen_dir in diagnostics.scenario_dirs(run_dir):
        view = _judge_view(scen_dir)
        if view:
            views[sid] = view
    return views


def add_shifts(doc: dict, against: Path) -> None:
    """Every run's gap SHIFT against one earlier run dir: what a change to the
    proposed system moved, with the baseline's own drift cancelled."""
    before = views_of(against)
    for entry in doc["runs"]:
        after = entry.get("_views") or {}
        entry["shift_vs"] = {"run_dir": against.name, "pairs": {
            pair: gap_shift(before, after, *pair.split(" - ", 1))
            for pair in entry.get("gaps") or {}}}


def print_shifts(doc: dict) -> None:
    for entry in doc["runs"]:
        sv = entry.get("shift_vs")
        if not sv or entry["run_dir"] == sv["run_dir"]:
            continue
        for pair, g in sv["pairs"].items():
            print(f"\n[{entry['run_dir']}] vs [{sv['run_dir']}]  shift of {pair}:  "
                  f"Total {_fmt_gap(g.get('total_score'))}  ADDIE {_fmt_gap(g.get('addie_median'))}"
                  f"  Traj {_fmt_gap(g.get('trajectory_score'))}")


def run(*, patterns: list[str] | None = None, out: Path | None = None,
        agents: list[str] | None = None, quiet: bool = False,
        against: Path | None = None, encoder: str | None = None) -> Path:
    """Discover, pool, report and write. Returns the JSON path."""
    profile = current_config().profile("tune")
    roster = agents or list(profile.agents)
    run_dirs_by_model = discover(patterns or [default_glob(profile)], profile)
    artifact = (presets.current().encoder(encoder).artifact if encoder
                else presets.PRIMARY_ARTIFACT)
    doc, rows = pool(run_dirs_by_model, roster, artifact)
    if against is not None:
        add_shifts(doc, against)
    for entry in doc["runs"]:
        entry.pop("_views", None)
    if not quiet:
        print_report(doc)
        print_shifts(doc)
    target = out or (paths.results_root() / "pooled_tune.json")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(json_safe(doc), ensure_ascii=False, indent=2) + "\n",
                      encoding="utf-8")
    csv_path = target.with_name("tune_diagnostics.csv")
    write_csv(rows, csv_path)
    if not quiet:
        print(f"\nwrote {target}\nwrote {csv_path}")
    return target

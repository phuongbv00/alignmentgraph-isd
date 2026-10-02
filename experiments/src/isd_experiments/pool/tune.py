"""Pooling the tune slice: what the ceilings and quotas are set from.

The tune experiment never enters the paper. What it is FOR is fixing the
harness parameters before ``isd-exp freeze`` -- the turn ceilings, the light
development quotas, the task ceiling, the thinking budget -- from what the
model actually did, and seeing the quality they buy next to it. So this pool is
descriptive only: no Holm family, no bootstrap, no failure policies. A baseline
carries cost and scores and nothing else, because it keeps no harness records.

Any run dir can be read, not only a tune one: each is read with the roster it
was launched with (``benchmark_summary.json``), so a comparison run dir shows
the proposed system against every baseline at every rung and an ablation run
dir shows the four arms -- the harness's own diagnosis of the official runs.
It is never the pooled RESULT: that is ``pool comparison`` / ``pool ablation``.

Per run dir it reports the posture the runner pinned, which LLM judge roster
scored it (two rosters in one run dir get no gap at all: they are never pooled
together), and per agent the scenarios it is missing and how often its LLM
judges disagreed. Gaps are paired by scenario, with their standard error, on
the LLM judge scores AND the alignment signals: each proposed agent against
each baseline, each ablation arm against the declared reference, and -- when
all four cells ran -- the 2x2 read as two main effects and an interaction.
Findings are charged to the stage whose family owns them, the reading of the
registered prediction that quality degrades with stage position in the single
arm; on the prose substrate only within-artifact checks run, so a prose arm's
count is lower by construction and is read within an arm, not across.

Two files, both under the results root:

``pooled_tune.json``      per RUN DIR, per agent: run health, cost,
                          per-stage autonomy (mean/median/p90/max, % given up,
                          % CUT by the turn ceiling), relation coverage, the
                          violation ledger, work-set sizes, the ceilings the
                          runs were held to, and the scores where judged.
``tune_diagnostics.csv``  one row per (run, scenario, agent), to sort and
                          filter when a single scenario needs looking at; one
                          column per alignment arm (``<signal>@<arm>``).

(``pooled_tune.<experiment>.json`` / ``tune_diagnostics.<experiment>.csv`` when
``--experiment comparison|ablation`` picks the run dirs.)

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
              "fanout_workers", "history_char_budget", "protocol_rev",
              "structured_outputs", "agent_mode", "context_mode")

#: The serving and generation posture the runner pinned for the whole run dir
#: (``benchmark_summary.json`` -> ``config.pinned_env``), under short names.
POSTURE_ENV = {"AGENT_MODEL_THINKING_BUDGET": "thinking_budget",
               "AGENT_MODEL_MAX_OUTPUT_TOKENS": "max_output_tokens",
               "AGENT_MODEL_CONTEXT_WINDOW": "context_window",
               "AGENT_MODEL_TEMPERATURE": "temperature",
               "AGENT_MODEL_STRUCTURED_OUTPUTS": "structured_outputs",
               "AGENT_MODEL_STREAMING": "streaming",
               "HARNESS_DEVELOPMENT_MODE": "development_mode",
               "HARNESS_FANOUT_WORKERS": "fanout_workers"}

#: The family that owns a finding -> the stage that family writes. A finding is
#: charged to the stage whose artifact it is about, on either decomposition arm
#: (the single arm's own phase is one ``design`` phase and says nothing).
FAMILY_STAGE = {"needs_analyst": "analysis", "outcome_designer": "outcomes",
                "assessment_designer": "assessment", "rubric_designer": "assessment",
                "activity_designer": "activities", "content_designer": "content",
                "implementation_planner": "implementation"}

PANEL = tuple(sig for sig, _family in ALIGNMENT_SIGNALS)

#: Column heads for the by-arm table; the full names do not fit and share a prefix.
PANEL_SHORT = {"objective_assessment_similarity": "C2 sim",
               "objective_activity_similarity": "C3 sim",
               "activity_assessment_similarity": "C4 sim",
               "objective_cognitive_congruence": "congruence",
               "porter_mean": "porter",
               "webb_bloom_consistency": "webb"}


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


def _arm_names() -> dict[str, str]:
    """Artifact file name -> the arm it belongs to, for every declared arm. The
    primary is named by its pair; a Bloom arm says it swaps the classifier."""
    arms = presets.current()
    names = {presets.PRIMARY_ARTIFACT: f"{arms.primary_encoder}+{arms.primary_bloom}"}
    for key, arm in arms.encoders.items():
        if arm.suffix:
            names[f"alignment_scores.{arm.suffix}.json"] = key
    for key, arm in arms.bloom.items():
        if arm.suffix:
            names[f"alignment_scores.{arm.suffix}.json"] = f"bloom:{key}"
    for key, arm in arms.baseline.items():
        names[arm.artifact] = key
    return names


def _arm_scores(scen_dir: Path, agent: str) -> dict[str, dict]:
    """``arm -> {signal: value}`` from EVERY alignment artifact the scenario
    holds, so one pool shows the whole sensitivity star beside the primary."""
    names = _arm_names()
    out: dict[str, dict] = {}
    for path in sorted(scen_dir.glob("alignment_scores*.json")):
        doc = diagnostics.load_json(path)
        if not isinstance(doc, dict):
            continue
        sc = (doc.get("agents") or {}).get(agent) or {}
        arm = names.get(path.name) or path.stem.split(".", 1)[-1]
        out[arm] = {sig: diagnostics.number(sc.get(sig)) for sig in PANEL}
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
             "required_empty", "stopped", "stage_abandoned", "repair_window_closed",
             "budget_exhausted")

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
        view["high_disagreement"] = bool(r.get("high_disagreement"))
        view["score_range"] = _range_width(r.get("score_range"))
        out[agent] = view
    return out


def _range_width(text) -> float | None:
    """``"58.1-86.9"`` -> 28.8: how far apart the LLM judges scored one cell."""
    try:
        lo, hi = (float(x) for x in str(text).split("-", 1))
    except (TypeError, ValueError):
        return None
    return hi - lo


def _panel_view(scen_dir: Path, artifact: str) -> dict:
    """``agent -> {signal: value}`` from one alignment artifact of one scenario."""
    doc = diagnostics.load_json(scen_dir / artifact)
    if not isinstance(doc, dict):
        return {}
    return {agent: {sig: diagnostics.number(sc.get(sig)) for sig in PANEL}
            for agent, sc in (doc.get("agents") or {}).items() if isinstance(sc, dict)}


def _scenario_view(scen_dir: Path, artifact: str) -> dict:
    """The LLM judge view of one scenario with the alignment signals merged in,
    so one paired difference covers both families."""
    view = _judge_view(scen_dir)
    for agent, sigs in _panel_view(scen_dir, artifact).items():
        view.setdefault(agent, {}).update(sigs)
    return view


def _rosters(scen_dir: Path) -> dict[str, tuple[str, ...]]:
    """``agent -> the LLM judges that scored it`` in one scenario, sorted; ``{}``
    when unjudged. Per AGENT, not per scenario: a union over the scenario would
    read "A+B for one agent, A+C for the other" as one roster, A+B+C."""
    report = diagnostics.load_json(scen_dir / "comparison_report.json")
    if not isinstance(report, dict):
        return {}
    out = {}
    for r in (report.get("comparison") or {}).get("rankings") or []:
        models = tuple(sorted({str(j.get("model") or "?") for j in r.get("judges") or []}))
        if r.get("agent_id") and models:
            out[r["agent_id"]] = models
    return out


def _roster_of(run_dir: Path) -> dict[tuple[str, ...], int]:
    """Every LLM judge roster in one run dir, with how many (scenario, agent)
    cells it scored."""
    out: dict[tuple[str, ...], int] = {}
    for _sid, scen_dir in diagnostics.scenario_dirs(run_dir):
        for roster in _rosters(scen_dir).values():
            out[roster] = out.get(roster, 0) + 1
    return out


def _summary_scenarios(run_dir: Path) -> list[str]:
    """The scenarios the run was launched over, from ``benchmark_summary.json``,
    so one where every agent failed still counts in N and in the missing lists."""
    doc = diagnostics.load_json(run_dir / "benchmark_summary.json")
    by_variant = doc.get("scenarios") if isinstance(doc, dict) else None
    if not isinstance(by_variant, dict):
        return []
    return sorted({sid for v in by_variant.values() if isinstance(v, dict) for sid in v})


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
    the three LLM judge scores and the alignment signals, then ADDIE and
    Trajectory per judge, then each rubric item per judge. ``views`` is
    scenario -> :func:`_scenario_view` (a bare :func:`_judge_view` works too)."""
    diffs: dict[str, list[float]] = {}

    def add(key: str, a, b) -> None:
        if isinstance(a, float) and isinstance(b, float):
            diffs.setdefault(key, []).append(a - b)

    for view in views.values():
        mine, theirs = view.get(proposed), view.get(baseline)
        if not mine or not theirs:
            continue
        for score in (*GAP_SCORES, *PANEL):
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
        for score in (*GAP_SCORES, *PANEL):
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


def _run_roster(run_dir: Path) -> list[str]:
    """The agents a run dir was launched with (``benchmark_summary.json``), so a
    comparison or ablation run dir is read with its own roster; ``[]`` when the
    summary is missing."""
    doc = diagnostics.load_json(run_dir / "benchmark_summary.json")
    cfg = (doc.get("config") or {}) if isinstance(doc, dict) else {}
    return [a for a in cfg.get("agents") or [] if isinstance(a, str)]


#: A run whose items are fewer than this share distinct questions is flagged:
#: the count the LLM judge and the panel read is then mostly repetition.
REPEATED_ITEMS_SHARE = 0.5


def _item_counts(by_scenario: dict[str, list[dict]]) -> dict:
    """Items per run and how many of them are distinct questions, off the
    deliverable; a run with no item, or mostly repeats, is named."""
    reads = [rec["triad_references"] for recs in by_scenario.values() for rec in recs
             if isinstance(rec.get("triad_references"), dict)]
    items = [r.get("n_items") or 0 for r in reads]
    distinct = [r.get("n_distinct_items", r.get("n_items")) or 0 for r in reads]
    return {"n_runs": len(reads),
            "items_mean": _mean([float(x) for x in items]) if items else None,
            "distinct_mean": _mean([float(x) for x in distinct]) if distinct else None,
            "runs_without_items": sum(1 for n in items if n == 0),
            "runs_with_repeated_items": sum(
                1 for n, k in zip(items, distinct) if n and k / n < REPEATED_ITEMS_SHARE)}


def _proposed_ids() -> set[str]:
    """Every agent id the proposed system's adapter answers to."""
    from ..runner.agents import proposed_cells
    return set(proposed_cells(current_config()))


def _reference(proposed: list[str]) -> str:
    """The arm every other arm is read against: the ablation's declared
    reference when it ran here, else the first agent with harness records."""
    try:
        ref = current_config().profile("ablation").reference
    except (SystemExit, KeyError, AttributeError):
        ref = None
    return ref if ref in proposed else proposed[0]


def _posture(run_dir: Path) -> dict:
    """What the runner pinned for this run dir, or ``{}`` for a run dir that
    predates ``pinned_env``."""
    doc = diagnostics.load_json(run_dir / "benchmark_summary.json")
    cfg = (doc.get("config") or {}) if isinstance(doc, dict) else {}
    env = cfg.get("pinned_env") or {}
    out = {short: env[key] for key, short in POSTURE_ENV.items() if key in env}
    if cfg.get("rate_limit"):
        out["rate_limit"] = cfg["rate_limit"]
    return out


def _findings_by_stage(scen_dir: Path, agent: str) -> dict | None:
    """``{"open": {stage: n}, "all": {stage: n}}`` from one ledger, each finding
    charged to the stage its owning family writes."""
    findings = diagnostics.load_json(scen_dir / f"{agent}_violations.json")
    if not isinstance(findings, list):
        return None
    out: dict[str, dict[str, int]] = {"open": {}, "all": {}}
    for f in findings:
        if not isinstance(f, dict):
            continue
        stage = FAMILY_STAGE.get(f.get("first_family") or f.get("target_designer"), "other")
        out["all"][stage] = out["all"].get(stage, 0) + 1
        if f.get("outcome") == "open":
            out["open"][stage] = out["open"].get(stage, 0) + 1
    return out


def _stage_findings_summary(per_scenario: list[dict]) -> dict | None:
    """Mean findings per run, per owning stage, in stage order."""
    if not per_scenario:
        return None
    stages = [st for st in diagnostics.STAGE_ORDER
              if any(st in one["all"] for one in per_scenario)]
    stages += sorted({st for one in per_scenario for st in one["all"]} - set(stages))
    n = len(per_scenario)
    return {"n_runs": n, "by_stage": {
        st: {"open": sum(one["open"].get(st, 0) for one in per_scenario) / n,
             "all": sum(one["all"].get(st, 0) for one in per_scenario) / n}
        for st in stages}}


def _judge_reliability(views: dict[str, dict], agent: str) -> dict | None:
    cells = [v[agent] for v in views.values()
             if agent in v and v[agent].get("judges")]
    if not cells:
        return None
    widths = [c["score_range"] for c in cells if isinstance(c.get("score_range"), float)]
    return {"n_judged": len(cells),
            "high_disagreement": sum(1 for c in cells if c.get("high_disagreement")),
            "range_mean": _mean(widths) if widths else None,
            "range_max": max(widths) if widths else None}


def _arm_cells(agents: list[str]) -> dict[tuple[str, str], str] | None:
    """(agent_mode, context_mode) -> arm id, when all four ablation cells are in
    the roster; None otherwise."""
    try:
        from .ablation import factorial_cells
        cells = factorial_cells()
    except (SystemExit, KeyError, AttributeError):
        return None
    if len(cells) != 4 or not all(a in agents for a in cells.values()):
        return None
    return cells


def factorial(views: dict[str, dict], cells: dict[tuple[str, str], str]) -> dict:
    """The 2x2 read descriptively, per measure, over the scenarios where all four
    cells have a value: each axis's main effect (the mean of its two simple
    effects), each simple effect, and the interaction -- multi/graph minus
    single/prose throughout, so positive favours decomposition / the graph."""
    mg, sg = cells[("multi", "graph")], cells[("single", "graph")]
    mp, sp = cells[("multi", "prose")], cells[("single", "prose")]
    out: dict = {}
    for m in (*GAP_SCORES, *PANEL):
        d = {k: [] for k in ("decomposition", "decomposition|graph", "decomposition|prose",
                             "substrate", "substrate|multi", "substrate|single", "interaction")}
        for view in views.values():
            vals = [(view.get(a) or {}).get(m) for a in (mg, sg, mp, sp)]
            if not all(isinstance(x, float) for x in vals):
                continue
            a, b, c, e = vals
            d["decomposition|graph"].append(a - b)
            d["decomposition|prose"].append(c - e)
            d["decomposition"].append(((a - b) + (c - e)) / 2)
            d["substrate|multi"].append(a - c)
            d["substrate|single"].append(b - e)
            d["substrate"].append(((a - c) + (b - e)) / 2)
            d["interaction"].append((a - b) - (c - e))
        if d["interaction"]:
            out[m] = {k: _mean_se(v) for k, v in d.items()}
    return out


def pool(run_dirs_by_model: dict[str, list[Path]], agents: list[str] | None,
         panel_artifact: str = presets.PRIMARY_ARTIFACT) -> tuple[dict, list[dict]]:
    """(pooled document, CSV rows). Pure: no printing, no writing.

    ``agents`` is read in every run dir; ``None`` reads each run dir with the
    roster it was launched with, which is what lets one pool read a tune, a
    comparison and an ablation run dir side by side."""
    fixed = agents
    entries, rows = [], []
    ordered = sorted(((label, d) for label, dirs in run_dirs_by_model.items() for d in dirs),
                     key=lambda ld: ld[1].name[-15:])        # the timestamp: oldest first
    for label, run_dir in ordered:
        agents = list(fixed or _run_roster(run_dir) or current_config().profile("tune").agents)
        cells: dict[str, dict[str, list[dict]]] = {a: {} for a in agents}
        agent_rows: dict[str, list[dict]] = {a: [] for a in agents}
        views: dict[str, dict] = {}
        outputs: dict[str, list[Path]] = {a: [] for a in agents}
        arm_rows: dict[str, dict[str, dict[str, list[float]]]] = {a: {} for a in agents}
        stage_findings: dict[str, list[dict]] = {a: [] for a in agents}
        scenario_ids: list[str] = _summary_scenarios(run_dir)
        rosters: dict[tuple[str, ...], int] = {}
        for sid, scen_dir in diagnostics.scenario_dirs(run_dir):
            if sid not in scenario_ids:
                scenario_ids.append(sid)
            view = _scenario_view(scen_dir, panel_artifact)
            if view:
                views[sid] = view
            for a, roster in _rosters(scen_dir).items():
                if a in agents:
                    rosters[roster] = rosters.get(roster, 0) + 1
            for a in agents:
                fs = _findings_by_stage(scen_dir, a)
                if fs is not None:
                    stage_findings[a].append(fs)
                if (scen_dir / f"{a}_output.json").exists():
                    outputs[a].append(scen_dir / f"{a}_output.json")
                cell = diagnostics.read_cell(scen_dir, a)
                if cell is None:
                    continue
                cells[a].setdefault(sid, []).append(cell)
                row = _row(label, run_dir, sid, a, cell,
                           _scores(scen_dir, a, panel_artifact))
                for arm, sigs in _arm_scores(scen_dir, a).items():
                    for sig, v in sigs.items():
                        if isinstance(v, float):
                            arm_rows[a].setdefault(arm, {}).setdefault(sig, []).append(v)
                            row[f"{sig}@{arm}"] = v
                agent_rows[a].append(row)
                rows.append(row)
        # Two LLM judge rosters are never pooled together: a run dir judged by
        # both gets no gap and no pooled LLM judge score at all.
        mixed_roster = len(rosters) > 1
        per_agent = {}
        for a in agents:
            # An agent of the launch roster with no trajectory anywhere stays,
            # as 0/N, rather than leaving the report.
            summary = diagnostics.summarize(cells[a], diagnostics.STAGE_ORDER)
            summary["run_config"] = _calibrated(
                [rec for recs in cells[a].values() for rec in recs])
            summary["scores"] = _score_summary(agent_rows[a])
            if mixed_roster:
                for score in LLM_JUDGE_SCORES:
                    summary["scores"].pop(score, None)
            summary["alignment_by_arm"] = {
                arm: {sig: {"n": len(v), "mean": _mean(v)} for sig, v in sigs.items()}
                for arm, sigs in arm_rows[a].items()}
            summary["fabrication"] = fabrication.summarize(
                [fabrication.audit_file(p) for p in outputs[a]])
            if summary.get("autonomy"):
                summary["harness"] = run_health(cells[a], outputs[a])
                tr = summary.get("triad_references") or {}
                attention = summary["harness"]["attention"]
                if tr.get("activities_prepare") == 0:
                    # Activities exist and not one names an assessment task: C4
                    # cannot be read on this arm at all, whatever its score says.
                    attention.append("no_c4_references")
                summary["items"] = _item_counts(cells[a])
                if summary["items"]["runs_without_items"]:
                    attention.append("no_assessment_items")
                if summary["items"]["runs_with_repeated_items"]:
                    attention.append("repeated_items")
                abandoned: dict[str, int] = {}
                for recs in cells[a].values():
                    for rec in recs:
                        for st in rec.get("abandoned_stages") or []:
                            abandoned[st] = abandoned.get(st, 0) + 1
                summary["abandoned_stages"] = abandoned
            summary["missing_scenarios"] = [sid for sid in scenario_ids if sid not in cells[a]]
            summary["judge_reliability"] = _judge_reliability(views, a)
            summary["findings_by_stage"] = _stage_findings_summary(stage_findings[a])
            per_agent[a] = summary
        # Proposed = an id the adapter answers to, whether or not it produced
        # anything: an arm that failed everywhere is a failed arm, never a
        # baseline the others are measured against.
        known = _proposed_ids()
        proposed = [a for a in per_agent if a in known or per_agent[a].get("autonomy")]
        gaps = arm_gaps = fact = {}
        if not mixed_roster:
            gaps = {f"{p} - {b}": paired_gap(views, p, b)
                    for p in proposed for b in per_agent if b not in proposed}
            # The ablation arms among themselves: each other arm minus the
            # reference, paired by scenario.
            ref = _reference(proposed) if proposed else None
            arm_gaps = {f"{p} - {ref}": paired_gap(views, p, ref)
                        for p in proposed if p != ref}
            cells_2x2 = _arm_cells(list(per_agent))
            fact = factorial(views, cells_2x2) if cells_2x2 else {}
        artifacts = sorted({p.name for _sid, sd in diagnostics.scenario_dirs(run_dir)
                            for p in sd.glob("alignment_scores*.json")})
        names = _arm_names()
        panel_missing = (None if panel_artifact in artifacts or not artifacts
                         else [names.get(a, a) for a in artifacts])
        entries.append({"run_dir": run_dir.name, "model": label,
                        "panel_missing": panel_missing,
                        "n_scenarios": len(scenario_ids), "roster": agents,
                        "posture": _posture(run_dir),
                        "judge_rosters": {" + ".join(r): n for r, n in rosters.items()},
                        "mixed_roster": mixed_roster,
                        "agents": per_agent, "gaps": gaps, "arm_gaps": arm_gaps,
                        "factorial": fact, "_views": views})
    doc = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "config": {
            "experiment": "tune",
            "agents": fixed or "per run dir (benchmark_summary.json)",
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


def _print_gap(title: str, g: dict) -> None:
    """One paired gap: the LLM judge scores, then each judge, the rubric items
    every judge separates, and the alignment signals."""
    print(f"  {title}  (mean±se; ~ = inside {DETECTION_SE:g} se, not detected)")
    print("      Total " + _fmt_gap(g.get("total_score")) + "  ADDIE "
          + _fmt_gap(g.get("addie_median")) + "  Traj " + _fmt_gap(g.get("trajectory_score")))
    models = sorted({k.split("@", 1)[1] for k in g if "@" in k})
    for model in models:
        print(f"      {model:<34} ADDIE {_fmt_gap(g.get(f'addie@{model}'))}  "
              f"Traj {_fmt_gap(g.get(f'traj@{model}'))}")
    items = sorted({k.split("@", 1)[0] for k in g if "@" in k} - {"addie", "traj"})
    detected = []
    for item in items:
        per = [g.get(f"{item}@{m}") for m in models]
        if all(x and x.get("detected") for x in per) and len(
                {x["mean"] > 0 for x in per}) == 1:
            detected.append(f"{item} " + "/".join(f"{x['mean']:+.1f}" for x in per))
    n = (g.get("total_score") or {}).get("n", 0)
    if models and n < 2:
        print(f"      items every LLM judge separates: not computable (n={n}, no standard error)")
    elif models:
        print("      items every LLM judge separates: " + (", ".join(detected) or "none"))
    if any(sig in g for sig in PANEL):
        print("      alignment: " + "  ".join(
            f"{PANEL_SHORT[sig]} {_fmt_signal(g.get(sig))}" for sig in PANEL))


def _fmt_signal(g: dict | None) -> str:
    """A gap on a [0,1] signal, at a precision that shows it."""
    if not g or "mean" not in g:
        return "--"
    if "se" not in g:
        return f"{g['mean']:+.3f}"
    return f"{g['mean']:+.3f}±{g['se']:.3f}" + ("" if g["detected"] else "~")


def _fmt_measure(m: str, g: dict | None) -> str:
    return _fmt_signal(g) if m in PANEL else _fmt_gap(g)


def print_report(doc: dict) -> None:
    print("\n" + "=" * 78)
    print("TUNE DIAGNOSTICS")
    print("=" * 78)
    print(f"alignment signals from {doc['config'].get('panel_artifact')}")
    for entry in doc["runs"]:
        if entry.get("panel_missing"):
            print(f"  ! {entry['run_dir']}: no scenario has {doc['config'].get('panel_artifact')}"
                  f"; arms present: {', '.join(entry['panel_missing']) or 'none'}"
                  " -- pass --encoder <arm> to read one of them")
    for entry in doc["runs"]:
        print(f"\n[{entry['run_dir']}]  {entry.get('n_scenarios', '?')} scenarios")
        posture = entry.get("posture") or {}
        if posture:
            print("  posture: " + "  ".join(f"{k}={v}" for k, v in posture.items()))
        rosters = entry.get("judge_rosters") or {}
        if entry.get("mixed_roster"):
            print("  !! MIXED LLM JUDGE ROSTERS -- no gap and no pooled LLM judge score "
                  "for this run dir; re-judge it with one roster ((scenario, agent) cells):")
            for r, n in rosters.items():
                print(f"       {n:>3} scenario(s): {r}")
        elif rosters:
            print("  LLM judges: " + next(iter(rosters)))
        for agent, s in entry["agents"].items():
            h = s["health"]
            print(f"  [{s.get('n_scenarios', 0)}/{entry.get('n_scenarios', '?')}] "
                  + diagnostics.one_line(agent, s))
            if s.get("missing_scenarios"):
                print("      MISSING: " + ", ".join(s["missing_scenarios"]))
            sc = s.get("scores") or {}
            if sc:
                print("      scores: " + "  ".join(
                    f"{k}={v['mean']:.3g}(n={v['n']})" for k, v in sc.items()))
            jr = s.get("judge_reliability")
            if jr:
                rm = jr.get("range_mean")
                print(f"      LLM judges: high disagreement {jr['high_disagreement']}/"
                      f"{jr['n_judged']}  range mean "
                      f"{'--' if rm is None else format(rm, '.1f')}  max "
                      f"{'--' if jr.get('range_max') is None else format(jr['range_max'], '.1f')}")
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
                print(f"      turns by stage (mean/p90/max, ceiling {ceiling}; the stage's own "
                      f"loop), % gave up, % cut, then requests (failed ones included) and tokens "
                      f"of the WHOLE stage (Developers included), Developer sets gave up per run:")
                for stage, st in au["by_stage"].items():
                    t = st.get("turns_used") or {}
                    if not t.get("n"):
                        continue
                    sg = (st.get("sets_gave_up") or {}).get("mean")
                    tok = [(st.get(k) or {}).get("mean") for k in ("prompt_tokens",
                                                                   "completion_tokens")]
                    calls = (st.get("llm_calls") or {}).get("mean")
                    print(f"        {stage:<15} {t['mean']:5.1f} / {t['p90']:5.1f} / "
                          f"{t['max']:4.0f}   gave_up {st.get('pct_gave_up', 0):3.0f}%  "
                          f"cut {st.get('pct_via_budget_exhaustion', 0):3.0f}%"
                          + (f"  {calls:4.0f} calls {sum(tok) / 1000:6.0f}k tok"
                             if calls is not None and None not in tok else "")
                          + (f"  sets gave_up {sg:.1f}" if sg else ""))
            ws = s.get("work_sets") or {}
            for phase, w in ws.items():
                def m(k, w=w):
                    return (w.get(k) or {}).get("mean")
                parts = [f"sets {m('set_count'):.1f}" if m("set_count") is not None else None,
                         f"appended {m('appended_sets'):.1f}" if m("appended_sets") else None,
                         f"oversized {m('oversized_splits'):.1f}"
                         if m("oversized_splits") else None]
                tp, tc = w.get("tasks_planned") or {}, w.get("task_ceiling") or {}
                if tp.get("n") and tc.get("n"):
                    parts.append(f"tasks {tp['mean']:.1f} (max {tp['max']:.0f}) vs ceiling "
                                 f"{tc['mean']:.1f}")
                parts = [p for p in parts if p]
                if parts:
                    print(f"      work sets {phase:<14} " + "  ".join(parts))
            by_arm = s.get("alignment_by_arm") or {}
            if len(by_arm) > 1:
                print("      alignment by arm (mean over scenarios):")
                print("        " + f"{'arm':<22}"
                      + "".join(f"{PANEL_SHORT.get(sig, sig[:11]):>12}" for sig in PANEL))
                for arm, sigs in by_arm.items():
                    print("        " + f"{arm:<22}" + "".join(
                        f"{sigs[sig]['mean']:>12.3f}" if sig in sigs else f"{'--':>12}"
                        for sig in PANEL))
            lg = s.get("ledger")
            if lg and lg.get("open_by_type"):
                top = list(lg["open_by_type"].items())[:6]
                print("      open findings by type: " + ", ".join(f"{t} {n}" for t, n in top))
            fs = s.get("findings_by_stage")
            if fs and fs.get("by_stage"):
                prose = "prose" in ((s.get("run_config") or {}).get("context_mode") or [])
                print("      findings per run by owning stage (open/all): " + "  ".join(
                    f"{st} {v['open']:.1f}/{v['all']:.1f}" for st, v in fs["by_stage"].items())
                    + ("  [prose: within-artifact checks only -- read within this arm]"
                       if prose else ""))
            hh = s.get("harness")
            if hh:
                print(f"      harness: passes {hh.get('passes', 0):.0f} (ok {hh.get('pass_accepted', 0):.0f}"
                      f", empty {hh.get('pass_empty', 0):.0f}, refused {hh.get('pass_refused', 0):.0f}"
                      f", skipped {hh.get('pass_skipped', 0):.0f})"
                      f"  rejected {hh.get('rejected', 0):.0f} (no args {hh.get('rejected_empty_args', 0):.0f})"
                      f"  gave_up {hh.get('gave_up', 0):.0f}  overflow {hh.get('context_overflow', 0):.0f}"
                      f"  cap {hh.get('completion_cap', 0):.0f}  conn {hh.get('connection', 0):.0f}"
                      f"  required_empty {hh.get('required_empty', '--')}")
                if hh.get("stage_abandoned") or hh.get("repair_window_closed") or hh.get(
                        "budget_exhausted"):
                    ab = s.get("abandoned_stages") or {}
                    print(f"      loop ends: stage_abandoned {hh.get('stage_abandoned', 0):.0f}"
                          + (" (" + ", ".join(f"{st} {n}" for st, n in ab.items()) + ")"
                             if ab else "")
                          + f"  repair_window_closed {hh.get('repair_window_closed', 0):.0f}"
                          f"  budget_exhausted {hh.get('budget_exhausted', 0):.0f}")
                it = s.get("items") or {}
                if it.get("n_runs"):
                    print(f"      assessment items per run {it['items_mean']:.1f} "
                          f"({it['distinct_mean']:.1f} distinct questions)  "
                          f"runs with none {it['runs_without_items']}  "
                          f"runs mostly repeats {it['runs_with_repeated_items']}")
                print("      ATTENTION: " + (", ".join(hh["attention"]) if hh.get("attention")
                                             else "none"))
            fb = s.get("fabrication") or {}
            if fb.get("n"):
                print(f"      post-pilot claims: result fields {fb['with_result_fields']}/{fb['n']}"
                      f"  human reviewers {fb['with_human_reviewers']}/{fb['n']}"
                      f"  decision taken {fb['with_decision_taken']}/{fb['n']}")
        for pair, g in (entry.get("arm_gaps") or {}).items():
            if g:
                _print_gap(f"arm gap {pair}", g)
        fact = entry.get("factorial") or {}
        if fact:
            print("  2x2 (multi/graph minus single/prose; main effect = mean of its two "
                  "simple effects; ~ = inside noise):")
            print(f"      {'measure':<14}{'decomposition':>18}{'substrate':>18}{'interaction':>18}")
            for m, eff in fact.items():
                label = PANEL_SHORT.get(m, {"total_score": "Total", "addie_median": "ADDIE",
                                            "trajectory_score": "Traj"}.get(m, m))
                n = (eff.get("interaction") or {}).get("n", 0)
                print(f"      {label:<14}" + "".join(
                    f"{_fmt_measure(m, eff.get(k)):>18}"
                    for k in ("decomposition", "substrate", "interaction")) + f"   n={n}")
        gaps = {p: g for p, g in (entry.get("gaps") or {}).items() if g}
        if len(gaps) > 2:
            # A comparison run: one line per pair, the detail in the JSON.
            print(f"  gaps to each baseline (mean±se; ~ = inside {DETECTION_SE:g} se; "
                  "per judge and per item in the JSON):")
            for pair, g in gaps.items():
                print(f"      {pair:<52} Total {_fmt_gap(g.get('total_score')):>12}  "
                      f"ADDIE {_fmt_gap(g.get('addie_median')):>12}  "
                      f"Traj {_fmt_gap(g.get('trajectory_score')):>12}")
                if any(sig in g for sig in PANEL):
                    print("          alignment: " + "  ".join(
                        f"{PANEL_SHORT[sig]} {_fmt_signal(g.get(sig))}" for sig in PANEL))
        else:
            for pair, g in gaps.items():
                _print_gap(f"gap {pair}", g)
    _print_across(doc)


def _print_across(doc: dict) -> None:
    """Every pair's Total and ADDIE gap, one column per run dir: the rungs of a
    comparison, or successive tune runs, read side by side."""
    runs = [e for e in doc["runs"] if (e.get("gaps") or e.get("arm_gaps"))]
    if len(runs) < 2:
        return
    pairs: list[str] = []
    for e in runs:
        for p in (*(e.get("gaps") or {}), *(e.get("arm_gaps") or {})):
            if p not in pairs:
                pairs.append(p)
    # model + MMDD_HHMM: two runs of one model a day apart stay apart.
    heads = [f"{e['model']}:{e['run_dir'][-11:-2]}" for e in runs]
    # Columns judged by another LLM judge roster than the first are marked: a
    # gap is a difference within one roster, and two rosters' gaps are not
    # the same quantity.
    first = next(iter(runs[0].get("judge_rosters") or {}), None)
    other = [bool(e.get("judge_rosters")) and next(iter(e["judge_rosters"])) != first
             for e in runs]
    heads = [h + ("*" if o else "") for h, o in zip(heads, other)]
    width = max(14, *(len(h) + 2 for h in heads))
    for score, label in (("total_score", "Total"), ("addie_median", "ADDIE")):
        print(f"\n{label} gap by run dir (mean±se):")
        print(f"  {'pair':<52}" + "".join(f"{h:>{width}}" for h in heads))
        for p in pairs:
            cells = []
            for e in runs:
                g = (e.get("gaps") or {}).get(p) or (e.get("arm_gaps") or {}).get(p)
                cells.append(_fmt_gap((g or {}).get(score)))
            if all(c == "--" for c in cells):
                continue
            print(f"  {p:<52}" + "".join(f"{c:>{width}}" for c in cells))
    if any(other):
        print(f"  * judged by another LLM judge roster than {first!r}: do not compare "
              "across the columns")


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


def views_of(run_dir: Path,
             panel_artifact: str = presets.PRIMARY_ARTIFACT) -> dict[str, dict]:
    """``scenario -> _scenario_view`` for every scored scenario of one run dir."""
    views = {}
    for sid, scen_dir in diagnostics.scenario_dirs(run_dir):
        view = _scenario_view(scen_dir, panel_artifact)
        if view:
            views[sid] = view
    return views


def add_shifts(doc: dict, against: Path) -> None:
    """Every run's gap SHIFT against one earlier run dir: what a change to the
    proposed system moved, with the other side's own drift cancelled -- for the
    gaps to the baseline and for the gaps between the ablation arms alike."""
    before = views_of(against, doc["config"].get("panel_artifact") or presets.PRIMARY_ARTIFACT)
    then = {" + ".join(r) for r in _roster_of(against)}
    for entry in doc["runs"]:
        now = set(entry.get("judge_rosters") or {})
        if len(then) > 1 or now != then:
            # A shift subtracts a gap under one roster from a gap under
            # another: the baseline's drift cancels, the judges' preferences
            # for one agent over the other do not.
            entry["shift_vs"] = {"run_dir": against.name, "pairs": {},
                                 "skipped": ("judged by another LLM judge roster: "
                                             f"{sorted(then) or 'unjudged'} then, "
                                             f"{sorted(now) or 'unjudged'} now")}
            continue
        after = entry.get("_views") or {}
        pairs = [*(entry.get("gaps") or {}), *(entry.get("arm_gaps") or {})]
        entry["shift_vs"] = {"run_dir": against.name, "pairs": {
            pair: gap_shift(before, after, *pair.split(" - ", 1)) for pair in pairs}}


def print_shifts(doc: dict) -> None:
    for entry in doc["runs"]:
        sv = entry.get("shift_vs")
        if not sv or entry["run_dir"] == sv["run_dir"]:
            continue
        if sv.get("skipped"):
            print(f"\n[{entry['run_dir']}] vs [{sv['run_dir']}]  no shift: {sv['skipped']}")
            continue
        for pair, g in sv["pairs"].items():
            print(f"\n[{entry['run_dir']}] vs [{sv['run_dir']}]  shift of {pair}:  "
                  f"Total {_fmt_gap(g.get('total_score'))}  ADDIE {_fmt_gap(g.get('addie_median'))}"
                  f"  Traj {_fmt_gap(g.get('trajectory_score'))}")
            if any(sig in g for sig in PANEL):
                print("      alignment: " + "  ".join(
                    f"{PANEL_SHORT[sig]} {_fmt_signal(g.get(sig))}" for sig in PANEL))


def run(*, patterns: list[str] | None = None, out: Path | None = None,
        agents: list[str] | None = None, quiet: bool = False,
        against: Path | None = None, encoder: str | None = None,
        experiment: str = "tune") -> Path:
    """Discover, pool, report and write. Returns the JSON path.

    ``experiment`` names the profile whose run dirs are read when no glob is
    given (``tune``, ``comparison`` or ``ablation``); each run dir is read with
    its own roster unless ``agents`` fixes one. Reading a comparison or an
    ablation run dir here is a diagnostic of the harness, never the pooled
    result the paper reads -- that is ``pool comparison`` / ``pool ablation``."""
    profile = current_config().profile(experiment)
    roster = agents or None
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
    doc["config"]["read_from"] = experiment
    name = "pooled_tune.json" if experiment == "tune" else f"pooled_tune.{experiment}.json"
    target = out or (paths.results_root() / name)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(json_safe(doc), ensure_ascii=False, indent=2) + "\n",
                      encoding="utf-8")
    csv_path = target.with_name(
        target.stem.replace("pooled_tune", "tune_diagnostics") + ".csv"
        if target.stem.startswith("pooled_tune") else "tune_diagnostics.csv")
    write_csv(rows, csv_path)
    if not quiet:
        print(f"\nwrote {target}\nwrote {csv_path}")
    return target

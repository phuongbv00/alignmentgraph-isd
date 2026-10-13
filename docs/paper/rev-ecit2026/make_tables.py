#!/usr/bin/env python3
"""Generate the REV-ECIT 2026 tables and number macros from the pooled results.

Reads the two documents the experiment's own pooling writes:

  pooled_comparison.json  (./isd-exp pool comparison)  -> Bảng I, Bảng II
  pooled_ablation.json    (./isd-exp pool ablation)    -> Bảng III

Four disclosures the pooling does not carry are read from the run dirs those two
documents name, and from the Bloom checkpoint's own held-out record:

  spread between the three LLM judges, and each judge's mean ADDIE for the
  proposed system and React-ADDIE        <- comparison_report.json per scenario
  constrained passes of the proposed system  <- its trajectory metadata.autonomy
  family-A signals of the four ablation arms <- alignment_summary.csv (primary arm;
                                                descriptive, no test)
  Bloom classifier agreement              <- held_out_metrics.json

and writes into ``generated/`` beside this file:

  tab_judge.tex     Bảng I   LLM judge scores (mean ± SD across scenarios) + tokens
  tab_panel.tex     Bảng II  the six alignment signals (mean across scenarios)
  tab_ablation.tex  Bảng III the 2x2 arms: ADDIE, Total, closed triads, tokens
  macros.tex        every number the prose cites, as \\newcommand

Statistics are the pooling's, not recomputed here: paired Wilcoxon per scenario
with Holm within one score (LLM judge) or within one signal (panel); the
ablation's two registered tests (H-D, H-S) and their Holm family come from
``registered``. Every mean and every test is under failure = 0: a scenario where
a system left no scorable output scores 0 for it. A baseline cell is starred when
its difference from the proposed system has p_holm < ALPHA.

The frame has ONE model size; a document with more than one is refused rather
than silently reduced to its first size.

Run with the experiment's interpreter (stdlib only, but kept beside the rest):
  experiments/.venv/bin/python docs/paper/rev-ecit2026/make_tables.py
"""
from __future__ import annotations

import argparse
import ast
import csv
import json
import math
import statistics
from pathlib import Path

HERE = Path(__file__).resolve().parent
RESULTS = HERE.parents[2] / "experiments" / "results"
BLOOM_METRICS = (HERE.parents[2] / "experiments" / "tests" / "fixtures" / "bloom"
                 / "held_out_metrics.json")
JUDGES = {  # LLM judge model id -> macro code
    "openai/gpt-6-luna": "Luna",
    "google/gemini-3.1-flash-lite": "Gem",
    "deepseek/deepseek-v4.1-flash": "Ds",
}
OUT = HERE / "generated"
ALPHA = 0.05

AGENTS = {  # id -> (display, macro code)
    "alignmentgraph-isd": ("AlignmentGraph-ISD", "AG"),
    "baseline": ("Baseline", "Base"),
    "react-isd": ("React-ADDIE", "React"),
    "addie-agent": ("ADDIE-Agent", "Addie"),
    "dick-carey-agent": ("Dick-Carey-Agent", "Dick"),
    "rpisd-agent": ("RPISD-Agent", "Rpisd"),
    "eduplanner": ("EduPlanner", "Edu"),
}
ARMS = {  # ablation arm id -> (display, macro code)
    "alignmentgraph-isd": ("multi, graph (đề xuất)", "MG"),
    "alignmentgraph-isd-multi-prose": ("multi, prose", "MP"),
    "alignmentgraph-isd-single-graph": ("single, graph", "SG"),
    "alignmentgraph-isd-single-prose": ("single, prose", "SP"),
}
SCORES = {  # pooled key -> (mean field, sd field, header, macro code)
    "addie_median": ("mean_addie", "sd_addie_across_scenarios", "ADDIE", "Addie"),
    "trajectory_score": ("mean_traj", "sd_traj_across_scenarios", "Trajectory", "Traj"),
    "total_score": ("mean_total", "sd_total_across_scenarios", "Total", "Total"),
}
SIGNALS = {  # panel key -> (header, macro code)
    "objective_assessment_similarity": ("OA", "OA"),
    "objective_activity_similarity": ("OT", "OT"),
    "activity_assessment_similarity": ("TA", "TA"),
    "objective_cognitive_congruence": ("Cg", "Cg"),
    "porter_mean": ("Po", "Po"),
    "webb_bloom_consistency": ("Wb", "Wb"),
}

DASH = "--"


# ── formatting ──────────────────────────────────────────────────────────────
def ok(x) -> bool:
    return isinstance(x, (int, float)) and not (isinstance(x, float) and math.isnan(x))


def f1(x) -> str:
    return f"{x:.1f}" if ok(x) else DASH


def f2(x) -> str:
    return f"{x:.2f}" if ok(x) else DASH


def fp(p) -> str:
    """A p-value with its relation, so the prose writes ``$p$\\cmpXP`` for
    both "p = 0.532" and "p < 0.001"."""
    if not ok(p):
        return DASH
    return "${<}\\,0.001$" if p < 0.001 else f"${{=}}\\,{p:.3f}$"


def pct(x) -> str:
    return f"{100 * x:.0f}" if ok(x) else DASH


def ktok(x) -> str:
    return f"{x / 1000:.0f}" if ok(x) else DASH


def bold_best(cells: list[str], values: list, higher: bool = True) -> list[str]:
    """Bold the best value of a column; ties are all bolded."""
    vals = [v for v in values if ok(v)]
    if not vals:
        return cells
    best = max(vals) if higher else min(vals)
    return [rf"\textbf{{{c}}}" if ok(v) and v == best else c
            for c, v in zip(cells, values)]


def table_note(*lines: str) -> list[str]:
    """Notes set under the tabular at column width, so a long note wraps
    instead of widening the table."""
    return [r"  \par\vspace{2pt}",
            r"  {\scriptsize\raggedright " + r"\\ ".join(lines) + r"\par}"]


def star(cell: str, p) -> str:
    return cell + r"$^{*}$" if ok(p) and p < ALPHA else cell


# ── reading ─────────────────────────────────────────────────────────────────
def one_model(doc: dict, what: str) -> dict:
    models = doc.get("models") or []
    if len(models) != 1:
        raise SystemExit(f"{what}: expected exactly one model size, found {len(models)}. "
                         "This frame reports one rung; pool that rung alone.")
    return models[0]


def comparison_rows(model: dict, score: str, policy: str) -> dict[str, dict]:
    rows = (model.get("comparisons", {}).get("by_score", {}).get(score, {})
            .get("policies", {}).get(policy, []))
    return {r["baseline"]: r for r in rows}


class Macros:
    def __init__(self) -> None:
        self.lines: list[str] = []

    def add(self, name: str, value: str) -> None:
        if not name.isalpha():
            raise ValueError(f"macro name must be letters only: {name}")
        self.lines.append(rf"\newcommand{{\{name}}}{{{value}}}")

    def write(self, path: Path) -> None:
        path.write_text("% Generated by make_tables.py — do not edit.\n"
                        + "\n".join(self.lines) + "\n", encoding="utf-8")


# ── Bảng I and II: the comparison ───────────────────────────────────────────
def comparison_tables(doc: dict, mac: Macros) -> tuple[str, str]:
    cfg = doc["config"]
    proposed = cfg["proposed"]
    order = [proposed] + [b for b in cfg["baselines"] if b != proposed]
    model = one_model(doc, "pooled_comparison")
    agents = model["agents"]
    n_union = model.get("n_scenarios_union")
    policy = model["comparisons"]["primary_policy"]
    tokens = (doc.get("token_usage", {}).get("models", {}).get(model["label"], {}))
    mac.add("ModelLabel", model["label"])
    mac.add("NScenCmp", str(n_union))

    # ---- Bảng I: LLM judge scores + tokens
    cols: dict[str, list[str]] = {s: [] for s in SCORES}
    vals: dict[str, list] = {s: [] for s in SCORES}
    tok_cells, failed = [], []
    for a in order:
        st = agents.get(a, {})
        code = AGENTS.get(a, (a, a))[1]
        n_failed = st.get("n_scenarios_any_missing")
        if ok(n_failed) and n_failed:
            failed.append((a, n_failed))
        for s, (mf, sf, _, sc) in SCORES.items():
            m, sd = st.get(mf), st.get(sf)
            p = comparison_rows(model, s, policy).get(a, {}).get("p_holm")
            cell = f"{f1(m)}\\,$\\pm$\\,{f1(sd)}" if ok(m) else DASH
            cols[s].append(star(cell, p) if a != proposed else cell)
            vals[s].append(m)
            mac.add(f"cmp{code}{sc}", f1(m))
            mac.add(f"cmp{code}{sc}SD", f1(sd))
            if a != proposed:
                row = comparison_rows(model, s, policy).get(a, {})
                mac.add(f"cmp{code}{sc}Diff", f1(row.get("mean_diff")))
                mac.add(f"cmp{code}{sc}P", fp(row.get("p_holm")))
        t = tokens.get(a, {}).get("total_tokens", {}).get("mean")
        tok_cells.append(ktok(t))
        mac.add(f"cmp{code}Tok", ktok(t))
        calls = tokens.get(a, {}).get("llm_calls", {}).get("mean")
        secs = tokens.get(a, {}).get("execution_time_seconds", {}).get("mean")
        mac.add(f"cmp{code}Calls", f"{calls:.0f}" if ok(calls) else DASH)
        mac.add(f"cmp{code}Min", f"{secs / 60:.0f}" if ok(secs) else DASH)
    for s in SCORES:
        cols[s] = bold_best(cols[s], vals[s])
    ag_tok = tokens.get(proposed, {}).get("total_tokens", {}).get("mean")
    re_tok = tokens.get("react-isd", {}).get("total_tokens", {}).get("mean")
    if ok(ag_tok) and ok(re_tok) and re_tok:
        mac.add("cmpTokRatioReact", f"{ag_tok / re_tok:.1f}")

    body = []
    for i, a in enumerate(order):
        name = AGENTS.get(a, (a, a))[0]
        cells = [cols[s][i] for s in SCORES] + [tok_cells[i]]
        body.append(f"    {name} & " + " & ".join(cells) + r" \\")
    notes = [r"$^{*}$ khác AlignmentGraph-ISD, Wilcoxon theo cặp, Holm trong từng điểm, "
             r"$p<0.05$."]
    if failed:
        notes.append("Kịch bản không có đầu ra chấm được, tính 0 điểm: "
                     + ", ".join(f"{AGENTS.get(a, (a,))[0]} {n}" for a, n in failed) + ".")
    tab1 = "\n".join([
        r"\begin{table}[t]",
        rf"  \caption{{Thí nghiệm 1: điểm LLM judge (trung bình $\pm$ độ lệch chuẩn qua "
        rf"{n_union} kịch bản) và token mỗi kịch bản}}",
        r"  \label{tab:judge}",
        r"  \centering",
        r"  \footnotesize",
        r"  \setlength{\tabcolsep}{2.5pt}",
        r"  \begin{tabular}{@{}lcccc@{}}",
        r"    \toprule",
        r"    Hệ & ADDIE $\uparrow$ & Trajectory $\uparrow$ & Total $\uparrow$ "
        r"& Token (k) $\downarrow$ \\",
        r"    \midrule",
        *body,
        r"    \bottomrule",
        r"  \end{tabular}",
        *table_note(*notes),
        r"\end{table}",
        "",
    ])

    # ---- Bảng II: the six alignment signals
    al = doc.get("alignment")
    if not al:
        raise SystemExit("pooled_comparison has no alignment layer: run "
                         "`./isd-exp judge alignment` on the run dir, then re-pool.")
    panel = al["stats"]["per_model"][0]["panel"]
    scols: dict[str, list[str]] = {s: [] for s in SIGNALS}
    for s, (_, sc) in SIGNALS.items():
        desc = panel.get(s, {}).get("align_descriptive", {}) or {}
        comps = {r["baseline"]: r for r in panel.get(s, {}).get("comparisons", [])}
        cells, vs = [], []
        for a in order:
            m = (desc.get(a) or {}).get("mean")
            code = AGENTS.get(a, (a, a))[1]
            mac.add(f"pan{code}{sc}", f2(m))
            cell = f2(m)
            if a != proposed:
                r = comps.get(a, {})
                cell = star(cell, r.get("p_holm"))
                mac.add(f"pan{code}{sc}Diff", f2(r.get("mean_diff")))
                mac.add(f"pan{code}{sc}P", fp(r.get("p_holm")))
            cells.append(cell)
            vs.append(m)
        scols[s] = bold_best(cells, vs)
    body = []
    for i, a in enumerate(order):
        name = AGENTS.get(a, (a, a))[0]
        body.append(f"    {name} & " + " & ".join(scols[s][i] for s in SIGNALS) + r" \\")
    tab2 = "\n".join([
        r"\begin{table}[t]",
        rf"  \caption{{Thí nghiệm 1: tín hiệu căn chỉnh (trung bình qua {n_union} kịch bản)}}",
        r"  \label{tab:panel}",
        r"  \centering",
        r"  \footnotesize",
        r"  \setlength{\tabcolsep}{3pt}",
        r"  \begin{tabular}{@{}lcccccc@{}}",
        r"    \toprule",
        r"    & \multicolumn{3}{c}{Họ A: văn bản} & \multicolumn{3}{c}{Họ B: Bloom} \\",
        r"    \cmidrule(lr){2-4}\cmidrule(l){5-7}",
        "    Hệ & " + " & ".join(h + r" $\uparrow$" for h, _ in SIGNALS.values()) + r" \\",
        r"    \midrule",
        *body,
        r"    \bottomrule",
        r"  \end{tabular}",
        *table_note(r"$^{*}$ khác AlignmentGraph-ISD, Wilcoxon theo cặp, Holm trong từng "
                    r"tín hiệu, $p<0.05$."),
        r"\end{table}",
        "",
    ])
    return tab1, tab2


# ── Bảng III: the ablation ──────────────────────────────────────────────────
def ablation_table(doc: dict, mac: Macros) -> str:
    cfg = doc["config"]
    ref = cfg["reference"]
    order = [ref] + [a for a in ARMS if a != ref]
    model = one_model(doc, "pooled_ablation")
    agents = model["agents"]
    n_union = model.get("n_scenarios_union")
    process = {p["label"]: p for p in doc.get("process", [])}.get(model["label"], {})
    arms = process.get("arms", {})
    # Closed triads per arm under failure = 0: the cell values H-S is the
    # difference of, so the column and \ablHSDiff come from the same numbers.
    triad_means = (((doc.get("registered") or {}).get("arm_means") or {})
                   .get(model["label"], {}).get("objectives_closed_triad", {}))
    mac.add("NScenAbl", str(n_union))

    cols = {"addie": [], "total": [], "triad": [], "tok": []}
    vals = {"addie": [], "total": [], "triad": []}
    for a in order:
        st = agents.get(a, {})
        pr = arms.get(a, {})
        code = ARMS[a][1]
        addie, total = st.get("mean_addie"), st.get("mean_total")
        triad = triad_means.get(a)
        tok = ((pr.get("cost") or {}).get("total_tokens") or {}).get("mean")
        cols["addie"].append(f"{f1(addie)}\\,$\\pm$\\,{f1(st.get('sd_addie_across_scenarios'))}"
                             if ok(addie) else DASH)
        cols["total"].append(f1(total))
        cols["triad"].append(pct(triad))
        cols["tok"].append(ktok(tok))
        vals["addie"].append(addie)
        vals["total"].append(total)
        vals["triad"].append(triad)
        mac.add(f"abl{code}Addie", f1(addie))
        mac.add(f"abl{code}Total", f1(total))
        mac.add(f"abl{code}Triad", pct(triad))
        mac.add(f"abl{code}Tok", ktok(tok))
        cut = (pr.get("autonomy") or {}).get("pct_stages_via_budget_exhaustion")
        mac.add(f"abl{code}Cut", f1(cut))
        repaired = (pr.get("triad_references") or {}).get("activities_repaired")
        mac.add(f"abl{code}Repaired", f1(100 * repaired) if ok(repaired) else DASH)
    for k in vals:
        cols[k] = bold_best(cols[k], vals[k])

    # the registered tests (H-D decomposition, H-S substrate) and their Holm family
    for t in (doc.get("registered") or {}).get("family", []):
        if t.get("size") != model["label"]:
            continue
        key = {"decomposition": "HD", "substrate": "HS"}.get(t.get("axis"))
        if not key:
            continue
        scale = 100 if t.get("measure") == "objectives_closed_triad" else 1
        fmt = (lambda v: f"{100 * v:.0f}") if scale == 100 else f1
        lo, hi = (t.get("ci95") or [None, None])[:2]
        mac.add(f"abl{key}Diff", fmt(t.get("mean_diff")) if ok(t.get("mean_diff")) else DASH)
        mac.add(f"abl{key}CILo", fmt(lo) if ok(lo) else DASH)
        mac.add(f"abl{key}CIHi", fmt(hi) if ok(hi) else DASH)
        mac.add(f"abl{key}CILoAbs", fmt(abs(lo)) if ok(lo) else DASH)
        mac.add(f"abl{key}P", fp(t.get("p_holm")))
        mac.add(f"abl{key}Verdict", t.get("verdict", DASH))

    body = []
    for i, a in enumerate(order):
        cells = [cols["addie"][i], cols["total"][i], cols["triad"][i], cols["tok"][i]]
        body.append(f"    {ARMS[a][0]} & " + " & ".join(cells) + r" \\")
    return "\n".join([
        r"\begin{table}[t]",
        rf"  \caption{{Thí nghiệm 2: phân rã $\times$ trạng thái ({n_union} kịch bản)}}",
        r"  \label{tab:ablation}",
        r"  \centering",
        r"  \footnotesize",
        r"  \setlength{\tabcolsep}{3pt}",
        r"  \begin{tabular}{@{}lcccc@{}}",
        r"    \toprule",
        r"    Biến thể & ADDIE $\uparrow$ & Total $\uparrow$ & Khép kín (\%) $\uparrow$ "
        r"& Token (k) $\downarrow$ \\",
        r"    \midrule",
        *body,
        r"    \bottomrule",
        r"  \end{tabular}",
        *table_note(r"Khép kín: tỉ lệ mục tiêu có đủ ba cạnh $C_2$--$C_4$ trong đầu ra."),
        r"\end{table}",
        "",
    ])


# ── disclosures read from the run dirs ──────────────────────────────────────
def _scenario_dirs(doc: dict) -> list[Path]:
    run_dirs = one_model(doc, "run dirs")["run_dirs"]
    if len(run_dirs) != 1:
        raise SystemExit(f"expected one run dir, found {len(run_dirs)}")
    root = Path(run_dirs[0])
    return sorted(p for p in root.glob("*/*") if (p / "comparison_report.json").exists())


def judge_disclosures(doc: dict, mac: Macros) -> None:
    """Spread between the three LLM judges over every judged output, and each
    judge's mean ADDIE for the proposed system and React-ADDIE."""
    proposed = doc["config"]["proposed"]
    spreads: list[float] = []
    per_judge: dict[tuple[str, str], list[float]] = {}
    for sc in _scenario_dirs(doc):
        report = json.loads((sc / "comparison_report.json").read_text(encoding="utf-8"))
        for row in report["comparison"]["rankings"]:
            judges = row["judges"]
            if isinstance(judges, str):
                judges = ast.literal_eval(judges)
            scores = [j["addie_score"] for j in judges
                      if ok(j.get("addie_score")) and not j.get("error")]
            if len(scores) >= 2:
                spreads.append(statistics.stdev(scores))
            for j, s in zip(judges, [j.get("addie_score") for j in judges]):
                if ok(s) and not j.get("error"):
                    per_judge.setdefault((row["agent_id"], j["model"]), []).append(s)
    mac.add("JudgeSD", f1(statistics.mean(spreads)) if spreads else DASH)
    for agent, acode in ((proposed, "AG"), ("react-isd", "React")):
        for model, jcode in JUDGES.items():
            vals = per_judge.get((agent, model), [])
            mac.add(f"judge{jcode}{acode}", f1(statistics.mean(vals)) if vals else DASH)


def constrained_disclosures(doc: dict, mac: Macros) -> None:
    """Constrained passes of the proposed system per scenario, and how many of
    them the validator still refused."""
    proposed = doc["config"]["proposed"]
    passes, refused = [], []
    for sc in _scenario_dirs(doc):
        path = sc / f"{proposed}_trajectory.json"
        if not path.exists():
            continue
        autonomy = json.loads(path.read_text(encoding="utf-8"))["metadata"]["autonomy"]
        stages = [v for v in autonomy.values() if isinstance(v, dict)]
        passes.append(sum(v.get("constrained_passes", 0) for v in stages))
        refused.append(sum(v.get("constrained_pass_rejected", 0) for v in stages))
    mac.add("CPass", f1(statistics.mean(passes)) if passes else DASH)
    mac.add("CPassRej", f1(statistics.mean(refused)) if refused else DASH)


def ablation_family_a(doc: dict, mac: Macros) -> None:
    """Family-A signals of the four arms (primary encoder), descriptive only."""
    root = Path(one_model(doc, "pooled_ablation")["run_dirs"][0])
    path = root / "alignment_summary.csv"
    if not path.exists():
        raise SystemExit(f"{path} not found: run `./isd-exp judge alignment` on the "
                         "ablation run dir.")
    with path.open(encoding="utf-8") as fh:
        rows = {r["agent_id"]: r for r in csv.DictReader(fh)}
    for arm, (_, code) in ARMS.items():
        r = rows.get(arm, {})
        for s, (_, sc) in list(SIGNALS.items())[:3]:
            v = r.get(s)
            mac.add(f"abl{code}{sc}", f2(float(v)) if v not in (None, "") else DASH)


def bloom_disclosure(mac: Macros) -> None:
    m = json.loads(BLOOM_METRICS.read_text(encoding="utf-8"))
    mac.add("BloomKappa", f2(m["cohen_kappa"]))
    mac.add("BloomN", str(m["n_held_out"]))


#: The pooled-file version these tables read: means and tests under failure = 0.
SCHEMA_VERSION = 2


def load_pooled(path: Path) -> dict:
    """A pooled file, refused when another pooling version wrote it: its numbers
    can share key names with a different meaning."""
    doc = json.loads(path.read_text(encoding="utf-8"))
    if doc.get("schema_version") != SCHEMA_VERSION:
        raise SystemExit(f"{path}: schema_version {doc.get('schema_version')!r}, expected "
                         f"{SCHEMA_VERSION}; re-pool it with the current ./isd-exp pool.")
    return doc


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--comparison", type=Path, default=RESULTS / "pooled_comparison.json")
    ap.add_argument("--ablation", type=Path, default=RESULTS / "pooled_ablation.json")
    ap.add_argument("--out", type=Path, default=OUT)
    args = ap.parse_args()

    args.out.mkdir(parents=True, exist_ok=True)
    mac = Macros()
    wrote = []
    bloom_disclosure(mac)
    if args.comparison.exists():
        cmp_doc = load_pooled(args.comparison)
        tab1, tab2 = comparison_tables(cmp_doc, mac)
        judge_disclosures(cmp_doc, mac)
        constrained_disclosures(cmp_doc, mac)
        (args.out / "tab_judge.tex").write_text(tab1, encoding="utf-8")
        (args.out / "tab_panel.tex").write_text(tab2, encoding="utf-8")
        wrote += ["tab_judge.tex", "tab_panel.tex"]
    else:
        print(f"skip Bảng I–II: {args.comparison} not found")
    if args.ablation.exists():
        abl_doc = load_pooled(args.ablation)
        tab3 = ablation_table(abl_doc, mac)
        ablation_family_a(abl_doc, mac)
        (args.out / "tab_ablation.tex").write_text(tab3, encoding="utf-8")
        wrote.append("tab_ablation.tex")
    else:
        print(f"skip Bảng III: {args.ablation} not found")
    mac.write(args.out / "macros.tex")
    wrote.append("macros.tex")
    print("wrote", ", ".join(str(args.out / w) for w in wrote))


if __name__ == "__main__":
    main()

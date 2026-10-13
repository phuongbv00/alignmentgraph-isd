"""What every pool checks before it reads a score: that every output was
judged, which LLM judges gave it, and whether the alignment artifact it is
about to read exists at all.

A pool runs on finished judging only. Under failure = 0 a scenario a system
left no output for scores 0, and that is the only way a score is missing: an
output nobody judged yet would otherwise be read as a failure and scored 0
against the system.

Two LLM judge rosters are never pooled together -- the median of two judges is
not the median of three, and a judge's preference for one agent over another
does not cancel in a difference. ``judge llm`` re-judges a report scored by
another roster (``judge/llm.py::report_gaps``), but a pool run before that, or
over a run dir nobody re-judged, would pool the two silently. So the pools that
feed the paper refuse, and say what to re-judge.
"""

from __future__ import annotations

from collections import Counter
from pathlib import Path

from ..config import current as current_config
from . import diagnostics


def declared() -> tuple[str, ...]:
    """The LLM judge roster ``experiment.toml [judge.llm]`` declares."""
    return tuple(m.name for m in current_config().judge.models)


def roster_problems(run_dirs: list[Path], agents: list[str] | None = None,
                    roster: tuple[str, ...] | None = None) -> tuple[list[str], int]:
    """``(cells judged by another roster, cells whose report records no judge)``.

    A cell is one (run dir, scenario, agent) row of a ``comparison_report.json``.
    A row that records no judge cannot be checked: it is counted, not refused,
    since a report written before the evaluator recorded its judges is not
    evidence of a second roster."""
    want = Counter(roster if roster is not None else declared())
    bad: list[str] = []
    unrecorded = 0
    for run_dir in run_dirs:
        for sid, scen_dir in diagnostics.scenario_dirs(run_dir):
            report = diagnostics.load_json(scen_dir / "comparison_report.json")
            if not isinstance(report, dict):
                continue
            for row in (report.get("comparison") or {}).get("rankings") or []:
                agent = row.get("agent_id")
                if agents is not None and agent not in agents:
                    continue
                models = [str(j.get("model")) for j in row.get("judges") or []
                          if j.get("model")]
                if not models:
                    unrecorded += 1
                elif want and Counter(models) != want:
                    bad.append(f"{run_dir.name}/{sid}/{agent}: "
                               f"{' + '.join(sorted(models))}")
    return bad, unrecorded


def require_declared_roster(run_dirs: list[Path], agents: list[str] | None = None,
                            *, quiet: bool = False) -> None:
    """Stop a pool that would mix LLM judge rosters, naming what to re-judge."""
    roster = declared()
    bad, unrecorded = roster_problems(run_dirs, agents, roster)
    if bad:
        shown = "\n    ".join(bad[:10]) + (f"\n    ... and {len(bad) - 10} more"
                                           if len(bad) > 10 else "")
        raise SystemExit(
            f"{len(bad)} (scenario, agent) cell(s) were judged by another LLM judge roster "
            f"than the declared {' + '.join(roster)}:\n    {shown}\n"
            "  Two rosters are never pooled together. Re-judge them first:\n"
            "    ./isd-exp judge llm '<run dir glob>'")
    if unrecorded and not quiet:
        print(f"  ! {unrecorded} report row(s) record no LLM judge: their roster cannot be "
              "checked")


def unjudged(run_dirs: list[Path], agents: list[str],
             artifact: str | None = None) -> list[str]:
    """Every (run dir, scenario) where an agent left an output that is not
    judged yet, and every scenario missing ``artifact`` when any scenario of
    the pool carries it -- across run dirs, so a whole run left unscored is
    caught. Agents that left no output are failures and belong in the pool, so
    they are never listed."""
    from ..judge import rundirs
    from ..judge.llm import report_gaps

    dirs_by_run = {run_dir: rundirs.scenario_dirs(run_dir) for run_dir in run_dirs}
    has_artifact = artifact is not None and any(
        (d / artifact).exists() for dirs in dirs_by_run.values() for d in dirs)
    out: list[str] = []
    for run_dir, dirs in dirs_by_run.items():
        for scen_dir in dirs:
            produced = tuple(rundirs.produced_agents(scen_dir, set(agents)))
            if not produced:
                continue
            gap = report_gaps(scen_dir, produced)
            if gap:
                out.append(f"{run_dir.name}/{scen_dir.name}: {gap}")
            elif has_artifact and not (scen_dir / artifact).exists():
                out.append(f"{run_dir.name}/{scen_dir.name}: no {artifact}")
    return out


def require_judged(run_dirs: list[Path], agents: list[str],
                   artifact: str | None = None) -> None:
    """Stop a pool over a run whose judging is not finished, naming what is left."""
    gaps = unjudged(run_dirs, agents, artifact)
    if gaps:
        shown = "\n    ".join(gaps[:10]) + (f"\n    ... and {len(gaps) - 10} more"
                                            if len(gaps) > 10 else "")
        raise SystemExit(
            f"{len(gaps)} scenario(s) hold an output that is not judged yet:\n    {shown}\n"
            "  A pool reads finished judging only: an unjudged output would score 0 as a\n"
            "  failure. Finish it first:\n"
            "    ./isd-exp judge llm '<run dir glob>'\n"
            "    ./isd-exp judge alignment '<run dir glob>'")


def missing_artifact(run_dirs: list[Path], artifact: str) -> dict[str, list[str]]:
    """``run dir -> alignment artifacts present`` for every run dir in which no
    scenario holds ``artifact`` (and some other alignment artifact does)."""
    out = {}
    for run_dir in run_dirs:
        present = sorted({p.name for _sid, sd in diagnostics.scenario_dirs(run_dir)
                          for p in sd.glob("alignment_scores*.json")})
        if present and artifact not in present:
            out[run_dir.name] = present
    return out


def warn_missing_artifact(run_dirs: list[Path], artifact: str, *, flag: str) -> None:
    """Say so when the alignment artifact a pool reads is absent from a run
    dir that holds others, instead of pooling it as if it had no panel."""
    for name, present in missing_artifact(run_dirs, artifact).items():
        print(f"  ! {name}: no scenario has {artifact}; present: {', '.join(present)}"
              f" -- pass {flag} to read one of them")

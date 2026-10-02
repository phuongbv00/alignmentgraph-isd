"""What every pool checks before it reads a score: which LLM judges gave it,
and whether the alignment artifact it is about to read exists at all.

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

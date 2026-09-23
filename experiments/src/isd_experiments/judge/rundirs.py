"""What both judges read: run dirs, the scenario dirs inside them, and the
scenario each one was generated from.

Shared rather than written twice, because the two judges must agree on what a
run holds. If they disagreed on which scenario dirs exist, or on who was
attempted, one judge would score a scenario the other never saw, and the two
families would be pooled over different denominators.
"""

from __future__ import annotations

import glob as globmod
import json
from pathlib import Path


def resolve(patterns: list[str] | tuple[str, ...]) -> list[Path]:
    """Run dirs named directly or by a glob, deduplicated, in the order given.

    Patterns are expanded here as well as by the shell: quoting a glob is the
    obvious thing to type, and an unexpanded pattern otherwise fails with a
    confusing "Not a directory: results/..._r[123]_*".
    """
    resolved: list[Path] = []
    unmatched: list[str] = []
    for pattern in patterns:
        hits = sorted(globmod.glob(str(pattern)))
        if hits:
            resolved += [Path(h).resolve() for h in hits]
        else:
            unmatched.append(str(pattern))
    if unmatched:
        raise SystemExit("No run dir matched: " + ", ".join(unmatched))
    not_dirs = [d for d in resolved if not d.is_dir()]
    if not_dirs:
        raise SystemExit("Not a directory: " + ", ".join(str(d) for d in not_dirs))
    run_dirs = list(dict.fromkeys(resolved))
    if not run_dirs:
        raise SystemExit("Name at least one run dir.")
    return run_dirs


def agent_filter(agents: str | list[str] | tuple[str, ...] | None) -> set[str] | None:
    """``--agents a,b`` as a set, or None for everyone the run attempted."""
    if not agents:
        return None
    items = agents.split(",") if isinstance(agents, str) else agents
    return {a.strip() for a in items if a.strip()} or None


def scenario_dirs(run_dir: Path) -> list[Path]:
    """Directories an agent was attempted in (flat run dir or nested).

    An attempt leaves ``<agent>_log.txt`` whether it succeeded or not, and
    ``<agent>_output.json`` only when it succeeded, so a scenario where every
    agent failed is still found.
    """
    markers = ("*_output.json", "*_log.txt")
    if any(any(run_dir.glob(m)) for m in markers):
        return [run_dir]
    found: set[Path] = set()
    for marker in markers:
        found |= {p.parent for p in run_dir.glob(f"*/*/{marker}")}
        found |= {p.parent for p in run_dir.glob(f"*/{marker}")}
    return sorted(found)


def attempted_agents(scenario_dir: Path, only: set[str] | None = None) -> set[str]:
    """Agents attempted in this scenario: an output on success, a log either way."""
    ids = {p.stem[: -len("_output")] for p in scenario_dir.glob("*_output.json")}
    ids |= {p.stem[: -len("_log")] for p in scenario_dir.glob("*_log.txt")}
    return ids if only is None else ids & only


def produced_agents(scenario_dir: Path, only: set[str] | None = None) -> list[str]:
    """Agents that left an output to judge, in a stable order."""
    ids = sorted(p.stem[: -len("_output")] for p in scenario_dir.glob("*_output.json"))
    return ids if only is None else [a for a in ids if a in only]


def load_scenario(scenario_dir: Path, run_dir: Path, scenario_root: Path) -> dict | None:
    """The scenario a scenario dir was generated from.

    Prefers the copy embedded in ``comparison_report.json`` (always matches the
    run), then ``<scenario_root>/<variant>/<dir_name>.json``, then any split
    holding a file of that name.
    """
    report_path = scenario_dir / "comparison_report.json"
    if report_path.exists():
        try:
            report = json.loads(report_path.read_text(encoding="utf-8"))
            scenario = report.get("scenario")
            if isinstance(scenario, dict) and scenario:
                return scenario
        except (json.JSONDecodeError, OSError):
            pass
    path = scenario_path(scenario_dir, run_dir, scenario_root)
    if path is None:
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None


def scenario_path(scenario_dir: Path, run_dir: Path, scenario_root: Path) -> Path | None:
    """The scenario FILE a scenario dir was generated from, if it can be found."""
    variant = scenario_dir.parent.name if scenario_dir != run_dir else None
    candidates = [scenario_root / f"{scenario_dir.name}.json"]
    if variant:
        candidates.insert(0, scenario_root / variant / f"{scenario_dir.name}.json")
    candidates += sorted(scenario_root.glob(f"*/{scenario_dir.name}.json"))
    return next((c for c in candidates if c.exists()), None)

"""Finding run directories and reading what is inside them.

Every default here is ABSOLUTE, resolved against ``paths.results_root()``. The
scripts this replaces used four different bases for the same idea -- one
``BENCH_ROOT.glob``, one bare ``glob.glob`` relative to the current directory,
one manual ``REPO_ROOT /`` prefix, and one ``REPO_ROOT.glob`` -- so whether a
command worked depended on which directory it was invoked from. That was
survivable while everything ran from the benchmark root; it is not survivable
now that nothing does.

A run directory is named
``<dataset>_benchmark_<model>_<tag>_<timestamp>`` and holds
``<variant>/<scenario>/`` beneath it.
"""

from __future__ import annotations

import glob as globmod
import json
import re
import sys
from pathlib import Path
from typing import Iterable, Optional

from . import paths

#: Run-dir name grammar. The tag is any token that is not the timestamp, so a
#: renamed tag namespace does not need this regex edited -- the old form pinned
#: `r\d+`, which silently folded the tag into the model label for every other
#: convention and produced a bogus model label rather than an error.
RUN_DIR_RE = re.compile(
    r"^(?P<dataset>.+)_benchmark_(?P<model>.+?)"
    r"(?:_(?P<tag>[A-Za-z]+\d*))?_(?P<ts>\d{8}_\d{6})$"
)


def parse_run_dir_name(name: str) -> dict[str, str] | None:
    """Split a run-dir name, or None when it does not match the convention."""
    m = RUN_DIR_RE.match(name)
    return m.groupdict() if m else None


def parse_size_key(model_safe: str) -> float:
    """Sort key: parameter count parsed from a model label.

    A regex rather than a lookup, so a ladder this config never declared still
    orders correctly.
    """
    matches = re.findall(r"(\d+(?:\.\d+)?)b\b", model_safe.lower())
    return float(matches[-1]) if matches else float("inf")


def resolve(patterns: Iterable[str]) -> list[Path]:
    """Expand glob patterns against the results root.

    An absolute pattern is honoured as given; a relative one is resolved
    against ``results_root()`` rather than the current directory, which is what
    makes these commands work from anywhere.
    """
    out: list[Path] = []
    for pattern in patterns:
        pat = pattern if Path(pattern).is_absolute() else str(paths.results_root() / pattern)
        out.extend(Path(p) for p in sorted(globmod.glob(pat)) if Path(p).is_dir())
    return out


def iter_scenario_dirs(run_dir: Path) -> Iterable[tuple[str, Path]]:
    """Yield (scenario_id, scenario_dir) for a run dir.

    Handles both a dataset run dir (results/<run>/<variant>/<scenario>/...)
    and a bare variant dir (results/<run>/<scenario>/...).
    """
    for child in sorted(p for p in run_dir.iterdir() if p.is_dir()):
        if (child / "comparison_report.json").exists():
            yield child.name, child          # run_dir IS the variant dir
        else:
            for scen in sorted(p for p in child.iterdir() if p.is_dir()):
                if (scen / "comparison_report.json").exists():
                    yield scen.name, scen



def load_run(run_dir: Path,
             scores_filename: str = "alignment_scores.json") -> dict[str, dict]:
    """scenario_id -> {"rankings": {agent_id: ranking}, "alignment": dict|None}.

    ``scores_filename`` selects which encoder's artifact to read. The default
    is the primary (unsuffixed) file — the only one pooled["alignment"] and
    every downstream generator know about; sweep arms pass
    ``alignment_scores.<suffix>.json``.
    """
    out: dict[str, dict] = {}
    for scenario_id, scen_dir in iter_scenario_dirs(run_dir):
        rep = scen_dir / "comparison_report.json"
        try:
            data = json.loads(rep.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as exc:
            print(f"  ! skipping unreadable report {rep}: {exc}", file=sys.stderr)
            continue
        rankings = {r["agent_id"]: r for r in data.get("comparison", {}).get("rankings", [])}
        alignment = None
        align_path = scen_dir / scores_filename
        if align_path.exists():
            try:
                alignment = json.loads(align_path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                alignment = None
        out[scenario_id] = {"rankings": rankings, "alignment": alignment}
    return out



def extract_alignment_metrics(doc, agents: list[str]) -> dict[str, dict[str, float]]:
    """Best-effort per-agent numeric metrics from an alignment_scores.json doc.

    Accepted shapes: {agent: {...}}, {"agents": {agent: {...}}},
    {"scores": {agent: {...}}}. Nested dicts flatten to dotted keys; numeric
    leaves only. Unknown shapes return {} (graceful skip).
    """
    if not isinstance(doc, dict):
        return {}
    for key in ("agents", "scores", "per_agent"):
        if isinstance(doc.get(key), dict):
            doc = doc[key]
            break
    out: dict[str, dict[str, float]] = {}
    for agent, payload in doc.items():
        if agent not in agents or not isinstance(payload, dict):
            continue
        flat: dict[str, float] = {}

        def walk(prefix: str, node) -> None:
            if isinstance(node, bool):
                return
            if isinstance(node, (int, float)):
                flat[prefix] = float(node)
            elif isinstance(node, dict):
                for k, v in node.items():
                    walk(f"{prefix}.{k}" if prefix else str(k), v)

        walk("", payload)
        if flat:
            out[agent] = flat
    return out



def group_by_glob(pattern: str) -> dict[str, list[Path]]:
    """Run dirs grouped by model label, ordered smallest model first."""
    groups: dict[str, list[Path]] = {}
    for path in resolve([pattern]):
        m = RUN_DIR_RE.match(path.name)
        if not m:
            print(f"  ! dir does not match naming convention, skipped: {path.name}", file=sys.stderr)
            continue
        groups.setdefault(m.group("model"), []).append(path)
    return dict(sorted(groups.items(), key=lambda kv: parse_size_key(kv[0])))


